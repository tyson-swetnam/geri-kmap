# geri-kmap: Global Ecosystem Research Infrastructure sites

An interactive map and database of the sites of the six research infrastructures (RIs) in the
**Global Ecosystem Research Infrastructure (GERI)**:

- **NEON**: National Ecological Observatory Network (United States)
- **eLTER**: Integrated European Long-Term Ecosystem, critical zone and socio-ecological Research
- **ICOS**: Integrated Carbon Observation System (Europe)
- **TERN**: Terrestrial Ecosystem Research Network (Australia)
- **SAEON** / **EFTEON**: South African Environmental Observation Network
- **CERN**: Chinese Ecosystem Research Network

GERI's NSF AccelNet project (award [2301655](https://www.nsf.gov/awardsearch/showAward?AWD_ID=2301655))
harmonizes observations across these networks, starting with ecological drought. geri-kmap
catalogues where the RIs operate and cross-walks each site's identifiers across registries. It also
records which sites the GERI harmonized products cover. Those products live on the CyVerse Data
Store at `/iplant/home/shared/geri`.

Today the catalogue holds 990 sites in 51 countries, from DEIMS-SDR, the NEON Data API and the
ICOS Carbon Portal. See [`docs/`](docs/index.md).

## Repository layout

A **two-stack** project, built on the engine of
[`tyson-swetnam/lto`](https://github.com/tyson-swetnam/lto) (itself forked from
[`tyson-swetnam/cod-kmap`](https://github.com/tyson-swetnam/cod-kmap)):

1. **Python data pipeline** (`scripts/`, `schema/`, `data/`):
   - Fetchers read each RI registry into `data/raw/R-GERI-*/` (committed).
   - `scripts/load_geri_sites.py` writes those files into a local [DuckLake](https://ducklake.select)
     store of record (DuckDB 2.0, SQLite catalog at `db/geri_catalog.sqlite`; data files in
     `db/lake/`; both gitignored).
   - `scripts/export_parquet.py` writes Parquet and GeoJSON to `public/`. The committed
     `public/parquet/` is the canonical copy of the data.
2. **Static MapLibre + DuckDB-Wasm site** (`index.html`, `src/`, `public/`), published to GitHub
   Pages with **no build step**.

## Quick start

Python 3.11 or newer (DuckDB 2.0).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/rebuild_lake_from_parquet.py   # public/parquet/ → db/geri_catalog.sqlite + db/lake/
python scripts/qa.py                          # data-quality + schema-constraint gate
python -m http.server 5173                    # then open http://localhost:5173/
```

Refresh from the registries:

```bash
python scripts/fetch_deims.py && python scripts/fetch_neon.py && python scripts/fetch_icos.py
python scripts/load_geri_sites.py
python scripts/apply_facility_fixes.py
python scripts/qa.py
python scripts/export_parquet.py && python scripts/export_view_caches.py
```

## License

Code: MIT (see `LICENSE`). Site records keep the terms of their source registries; see
[`docs/sources.md`](docs/sources.md).
