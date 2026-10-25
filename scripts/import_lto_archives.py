#!/usr/bin/env python3
"""Copy the lto data-archive records that serve GERI sites into data/raw/J-LTO/.

tyson-swetnam/lto catalogues 80 data archives, with documented API calls
and cloud buckets. Most serve U.S. regional networks; these serve GERI
sites:

  neon-data-portal                 every NEON site (lto links it to all 81)
  gbif, obis, knb, nasa-earthdata, ornl-daac
                                   global services that answer for any site

This script copies their data_archives, api_endpoints and cloud_buckets
rows, as lto publishes them (public/parquet/), to
data/raw/J-LTO/{archives,api_endpoints,cloud_buckets}.json with the lto
commit they came from. It does not judge them: check_endpoints.py
requests every URL, and load_geri_archives.py loads only rows whose check
did not find them gone. (On 2026-10-25 four of lto's five bucket records
for these archives named buckets that do not exist; lto#26 fixed them.)
Pass --lto a checkout of lto's main: ../lto may be on a work branch.

Usage::

    python scripts/import_lto_archives.py                  # ../lto
    python scripts/import_lto_archives.py --lto /path/to/lto
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "J-LTO"
ARCHIVES = ["neon-data-portal", "gbif", "obis", "knb", "nasa-earthdata", "ornl-daac"]


def rows(con, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        out.append({c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lto", type=Path, default=ROOT.parent / "lto")
    args = ap.parse_args()
    pq = args.lto / "public" / "parquet"
    commit = subprocess.run(["git", "-C", str(args.lto), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or None
    con = duckdb.connect()
    ids = ARCHIVES
    meta = {"source": "https://github.com/tyson-swetnam/lto (public/parquet)", "lto_commit": commit,
            "imported_at": dt.date.today().isoformat()}
    OUT.mkdir(parents=True, exist_ok=True)
    for table, key in (("data_archives", "archives"), ("api_endpoints", "api_endpoints"),
                       ("cloud_buckets", "cloud_buckets")):
        data = rows(con, f"SELECT * EXCLUDE (created_at) FROM read_parquet(?) "
                         f"WHERE archive_id IN (SELECT unnest(?::VARCHAR[])) ORDER BY ALL"
                    if table == "data_archives" else
                    f"SELECT * FROM read_parquet(?) WHERE archive_id IN (SELECT unnest(?::VARCHAR[])) "
                    f"ORDER BY ALL", [str(pq / f"{table}.parquet"), ids])
        (OUT / f"{key}.json").write_text(json.dumps({**meta, key: data}, ensure_ascii=False, indent=1) + "\n")
        print(f"[import] {table:<14} {len(data):>3} rows -> {(OUT / f'{key}.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
