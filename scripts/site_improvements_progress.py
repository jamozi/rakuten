#!/usr/bin/env python3
"""Copy the owner's audit workbook and append evidence-backed progress columns."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
N = {"m": NS}
ET.register_namespace("x", NS)
ET.register_namespace(
    "r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
ID = re.compile(r"(?:G\d{2}|PG\d{3}-\d{2}|Q\d{2})\Z")
HEADERS = [
    "実装状況（今回）",
    "根拠・変更箇所",
    "検証（local / baseline / external）",
    "残る条件",
    "候補・公開版",
]


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(cell.find("m:is", N).itertext())
    value = cell.find("m:v", N)
    if value is None:
        return ""
    return strings[int(value.text)] if cell.get("t") == "s" else (value.text or "")


def workbook_rows(path: Path) -> dict[str, dict[str, str]]:
    with zipfile.ZipFile(path) as book:
        strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            strings = [
                "".join(e.itertext())
                for e in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(
                    "m:si", N
                )
            ]
        rows = {}
        for row in ET.fromstring(book.read("xl/worksheets/sheet3.xml")).findall(
            ".//m:sheetData/m:row", N
        ):
            values = {
                re.sub(r"\d", "", c.get("r", "")): cell_text(c, strings)
                for c in row.findall("m:c", N)
            }
            ident = values.get("A", "")
            if ID.fullmatch(ident):
                if ident in rows:
                    raise ValueError("Duplicate audit ID")
                rows[ident] = values
        return rows


def column(number: int) -> str:
    result = ""
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def validation_text(item: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in item["validation"].items())


def append_columns(xml: bytes, strings: list[str], items: dict, start: int) -> bytes:
    root = ET.fromstring(xml)
    rows = root.findall(".//m:sheetData/m:row", N)
    for row in rows:
        values = {
            re.sub(r"\d", "", c.get("r", "")): cell_text(c, strings)
            for c in row.findall("m:c", N)
        }
        ident = values.get("A", "")
        if ident == "ID":
            texts = HEADERS
        elif ident in items:
            item = items[ident]
            texts = [
                item["implementation"],
                "\n".join(item["evidence"]),
                validation_text(item),
                item["residual"],
                item["publication_version"],
            ]
        else:
            continue
        style = row.findall("m:c", N)[-1].get("s", "0")
        for offset, text in enumerate(texts):
            cell = ET.SubElement(
                row,
                f"{{{NS}}}c",
                {
                    "r": f"{column(start + offset)}{row.get('r')}",
                    "s": style,
                    "t": "inlineStr",
                },
            )
            inline = ET.SubElement(cell, f"{{{NS}}}is")
            ET.SubElement(inline, f"{{{NS}}}t").text = text
    last_row = max(int(r.get("r")) for r in rows)
    dimension = root.find("m:dimension", N)
    if dimension is not None:
        dimension.set("ref", f"A1:{column(start + 4)}{last_row}")
    columns = root.find("m:cols", N)
    if columns is not None:
        for offset, width in enumerate([38, 64, 76, 70, 42]):
            ET.SubElement(
                columns,
                f"{{{NS}}}col",
                {
                    "min": str(start + offset),
                    "max": str(start + offset),
                    "width": str(width),
                    "customWidth": "1",
                },
            )
    autofilter = root.find("m:autoFilter", N)
    if autofilter is not None:
        first = autofilter.get("ref").split(":")[0]
        autofilter.set("ref", f"{first}:{column(start + 4)}{last_row}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def apply_validation(items: dict, path: Path) -> None:
    report = json.loads(path.read_text())
    if report.get("schema") == "RAOSSiteImprovementsReadOnlyAuditV1":
        if report.get("mode") == "public-baseline":
            raise ValueError(
                "Public baseline cannot be applied as candidate validation"
            )
        categories = {
            "Q01": {"HTTP_NOT_200"},
            "Q02": {
                "TITLE_EMPTY",
                "CANONICAL_PATH_MISMATCH",
                "CANONICAL_ORIGIN_MISMATCH",
            },
            "Q05": {"INVALID_JSON_LD"},
            "Q06": {"BROKEN_INTERNAL_ANCHORS"},
            "Q08": {"IMAGE_UNLOADED", "IMAGE_UPSCALED"},
            "Q12": {"HORIZONTAL_OVERFLOW"},
        }
        for ident, codes in categories.items():
            failures = [
                r["post_id"]
                for r in report["rows"]
                if any(
                    f in codes
                    or f == "NAVIGATION_OR_DOM_FAILURE"
                    or f.startswith("H1_COUNT_")
                    and ident == "Q02"
                    for f in r.get("failures", [])
                )
            ]
            items[ident]["validation"]["local"] = (
                f"取得{len(report['rows'])}/34ページ（{report.get('viewport_scope')}）。対象検査の検出: {failures or 'なし'}。当該Qの全受入条件合格を意味しない。"
            )
            items[ident]["evidence"].append(str(path))
    else:
        for ident, updates in report.get("items", {}).items():
            if ident not in items:
                raise ValueError(f"Unknown ID in validation report: {ident}")
            for key in ("implementation", "residual"):
                if key in updates:
                    items[ident][key] = updates[key]
            if "validation" in updates:
                items[ident]["validation"].update(updates["validation"])
            items[ident]["evidence"].extend(updates.get("evidence", []))


def build(
    source: Path,
    mapping: Path,
    output_dir: Path,
    validation: Path | None = None,
    candidate: str | None = None,
) -> dict:
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    inventory = workbook_rows(source)
    data = json.loads(mapping.read_text())
    items = data["items"]
    if len(inventory) != 136 or set(items) != set(inventory):
        raise ValueError("Mapping must match all 136 workbook IDs exactly")
    if validation:
        apply_validation(items, validation)
    for item in items.values():
        item["publication_version"] = (
            f"候補 {candidate}／未公開・本番反映照合未実施"
            if candidate
            else "候補未固定／未公開・本番反映照合未実施"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = (
        output_dir / "kurashinoshirube_all_pages_improvements_20260913_progress.xlsx"
    )
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite original workbook")
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as result,
    ):
        strings = []
        if "xl/sharedStrings.xml" in original.namelist():
            strings = [
                "".join(e.itertext())
                for e in ET.fromstring(original.read("xl/sharedStrings.xml")).findall(
                    "m:si", N
                )
            ]
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet3.xml":
                content = append_columns(content, strings, items, 13)
            elif entry.filename == "xl/worksheets/sheet4.xml":
                content = append_columns(content, strings, items, 8)
            result.writestr(entry, content)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise RuntimeError("Original workbook changed")
    if workbook_rows(destination).keys() != inventory.keys():
        raise ValueError("Output IDs changed")
    counts = Counter(item["implementation"].split("：")[0] for item in items.values())
    lines = [
        "# 全136項目の対応進捗",
        "",
        "元Excelは変更していません。既存の『状態』列は元監査時点、新しい5列が今回の進捗です。ローカル実装・検証・既存本番baseline・公開を分けています。",
        "",
        f"対象136件／実装状況内訳：{dict(counts)}",
        "",
        "候補・公開：" + next(iter(items.values()))["publication_version"],
        "",
        "GSC・GA4アカウント設定・ASP実注文/確定報酬はUNAVAILABLE。問い合わせ下書きは未送信です。",
        "",
        "| ID | 項目 | 実装 | 検証 | 残る条件 | 根拠 |",
        "|---|---|---|---|---|---|",
    ]

    def esc(value: object) -> str:
        return str(value).replace("|", "／").replace("\n", "<br>")

    for ident, item in items.items():
        lines.append(
            "| "
            + " | ".join(
                map(
                    esc,
                    [
                        ident,
                        item["title"],
                        item["implementation"],
                        validation_text(item),
                        item["residual"],
                        "; ".join(item["evidence"]),
                    ],
                )
            )
            + " |"
        )
    (output_dir / "progress.md").write_text("\n".join(lines) + "\n")
    (output_dir / "progress-resolved.json").write_text(
        json.dumps(
            {
                **data,
                "items": items,
                "source_sha256": before,
                "original_unchanged": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return {
        "items": len(items),
        "original_unchanged": True,
        "workbook": str(destination),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(
            "/mnt/c/Users/naoki/Downloads/kurashinoshirube_all_pages_improvements_20260913.xlsx"
        ),
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("changes/site-improvements-20260913/progress-evidence.v1.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output/site-improvements-20260913")
    )
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--candidate")
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.source,
                args.mapping,
                args.output_dir,
                args.validation_report,
                args.candidate,
            ),
            ensure_ascii=False,
        )
    )
