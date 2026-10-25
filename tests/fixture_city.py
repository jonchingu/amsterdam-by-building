"""A small made-up city for testing the quest flyovers without the real data (which needs the 3D BAG downloads).

    uv run python tests/fixture_city.py /tmp/ams-fixture
    python3 -m http.server 8642 --directory /tmp/ams-fixture/web

Writes, under the given folder (never the repository's own data/): data/ with buildings and LoD 1.3 parts in the
shapes s01/s02 leave them, then runs the real s03_tiles for the tiles and the city config, writes the small JSON
files the app reads, two quests in the shape s13_quests writes, and plans their routes with
`s13_quests --routes-only`. web/ links the app's files next to the generated web/data/.

The city: blocks of narrow canal houses (8–22 m) on a street grid, a few landmarks, and a made-up 260 m tower between
two quest buildings, so that the route planner has a leg to lift or bend.
"""
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pipeline.periods import period_index  # noqa: E402

DAM = (121390.0, 487380.0)


def rect(cx, cz, w, d):
    """A footprint in RD New from a rectangle in the local frame (x east, z south)."""
    return shapely.box(DAM[0] + cx - w / 2, DAM[1] - cz - d / 2, DAM[0] + cx + w / 2, DAM[1] - cz + d / 2)


# name, parts [(cx, cz, w, d, height)], year
LANDMARKS = {
    "church_w": ("Westerkerk", [(-560, -120, 22, 55, 28), (-560, -155, 11, 11, 85)], 1631),
    "station": ("Centraal Station", [(120, -640, 320, 60, 32)], 1889),
    "tower": ("Made-up tower", [(-215, -385, 34, 34, 260)], 2020),
    "church_z": ("Zuiderkerk", [(320, 120, 18, 40, 24), (320, 95, 10, 10, 72)], 1611),
    "tiny": ("Tiny house", [(60, 40, 4, 8, 9)], 1738),
    "museum": ("Rijksmuseum", [(-150, 520, 140, 60, 35)], 1885),
}


def city():
    rng = np.random.default_rng(7)
    marks = shapely.union_all([rect(cx, cz, w + 8, d + 8) for _, parts, _ in LANDMARKS.values() for cx, cz, w, d, _ in parts])
    rows, parts = [], []
    n = 0

    def add(geoms_heights, year, key=None):
        nonlocal n
        bag = f"{363100000000000 + n:016d}"
        n += 1
        ident = f"NL.IMBAG.Pand.{bag}"
        fp = shapely.union_all([g for g, _ in geoms_heights])
        top = max(h for _, h in geoms_heights)
        rows.append(dict(identificatie=ident, oorspronkelijkbouwjaar=year, year=year, date_flag=0,
                         period=period_index(year), height=float(top), floors=max(1, round(top / 3.2)), floors_src=1,
                         monument=None, b3_h_maaiveld=0.5, geometry=fp, key=key))
        for k, (g, h) in enumerate(geoms_heights):
            parts.append(dict(identificatie=ident, b3_pand_deel_id=k, b3_dd_id=0, b3_h_min=0.5 + h * 0.6,
                              b3_h_50p=0.5 + h * 0.85, b3_h_70p=0.5 + h * 0.9, b3_h_max=0.5 + h, geometry=g))
        return bag

    for bx in np.arange(-840, 841, 70.0):
        for bz in np.arange(-605, 606, 55.0):
            year = int(rng.integers(1600, 2000))
            # houses round the block's edge: 55 × 40 m, each 7 m wide and 12 m deep
            for side in range(4):
                length = 55 if side % 2 == 0 else 40
                for k in range(int(length // 7)):
                    off = -length / 2 + 3.5 + 7 * k
                    if side == 0:
                        cx, cz, w, d = bx + off, bz - 14, 7, 12
                    elif side == 2:
                        cx, cz, w, d = bx + off, bz + 14, 7, 12
                    elif side == 1:
                        cx, cz, w, d = bx + 21.5, bz + off, 12, 7
                    else:
                        cx, cz, w, d = bx - 21.5, bz + off, 12, 7
                    g = rect(cx, cz, w - 0.3, d - 0.3)
                    if g.intersects(marks):
                        continue
                    add([(g, float(rng.uniform(8, 22)))], int(np.clip(year + rng.integers(-40, 40), 1300, 2024)))
    bags = {key: add([(rect(cx, cz, w, d), h) for cx, cz, w, d, h in ps], year, key)
            for key, (_, ps, year) in LANDMARKS.items()}
    return gpd.GeoDataFrame(rows, crs=28992), gpd.GeoDataFrame(parts, crs=28992), bags


def polygons_bin(polys):
    """Polygons in the format of s04_water: counts, ring and vertex starts, then x, z pairs in the local frame."""
    ring_start, vert_start, xz = [0], [0], []
    for ring in polys:
        xz += [c for p in ring for c in p]
        vert_start.append(vert_start[-1] + len(ring))
        ring_start.append(len(vert_start) - 1)
    out = struct.pack("<3I", len(polys), len(polys), len(xz) // 2)
    out += np.array(ring_start, "<u4").tobytes() + np.array(vert_start, "<u4").tobytes()
    return out + np.array(xz, "<f4").tobytes()


def T(en, nl):
    return dict(en=en, nl=nl)


PHOTO = "data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='40'%3E%3Crect width='64' height='40' fill='%23b5c7c6'/%3E%3C/svg%3E"


def quests(bags):
    def find(key, riddle):
        return dict(kind="find", riddle=T(riddle, riddle), hints=[T("A hint.", "Een hint.")],
                    reveal=T(f"It is the {LANDMARKS[key][0]}.", f"Het is de {LANDMARKS[key][0]}."), bags=[bags[key]], sources=[])

    def where(key):
        name = LANDMARKS[key][0]
        return dict(kind="where", riddle=T(f"Where is {name}?", f"Waar staat {name}?"), reveal=T(name, name),
                    clue=dict(thumb=PHOTO), bags=[bags[key]], sources=[])

    return [
        dict(id="fixture", level=1, title=T("Fixture walk", "Testwandeling"), intro=T("Four stops.", "Vier stops."), steps=[
            find("church_w", "A church with a tall tower in the west."),
            dict(kind="choice", ask=T("When did the station open?", "Wanneer ging het station open?"),
                 options=[T("1889", "1889"), T("1850", "1850"), T("1920", "1920")], reveal=T("In 1889.", "In 1889."),
                 bags=[bags["station"]], sources=[]),
            dict(kind="year", ask=T("When was this tiny house built?", "Wanneer werd dit huisje gebouwd?"), year=1738,
                 reveal=T("In 1738.", "In 1738."), bags=[bags["tiny"]], sources=[]),
            find("church_z", "A church with a tower in the east."),
        ]),
        dict(id="fixture-where", level=1, title=T("Fixture where", "Test waar"), intro=T("Three taps.", "Drie tikken."),
             steps=[where("museum"), where("church_z"), where("church_w")]),
    ]


def main(root):
    root = Path(root).resolve()
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    web = root / "web"
    web.mkdir(exist_ok=True)
    for f in os.listdir(REPO / "web"):
        if f != "data" and not (web / f).exists():
            (web / f).symlink_to(REPO / "web" / f)
    b, q, bags = city()
    wk = {bag: i for i, bag in enumerate(bags.values())}
    b.drop(columns="key").to_parquet(root / "data" / "buildings.parquet")
    q.to_parquet(root / "data" / "parts.parquet")
    pd.DataFrame(dict(identificatie=b.identificatie, lay0=0, lay1=0)).to_parquet(root / "data" / "layers.parquet")
    pd.DataFrame(dict(bag=list(wk), wk=list(wk.values()))).to_parquet(root / "data" / "wiki_index.parquet")
    (root / "data" / "raw" / "energy.json").write_text("{}")
    env = dict(os.environ, PYTHONPATH=str(REPO))
    subprocess.run([sys.executable, "-m", "pipeline.s03_tiles"], cwd=root, env=env, check=True)
    out = root / "web" / "data"
    land = [[(-1500, -1200), (1500, -1200), (1500, 1200), (-1500, 1200)]]
    water = [[(-1500, z), (1500, z), (1500, z + 15), (-1500, z + 15)] for z in (-305.0, 245.0)]
    (out / "land.bin").write_bytes(polygons_bin(land))
    (out / "water.bin").write_bytes(polygons_bin(water))
    (out / "labels.json").write_text("[]")
    (out / "layers.json").write_text("[]")
    (out / "facts.json").write_text("{}")
    (out / "wiki.json").write_text(json.dumps([dict(label=LANDMARKS[k][0], label_nl=LANDMARKS[k][0]) for k in bags]))
    (out / "quests.json").write_text(json.dumps(quests(bags)))
    subprocess.run([sys.executable, "-m", "pipeline.s13_quests", "--routes-only"], cwd=root, env=env, check=True)
    print("fixture city in", root)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ams-fixture")
