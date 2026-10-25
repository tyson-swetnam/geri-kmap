#!/usr/bin/env python3
"""Fetch every DEIMS-SDR site of the GERI research infrastructures.

DEIMS-SDR (https://deims.org) is the site registry eLTER and ILTER use,
and every GERI RI keeps a network record there. A DEIMS site lists all of
its network memberships with the network's own site code, so a site that
is both an eLTER site and an ICOS station is one record with two
affiliations -- co-location comes from the registry, not from matching.

Output: ``data/raw/R-GERI-DEIMS/sites_deims.json``, one record per site,
holding what the DEIMS API says, as written (boundaries dropped; they are
large and nothing reads them yet). Site detail responses are cached in
``data/cache/deims/`` (gitignored); ``--refresh`` re-fetches them.

Usage::

    python scripts/fetch_deims.py
    python scripts/fetch_deims.py --refresh
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-DEIMS" / "sites_deims.json"
CACHE = ROOT / "data" / "cache" / "deims"
API = "https://deims.org/api"

# DEIMS network ids, read from https://deims.org/api/networks (2026-10-25).
# The key is our networks.csv slug.
NETWORKS = {
    "geri": "c3abdc60-49f1-49db-81fe-863b7dbb21d3",
    "elter": "4742ffca-65ac-4aae-815f-83738500a1fc",   # "LTER Europe"
    "icos": "80633d38-4c85-4ee0-a4ce-7bbbd99c888c",
    "neon": "fd9fbc88-0baa-4d02-b824-dc29f721782c",
    "tern": "1ebec4aa-df7e-4657-84b6-1869c0b9437c",    # "TERN Australia"
    "saeon": "bce17afa-e548-4410-99d2-4eade740c9a9",
    "cern": "4dac034d-92d5-4c06-8e4e-aabafdbcedff",    # "CERN (LTER China)"
}


def get_json(session: requests.Session, url: str, params: dict | None = None):
    for attempt in range(4):
        try:
            r = session.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == 3:
                raise
            print(f"[retry] {url}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)


def site_detail(session: requests.Session, uuid: str, refresh: bool) -> dict:
    f = CACHE / f"{uuid}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    d = get_json(session, f"{API}/sites/{uuid}")
    f.write_text(json.dumps(d, ensure_ascii=False))
    time.sleep(0.2)
    return d


def compact(d: dict) -> dict:
    a = d.get("attributes") or {}
    g = a.get("general") or {}
    geo = a.get("geographic") or {}
    env = a.get("environmentalCharacteristics") or {}
    aff = (a.get("affiliation") or {}).get("networks") or []
    return {
        "deims_id": d["id"]["suffix"],
        "url": d["id"]["prefix"] + d["id"]["suffix"],
        "title": d.get("title"),
        "changed": d.get("changed"),
        "site_name": g.get("siteName"),
        "short_name": g.get("shortName"),
        "status": (g.get("status") or {}).get("label"),
        "year_established": g.get("yearEstablished"),
        "year_closed": g.get("yearClosed"),
        "site_type": g.get("siteType"),
        "coordinates": geo.get("coordinates"),
        "country": geo.get("country"),
        "elevation": geo.get("elevation"),
        "size": geo.get("size"),
        "biome": env.get("biome"),
        "ecosystem_type": [e.get("label") for e in (env.get("ecosystemType") or [])],
        "geobon_biome": env.get("geoBonBiome"),
        "air_temperature_mean": (env.get("airTemperature") or {}).get("yearlyAverage"),
        "precipitation_mean": (env.get("precipitation") or {}).get("yearlyAverage"),
        "networks": [
            {"name": n["network"]["name"], "deims_network_id": n["network"]["id"]["suffix"],
             "site_code": n.get("siteCode"), "verified": n.get("verified")}
            for n in aff if n.get("network")
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached site details")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"

    listed: dict[str, set[str]] = {}
    for slug, nid in NETWORKS.items():
        sites = get_json(s, f"{API}/sites", {"network": nid})
        print(f"[list] {slug:<6} {len(sites):>4} sites")
        for site in sites:
            listed.setdefault(site["id"]["suffix"], set()).add(slug)

    records = []
    for i, uuid in enumerate(sorted(listed), 1):
        rec = compact(site_detail(s, uuid, args.refresh))
        rec["listed_in"] = sorted(listed[uuid])
        records.append(rec)
        if i % 100 == 0:
            print(f"[detail] {i}/{len(listed)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": f"{API}/sites?network=<id>",
        "retrieved_at": dt.date.today().isoformat(),
        "networks": NETWORKS,
        "sites": records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(records)} sites -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
