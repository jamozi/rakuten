#!/usr/bin/env python3
"""Offline checks of anonymous public responses; no network or CMS writes.

Input is a RAOSAnonymousPageBatchV1 JSON export, not owner-private snapshots.
PASS means only the listed checks passed. It is not proof of indexing, legal
compliance, product accuracy, merchant availability, conversions or revenue.
No outbound URLs, article prose or account identifiers appear in the report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit

ORIGIN = 'https://kurashinoshirube.com'
HOST = 'kurashinoshirube.com'
MAX_BYTES = 24 * 1024 * 1024
AFFILIATE_HOSTS = frozenset({
    'hb.afl.rakuten.co.jp', 'af.moshimo.com', 'px.a8.net',
    'ck.jp.ap.valuecommerce.com', 'click.linksynergy.com',
    'h.accesstrade.net', 't.afi-b.com',
})
VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
DISCLOSURE = re.compile(r'広告[・をが]|アフィリエイトリンク[をが]|広告を含|広告が含')


def _path(value):
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        raise ValueError('PATH_INVALID')
    decoded = unquote(value)
    if any(c in decoded for c in ('\\', '\r', '\n', '\x00')):
        raise ValueError('PATH_INVALID')
    parsed = urlsplit(decoded)
    if parsed.netloc or parsed.scheme or parsed.query or parsed.fragment or '..' in parsed.path.split('/'):
        raise ValueError('PATH_INVALID')
    return value


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.position = 0
        self.ids = []
        self.robots = []
        self.canonicals = []
        self.h1_count = 0
        self.title = []
        self.description = []
        self.links = []
        self.disclosures = []
        self.visible_text = []
        self.cost_container = False
        self.cost_script = False
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.position += 1
        attributes = dict(attrs)
        hidden = (any(x[1] for x in self.stack) or 'hidden' in attributes
                  or attributes.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attributes.get('style') or '', re.I))
                  or tag in {'script', 'style', 'template', 'noscript'})
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if tag == 'h1':
            self.h1_count += 1
        if tag == 'meta':
            name = (attributes.get('name') or '').lower()
            if name in {'robots', 'googlebot'}:
                self.robots.append(attributes.get('content') or '')
            if name == 'description':
                self.description.append(attributes.get('content') or '')
        if tag == 'link' and 'canonical' in (attributes.get('rel') or '').lower().split():
            self.canonicals.append(attributes.get('href') or '')
        if tag == 'a' and attributes.get('href') and not hidden:
            self.links.append((attributes['href'], set((attributes.get('rel') or '').lower().split()), self.position))
        if attributes.get('data-raos-cost-calculator') == 'v1':
            self.cost_container = True
        if tag == 'script':
            parsed = urlsplit(urljoin(ORIGIN, attributes.get('src') or ''))
            if parsed.scheme == 'https' and parsed.hostname == HOST and parsed.path.endswith('/local-running-cost.js'):
                self.cost_script = True
        if tag not in VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.position += 1
        if any(tag == 'title' for tag, _ in self.stack):
            self.title.append(data)
        if not any(hidden for _, hidden in self.stack):
            self.visible_text.append(data)
            if DISCLOSURE.search(data):
                self.disclosures.append(self.position)


def assess(observations, expected_paths, *, sitemap_paths=None):
    """Assess full HTML observations without trusting HTTP 200 as completion."""
    if not isinstance(observations, list) or not isinstance(expected_paths, list):
        raise ValueError('BATCH_INVALID')
    if not 1 <= len(expected_paths) <= 64 or len(observations) > 64:
        raise ValueError('BATCH_SIZE_INVALID')
    expected = [_path(path) for path in expected_paths]
    if len(expected) != len(set(expected)):
        raise ValueError('EXPECTED_PATH_DUPLICATE')
    observed = {}
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError('OBSERVATION_INVALID')
        path = _path(row.get('path'))
        if path not in expected or path in observed:
            raise ValueError('OBSERVATION_TARGET_INVALID')
        observed[path] = row
    sitemap = None if sitemap_paths is None else {_path(path) for path in sitemap_paths}
    findings = []
    pages = {}
    details = {}

    def note(path, code, level='failure'):
        item = {'path': path, 'code': code, 'level': level}
        if item not in findings:
            findings.append(item)

    for path in expected:
        row = observed.get(path)
        if row is None or row.get('status') is None:
            note(path, 'RESPONSE_UNAVAILABLE', 'unknown')
            continue
        if type(row['status']) is not int or row['status'] != 200:
            note(path, 'HTTP_NOT_200')
            continue
        text = row.get('html')
        if row.get('full_html') is not True or not isinstance(text, str) or not text.strip():
            note(path, 'FULL_HTML_UNAVAILABLE', 'unknown')
            continue
        if len(text.encode('utf-8')) > 4 * 1024 * 1024:
            raise ValueError('HTML_TOO_LARGE')
        lower = text.lower()
        if not all(token in lower for token in ('<html', '</html>', '<head', '</head>', '<body', '</body>')):
            note(path, 'FULL_HTML_UNAVAILABLE', 'unknown')
            continue
        if row.get('final_url') != ORIGIN + path:
            note(path, 'FINAL_URL_NOT_SELF')
        doc = Page(text)
        pages[path] = doc
        headers = row.get('headers', {})
        if not isinstance(headers, dict):
            raise ValueError('HEADERS_INVALID')
        robots = list(doc.robots)
        robots.extend(str(value) for key, value in headers.items() if str(key).lower() == 'x-robots-tag')
        directives = set(re.findall(r'[a-z-]+', ','.join(robots).lower()))
        if {'noindex', 'none'} & directives:
            note(path, 'NOINDEX')
        if {'nofollow', 'none'} & directives:
            note(path, 'PAGE_NOFOLLOW')
        if len(doc.canonicals) != 1:
            note(path, 'CANONICAL_MISSING_OR_DUPLICATE')
        elif doc.canonicals[0] != ORIGIN + path:
            note(path, 'CANONICAL_NOT_SELF')
        if doc.h1_count != 1:
            note(path, 'H1_COUNT')
        if any(count > 1 for count in Counter(doc.ids).values()):
            note(path, 'DUPLICATE_ID')
        if not ''.join(doc.title).strip():
            note(path, 'TITLE_MISSING')
        if len(doc.description) != 1 or not doc.description[0].strip():
            note(path, 'DESCRIPTION_MISSING_OR_DUPLICATE')
        if '現在、条件に合う公開記事はありません' in ''.join(doc.visible_text):
            note(path, 'EMPTY_LISTING')
        paid = [(rel, pos) for href, rel, pos in doc.links
                if (urlsplit(urljoin(ORIGIN + path, href)).hostname or '').lower() in AFFILIATE_HOSTS]
        if any(not ({'sponsored', 'nofollow'} & rel) for rel, _ in paid):
            note(path, 'AFFILIATE_REL_MISSING')
        if paid and not any(pos < min(p for _, p in paid) for pos in doc.disclosures):
            note(path, 'DISCLOSURE_NOT_BEFORE_LINK')
        if doc.cost_container:
            if not doc.cost_script:
                note(path, 'COST_SCRIPT_MISSING')
            elif row.get('browser_checks', {}).get('cost_calculation_verified') is not True:
                note(path, 'COST_INTERACTION_UNVERIFIED', 'unknown')
        if sitemap is not None and path not in sitemap:
            note(path, 'SITEMAP_MISSING')
        details[path] = {'affiliate_links': len(paid), 'h1_count': doc.h1_count,
                         'cost_container': doc.cost_container, 'cost_script': doc.cost_script}

    for path, doc in pages.items():
        for href, _, _ in doc.links:
            target = urlsplit(urljoin(ORIGIN + path, href))
            if target.hostname != HOST or target.scheme not in {'http', 'https'} or target.query or not target.fragment:
                continue
            target_path = target.path or '/'
            if target_path not in pages:
                note(path, 'ANCHOR_TARGET_UNCHECKED', 'unknown')
            elif unquote(target.fragment) not in pages[target_path].ids:
                note(path, 'ANCHOR_MISSING')
    levels = {finding['level'] for finding in findings}
    return {
        'schema': 'RAOSPublicAcceptanceV1', 'publication_authority': False,
        'status': 'FAIL' if 'failure' in levels else 'INCOMPLETE' if 'unknown' in levels else 'PASS',
        'expected_pages': len(expected), 'parsed_pages': len(pages),
        'findings': findings, 'page_checks': details,
        'not_verified': ['actual_search_indexing', 'merchant_stock_and_prices', 'product_accuracy',
                         'legal_compliance', 'conversion_and_profit', 'visual_layout', 'consent_runtime'],
        'sitemap_checked': sitemap is not None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Anonymous response export; omit to read stdin')
    args = parser.parse_args(argv)
    try:
        if args.input:
            if args.input.is_symlink() or not args.input.is_file() or args.input.stat().st_size > MAX_BYTES:
                raise ValueError('INPUT_INVALID')
            raw = args.input.read_bytes()
        else:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('INPUT_TOO_LARGE')
        batch = json.loads(raw)
        if not isinstance(batch, dict) or batch.get('schema') != 'RAOSAnonymousPageBatchV1':
            raise ValueError('INPUT_SCHEMA_INVALID')
        report = assess(batch['observations'], batch['expected_paths'], sitemap_paths=batch.get('sitemap_paths'))
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return {'PASS': 0, 'FAIL': 1, 'INCOMPLETE': 2}[report['status']]
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        print('{"status":"INCOMPLETE","error":"INPUT_INVALID","publication_authority":false}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
