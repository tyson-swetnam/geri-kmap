# Harmonized products

The GERI harmonization pipeline publishes drought-relevant datasets in `/iplant/home/shared/geri/geri-harmonized/` on the CyVerse Data Store. They are readable anonymously at `https://data.cyverse.org/dav-anon/iplant/projects/geri/geri-harmonized/`. The catalogue does not copy the observations. It records:

- one `data_products` row per file;
- which catalogue site each harmonized site id belongs to (`site_identifiers`, scheme `geri-harmonized-id`);
- what each file holds for each site (`harmonized_coverage`).

Choose **Harmonized sites** in the Scope lens to see them on the map.

| Product | Sites | Values |
|---|---:|---:|
| Air temperature, 30-minute | 115 | 15,009,008 |
| Precipitation, hourly | 115 | 7,092,660 |
| Soil moisture, 30-minute | 115 | 12,579,845 |
| Soil temperature, 30-minute | 115 | 13,753,413 |
| Soil texture, static | 82 | 2,082 |

The products name **117 site ids**, and all of them resolve. Two pairs share a site, so 115 catalogue sites carry them:
- DE-HoH-E and DE-HoH-I are the eLTER and ICOS series of TERENO Hohes Holz.
- ZA-BfK and ZA-BfS are the Karoo and Savanna towers on Benfontein Private Nature Reserve.

| RI | Sites |
|---|---:|
| NEON | 46 |
| ICOS | 33 |
| TERN | 27 |
| eLTER | 14 |
| SAEON | 7 |
| EFTEON | 4 |

Coverage rows for a site with two series are added together: earliest first value, latest last value, summed counts.

## How ids are resolved

1. **Reviewed rows first.** `data/seed/geri_harmonized_site_map.csv` gives a scheme, value, source and evidence for each id the rules below cannot place, or would place wrongly.
2. **NEON:** `US-ABBY` → NEON site ABBY.
3. **ICOS:** `BE-Bra` → ICOS station `ES_BE-Bra`.
4. **TERN:** `AU-How` → the OzFlux tower whose `fluxnet_id` is AU-How.

Five ids are known only from the harmonized products and become sites of their own (`harmonized-only`), named as the products name them: ZA-CCs, ZA-Kru, FR-Lus, FR-Lqu and DE-RuS.

`scripts/summarize_harmonized.py` reads the downloaded files (their MD5s match the Data Store's iRODS checksums) and writes the committed `data/raw/R-GERI-HARMONIZED/harmonized_summary.csv`. The loaders read that summary, so the 1 GB download is needed only to refresh it.

## Problems found in the harmonized site list

These were found while resolving ids. They are recorded here for the harmonization team; the catalogue does not edit the products. `qa.py` warns about any harmonized id more than 25 km from the site it resolves to.

### Ids that name a different ICOS station

The site name and point in the products show which site the data is from.

| Id in the products | Site name in the products | CSV point | What ICOS means by the id |
|---|---|---|---|
| FR-FBn | Fontainebleau | 48.4729, 2.7801 | Font-Blanche (43.24, 5.68). The data is Fontainebleau-Barbeau, ICOS **FR-Fon** |
| FR-Lus | Lussas | 44.59, 4.33 | Lusignan (46.41, 0.12) |
| FR-Lqu | Landes de Gascogne (Lourquen) | 44.02, -0.957 | Laqueuille (45.64, 2.73) |
| DE-RuS | Rursee-Schwammenauel | 50.6231, 6.4258 | Selhausen (50.87, 6.45) |

FR-FBn is filed under ICOS FR-Fon. The other three are not ICOS stations under any name, classified or not, and are kept as harmonized-only sites.

### Wrong coordinates in `geri_harmonized_sites.csv`

| Id | CSV point | Registry point | Note |
|---|---|---|---|
| US-NOGP | 46.7697, **100.9154** | 46.7697, -100.9154 (NEON) | Longitude sign |
| NL-Loo | **57.199**, 5.7435 | 52.1665, 5.7436 (ICOS) | Latitude |
| AU-TTE | -22.283, 133.249 | -22.287, 133.640 (OzFlux Ti Tree East) | Carries AU-ASM's point |
| AU-Ya1 | -33.62081, 150.7633 | -33.6135, 150.7349 (OzFlux Yarramundi Control) | Carries AU-Ya2's point |

### Encoding

The CSV is Latin-1, not UTF-8: `FI-Värriö` reads as `FI-V?rri?` in a UTF-8 reader. The parquet files spell it correctly.

## Upstream registry problems found on the way

- **OzFlux:** the Wedgetail L3 file's `fluxnet_id` is `Au-Sil`, which is Silver Plains' id. Six OzFlux files carry no `fluxnet_id`.
- **SAEON DataCite:** the record for Benfontein Savanna EC (10.15493/obs.monitor.90686782) places it at 29.626 E, in KwaZulu-Natal. It is corrected in `data/seed/facility_fixes.csv` from the harmonized CSV.
- **DEIMS-SDR:** the points for Monte Bondone, Hetzdorf and Las Majadas de Tiétar are 190–263 km from the ICOS stations those records hold. The loader uses the ICOS coordinates whenever the gap exceeds 50 km.
