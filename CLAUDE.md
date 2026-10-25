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
python scripts/fetch_ozflux.py                # OzFlux towers from TERN THREDDS (L3 global attributes via .das)
python scripts/fetch_saeon_stations.py        # every SAEON / EFTEON Observations Monitor station (DataCite, prefix 10.15493)
python scripts/fetch_geri_datastore.py        # GERI Data Store (anonymous WebDAV): harmonized site list, eLTER/SAEON metadata, file listing
python scripts/summarize_harmonized.py --download   # harmonized parquet (~1 GB, data/cache/) → committed harmonized_summary.csv; only when the products change
python scripts/load_geri_sites.py             # data/raw/R-GERI-* → lake (owns every R-GERI-* facility; assigns harmonized ids)
python scripts/apply_facility_fixes.py        # data/seed/facility_fixes.csv — ALWAYS after load_geri_sites
python scripts/load_geri_archives.py          # Data Store pointer archives/products + harmonized_coverage — after load_geri_sites
python scripts/qa.py                          # the correctness gate (non-zero on failure)
python scripts/export_parquet.py              # lake → public/parquet/, public/facilities.geojson
python scripts/export_view_caches.py          # → public/cache/browse_cards.json
python scripts/build_country_bbox.py          # Natural Earth → schema/vocab/country_{bbox,names}.csv (rarely)

python -m http.server 5173                    # web UI
```

The canonical sequence after a data change is: `load_geri_sites.py` → `apply_facility_fixes.py` → `load_geri_archives.py` → `qa.py` → `export_parquet.py` → `export_view_caches.py` → `cp schema/vocab/*.csv public/vocab/`. `load_geri_sites.py` rewrites every facility it owns, so it overwrites the fixes; re-run `apply_facility_fixes.py` after it every time.

There is no test framework. `qa.py` is the only correctness gate; add new invariants there rather than introducing pytest. Its JS parse check needs `node` on PATH. QA checks:
- every PRIMARY KEY / UNIQUE / FOREIGN KEY / CHECK / NOT NULL in `schema/schema.sql`, against the lake;
- every facility is in GERI or a continental RI;
- no `site_identifiers` value (deims-id, neon-site, icos-station, geri-harmonized-id) names two facilities;
- every id in the harmonized site list resolves to a facility, or has a reviewed `unresolved` row. A harmonized id more than 25 km from its facility is a warning: it means a CSV point error or a mislabelled id.
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
- **Never `cache: 'force-cache'` a data fetch.** It served returning visitors pre-update cards. Default caching honours Pages' 10-minute max-age.
- **The Browse cache bypasses DuckDB.** `src/views/list.js` reads `public/cache/browse_cards.json` first. Keep `BROWSE_SQL` in `scripts/export_view_caches.py` and the fallback SQL in `list.js` identical.
- **Vocabularies are duplicated** in `schema/vocab/` (canonical) and `public/vocab/` (served). One mapping, `scripts/load_vocab.py`, is used by the loaders and by QA's vocab-sync check.
- **The scope lens is defined twice.** `SCOPES` in `src/filters.js` has `sql` for DuckDB and `test` over the GeoJSON properties (`ris`, `geri_harmonized`) that `export_parquet.py` writes. Keep them in step.
- **Export is deterministic.** Re-exporting unchanged data gives byte-identical files, so a diff in `public/` is a real change.

## GERI site layer

- **Identity.** One facility per DEIMS-SDR site, `sha1("deims:" + uuid)[:16]`. NEON joins DEIMS through the `deimsId` NEON publishes. ICOS stations join through the station URI DEIMS records in the site's ICOS affiliation, normalised to `ES_FR-Lus`. An unmatched ICOS station becomes `sha1("icos:" + key)[:16]`. DEIMS station codes are canonicalised to Carbon Portal keys (`icos_canonicalizer`: case-insensitive, prefix optional). Nothing is matched by distance alone. One field site recorded twice is joined by a reviewed `data/seed/facility_merge_seed.csv` row (survivor_id, duplicate_id, evidence), which **`load_geri_sites.py` applies itself** (`merge_sites`). `merge_facilities.py` (lto) would be undone by the next load, because the loader rebuilds every site from the raw sources. A seed row naming an id no source produces stops the load. QA fails if a merged id is back.
- **Umbrella sites.** When several DEIMS sites name one ICOS station (an LTSER platform and the plot inside it), the station id goes to the most specific one: not a platform, then the closest name. The loader prints each decision.
- **Precedence.** RI-native values (NEON coordinates, name, habitat; ICOS coordinates) win over DEIMS. `facilities.country` is where the site is, not the operating country. DEIMS gives a list; the loader picks the listed country whose box holds the point. Corrections go in `data/seed/facility_fixes.csv` with a source per row.
- **More sources.**
  - OzFlux towers (`fetch_ozflux.py`) attach to a TERN DEIMS site whose TERN code carries the tower's FLUXNET code (`TERN_ASM_AU_11` ↔ `AU-ASM`). Otherwise each is its own facility, `sha1("ozflux:" + folder)`. A `fluxnet_id` that is malformed or not unique is ignored (Wedgetail says `Au-Sil`).
  - SAEON/EFTEON stations: every Observations Monitor DOI from DataCite (`fetch_saeon_stations.py`), `sha1("doi:" + doi)`. EFTEON by creator or an 'EFTEON …' subject; the landscape comes from `EFTEON_LANDSCAPE`. Types are `weather-station` and `flux-tower`.
  - CERN stations DEIMS lacks come from CERN's brochure (`data/seed/cern_stations.csv`, `sha1("cern:" + name)`); today only Daya Bay.
  - When a DEIMS point lies more than 50 km from the ICOS station the site holds, the ICOS coordinates win (Monte Bondone, Hetzdorf, Las Majadas).
- **Harmonized ids.** `resolve_harmonized()` tries, in order:
  1. the reviewed `data/seed/geri_harmonized_site_map.csv` (every row has evidence);
  2. NEON `US-ABBY` → neon-site ABBY;
  3. ICOS `BE-Bra` → `ES_BE-Bra`;
  4. TERN `AU-How` → fluxnet-id.

  The seed outranks the rules on purpose: the products mislabel some ICOS ids (FR-FBn is Fontainebleau, i.e. ICOS FR-Fon), and the products' `site_name` decides. Scheme `harmonized-only` builds a facility from the CSV point and product name, for sites no registry has. The harmonized CSV is Latin-1. `docs/harmonized.md` lists every defect found in it; report them upstream, don't edit them in.
- **Timezones.** `summarize_harmonized.py` and `load_geri_archives.py` set DuckDB's `TimeZone` to UTC. Without it, timestamps print in the machine's zone and committed files differ by machine.
- **Nothing from recall.** Every site, coordinate and id comes from a fetched registry response or a cited page. Vocabulary URLs were checked by fetching them.
- **DEIMS network ids** are hard-coded in `fetch_deims.NETWORKS` and `load_geri_sites.DEIMS_NETWORK` (keep them equal), as read from `https://deims.org/api/networks`.

### Known gaps (next waves)

- **More duplicates** may surface as sources grow. Find candidates by same name within about 10 km across sources; a reviewed seed row merges them.
- **CERN completeness:** DEIMS's 42 plus the brochure's Daya Bay. CERN's English site (www.cern.ac.cn:8080) was unreachable; check it for a current list.
- **Frontend:** the map colours by RI by default (`RI_COLORS` in `src/map.js`, hues validated with the dataviz palette script). `primary_ri` is the RI whose label `load_geri_sites.py` writes to `facilities.parent_org` (its `RI_ORDER`); `export_parquet.py`'s GeoJSON and `query()` in `src/db.js` derive it identically. Browse cards and map popups show registry ids and harmonized coverage. Both read the site's card from `browse_cards.json` through `src/cards.js` (one loader, one set of labels); the card SQL is the `ids` / `cov` CTEs in both `BROWSE_SQL` and `list.js`.

## MESA project on the CyVerse Data Store

The published copy goes to `/iplant/home/shared/geri/geri-kmap`, its own MESA project inside the shared GERI collection. **Never write AVUs on the parent `/iplant/home/shared/geri`**: it carries the collection's DataCite record.

- **Published.** First publish was 2026-10-25, commit `15148ae`, 48 tables. Republished the same day at `ebdcee1` (1,019 sites, after the duplicate merges). The project is registered in the DuckLake catalog as `59c8732f-…`. Public read: `https://data.cyverse.org/dav-anon/iplant/projects/geri/geri-kmap/`.
- `scripts/publish_to_mesa.py`: `--dry-run`, then a real run (`gocmd sync`). Then apply `.mesa_publish_avus.json` through mesa-mcp: delete the previous `geri_kmap.publish.*` values on the root first, then one `ds_add_avus` per target. Table AVUs (`geri_kmap.table.*`) come from `schema/table_descriptions.csv`; re-add one only when its value changes, deleting the old value first.
- **Upload by checksum.** The upload used to run `gocmd sync --no_hash`, which compares sizes only. A same-size changed file (`MANIFEST.json`, `TABLES.json`, a doc) was silently skipped. The script now syncs by checksum.
- **Replica lag.** iRODS keeps two replicas (ds28, corral4). After an upload the second is marked Stale until CyVerse replicates it, and the anonymous `dav-anon` URL can serve the stale copy for a while. Verify against iRODS (`gocmd ls -l`, mesa-mcp `ds_read_file`), not the anonymous URL.
- The root carries a DataCite record written with `mesa_avu_apply_datacite`. That tool wants `titles` as strings and `value` keys, and has no `fundingReferences`. The NSF funding reference is therefore plain `datacite.fundingReference.1.*` AVUs, named as on the parent. Writes and deletes of values near 560 characters land in iRODS but report no server response and miss the DuckLake mirror. The current description is kept under 400 characters.
- Metadata goes through mesa-mcp (`ds_add_avus`), never `imeta`. iRODS adds AVUs and never replaces them: delete the old value first. Keep values under about 400 characters.
- Run `mesa_ducklake_init_project` on the target once per machine before writing AVUs.
