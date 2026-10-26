#!/usr/bin/env python3
"""Fetch TERN's surveillance-monitoring plots (AusPlots) from the public AusPlots API.

DEIMS-SDR lists TERN's SuperSites and plot networks as a few dozen sites,
but TERN's site count -- about 800 in Loescher et al. (2026, Ecosphere,
doi:10.1002/ecs2.70789, Figure 1f) -- is mostly its Ecosystem Surveillance
plots: permanent 1 ha plots across Australia's bioregions, revisited over
time. The AusPlots API (the PostgREST service the ausplotsR package reads,
no key needed) serves one row per published site visit at ``/site``.

This collapses those visits to one record per plot (site_location_name):

  site_location_name, bioregion_name, latitude, longitude, plot_dimensions,
  description (the plot's location text), first_visit, last_visit, n_visits

taking the point of the latest visit. Observer ids, soil-pit coordinates
and free-text visit notes are dropped.

Output: ``data/raw/R-GERI-TERN/sites_ausplots.json``.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "R-GERI-TERN" / "sites_ausplots.json"
API = "http://swarmapi.ausplots.aekos.org.au"
FIELDS = ("site_location_name,site_location_visit_id,visit_start_date,bioregion_name,"
          "latitude,longitude,plot_dimensions,description")
PAGE = 500


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    visits: list[dict] = []
    while True:
        r = s.get(f"{API}/site", params={"select": FIELDS, "order": "site_location_visit_id",
                                         "limit": PAGE, "offset": len(visits)}, timeout=120)
        r.raise_for_status()
        page = r.json()
        visits += page
        if len(page) < PAGE:
            break
    stats = {x["name"]: x["stat"] for x in s.get(f"{API}/ausplots_stats", timeout=60).json()}

    plots: dict[str, dict] = {}
    for v in visits:
        name = (v.get("site_location_name") or "").strip()
        if not name:
            continue
        day = (v.get("visit_start_date") or "")[:10] or None
        p = plots.setdefault(name, {"site_location_name": name, "n_visits": 0,
                                    "first_visit": day, "last_visit": day, "_last_id": -1})
        p["n_visits"] += 1
        if day and (p["first_visit"] is None or day < p["first_visit"]):
            p["first_visit"] = day
        if day and (p["last_visit"] is None or day > p["last_visit"]):
            p["last_visit"] = day
        if v["site_location_visit_id"] > p["_last_id"] and v.get("latitude") is not None:
            p.update(_last_id=v["site_location_visit_id"], latitude=v["latitude"],
                     longitude=v["longitude"], bioregion_name=v.get("bioregion_name"),
                     plot_dimensions=v.get("plot_dimensions"),
                     description=(v.get("description") or "").strip() or None)
    out = []
    for name in sorted(plots):
        p = plots[name]
        p.pop("_last_id")
        if p.get("latitude") is None:
            print(f"[skip] {name}: no coordinates in any visit", file=sys.stderr)
            continue
        out.append(p)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": f"{API}/site", "retrieved_at": dt.date.today().isoformat(),
                               "published_visits": len(visits),
                               "api_stats": {k: stats[k] for k in sorted(stats)},
                               "sites": out}, ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(visits)} published visits -> {len(out)} plots -> {OUT.relative_to(ROOT)} "
          f"(API total site count {stats.get('Total site count')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
