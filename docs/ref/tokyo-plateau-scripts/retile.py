"""b3dm (CESIUM_RTC, y-up glTF) -> plain GLB placed in a local frame (three.js: x=east, y=up, z=south).
Also writes per-tile building attributes for picking."""
import sys, json, struct, math, glob, os
sys.path.insert(0, os.path.dirname(__file__)); import b3dm
import numpy as np
a, f = 6378137.0, 1 / 298.257223563; e2 = f * (2 - f)
def ecef(lat, lon, h):
    la, lo = math.radians(lat), math.radians(lon); N = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return np.array([(N + h) * math.cos(la) * math.cos(lo), (N + h) * math.cos(la) * math.sin(lo), (N * (1 - e2) + h) * math.sin(la)])
LAT0, LON0, H0 = map(float, sys.argv[1:4]); src, dst = sys.argv[4], sys.argv[5]
la, lo = math.radians(LAT0), math.radians(LON0)
R = np.array([[-math.sin(lo), math.cos(lo), 0],
              [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
              [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)]])  # ECEF -> ENU
Y2Z = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])   # glTF (x,y,z) -> ECEF (x,-z,y)
E2T = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])   # ENU (e,n,u) -> three (e,u,-n)
O = ecef(LAT0, LON0, H0)
os.makedirs(dst, exist_ok=True)
meta = {}
for p in sys.argv[6:]:
    name = os.path.basename(p).replace(".b3dm", "")
    ft, bt, btbin, glb = b3dm.read(os.path.join(src, p))
    jl, = struct.unpack("<I", glb[12:16]); g = json.loads(glb[20:20 + jl]); rest = glb[20 + jl:]
    rtc = np.array(g["extensions"].pop("CESIUM_RTC")["center"])
    if not g["extensions"]: del g["extensions"]
    for k in ("extensionsUsed", "extensionsRequired"):
        g[k] = [x for x in g.get(k, []) if x != "CESIUM_RTC"]
    L = E2T @ R @ Y2Z; t = E2T @ R @ (rtc - O)
    M = np.eye(4); M[:3, :3] = L; M[:3, 3] = t
    assert len(g["nodes"]) == 1
    g["nodes"][0]["matrix"] = [float(x) for x in M.T.flatten()]  # column-major
    js = json.dumps(g, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    open(os.path.join(dst, name + ".glb"), "wb").write(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    n = ft["BATCH_LENGTH"]
    cols = {k: b3dm.bt_scalar(bt, btbin, k, n) for k in ("gml_id", "gml:name", "bldg:measuredHeight", "_lod", "bldg:storeysAboveGround", "bldg:usage")}
    meta[name] = [[cols["gml_id"][i], cols["gml:name"][i] if cols["gml:name"] else None,
                   (round(cols["bldg:measuredHeight"][i], 1) if cols["bldg:measuredHeight"][i] is not None else None) if cols["bldg:measuredHeight"] else None,
                   cols["_lod"][i], cols["bldg:storeysAboveGround"][i] if cols["bldg:storeysAboveGround"] else None,
                   cols["bldg:usage"][i] if cols["bldg:usage"] else None] for i in range(n)]
json.dump(meta, open(os.path.join(dst, "buildings.json"), "w"), ensure_ascii=False, separators=(",", ":"))
print("wrote", len(meta), "tiles")
