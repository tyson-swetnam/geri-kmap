# geri-kmap

geri-kmap is a map and database of the sites of the **Global Ecosystem Research Infrastructure (GERI)**. GERI brings together six continental-scale ecosystem research infrastructures (RIs):

- **NEON** (United States)
- **eLTER** (Europe)
- **ICOS** (Europe)
- **TERN** (Australia)
- **SAEON**, with EFTEON (South Africa)
- **CERN** (China)

GERI's NSF AccelNet project (award 2301655) harmonizes observations across these networks, starting with ecological drought. That work produces common data models, standardized metadata and reproducible workflows.

The catalogue answers the questions the harmonization work keeps asking:

- Where does each RI operate?
- Which sites are the same place under two registries?
- Which sites do the GERI harmonized products cover?

## What is in it

| | |
|---|---:|
| Sites (facilities) | 1,040 |
| Countries | 51 |
| Sites covered by the GERI harmonized products | 115 (117 ids) |

Every site comes from an RI's own registry or from the GERI products themselves: DEIMS-SDR, the NEON Data API, the ICOS Carbon Portal, TERN's OzFlux server, SAEON's DataCite station records, CERN's own station list and the GERI Data Store. Each site keeps every identifier it carries in those sources. See [Data access](data-access.md) for where each site's data can be fetched (APIs, SPARQL, CSW, THREDDS, WebDAV, buckets) and what access each needs, [Sources](sources.md) for the endpoints, [Networks](networks.md) for the counts per RI, and [Harmonized](harmonized.md) for the harmonized products. The Harmonized page includes the problems found in the products' site list.

## How to use the map

The **Scope** lens at the top of the sidebar narrows everything to one RI, or to the sites the harmonized products cover. Colour the points by sphere or by facility type. Facility types follow the RIs closely: NEON greens, ICOS blues, TERN ochre, CERN red, eLTER purple.

The **SQL** tab runs DuckDB in the browser over the published parquet. For example:

```sql
SELECT canonical_name, ris, identifiers
FROM v_facility_geri
WHERE len(ris) > 1
ORDER BY canonical_name;
```

## Where the data lives

- The parquet tables in this repository (`public/parquet/`) are the published copy.
- The same tables, with a manifest and checksums, are published to the CyVerse Data Store at `/iplant/home/shared/geri/geri-kmap`, next to the GERI harmonized data.
- The harmonized observations themselves stay in `/iplant/home/shared/geri/geri-harmonized/`. This catalogue links to them and summarizes their coverage; it does not copy them.

geri-kmap reuses the engine of [lto](https://github.com/tyson-swetnam/lto) (U.S. long-term observatories), which was forked from [cod-kmap](https://github.com/tyson-swetnam/cod-kmap).
