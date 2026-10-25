# Sources

Every value in the catalogue is read from one of these sources. The fetchers write what the source returns, as written, to `data/raw/`, which is committed. The loaders map those files into the lake.

| Source | Endpoint | Fetcher | Raw file |
|---|---|---|---|
| DEIMS-SDR | `https://deims.org/api/sites?network=<id>` and `/api/sites/<uuid>` | `scripts/fetch_deims.py` | `data/raw/R-GERI-DEIMS/sites_deims.json` |
| NEON Data API | `https://data.neonscience.org/api/v0/sites` and `/locations/<site>` | `scripts/fetch_neon.py` | `data/raw/R-GERI-NEON/sites_neon.json` |
| ICOS Carbon Portal | SPARQL `https://meta.icos-cp.eu/sparql` | `scripts/fetch_icos.py` | `data/raw/R-GERI-ICOS/stations_icos.json` |
| TERN OzFlux | THREDDS `https://dap.tern.org.au/thredds/catalog/ecosystem_process/ozflux/`; L3 global attributes from OPeNDAP `.das` | `scripts/fetch_ozflux.py` | `data/raw/R-GERI-TERN/sites_ozflux.json` |
| GERI Data Store | anonymous WebDAV `https://data.cyverse.org/dav-anon/iplant/projects/geri/` (iRODS `/iplant/home/shared/geri`) | `scripts/fetch_geri_datastore.py` | `data/raw/R-GERI-HARMONIZED/` (site list, eLTER DEIMS records, SAEON DataCite records, file listing) |
| GERI harmonized parquet | the same, `geri-harmonized/*.parquet` | `scripts/summarize_harmonized.py --download` | `data/raw/R-GERI-HARMONIZED/harmonized_summary.csv` |
| Natural Earth 1:10m admin-0 | natural-earth-vector v5.1.2 | `scripts/build_country_bbox.py` | `schema/vocab/country_bbox.csv`, `country_names.csv` |

DEIMS network ids are listed in `scripts/fetch_deims.py` and were read from `https://deims.org/api/networks`.

Corrections to source values go in `data/seed/facility_fixes.csv`, one cited fact per row, applied by `scripts/apply_facility_fixes.py` after the loaders. Today there are three facilities with fixes:
- Station Nord: ICOS files it under Denmark, but it is in Greenland.
- OMERE Kamech: DEIMS files it under France, but it is in Tunisia.
- Benfontein Savanna EC: its DataCite point is 500 km off.

Harmonized site ids the rules cannot place are mapped in `data/seed/geri_harmonized_site_map.csv`, each row with its evidence (see [Harmonized](harmonized.md)).
