#!/usr/bin/env python3
"""Fetch the "nearest neighbor" organization survey behind Loescher et al. (2026).

Loescher et al. (2026, Ecosphere, doi:10.1002/ecs2.70789, Table 3) report a
snowball landscape scan of terrestrial ecosystem observatories, observation
networks and data aggregators that could partner with GERI. The scan is
published as Ceron Castano, Specht, Morris & Loescher, "Terrestrial
Ecosystem Observatories" (Zenodo, doi:10.5281/zenodo.17717896, CC BY 4.0):
one spreadsheet row per organization, with name, English name, acronym,
web link, scope, region, country, type (Observation / Aggregation /
Network) and a description. Version 2 of the spreadsheet lists 251
organizations; the paper counts 223 (an earlier cut).

The paper's GENNI use case (Box 1) names five Mexican networks. MexFlux
is in the spreadsheet; the other four (RISZA, OSPE, PUEIS, YECS-IUSS) are
added from Box 1 with the links it gives, marked ``source = ecs2.70789-box1``.

The spreadsheet is downloaded to data/cache/ (gitignored); its rows go to
``data/raw/J-GENNI/landscape_orgs.json`` (committed). The spreadsheet's
``Location`` column is a broken formula (#REF!) in every row and is dropped.
E-mail addresses in descriptions are removed: contact details are not published.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import openpyxl
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "J-GENNI" / "landscape_orgs.json"
CACHE = ROOT / "data" / "cache" / "terrestrial_ecosystem_observatories_v2.xlsx"
RECORD = "https://zenodo.org/api/records/17717896"
DOI = "10.5281/zenodo.17717896"
PAPER = "https://doi.org/10.1002/ecs2.70789"
# Box 1 of the paper: the Mexican networks of the GENNI use case that the
# survey does not list. Descriptions are summaries of Box 1, links as given.
BOX1 = [
    {"name": "Red Internacional para la Sostenibilidad de las Zonas Áridas",
     "name_en": "International Network for Drylands Sustainability", "acronym": "RISZA",
     "url": "https://risza.mx/", "scope": "International", "region": "Americas", "country": "Mexico",
     "type": "Network", "description": "Multidisciplinary international network for drylands "
     "sustainability, established in 2017. One of the five Mexican networks of the GENNI use case."},
    {"name": "Red de Observatorios Socio-Ecológicos Participativos",
     "name_en": "Network of Social-Ecological Participatory Observatories", "acronym": "OSPE",
     "url": "https://conahcyt.mx/convocatorias/programas-nacionales-estrategicos/"
            "convocatoria-2024-propuestas-de-proyectos-nacionales-de-investigacion-e-incidencia/",
     "scope": "Domestic", "region": "Americas", "country": "Mexico", "type": "Observation|Network",
     "description": "Participatory social-ecological observatories that grew out of a national "
     "research-and-impact project (Pronaii). One of the five Mexican networks of the GENNI use case."},
    {"name": "Programa Universitario de Estudios Interdisciplinarios del Suelo",
     "name_en": "University Program for Interdisciplinary Soil Studies", "acronym": "PUEIS",
     "url": "https://pueis.cic.unam.mx/", "scope": "Domestic", "region": "Americas", "country": "Mexico",
     "type": "Network", "description": "UNAM's national network for interdisciplinary soil studies, "
     "promoting soil science education and transdisciplinary soil projects. One of the five Mexican "
     "networks of the GENNI use case."},
    {"name": "Young and Early Career Scientists Working Group, International Union of Soil Sciences",
     "name_en": None, "acronym": "YECS-IUSS", "url": "https://www.iuss.org/working-groups/",
     "scope": "International", "region": "Americas", "country": "Mexico", "type": "Network",
     "description": "IUSS working group for young and early-career soil scientists, established in "
     "2022 by Poland and Mexico. One of the five Mexican networks of the GENNI use case."},
]
EMAIL_RE = re.compile(r"\s*\(?[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\)?")
FIELDS = ["name", "name_en", "acronym", "url", "scope", "region", "country", "location", "type", "description"]


def clean(v):
    if v is None:
        return None
    v = " ".join(str(v).split())
    return v or None


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    rec = s.get(RECORD, timeout=60).json()
    f = rec["files"][0]
    if not CACHE.exists() or CACHE.stat().st_size != f["size"]:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(s.get(f["links"]["self"], timeout=120).content)
    rows = list(openpyxl.load_workbook(CACHE, read_only=True, data_only=True)
                .worksheets[0].iter_rows(values_only=True))
    if not str(rows[1][0]).startswith("Capability name"):
        print(f"[error] unexpected header row: {rows[1]}", file=sys.stderr)
        return 1
    orgs = []
    for r in rows[2:]:
        d = {k: clean(v) for k, v in zip(FIELDS, r)}
        if not d["name"]:
            continue
        d.pop("location")
        if d["description"]:
            d["description"] = EMAIL_RE.sub("", d["description"]).strip() or None
        d["source"] = "zenodo.17717896"
        orgs.append(d)
    have = {(o["acronym"] or "").upper() for o in orgs} | {o["name"].upper() for o in orgs}
    for b in BOX1:
        if b["acronym"].upper() in have or b["name"].upper() in have:
            print(f"[box1] {b['acronym']} already in the survey")
            continue
        orgs.append({**b, "source": "ecs2.70789-box1"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": f"https://doi.org/{DOI}", "file": f["key"],
                               "file_md5": f.get("checksum"), "license": rec["metadata"]["license"]["id"],
                               "title": rec["metadata"]["title"], "paper": PAPER,
                               "retrieved_at": dt.date.today().isoformat(), "orgs": orgs},
                              ensure_ascii=False, indent=1) + "\n")
    n_box = sum(o["source"] == "ecs2.70789-box1" for o in orgs)
    print(f"[done] {len(orgs) - n_box} survey organizations + {n_box} from Box 1 -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
