#!/usr/bin/env python3
"""Fetch the OzFlux flux-tower sites from TERN's THREDDS server.

DEIMS-SDR lists TERN's SuperSites and plot networks but not the OzFlux
eddy-covariance towers, which are most of the GERI harmonized Australian
sites. Every OzFlux L3 netCDF file names its tower in its global
attributes: ``fluxnet_id`` (AU-How), ``site_name``, ``latitude``,
``longitude``, ``time_coverage_start/end``, ``license`` and more. Those
are read from the OPeNDAP ``.das`` response (metadata only, a few KB), not
by downloading data.

For each site folder under ``ecosystem_process/ozflux/`` the newest
version folder (highest name: ``2025_v2`` > ``2025_v1`` > ``2024_v2``) is
read. Contact e-mail addresses in the attributes are dropped: contact
details are not published.

Output: ``data/raw/R-GERI-TERN/sites_ozflux.json``.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-TERN" / "sites_ozflux.json"
THREDDS = "https://dap.tern.org.au/thredds"
BASE = "ecosystem_process/ozflux"
DROP_ATTRS = {"contact"}
TITLE_RE = re.compile(r'xlink:title="([^"]+)"')
URLPATH_RE = re.compile(r'urlPath="([^"]+\.nc)"')
ATTR_RE = re.compile(r'^\s*(?:String|Float\d+|Int\d+)\s+(\w+)\s+"?(.*?)"?;\s*$', re.S)


def get(session: requests.Session, url: str) -> str:
    for attempt in range(4):
        try:
            r = session.get(url, timeout=90)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt == 3:
                raise
            print(f"[retry] {url}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)


def catalog_titles(session, path: str) -> list[str]:
    return TITLE_RE.findall(get(session, f"{THREDDS}/catalog/{path}/catalog.xml"))


def global_attrs(das: str) -> dict:
    """NC_GLOBAL attributes from a DAS response (values may span lines)."""
    block = das.split("NC_GLOBAL {", 1)[1].split("\n    }", 1)[0]
    attrs, cur = {}, ""
    for line in block.splitlines():
        cur = f"{cur}\n{line}" if cur else line
        if cur.rstrip().endswith(";"):
            m = ATTR_RE.match(cur)
            if m:
                attrs[m.group(1)] = re.sub(r"\s*\n\s*", " ", m.group(2)).strip()
            cur = ""
    return attrs


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    sites, skipped = [], []
    for folder in catalog_titles(s, BASE):
        versions = sorted(catalog_titles(s, f"{BASE}/{folder}"))
        nc = None
        for version in reversed(versions):
            try:
                xml = get(s, f"{THREDDS}/catalog/{BASE}/{folder}/{version}/L3/default/catalog.xml")
            except requests.RequestException:
                continue
            paths = URLPATH_RE.findall(xml)
            if paths:
                nc, chosen = paths[0], version
                break
        if not nc:
            skipped.append(folder)
            print(f"[skip] {folder}: no L3 file in {versions}")
            continue
        attrs = global_attrs(get(s, f"{THREDDS}/dodsC/{nc}.das"))
        attrs = {k: v for k, v in attrs.items() if k not in DROP_ATTRS}
        sites.append({"folder": folder, "version": chosen,
                      "opendap_url": f"{THREDDS}/dodsC/{nc}",
                      "catalog_url": f"{THREDDS}/catalog/{BASE}/{folder}/catalog.html",
                      "attributes": attrs})
        print(f"[site] {folder:<34} {attrs.get('fluxnet_id', '?'):<8} {chosen}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": f"{THREDDS}/catalog/{BASE}/catalog.xml",
                               "retrieved_at": dt.date.today().isoformat(),
                               "skipped": skipped, "sites": sites},
                              ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(sites)} OzFlux sites ({len(skipped)} skipped) -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
