#!/usr/bin/env python3
"""Pre-compute the Browse view-card JSON cache.

The Browse view runs multi-CTE aggregation queries against DuckDB-Wasm on
first paint. On a high-RTT mobile link that means: download 8+
parquet files, parse the Arrow result, deserialize ~600 rows of nested
list/struct columns. End-to-end ~3-10 seconds.

This script runs the SAME SQL the views run, materialises the result
as a static JSON file under `public/cache/`, and the views fetch it
on first paint with a single HTTP request. Render becomes
fetch + JSON.parse + DOM build — sub-second on mobile.

DuckDB stays as the fallback path if the cache is missing or stale,
so the SQL tab keeps working and any future filtered queries still
go through the full DuckDB path.

The SQL reads the DuckLake store of record (scripts/geri_db.py),
read-only. Output is deterministic: every result set has a total
ORDER BY and every list() aggregate orders its elements with a unique
tie-break, so re-running on unchanged data rewrites byte-identical JSON
and a diff of public/cache/ shows only real changes. (Before this, row
order followed whatever the engine produced, and DuckDB 1.5 and 2.0
produced different orders from the same data.) The ordering changes
alter neither columns nor types, so the row shape still matches the
in-file fallback SQL in src/views/list.js.

Usage::

    python scripts/export_view_caches.py
    python scripts/export_view_caches.py --out /tmp/x/cache
    python scripts/export_view_caches.py --catalog /tmp/x/cat.sqlite
                                         # -> /tmp/x/export/cache/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geri_db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "public" / "cache"


BROWSE_SQL = """
WITH base AS (
  SELECT f.facility_id        AS id,
         f.canonical_name     AS name,
         f.acronym,
         f.facility_type      AS type,
         f.country,
         f.state,
         f.region,
         f.hq_lat             AS lat,
         f.hq_lng             AS lng,
         f.url,
         f.parent_org,
         f.established,
         f.record_length_years,
         f.long_term_threshold_met,
         f.data_portal_url,
         (SELECT min(sphere_slug) FROM facility_spheres
          WHERE facility_id = f.facility_id AND role = 'primary')
                              AS primary_sphere,
         (SELECT list(sphere_slug ORDER BY sphere_slug) FROM facility_spheres
          WHERE facility_id = f.facility_id AND role = 'secondary')
                              AS secondary_spheres
  FROM facilities f
),
nets AS (
  SELECT nm.facility_id,
         list(struct_pack(slug := n.network_id, label := n.label, url := n.url)
              ORDER BY n.network_id) AS networks
  FROM network_membership nm
  JOIN networks n ON n.network_id = nm.network_id
  GROUP BY nm.facility_id
),
archives AS (
  SELECT fa.facility_id,
         count(DISTINCT fa.archive_id) AS n_archives,
         list(struct_pack(
           archive_id := fa.archive_id,
           name       := da.name,
           base_url   := da.base_url,
           scope_url  := fa.scope_url,
           sample_doi := fa.sample_doi
         ) ORDER BY da.name, fa.archive_id, fa.scope_url) AS archive_list
  FROM facility_archives fa
  LEFT JOIN data_archives da ON da.archive_id = fa.archive_id
  GROUP BY fa.facility_id
),
products AS (
  SELECT facility_id, count(*) AS n_products
  FROM data_products GROUP BY facility_id
),
personnel AS (
  SELECT fp.facility_id,
         count(DISTINCT fp.person_id) AS n_personnel,
         list(struct_pack(
           person_id := p.person_id,
           name      := p.name,
           role      := fp.role,
           title     := fp.title,
           orcid     := p.orcid,
           openalex  := p.openalex_id,
           homepage  := p.homepage_url,
           is_key    := fp.is_key_personnel,
           is_current := fp.is_current
         ) ORDER BY (fp.is_current IS NOT FALSE
                     AND (fp.end_date IS NULL OR fp.end_date > current_date)) DESC,
                    CASE fp.role WHEN 'lead-PI' THEN 0 WHEN 'PI' THEN 0 WHEN 'director' THEN 1 WHEN 'executive-officer' THEN 1 WHEN 'superintendent' THEN 1 WHEN 'leader' THEN 1 WHEN 'manager' THEN 2 WHEN 'site-manager' THEN 2 WHEN 'domain-manager' THEN 2 WHEN 'deputy-director' THEN 3 WHEN 'associate-director' THEN 4 WHEN 'co-PI' THEN 5 WHEN 'co-leader' THEN 5 WHEN 'leadership-team' THEN 6 ELSE 9 END, fp.is_key_personnel DESC, fp.role, fp.person_id, fp.title)
                              AS personnel_list
  FROM facility_personnel fp
  JOIN people p ON p.person_id = fp.person_id
  GROUP BY fp.facility_id
),
pubs AS (
  SELECT fp.facility_id,
         count(DISTINCT a.publication_id) AS n_pubs
  FROM authorship a
  JOIN facility_personnel fp ON fp.person_id = a.person_id
  GROUP BY fp.facility_id
),
funding AS (
  SELECT fe.facility_id,
         count(*) AS n_funding,
         list_sum(list(coalesce(fe.amount_usd, 0) ORDER BY fe.event_id))
                                     AS total_funding,
         list(struct_pack(
           funder := fr.name,
           program := fe.program,
           amount := fe.amount_usd,
           fy := fe.fiscal_year
         ) ORDER BY coalesce(fe.amount_usd, 0) DESC, fe.fiscal_year DESC,
                    fr.name, fe.program, fe.event_id) AS funding_list
  FROM funding_events fe
  JOIN funders fr ON fr.funder_id = fe.funder_id
  GROUP BY fe.facility_id
),
ids AS (
  SELECT facility_id,
         list(struct_pack(scheme := scheme, value := value, url := source_url)
              ORDER BY scheme, value) AS identifiers
  FROM site_identifiers
  GROUP BY facility_id
),
cov AS (
  SELECT h.facility_id,
         list(struct_pack(
           product  := p.title,
           variable := h.variable,
           first    := strftime(h.first_ts, '%Y-%m-%d'),
           last     := strftime(h.last_ts, '%Y-%m-%d'),
           n        := CAST(h.n_obs AS INTEGER)
         ) ORDER BY p.title, h.variable) AS coverage
  FROM harmonized_coverage h
  JOIN data_products p ON p.product_id = h.product_id
  GROUP BY h.facility_id
),
areas AS (
  SELECT al.facility_id, list(DISTINCT ra.label ORDER BY ra.label) AS research_areas
  FROM area_links al
  JOIN research_areas ra ON ra.area_id = al.area_id
  GROUP BY al.facility_id
)
SELECT b.*,
       coalesce(n.networks, [])                  AS networks,
       coalesce(a.n_archives, 0)                 AS n_archives,
       coalesce(a.archive_list, [])              AS archive_list,
       coalesce(pr.n_products, 0)                AS n_products,
       coalesce(pe.n_personnel, 0)               AS n_personnel,
       coalesce(pe.personnel_list, [])           AS personnel_list,
       coalesce(pu.n_pubs, 0)                    AS n_pubs,
       coalesce(fu.n_funding, 0)                 AS n_funding,
       coalesce(fu.total_funding, 0)             AS total_funding,
       coalesce(fu.funding_list, [])             AS funding_list,
       coalesce(i.identifiers, [])               AS identifiers,
       coalesce(c.coverage, [])                  AS coverage,
       coalesce(ar.research_areas, [])           AS research_areas
FROM base b
LEFT JOIN nets      n  ON n.facility_id  = b.id
LEFT JOIN archives  a  ON a.facility_id  = b.id
LEFT JOIN products  pr ON pr.facility_id = b.id
LEFT JOIN personnel pe ON pe.facility_id = b.id
LEFT JOIN pubs      pu ON pu.facility_id = b.id
LEFT JOIN funding   fu ON fu.facility_id = b.id
LEFT JOIN areas     ar ON ar.facility_id = b.id
LEFT JOIN ids       i  ON i.facility_id  = b.id
LEFT JOIN cov       c  ON c.facility_id  = b.id
ORDER BY b.id
"""


def to_jsonable(v):
    """Recursively convert DuckDB results to plain JSON-friendly Python.

    DuckDB returns LIST<STRUCT> as nested dicts/lists already; the only
    fixups needed are bytes (none here) and Decimals (we only have ints
    + floats). Drop nulls inside list items so the JS view doesn't have
    to defend against {} placeholders.
    """
    if v is None:
        return None
    if isinstance(v, list):
        return [to_jsonable(x) for x in v if x is not None]
    if isinstance(v, dict):
        return {k: to_jsonable(val) for k, val in v.items()}
    return v


def export_query(conn, sql: str, out_path: Path) -> int:
    # Use DuckDB's native dict-row fetcher (no pyarrow dependency).
    # `fetchall()` returns tuples; combine with the cursor's description
    # to build per-row dicts. LIST<STRUCT> columns come back as nested
    # Python lists/dicts already.
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    payload = [
        {col: to_jsonable(val) for col, val in zip(cols, row)}
        for row in cur.fetchall()
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.tmp")
    # Compact JSON — every byte saved is a byte mobile users don't pay
    # for. The browser does JSON.parse anyway so whitespace adds no
    # value. Use ensure_ascii=False so unicode (Guánica, Pu'u Maka'ala)
    # stays as UTF-8 instead of \u escapes.
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, out_path)
    return len(payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    geri_db.add_argparse_catalog(ap)
    ap.add_argument("--out", type=Path, default=None,
                    help="cache dir (default: public/cache; <catalog dir>/export/cache "
                         "for a non-default catalog, so a scratch lake never "
                         "overwrites the committed caches)")
    args = ap.parse_args()
    if args.out is None:
        if geri_db.is_default_catalog(args.catalog):
            args.out = DEFAULT_OUT
        else:
            args.out = geri_db.catalog_path(args.catalog).parent / "export" / "cache"
            print(f"[note] non-default catalog: writing to {args.out} rather than "
                  "public/cache (pass --out to override)", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)

    try:
        conn = geri_db.connect(read_only=True, catalog=args.catalog, data=args.lake_data)
    except geri_db.LakeNotFound as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    with conn:

        n_browse = export_query(conn, BROWSE_SQL, args.out / "browse_cards.json")
        print(f"[cache] wrote {n_browse:4d} rows → {args.out / 'browse_cards.json'}"
              f"  ({(args.out / 'browse_cards.json').stat().st_size // 1024} KB)")


    return 0


if __name__ == "__main__":
    raise SystemExit(main())
