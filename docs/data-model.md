# Data model

The schema is lto's (itself cod-kmap's), with two GERI tables added. Constraints are declared in `schema/schema.sql` and enforced by `scripts/qa.py`; the DuckLake store cannot hold them.

## Sites

- **facilities**: one row per site. `facility_id` is `sha1("deims:" + DEIMS uuid)[:16]` for a DEIMS site, or `sha1("icos:" + station)[:16]` for an ICOS station with no DEIMS record.
  - `country` is where the site is (ISO 3166-1 alpha-2), not the operating country.
  - `established` comes from DEIMS. `record_length_years` and `long_term_threshold_met` (at least 10 years) are derived from it.
- **locations**: the points of a site. One per registry that gives coordinates, so an eLTER site that holds an ICOS station has both points.
- **network_membership**: site → network. `networks.level` is `global-ri-federation` (GERI), `continental-ri` (the six RIs and EFTEON) or `ri-component` (ICOS ES/AS/OS, NEON terrestrial/aquatic). `networks.parent_id` gives the hierarchy.
- **facility_spheres**: the seven-sphere classification from lto (atmosphere, cryosphere, terrestrial, arid, agriculture, ocean/estuarine, freshwater). It is derived from the DEIMS GEO BON biome and biome fields, the ICOS station type and the NEON habitat.
- **provenance**: one row per site per source, with the source URL.

## GERI tables

- **site_identifiers** (`facility_id`, `scheme`, `value`, `source_url`): every id a site carries. Schemes:
  - `deims-id`
  - `neon-site`
  - `icos-station` (the Carbon Portal station key, e.g. `ES_FI-Hyy`)
  - `geri-harmonized-id` (the site id in the GERI harmonized products)
  - `<network>-site-code` (the network's own code in DEIMS)

  QA fails if one value of a scheme names two sites.
- **harmonized_coverage** (`facility_id`, `product_id`, `variable`, `first_ts`, `last_ts`, `n_obs`): what the GERI harmonized products hold for each site. It is derived from the parquet on the Data Store; the observations are not copied.

## Views

- **v_facility_geri**: one row per site with `ris` (its research infrastructures), `geri_harmonized` and `identifiers`. It is defined in `schema/schema.sql` and re-created in the browser by `src/db.js`.
