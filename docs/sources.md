# Sources

Every value in the catalogue is read from one of these sources. The fetchers write what the source returns, as written, to `data/raw/`, which is committed. The loaders map those files into the lake.

| Source | Endpoint | Fetcher | Raw file |
|---|---|---|---|
| DEIMS-SDR | `https://deims.org/api/sites?network=<id>` and `/api/sites/<uuid>` | `scripts/fetch_deims.py` | `data/raw/R-GERI-DEIMS/sites_deims.json` |
| NEON Data API | `https://data.neonscience.org/api/v0/sites` and `/locations/<site>` | `scripts/fetch_neon.py` | `data/raw/R-GERI-NEON/sites_neon.json` |
| ICOS Carbon Portal | SPARQL `https://meta.icos-cp.eu/sparql` | `scripts/fetch_icos.py` | `data/raw/R-GERI-ICOS/stations_icos.json` |
| Natural Earth 1:10m admin-0 | natural-earth-vector v5.1.2 | `scripts/build_country_bbox.py` | `schema/vocab/country_bbox.csv`, `country_names.csv` |
| GERI Data Store | `/iplant/home/shared/geri` (CyVerse) | (harmonized-site mapping, in progress) | |

DEIMS network ids are listed in `scripts/fetch_deims.py` and were read from `https://deims.org/api/networks`.

Corrections to source values go in `data/seed/facility_fixes.csv`, one cited fact per row, applied by `scripts/apply_facility_fixes.py` after the loaders. Today there are two. Both set `country` to where the site is: Station Nord, which ICOS files under Denmark, is in Greenland; OMERE Kamech, which DEIMS files under France, is in Tunisia.
