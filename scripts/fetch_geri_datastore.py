#!/usr/bin/env python3
"""Fetch the GERI harmonized-site list and per-RI site metadata from the
CyVerse Data Store (anonymous WebDAV; no credentials needed).

The collection is ``/iplant/home/shared/geri`` in iRODS; anonymously it
resolves under ``https://data.cyverse.org/dav-anon/iplant/projects/geri/``.

Writes to ``data/raw/R-GERI-HARMONIZED/``:

  geri_harmonized_sites.csv   byte-for-byte copy (research_infrastructure,
                              site_id, lat, lon). Its bytes are Latin-1, not
                              UTF-8 ('FI-V\\xe4rri\\xf6'); the loader decodes it.
  elter_sites.json            geri-metadata/elter/*.json -- DEIMS-SDR site
                              records, boundaries dropped (one is ~1 MB).
  saeon_stations.json         geri-metadata/saeon/*.json -- DataCite records
                              of SAEON/EFTEON observation stations.
  datastore_listing.json      name, size and URL of every file under
                              geri-harmonized/ (for the pointer records).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-HARMONIZED"
DAV = "https://data.cyverse.org/dav-anon/iplant/projects/geri"
HREF_RE = re.compile(r"<D:href>([^<]+)</D:href>", re.I)
LEN_RE = re.compile(r"<D:getcontentlength>(\d+)</D:getcontentlength>", re.I)


def listing(s: requests.Session, path: str) -> list[dict]:
    """Files directly under a collection: [{name, url, size}]."""
    r = s.request("PROPFIND", f"{DAV}/{path}/", headers={"Depth": "1"}, timeout=60)
    r.raise_for_status()
    out = []
    for resp in re.split(r"</D:response>", r.text, flags=re.I):
        h = HREF_RE.search(resp)
        if not h or h.group(1).endswith("/"):
            continue
        n = LEN_RE.search(resp)
        name = unquote(h.group(1).rsplit("/", 1)[-1])
        out.append({"name": name, "url": f"{DAV}/{path}/{name}",
                    "size": int(n.group(1)) if n else None})
    return sorted(out, key=lambda f: f["name"])


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()

    r = s.get(f"{DAV}/geri-harmonized/geri_harmonized_sites.csv", timeout=60)
    r.raise_for_status()
    (OUT / "geri_harmonized_sites.csv").write_bytes(r.content)
    print(f"[csv] geri_harmonized_sites.csv {len(r.content)} bytes")

    elter = []
    for f in listing(s, "geri-metadata/elter"):
        d = s.get(f["url"], timeout=60).json()
        (d.get("attributes") or {}).get("geographic", {}).pop("boundaries", None)
        elter.append({"file": f["name"], "url": f["url"], "record": d})
    (OUT / "elter_sites.json").write_text(json.dumps(
        {"source": f"{DAV}/geri-metadata/elter/", "retrieved_at": today, "sites": elter},
        ensure_ascii=False, indent=1) + "\n")
    print(f"[elter] {len(elter)} DEIMS records")

    saeon = []
    for f in listing(s, "geri-metadata/saeon"):
        saeon.append({"file": f["name"], "url": f["url"], "record": s.get(f["url"], timeout=60).json()})
    (OUT / "saeon_stations.json").write_text(json.dumps(
        {"source": f"{DAV}/geri-metadata/saeon/", "retrieved_at": today, "stations": saeon},
        ensure_ascii=False, indent=1) + "\n")
    print(f"[saeon] {len(saeon)} DataCite records")

    files = listing(s, "geri-harmonized")
    (OUT / "datastore_listing.json").write_text(json.dumps(
        {"source": f"{DAV}/geri-harmonized/", "retrieved_at": today, "files": files},
        ensure_ascii=False, indent=1) + "\n")
    print(f"[listing] {len(files)} files under geri-harmonized/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
