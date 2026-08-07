from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "output" / "doc" / "raos_human_work_support_pack_ja-JP.pdf"
RENDER_DIR = ROOT / "tmp" / "docs" / "rendered_support_pack"


def main() -> None:
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    document = fitz.open(PDF)
    thumbnails: list[Image.Image] = []
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
        page_path = RENDER_DIR / f"page-{index + 1:02d}.png"
        pixmap.save(page_path)
        image = Image.open(page_path).convert("RGB")
        image.thumbnail((300, 424))
        framed = Image.new("RGB", (320, 465), "white")
        framed.paste(image, ((320 - image.width) // 2, 28))
        draw = ImageDraw.Draw(framed)
        draw.text((12, 7), f"Page {index + 1}", fill="#17324D")
        thumbnails.append(framed)

    for sheet_index in range(0, len(thumbnails), 12):
        group = thumbnails[sheet_index : sheet_index + 12]
        columns = 3
        rows = (len(group) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * 320, rows * 465), "#DDE3EA")
        for item_index, image in enumerate(group):
            x = (item_index % columns) * 320
            y = (item_index // columns) * 465
            sheet.paste(image, (x, y))
        sheet.save(RENDER_DIR / f"contact-{sheet_index // 12 + 1}.png")

    print(f"pages={len(document)}")
    print(f"render_dir={RENDER_DIR}")


if __name__ == "__main__":
    main()
