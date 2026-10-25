#!/usr/bin/env python3
"""Fetch every SAEON / EFTEON observation station from DataCite.

SAEON registers each station of its Terrestrial Observations Monitor as a
DataCite DOI under prefix 10.15493 (``10.15493/obs.monitor.<n>``), titled
'<station> - SAEON Terrestrial Observations Monitor'. The DataCite REST API
is the registry of those DOIs, so it is the full list -- the six records in
the GERI Data Store's geri-metadata/saeon/ are a subset.

Output: ``data/raw/R-GERI-SAEON/stations_saeon.json``, one record per DOI
with the fields the loader reads, as DataCite returns them: doi, url,
titles, creators (organisation names), subjects (they name the EFTEON
landscape or SAEON node), geoLocations, dates. Contributors (people) are
not kept.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-SAEON" / "stations_saeon.json"
API = "https://api.datacite.org/dois"
QUERY = 'titles.title:"Observations Monitor"'
PREFIX = "10.15493"


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    url, params, records = API, {"query": QUERY, "prefix": PREFIX, "page[size]": 100}, []
    while url:
        r = s.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        for item in body["data"]:
            a = item["attributes"]
            records.append({
                "doi": a["doi"].lower(),
                "id": f"https://doi.org/{a['doi'].lower()}",
                "url": a.get("url"),
                "titles": a.get("titles"),
                "creators": [{"name": c.get("name")} for c in a.get("creators") or []],
                "subjects": [{"subject": x.get("subject")} for x in a.get("subjects") or []],
                "geoLocations": a.get("geoLocations"),
                "dates": a.get("dates"),
            })
        url, params = body.get("links", {}).get("next"), None
    records.sort(key=lambda r: r["doi"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": f"{API}?query={QUERY}&prefix={PREFIX}",
                               "retrieved_at": dt.date.today().isoformat(),
                               "stations": records}, ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(records)} SAEON/EFTEON stations -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
