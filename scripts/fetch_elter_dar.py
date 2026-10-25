#!/usr/bin/env python3
"""Count the eLTER Digital Asset Register's records per DEIMS site.

Every DAR record (dataset, external dataset) lists the sites it covers in
``metadata.siteReferences[]``, each with ``siteID`` -- the site's DEIMS-SDR
uuid, the key geri-kmap builds facilities on -- and ``siteName``. This
pages through ``https://dar.elter-ri.eu/api/records`` (oldest first, 100 a
page) and writes, per siteID:

  site_id, site_names, n_records, sample_record (landing page), sample_doi

to ``data/raw/J-GERI/dar_site_records.json``. load_geri_archives.py links
each facility whose deims-id has records to the DAR, with the per-site
search the API and the web search both accept:
``q=metadata.siteReferences.siteID:"<uuid>"``.

The sample is the record with the lowest DAR id that carries a DOI (from
``pids.doi`` unless it says NotDefined, else an alternateIdentifier of
type DOI), so it does not move between runs while the record stays.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "J-GERI" / "dar_site_records.json"
API = "https://dar.elter-ri.eu/api/records"


def record_doi(h: dict) -> str | None:
    pid = ((h.get("pids") or {}).get("doi") or {}).get("identifier")
    if pid and pid != "NotDefined":
        return pid.lower()
    for a in h["metadata"].get("alternateIdentifiers") or []:
        if (a.get("alternateIDType") or "").upper() == "DOI" and a.get("alternateID"):
            return a["alternateID"].lower().removeprefix("https://doi.org/").removeprefix("doi:")
    return None


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    url, params = API, {"size": 100, "sort": "oldest", "page": 1}
    seen: set[str] = set()
    sites: dict[str, dict] = {}
    total = None
    while url:
        r = s.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        total = body["hits"]["total"]
        for h in body["hits"]["hits"]:
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            doi = record_doi(h)
            for ref in h["metadata"].get("siteReferences") or []:
                sid = (ref.get("siteID") or "").strip().lower()
                if not sid:
                    continue
                e = sites.setdefault(sid, {"site_id": sid, "site_names": set(), "n_records": 0,
                                           "_sample": None})
                e["n_records"] += 1
                if ref.get("siteName"):
                    e["site_names"].add(ref["siteName"].strip())
                if doi and (e["_sample"] is None or h["id"] < e["_sample"][0]):
                    e["_sample"] = (h["id"], h["links"].get("self_html"), doi)
        url, params = body.get("links", {}).get("next"), None
    if len(seen) != total:
        print(f"[warn] read {len(seen)} distinct records of {total}", file=sys.stderr)
    out = []
    for sid in sorted(sites):
        e = sites[sid]
        out.append({"site_id": sid, "site_names": sorted(e["site_names"]), "n_records": e["n_records"],
                    "sample_record": e["_sample"][1] if e["_sample"] else None,
                    "sample_doi": e["_sample"][2] if e["_sample"] else None})
    OUT.write_text(json.dumps({"source": f"{API}?sort=oldest&size=100",
                               "retrieved_at": dt.date.today().isoformat(),
                               "records": len(seen), "sites": out},
                              ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(seen)} DAR records name {len(out)} DEIMS sites -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
