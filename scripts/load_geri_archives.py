#!/usr/bin/env python3
"""Pointer records for the GERI harmonized data on the CyVerse Data Store.

Writes two data_archives rows -- the Data Store collection and the GERI
DataONE portal that publishes the same products -- and one data_products
row per file under ``geri-harmonized/`` (from
``data/raw/R-GERI-HARMONIZED/datastore_listing.json``, written by
fetch_geri_datastore.py). Metadata and links only: no observation is
copied.

From ``harmonized_summary.csv`` (summarize_harmonized.py) it also writes
``harmonized_coverage`` -- per facility, product and variable, the first
and last timestamp and the number of values -- each product's period and
variable list, and a facility_archives link from every covered facility
to the Data Store collection. Two harmonized ids on one facility (DE-HoH-E
and DE-HoH-I: the eLTER and ICOS series of Hohes Holz) are added together.
Run after load_geri_sites.py, which assigns the harmonized ids.

The collection's licence is its DataCite record's (AVU
``datacite.rights.1.value`` on /iplant/home/shared/geri: Creative Commons
Zero v1.0 Universal).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geri_db  # noqa: E402
from load_vocab import load_vocab  # noqa: E402

ROOT = geri_db.ROOT
LISTING = ROOT / "data" / "raw" / "R-GERI-HARMONIZED" / "datastore_listing.json"
SUMMARY = ROOT / "data" / "raw" / "R-GERI-HARMONIZED" / "harmonized_summary.csv"
DAV = "https://data.cyverse.org/dav-anon/iplant/projects/geri/"
ARCHIVES = [
    {"archive_id": "geri-cyverse", "name": "GERI collection, CyVerse Data Store",
     "organization": "CyVerse (University of Arizona) for the GERI AccelNet project",
     "archive_type": "repository", "base_url": DAV, "api_url": DAV, "api_type": "custom",
     "api_doc_url": "https://learning.cyverse.org/ds/", "license_slug": "cc0",
     "notes": "iRODS path /iplant/home/shared/geri; anonymous WebDAV at the base URL. "
              "Holds source data by research infrastructure, intermediate outputs and the "
              "harmonized drought datasets."},
    {"archive_id": "geri-dataone", "name": "GERI data portal (DataONE)",
     "organization": "DataONE for the GERI AccelNet project",
     "archive_type": "data-portal", "base_url": "https://geri.dataone.org/",
     "api_url": None, "api_type": None, "api_doc_url": None, "license_slug": "cc0",
     "notes": "Where the Data Store README says the harmonized datasets are published and "
              "discoverable."},
]
# GERI_<variable>_<resolution>[_v<n>].parquet
NAME_RE = re.compile(r"^GERI_(?P<var>[a-z0-9]+?)_(?P<res>\d+min|monthly|static)(?:_v\d+)?\.parquet$", re.I)
VAR_LABEL = {"airtemperature": "air temperature", "precipitation": "precipitation",
             "soilmoisture": "soil moisture", "soiltemperature": "soil temperature",
             "soiltexture": "soil texture"}
RES_LABEL = {"30min": "30-minute", "60min": "hourly", "monthly": "monthly", "static": "static"}


def product_id(name: str) -> str:
    return hashlib.sha1(f"geri-cyverse|{name}".encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    geri_db.add_argparse_catalog(ap)
    args = ap.parse_args()
    listing = json.loads(LISTING.read_text())
    products = []
    for f in listing["files"]:
        m = NAME_RE.match(f["name"])
        if not m:
            continue
        var, res = m.group("var").lower(), m.group("res").lower()
        products.append({
            "product_id": product_id(f["name"]), "archive_id": "geri-cyverse",
            "title": f"GERI harmonized {VAR_LABEL.get(var, var)}, {RES_LABEL.get(res, res)}",
            "identifier": f["name"], "url": f["url"], "api_url": f["url"],
            "format_slug": "parquet", "license_slug": "cc0",
            "category": f"GERI harmonized / {RES_LABEL.get(res, res)}",
            "source": "scripts/fetch_geri_datastore.py", "retrieved_at": listing["retrieved_at"],
            "confidence": "high",
            "notes": f"{f['size']:,} bytes" if f.get("size") else None,
        })
    con = geri_db.connect(catalog=args.catalog, data=args.lake_data)
    con.execute("SET TimeZone = 'UTC'")   # summary timestamps are UTC; dates stay midnight
    with geri_db.transaction(con, f"load_geri_archives: {len(ARCHIVES)} archives, "
                                  f"{len(products)} harmonized products + coverage"):
        geri_db.ensure_schema(con)
        load_vocab(con)
        con.execute("CREATE OR REPLACE TEMP TABLE s_arch AS SELECT * FROM (VALUES "
                    + ",".join(["(?,?,?,?,?,?,?,?,?,?)"] * len(ARCHIVES)) + ") t(archive_id, name, "
                    "organization, archive_type, base_url, api_url, api_type, api_doc_url, "
                    "license_slug, notes)",
                    [a[k] for a in ARCHIVES for k in ("archive_id", "name", "organization",
                                                       "archive_type", "base_url", "api_url",
                                                       "api_type", "api_doc_url", "license_slug",
                                                       "notes")])
        geri_db.merge_upsert(con, "data_archives", ["archive_id"], "s_arch")
        cols = list(products[0]) if products else []
        con.execute("CREATE OR REPLACE TEMP TABLE s_prod (" + ", ".join(
            f"{c} {'DATE' if c == 'retrieved_at' else 'VARCHAR'}" for c in cols) + ")")
        con.executemany(f"INSERT INTO s_prod VALUES ({', '.join('?' * len(cols))})",
                        [[p[c] for c in cols] for p in products])
        # Products of this archive no longer in the listing go; coverage first.
        con.execute("""DELETE FROM harmonized_coverage WHERE product_id IN (
                         SELECT product_id FROM data_products WHERE archive_id = 'geri-cyverse'
                           AND product_id NOT IN (SELECT product_id FROM s_prod))""")
        con.execute("""DELETE FROM data_products WHERE archive_id = 'geri-cyverse'
                         AND product_id NOT IN (SELECT product_id FROM s_prod)""")
        res = geri_db.merge_upsert(con, "data_products", ["product_id"], "s_prod")

        # Coverage from the committed summary.
        con.execute("""CREATE OR REPLACE TEMP TABLE s_sum AS
                       SELECT * FROM read_csv(?, header = true, all_varchar = true)""",
                    [str(SUMMARY)])
        con.execute("CREATE OR REPLACE TEMP TABLE s_pid (file VARCHAR, product_id VARCHAR)")
        con.executemany("INSERT INTO s_pid VALUES (?, ?)",
                        [(p["identifier"], p["product_id"]) for p in products])
        unmapped = geri_db.rows(con, """SELECT DISTINCT site_id FROM s_sum WHERE site_id NOT IN (
                       SELECT value FROM site_identifiers WHERE scheme = 'geri-harmonized-id')
                       ORDER BY 1""")
        if unmapped:
            print(f"[coverage] site ids with no facility (run load_geri_sites.py first): "
                  f"{[r[0] for r in unmapped]}")
        con.execute("DELETE FROM harmonized_coverage")
        con.execute("""INSERT INTO harmonized_coverage BY NAME
                       SELECT si.facility_id, p.product_id, s.variable,
                              min(s.first_ts::TIMESTAMPTZ AT TIME ZONE 'UTC') AS first_ts,
                              max(s.last_ts::TIMESTAMPTZ AT TIME ZONE 'UTC')  AS last_ts,
                              sum(s.n_obs::BIGINT)                          AS n_obs
                       FROM s_sum s
                       JOIN s_pid p USING (file)
                       JOIN site_identifiers si
                         ON si.scheme = 'geri-harmonized-id' AND si.value = s.site_id
                       GROUP BY si.facility_id, p.product_id, s.variable""")
        con.execute("""CREATE OR REPLACE TEMP TABLE s_ext AS
                       SELECT p.product_id,
                              min(s.first_ts::TIMESTAMPTZ AT TIME ZONE 'UTC')::DATE AS temporal_start,
                              max(s.last_ts::TIMESTAMPTZ AT TIME ZONE 'UTC')::DATE  AS temporal_end,
                              string_agg(DISTINCT s.variable, ', ' ORDER BY s.variable) AS variables_text
                       FROM s_sum s JOIN s_pid p USING (file) GROUP BY p.product_id""")
        geri_db.merge_upsert(con, "data_products", ["product_id"], "s_ext")
        con.execute("DELETE FROM facility_archives WHERE archive_id = 'geri-cyverse'")
        con.execute("""INSERT INTO facility_archives BY NAME
                       SELECT si.facility_id, 'geri-cyverse' AS archive_id,
                              'distribution' AS role,
                              string_agg(si.value, ' ' ORDER BY si.value) AS scope_id,
                              'GERI harmonized drought products' AS notes
                       FROM site_identifiers si WHERE si.scheme = 'geri-harmonized-id'
                       GROUP BY si.facility_id""")
        n_cov = geri_db.scalar(con, "SELECT count(*) FROM harmonized_coverage")
        geri_db.assert_integrity(con, ["data_archives", "data_products", "harmonized_coverage",
                                       "facility_archives"])
    print(f"[archives] {len(ARCHIVES)}; [products] {res}; [coverage] {n_cov} rows")
    for p in products:
        print(f"[product] {p['identifier']:<38} {p['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
