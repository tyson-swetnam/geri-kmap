#!/usr/bin/env python3
"""The data-access layer: where each site's data can be fetched, and how.

Archives, API endpoints and cloud buckets come from two committed sources,
read in this order (a later row with the same archive and URL wins):

  data/raw/J-LTO/   records copied from tyson-swetnam/lto for the archives
                    that serve GERI sites (import_lto_archives.py)
  data/raw/J-GERI/  the GERI research infrastructures' own services (ICOS,
                    DEIMS-SDR, eLTER DAR, TERN, OzFlux, SAEON, CNERN,
                    DataCite, the GERI Data Store and DataONE portal), each
                    row citing the page or response it was read from, plus
                    archive_overrides (e.g. NEON's token requirement)

data/seed/endpoint_checks.csv (check_endpoints.py) says what answered when
each URL was requested. A row found 'gone' (404, no such bucket, dead host)
is not loaded. An endpoint's access_mode is the curated one, else follows
from its check (auth -> registered-users, ok -> public-read); a bucket's is
what an anonymous listing showed.

facility_archives links every site to its research infrastructure's
archive with a per-site entry URL: NEON site -> the NEON explorer, ICOS
station -> its landing page, DEIMS site -> its DEIMS record, OzFlux tower
-> its THREDDS catalog, SAEON station -> its ODP landing page, CERN
station -> CNERN, TERN surveillance plot -> its AusPlots API record,
MexFlux tower registered in AmeriFlux -> its AmeriFlux site page. A site with records in the eLTER Digital Asset Register
(data/raw/J-GERI/dar_site_records.json, fetch_elter_dar.py) links to the
DAR's search for its DEIMS id, with the record count and a sample DOI:
primary for eLTER sites, secondary for the rest.

It also writes one data_products row per GERI harmonized file under
``geri-harmonized/`` (from
``data/raw/R-GERI-HARMONIZED/datastore_listing.json``, written by
fetch_geri_datastore.py). Metadata and links only: no observation is
copied. Each row's description and citation point to Karns et al. (2026):
the CyVerse Data Commons collection that archives the products as its
human reference (doi:10.25739/e9d8-ee77) and the EGU abstract on the
LLM-agent harmonization they validated (doi:10.5194/egusphere-egu26-12357).

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
RAW = ROOT / "data" / "raw"
CHECKS = ROOT / "data" / "seed" / "endpoint_checks.csv"
LISTING = RAW / "R-GERI-HARMONIZED" / "datastore_listing.json"
SUMMARY = ROOT / "data" / "raw" / "R-GERI-HARMONIZED" / "harmonized_summary.csv"
DAV = "https://data.cyverse.org/dav-anon/iplant/projects/geri/"
ARCHIVE_COLS = ["archive_id", "name", "organization", "archive_type", "base_url", "api_url",
                "api_doc_url", "api_type", "license_slug", "doi_prefix", "notes", "access_mode",
                "source_url", "check_verdict", "checked_at"]
ENDPOINT_COLS = ["endpoint_id", "archive_id", "facility_id", "path_or_url", "method", "purpose",
                 "response_format", "schema_url", "example_call", "notes", "access_mode",
                 "source_url", "check_verdict", "checked_at"]
BUCKET_COLS = ["bucket_id", "archive_id", "facility_id", "provider", "bucket_name", "region",
               "access_mode", "documentation_url", "sample_prefix", "notes", "source_url",
               "check_verdict", "checked_at"]
# A check verdict -> the access mode it shows, for rows that do not state one.
VERDICT_ACCESS = {"ok": "public-read", "alive": "public-read", "auth": "registered-users"}
# facility_archives: site identifier scheme -> (archive, role, entry-URL template)
SITE_LINKS = [
    ("neon-site", "neon-data-portal", "primary",
     "https://data.neonscience.org/data-products/explore?siteCodes={value}"),
    ("icos-station", "icos-cp", "primary", "https://meta.icos-cp.eu/resources/stations/{value}"),
    ("ozflux-site", "tern-dap", "primary", None),            # the identifier's own source_url
    ("doi", "saeon-odp", "primary", "https://api.odp.saeon.ac.za/catalog/SAEON/go/{value}"),
    ("deims-id", "deims-sdr", "secondary", "https://deims.org/{value}"),
    ("ausplots-site", "tern-ausplots", "primary",
     "http://swarmapi.ausplots.aekos.org.au/site?site_location_name=eq.{value}"),
    ("ameriflux-id", "ameriflux", "primary", "https://ameriflux.lbl.gov/sites/siteinfo/{value}"),
]
NETWORK_LINKS = [("cern", "cnern", "primary")]           # no per-station page
# The DAR's per-site search; the API (/api/records) takes the same q.
DAR_SITES = RAW / "J-GERI" / "dar_site_records.json"
DAR_SEARCH = 'https://dar.elter-ri.eu/search/?q=metadata.siteReferences.siteID:%22{value}%22'


def sha16(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def read_raw(name: str) -> tuple[list[dict], list[dict]]:
    """Rows of data/raw/J-LTO then J-GERI <name>.json, and J-GERI overrides."""
    rows, overrides = [], []
    for d in ("J-LTO", "J-GERI"):
        f = RAW / d / f"{name}.json"
        if f.exists():
            body = json.loads(f.read_text())
            rows += body.get(name, [])
            overrides += body.get(f"{name.rstrip('s')}_overrides", [])
    return rows, overrides


def read_checks() -> dict[tuple, dict]:
    import csv                                            # noqa: PLC0415
    if not CHECKS.exists():
        return {}
    with CHECKS.open(newline="", encoding="utf-8") as fh:
        return {(r["kind"], r["archive_id"], r["key"]): r for r in csv.DictReader(fh)}


def access_rows(con) -> dict:
    """Build archive / endpoint / bucket rows, applying checks and overrides."""
    checks = read_checks()
    dropped = []
    archives: dict[str, dict] = {}
    raw_a, over_a = read_raw("archives")
    for a in raw_a:
        archives[a["archive_id"]] = {c: a.get(c) for c in ARCHIVE_COLS}
    for o in over_a:
        archives[o["archive_id"]].update({k: v for k, v in o.items() if k != "archive_id"})
    for aid, a in archives.items():
        chk = checks.get(("archive", aid, f"base_url:{a['base_url']}")) if a.get("base_url") else None
        if chk and chk["verdict"] == "gone":
            dropped.append(f"archive {aid} ({a['base_url']})")
            continue
        if chk:
            a["check_verdict"], a["checked_at"] = chk["verdict"], chk["checked_at"]
    archives = {k: v for k, v in archives.items() if not any(d.startswith(f"archive {k} ") for d in dropped)}

    endpoints: dict[str, dict] = {}
    for e in read_raw("api_endpoints")[0]:
        if e["archive_id"] not in archives:
            continue
        chk = checks.get(("endpoint", e["archive_id"], e["path_or_url"]))
        if chk and chk["verdict"] == "gone":
            dropped.append(f"endpoint {e['path_or_url']}")
            continue
        row = {c: e.get(c) for c in ENDPOINT_COLS}
        row["endpoint_id"] = sha16(f"{e['archive_id']}|{e['path_or_url']}")
        row["facility_id"] = None
        if chk:
            row["check_verdict"], row["checked_at"] = chk["verdict"], chk["checked_at"]
            row["access_mode"] = row["access_mode"] or VERDICT_ACCESS.get(chk["verdict"])
        endpoints[row["endpoint_id"]] = row               # later source wins

    buckets: dict[str, dict] = {}
    for b in read_raw("cloud_buckets")[0]:
        if b["archive_id"] not in archives:
            continue
        chk = checks.get(("bucket", b["archive_id"], f"{b['provider']}:{b['bucket_name']}"))
        if chk and chk["verdict"] == "gone":
            dropped.append(f"bucket {b['provider']}:{b['bucket_name']}")
            continue
        row = {c: b.get(c) for c in BUCKET_COLS}
        row["facility_id"] = None
        if chk:
            observed = VERDICT_ACCESS.get(chk["verdict"])
            if observed and observed != row["access_mode"]:
                row["notes"] = (f"{row['notes'] or ''} Access mode set from an anonymous listing on "
                                f"{chk['checked_at']} ({chk['detail']}); lto recorded "
                                f"{row['access_mode']}.").strip()
                row["access_mode"] = observed
            row["check_verdict"], row["checked_at"] = chk["verdict"], chk["checked_at"]
        buckets[row["bucket_id"]] = row
    # An archive that states no access mode takes the strictest its
    # checked endpoints and buckets show (ORNL DAAC data files answer 401).
    rank = {"public-read": 0, "registered-users": 1, "license-required": 1}
    for aid, a in archives.items():
        if a.get("access_mode"):
            continue
        seen = [r["access_mode"] for r in list(endpoints.values()) + list(buckets.values())
                if r["archive_id"] == aid and r.get("access_mode") and r.get("check_verdict")]
        if seen:
            a["access_mode"] = max(seen, key=lambda m: rank.get(m, 0))
            a["notes"] = (f"{a.get('notes') or ''} Access mode derived from the checked endpoints "
                          f"and buckets ({', '.join(sorted(set(seen)))}).").strip()
    for d in dropped:
        print(f"[access] not loaded (check found it gone): {d}")
    return {"archives": list(archives.values()), "endpoints": list(endpoints.values()),
            "buckets": list(buckets.values())}


def stage(con, name: str, cols: list[str], rows: list[dict], dates=("checked_at", "retrieved_at")) -> None:
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} (" + ", ".join(
        f"{c} {'DATE' if c in dates else 'VARCHAR'}" for c in cols) + ")")
    if rows:
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})",
                        [[r.get(c) or None for c in cols] for r in rows])


# GERI_<variable>_<resolution>[_v<n>].parquet
NAME_RE = re.compile(r"^GERI_(?P<var>[a-z0-9]+?)_(?P<res>\d+min|monthly|static)(?:_v\d+)?\.parquet$", re.I)
VAR_LABEL = {"airtemperature": "air temperature", "precipitation": "precipitation",
             "soilmoisture": "soil moisture", "soiltemperature": "soil temperature",
             "soiltexture": "soil texture"}
RES_LABEL = {"30min": "30-minute", "60min": "hourly", "monthly": "monthly", "static": "static"}


# How the harmonized products are made and cited. The Data Commons
# collection (README of its C_reference_harmonized/) names geri-harmonized/
# as the human-expert reference and archives March, May and July 2026
# versions of the five products, with the 121 source-dataset citations.
KARNS_DATA_DOI = "10.25739/e9d8-ee77"
KARNS_EGU_DOI = "10.5194/egusphere-egu26-12357"
HARMONIZED_DESCRIPTION = (     # the Data tab shows 220 characters: DOIs first
    f"Cite: Karns et al. 2026, doi:{KARNS_DATA_DOI} (CyVerse Data Commons; archives this "
    f"human-expert harmonization as its reference). Method: Karns et al. 2026, EGU26-12357, "
    f"doi:{KARNS_EGU_DOI}. Harmonized by GERI domain experts into the GERI target schema; the "
    "collection also lists citations for the 121 source datasets, which must be cited too.")
HARMONIZED_CITATION = (
    "Karns, T. D., C. J. Hagen, K. Deshpande, M. D. SanClements, C. Laney, B. L. Ruddell, "
    "H. W. Loescher and T. L. Swetnam. 2026. Autonomous LLM-agent harmonization of environmental "
    "data across global research infrastructures (GERI): input data, metadata, human reference "
    "harmonization, target schema, and agent decision logs. CyVerse Data Commons. "
    f"https://doi.org/{KARNS_DATA_DOI}. Cite the source datasets too (A_source_data_citations.csv).")


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
            "description": HARMONIZED_DESCRIPTION, "citation": HARMONIZED_CITATION,
        })
    con = geri_db.connect(catalog=args.catalog, data=args.lake_data)
    con.execute("SET TimeZone = 'UTC'")   # summary timestamps are UTC; dates stay midnight
    with geri_db.transaction(con, f"load_geri_archives: data-access layer, "
                                  f"{len(products)} harmonized products + coverage"):
        geri_db.ensure_schema(con)
        load_vocab(con)
        acc = access_rows(con)
        stage(con, "s_arch", ARCHIVE_COLS, acc["archives"])
        geri_db.merge_upsert(con, "data_archives", ["archive_id"], "s_arch")
        con.execute("DELETE FROM data_archives WHERE archive_id NOT IN (SELECT archive_id FROM s_arch)")
        stage(con, "s_ep", ENDPOINT_COLS, acc["endpoints"])
        con.execute("DELETE FROM api_endpoints")
        con.execute("INSERT INTO api_endpoints BY NAME SELECT * FROM s_ep")
        stage(con, "s_cb", BUCKET_COLS, acc["buckets"])
        con.execute("DELETE FROM cloud_buckets")
        con.execute("INSERT INTO cloud_buckets BY NAME SELECT * FROM s_cb")
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
        con.execute("DELETE FROM facility_archives")
        con.execute("""INSERT INTO facility_archives BY NAME
                       SELECT si.facility_id, 'geri-cyverse' AS archive_id,
                              'distribution' AS role,
                              string_agg(si.value, ' ' ORDER BY si.value) AS scope_id,
                              'GERI harmonized drought products' AS notes
                       FROM site_identifiers si WHERE si.scheme = 'geri-harmonized-id'
                       GROUP BY si.facility_id""")
        for scheme, archive, role, tmpl in SITE_LINKS:
            con.execute("""INSERT INTO facility_archives BY NAME
                           SELECT facility_id, ? AS archive_id, ? AS role,
                                  CASE WHEN ? IS NULL THEN any_value(source_url ORDER BY value)
                                       -- an ICOS ecosystem station first, then the lowest id
                                       ELSE replace(?, '{value}', first(value ORDER BY value NOT LIKE 'ES\_%' ESCAPE '\\', value))
                                  END AS scope_url,
                                  string_agg(value, ' ' ORDER BY value) AS scope_id
                           FROM site_identifiers
                           WHERE scheme = ? AND facility_id NOT IN (
                                 SELECT facility_id FROM facility_archives WHERE archive_id = ?)
                           GROUP BY facility_id""", [archive, role, tmpl, tmpl, scheme, archive])
        if DAR_SITES.exists():
            dar = json.loads(DAR_SITES.read_text())
            con.execute("CREATE OR REPLACE TEMP TABLE s_dar (site_id VARCHAR, n_records INTEGER, "
                        "sample_doi VARCHAR)")
            con.executemany("INSERT INTO s_dar VALUES (?, ?, ?)",
                            [[x["site_id"], x["n_records"], x["sample_doi"]] for x in dar["sites"]])
            # A merged facility can hold two DEIMS ids: link the one with
            # the most records, count both (a record naming both counts twice).
            con.execute("""INSERT INTO facility_archives BY NAME
                           SELECT si.facility_id, 'elter-dar' AS archive_id,
                                  CASE WHEN si.facility_id IN (SELECT facility_id FROM network_membership
                                                               WHERE network_id = 'elter')
                                       THEN 'primary' ELSE 'secondary' END AS role,
                                  replace(?, '{value}', arg_max(d.site_id, (d.n_records, d.site_id))) AS scope_url,
                                  string_agg(d.site_id, ' ' ORDER BY d.site_id) AS scope_id,
                                  arg_max(d.sample_doi, (d.n_records, d.site_id)) AS sample_doi,
                                  sum(d.n_records) || ' records in the eLTER DAR (as of ' || ? || ')' AS notes
                           FROM site_identifiers si JOIN s_dar d ON d.site_id = si.value
                           WHERE si.scheme = 'deims-id'
                           GROUP BY si.facility_id""", [DAR_SEARCH, dar["retrieved_at"]])
            print(f"[dar] {geri_db.scalar(con, "SELECT count(*) FROM facility_archives WHERE archive_id = 'elter-dar'")}"
                  f" sites linked to the eLTER DAR ({len(dar['sites'])} DEIMS sites have records)")
        for network, archive, role in NETWORK_LINKS:
            con.execute("""INSERT INTO facility_archives BY NAME
                           SELECT facility_id, ? AS archive_id, ? AS role
                           FROM network_membership WHERE network_id = ?""", [archive, role, network])
        n_cov = geri_db.scalar(con, "SELECT count(*) FROM harmonized_coverage")
        geri_db.assert_integrity(con, ["data_archives", "data_products", "harmonized_coverage",
                                       "facility_archives", "api_endpoints", "cloud_buckets"])
    print(f"[access] {len(acc['archives'])} archives, {len(acc['endpoints'])} endpoints, "
          f"{len(acc['buckets'])} buckets")
    print(f"[products] {res}; [coverage] {n_cov} rows")
    for p in products:
        print(f"[product] {p['identifier']:<38} {p['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
