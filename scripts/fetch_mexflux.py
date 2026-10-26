#!/usr/bin/env python3
"""Fetch MexFlux's eddy-covariance sites: the Mexican network in the GENNI use case.

Loescher et al. (2026, Ecosphere, doi:10.1002/ecs2.70789) propose GENNI,
a Global Ecosystem Network-of-Networks Initiative linking environmental
networks to GERI, and use five Mexican networks as its first case (their
Box 1). MexFlux is the one with registered sites (their Figure 3).

Sources, all public:

  https://mexflux.gitlab.io/sites/                 the site table: name, id,
                                                   years, vegetation, where the
                                                   data are (bold = active)
  https://mexflux.gitlab.io/mexflux_site_map_2024.html
                                                   the site map (Plotly): a
                                                   point for every site
  https://amfcdn.lbl.gov/api/v1/site_display/AmeriFlux
                                                   AmeriFlux's registry: point,
                                                   IGBP class, tower years

A row's AmeriFlux link gives its registered id, which wins over the id as
typed in the table (the table says MX-lit and MC-Lpa for AmeriFlux MX-Iit
and MX-Lpa). A site AmeriFlux registers gets its AmeriFlux page even when
the table says its data are with the PI (La Colorada - buffel, MX-CHB). The point is AmeriFlux's when the site is registered there,
else the MexFlux map's. PI names and e-mail addresses on both MexFlux
pages are not kept: contact details are not published.

Output: ``data/raw/R-GENNI-MEXFLUX/sites_mexflux.json``.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GENNI-MEXFLUX" / "sites_mexflux.json"
SITES = "https://mexflux.gitlab.io/sites/"
MAP = "https://mexflux.gitlab.io/mexflux_site_map_2024.html"
AMF = "https://amfcdn.lbl.gov/api/v1/site_display/AmeriFlux"
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td>(.*?)</td>", re.S)
AMF_LINK_RE = re.compile(r"ameriflux\.lbl\.gov/sites/siteinfo/([A-Za-z0-9-]+)")
TAG_RE = re.compile(r"<[^>]+>")
# A Plotly scattermapbox trace: "lat":[...],"lon":[...], ... "text":[...]
TRACE_RE = re.compile(r'"lat":\[([^\]]*)\],"lon":\[([^\]]*)\].*?"text":\[(.*?)\],"type":"scattermapbox"', re.S)
MAP_ID_RE = re.compile(r"Site ID:\s*([A-Za-z]{2}-[A-Za-z0-9]{3})")
YEARS_RE = re.compile(r"\((\d{4})")
PERIOD_RE = re.compile(r"\(([^)]*)\)")


def text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", cell))).strip()


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    page = s.get(SITES, timeout=60).text
    rows = []
    for tr in ROW_RE.findall(page.split("<tbody>", 1)[1]):
        c = CELL_RE.findall(tr)
        if len(c) < 7:
            continue
        link = AMF_LINK_RE.search(c[6])
        typed = text(c[1])
        rows.append({"site_id": link.group(1) if link else typed, "id_as_typed": typed,
                     "name": text(c[0]), "active": "<strong>" in c[0],
                     "years": text(c[2]), "vegetation": text(c[5]),
                     "data_at": text(c[6]), "ameriflux_url": f"https://{link.group(0)}" if link else None})

    points: dict[str, tuple[float, float]] = {}
    for lat, lon, txt in TRACE_RE.findall(s.get(MAP, timeout=120).text):
        ids = MAP_ID_RE.findall(txt)
        lats, lons = [float(x) for x in lat.split(",")], [float(x) for x in lon.split(",")]
        if len(ids) == len(lats) == len(lons):
            for i, la, lo in zip(ids, lats, lons):
                points[i.upper()] = (la, lo)

    amf = {r["SITE_ID"].upper(): r for r in s.get(AMF, timeout=120).json()}
    out = []
    for r in rows:
        a = amf.get(r["site_id"].upper())
        loc = a and a.get("GRP_LOCATION") or {}
        mp = points.get(r["id_as_typed"].upper()) or points.get(r["site_id"].upper())
        if a and loc.get("LOCATION_LAT"):
            r.update(lat=float(loc["LOCATION_LAT"]), lng=float(loc["LOCATION_LONG"]), point_source="ameriflux",
                     igbp=a.get("IGBP"), tower_began=a.get("TOWER_BEGAN"), tower_end=a.get("TOWER_END"),
                     site_id=a["SITE_ID"], ameriflux_url=a.get("URL_AMERIFLUX") or r["ameriflux_url"])
        elif mp:
            r.update(lat=mp[0], lng=mp[1], point_source="mexflux-map")
        else:
            print(f"[skip] {r['site_id']} {r['name']}: no point on the map or in AmeriFlux", file=sys.stderr)
            continue
        m = YEARS_RE.search(r["years"])
        r["first_year"] = int(m.group(1)) if m else None
        # '(2016-2018)' ended in 2018; '(2016- )' is still running (None).
        period = PERIOD_RE.search(r["years"])
        span = period.group(1).strip() if period else ""
        r["last_year"] = (None if not span or span.endswith("-")
                          else max(int(y) for y in re.findall(r"\d{4}", span)))
        out.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": SITES, "map": MAP, "ameriflux": AMF,
                               "retrieved_at": dt.date.today().isoformat(), "sites": out},
                              ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(rows)} MexFlux sites in the table, {len(points)} on the map, "
          f"{sum(1 for r in out if r['point_source'] == 'ameriflux')} with an AmeriFlux point "
          f"-> {len(out)} -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
