"""Names, years, architects, photos, heritage status and Wikipedia articles from Wikidata, matched to PLATEAU buildings.

Wikidata items that are buildings or towers and carry coordinates inside the converted wards are matched to the
building whose footprint contains the point, else the nearest within MATCH_RADIUS metres. Where Wikidata gives a
height or a floor count, a building that disagrees by more than a third loses to a better fitting neighbour.
Railway stations count only when the point falls inside a footprint (station buildings, not platforms or tracks).
When several items land on one building, the best-known one (most sitelinks) keeps it.
Corrections checked by hand live in tokyo_wiki_fixes.py: an item pinned to a building, or dropped.

Heritage designations (P1435) are grouped by who designates them: the nation (国宝, 重要文化財, 登録有形文化財),
Tokyo Metropolis, or the ward.

PLATEAU's own 名称 is sometimes a tenant rather than the building (the Grand Hyatt is filed under the police box on
its ground floor), so the viewer shows the Wikidata name first.

Wikidata is CC0. Photos are Wikimedia Commons file names; the viewer loads them from Commons and links each file page.

Output: web/data/tokyo/wiki.json  {PLATEAU id: {wd, ja, en, descJa, descEn, year, architects, types, styles,
                                                heritage, image, commons, website, jawiki, enwiki}}
         Labelled values are [English, Japanese]; heritage entries add their level (see HERITAGE_LEVELS).

    uv run python -m pipeline.tokyo_s02_wiki      # after tokyo_s01_buildings
"""
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import requests
from scipy.spatial import cKDTree

from .tokyo_wiki_fixes import FIXES

OUT = Path("web/data/tokyo")
RAW = Path("data/tokyo/wikidata.json")
SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "amsterdam-by-building/tokyo (https://github.com/jonchingu/amsterdam-by-building)",
           "Accept": "application/sparql-results+json"}
STEP = 0.03  # degrees per query box
MATCH_RADIUS = 40.0
KINDS = ["wd:Q41176", "wd:Q12518"]  # building, tower
INSIDE_ONLY = ["wd:Q55488"]  # railway station
GENERIC = {"Q41176", "Q811979", "Q12518"}  # building, architectural structure, tower: not shown as a type
# Heritage levels, highest first; a designation's Japanese label decides its level.
HERITAGE_LEVELS = [
    ("National Treasure", ("国宝",)),
    ("Important Cultural Property", ("重要文化財",)),
    ("Registered Tangible Cultural Property", ("登録有形文化財",)),
    ("Tokyo Metropolis designated", ("東京都", "都指定", "都選定")),
    ("Ward designated or registered", ("区指定", "区登録", "区の")),
    ("Other designation", ("",)),
]

ITEMS = """
SELECT ?i ?t ?tJa ?tEn ?ja ?en ?descJa ?descEn ?c ?inception ?opened ?img ?commons ?site ?arch ?archJa ?archEn
       ?height ?floors ?links ?jawiki ?enwiki WHERE {
  SERVICE wikibase:box { ?i wdt:P625 ?c .
    bd:serviceParam wikibase:cornerSouthWest "Point(%(w)s %(s)s)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(%(e)s %(n)s)"^^geo:wktLiteral . }
  ?i wdt:P31 ?t ; wikibase:sitelinks ?links .
  FILTER NOT EXISTS { ?i wdt:P576 [] }  # demolished or closed
  OPTIONAL { ?i rdfs:label ?ja FILTER(LANG(?ja) = "ja") }
  OPTIONAL { ?i rdfs:label ?en FILTER(LANG(?en) = "en") }
  OPTIONAL { ?t rdfs:label ?tJa FILTER(LANG(?tJa) = "ja") }
  OPTIONAL { ?t rdfs:label ?tEn FILTER(LANG(?tEn) = "en") }
  OPTIONAL { ?i schema:description ?descJa FILTER(LANG(?descJa) = "ja") }
  OPTIONAL { ?i schema:description ?descEn FILTER(LANG(?descEn) = "en") }
  OPTIONAL { ?i wdt:P373 ?commons }
  OPTIONAL { ?i wdt:P856 ?site }
  OPTIONAL { ?i wdt:P571 ?inception }
  OPTIONAL { ?i wdt:P1619 ?opened }
  OPTIONAL { ?i wdt:P18 ?img }
  OPTIONAL { ?i wdt:P84 ?arch .
    OPTIONAL { ?arch rdfs:label ?archJa FILTER(LANG(?archJa) = "ja") }
    OPTIONAL { ?arch rdfs:label ?archEn FILTER(LANG(?archEn) = "en") } }
  OPTIONAL { ?i wdt:P2048 ?height }
  OPTIONAL { ?i wdt:P1101 ?floors }
  OPTIONAL { ?jawiki schema:about ?i ; schema:isPartOf <https://ja.wikipedia.org/> }
  OPTIONAL { ?enwiki schema:about ?i ; schema:isPartOf <https://en.wikipedia.org/> }
}"""
# Style (P149) and heritage designation (P1435) apart, so their values do not multiply the rows above.
EXTRAS = """
SELECT ?i ?kind ?v ?vJa ?vEn WHERE {
  SERVICE wikibase:box { ?i wdt:P625 ?c .
    bd:serviceParam wikibase:cornerSouthWest "Point(%(w)s %(s)s)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(%(e)s %(n)s)"^^geo:wktLiteral . }
  { ?i wdt:P149 ?v BIND("styles" AS ?kind) } UNION { ?i wdt:P1435 ?v BIND("heritage" AS ?kind) }
  OPTIONAL { ?v rdfs:label ?vJa FILTER(LANG(?vJa) = "ja") }
  OPTIONAL { ?v rdfs:label ?vEn FILTER(LANG(?vEn) = "en") }
}"""
KIND_OF = "SELECT DISTINCT ?t WHERE { VALUES ?t { %s } VALUES ?k { %s } ?t wdt:P279* ?k }"


def sparql(query):
    for attempt in range(5):
        r = requests.get(SPARQL, params={"query": query}, headers=HEADERS, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(int(r.headers.get("Retry-After", 0)) or 5 * 2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()["results"]["bindings"]
    raise RuntimeError(f"Wikidata kept refusing: {r.status_code}")


def qid(uri):
    return uri.rsplit("/", 1)[1]


# Metres around Tokyo Station <-> degrees, the same small-area approximation as the viewer's map links.
def frame(origin):
    lat0, lon0 = origin
    a, e2, p = 6378137, 6.69437999014e-3, math.radians(lat0)
    s = math.sin(p) ** 2
    m, n = a * (1 - e2) / (1 - e2 * s) ** 1.5, a / math.sqrt(1 - e2 * s)
    to_deg = lambda x, z: (lat0 - np.asarray(z) / m * 180 / math.pi, lon0 + np.asarray(x) / (n * math.cos(p)) * 180 / math.pi)
    to_xz = lambda lat, lon: ((np.asarray(lon) - lon0) * math.pi / 180 * n * math.cos(p), -(np.asarray(lat) - lat0) * math.pi / 180 * m)
    return to_deg, to_xz


def fetch_items(index):
    if RAW.exists():
        return json.loads(RAW.read_text())
    to_deg, _ = frame(index["origin"])
    lat, lon = to_deg(index["columns"]["x"], index["columns"]["z"])
    rows, extras = [], []
    for s in np.arange(lat.min() - 0.002, lat.max() + 0.002, STEP):
        for w in np.arange(lon.min() - 0.002, lon.max() + 0.002, STEP):
            box = dict(s=round(s, 4), w=round(w, 4), n=round(s + STEP, 4), e=round(w + STEP, 4))
            rows += sparql(ITEMS % box)
            extras += sparql(EXTRAS % box)
            time.sleep(1)
    types = sorted({r["t"]["value"] for r in rows})
    kinds, strict = set(), set()
    for i in range(0, len(types), 200):
        values = " ".join(f"wd:{qid(t)}" for t in types[i:i + 200])
        kinds |= {r["t"]["value"] for r in sparql(KIND_OF % (values, " ".join(KINDS)))}
        strict |= {r["t"]["value"] for r in sparql(KIND_OF % (values, " ".join(INSIDE_ONLY)))}
    items = {}
    for r in rows:
        if r["t"]["value"] not in kinds | strict:
            continue
        v = lambda k: r[k]["value"] if k in r else None
        d = items.setdefault(qid(v("i")), dict(wd=qid(v("i")), years=[], architects=[], types=[], styles=[],
                                               heritage=[], links=int(v("links")), inside_only=True))
        d["inside_only"] &= r["t"]["value"] not in kinds
        kind = [v("tEn") or v("tJa"), v("tJa")]
        if qid(v("t")) not in GENERIC and kind[0] and kind not in d["types"]:
            d["types"].append(kind)
        lon_, lat_ = map(float, v("c").removeprefix("Point(").rstrip(")").split())
        d.setdefault("lat", lat_); d.setdefault("lon", lon_)
        for k in ("ja", "en", "descJa", "descEn", "jawiki", "enwiki", "img", "commons", "site", "height", "floors"):
            if v(k) and k not in d:
                d[k] = v(k)
        for k in ("inception", "opened"):
            year = re.match(r"(-?\d+)-", v(k) or "")
            if year:
                d["years"].append(int(year.group(1)))
        arch = [v("archEn") or v("archJa"), v("archJa")]
        if arch[0] and arch not in d["architects"]:
            d["architects"].append(arch)
    for r in extras:
        d = items.get(qid(r["i"]["value"]))
        label = [r.get("vEn", r.get("vJa", {})).get("value"), r.get("vJa", {}).get("value")]
        if d and label[0] and label not in d[r["kind"]["value"]]:
            d[r["kind"]["value"]].append(label)
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(list(items.values()), ensure_ascii=False))
    return list(items.values())


def footprints(index):
    """Per building, its triangles flattened to the ground (x, z), for point-in-footprint tests."""
    cols = index["columns"]
    members = [[] for _ in index["cells"]]
    for i, (c, s) in enumerate(zip(cols["cell"], cols["slot"])):
        members[c].append((s, i))
    tris = {}
    for ci, key in enumerate(index["cells"]):
        buf = (OUT / "cells" / f"{key}.bin").read_bytes()
        n = int(np.frombuffer(buf, np.uint32, 1)[0])
        vc = np.frombuffer(buf, np.uint32, n, 4).astype(np.int64)
        ic = np.frombuffer(buf, np.uint32, n, 4 + 4 * n).astype(np.int64)
        verts = np.frombuffer(buf, np.float32, 3 * int(vc.sum()), 4 + 8 * n).reshape(-1, 3)
        faces = np.frombuffer(buf, np.uint32, int(ic.sum()), 4 + 8 * n + 12 * int(vc.sum()))
        vs, fs = np.r_[0, np.cumsum(vc)], np.r_[0, np.cumsum(ic)]
        for s, i in sorted(members[ci]):
            v = verts[vs[s]:vs[s + 1]][:, [0, 2]] + (cols["x"][i], cols["z"][i])
            tris[i] = v[faces[fs[s]:fs[s + 1]].reshape(-1, 3)]
    return tris


def inside(point, tri):
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    cross = lambda p, q, r: (q[:, 0] - p[:, 0]) * (r[1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (r[0] - p[:, 0])
    d1, d2, d3 = cross(a, b, point), cross(b, c, point), cross(c, a, point)
    neg, pos = (d1 < 0) | (d2 < 0) | (d3 < 0), (d1 > 0) | (d2 > 0) | (d3 > 0)
    return bool(np.any(~(neg & pos)))


def heritage_level(label):
    ja = label[1] or ""
    return next(k for k, (_, marks) in enumerate(HERITAGE_LEVELS) if any(m in ja for m in marks))


def main():
    index = json.loads((OUT / "buildings.json").read_text())
    cols = index["columns"]
    items = fetch_items(index)
    _, to_xz = frame(index["origin"])
    tris = footprints(index)
    tree = cKDTree(np.c_[cols["x"], cols["z"]])
    lo = {i: t.reshape(-1, 2).min(0) for i, t in tris.items()}
    hi = {i: t.reshape(-1, 2).max(0) for i, t in tris.items()}

    ids = {f"{index['wards'][w][0]}-bldg-{b}": i for i, (w, b) in enumerate(zip(cols["ward"], cols["bldg"]))}
    best, fixed = {}, 0
    for it in items:
        if it["wd"] in FIXES:
            fixed += 1
            if FIXES[it["wd"]] is not None:
                best[ids[FIXES[it["wd"]]]] = (dict(it, links=10 ** 6), 0.0)
            continue
        p = np.array(to_xz(it["lat"], it["lon"]))
        known = float(it["height"]) if it.get("height") else (float(it["floors"]) * 3.8 if it.get("floors") else None)
        choice = None
        for i in tree.query_ball_point(p, 400):
            if i not in tris:
                continue
            gap = np.maximum(np.maximum(lo[i] - p, p - hi[i]), 0)
            d = 0.0 if not gap.any() and inside(p, tris[i]) else float(np.hypot(*gap)) + 1.0
            if d > (0 if it["inside_only"] else MATCH_RADIUS):
                continue
            # A height that disagrees only ranks a candidate lower; it never rules the item out.
            h = cols["height"][i] or 0
            score = d + (MATCH_RADIUS if known and abs(h - known) > max(h, known) / 3 else 0)
            if choice is None or score < choice[0]:
                choice = (score, d, i)
        if choice:
            _, d, i = choice
            if i not in best or (it["links"], -d) > (best[i][0]["links"], -best[i][1]):
                best[i] = (it, d)

    wards = index["wards"]
    out = {}
    for i, (it, _) in best.items():
        rec = {k: it[k] for k in ("wd", "ja", "en", "descJa", "descEn", "jawiki", "enwiki", "commons", "site",
                                  "types", "styles") if it.get(k)}
        if it["heritage"]:
            rec["heritage"] = sorted(([*h, heritage_level(h)] for h in it["heritage"]), key=lambda h: h[2])
        if it["years"]:
            rec["year"] = min(it["years"])
        if it["architects"]:
            rec["architects"] = it["architects"]
        if it.get("img"):
            rec["image"] = requests.utils.unquote(it["img"].rsplit("/", 1)[1])
        for k in ("jawiki", "enwiki"):
            if k in rec:
                rec[k] = requests.utils.unquote(rec[k].rsplit("/wiki/", 1)[1])
        out[f"{wards[cols['ward'][i]][0]}-bldg-{cols['bldg'][i]}"] = rec
    (OUT / "wiki.json").write_text(json.dumps(
        dict(source="Wikidata (CC0); photos from Wikimedia Commons", heritageLevels=[h for h, _ in HERITAGE_LEVELS],
             buildings=out), ensure_ascii=False, separators=(",", ":")))
    print(f"{len(items)} Wikidata buildings, {len(out)} matched: {sum('year' in r for r in out.values())} with a year, "
          f"{sum('image' in r for r in out.values())} with a photo, {sum('architects' in r for r in out.values())} "
          f"with an architect, {sum('heritage' in r for r in out.values())} with heritage status, "
          f"{sum(not cols['name'][i] for i in best)} were unnamed in PLATEAU; {fixed} set by hand")


if __name__ == "__main__":
    main()
