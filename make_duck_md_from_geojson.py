#!/usr/bin/env python3
"""
Create missing duck Markdown files from map.geojson.

- Reads: map.geojson (in the same directory as this script by default, override with --geojson)
- Writes: ducks/<slug>.md for features that don't already exist
- The file name slug is derived from properties["name"] (lowercase, non-alnum -> "-")
- Frontmatter mirrors chewduckka.md keys when available:
    title, pic_url, umap_url, from, status, description, city, date, number
- Field mapping from GeoJSON properties (fallbacks):
    title     <- name
    pic_url   <- pic_url | picture | image | photo | url (if it's an image) 
    umap_url  <- umap_url (left empty if not present; if geometry exists, an OSM link is added)
    from      <- from | author | by
    status    <- status
    description <- description | desc
    city      <- city | place | location
    date      <- date
    number    <- number (if not present, autoincrement after the current max found in existing ducks)
    
Usage:
    python make_duck_md_from_geojson.py --geojson path/to/map.geojson --out ducks
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Any, List

try:
    import yaml  # type: ignore
except Exception:
    raise SystemExit("Please 'pip install pyyaml' to run this script.")

FRONTMATTER_KEYS = ["title","pic_url","umap_url","from","status","description","city","date","number"]

def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")

def is_image_url(u: str) -> bool:
    return bool(re.search(r"\.(png|jpe?g|webp|gif|svg)(\?.*)?$", u, re.I))

def load_existing_numbers(ducks_dir: Path) -> int:
    """Scan existing duck .md files and return max 'number' found (int)."""
    max_num = 0
    for md in ducks_dir.glob("*.md"):
        try:
            with md.open("r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("---"):
                _, fm, _ = content.split("---", 2)
                data = yaml.safe_load(fm) or {}
                num = data.get("number")
                if isinstance(num, int):
                    max_num = max(max_num, num)
                elif isinstance(num, str) and num.isdigit():
                    max_num = max(max_num, int(num))
        except Exception:
            continue
    return max_num

def build_umap_or_osm_url(props: Dict[str, Any], geom: Dict[str, Any]) -> str:
    if "umap_url" in props and isinstance(props["umap_url"], str):
        return props["umap_url"]
    # fallback: build an OpenStreetMap link if we have geometry
    try:
        if geom and geom.get("type") == "Point":
            lon, lat = geom.get("coordinates", [None, None])
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.6f}/{lon:.6f}"
    except Exception:
        pass
    return ""

def pick_pic_url(props: Dict[str, Any]) -> str:
    for key in ["pic_url","picture","image","photo"]:
        v = props.get(key)
        if isinstance(v, str) and v:
            return v
    # sometimes "url" might be an image; check extension
    v = props.get("url")
    if isinstance(v, str) and is_image_url(v):
        return v
    return ""

def map_properties_to_frontmatter(props: Dict[str, Any], geom: Dict[str, Any], next_number: int) -> Dict[str, Any]:
    data = {}
    name = props.get("name") or ""
    data["title"] = name

    data["pic_url"] = pick_pic_url(props)
    data["umap_url"] = build_umap_or_osm_url(props, geom)

    data["from"] = props.get("from") or props.get("author") or props.get("by") or ""
    data["status"] = props.get("status") or ""

    data["description"] = props.get("description") or props.get("desc") or ""

    data["city"] = props.get("city") or props.get("place") or props.get("location") or ""
    data["date"] = props.get("date") or ""

    number = props.get("number")
    if isinstance(number, int):
        data["number"] = number
    elif isinstance(number, str) and number.isdigit():
        data["number"] = int(number)
    else:
        data["number"] = next_number

    return data

def render_markdown(frontmatter: Dict[str, Any]) -> str:
    # Keep the same structure as chewduckka.md (including the Jinja vars in the body)
    # Ensure numbers are plain int in YAML
    fm_dump = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    body = f"""---
{fm_dump}
---
# Duck {{ {{ page.meta.number }} }}: {{ {{ page.meta.title }} }}

<img src="{{ {{ page.meta.pic_url }} }}" alt="{{ {{ page.meta.title }} }}" width="600">

**Place:** {{ {{ page.meta.city }} }}

**Status:** {{ {{ page.meta.status }} }}

**From:** {{ {{ page.meta.from }} }}

## Description

{{ {{ page.meta.description }} }}

**umap:** [Link]({{ {{ page.meta.umap_url }} }})
""".rstrip() + "\n"
    return body

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", type=Path, default=Path("map.geojson"))
    ap.add_argument("--out", type=Path, default=Path("ducks"))
    ap.add_argument("--dry-run", action="store_true", help="Do not write files, just print actions")
    args = ap.parse_args()

    if not args.geojson.exists():
        raise SystemExit(f"GeoJSON not found: {args.geojson}")

    args.out.mkdir(parents=True, exist_ok=True)

    with args.geojson.open("r", encoding="utf-8") as f:
        geo = json.load(f)

    existing_max = load_existing_numbers(args.out)
    created = []
    skipped = []

    next_number = existing_max + 1

    for feat in geo.get("features", []):
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry", {}) or {}

        name = props.get("name")
        if not isinstance(name, str) or not name.strip():
            # skip features without a proper name
            continue

        slug = slugify(name)
        out_file = args.out / f"{slug}.md"

        if out_file.exists():
            skipped.append(out_file.name)
            continue

        fm = map_properties_to_frontmatter(props, geom, next_number)
        # Only increment next_number if we assigned one (i.e., original had none)
        if fm.get("number") == next_number:
            next_number += 1

        content = render_markdown(fm)

        if args.dry_run:
            print(f"[DRY] would create: {out_file.name}")
        else:
            with out_file.open("w", encoding="utf-8") as f:
                f.write(content)
            created.append(out_file.name)

    print(f"Created: {len(created)} file(s)")
    for c in created:
        print(" -", c)
    if skipped:
        print(f"Skipped (already exist): {len(skipped)}")
        for s in skipped:
            print(" -", s)

if __name__ == "__main__":
    main()
