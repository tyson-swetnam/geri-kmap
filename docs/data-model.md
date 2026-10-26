# Data model

The schema is lto's (itself cod-kmap's), with four GERI tables added. Constraints are declared in `schema/schema.sql` and enforced by `scripts/qa.py`; the DuckLake store cannot hold them.

## Sites

- **facilities**: one row per site. `facility_id` is `sha1("<source>:" + id)[:16]`, where source is `deims` (DEIMS uuid), `icos` (an ICOS station with no DEIMS record), `ozflux` (an OzFlux folder with no TERN SuperSite), `doi` (a SAEON station), `ausplots` (a TERN surveillance plot), `mexflux` (a MexFlux tower) or `geri-harmonized` (a site only the harmonized products know).
  - `country` is where the site is (ISO 3166-1 alpha-2), not the operating country.
  - `established` comes from DEIMS. `record_length_years` and `long_term_threshold_met` (at least 10 years) are derived from it.
- **locations**: the points of a site. One per registry that gives coordinates, so an eLTER site that holds an ICOS station has both points.
- **network_membership**: site → network. `networks.level` is `global-ri-federation` (GERI), `continental-ri` (the six RIs and EFTEON), `ri-component` (ICOS ES/AS/OS, NEON terrestrial/aquatic, OzFlux, TERN surveillance plots), `network-of-networks` (GENNI) or `environmental-network` (MexFlux, under GENNI). `networks.parent_id` gives the hierarchy.
- **facility_spheres**: the seven-sphere classification from lto (atmosphere, cryosphere, terrestrial, arid, agriculture, ocean/estuarine, freshwater). It is derived from the DEIMS GEO BON biome and biome fields, the ICOS station type and the NEON habitat.
- **provenance**: one row per site per source, with the source URL.

## GERI tables

- **site_identifiers** (`facility_id`, `scheme`, `value`, `source_url`): every id a site carries. Schemes:
  - `deims-id`
  - `neon-site`
  - `icos-station` (the Carbon Portal station key, e.g. `ES_FI-Hyy`)
  - `geri-harmonized-id` (the site id in the GERI harmonized products)
  - `fluxnet-id` and `ozflux-site` (OzFlux towers)
  - `doi` (SAEON/EFTEON station DataCite records)
  - `ausplots-site` (TERN surveillance plots: the AusPlots `site_location_name`)
  - `mexflux-site` and `ameriflux-id` (MexFlux towers; the second only for towers AmeriFlux registers)
  - `harmonized-only` (a site known only from the GERI products)
  - `<network>-site-code` (the network's own code in DEIMS)

  QA fails if one value of a scheme names two sites.
- **harmonized_coverage** (`facility_id`, `product_id`, `variable`, `first_ts`, `last_ts`, `n_obs`): what the GERI harmonized products hold for each site. It is derived from the parquet on the Data Store; the observations are not copied.
- **ri_profiles** (`network_id`, `data_volume_tib`, `data_rate_tib_year`, `data_variety`, `n_data_products`, `paper_site_count`, `notes`, `as_of`, `source_doi`): each RI as Loescher et al. (2026) describe it (Table 1, Figure 1).
- **network_organizations**: the 251 organizations of that paper's landscape survey plus the Mexican networks of its GENNI use case, with scope, region, country (ISO-2 when one), functions (observation, aggregation, network), `genni_case`, and `network_id` when the organization is a network the catalogue holds. See [GERI & GENNI](genni.md).
- **publications** (lto's table, otherwise empty here): the paper, the GERI paper it builds on and the two Zenodo records it cites.

## Views

- **v_facility_geri**: one row per site with `ris` (its research infrastructures, and `mexflux` for MexFlux towers), `geri_harmonized` and `identifiers`. It is defined in `schema/schema.sql` and re-created in the browser by `src/db.js`.
