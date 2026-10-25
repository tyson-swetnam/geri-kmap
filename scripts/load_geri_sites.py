#!/usr/bin/env python3
"""Load the GERI research-infrastructure sites into the lake.

Inputs (committed, written by the fetchers):

  data/raw/R-GERI-DEIMS/sites_deims.json   fetch_deims.py  -- the backbone
  data/raw/R-GERI-NEON/sites_neon.json     fetch_neon.py
  data/raw/R-GERI-ICOS/stations_icos.json  fetch_icos.py

Identity
--------
One facility per DEIMS-SDR site, ``facility_id = sha1("deims:" + uuid)[:16]``.
A DEIMS site lists every network it belongs to, so co-location across RIs
(an eLTER site that is also an ICOS station) comes from the registry.

* A NEON site joins its DEIMS record through the ``deimsId`` NEON itself
  publishes; NEON's own coordinates, name and domain win.
* An ICOS station joins the DEIMS record whose ICOS affiliation names the
  station's URI. Unmatched stations become their own facility,
  ``sha1("icos:" + station_uri)[:16]``. Stations are never matched by
  distance here: an ICOS atmosphere tower and the ecosystem station beside
  it are different stations, and a reviewed pair goes through
  merge_facilities.py instead.

The run owns every facility whose provenance agent starts ``R-GERI-``: it
upserts them (``created_at`` survives) and replaces their child rows, and
removes any such facility no input names any more. One transaction, one
snapshot; ``assert_integrity`` runs before COMMIT.

Usage::

    python scripts/load_geri_sites.py
    python scripts/load_geri_sites.py --catalog /tmp/x/cat.sqlite
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geri_db  # noqa: E402
from load_vocab import load_vocab  # noqa: E402

ROOT = geri_db.ROOT
RAW = ROOT / "data" / "raw"
DEIMS_JSON = RAW / "R-GERI-DEIMS" / "sites_deims.json"
NEON_JSON = RAW / "R-GERI-NEON" / "sites_neon.json"
ICOS_JSON = RAW / "R-GERI-ICOS" / "stations_icos.json"
COUNTRY_NAMES = ROOT / "schema" / "vocab" / "country_names.csv"
COUNTRY_BBOX = ROOT / "schema" / "vocab" / "country_bbox.csv"

AGENT_PREFIX = "R-GERI-"
# DEIMS network uuid -> our continental-ri slug (the GERI network itself is
# membership in `geri`). Same ids as fetch_deims.NETWORKS.
DEIMS_NETWORK = {
    "c3abdc60-49f1-49db-81fe-863b7dbb21d3": "geri",
    "4742ffca-65ac-4aae-815f-83738500a1fc": "elter",
    "80633d38-4c85-4ee0-a4ce-7bbbd99c888c": "icos",
    "fd9fbc88-0baa-4d02-b824-dc29f721782c": "neon",
    "1ebec4aa-df7e-4657-84b6-1869c0b9437c": "tern",
    "bce17afa-e548-4410-99d2-4eade740c9a9": "saeon",
    "4dac034d-92d5-4c06-8e4e-aabafdbcedff": "cern",
}
RI_LABEL = {"neon": "NEON", "elter": "eLTER", "icos": "ICOS", "tern": "TERN",
            "saeon": "SAEON", "cern": "CERN"}
# Precedence when a facility belongs to several RIs: which one names its type.
RI_ORDER = ["neon", "icos", "tern", "cern", "saeon", "elter"]
ICOS_KIND = {"ES": ("icos-ecosystem", "icos-ecosystem-station", "terrestrial", "flux-tower"),
             "AS": ("icos-atmosphere", "icos-atmosphere-station", "atmosphere", "observatory"),
             "OS": ("icos-ocean", "icos-ocean-station", "ocean-estuarine", "observatory")}
# DEIMS geoBonBiome -> sphere.
GEOBON_SPHERE = {"Terrestrial": "terrestrial", "Fresh water lakes": "freshwater",
                 "Fresh water rivers": "freshwater", "Marine": "ocean-estuarine",
                 "Coastal": "ocean-estuarine"}
# DEIMS biome -> an extra (secondary) sphere it implies.
BIOME_SPHERE = {"desert": "arid", "desert_scrub": "arid", "chaparral": "arid",
                "agricultural": "agriculture", "tundra": "cryosphere",
                "freshwater_lakes": "freshwater", "freshwater_rivers": "freshwater",
                "marine": "ocean-estuarine", "coastal": "ocean-estuarine"}
# ICOS ocean-network site codes as DEIMS records them: ships of opportunity
# (ES-SOOP-ESTOC) and fixed ocean stations (DE-FOS-CVOO).
ICOS_OCEAN_CODE = re.compile(r"-(SOOP|FOS)-")
POINT_RE = re.compile(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")


def fid(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def icos_key(uri: str) -> str:
    """'https://meta.icos-cp.eu/resources/stations/ES_FR-Lus' -> 'ES_FR-Lus'."""
    return uri.rstrip("/").rsplit("/", 1)[-1]


def country_lookup() -> dict[str, str]:
    with COUNTRY_NAMES.open(newline="") as fh:
        return {r["name"]: r["iso2"] for r in csv.DictReader(fh)}


def country_boxes() -> dict[str, list[tuple[float, float, float, float]]]:
    boxes: dict[str, list] = {}
    with COUNTRY_BBOX.open(newline="") as fh:
        for r in csv.DictReader(fh):
            boxes.setdefault(r["iso2"], []).append(
                (float(r["min_lat"]), float(r["max_lat"]), float(r["min_lng"]), float(r["max_lng"])))
    return boxes


def pick_country(codes: list[str], lat, lng, boxes) -> str | None:
    """The listed country whose box holds the point, else the first listed.

    A DEIMS site spanning several countries (an Amazon-basin observatory
    lists five) lists them all; the point decides which one it is filed under.
    """
    if lat is not None and lng is not None:
        for c in codes:
            if any(a <= lat <= b and lo <= lng <= hi for a, b, lo, hi in boxes.get(c, [])):
                return c
    return codes[0] if codes else None


def num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def clean_title(title: str | None, country: list[str] | None) -> str | None:
    """DEIMS titles end in ' - <Country>'; the name is what precedes it."""
    if not title:
        return title
    for c in country or []:
        suffix = f" - {c}"
        if title.endswith(suffix):
            return title[: -len(suffix)]
    return title


class Site:
    """Everything one facility gathers from its sources before it is written."""

    def __init__(self, facility_id: str):
        self.facility_id = facility_id
        self.name = self.acronym = self.country = self.region = None
        self.lat = self.lng = None
        self.url = self.portal = None
        self.established: int | None = None
        self.retrieved_year: int | None = None
        self.ris: set[str] = set()
        self.networks: set[str] = set()
        self.ftype: str | None = None
        self.primary_sphere: str | None = None
        self.spheres: set[str] = set()
        self.ids: dict[tuple[str, str], str] = {}        # (scheme, value) -> source_url
        self.locations: list[dict] = []
        self.prov: list[tuple[str, str, str]] = []       # (source_url, retrieved_at, agent)


def from_deims(rec: dict, retrieved: str, countries: dict[str, str], boxes) -> Site:
    s = Site(fid("deims:" + rec["deims_id"]))
    s.name = clean_title(rec.get("title"), rec.get("country")) or rec.get("site_name")
    s.acronym = rec.get("short_name")
    m = POINT_RE.search(rec.get("coordinates") or "")
    if m:
        s.lng, s.lat = float(m.group(1)), float(m.group(2))
    codes = [countries[n] for n in rec.get("country") or [] if n in countries]
    s.country = pick_country(codes, s.lat, s.lng, boxes)
    s.url = rec["url"]
    s.established = rec.get("year_established")
    s.retrieved_year = int(retrieved[:4])
    s.ids[("deims-id", rec["deims_id"])] = rec["url"]
    ocean_code = False
    for n in rec.get("networks") or []:
        slug = DEIMS_NETWORK.get(n["deims_network_id"])
        if not slug:
            continue
        s.networks.add(slug)
        if slug != "geri":
            s.ris.add(slug)
        code = n.get("site_code")
        if code and slug == "neon":
            s.ids[("neon-site", code)] = rec["url"]
        elif code and slug == "icos":
            s.ids[("icos-station", icos_key(code))] = rec["url"]
            if ICOS_OCEAN_CODE.search(code):
                s.networks.add("icos-ocean")
                s.spheres.add("ocean-estuarine")
                ocean_code = True
        elif code and slug != "geri":
            s.ids[(f"{slug}-site-code", code)] = rec["url"]
    for slug in rec.get("listed_in") or []:
        s.networks.add(slug)
        if slug != "geri":
            s.ris.add(slug)
    geobon = rec.get("geobon_biome") or []
    for g in geobon:
        if g in GEOBON_SPHERE:
            s.spheres.add(GEOBON_SPHERE[g])
    if rec.get("biome") in BIOME_SPHERE:
        s.spheres.add(BIOME_SPHERE[rec["biome"]])
    # Primary sphere: terrestrial if the site has land at all, else its
    # water; an ICOS ocean-network code makes the site an ocean site.
    for cand in (("ocean-estuarine",) if ocean_code else ()) + ("terrestrial", "freshwater", "ocean-estuarine"):
        if cand in s.spheres:
            s.primary_sphere = cand
            break
    title = rec.get("title") or ""
    st = rec.get("site_type")
    if "SuperSite" in title:
        s.ftype = "supersite"
    elif "Plot Network" in title:
        s.ftype = "plot-network"
    elif "cern" in s.ris:
        s.ftype = "field-station"          # CERN's units are staffed stations
    elif st == "Platform":
        s.ftype = "ltser-platform"
    elif s.primary_sphere == "ocean-estuarine" or st in ("Research vessel", "Buoy(s)"):
        s.ftype = "marine-site"
    elif st and "site" in st.lower():
        s.ftype = "lter-site"
    else:
        s.ftype = "ri-site"
    if s.lat is not None:
        s.locations.append({"label": s.name, "lat": s.lat, "lng": s.lng, "role": "field-station"})
    s.prov.append((rec["url"], retrieved, "R-GERI-DEIMS"))
    return s


def apply_neon(s: Site, n: dict, retrieved: str, source: str) -> None:
    url = f"{source}/{n['siteCode']}"
    s.name = n.get("siteName") or s.name
    s.acronym = n["siteCode"]
    s.lat, s.lng = num(n.get("siteLatitude")), num(n.get("siteLongitude"))
    s.country = "PR" if n.get("stateCode") == "PR" else "US"
    s.region = f"{n.get('domainCode')} {n.get('domainName')}".strip()
    s.ris.add("neon")
    s.networks.add("neon")
    s.ids[("neon-site", n["siteCode"])] = url
    # NEON's own HABITAT property ('Aquatic Wadeable Stream', 'Terrestrial ...').
    aquatic = (n.get("habitat") or "").lower().startswith("aquatic")
    if n.get("fieldSiteUrlPath"):
        s.url = f"https://www.neonscience.org/field-sites/{n['fieldSiteUrlPath']}"
    s.primary_sphere = "freshwater" if aquatic else "terrestrial"
    s.spheres.add(s.primary_sphere)
    s.networks.add("neon-aquatic" if aquatic else "neon-terrestrial")
    s.ftype = "neon-aquatic-site" if aquatic else "neon-terrestrial-site"
    s.locations = [{"label": f"{n['siteCode']} {n.get('siteName')}", "lat": s.lat,
                    "lng": s.lng, "role": "field-station"}]
    s.prov.append((url, retrieved, "R-GERI-NEON"))


def apply_icos(s: Site, st: dict, retrieved: str, own: bool) -> None:
    sub, ftype, sphere, role = ICOS_KIND[st["station_type"]]
    key = icos_key(st["s"])
    s.ris.add("icos")
    s.networks.update({"icos", sub})
    s.ids[("icos-station", key)] = st["s"]
    s.spheres.add(sphere)
    lat, lng = num(st.get("lat")), num(st.get("lon"))
    if own:
        s.name = st["name"]
        s.acronym = st["id"]
        s.country = st.get("country")
        s.lat, s.lng = lat, lng
        s.url = st["s"]
        s.ftype = ftype
        s.primary_sphere = sphere
    if lat is not None and lng is not None:
        s.locations.append({"label": f"ICOS {st['station_type']} {st['id']} {st['name']}",
                            "lat": lat, "lng": lng, "role": role})
    s.prov.append((st["s"], retrieved, "R-GERI-ICOS"))


def build_sites() -> tuple[list[Site], dict]:
    countries = country_lookup()
    boxes = country_boxes()
    deims = json.loads(DEIMS_JSON.read_text())
    neon = json.loads(NEON_JSON.read_text())
    icos = json.loads(ICOS_JSON.read_text())
    stats: dict[str, int] = {}

    sites: dict[str, Site] = {}
    by_deims: dict[str, Site] = {}
    claims: dict[str, list[Site]] = {}
    for rec in deims["sites"]:
        s = from_deims(rec, deims["retrieved_at"], countries, boxes)
        sites[s.facility_id] = s
        by_deims[rec["deims_id"]] = s
        for scheme, value in s.ids:
            if scheme == "icos-station":
                claims.setdefault(value, []).append(s)
    stats["deims"] = len(deims["sites"])

    # Several DEIMS sites can name one ICOS station: an LTSER platform or a
    # regional observatory and the specific site inside it. The station
    # belongs to the specific site -- not a platform, then the closest name
    # to the ICOS station's own. The umbrella keeps its ICOS membership
    # (DEIMS says it is affiliated) but not the station id.
    icos_names = {icos_key(st["s"]): st["name"] for st in json.loads(ICOS_JSON.read_text())["stations"]}
    by_icos: dict[str, Site] = {}
    for key, cands in sorted(claims.items()):
        ranked = sorted(cands, key=lambda c: (c.ftype == "ltser-platform",
                                              -fuzz.token_set_ratio(c.name or "", icos_names.get(key, key)),
                                              c.facility_id))
        by_icos[key] = ranked[0]
        for loser in ranked[1:]:
            del loser.ids[("icos-station", key)]
            print(f"[icos] {key}: station kept on '{ranked[0].name}', "
                  f"not on umbrella '{loser.name}'")

    neon_own = 0
    for n in neon["sites"]:
        uuid = (n.get("deimsId") or "").rstrip("/").rsplit("/", 1)[-1]
        s = by_deims.get(uuid)
        if s is None:
            s = sites.setdefault(fid("neon:" + n["siteCode"]), Site(fid("neon:" + n["siteCode"])))
            neon_own += 1
        apply_neon(s, n, neon["retrieved_at"], neon["source"])
    stats["neon"], stats["neon_without_deims"] = len(neon["sites"]), neon_own

    icos_matched = 0
    for st in icos["stations"]:
        key = icos_key(st["s"])
        s = by_icos.get(key)
        if s is not None:
            icos_matched += 1
            apply_icos(s, st, icos["retrieved_at"], own=False)
        else:
            s = sites.setdefault(fid("icos:" + key), Site(fid("icos:" + key)))
            apply_icos(s, st, icos["retrieved_at"], own=True)
    stats["icos"], stats["icos_matched_deims"] = len(icos["stations"]), icos_matched

    for s in sites.values():
        # The type follows the RI with precedence when DEIMS gave none better.
        if s.ftype in (None, "ri-site", "lter-site") and "icos" in s.ris and "elter" not in s.ris:
            kinds = [k for k in ("ES", "AS", "OS") if ICOS_KIND[k][0] in s.networks]
            if kinds:
                s.ftype = ICOS_KIND[kinds[0]][1]
        if s.primary_sphere is None:
            s.primary_sphere = "terrestrial"
        s.spheres.add(s.primary_sphere)
    return list(sites.values()), stats


def stage(con, name: str, cols: list[str], rows: list[tuple]) -> None:
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} ({', '.join(cols)})")
    if rows:
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    geri_db.add_argparse_catalog(ap)
    args = ap.parse_args()

    sites, stats = build_sites()
    for k, v in stats.items():
        print(f"[input] {k:<22} {v}")

    fac_rows, loc_rows, net_rows, sph_rows, id_rows, prov_rows = [], [], [], [], [], []
    for s in sorted(sites, key=lambda x: x.facility_id):
        primary_ri = next((r for r in RI_ORDER if r in s.ris), None)
        rec_len = (s.retrieved_year - s.established
                   if s.established and s.retrieved_year else None)
        fac_rows.append((
            s.facility_id, s.name, s.acronym, RI_LABEL.get(primary_ri), s.ftype,
            s.country or "ZZ", s.region, s.lat, s.lng, s.url, s.established,
            rec_len, (rec_len >= 10) if rec_len is not None else None, s.portal))
        seen_loc = set()
        for loc in s.locations:
            lid = fid(f"{s.facility_id}|{loc['label']}")
            if lid in seen_loc:
                continue
            seen_loc.add(lid)
            loc_rows.append((lid, s.facility_id, loc["label"], loc["lat"], loc["lng"], loc["role"]))
        for n in sorted(s.networks):
            net_rows.append((s.facility_id, n, "member"))
        for sp in sorted(s.spheres):
            sph_rows.append((s.facility_id, sp, "primary" if sp == s.primary_sphere else "secondary"))
        for (scheme, value), src in sorted(s.ids.items()):
            id_rows.append((s.facility_id, scheme, value, src))
        for src, retrieved, agent in s.prov:
            prov_rows.append(("facility", s.facility_id, src, retrieved, "high", agent))

    con = geri_db.connect(catalog=args.catalog, data=args.lake_data)
    with geri_db.transaction(con, f"load_geri_sites: {len(fac_rows)} GERI RI sites "
                                  f"(DEIMS {stats['deims']}, NEON {stats['neon']}, "
                                  f"ICOS {stats['icos']})"):
        for change in geri_db.ensure_schema(con):
            print(f"[schema] {change}")
        load_vocab(con)
        stage(con, "s_fac", ["facility_id VARCHAR", "canonical_name VARCHAR", "acronym VARCHAR",
                             "parent_org VARCHAR", "facility_type VARCHAR", "country VARCHAR",
                             "region VARCHAR", "hq_lat DOUBLE", "hq_lng DOUBLE", "url VARCHAR",
                             "established INTEGER", "record_length_years INTEGER",
                             "long_term_threshold_met BOOLEAN", "data_portal_url VARCHAR"], fac_rows)
        owned = geri_db.rows(con, "SELECT DISTINCT record_id FROM provenance "
                                  "WHERE record_type = 'facility' AND starts_with(agent, ?)",
                             [AGENT_PREFIX])
        keep = {r[0] for r in fac_rows}
        stale = sorted({r[0] for r in owned} - keep)
        touched = sorted(keep | set(stale))
        stage(con, "s_touched", ["facility_id VARCHAR"], [(f,) for f in touched])
        for t in ("locations", "network_membership", "facility_spheres", "site_identifiers"):
            con.execute(f"DELETE FROM {t} WHERE facility_id IN (SELECT facility_id FROM s_touched)")
        con.execute("DELETE FROM provenance WHERE record_type = 'facility' "
                    "AND record_id IN (SELECT facility_id FROM s_touched)")
        if stale:
            stage(con, "s_stale", ["facility_id VARCHAR"], [(f,) for f in stale])
            con.execute("DELETE FROM facilities WHERE facility_id IN (SELECT facility_id FROM s_stale)")
        res = geri_db.merge_upsert(con, "facilities", ["facility_id"], "s_fac")
        stage(con, "s_loc", ["location_id VARCHAR", "facility_id VARCHAR", "label VARCHAR",
                             "lat DOUBLE", "lng DOUBLE", "role VARCHAR"], loc_rows)
        con.execute("INSERT INTO locations BY NAME SELECT * FROM s_loc")
        stage(con, "s_net", ["facility_id VARCHAR", "network_id VARCHAR", "role VARCHAR"], net_rows)
        con.execute("INSERT INTO network_membership BY NAME SELECT * FROM s_net")
        stage(con, "s_sph", ["facility_id VARCHAR", "sphere_slug VARCHAR", "role VARCHAR"], sph_rows)
        con.execute("INSERT INTO facility_spheres BY NAME SELECT * FROM s_sph")
        stage(con, "s_ids", ["facility_id VARCHAR", "scheme VARCHAR", "value VARCHAR",
                             "source_url VARCHAR"], id_rows)
        con.execute("INSERT INTO site_identifiers BY NAME SELECT * FROM s_ids")
        stage(con, "s_prov", ["record_type VARCHAR", "record_id VARCHAR", "source_url VARCHAR",
                              "retrieved_at DATE", "confidence VARCHAR", "agent VARCHAR"], prov_rows)
        con.execute("INSERT INTO provenance BY NAME SELECT * FROM s_prov")
        geri_db.assert_integrity(con, ["facilities", "locations", "network_membership",
                                       "facility_spheres", "site_identifiers", "networks",
                                       "facility_types", "spheres"])
    print(f"[facilities] {res}; {len(stale)} stale removed")
    print(f"[rows] locations {len(loc_rows)}, network_membership {len(net_rows)}, "
          f"facility_spheres {len(sph_rows)}, site_identifiers {len(id_rows)}, "
          f"provenance {len(prov_rows)}")
    for ri, n in geri_db.rows(con, """SELECT network_id, count(*) FROM network_membership
                                     GROUP BY 1 ORDER BY 2 DESC"""):
        print(f"[network] {ri:<18} {n}")
    snap = geri_db.latest_snapshot(con)
    print(f"[done] snapshot {snap.get('snapshot_id')} \"{snap.get('commit_message')}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
