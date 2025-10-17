#!/usr/bin/env python3
"""
Create missing duck Markdown files from map.geojson.

Changes:
- Render literal Jinja tags like {{ page.meta.title }} exactly in the MD body.
- Quote ALL frontmatter values with double quotes, including numbers/booleans.

Usage:
    python make_duck_md_from_geojson.py --geojson path/to/map.geojson --out ducks
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Any

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
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    _, fm, _ = parts
                    import yaml as _yaml
                    data = _yaml.safe_load(fm) or {}
                    num = data.get("number")
                    if isinstance(num, int):
                        max_num = max(max_num, num)
                    elif isinstance(num, str) and num.isdigit():
                        max_num = max(max_num, int(num))
        except Exception:
            continue
    return max_num

def build_umap_or_osm_url(props: Dict[str, Any], geom: Dict[str, Any]) -> str:
    if isinstance(props.get("umap_url"), str):
        return props["umap_url"]
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
    v = props.get("url")
    if isinstance(v, str) and is_image_url(v):
        return v
    return ""

def map_properties_to_frontmatter(props: Dict[str, Any], geom: Dict[str, Any], next_number: int) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
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
        data["number"] = str(number)
    elif isinstance(number, str) and number.strip():
        data["number"] = number.strip()
    else:
        data["number"] = str(next_number)

    ordered = {k: data.get(k, "") for k in FRONTMATTER_KEYS}
    return ordered

class QuotedStr(str):
    """Marker class so PyYAML always double-quotes our strings."""

def _quoted_str_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data), style='"')

yaml.add_representer(QuotedStr, _quoted_str_representer)
# Ensure SafeDumper knows how to handle QuotedStr
try:
    from yaml import SafeDumper
    SafeDumper.add_representer(QuotedStr, _quoted_str_representer)
except Exception:
    pass

def quote_all_values(d: Dict[str, Any]) -> Dict[str, QuotedStr]:
    q: Dict[str, QuotedStr] = {}
    for k, v in d.items():
        if v is None:
            v = ""
        q[k] = QuotedStr(str(v))
    return q

def yaml_dump_quoted(d: Dict[str, Any]) -> str:
    quoted = quote_all_values(d)
    return yaml.safe_dump(quoted, sort_keys=False, allow_unicode=True).strip()

def render_markdown(frontmatter: Dict[str, Any]) -> str:
    fm_dump = yaml_dump_quoted(frontmatter)
    parts = []
    parts.append("---")
    parts.append(fm_dump)
    parts.append("---")
    parts.append("# Duck {{ page.meta.number }}: {{ page.meta.title }}")
    parts.append("")
    parts.append("<img src=\"{{ page.meta.pic_url }}\" alt=\"{{ page.meta.title }}\" width=\"600\">")
    parts.append("")
    parts.append("**Place:** {{ page.meta.city }}")
    parts.append("")
    parts.append("**Status:** {{ page.meta.status }}")
    parts.append("")
    parts.append("**From:** {{ page.meta.from }}")
    parts.append("")
    parts.append("## Description")
    parts.append("")
    parts.append("{{ page.meta.description }}")
    parts.append("")
    parts.append("**umap:** [Link]({{ page.meta.umap_url }})")
    parts.append("")
    return "\n".join(parts)

def main():
    import argparse
    import json
    from pathlib import Path

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
            continue

        slug = slugify(name)
        out_file = args.out / f"{slug}.md"

        if out_file.exists():
            skipped.append(out_file.name)
            continue

        fm = map_properties_to_frontmatter(props, geom, next_number)
        if fm.get("number") == str(next_number):
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
