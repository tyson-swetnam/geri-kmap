#!/usr/bin/env python3
"""Load what Loescher et al. (2026) adds beyond sites: RI profiles, partner organizations, citations.

Loescher, SanClements, Laney et al. (2026) "Toward a global ecosystem
network-of-networks: Team science as a pathway for equitable macrosystem
collaboration", Ecosphere 17(10): e70789, doi:10.1002/ecs2.70789 (CC BY 4.0).

  ri_profiles            one row per GERI RI from the paper's Table 1 (data
                         volume, yearly growth, variety, products) and the
                         site count its Figure 1 maps. Values transcribed
                         from the article page (2026-10-26); RI_PROFILES
                         below keeps the table's footnotes with them.
  network_organizations  the "nearest neighbor" landscape survey (Table 3;
                         data: doi:10.5281/zenodo.17717896) and the Mexican
                         networks of the GENNI use case (Box 1), from
                         data/raw/J-GENNI/landscape_orgs.json
                         (fetch_landscape_survey.py)
  publications           the paper, the GERI paper it builds on and the two
                         Zenodo records, from data/raw/J-GENNI/publications.json
                         (fetch_geri_papers.py)

Run after load_geri_sites.py (the networks vocabulary must be loaded).
The script owns ri_profiles and network_organizations whole, and the
publications rows of the DOIs it loads. One transaction, one snapshot.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geri_db  # noqa: E402

ROOT = geri_db.ROOT
ORGS = ROOT / "data" / "raw" / "J-GENNI" / "landscape_orgs.json"
PAPERS = ROOT / "data" / "raw" / "J-GENNI" / "publications.json"
COUNTRY_NAMES = ROOT / "schema" / "vocab" / "country_names.csv"
PAPER_DOI = "10.1002/ecs2.70789"
SURVEY_URL = "https://doi.org/10.5281/zenodo.17717896"

# Table 1 (data volume to 2025-01-31) and Figure 1 (sites mapped).
# (network, volume TiB, TiB/year, variety, products, sites, notes)
RI_PROFILES = [
    ("neon", 1497.0, 153.4, 5, 181, 81,
     "Volume and yearly growth include remote-sensing data (Table 1, note a)."),
    ("elter", 454.0, None, 20, 547, 185,
     "Yearly growth to be determined. Variety (approximately 20) and products from Zacharias et al. "
     "(2021). Figure 1 maps about 185 sites; eLTER has about 200 Category 1 and 2 candidate sites, "
     "labelled from 2026 onwards, 30 of them shared with ICOS."),
    ("icos", 963.0, 3.0, 94, 41, 150,
     "Yearly growth approximate. Products are processed Level 1 and 2 only (Table 1, note c). "
     "Figure 1 maps about 150 sites."),
    ("tern", 164.0, 10.9, 3, 2700, 800,
     "Products approximate (about 2,700). Figure 1 maps 800 sites."),
    ("cern", 8.2, 2.7, None, 900, 40,
     "Variety not available. Products approximate (about 900), inflated by a different naming "
     "convention (Table 1, note d). Figure 1 maps 40 sites."),
    ("saeon", 1455.0, None, 7, None, 18,
     "Yearly growth to be determined; Table 1 gives no product count. Figure 1 maps 18 sites, "
     "including coastal and marine sites."),
]
AS_OF = "2025-01-31"
# Survey organizations that are a network the catalogue holds (exact names).
ORG_NETWORK = {
    "National Ecological Observatory Network": "neon",
    "Long Term Ecological Research Network (Europe)": "elter",
    "Integrated Carbon Observation System": "icos",
    "ICOS ERIC": "icos",
    "Terrestrial Ecosystem Research Network": "tern",
    "South African Environmental Observation Network": "saeon",
    "Chinese Ecosystem Research Network": "cern",
    "OzFlux": "ozflux",
    "MexFlux": "mexflux",
}
GENNI_CASE = {"MexFlux", "RISZA", "OSPE", "PUEIS", "YECS-IUSS"}
# The survey's country names the Natural Earth list spells differently.
# 'Republic of China' rows are mainland organizations (CERN, the Chinese
# Academy of Sciences and its institutes), so CN.
COUNTRY_ALIAS = {"republic of china": "CN"}
FUNCTIONS = ("observation", "aggregation", "network")


def sha16(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def scope_of(o: dict) -> str | None:
    s = (o.get("scope") or "").lower()
    for k in ("domestic", "international", "global", "regional"):
        if s.startswith(k):
            return k
    return None


def org_rows() -> list[tuple]:
    body = json.loads(ORGS.read_text())
    with COUNTRY_NAMES.open(newline="", encoding="utf-8") as fh:
        iso = {r["name"].lower(): r["iso2"] for r in csv.DictReader(fh)}
    iso.update(COUNTRY_ALIAS)
    out = []
    for o in body["orgs"]:
        label = o.get("country") or ""
        funcs = [f for f in FUNCTIONS if f in (o.get("type") or "").lower()]
        network = ORG_NETWORK.get(o["name"]) or ("icos" if o["name"].startswith("ICOS ") else None)
        box1 = o["source"] == "ecs2.70789-box1"
        out.append((sha16(f"org:{o['name']}|{o.get('url') or ''}"), o["name"], o.get("name_en"),
                    o.get("acronym"), o.get("url"), scope_of(o), o.get("region"),
                    iso.get(label.lower()), label, funcs or None, o.get("description"),
                    (o.get("acronym") or o["name"]) in GENNI_CASE, network, o["source"],
                    f"https://doi.org/{PAPER_DOI}" if box1 else SURVEY_URL))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    geri_db.add_argparse_catalog(ap)
    args = ap.parse_args()

    orgs = org_rows()
    papers = json.loads(PAPERS.read_text())
    pub_rows = [(sha16("doi:" + p["doi"]), p["doi"], p["title"], p.get("abstract"), p["pub_year"],
                 p["pub_type"], p.get("journal"), None, 0, p["url"], p["registry"],
                 papers["retrieved_at"]) for p in papers["publications"]]
    prof_rows = [(n, v, r, var, prod, sites, notes, AS_OF, PAPER_DOI)
                 for n, v, r, var, prod, sites, notes in RI_PROFILES]

    con = geri_db.connect(catalog=args.catalog, data=args.lake_data)
    with geri_db.transaction(con, f"load_geri_paper: {len(prof_rows)} RI profiles, "
                                  f"{len(orgs)} partner organizations, {len(pub_rows)} publications "
                                  f"(doi:{PAPER_DOI})"):
        for change in geri_db.ensure_schema(con):
            print(f"[schema] {change}")
        con.execute("DELETE FROM ri_profiles")
        con.executemany("INSERT INTO ri_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", prof_rows)
        con.execute("DELETE FROM network_organizations")
        con.executemany("INSERT INTO network_organizations VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", orgs)
        con.execute("CREATE OR REPLACE TEMP TABLE s_pub (publication_id VARCHAR, doi VARCHAR, "
                    "title VARCHAR, abstract VARCHAR, pub_year INTEGER, pub_type VARCHAR, "
                    "journal VARCHAR, venue VARCHAR, cited_by_count INTEGER, url VARCHAR, "
                    "source VARCHAR, retrieved_at DATE)")
        con.executemany("INSERT INTO s_pub VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", pub_rows)
        res = geri_db.merge_upsert(con, "publications", ["publication_id"], "s_pub")
        geri_db.assert_integrity(con, ["ri_profiles", "network_organizations", "publications", "networks"])
    n_net = sum(1 for o in orgs if o[12])
    n_case = sum(1 for o in orgs if o[11])
    print(f"[ri_profiles] {len(prof_rows)}")
    print(f"[network_organizations] {len(orgs)} ({n_net} are catalogue networks, "
          f"{n_case} in the GENNI use case, {sum(1 for o in orgs if o[7])} with one country)")
    print(f"[publications] {res}")
    snap = geri_db.latest_snapshot(con)
    print(f"[done] snapshot {snap.get('snapshot_id')} \"{snap.get('commit_message')}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
