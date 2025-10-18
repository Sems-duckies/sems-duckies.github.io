#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erzeugt aus doc/Ducks/*.md eine Galerie 'gallery.md' mit Lightbox:
- Bild-Klick öffnet Lightbox (glightbox)
- Titel/Caption-Klick führt zur jeweiligen Duck-Seite
Voraussetzung: mkdocs-glightbox Plugin in mkdocs.yml aktiviert.
"""

from pathlib import Path
import re
from typing import Dict, Optional

DUCKS_DIR = Path("doc/ducks")
GALLERY_FILE = DUCKS_DIR / "gallery.md"
GALLERY_TITLE = "Duck Gallery"
EXCLUDES = {"index.md", "gallery.md"}

IMAGE_KEYS = ["picture_url", "pic_url", "image", "image_url"]
TITLE_KEYS = ["title", "duck_title", "name"]

FRONTMATTER_PATTERN = re.compile(r"^\s*---\s*\n(.*?)\n---\s*", re.DOTALL | re.MULTILINE)

def parse_frontmatter(md_text: str) -> Dict[str, str]:
    m = FRONTMATTER_PATTERN.search(md_text)
    if not m:
        return {}
    block = m.group(1)
    data: Dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        data[key] = val
    return data

def get_ci(d: Dict[str, str], keys: list[str]) -> Optional[str]:
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v and str(v).strip():
            return str(v).strip()
    return None

def build_card(title: str, img_url: str, md_stem: str) -> str:
    alt = (title or md_stem).replace('"', '&quot;')
    # VORHER: page_link = f"./{md_stem}/"   -> ergab /ducks/gallery/{md_stem}/
    page_link = f"../{md_stem}/"            # ergibt /ducks/{md_stem}/
    return f"""
- <figure markdown>
    <img src="{img_url}" alt="{alt}">
    <figcaption><a href="{page_link}">{alt}</a></figcaption>
  </figure>
""".strip()


def main():
    if not DUCKS_DIR.exists():
        raise SystemExit(f"Ordner nicht gefunden: {DUCKS_DIR}")

    ducks = []
    for md in DUCKS_DIR.glob("*.md"):
        if md.name in EXCLUDES:
            continue
        txt = md.read_text(encoding="utf-8", errors="ignore")
        fm = parse_frontmatter(txt)

        title = get_ci(fm, TITLE_KEYS) or md.stem
        img = get_ci(fm, IMAGE_KEYS)
        if not img:
            continue
        ducks.append((title, img, md.stem))

    ducks.sort(key=lambda t: t[0].casefold())

    items = "\n".join(build_card(t, img, stem) for t, img, stem in ducks)

    # Galerie-Seite: Material Grid (cards) + Markdown-Listentricks
    page = f"""---
title: {GALLERY_TITLE}
---

# {GALLERY_TITLE}

<div class="grid cards" markdown>

{items}

</div>
"""
    GALLERY_FILE.write_text(page.strip() + "\n", encoding="utf-8")
    print(f"Galerie erzeugt: {GALLERY_FILE} – {len(ducks)} Einträge")

if __name__ == "__main__":
    main()
