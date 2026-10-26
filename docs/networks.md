# Networks

GERI's six research infrastructures, as they appear in the catalogue. A site belongs to every network its registry record names, so the counts overlap.

| Network | Sites | Registry the sites come from |
|---|---:|---|
| eLTER (DEIMS network "LTER Europe") | 637 | DEIMS-SDR |
| ICOS | 180 | ICOS Carbon Portal (169 classified stations), DEIMS-SDR, GERI products |
| NEON | 81 | NEON Data API, joined to DEIMS-SDR by the DEIMS id NEON publishes |
| CERN | 43 | DEIMS-SDR (42) + CERN's own station list (Daya Bay) |
| TERN | 882 | DEIMS-SDR (27 SuperSites and plot networks) + 47 OzFlux towers from TERN's THREDDS server, 12 of them at a SuperSite + 820 Ecosystem Surveillance plots from the AusPlots API |
| SAEON | 46 | DEIMS-SDR (22) + every SAEON Terrestrial Observations Monitor station (DataCite) + GERI products |
| EFTEON | 17 | SAEON DataCite station records + GERI products |
| GERI (the DEIMS GERI network) | 561 | DEIMS-SDR |
| MexFlux (GENNI; not GERI) | 33 | MexFlux's site table and map, AmeriFlux for the 14 towers it registers |

ICOS stations are split by kind:

- ecosystem (`icos-ecosystem`): 106 sites
- atmosphere (`icos-atmosphere`): 41
- ocean (`icos-ocean`): 23

Only stations with an ICOS station class (1, 2 or Associated) are included. The Carbon Portal also lists about 300 stations that never entered ICOS labelling.

NEON sites are split into terrestrial (47) and aquatic (34) by NEON's own `HABITAT` location property.

## TERN surveillance plots

TERN's Ecosystem Surveillance program revisits permanent plots across Australia's bioregions, most of them 1 ha (100 × 100 m). The AusPlots API (`http://swarmapi.ausplots.aekos.org.au/site`, no key) serves one row per published visit. `scripts/fetch_ausplots.py` reduces those visits to one record per plot (`ausplots-site` id = the plot's `site_location_name`), with the point of its latest visit. That gives 820 plots (network `tern-surveillance`, type `surveillance-plot`), close to the 800 TERN sites in Loescher et al. (2026, Figure 1). Observer ids and visit notes are not kept. A plot's `established` is its first visit and its record length runs to its last visit. 561 plots have been surveyed once, so they have no record length yet. A plot that sits inside a SuperSite is kept as its own record, because plots and the SuperSite are separate registrations.

## MexFlux and GENNI

MexFlux is the Mexican flux-tower network in the GENNI use case of Loescher et al. (2026). It is not a GERI member, so its 33 towers are in the networks `mexflux` and `genni` and never in `geri` (see [GERI & GENNI](genni.md)). A tower's record length runs from its first year to its last year of data, taken from MexFlux's site table; for a tower still running, it runs to today.

## SAEON and EFTEON stations

SAEON registers every station of its Terrestrial Observations Monitor as a DataCite DOI (`10.15493/obs.monitor.*`). All 33 are loaded: 7 eddy-covariance towers and 26 automatic weather stations. Five weather stations and four towers stand at a DEIMS site and are part of it, and the Spioenkop weather station shares its point with the Spioenkop tower.

A station is EFTEON when EFTEON is its creator or one of its subjects is "EFTEON …". That subject also places it in one of EFTEON's six landscapes (https://efteon.saeon.ac.za/landscapes/):

| Landscape | Sites |
|---|---:|
| Northern Maluti-Drakensberg | 5 |
| KIMTRI (Kimberley) | 3 |
| Lowveld | 3 |
| Maputaland | 2 |
| Greater Cape Town | 1 |
| Garden Route Gateway | 0 (no station registered yet) |

The record for Benfontein Savanna EC gives the subject "EFTEON Savanna", which is not one of the six landscapes, so that station is left unplaced. Its point is also wrong (see [Harmonized](harmonized.md)).

## CERN stations

CERN's station page (https://www.cern.ac.cn/1wljs/index.asp?channelid1=100110) links its English brochure, which lists 36 stations. 35 of them are DEIMS-SDR sites in the CERN network. The 36th, the Marine Biological Research Station at Daya Bay, is not, so it is added from the brochure (`data/seed/cern_stations.csv`). DEIMS also has seven stations newer than the brochure. Together that is 43.

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

- **CERN:** the brochure is a first edition. CERN's English site, which might list the current set, was unreachable on 2026-10-25.
- **EFTEON:** a landscape with no registered station (Garden Route Gateway) has no site yet. EFTEON's landscape pages give no coordinates, so the landscapes are networks, not points.
