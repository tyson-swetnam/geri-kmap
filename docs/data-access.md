# Data access

The **Data** tab lists every archive and service that holds data for GERI sites:
- how to reach it (API root, documented calls, buckets);
- what access it needs;
- whether it answered when it was last checked.

Every site links to its research infrastructure's archive, with a per-site entry point.

## Access at a glance

| Archive | What it holds | Machine access | Access |
|---|---|---|---|
| NEON Data Portal | NEON products, 81 sites | REST (`data.neonscience.org/api/v0`) | Catalog calls public; **data calls need a NEON API token** (403 without one) |
| ICOS Carbon Portal | ICOS stations and data objects | SPARQL, station/object JSON, `icoscp` library | Metadata public; **downloads need acceptance of the ICOS CC BY 4.0 licence** |
| DEIMS-SDR | Site records of eLTER, ICOS, NEON, TERN, SAEON, CERN | REST (OpenAPI at `deims.org/api`) | Public (metadata CC BY-NC 4.0) |
| eLTER Digital Asset Register | eLTER datasets | REST (`dar.elter-ri.eu/api`) | Public |
| TERN Data Access Platform | OzFlux and other TERN netCDF | THREDDS, OPeNDAP, HTTP download | Public (CC BY 4.0) |
| TERN Data Discovery Portal | TERN metadata | OGC CSW 2.0.2 (XML) | Public |
| SAEON Open Data Platform | SAEON / EFTEON station records | REST (ODP API 2.4) | **API needs an ODP client (OAuth2)**; landing pages public |
| CNERN resource service | CERN station data | Web | **Account required** |
| GERI collection, CyVerse Data Store | GERI source and harmonized data | WebDAV (anonymous), iRODS | Read public; **iRODS needs a CyVerse account** |
| GERI DataONE portal | Harmonized datasets | DataONE Solr | Public |
| GBIF, OBIS, KNB | Biodiversity and ecological data | REST, DataONE | Public |
| NASA Earthdata, ORNL DAAC | Remote sensing and site datasets | CMR REST, S3 | Search public; **data needs an Earthdata login** |

Each archive and endpoint row carries `access_mode` (from `schema/vocab/access_modes.csv`) and the `source_url` it was read from. The Data tab's **Access** filter separates public archives from those that need an account or a licence; a 🔒 marks restricted calls.

## Per-site links

`facility_archives` gives each site an entry URL into its archive:
- **NEON site:** the data-product explorer for its site code.
- **ICOS station:** its Carbon Portal landing page (the ecosystem station when a site has several).
- **DEIMS-SDR site:** its DEIMS record. Every DEIMS site; this is a secondary link when the site's RI has its own archive.
- **OzFlux tower:** its THREDDS catalog.
- **SAEON/EFTEON station:** its ODP landing page (the URL DataCite holds for its DOI).
- **CERN station:** CNERN, which has no per-station page.
- **GERI harmonized site:** the GERI Data Store collection.

## Where the records come from

- **`data/raw/J-GERI/`:** the GERI research infrastructures' own services. Each row was read from the service's documentation or response: the DEIMS OpenAPI document, the ODP API's `openapi.json`, an ICOS data object, the NEON token tutorial and the 403 the NEON data API returns without a token.
- **`data/raw/J-LTO/`:** records copied from [lto](https://github.com/tyson-swetnam/lto) for the archives that serve GERI sites: NEON, GBIF, OBIS, KNB, NASA Earthdata, ORNL DAAC (`scripts/import_lto_archives.py`).
- **`data/seed/endpoint_checks.csv`:** `scripts/check_endpoints.py` requests every URL and records what answered: ok, auth, alive, gone or error. A row found **gone** is not loaded.

On 2026-10-25 the check found four of lto's five bucket records for these archives naming buckets that do not exist (`neon-prod-pub-1`, `neon-aop-products`, `asf-cumulus-prod-s1-slc`, `ornldaac-cumulus-prod-public`). The fifth, `podaac-ops-cumulus-public`, refused anonymous access. lto fixed its bucket table the same day ([lto#26](https://github.com/tyson-swetnam/lto/pull/26), `scripts/check_cloud_buckets.py`), checking every bucket against the storage service and the AWS Open Data Registry. The import now carries two buckets, both needing an Earthdata login: `podaac-ops-cumulus-public` and ASF's Sentinel-1 SLC bucket `asf-ngap2w-p-s1-slc-7b420b89`.

NEON serves files through pre-signed URLs from its token-protected data API, not through a public bucket.
