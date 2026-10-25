# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo shape

`geri-kmap` is a catalogue of the sites of the six GERI research infrastructures (NEON, eLTER, ICOS, TERN, SAEON/EFTEON, CERN). It reuses the engine of [`tyson-swetnam/lto`](https://github.com/tyson-swetnam/lto), which was forked from [`tyson-swetnam/cod-kmap`](https://github.com/tyson-swetnam/cod-kmap). It is a **two-stack** project:

1. **Python data pipeline** (`scripts/`, `schema/`, `data/`):
   - Fetchers read RI registries into `data/raw/R-GERI-*/`.
   - Loaders write a **DuckLake** store of record (DuckDB 2.0, SQLite catalog).
   - Parquet, GeoJSON and a JSON view cache are exported to `public/`.
2. **Static MapLibre + DuckDB-Wasm site** (`index.html`, `src/`, `public/`), published to GitHub Pages with **no build step**. ES modules + CDN importmap; do not introduce npm/Vite.

The browser reads `public/parquet/*.parquet` over HTTP range requests via DuckDB-Wasm. It uses `public/facilities.geojson` as a first-paint fallback and `public/cache/browse_cards.json` as the Browse fast path. The browser never touches the lake.

The store is `db/geri_catalog.sqlite` (catalog) + `db/lake/` (data files), both gitignored, opened only through `scripts/geri_db.py`.

## Common commands

```bash
python -m venv .venv && source .venv/bin/activate   # Python >= 3.11
pip install -r requirements.txt                      # pins duckdb==2.0.0

python scripts/rebuild_lake_from_parquet.py   # FIRST after a clone or pull (--empty: schema only)
python scripts/fetch_deims.py                 # DEIMS-SDR sites of the 6 RIs + GERI network (caches details in data/cache/)
python scripts/fetch_neon.py                  # NEON sites + habitat / field-site URL
python scripts/fetch_icos.py                  # ICOS ES/AS/OS stations with a station class
python scripts/load_geri_sites.py             # data/raw/R-GERI-* → lake (owns every R-GERI-* facility)
python scripts/apply_facility_fixes.py        # data/seed/facility_fixes.csv — ALWAYS after load_geri_sites
python scripts/qa.py                          # the correctness gate (non-zero on failure)
python scripts/export_parquet.py              # lake → public/parquet/, public/facilities.geojson
python scripts/export_view_caches.py          # → public/cache/browse_cards.json
python scripts/build_country_bbox.py          # Natural Earth → schema/vocab/country_{bbox,names}.csv (rarely)

python -m http.server 5173                    # web UI
```

The canonical sequence after a data change is: load → `apply_facility_fixes.py` → `qa.py` → `export_parquet.py` → `export_view_caches.py` → `cp schema/vocab/*.csv public/vocab/`. `load_geri_sites.py` rewrites every facility it owns, so it overwrites the fixes; re-run `apply_facility_fixes.py` after it every time.

There is no test framework. `qa.py` is the only correctness gate; add new invariants there rather than introducing pytest. Its JS parse check needs `node` on PATH. QA checks:
- every PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK / NOT NULL in `schema/schema.sql`, against the lake;
- every facility is in GERI or a continental RI;
- no `site_identifiers` value (deims-id, neon-site, icos-station, geri-harmonized-id) names two facilities;
- every point falls inside a Natural Earth box of its country. Marine sites, ICOS ocean stations and stations south of 60° S are exempt.

## DuckLake store (unchanged from lto)

- **Layout.** `db/geri_catalog.sqlite` is the DuckLake 1.1 catalog; `db/lake/` holds its parquet data files. Writers are serialised by an exclusive `flock` on `<catalog>.lock`, held by `geri_db.transaction()`.
- **One way in.** Every script calls `geri_db.connect()` (`read_only=True` for readers). It raises `LakeNotFound` rather than creating an empty lake; only the rebuild passes `create=True`.
- **Scratch lakes.** Set `GERI_LAKE_CATALOG=/path/cat.sqlite` (and optionally `GERI_LAKE_DATA`), or pass `--catalog` / `--lake-data`. With a non-default catalog the exporters write to `<catalog dir>/export/`, not `public/`.
- **One run, one snapshot.** Wrap writes in `with geri_db.transaction(con, "script: what changed"):`. `geri_db.ensure_schema(con)` recreates every view, so call it **inside** the transaction; outside, each view becomes its own snapshot.
- **The lake is disposable; `public/parquet/` is not.** Unexported lake changes are lost on a rebuild.

## Critical gotchas

- **Constraints are logical, enforced by QA, not at write time.** DuckLake rejects PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK, indexes and sequences. `schema/schema.sql` keeps them all, but it runs only in an in-memory spec database. Loaders call `geri_db.assert_integrity(con, tables)` before COMMIT.
- **Upserts are `MERGE`, never `INSERT OR REPLACE` / `ON CONFLICT`.** Use `geri_db.merge_upsert`.
- **DuckDB 2.0 Python API.** `Relation.fetchone()` is removed (use `geri_db.scalar()` / `geri_db.rows()`). `.pl()` / `.arrow()` on `execute()` are removed.
- **Browser SQL is DuckDB 1.5 SQL** (`@duckdb/duckdb-wasm@1.33.1-dev65.0`). Anything in `src/` must run on 1.5.
- **Views live in two places.** A view the frontend needs goes in **both** `schema/schema.sql` and `helperViews` in `src/db.js`. `v_facility_geri` is the GERI one.
- **The table lists must agree.** They are `TABLES` in `scripts/export_parquet.py` and the `tables` / `lazyTables` arrays in `src/db.js`. A new table also needs a row in `schema/table_descriptions.csv`, or the MESA publish preflight fails.
- **The Browse cache bypasses DuckDB.** `src/views/list.js` reads `public/cache/browse_cards.json` first. Keep `BROWSE_SQL` in `scripts/export_view_caches.py` and the fallback SQL in `list.js` identical.
- **Vocabularies are duplicated** in `schema/vocab/` (canonical) and `public/vocab/` (served). One mapping, `scripts/load_vocab.py`, is used by the loaders and by QA's vocab-sync check.
- **The scope lens is defined twice.** `SCOPES` in `src/filters.js` has `sql` for DuckDB and `test` over the GeoJSON properties (`ris`, `geri_harmonized`) that `export_parquet.py` writes. Keep them in step.
- **Export is deterministic.** Re-exporting unchanged data gives byte-identical files, so a diff in `public/` is a real change.

## GERI site layer

- **Identity.** One facility per DEIMS-SDR site, `sha1("deims:" + uuid)[:16]`. NEON joins DEIMS through the `deimsId` NEON publishes. ICOS stations join through the station URI DEIMS records in the site's ICOS affiliation, normalised to `ES_FR-Lus`. An unmatched ICOS station becomes `sha1("icos:" + key)[:16]`. Nothing is matched by distance; co-located stations that are really one site go through `merge_facilities.py` with a reviewed `data/seed/facility_merge_seed.csv` row.
- **Umbrella sites.** When several DEIMS sites name one ICOS station (an LTSER platform and the plot inside it), the station id goes to the most specific one: not a platform, then the closest name. The loader prints each decision.
- **Precedence.** RI-native values (NEON coordinates, name, habitat; ICOS coordinates) win over DEIMS. `facilities.country` is where the site is, not the operating country. DEIMS gives a list; the loader picks the listed country whose box holds the point. Corrections go in `data/seed/facility_fixes.csv` with a source per row.
- **Nothing from recall.** Every site, coordinate and id comes from a fetched registry response or a cited page. Vocabulary URLs were checked by fetching them.
- **DEIMS network ids** are hard-coded in `fetch_deims.NETWORKS` and `load_geri_sites.DEIMS_NETWORK` (keep them equal), as read from `https://deims.org/api/networks`.

### Known gaps (next waves)

- **Harmonized-site flag:** map each `site_id` in `/iplant/home/shared/geri/geri-harmonized/geri_harmonized_sites.csv` to a facility as a `geri-harmonized-id`. NEON (`US-ABBY` → ABBY) and ICOS (`BE-Bra` → `ES_BE-Bra`) map by code. eLTER sites map via `geri-metadata/elter/*.json`. Known defects in that CSV must be cited fixes, not silent edits:
  - `US-NOGP` longitude is positive;
  - `NL-Loo` latitude is 57.199 (Loobos is about 52.17);
  - `FI-Värriö` is mis-encoded;
  - `AU-ASM`/`AU-TTE` and `AU-Ya1`/`AU-Ya2` share coordinates.
- **TERN OzFlux towers and SAEON/EFTEON flux sites** are missing from DEIMS. Source them from TERN/SAEON registries or `geri-metadata/{tern,saeon}/`.
- **Harmonized coverage:** `data_archives` / `data_products` pointer rows for `/iplant/home/shared/geri/geri-harmonized/*.parquet`, plus `harmonized_coverage` computed from those files. `POINTER_ARCHIVES` in `qa.py` already names `geri-cyverse`. Write it as `scripts/load_geri_archives.py`, modelled on lto's `scripts/load_lto_archives.py`.
- **Frontend:** a colour-by-RI mode needs a scalar `primary_ri` on both the DuckDB and the GeoJSON paths. A site panel should show `site_identifiers` and `harmonized_coverage`. The Stats tab still has lto sections that read absent derived tables.

## MESA project on the CyVerse Data Store

The published copy goes to `/iplant/home/shared/geri/geri-kmap`, its own MESA project inside the shared GERI collection. **Never write AVUs on the parent `/iplant/home/shared/geri`**: it carries the collection's DataCite record.

- `scripts/publish_to_mesa.py` is still lto's (target `/iplant/home/tswetnam/lto`, `lto.*` AVUs). Retarget it before the first publish.
- Metadata goes through mesa-mcp (`ds_add_avus`), never `imeta`. iRODS adds AVUs and never replaces them: delete the old value first. Keep values under about 400 characters.
- Run `mesa_ducklake_init_project` on the target once per machine before writing AVUs.
