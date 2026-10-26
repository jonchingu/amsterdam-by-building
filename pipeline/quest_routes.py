"""Flyover routes for the quests: the camera path the app flies through a quest's buildings (web/app.js, 'Quest flyovers').

A route is a list of anchors in the app's local frame (metres from the Dam, x east, y up from the street, z south):
  {p: [x, y, z], yaw, pitch, zoom, hold, speed, target?: [x, y, z], step?: k}
yaw is degrees clockwise from north, pitch degrees above the horizon (negative looks down), zoom the lens (1 = the
app's 35° field of view, 2 = half as wide), hold the seconds the camera rests there, speed the cruise speed in m/s to
the next anchor. An anchor with a target keeps that point in the middle of the frame; `step` marks the anchor that
frames step k's building. The app flies a centripetal Catmull-Rom curve through the anchors (three.js
CatmullRomCurve3), so `curve_points` below is a port of that curve: the checks here test the path the app flies.

Planning, per quest: an opening view over all its buildings; for each step a framing of its building(s), from the
direction with a clear line of sight that best continues the flight and shows the sunlit (south-west) faces; between
buildings far apart, two transit points at a cruise height over everything in the corridor; the opening view again
at the end. Every leg is then sampled every 1.5 m against the building heights: a sample that passes within CLEAR
metres of a roof or wall is a clip. A clipping leg is bent sideways or lifted with extra anchors until it is clear;
a route that still clips fails the build.
Everything is deterministic: no randomness, fixed candidate order, rounded output.
"""
import math

import numpy as np
import shapely

FOV = 35.0         # the app camera's vertical field of view at zoom 1, degrees
CLEAR = 8.0        # metres the camera keeps from any roof or wall (the app's near plane is 5 m)
STEP = 1.5         # metres between samples along a leg
SUN = 222.0        # compass bearing of the light in the app's shader: faces seen from here are lit
HOLD = 2.5         # seconds on each step's building
DAM = (121390.0, 487380.0)  # RD New; the local frame's origin (s03_tiles.DAM)


# ---------- Heights ----------
class Heights:
    """Building parts in the local frame with their top above the street, for 'how tall is it around here?'."""

    def __init__(self, geoms, tops, owners):
        self.geoms = np.asarray(geoms)
        self.tops = np.asarray(tops, dtype=float)
        self.owners = np.asarray(owners)           # BAG id (16 digits) of each part's building
        self.tree = shapely.STRtree(self.geoms)
        self.by_bag = {}
        for i, b in enumerate(self.owners):
            self.by_bag.setdefault(b, []).append(i)

    def around(self, xz, r, ignore=()):
        """Highest top within r metres of each point (N, 2); 0 where there is nothing. Parts in `ignore` don't count."""
        xz = np.atleast_2d(np.asarray(xz, dtype=float))
        out = np.zeros(len(xz))
        if not len(xz):
            return out
        ip, ig = self.tree.query(shapely.points(xz), predicate="dwithin", distance=r)
        if len(ignore):
            keep = ~np.isin(ig, np.fromiter(ignore, int))
            ip, ig = ip[keep], ig[keep]
        np.maximum.at(out, ip, self.tops[ig])
        return out

    def building(self, bags):
        """Centre, top, size and part indices of one step's building(s)."""
        idx = [i for b in bags for i in self.by_bag.get(b, [])]
        if not idx:
            raise ValueError(f"no parts for {bags}")
        x0, z0, x1, z1 = shapely.total_bounds(self.geoms[idx])
        # The app aims at the mean of the buildings' centres (app.js centre()); the parts' centroid is close to that.
        c = shapely.centroid(shapely.union_all(self.geoms[idx]))
        return dict(x=c.x, z=c.y, top=float(self.tops[idx].max()), size=float(max(x1 - x0, z1 - z0)), parts=idx)


def load_heights(buildings="data/buildings.parquet", parts="data/parts.parquet"):
    """The 3D BAG LoD 1.3 parts (s01_load), each with its highest point above its building's ground level.

    The map draws a part at its 70th-percentile roof height; the camera keeps clear of the highest point instead,
    so a spire or a roof ridge is not grazed. Parts with impossible heights are repaired as the map repairs them.
    """
    import geopandas as gpd
    import pandas as pd

    b = pd.read_parquet(buildings, columns=["identificatie", "b3_h_maaiveld"])
    q = gpd.read_parquet(parts, columns=["identificatie", "b3_h_min", "b3_h_50p", "b3_h_70p", "b3_h_max", "geometry"])
    return heights_from(b, q)


def heights_from(b, q):
    """Heights from frames shaped as data/buildings.parquet (identificatie, b3_h_maaiveld) and data/parts.parquet."""
    from .s02_attributes import clean_parts

    q = clean_parts(q.copy())
    q = q[q.identificatie.isin(b.identificatie)]
    ground = q.identificatie.map(dict(zip(b.identificatie, b.b3_h_maaiveld)))
    broken = (q.b3_h_max > 400) | (q.b3_h_min < -100)
    top = (q.b3_h_max.where(~broken, q.b3_h_70p) - ground).clip(lower=2.5).fillna(2.5)
    geoms = shapely.transform(q.geometry.values, lambda c: np.c_[c[:, 0] - DAM[0], -(c[:, 1] - DAM[1])])
    return Heights(geoms, top.to_numpy(), q.identificatie.str.slice(-16).to_numpy())


# ---------- The curve the app flies (three.js CatmullRomCurve3, centripetal, open) ----------
def curve_points(P, u):
    """Points at curve parameters u in [0, 1] through anchor positions P (n, 3), as CatmullRomCurve3.getPoint."""
    P = np.asarray(P, dtype=float)
    n = len(P)
    u = np.atleast_1d(np.asarray(u, dtype=float))
    p = (n - 1) * u
    i = np.floor(p).astype(int)
    w = p - i
    end = (w == 0) & (i == n - 1)
    i[end] = n - 2
    w[end] = 1.0
    i = np.clip(i, 0, n - 2)
    first, last = 2 * P[0] - P[1], 2 * P[-1] - P[-2]
    p0 = np.where((i > 0)[:, None], P[np.maximum(i - 1, 0)], first)
    p1, p2 = P[i], P[i + 1]
    p3 = np.where((i + 2 < n)[:, None], P[np.minimum(i + 2, n - 1)], last)
    d = lambda a, b: np.sum((a - b) ** 2, axis=1) ** 0.25
    dt0, dt1, dt2 = d(p0, p1), d(p1, p2), d(p2, p3)
    dt1 = np.where(dt1 < 1e-4, 1.0, dt1)
    dt0 = np.where(dt0 < 1e-4, dt1, dt0)
    dt2 = np.where(dt2 < 1e-4, dt1, dt2)
    dt0, dt1, dt2 = dt0[:, None], dt1[:, None], dt2[:, None]
    t1 = ((p1 - p0) / dt0 - (p2 - p0) / (dt0 + dt1) + (p2 - p1) / dt1) * dt1
    t2 = ((p2 - p1) / dt1 - (p3 - p1) / (dt1 + dt2) + (p3 - p2) / dt2) * dt1
    c2 = -3 * p1 + 3 * p2 - 2 * t1 - t2
    c3 = 2 * p1 - 2 * p2 + t1 + t2
    w = w[:, None]
    return p1 + t1 * w + c2 * w ** 2 + c3 * w ** 3


def leg_samples(P, leg):
    """Samples along one leg, about STEP metres apart, both ends included."""
    n = len(P)
    rough = curve_points(P, (leg + np.linspace(0, 1, 33)) / (n - 1))
    L = float(np.sum(np.linalg.norm(np.diff(rough, axis=0), axis=1)))
    k = max(2, math.ceil(L / STEP))
    return curve_points(P, (leg + np.linspace(0, 1, k + 1)) / (n - 1)), L


def clips(anchors, H):
    """Every leg that passes through or too close to a building: [(leg, samples (k, 3), clipped mask)]."""
    P = [a["p"] for a in anchors]
    bad = []
    for leg in range(len(P) - 1):
        q, _ = leg_samples(P, leg)
        hit = (q[:, 1] - CLEAR < H.around(q[:, [0, 2]], CLEAR)) | (q[:, 1] < CLEAR)
        if hit.any():
            bad.append((leg, q, hit))
    return bad


# ---------- Anchors ----------
def look(frm, to):
    d = np.subtract(to, frm)
    return (math.degrees(math.atan2(d[0], -d[2])) % 360, math.degrees(math.atan2(d[1], math.hypot(d[0], d[2]))))


def r1(v):
    return round(float(v), 1)


def anchor(p, aim, zoom=1.0, hold=0.0, step=None, target=None, max_pitch=-8.0):
    """An anchor at p looking at aim. Pitch stays below the horizon, so the app's map controls can take over."""
    yaw, pitch = look(p, aim)
    a = dict(p=[r1(v) for v in p], yaw=r1(yaw), pitch=r1(min(max_pitch, max(-80.0, pitch))), zoom=round(zoom, 2),
             hold=hold, speed=0.0)
    if target is not None:
        a["target"] = [r1(v) for v in target]
    if step is not None:
        a["step"] = step
    return a


def angdiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def frame(bld, came_from, H):
    """The camera for one step: where it stands, its lens and what it aims at."""
    T = np.array([bld["x"], bld["top"] * 0.55, bld["z"]])
    S = max(bld["size"], bld["top"], 12.0)
    # The building fills about 45% of the frame's height: at zoom 1 that takes 3.5 times its size. Stand at least
    # 160 m off and close the lens instead, up to 1.8×; very large buildings are framed from up to 650 m.
    need = S / (0.45 * 2 * math.tan(math.radians(FOV / 2)))
    D = min(650.0, max(160.0, need))
    zoom = min(1.8, max(1.0, D / need))
    approach = look(T, came_from)[0] if came_from is not None else SUN
    ignore = set(bld["parts"])
    best = None
    for k, el in enumerate((30.0, 40.0, 52.0)):
        for az in np.arange(0, 360, 15.0):
            a, e = math.radians(az), math.radians(el)
            C = T + D * np.array([math.sin(a) * math.cos(e), math.sin(e), -math.cos(a) * math.cos(e)])
            if C[1] - CLEAR < H.around(C[[0, 2]], CLEAR + 4)[0]:
                continue
            # Line of sight: the camera must see the aim point over everything but the building itself.
            f = np.linspace(0.02, 0.98, 48)[:, None]
            ray = C + (T - C) * f
            blocked = float(np.mean(ray[:, 1] < H.around(ray[:, [0, 2]], 1.0, ignore)))
            score = (blocked * 10 + angdiff(az, approach) / 180 * 1.2 + angdiff(az, SUN) / 180 * 0.8 + k * 0.25)
            if best is None or score < best[0] - 1e-9:
                best = (score, C)
    if best is None:
        raise RuntimeError(f"no clear viewpoint for the building at {bld['x']:.0f}, {bld['z']:.0f}")
    return anchor(best[1], T, zoom=zoom, hold=HOLD, target=T)


def overview(blds):
    """High over every building of the quest, from the south-west, as the app's own quest overview."""
    xs, zs = [b["x"] for b in blds], [b["z"] for b in blds]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    d = min(3500.0, max(700.0, math.hypot(max(xs) - min(xs), max(zs) - min(zs)) * 1.3))
    a, e = math.radians(SUN), math.radians(50)
    C = np.array([cx + d * math.sin(a) * math.cos(e), d * math.sin(e), cz - d * math.cos(a) * math.cos(e)])
    return anchor(C, (cx, 0.0, cz), hold=1.0)


def transit(A, B, H):
    """Two raised points between framings far apart: climb out, cruise over everything in the corridor, descend.

    The cruise height grows with the hop (60 m plus 18% of its length, up to 450 m) and clears the tallest roof
    within 2 × CLEAR of the straight line by 2 × CLEAR. Both points look ahead to the next building.
    """
    pa, pb = np.array(A["p"]), np.array(B["p"])
    d = math.hypot(*(pb - pa)[[0, 2]])
    line = pa[[0, 2]] + (pb - pa)[[0, 2]] * np.linspace(0, 1, max(2, int(d / 5)))[:, None]
    y = max(pa[1], pb[1], min(450.0, 60 + 0.18 * d), H.around(line, 2 * CLEAR).max() + 2 * CLEAR)
    out = []
    for f in (0.3, 0.7):
        c = pa + (pb - pa) * f
        c[1] = y
        out.append(anchor(c, B.get("target", pb), max_pitch=-10.0))
    return out


def timing(anchors):
    """Cruise speed per leg: a short hop takes a few seconds, a long transit up to eight; bends add a little."""
    P = [a["p"] for a in anchors]
    for i in range(len(anchors) - 1):
        _, L = leg_samples(P, i)
        T = min(8.0, max(2.5, 2.2 + L / 140))
        anchors[i]["speed"] = r1(max(4.0, L / T))
    anchors[-1]["speed"] = 0.0
    anchors[-1]["hold"] = 2.0


def detour(anchors, leg, q, hit, H):
    """Ways round or over the first obstacle on a clipping leg, best first: each is a list of anchors to insert.

    Bends go sideways from the middle of the blocked stretch, a little at first, then further. A lift raises the
    leg CLEAR × 2 over the obstacle with a pair of anchors, one before it and one after, so the climb itself
    clears it too.
    """
    run = np.flatnonzero(hit)
    j0 = j1 = run[0]
    while j1 + 1 < len(q) and hit[j1 + 1]:
        j1 += 1
    mid = q[(j0 + j1) // 2]
    d = q[min(j1 + 1, len(q) - 1)] - q[max(j0 - 1, 0)]
    side = np.array([-d[2], 0.0, d[0]])
    side = side / (np.linalg.norm(side) or 1)
    nxt = next((a["target"] for a in anchors[leg + 1:] if "target" in a), anchors[-1]["p"])
    back = int(40 / STEP)
    a, b = q[max(0, j0 - back)].copy(), q[min(len(q) - 1, j1 + back)].copy()
    top = H.around(q[j0:j1 + 1, [0, 2]], 2 * CLEAR).max() + 2 * CLEAR
    a[1], b[1] = max(a[1], top), max(b[1], top)
    bends = lambda ss: [[mid + side * x] for s in ss for x in (s, -s)]
    out = bends((30, 60)) + [[a, b]] + bends((100, 160, 240))
    return [[anchor(c, nxt, max_pitch=-10.0) for c in cs] for cs in out]


def plan(steps, H, max_fixes=24):
    """The route through a quest's steps (each a list of BAG ids). Raises if a leg can't be made clear."""
    blds = [H.building(bags) for bags in steps]
    start = overview(blds)
    anchors, prev = [start], start["p"]
    for k, b in enumerate(blds):
        a = frame(b, prev, H)
        a["step"] = k
        last = anchors[-1]
        if math.hypot(a["p"][0] - last["p"][0], a["p"][2] - last["p"][2]) > 350 and last is not start:
            anchors += transit(last, a, H)
        anchors.append(a)
        prev = a["p"]
    end = dict(start, p=list(start["p"]))
    anchors.append(end)
    # Clear the legs one obstacle at a time; every fix must lower the number of clipped samples.
    bad = clips(anchors, H)
    for _ in range(max_fixes):
        if not bad:
            break
        leg, q, hit = bad[0]
        now = sum(int(m.sum()) for _, _, m in bad)
        best = None
        for cs in detour(anchors, leg, q, hit, H):
            trial = anchors[:leg + 1] + cs + anchors[leg + 1:]
            tb = clips(trial, H)
            n = sum(int(m.sum()) for _, _, m in tb)
            if n < now and (best is None or n < best[0]):
                best = (n, trial, tb)
        if best is None:
            break
        _, anchors, bad = best
    if bad:
        leg, q, hit = bad[0]
        x, y, z = q[np.argmax(hit)]
        raise RuntimeError(f"leg {leg + 1} still passes through a building near ({x:.0f}, {y:.0f}, {z:.0f})")
    timing(anchors)
    return anchors
