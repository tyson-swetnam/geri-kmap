# Sources

Every value in the catalogue is read from one of these sources. The fetchers write what the source returns, as written, to `data/raw/`, which is committed. The loaders map those files into the lake.

| Source | Endpoint | Fetcher | Raw file |
|---|---|---|---|
| DEIMS-SDR | `https://deims.org/api/sites?network=<id>` and `/api/sites/<uuid>` | `scripts/fetch_deims.py` | `data/raw/R-GERI-DEIMS/sites_deims.json` |
| NEON Data API | `https://data.neonscience.org/api/v0/sites` and `/locations/<site>` | `scripts/fetch_neon.py` | `data/raw/R-GERI-NEON/sites_neon.json` |
| ICOS Carbon Portal | SPARQL `https://meta.icos-cp.eu/sparql` | `scripts/fetch_icos.py` | `data/raw/R-GERI-ICOS/stations_icos.json` |
| TERN OzFlux | THREDDS `https://dap.tern.org.au/thredds/catalog/ecosystem_process/ozflux/`; L3 global attributes from OPeNDAP `.das` | `scripts/fetch_ozflux.py` | `data/raw/R-GERI-TERN/sites_ozflux.json` |
| TERN AusPlots | PostgREST `http://swarmapi.ausplots.aekos.org.au/site` (one row per published plot visit) | `scripts/fetch_ausplots.py` | `data/raw/R-GERI-TERN/sites_ausplots.json` |
| SAEON / EFTEON stations | DataCite REST `https://api.datacite.org/dois?query=titles.title:"Observations Monitor"&prefix=10.15493` | `scripts/fetch_saeon_stations.py` | `data/raw/R-GERI-SAEON/stations_saeon.json` |
| CERN station list | CERN English brochure, linked from https://www.cern.ac.cn/1wljs/index.asp?channelid1=100110 | (transcribed) | `data/seed/cern_stations.csv` (only stations DEIMS lacks) |
| MexFlux (GENNI) | https://mexflux.gitlab.io/sites/ (table), `mexflux_site_map_2024.html` (points), AmeriFlux `https://amfcdn.lbl.gov/api/v1/site_display/AmeriFlux` | `scripts/fetch_mexflux.py` | `data/raw/R-GENNI-MEXFLUX/sites_mexflux.json` |
| Loescher et al. (2026) landscape survey | Zenodo record 17717896 (spreadsheet, CC BY 4.0) + the paper's Box 1 | `scripts/fetch_landscape_survey.py` | `data/raw/J-GENNI/landscape_orgs.json` |
| Papers and datasets cited | Crossref and DataCite REST APIs | `scripts/fetch_geri_papers.py` | `data/raw/J-GENNI/publications.json` |
| RI profiles | Loescher et al. (2026), Table 1 and Figure 1 (article page, 2026-10-26) | (transcribed) | `RI_PROFILES` in `scripts/load_geri_paper.py` |
| Data-access layer | each archive's documentation and API responses; lto's records for NEON, GBIF, OBIS, KNB, NASA Earthdata, ORNL DAAC | `scripts/import_lto_archives.py`, `scripts/check_endpoints.py` | `data/raw/J-GERI/`, `data/raw/J-LTO/`, `data/seed/endpoint_checks.csv` (see [Data access](data-access.md)) |
| GERI Data Store | anonymous WebDAV `https://data.cyverse.org/dav-anon/iplant/projects/geri/` (iRODS `/iplant/home/shared/geri`) | `scripts/fetch_geri_datastore.py` | `data/raw/R-GERI-HARMONIZED/` (site list, eLTER DEIMS records, SAEON DataCite records, file listing) |
| GERI harmonized parquet | the same, `geri-harmonized/*.parquet` | `scripts/summarize_harmonized.py --download` | `data/raw/R-GERI-HARMONIZED/harmonized_summary.csv` |
| Natural Earth 1:10m admin-0 | natural-earth-vector v5.1.2 | `scripts/build_country_bbox.py` | `schema/vocab/country_bbox.csv`, `country_names.csv` |

DEIMS network ids are listed in `scripts/fetch_deims.py` and were read from `https://deims.org/api/networks`.

Corrections to source values go in `data/seed/facility_fixes.csv`, one cited fact per row, applied by `scripts/apply_facility_fixes.py` after the loaders. Today there are three facilities with fixes:
- Station Nord: ICOS files it under Denmark, but it is in Greenland.
- OMERE Kamech: DEIMS files it under France, but it is in Tunisia.
- Benfontein Savanna EC: its DataCite point is 500 km off.

Harmonized site ids the rules cannot place are mapped in `data/seed/geri_harmonized_site_map.csv`, each row with its evidence (see [Harmonized](harmonized.md)).
