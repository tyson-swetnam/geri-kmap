# Networks

GERI's six research infrastructures, as they appear in the catalogue. A site belongs to every network its registry record names, so the counts overlap.

| Network | Sites | Registry the sites come from |
|---|---:|---|
| eLTER (DEIMS network "LTER Europe") | 637 | DEIMS-SDR |
| ICOS | 188 | ICOS Carbon Portal (169 classified stations) and DEIMS-SDR |
| NEON | 81 | NEON Data API, joined to DEIMS-SDR by the DEIMS id NEON publishes |
| CERN (DEIMS network "CERN (LTER China)") | 42 | DEIMS-SDR |
| TERN (DEIMS network "TERN Australia") | 27 | DEIMS-SDR |
| SAEON | 22 | DEIMS-SDR |
| GERI (the DEIMS GERI network) | 561 | DEIMS-SDR |

ICOS stations are split by kind:

- ecosystem (`icos-ecosystem`): 107 stations
- atmosphere (`icos-atmosphere`): 41
- ocean (`icos-ocean`): 23

Only stations with an ICOS station class (1, 2 or Associated) are included. The Carbon Portal also lists about 300 stations that never entered ICOS labelling.

NEON sites are split into terrestrial (47) and aquatic (34) by NEON's own `HABITAT` location property.

32 sites appear in the DEIMS GERI network but in no RI network; they are national LTER, ICP Forests and similar sites. They are kept as GERI members.

## Gaps known today

- **TERN:** DEIMS lists TERN's SuperSites and LTERN/AusLTER plot networks, but not the OzFlux flux towers. Most harmonized Australian sites are OzFlux towers (AU-How, AU-DaS, AU-Stp and others).
- **SAEON and EFTEON:** DEIMS lists 22 SAEON sites. The EFTEON landscapes and the South African flux sites in the harmonized products (ZA-Kru, ZA-BfK and others) are not in DEIMS.
- **CERN:** DEIMS lists 42 CERN stations, which may not be the full current CERN station list.

These are filled from the RIs' own registries and the GERI Data Store metadata (`geri-metadata/`), never from recall.
