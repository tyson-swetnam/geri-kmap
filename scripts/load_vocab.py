"""Reload the vocabulary tables from schema/vocab/*.csv.

One mapping, used by every loader (``load_vocab``) and by qa.py's
vocab-sync check (``VOCAB_SQL``), so the two cannot disagree on how a CSV
maps onto its table.
"""
from __future__ import annotations

from pathlib import Path

VOCAB_DIR = Path(__file__).resolve().parent.parent / "schema" / "vocab"

VOCAB_SQL = {
    "facility_types": "SELECT slug, label, description FROM read_csv_auto(?, header=True)",
    "research_areas": "SELECT slug AS area_id, label, gcmd_uri, parent_slug AS parent_id "
                      "FROM read_csv_auto(?, header=True)",
    "networks": "SELECT slug AS network_id, label, level, url, parent AS parent_id "
                "FROM read_csv_auto(?, header=True, all_varchar=True)",
    **{t: "SELECT * FROM read_csv_auto(?, header=True)"
       for t in ("spheres", "ecosystem_types", "life_zones", "archive_types",
                 "data_formats", "data_licenses", "access_modes")},
}


def load_vocab(con) -> None:
    """Replace every vocab table with its CSV. Call inside a transaction."""
    for table, sql in VOCAB_SQL.items():
        f = VOCAB_DIR / f"{table}.csv"
        if not f.exists():
            continue
        con.execute(f"DELETE FROM {table}")
        con.execute(f"INSERT INTO {table} BY NAME {sql}", [str(f)])
