"""Split PLATEAU 3D Tiles into single buildings, for the one-by-one viewer in web/tokyo/.

Each b3dm tile holds a glTF whose vertices carry a _BATCHID; the batch table gives each id its attributes.
Every building is cut out, moved from Earth-centred coordinates to metres around Tokyo Station, and set on its own
base: x east, y up, z south (three.js), with (0, 0, 0) under the middle of its footprint.

Output (web/data/tokyo/):
  buildings.json   columnar index: attributes (with flood depth, fire zone and planning districts), position, cell
                   and slot of every building; a building's PLATEAU id
                   (建物ID) is its ward code, "-bldg-" and its bldg number
  cells/<i>_<j>.bin  the buildings whose centre falls in one 500 m cell, little-endian:
      u32 n; u32 vertCount[n]; u32 indexCount[n]; f32 xyz[3 * sum(vertCount)]; u32 index[sum(indexCount)]
  Indices count from each building's first vertex.

    uv run python -m pipeline.tokyo_s01_buildings              # every ward fetched by tokyo_s00_fetch
    uv run python -m pipeline.tokyo_s01_buildings 13101 13102  # only these
"""
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from .tokyo_s00_fetch import RAW, WARDS

OUT = Path("web/data/tokyo")
CELL = 500.0
ORIGIN = (35.681236, 139.767125, 40.0)  # Tokyo Station, lat, lon, ellipsoidal height

# PLATEAU 2020 code values, in English for the viewer; anything unlisted is shown as given.
USAGE = {
    "業務施設": "Offices", "商業施設": "Shops and commerce", "宿泊施設": "Hotel", "商業系複合施設": "Mixed commercial",
    "住宅": "House", "共同住宅": "Apartments", "店舗等併用住宅": "House with shop", "店舗等併用共同住宅": "Apartments with shops",
    "作業所併用住宅": "House with workshop", "官公庁施設": "Government", "文教厚生施設": "Education, health and welfare",
    "運輸倉庫施設": "Transport and storage", "工場": "Factory", "農林漁業用施設": "Farming and fishing",
    "供給処理施設": "Utilities", "防衛施設": "Defence", "その他": "Other", "不明": "Unknown",
}
STRUCTURE = {
    "耐火構造": "Fire-resistant", "準耐火構造": "Semi-fire-resistant", "防火造": "Fire-protected",
    "準防火造": "Semi-fire-protected", "木造": "Wood", "鉄骨造": "Steel frame", "鉄筋コンクリート造": "Reinforced concrete",
    "鉄骨鉄筋コンクリート造": "Steel-reinforced concrete", "非木造": "Non-wood",
}
FIRE = {"防火地域": "Fire zone", "準防火地域": "Semi-fire zone"}
HEIGHT_DISTRICT = {
    "第一種高度地区": "Class 1 height district", "第二種高度地区": "Class 2 height district",
    "第三種高度地区": "Class 3 height district", "最低限高度、再高限高度指定のみ": "Minimum or maximum height only",
}
LANDSLIDE = {
    "急傾斜地の崩壊 - 土砂災害警戒区域": "Steep-slope collapse warning zone",
    "急傾斜地の崩壊 - 土砂災害特別警戒区域": "Steep-slope collapse special warning zone",
}
# Flood columns are named "<scenario area>_想定最大規模_浸水深" (depth under the assumed maximum rainfall), one per river basin.
FLOOD_DEPTH, FLOOD_HOURS = "_想定最大規模_浸水深", "_想定最大規模_継続時間"
RIVERS = {
    "荒川水系荒川洪水浸水想定区域": "Arakawa River", "神田川流域浸水予想区域": "Kanda River basin",
    "城南地区河川流域浸水予想区域（改定）": "Jōnan rivers (Shibuya, Furukawa, Meguro)",
    "江東内部河川流域浸水予想区域": "Kōtō inner rivers",
}
COMPONENT = {"BYTE": "b", "UNSIGNED_BYTE": "B", "SHORT": "h", "UNSIGNED_SHORT": "H", "INT": "i", "UNSIGNED_INT": "I",
             "FLOAT": "f", "DOUBLE": "d", 5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def ecef(lat, lon, h):
    a, e2 = 6378137.0, 6.69437999014e-3
    p, l = np.radians(lat), np.radians(lon)
    n = a / np.sqrt(1 - e2 * np.sin(p) ** 2)
    return np.array([(n + h) * np.cos(p) * np.cos(l), (n + h) * np.cos(p) * np.sin(l), (n * (1 - e2) + h) * np.sin(p)])


def enu_frame(lat, lon, h):
    p, l = np.radians(lat), np.radians(lon)
    rot = np.array([
        [-np.sin(l), np.cos(l), 0],
        [-np.sin(p) * np.cos(l), -np.sin(p) * np.sin(l), np.cos(p)],
        [np.cos(p) * np.cos(l), np.cos(p) * np.sin(l), np.sin(p)],
    ])
    return ecef(lat, lon, h), rot


def read_b3dm(path: Path):
    f = path.read_bytes()
    magic, _, _, ftj, ftb, btj, btb = struct.unpack("<4sIIIIII", f[:28])
    if magic != b"b3dm":
        raise ValueError(f"{path} is not a b3dm")
    feature = json.loads(f[28:28 + ftj])
    o = 28 + ftj + ftb
    table = json.loads(f[o:o + btj]) if btj else {}
    binary = f[o + btj:o + btj + btb]
    n = feature["BATCH_LENGTH"]
    attrs = {}
    for key, v in table.items():
        if isinstance(v, dict) and "byteOffset" in v:
            k = WIDTH[v["type"]]
            attrs[key] = np.frombuffer(binary, COMPONENT[v["componentType"]], n * k, v["byteOffset"]).reshape(n, k)[:, 0]
        else:
            attrs[key] = v
    return n, attrs, f[o + btj + btb:]


def read_glb(glb: bytes):
    """Triangles of every primitive as Earth-centred positions, their batch ids and indices."""
    jl = struct.unpack("<I", glb[12:16])[0]
    gltf = json.loads(glb[20:20 + jl])
    bl = struct.unpack("<I", glb[20 + jl:24 + jl])[0]
    binary = glb[28 + jl:28 + jl + bl]

    def accessor(i):
        a = gltf["accessors"][i]
        view = gltf["bufferViews"][a["bufferView"]]
        k, dtype = WIDTH[a["type"]], np.dtype(COMPONENT[a["componentType"]])
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", 0) or k * dtype.itemsize
        raw = np.frombuffer(binary, np.uint8, (a["count"] - 1) * stride + k * dtype.itemsize, start)
        rows = np.lib.stride_tricks.as_strided(raw, (a["count"], k * dtype.itemsize), (stride, 1))
        return np.ascontiguousarray(rows).view(dtype).reshape(a["count"], k)

    center = np.array(gltf.get("extensions", {}).get("CESIUM_RTC", {}).get("center", [0, 0, 0]), float)
    out = []
    for node in gltf.get("nodes", []):
        if "mesh" not in node:
            continue
        m = np.array(node.get("matrix", np.eye(4).ravel()), float).reshape(4, 4).T
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            pos = accessor(prim["attributes"]["POSITION"]).astype(float)
            pos = pos @ m[:3, :3].T + m[:3, 3]
            # 3D Tiles glTF is y-up: rotate to the z-up Earth frame, then add the tile centre.
            pos = np.c_[pos[:, 0], -pos[:, 2], pos[:, 1]] + center
            batch = accessor(prim["attributes"]["_BATCHID"])[:, 0].astype(np.int64)
            idx = accessor(prim["indices"])[:, 0].astype(np.int64) if "indices" in prim else np.arange(len(pos))
            out.append((pos, batch, idx.reshape(-1, 3)))
    return out


def text(v):
    return v.strip() if isinstance(v, str) else ""


def name_of(v):
    # A few buildings carry their gml id as 名称.
    v = text(v)
    return "" if v.startswith("BLD_") else v


def number(v, digits=1):
    if v is None:
        return None
    v = float(v)
    return None if not np.isfinite(v) or v < 0 else round(v, digits)


def buildings_of(tile: Path, origin, rot):
    n, attrs, glb = read_b3dm(tile)
    tris = defaultdict(list)
    for pos, batch, faces in read_glb(glb):
        local = (pos - origin) @ rot.T  # east, north, up
        owner = batch[faces[:, 0]]
        order = np.argsort(owner, kind="stable")
        ids, starts = np.unique(owner[order], return_index=True)
        for b, group in zip(ids, np.split(order, starts[1:])):
            tris[int(b)].append(local[faces[group]].reshape(-1, 3))
    for b, parts in tris.items():
        if not 0 <= b < n:
            continue
        corners = np.concatenate(parts)
        verts, faces = np.unique(np.round(corners, 2), axis=0, return_inverse=True)
        faces = faces.reshape(-1, 3)
        faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
        if not len(faces):
            continue
        cx, cy = (verts[:, 0].min() + verts[:, 0].max()) / 2, (verts[:, 1].min() + verts[:, 1].max()) / 2
        base = verts[:, 2].min()
        three = np.c_[verts[:, 0] - cx, verts[:, 2] - base, -(verts[:, 1] - cy)].astype(np.float32)
        get = lambda k: attrs[k][b] if k in attrs else None
        flood, river = None, ""
        for key in attrs:
            depth = number(get(key), 2) if key.endswith(FLOOD_DEPTH) else None
            if depth and (flood is None or depth > flood):
                flood, river = depth, key[:-len(FLOOD_DEPTH)]
        hours = [number(get(k), 0) for k in attrs if k.endswith(FLOOD_HOURS)]
        yield dict(
            flood=flood, river=river, flood_hours=max((h for h in hours if h), default=None),
            fire=text(get("防火及び準防火地域")), height_district=text(get("高度地区")),
            district_plan=text(get("地区計画")), landslide=text(get("土砂災害警戒区域")),
            gml=text(get("_gml_id")), bldg=text(get("建物ID")), name=name_of(get("名称")), usage_ja=text(get("用途")),
            structure_ja=text(get("建物構造")), address=text(get("住所")),
            height=number(get("計測高さ")) or round(float(three[:, 1].max()), 1),
            floors=int(get("地上階数") or 0), basements=int(get("地下階数") or 0),
            area=number(get("建物利用現況_図上面積"), 0), lod=int(get("_lod") or 1),
            x=round(float(cx), 1), z=round(float(-cy), 1), verts=three, faces=faces.astype(np.uint32),
        )


def main(only=()):
    origin, rot = enu_frame(*ORIGIN)
    fetched = [c for c in WARDS if (RAW / f"{c}_{WARDS[c][0]}_notexture" / "tileset.json").exists()
               and (not only or c in only)]
    if not fetched:
        raise SystemExit("no wards in data/tokyo: run pipeline.tokyo_s00_fetch first")
    seen, rows = set(), []
    for code in fetched:
        tiles = sorted((RAW / f"{code}_{WARDS[code][0]}_notexture").rglob("*.b3dm"))
        count = 0
        for tile in tiles:
            for b in buildings_of(tile, origin, rot):
                if b["gml"] in seen:
                    continue
                # A building on a ward border can sit in the neighbour's tiles; its id names its own ward.
                ward, _, number = b["bldg"].partition("-bldg-")
                if ward not in WARDS or not number.isdigit():
                    raise ValueError(f"unexpected building id {b['bldg']!r} in {tile}")
                seen.add(b["gml"]); b["ward"] = ward; rows.append(b); count += 1
        print(WARDS[code][1], count, "buildings from", len(tiles), "tiles")
    wards = sorted({b["ward"] for b in rows})

    cells = defaultdict(list)
    for i, b in enumerate(rows):
        cells[(int(np.floor(b["x"] / CELL)), int(np.floor(b["z"] / CELL)))].append(i)
    (OUT / "cells").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "cells").glob("*.bin"):
        old.unlink()
    keys = sorted(cells)
    cell_of, slot_of = np.zeros(len(rows), int), np.zeros(len(rows), int)
    for ci, key in enumerate(keys):
        members = cells[key]
        for s, i in enumerate(members):
            cell_of[i], slot_of[i] = ci, s
        bs = [rows[i] for i in members]
        head = np.array([len(bs)] + [len(b["verts"]) for b in bs] + [b["faces"].size for b in bs], np.uint32)
        body = [head.tobytes()] + [b["verts"].tobytes() for b in bs] + [b["faces"].tobytes() for b in bs]
        (OUT / "cells" / f"{key[0]}_{key[1]}.bin").write_bytes(b"".join(body))

    def codes(values):
        table = sorted(set(values) - {""})
        lookup = {v: i + 1 for i, v in enumerate(table)}
        return [""] + table, [lookup.get(v, 0) for v in values]

    usages, usage = codes([b["usage_ja"] for b in rows])
    structures, structure = codes([b["structure_ja"] for b in rows])
    addresses, address = codes([b["address"] for b in rows])
    rivers, river = codes([b["river"] for b in rows])
    fires, fire = codes([b["fire"] for b in rows])
    height_districts, height_district = codes([b["height_district"] for b in rows])
    district_plans, district_plan = codes([b["district_plan"] for b in rows])
    landslides, landslide = codes([b["landslide"] for b in rows])
    index = dict(
        source="3D都市モデル（Project PLATEAU）東京都23区（2020年度）国土交通省",
        origin=ORIGIN[:2], cell=CELL, cells=[f"{i}_{j}" for i, j in keys],
        wards=[[c, WARDS[c][1], WARDS[c][2]] for c in wards],
        usages=[[u, USAGE.get(u, u)] for u in usages],
        structures=[[s, STRUCTURE.get(s, s)] for s in structures],
        addresses=addresses,
        rivers=[[r, RIVERS.get(r, r)] for r in rivers], fires=[[f, FIRE.get(f, f)] for f in fires],
        heightDistricts=[[h, HEIGHT_DISTRICT.get(h, h)] for h in height_districts],
        districtPlans=district_plans, landslides=[[l, LANDSLIDE.get(l, l)] for l in landslides],
        columns=dict(
            bldg=[int(b["bldg"].rsplit("-", 1)[1]) for b in rows], name=[b["name"] for b in rows],
            ward=[wards.index(b["ward"]) for b in rows], usage=usage, structure=structure, address=address,
            height=[b["height"] for b in rows], floors=[b["floors"] for b in rows],
            basements=[b["basements"] for b in rows], area=[b["area"] for b in rows],
            lod=[b["lod"] for b in rows], x=[b["x"] for b in rows], z=[b["z"] for b in rows],
            cell=cell_of.tolist(), slot=slot_of.tolist(),
            flood=[b["flood"] for b in rows], floodHours=[b["flood_hours"] for b in rows], river=river,
            fire=fire, heightDistrict=height_district, districtPlan=district_plan, landslide=landslide,
        ),
    )
    (OUT / "buildings.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    size = sum(p.stat().st_size for p in (OUT / "cells").glob("*.bin"))
    print(f"{len(rows)} buildings, {sum(1 for b in rows if b['name'])} named, "
          f"{sum(1 for b in rows if b['lod'] >= 2)} LOD2, {sum(1 for b in rows if b['flood'])} in a flood zone, "
          f"{len(keys)} cells, {size / 1e6:.1f} MB of geometry")


if __name__ == "__main__":
    main(sys.argv[1:])
