import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS,
  createPublicationReviewWorkspaceV2,
  renderPublicationReviewWorkspaceHtmlV2,
} from '../../packages/web-ui/src/index.ts';

describe('ST-0906 V2 deterministic semantic HTML renderer', () => {
  it('renders the same standalone script-free document byte-for-byte', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'PUBA-002' });
    const first = renderPublicationReviewWorkspaceHtmlV2(model);
    const second = renderPublicationReviewWorkspaceHtmlV2(model);
    assert.equal(first, second);
    assert.match(first, /^<!doctype html>\n<html lang="ja-JP">/u);
    assert.match(first, /<meta name="robots" content="noindex,nofollow,noarchive">/u);
    assert.match(first, /Content-Security-Policy/u);
    assert.doesNotMatch(first, /<script\b|<iframe\b|<form\b|<input\b|<textarea\b/iu);
    assert.doesNotMatch(first, /\bon(?:click|submit|load|error)\s*=/iu);
    assert.doesNotMatch(first, /javascript:|fetch\s*\(|XMLHttpRequest|WebSocket/iu);
  });

  it('renders one H1, skip navigation, labelled sections and a keyboard-scrollable diff table', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'REV-002' });
    const html = renderPublicationReviewWorkspaceHtmlV2(model);
    assert.equal((html.match(/<h1\b/gu) ?? []).length, 1);
    assert.match(html, /class="skip-link" href="#publication-review-v2-main"/u);
    assert.match(html, /<main id="publication-review-v2-main" tabindex="-1"/u);
    assert.match(html, /<nav aria-label="Publication review sections">/u);
    for (const sectionId of PUBLICATION_REVIEW_WORKSPACE_V2_SECTION_IDS) {
      assert.match(html, new RegExp(`<section id="${sectionId}"`, 'u'));
      assert.match(html, new RegExp(`href="#${sectionId}"`, 'u'));
    }
    assert.match(html, /<caption>ST-0903 immutable snapshot to ST-0904 public projection/u);
    assert.equal((html.match(/<th scope="col">/gu) ?? []).length, 7);
    assert.equal((html.match(/<th scope="row">/gu) ?? []).length, 10);
    assert.equal((html.match(/<h4 id="preview-/gu) ?? []).length, 9);
    assert.match(html, /class="table-scroll" tabindex="0"/u);
    assert.match(html, /:focus-visible\{outline:3px solid/u);
  });

  it('shows immutable hashes, text-only preview, audit states and three disabled actions', () => {
    const model = createPublicationReviewWorkspaceV2({ screenId: 'PUBA-004' });
    const html = renderPublicationReviewWorkspaceHtmlV2(model);
    assert.match(html, new RegExp(model.snapshot.snapshotSha256, 'u'));
    assert.match(html, new RegExp(model.finalApproval.canonicalAstSha256, 'u'));
    assert.match(html, /EXACT_RECORDED_BINDINGS_VERIFIED/u);
    assert.match(html, /NOT_ESTABLISHED_RECONCILIATION_REQUIRED/u);
    assert.match(html, /PROCESS_LOCAL_NOT_PERSISTED_NOT_EMITTED/u);
    assert.equal((html.match(/<button type="button" disabled/gu) ?? []).length, 3);
    assert.equal((html.match(/UI dispatch は無効です。/gu) ?? []).length, 3);
    assert.doesNotMatch(html, /<img\b|Product|Offer|AggregateRating/iu);
  });
});
