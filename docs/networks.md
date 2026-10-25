# Networks

GERI's six research infrastructures, as they appear in the catalogue. A site belongs to every network its registry record names, so the counts overlap.

| Network | Sites | Registry the sites come from |
|---|---:|---|
| eLTER (DEIMS network "LTER Europe") | 637 | DEIMS-SDR |
| ICOS | 191 | ICOS Carbon Portal (169 classified stations), DEIMS-SDR, GERI products |
| NEON | 81 | NEON Data API, joined to DEIMS-SDR by the DEIMS id NEON publishes |
| CERN (DEIMS network "CERN (LTER China)") | 42 | DEIMS-SDR |
| TERN | 62 | DEIMS-SDR (27 SuperSites and plot networks) + 47 OzFlux towers from TERN's THREDDS server, 12 of them at a SuperSite |
| SAEON | 30 | DEIMS-SDR (22) + SAEON/EFTEON DataCite station records + GERI products |
| EFTEON | 5 | SAEON DataCite station records + GERI products |
| GERI (the DEIMS GERI network) | 561 | DEIMS-SDR |

ICOS stations are split by kind:

- ecosystem (`icos-ecosystem`): 107 stations
- atmosphere (`icos-atmosphere`): 41
- ocean (`icos-ocean`): 23

Only stations with an ICOS station class (1, 2 or Associated) are included. The Carbon Portal also lists about 300 stations that never entered ICOS labelling.

NEON sites are split into terrestrial (47) and aquatic (34) by NEON's own `HABITAT` location property.

32 sites appear in the DEIMS GERI network but in no RI network; they are national LTER, ICP Forests and similar sites. They are kept as GERI members.

## Gaps known today

- **SAEON and EFTEON:** DEIMS lists 22 SAEON sites, and the GERI Data Store holds DataCite records for six eddy-covariance stations. The full EFTEON landscape and station list is not yet in the catalogue.
- **CERN:** DEIMS lists 42 CERN stations, which may not be the full current CERN station list.
- **Co-located duplicates:** where two registries describe one place without naming each other, it appears twice. Examples are ICOS Hyytiälä and eLTER's SMEAR II record. They are merged only through a reviewed `data/seed/facility_merge_seed.csv` row, never by distance alone.
