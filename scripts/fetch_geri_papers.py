#!/usr/bin/env python3
"""Fetch the bibliographic records of the GERI papers and datasets the catalogue cites.

DOIs are listed in PAPERS; each is read from its registration agency
(Crossref, else DataCite: Zenodo and CyVerse Data Commons datasets) and
written to ``data/raw/J-GENNI/publications.json`` for load_geri_paper.py:

  doi, title, pub_year, pub_type, journal, venue, url, abstract, license, authors

VENUE names the meeting of a conference abstract, which Crossref does not
carry (read from the abstract's landing page).

Authors are names as registered (no affiliations, no contact details).
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
OUT = ROOT / "data" / "raw" / "J-GENNI" / "publications.json"
# doi -> why the catalogue cites it
PAPERS = {
    "10.1002/ecs2.70789": "GERI and the GENNI network-of-networks proposal: RI profiles (Table 1), "
                          "site counts (Figure 1), Mexican networks (Box 1), landscape survey (Table 3)",
    "10.1002/ecs2.4262": "GERI's network-of-networks pathway (SanClements et al. 2022), cited by the above",
    "10.5281/zenodo.17717896": "The landscape survey's data: network_organizations",
    "10.5281/zenodo.17726569": "The Mexican network-of-networks vision statement (GENNI use case)",
    "10.5194/egusphere-egu26-12357": "Karns et al. (2026), EGU: LLM-agent harmonization of GERI data, "
                                     "tuned and validated on GERI's hand-harmonized products",
    "10.25739/e9d8-ee77": "Karns et al. (2026), CyVerse Data Commons: the inputs, human reference "
                          "harmonized products, target schema and agent logs of that study",
}
# https://meetingorganizer.copernicus.org/EGU26/EGU26-12357.html
VENUE = {"10.5194/egusphere-egu26-12357": "EGU General Assembly 2026, Vienna, 3-8 May 2026; "
                                          "session ESSI2.5, abstract EGU26-12357"}
TAG_RE = re.compile(r"<[^>]+>")


def strip(x: str | None) -> str | None:
    if not x:
        return None
    x = re.sub(r"^\s*Abstract\s*", "", html.unescape(TAG_RE.sub(" ", x)))
    return " ".join(x.split()) or None


def crossref(s: requests.Session, doi: str) -> dict:
    m = s.get(f"https://api.crossref.org/works/{doi}", timeout=60).json()["message"]
    date = m.get("published") or m.get("posted")
    lic = next((l["URL"] for l in m.get("license", []) if l.get("content-version") == "vor"), None)
    return {"title": m["title"][0], "pub_year": date["date-parts"][0][0],
            "pub_type": m["type"], "journal": (m.get("container-title") or [None])[0],
            "volume": m.get("volume"), "article_number": m.get("article-number"),
            "url": f"https://doi.org/{doi}", "abstract": strip(m.get("abstract")), "license": lic,
            "authors": [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in m.get("author", [])],
            "registry": "crossref"}


def datacite(s: requests.Session, doi: str) -> dict:
    a = s.get(f"https://api.datacite.org/dois/{doi}", timeout=60).json()["data"]["attributes"]
    desc = next((d["description"] for d in a.get("descriptions", []) if d.get("descriptionType") == "Abstract"), None)
    return {"title": a["titles"][0]["title"], "pub_year": int(a["publicationYear"]),
            "pub_type": (a.get("types") or {}).get("resourceTypeGeneral", "Dataset").lower(),
            "journal": a.get("publisher") if isinstance(a.get("publisher"), str) else (a.get("publisher") or {}).get("name"),
            "url": f"https://doi.org/{doi}", "abstract": strip(desc)[:2000] if desc else None,
            "license": next((r.get("rightsUri") for r in a.get("rightsList", []) if r.get("rightsUri")), None),
            "authors": [c.get("name") for c in a.get("creators", [])], "registry": "datacite"}


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = "geri-kmap (https://github.com/tyson-swetnam/geri-kmap)"
    out = []
    for doi, why in PAPERS.items():
        found = s.get(f"https://api.crossref.org/works/{doi}", timeout=60).status_code == 200
        rec = crossref(s, doi) if found else datacite(s, doi)
        out.append({"doi": doi, "cited_for": why, **rec, "venue": VENUE.get(doi)})
        print(f"[paper] {doi}: {rec['title'][:70]} ({rec['pub_year']})")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"retrieved_at": dt.date.today().isoformat(), "publications": out},
                              ensure_ascii=False, indent=1) + "\n")
    print(f"[done] {len(out)} records -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
