# Networks

GERI's six research infrastructures, as they appear in the catalogue. A site belongs to every network its registry record names, so the counts overlap.

| Network | Sites | Registry the sites come from |
|---|---:|---|
| eLTER (DEIMS network "LTER Europe") | 637 | DEIMS-SDR |
| ICOS | 180 | ICOS Carbon Portal (169 classified stations), DEIMS-SDR, GERI products |
| NEON | 81 | NEON Data API, joined to DEIMS-SDR by the DEIMS id NEON publishes |
| CERN (DEIMS network "CERN (LTER China)") | 42 | DEIMS-SDR |
| TERN | 62 | DEIMS-SDR (27 SuperSites and plot networks) + 47 OzFlux towers from TERN's THREDDS server, 12 of them at a SuperSite |
| SAEON | 26 | DEIMS-SDR (22) + SAEON/EFTEON DataCite station records + GERI products |
| EFTEON | 4 | SAEON DataCite station records + GERI products |
| GERI (the DEIMS GERI network) | 561 | DEIMS-SDR |

ICOS stations are split by kind:

- ecosystem (`icos-ecosystem`): 106 sites
- atmosphere (`icos-atmosphere`): 41
- ocean (`icos-ocean`): 23

Only stations with an ICOS station class (1, 2 or Associated) are included. The Carbon Portal also lists about 300 stations that never entered ICOS labelling.

NEON sites are split into terrestrial (47) and aquatic (34) by NEON's own `HABITAT` location property.

32 sites appear in the DEIMS GERI network but in no RI network; they are national LTER, ICP Forests and similar sites. They are kept as GERI members.

## One field site, one record

A field site often appears in several records: its DEIMS-SDR site, an ICOS ecosystem station, an ICOS atmosphere station, an eddy-covariance tower. Where the records name each other (a DEIMS site listing its ICOS station), the loader joins them. DEIMS's station codes are matched case-insensitively and without the ES_/AS_/OS_ prefix: DEIMS writes `ES_IT-Oxm`, `ES_CZ-Wet` and `SE-OES` for ICOS `ES_IT-OXm`, `ES_CZ-wet` and `ES_SE-Oes`.

Where they don't, a reviewed row in `data/seed/facility_merge_seed.csv` joins them, with evidence: the same name and the same place. Fourteen pairs are merged today:
- **Hyytiälä:** two ICOS stations into SMEAR II.
- **ICOS atmosphere stations into their sites:** Hyltemossa, Norunda, Svartberget, Pallas.
- **ICOS stations into DEIMS sites:** Oulanka, Leam West, Östergarnsholm, Torgnon larch forest.
- **SAEON eddy-covariance towers into their DEIMS sites:** Jonkershoek, Cathedral Peak, Benfontein (×2).

Two kinds of neighbour are left apart on purpose:
- distinct stations a few hundred metres apart, such as Zackenberg Fen and Gras, Westmalle 1 and 2, or a NEON terrestrial site and its aquatic site;
- DEIMS's own platform-and-site hierarchy, such as an LTSER platform and the sites in it.

## Gaps known today

- **SAEON and EFTEON:** DEIMS lists 22 SAEON sites, and the GERI Data Store holds DataCite records for six eddy-covariance stations. The full EFTEON landscape and station list is not yet in the catalogue.
- **CERN:** DEIMS lists 42 CERN stations, which may not be the full current CERN station list.
