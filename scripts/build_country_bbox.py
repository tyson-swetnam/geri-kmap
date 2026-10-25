#!/usr/bin/env python3
"""Build schema/vocab/country_bbox.csv from Natural Earth admin-0 countries.

qa.py checks every facility's point against its country's boxes. A
country is one box per polygon part (French Guiana and Réunion are their
own boxes, not one box spanning half the planet), padded by ``--pad``
degrees so a coastal station does not read as misplaced. A part that crosses the antimeridian is split into two boxes.

Source: Natural Earth 1:10m admin-0 countries (1:50m drops small islands
such as Lampedusa) (public domain), via the
natural-earth-vector repository. ``ISO_A2_EH`` is used because ``ISO_A2``
is ``-99`` for France and Norway in current releases.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "schema" / "vocab" / "country_bbox.csv"
NAMES_OUT = ROOT / "schema" / "vocab" / "country_names.csv"
# Registry spellings Natural Earth does not carry, mapped to the ISO-2 code
# whose Natural Earth polygon holds the place. ISO 3166 short names for
# DEIMS; overseas departments go to FR because Natural Earth draws them as
# parts of France.
ALIASES = {
    "Congo (the Democratic Republic of the)": "CD",
    "Viet Nam": "VN",
    "Réunion": "FR",
    "Guadeloupe": "FR",
    "French Guiana": "FR",
    "Martinique": "FR",
    "United States of America": "US",
    "Korea (the Republic of)": "KR",
    "Russian Federation": "RU",
    "Iran (Islamic Republic of)": "IR",
    "Tanzania, the United Republic of": "TZ",
    "Bolivia (Plurinational State of)": "BO",
    "Venezuela (Bolivarian Republic of)": "VE",
    "Taiwan (Province of China)": "TW",
    "Svalbard and Jan Mayen": "NO",
}
URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
       "geojson/ne_10m_admin_0_countries.geojson")


def parts(geom: dict):
    if geom["type"] == "Polygon":
        yield geom["coordinates"][0]
    elif geom["type"] == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pad", type=float, default=0.5, help="degrees added on every side")
    args = ap.parse_args()
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    rows = set()
    names: dict[str, str] = dict(ALIASES)
    for feat in r.json()["features"]:
        iso = feat["properties"].get("ISO_A2_EH")
        if not iso or iso == "-99":
            continue
        for key in ("NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "NAME_EN", "SOVEREIGNT"):
            v = feat["properties"].get(key)
            if v and (key != "SOVEREIGNT" or v == feat["properties"].get("ADMIN")):
                names.setdefault(v, iso)
        for ring in parts(feat["geometry"]):
            lngs = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            p = args.pad
            box = (max(min(lats) - p, -90), min(max(lats) + p, 90))
            if max(lngs) - min(lngs) > 180:          # crosses the antimeridian
                east = [x for x in lngs if x > 0]
                west = [x for x in lngs if x <= 0]
                spans = [(min(east) - p, 180.0), (-180.0, max(west) + p)]
            else:
                spans = [(max(min(lngs) - p, -180), min(max(lngs) + p, 180))]
            for lo, hi in spans:
                rows.add((iso, round(box[0], 3), round(box[1], 3), round(lo, 3), round(hi, 3)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["iso2", "min_lat", "max_lat", "min_lng", "max_lng"])
        w.writerows(sorted(rows))
    with NAMES_OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "iso2"])
        w.writerows(sorted(names.items()))
    print(f"[done] {len(names)} country names -> {NAMES_OUT.relative_to(ROOT)}")
    print(f"[done] {len(rows)} boxes for {len({r[0] for r in rows})} countries -> "
          f"{OUT.relative_to(ROOT)} (source {URL})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
