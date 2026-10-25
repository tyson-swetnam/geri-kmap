#!/usr/bin/env python3
"""Fetch ICOS stations from the ICOS Carbon Portal metadata store (SPARQL).

ICOS runs three station types: ecosystem (ES), atmosphere (AS) and ocean
(OS). The portal also lists stations that never entered ICOS labelling;
only stations with an ICOS station class (``1``, ``2`` or ``Associated``)
are kept, and the class is recorded. The count of skipped unclassified
stations is printed so a change in that rule is visible.

Output: ``data/raw/R-GERI-ICOS/stations_icos.json``, values as the portal
returns them.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-ICOS" / "stations_icos.json"
ENDPOINT = "https://meta.icos-cp.eu/sparql"

QUERY = """prefix cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
select ?s ?id ?name ?lat ?lon ?elev ?country ?cls ?labelDate where {
  ?s a cpmeta:%s ; cpmeta:hasStationId ?id ; cpmeta:hasName ?name .
  OPTIONAL { ?s cpmeta:hasLatitude ?lat }
  OPTIONAL { ?s cpmeta:hasLongitude ?lon }
  OPTIONAL { ?s cpmeta:hasElevation ?elev }
  OPTIONAL { ?s cpmeta:countryCode ?country }
  OPTIONAL { ?s cpmeta:hasStationClass ?cls }
  OPTIONAL { ?s cpmeta:hasLabelingDate ?labelDate }
}"""


def main() -> int:
    out = []
    for kind in ("ES", "AS", "OS"):
        r = requests.post(ENDPOINT, data={"query": QUERY % kind}, timeout=180,
                          headers={"Accept": "application/sparql-results+json"})
        r.raise_for_status()
        rows = [{k: v["value"] for k, v in b.items()} for b in r.json()["results"]["bindings"]]
        kept = [dict(row, station_type=kind) for row in rows if row.get("cls")]
        print(f"[{kind}] {len(rows)} stations, {len(kept)} with an ICOS class, "
              f"{len(rows) - len(kept)} unclassified skipped")
        out.extend(kept)
    # One row per station: a station with two class or label values would
    # otherwise repeat; keep the first after sorting so output is stable.
    out.sort(key=lambda r: (r["station_type"], r["id"], r.get("cls", ""), r.get("labelDate", "")))
    seen, stations = set(), []
    for r in out:
        if r["s"] not in seen:
            seen.add(r["s"])
            stations.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": ENDPOINT, "query": QUERY,
                               "retrieved_at": dt.date.today().isoformat(),
                               "stations": stations}, ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(stations)} ICOS stations -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
