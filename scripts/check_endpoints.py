#!/usr/bin/env python3
"""Request every data-access URL the archives layer records and say what answered.

Reads data/raw/J-GERI/ and data/raw/J-LTO/ (archives, api_endpoints,
cloud_buckets) and writes data/seed/endpoint_checks.csv, one row per URL:

  kind, archive_id, key, checked_url, http_status, verdict, detail, checked_at

  verdict  ok     2xx (after redirects)
           auth   401 / 403, or a redirect to a licence or login page:
                  the service is there and wants an account or acceptance
           alive  the server answers but the bare URL is not a full call
                  (400 / 405, e.g. a SPARQL endpoint without a query; or an
                  API root that is 404 while the calls under it work)
           gone   404 / 410, NoSuchBucket, an unknown host or a refused
                  connection -- load_geri_archives.py does not load these
           error  5xx or a timeout: try again before concluding anything

URLs come from an endpoint's check_url (J-GERI), else the first http(s)
URL in its example_call, else path_or_url when it has no {placeholder}.
Templated endpoints with neither are recorded as 'unchecked'. Buckets are
asked anonymously (S3 / GCS list request): AccessDenied is 'auth'.

Only GET (and one POSTed SPARQL query) are sent; nothing is written to
any service.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "seed" / "endpoint_checks.csv"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 geri-kmap"
URL_RE = re.compile(r"https?://[^\s'\"]+")
GATE_RE = re.compile(r"licen[cs]e|login|signin|sign-in|auth", re.I)


def load(name: str) -> list[dict]:
    rows = []
    for d in ("J-LTO", "J-GERI"):
        f = RAW / d / f"{name}.json"
        if f.exists():
            body = json.loads(f.read_text())
            rows += [dict(r, _src=d) for r in body.get(name, [])]
    return rows


def check_url(s: requests.Session, url: str) -> tuple[int | None, str, str]:
    try:
        r = s.get(url, timeout=30, allow_redirects=True, stream=True)
        r.close()
    except requests.exceptions.ConnectionError as e:
        return None, "gone", f"connection: {str(e)[:80]}"
    except requests.exceptions.Timeout:
        return None, "error", "timeout"
    except requests.RequestException as e:
        return None, "error", str(e)[:80]
    code = r.status_code
    hops = [h.headers.get("Location", "") for h in r.history]
    if any(GATE_RE.search(h) for h in hops) or (r.history and GATE_RE.search(r.url)):
        return code, "auth", f"redirected to {r.url[:100]}"
    if 200 <= code < 300:
        return code, "ok", ""
    if code in (401, 403):
        return code, "auth", ""
    if code in (400, 405, 406):
        return code, "alive", ""
    if code in (404, 410):
        return code, "gone", ""
    return code, "error", ""


def check_sparql(s: requests.Session, url: str) -> tuple[int | None, str, str]:
    try:
        r = s.post(url, data={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 1"},
                   headers={"Accept": "application/sparql-results+json"}, timeout=60)
    except requests.RequestException as e:
        return None, "error", str(e)[:80]
    return r.status_code, "ok" if r.ok else "error", "POSTed a 1-row query"


def check_bucket(s: requests.Session, b: dict) -> tuple[str, int | None, str, str]:
    name, prov, region = b["bucket_name"], b.get("provider"), b.get("region") or "us-east-1"
    if prov == "s3":
        url = f"https://{name}.s3.{region}.amazonaws.com/?list-type=2&max-keys=1"
    elif prov == "gcs":
        url = f"https://storage.googleapis.com/{name}?max-keys=1"
    elif prov == "azure":
        url = f"https://{name}.blob.core.windows.net/?comp=list&maxresults=1"
    else:
        return "", None, "unchecked", f"provider {prov}"
    try:
        r = s.get(url, timeout=30)
    except requests.RequestException as e:
        return url, None, "gone", str(e)[:80]
    body = r.text[:2000]
    if "NoSuchBucket" in body or "ResourceNotFound" in body or "ContainerNotFound" in body:
        return url, r.status_code, "gone", "no such bucket"
    if "AccessDenied" in body or "AuthorizationPermissionMismatch" in body or r.status_code in (401, 403):
        return url, r.status_code, "auth", "anonymous listing denied"
    if r.ok:
        return url, r.status_code, "ok", "anonymous listing allowed"
    return url, r.status_code, "error", ""


def endpoint_url(e: dict) -> str | None:
    if e.get("check_url"):
        return e["check_url"]
    m = URL_RE.search(e.get("example_call") or "")
    if m and "{" not in m.group(0):
        return m.group(0)
    p = e.get("path_or_url") or ""
    return p if p.startswith("http") and "{" not in p else None


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    now = dt.date.today().isoformat()
    out: list[dict] = []
    seen: set[tuple] = set()

    def add(kind, archive_id, key, url, code, verdict, detail):
        if (kind, archive_id, key) in seen:
            return
        seen.add((kind, archive_id, key))
        out.append(dict(kind=kind, archive_id=archive_id, key=key, checked_url=url or "",
                        http_status="" if code is None else code, verdict=verdict,
                        detail=detail, checked_at=now))
        print(f"[{verdict:>9}] {kind:<8} {archive_id:<18} {str(code or ''):>4} {key[:90]}")

    for a in load("archives"):
        for field in ("base_url", "api_url"):
            u = a.get(field)
            if u:
                code, verdict, detail = (check_sparql(s, u) if a.get("api_type") == "sparql" and field == "api_url"
                                         else check_url(s, u))
                # An API root often has nothing at '/' while every call
                # beneath it works (NEON, SAEON): the host answered.
                if field == "api_url" and verdict == "gone" and code == 404:
                    verdict, detail = "alive", "root path returns 404; the host answers"
                add("archive", a["archive_id"], f"{field}:{u}", u, code, verdict, detail)
    for e in load("api_endpoints"):
        u = endpoint_url(e)
        key = e["path_or_url"]
        if not u:
            add("endpoint", e["archive_id"], key, None, None, "unchecked", "templated, no example URL")
        elif (e.get("method") or "GET").upper() == "POST" and "sparql" in key:
            add("endpoint", e["archive_id"], key, key, *check_sparql(s, key))
        elif (e.get("method") or "GET").upper() not in ("GET", "HEAD"):
            add("endpoint", e["archive_id"], key, None, None, "unchecked",
                f"{e.get('method')} call; not sent")
        else:
            add("endpoint", e["archive_id"], key, u, *check_url(s, u))
    for b in load("cloud_buckets"):
        url, code, verdict, detail = check_bucket(s, b)
        add("bucket", b["archive_id"], f"{b['provider']}:{b['bucket_name']}", url, code, verdict, detail)

    out.sort(key=lambda r: (r["kind"], r["archive_id"], r["key"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    tally: dict[str, int] = {}
    for r in out:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"[done] {len(out)} checks -> {OUT.relative_to(ROOT)}: {tally}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
