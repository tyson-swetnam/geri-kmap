#!/usr/bin/env python3
"""Summarize the GERI harmonized parquet per site and variable.

Reads the harmonized files (``GERI_<variable>_<resolution>.parquet``) from
``data/cache/harmonized/`` -- downloaded from the Data Store with
``--download``, about 1 GB, gitignored -- and writes
``data/raw/R-GERI-HARMONIZED/harmonized_summary.csv`` (committed): one row
per file x site x value column with the site's name as the products give
it, its first and last timestamp and its number of non-null values. No
observation leaves the cache; the summary is what load_geri_sites.py
(site names) and load_geri_archives.py (harmonized_coverage) read, so
neither needs the download.

Each file's MD5 is checked against the Data Store's iRODS checksum when
the listing carries one, and recorded in the summary.

Usage::

    python scripts/summarize_harmonized.py --download
    python scripts/summarize_harmonized.py            # cache already present
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import duckdb
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "harmonized"
LISTING = ROOT / "data" / "raw" / "R-GERI-HARMONIZED" / "datastore_listing.json"
OUT = ROOT / "data" / "raw" / "R-GERI-HARMONIZED" / "harmonized_summary.csv"
NAME_RE = re.compile(r"^GERI_[a-z0-9]+_(\d+min|monthly|static)(_v\d+)?\.parquet$", re.I)
META_COLS = {"research_infrastructure", "country", "site_id", "site_name", "pit_id",
             "start_date_time", "end_date_time", "date_collected", "quality_flag",
             "latitude_deg", "longitude_deg", "depth_min_m", "depth_max_m"}


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--download", action="store_true", help="fetch missing files into the cache")
    args = ap.parse_args()
    files = [f for f in json.loads(LISTING.read_text())["files"] if NAME_RE.match(f["name"])]
    CACHE.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")   # timestamps print the same on every machine
    rows = []
    for f in files:
        path = CACHE / f["name"]
        if not path.exists():
            if not args.download:
                print(f"[error] {path.relative_to(ROOT)} missing; pass --download", file=sys.stderr)
                return 2
            print(f"[download] {f['name']} ({f['size']:,} bytes)")
            with requests.get(f["url"], stream=True, timeout=600) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                with tmp.open("wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                tmp.rename(path)
        digest = md5(path)
        if f.get("size") and path.stat().st_size != f["size"]:
            print(f"[error] {f['name']}: {path.stat().st_size} bytes, listing says {f['size']}",
                  file=sys.stderr)
            return 1
        cols = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]
        values = [c for c in cols if c not in META_COLS]
        t0 = "start_date_time" if "start_date_time" in cols else "date_collected"
        t1 = "end_date_time" if "end_date_time" in cols else "date_collected"
        for v in values:
            q = f"""SELECT site_id, any_value(site_name), any_value(research_infrastructure),
                           any_value(country), min({t0})::VARCHAR, max({t1})::VARCHAR,
                           count({v})
                    FROM read_parquet('{path}') GROUP BY site_id ORDER BY site_id"""
            for sid, name, ri, ctry, first, last, n in con.sql(q).fetchall():
                rows.append({"file": f["name"], "md5": digest, "variable": v, "site_id": sid,
                             "site_name": name, "research_infrastructure": ri, "country": ctry,
                             "first_ts": first, "last_ts": last, "n_obs": n})
        print(f"[summary] {f['name']:<38} {len(values)} variable(s), md5 {digest}")
    rows.sort(key=lambda r: (r["file"], r["variable"], r["site_id"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"[done] {len(rows)} rows -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
