#!/usr/bin/env python3
"""Fetch the NEON field-site list from the NEON Data API.

Output: ``data/raw/R-GERI-NEON/sites_neon.json`` -- every site
``https://data.neonscience.org/api/v0/sites`` returns, as written, minus
the per-site ``dataProducts`` and ``releases`` lists (large, and the
catalogue only needs the site). Each NEON record carries its DEIMS id,
which is how load_geri_sites.py joins it to the DEIMS backbone.

Each site also gets four fields from its location record
(``/api/v0/locations/<siteCode>``): ``habitat`` (NEON's HABITAT property,
e.g. 'Aquatic Wadeable Stream' -- what tells an aquatic site from a
terrestrial one), ``fieldSiteUrlPath`` (NEONSCI_FIELD_SITE_URL_PATH, the
slug of the site's page on neonscience.org), ``elevation`` and ``county``.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-NEON" / "sites_neon.json"
URL = "https://data.neonscience.org/api/v0/sites"
LOC_URL = "https://data.neonscience.org/api/v0/locations/{}"
LOC_PROPS = {"Value for HABITAT": "habitat",
             "Value for NEONSCI_FIELD_SITE_URL_PATH": "fieldSiteUrlPath",
             "Value for County": "county"}
DROP = {"dataProducts", "releases"}


def main() -> int:
    r = requests.get(URL, timeout=60,
                     headers={"User-Agent": "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"})
    r.raise_for_status()
    sites = [{k: v for k, v in s.items() if k not in DROP} for s in r.json()["data"]]
    sites.sort(key=lambda s: s["siteCode"])
    session = requests.Session()
    for site in sites:
        loc = session.get(LOC_URL.format(site["siteCode"]), timeout=60)
        loc.raise_for_status()
        d = loc.json()["data"]
        site["elevation"] = d.get("locationElevation")
        for p in d.get("locationProperties") or []:
            key = LOC_PROPS.get(p["locationPropertyName"])
            if key:
                site[key] = p["locationPropertyValue"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": URL, "retrieved_at": dt.date.today().isoformat(),
                               "sites": sites}, ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(sites)} NEON sites -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
