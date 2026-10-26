# GERI and GENNI

Loescher, H. W., M. SanClements, C. Laney, et al. 2026. "Toward a Global Ecosystem Network-of-Networks: Team Science as a Pathway for Equitable Macrosystem Collaboration." *Ecosphere* 17(10): e70789. https://doi.org/10.1002/ecs2.70789 (CC BY 4.0)

The paper describes GERI's six research infrastructures (RIs) and proposes **GENNI**, a Global Ecosystem Network-of-Networks Initiative. GENNI would be a light-governance framework that links self-organizing networks of environmental networks to GERI. GERI's member RIs cover only part of the globe, with the largest gaps in the southern hemisphere and lower-income regions. The paper argues that the main barriers to joining smaller networks to the RIs are organizational and cultural, not technical. It tests team-science methods (participatory governance, distributed leadership, a code of conduct) in a November 2024 workshop with five Mexican networks. A landscape survey found 223 organizations in 41 countries that could partner with GERI.

This page lists what geri-kmap takes from the paper and where it is in the catalogue.

## The six RIs (Table 1)

Table `ri_profiles`, one row per RI:

| RI | Data held (TiB, to Jan 2025) | Added per year (TiB) | Data types | Data products | Sites in Figure 1 | Sites in geri-kmap |
|---|---:|---:|---:|---:|---:|---:|
| NEON | 1,497 | 153.4 | 5 | 181 | 81 | 81 |
| eLTER | 454 | to be determined | ≈20 | 547 | ≈185 | 637 |
| ICOS | 963 | ≈3.0 | 94 | 41 | ≈150 | 180 |
| TERN | 164 | 10.9 | 3 | ≈2,700 | 800 | 882 |
| CERN | 8.2 | 2.7 | not available | ≈900 | 40 | 43 |
| SAEON | 1,455 | to be determined | 7 | not given | 18 | 46 |

`ri_profiles.notes` keeps the table's footnotes: NEON's figures include remote sensing, ICOS counts Level 1 and 2 products only, and CERN's product count is inflated by its naming convention.

The site counts differ for reasons that are known:

- **TERN.** The paper's 800 are mostly TERN's Ecosystem Surveillance plots. geri-kmap now loads every published plot from the AusPlots API (`scripts/fetch_ausplots.py`): **820 plots**, type `surveillance-plot`, network `tern-surveillance`. Together with 27 DEIMS sites (SuperSites and plot networks) and 47 OzFlux towers, TERN has 882 sites. The API's own statistics count 954 sites, but its `/site` table serves published visits only (1,133, matching its published-visit count). The other 134 sites are not there.
- **eLTER.** The paper counts eLTER's own sites, about 185 in Europe; eLTER has about 200 Category 1 and 2 candidates, to be labelled from 2026. geri-kmap counts every site in the DEIMS network "LTER Europe", which also holds national LTER sites outside the eLTER categories. No machine-readable list of the Category 1 and 2 candidates was found, so the category is not in the catalogue yet.
- **ICOS.** geri-kmap includes ICOS atmosphere and ocean stations as well as ecosystem stations (106 ES, 41 AS, 23 OS), each with an ICOS station class.
- **SAEON.** The paper counts sites. geri-kmap counts SAEON's DEIMS sites and also each Observations Monitor station (weather station or flux tower) as its own record.
- **CERN.** geri-kmap takes 42 stations from DEIMS and Daya Bay from CERN's brochure; seven of the DEIMS stations are newer than that brochure (see [Networks](networks.md)).

## GENNI and MexFlux (Box 1, Figure 3)

GENNI is in the `networks` vocabulary at level `network-of-networks`. **MexFlux**, the Mexican flux-tower network and the only network in the paper's Mexican use case with registered sites, sits under it at level `environmental-network`. Both are outside GERI:

- MexFlux towers are members of `mexflux` and `genni`, never of `geri`. QA fails if a GENNI site is ever placed in the GERI network.
- The map's **Scope** lens has a *MexFlux (GENNI)* entry, and the default lens is now *All sites*, not *All GERI*. In RI colouring, MexFlux is green (it was checked against NEON's aqua, its only neighbour on the map).
- **33 towers** come from MexFlux's site table and map (`scripts/fetch_mexflux.py`). The 14 registered in AmeriFlux take AmeriFlux's point and link to their AmeriFlux page (archive `ameriflux`); the other 19 take the point on MexFlux's own map.
- The site table's PI names and e-mail addresses are not stored.

The paper's other four Mexican networks have no site registry:
- **RISZA**: an international drylands network;
- **OSPE**: participatory social-ecological observatories;
- **PUEIS**: UNAM's interdisciplinary soil network;
- **YECS-IUSS**: the soil-science early-career working group.

All five are rows of `network_organizations` with `genni_case = true`. Figure 3 also maps PUEIS and YECS-IUSS sites and regions, but those are not published as data.

## The landscape survey (Table 3)

Table `network_organizations`. The survey is published as Ceron Castano, Specht, Morris and Loescher, "Terrestrial Ecosystem Observatories", https://doi.org/10.5281/zenodo.17717896 (CC BY 4.0). Version 2 of the spreadsheet lists **251 organizations**; the paper reports 223 from an earlier cut. `scripts/fetch_landscape_survey.py` reads the spreadsheet as published. The four Mexican networks it lacks are added from Box 1, for 255 rows.

| By scope | Organizations |
|---|---:|
| Domestic (one country) | 155 |
| Global | 64 |
| Regional | 25 |
| International | 1 |
| Not stated | 6 |

| By function | Organizations |
|---|---:|
| Aggregation only | 81 |
| Observation only | 71 |
| Observation and aggregation | 54 |
| Network only | 23 |
| Observation and network | 17 |
| Aggregation and network | 5 |

The domestic organizations are in 37 countries. The most are in the United States (25), Canada (21), Australia (16), Mexico (12 with the Box 1 networks), Brazil (11) and New Zealand (10).

These are organizations, not sites, so they have no points on the map. 25 of them are networks the catalogue holds, and their `network_id` says which:
- NEON, eLTER, CERN, SAEON and TERN;
- ICOS ERIC, the ICOS umbrella record and 16 national ICOS networks;
- OzFlux and MexFlux.

The survey's "Republic of China" rows are mainland organizations (CERN, the Chinese Academy of Sciences), so their country is CN. Its Location column is a broken formula in every row and is dropped.

## Publications

`publications` holds the paper, the GERI network-of-networks paper it builds on (SanClements et al. 2022, https://doi.org/10.1002/ecs2.4262), the survey dataset and the Mexican network-of-networks vision statement (https://doi.org/10.5281/zenodo.17726569). Metadata comes from Crossref and DataCite (`scripts/fetch_geri_papers.py`).

## Queries

The partner organizations in countries with no GERI site:

```sql
SELECT o.country_label, count(*) AS orgs, list(coalesce(o.acronym, o.name)) AS names
FROM network_organizations o
WHERE o.country IS NOT NULL
  AND o.country NOT IN (SELECT DISTINCT f.country FROM facilities f
                        JOIN network_membership nm USING (facility_id)
                        WHERE nm.network_id = 'geri' OR nm.network_id IN
                              (SELECT network_id FROM networks WHERE level = 'continental-ri'))
GROUP BY 1 ORDER BY orgs DESC;
```

Each RI's site count in the paper against the catalogue:

```sql
SELECT p.network_id, p.paper_site_count,
       (SELECT count(DISTINCT facility_id) FROM network_membership nm
        WHERE nm.network_id = p.network_id) AS in_catalogue,
       p.data_volume_tib, p.n_data_products
FROM ri_profiles p ORDER BY p.data_volume_tib DESC;
```
