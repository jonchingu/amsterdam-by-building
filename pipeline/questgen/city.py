"""The building directory the quest builder sources from: what the pipeline already knows, one row per checkpoint.

A checkpoint is a building, or all the buildings of one Wikidata item (the Rijksmuseum is several BAG panden), as
s13 resolves a `wd:` step. Its columns:

  key, bags            item key and its BAG ids (16 digits); `primary` is the tallest of them
  x, z                 centre in the app's local frame (metres from the Dam, x east, z south)
  year, date_flag      the map's year (s02_attributes) and how sure it is; `exact` for BAG as recorded, an RCE year
                       or a Wikidata inception (flags 0, 3, 5): only those years are ever told to the player
  period               index into periods.PERIODS
  height, floors, area metres to the roof (70th percentile, as the map draws it), storeys, footprint m²
  prominence           height over the median of its 12 nearest neighbours: how it stands out from the air
  monument             a national or municipal monument (RCE link or the heritage layer)
  name_en, name_nl     Wikidata labels (s06_wiki), or None
  image                the Commons photo the card shows (s06_wiki, s10_commons), or None
  wiki_url             the Wikipedia article, or None
  architects, styles   Wikidata's lists
  fact                 the checked 'Did you know' (s11_facts): {en, nl, source}, or None
  stories              layer notes in both languages (s05_layers): [{en, nl, source, layer}]
  g:<layer>:<group>    one boolean column per context-layer group (s05_layers), e.g. g:styles:as

Every file but the buildings is optional: a missing one leaves its columns empty, and a theme that needs it finds
nothing.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from ..quest_routes import DAM

EXACT_FLAGS = (0, 3, 5)  # s02_attributes: exact, monument (RCE year), Wikidata inception


class City:
    def __init__(self, df, catalogue=(), bag_years=None, heights=None, heights_fn=None):
        self.df = df
        self.catalogue = list(catalogue)
        self.bag_years = bag_years if bag_years is not None else {}
        self._heights, self._heights_fn = heights, heights_fn
        self.layers = {L["id"]: L for L in self.catalogue}

    @property
    def heights(self):
        """quest_routes.Heights of every building part, loaded on first use (the route planner needs it)."""
        if self._heights is None:
            if self._heights_fn is None:
                raise RuntimeError("this city has no building heights")
            self._heights = self._heights_fn()
        return self._heights

    def group_label(self, col):
        """{en, nl} label of a g:<layer>:<group> column, from the layer catalogue."""
        _, layer, group = col.split(":", 2)
        g = next((g for g in self.layers.get(layer, {}).get("groups", []) if g["key"] == group), None)
        return dict(en=g["label"], nl=g.get("label_nl") or g["label"]) if g else None

    def layer_source(self, col):
        _, layer, _ = col.split(":", 2)
        return (self.layers.get(layer, {}).get("source") or {}).get("url")

    def groups(self):
        return [c for c in self.df.columns if c.startswith("g:")]

    # ---------- loading ----------
    @classmethod
    def load(cls, root="."):
        """The directory from the pipeline's outputs under root (data/ and web/data/)."""
        import geopandas as gpd

        from ..quest_routes import load_heights

        root = Path(root)
        opt = lambda p: (root / p) if (root / p).exists() else None
        b = gpd.read_parquet(root / "data/buildings.parquet",
                             columns=["identificatie", "year", "date_flag", "height", "floors", "monument", "geometry"])
        bits = pd.read_parquet(opt("data/layers.parquet")) if opt("data/layers.parquet") else None
        catalogue = json.loads(opt("web/data/layers.json").read_text()) if opt("web/data/layers.json") else []
        wiki = json.loads(opt("web/data/wiki.json").read_text()) if opt("web/data/wiki.json") else []
        index = {}
        if opt("data/wiki_index.parquet"):
            w = pd.read_parquet(root / "data/wiki_index.parquet")
            index = dict(zip(w.bag, w.wk))
        facts = json.loads(opt("web/data/facts.json").read_text()) if opt("web/data/facts.json") else {}
        heights_fn = lambda: load_heights(root / "data/buildings.parquet", root / "data/parts.parquet")
        return cls.from_frames(b, bits, catalogue, wiki, index, facts, heights_fn=heights_fn)

    @classmethod
    def from_frames(cls, buildings, bits=None, catalogue=(), wiki=(), wiki_index=None, facts=None, heights=None,
                    heights_fn=None):
        """The directory from in-memory frames shaped as the pipeline's files (see load)."""
        b = pd.DataFrame(buildings.drop(columns="geometry"))
        b["bag"] = b.identificatie.str.slice(-16)
        geom = buildings.geometry.values
        c = shapely.centroid(geom)
        b["x"], b["z"] = shapely.get_x(c) - DAM[0], -(shapely.get_y(c) - DAM[1])
        b["area"] = shapely.area(geom)
        b["year"] = b.year.astype(int)
        b["exact"] = b.date_flag.isin(EXACT_FLAGS)
        from ..periods import period_index
        b["period"] = b.year.map(period_index)
        b["height"] = b.height.astype(float)
        b["floors"] = b.floors.fillna(0).astype(int) if "floors" in b else 0
        mon = b.monument.fillna("").astype(str) != "" if "monument" in b else pd.Series(False, index=b.index)

        # How it stands out from the air: its height over its neighbours'.
        xz = b[["x", "z"]].to_numpy()
        k = min(13, len(b))
        _, nn = cKDTree(xz).query(xz, k=k)
        nh = np.median(b.height.to_numpy()[nn[:, 1:]], axis=1) if k > 1 else b.height.to_numpy()
        b["prominence"] = b.height / np.maximum(nh, 3.0)

        # Context layers: a column per group.
        catalogue = list(catalogue)
        cols = {}
        if bits is not None and len(catalogue):
            m = b[["identificatie"]].merge(bits, on="identificatie", how="left").fillna(0)
            lay = (m.lay1.astype(np.uint64).to_numpy() << np.uint64(32)) | m.lay0.astype(np.uint64).to_numpy()
            for L in catalogue:
                for g in L.get("groups", []):
                    cols[f"g:{L['id']}:{g['key']}"] = (lay >> np.uint64(g["bit"])) & np.uint64(1) == 1
        groups = pd.DataFrame(cols, index=b.index)
        if "g:heritage:Rijksmonument" in groups or "g:heritage:Gemeentelijk monument" in groups:
            mon |= groups.filter(like="g:heritage:").any(axis=1)
        b["monument"] = mon
        stories = {}
        for L in catalogue:
            src = (L.get("source") or {}).get("url")
            for bag, n in (L.get("notes") or {}).items():
                if n.get("story") and n.get("story_nl"):
                    stories.setdefault(bag, []).append(dict(en=n["story"], nl=n["story_nl"],
                                                            source=n.get("source") or src, layer=L["id"]))
        b["stories"] = b.bag.map(lambda x: stories.get(x, []))

        # Wikidata: names, photos, articles. All the buildings of one item become one checkpoint.
        wiki, index, facts = list(wiki), dict(wiki_index or {}), dict(facts or {})
        wk = b.bag.map(index)
        entry = wk.map(lambda i: wiki[int(i)] if pd.notna(i) and int(i) < len(wiki) else {})
        b["name_en"] = entry.map(lambda e: e.get("label"))
        b["name_nl"] = entry.map(lambda e: e.get("label_nl") or e.get("label"))
        b["image"] = entry.map(lambda e: e.get("image") if (e.get("image") or {}).get("thumb") else None)
        b["wiki_url"] = entry.map(lambda e: (e.get("wiki") or e.get("wiki_nl") or {}).get("url"))
        b["architects"] = entry.map(lambda e: list(e.get("architects") or []))
        b["styles"] = entry.map(lambda e: list(e.get("styles") or []))
        b["fact"] = b.bag.map(lambda x: facts.get(x))
        # Only a named item groups its buildings: Commons photos found by address are one building each.
        b["key"] = np.where(b.name_en.notna() & wk.notna(), "wk" + wk.fillna(-1).astype(int).astype(str), b.bag)
        b = pd.concat([b, groups], axis=1)
        bag_years = dict(zip(b.bag, b.year))
        return cls(_items(b, list(cols)), catalogue, bag_years, heights, heights_fn)


def _items(b, gcols):
    """One row per checkpoint: a Wikidata item's buildings are merged, its tallest building speaks for it."""
    b = b.sort_values(["key", "height", "bag"], ascending=[True, False, True])
    dup = b.key.duplicated(keep=False)
    single, multi = b[~dup].copy(), b[dup]
    single["bags"] = single.bag.map(lambda x: (x,))
    rows = []
    for key, g in multi.groupby("key", sort=True):
        r = g.iloc[0].copy()
        w = g.area.to_numpy()
        r["bags"] = tuple(sorted(g.bag))
        r["x"], r["z"] = float(np.average(g.x, weights=w)), float(np.average(g.z, weights=w))
        r["area"], r["height"] = float(w.sum()), float(g.height.max())
        r["prominence"], r["monument"] = float(g.prominence.max()), bool(g.monument.any())
        r["fact"] = next((f for f in g.fact if f), None)
        seen, st = set(), []
        for s in (s for ss in g.stories for s in ss):
            if s["en"] not in seen:
                seen.add(s["en"])
                st.append(s)
        r["stories"] = st
        for c in gcols:
            r[c] = bool(g[c].any())
        rows.append(r)
    df = pd.concat([single, pd.DataFrame(rows)], ignore_index=True) if rows else single.reset_index(drop=True)
    df = df.rename(columns={"bag": "primary"})
    keep = ["key", "bags", "primary", "x", "z", "year", "date_flag", "exact", "period", "height", "floors", "area",
            "prominence", "monument", "name_en", "name_nl", "image", "wiki_url", "architects", "styles", "fact",
            "stories"] + gcols
    df = df[keep].sort_values("key").reset_index(drop=True)
    df["monument"] = df.monument.astype(bool)
    # None, never NaN, for what is missing: NaN is truthy.
    for col, ok in (("image", dict), ("fact", dict), ("wiki_url", str), ("name_en", str), ("name_nl", str)):
        df[col] = pd.Series([v if isinstance(v, ok) else None for v in df[col]], index=df.index, dtype=object)
    for col in ("architects", "styles", "stories"):
        df[col] = pd.Series([v if isinstance(v, list) else [] for v in df[col]], index=df.index, dtype=object)
    for c in gcols:
        df[c] = df[c].astype(bool)
    return df
