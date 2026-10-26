"""The fixture city (fixture_city.py) with what the quest builder sources from: context layers, Wikidata names and
photos, facts and stories. Made up, like the city; nothing here is about the real Amsterdam.

    uv run python tests/questgen_fixture.py /tmp/ams-qg          # write it, then:
    uv run python -m pipeline.questgen --root /tmp/ams-qg --list-themes

On top of the plain fixture: churches from 1306 to 2004 and a synagogue, post-war and new towers, and two Amsterdam
School public buildings, in empty courtyards; a 'canal ring' between the two strips of water with gabled and listed
houses, hofjes, and warehouses along the northern one; Amsterdam School blocks south of the southern water; post-war
houses with wall art and war damage; one in five houses with an estimated year. city() gives the same thing in
memory, for tests that need no files.
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
import fixture_city as fc  # noqa: E402
from pipeline.periods import period_index  # noqa: E402

# key: name, [(cx, cz, w, d, height)], year, architect, [(layer, group)] — each in a courtyard the plain fixture
# leaves empty. Churches and towers span the eras, so that themes with era roles have more than one candidate per role.
W, SYN, AS, LISTED = ("faith", "worship"), ("faith", "synagogue"), ("styles", "as"), ("heritage", "Rijksmonument")
EXTRA = {
    # churches, medieval to modern
    "church_old": ("Oudekerk (fixture)", [(0, -220, 22, 12, 22), (12, -220, 6, 6, 67)], 1306, None, [W, LISTED]),
    "church_new": ("Nieuwekerk (fixture)", [(70, -110, 22, 12, 24), (82, -110, 6, 6, 60)], 1408, None, [W, LISTED]),
    "chapel_a": ("Agnietenkapel (fixture)", [(-140, 55, 20, 12, 18)], 1470, None, [W, LISTED]),
    "church_n": ("Noorderkerk (fixture)", [(-280, -385, 22, 12, 20), (-268, -385, 6, 6, 55)], 1623,
                 "Hendrick de Keyser", [W, LISTED]),
    "church_e": ("Oosterkerk (fixture)", [(560, -55, 22, 12, 18), (572, -55, 6, 6, 48)], 1671, "Daniel Stalpaert",
                 [W, LISTED]),
    "synagogue": ("Synagogue (fixture)", [(420, 275, 24, 14, 22)], 1671, "Elias Bouman", [SYN, LISTED]),
    "church_am": ("Amstelkerk (fixture)", [(210, 220, 20, 12, 20)], 1770, None, [W, LISTED]),
    "church_mo": ("Mozeskerk (fixture)", [(350, 165, 22, 12, 22), (362, 165, 6, 6, 42)], 1841, None, [W]),
    "church_ph": ("Posthoornkerk (fixture)", [(-490, 165, 22, 12, 24), (-478, 165, 6, 6, 58)], 1863,
                  "Pierre Cuypers", [W]),
    "church_kb": ("Krijtbergkerk (fixture)", [(-420, -55, 22, 12, 22), (-408, -55, 6, 6, 50)], 1883,
                  "Alfred Tepe", [W]),
    "church_s": ("Zuiderkapel (fixture)", [(140, 330, 22, 12, 16), (152, 330, 6, 6, 40)], 1928, "Jan Gratama",
                 [W, AS]),
    "church_el": ("Elandskerk (fixture)", [(-630, 330, 22, 12, 18), (-618, 330, 6, 6, 45)], 1962, None, [W]),
    "church_kr": ("Kruiskerk (fixture)", [(630, 385, 20, 12, 25)], 2004, None, [W]),
    # towers, post-war to now
    "tower_a": ("Rivierentoren (fixture)", [(-700, 440, 14, 14, 90)], 1972, None, []),
    "tower_w": ("Flatgebouw West (fixture)", [(-770, -165, 14, 14, 65)], 1968, None, []),
    "tower_bj": ("Bijlmertoren (fixture)", [(490, 495, 14, 14, 70)], 1975, None, []),
    "tower_b": ("Zuidastoren (fixture)", [(700, -495, 14, 14, 120)], 2005, None, [("arcam", "won")]),
    "tower_c": ("Oevertoren (fixture)", [(-560, 550, 14, 14, 75)], 1999, None, []),
    "tower_d": ("Haventoren (fixture)", [(280, -550, 14, 14, 95)], 1985, None, []),
    "tower_ij": ("IJtoren (fixture)", [(-70, -495, 14, 14, 110)], 2012, None, [("arcam", "nominated")]),
    # Amsterdam School public buildings
    "as_school": ("Zuiderschool (fixture)", [(-350, 385, 24, 12, 16)], 1925, "Jan Frederik Staal", [AS]),
    "as_post": ("Postkantoor Zuid (fixture)", [(210, 440, 24, 12, 18)], 1919, "Piet Kramer", [AS]),
}
AS_ARCHITECTS = ["Michel de Klerk", "Piet Kramer", "Jan Gratama", "Jan Frederik Staal"]
WIKI = "https://nl.wikipedia.org/wiki/"
PHOTO = fc.PHOTO
CATALOGUE = [  # (layer id, title, source url, [(group key, label)])
    ("gables", "Gables", "https://monumentenregister.cultureelerfgoed.nl",
     [("trap", "Stepped gable"), ("hals", "Neck gable"), ("klok", "Bell gable"), ("lijst", "Cornice")]),
    ("trade", "Warehouses and the companies", "https://monumentenregister.cultureelerfgoed.nl",
     [("pakhuis", "Warehouse"), ("company", "VOC and WIC buildings")]),
    ("unesco", "The canal ring", "https://api.data.amsterdam.nl/v1/monumenten/unesco/",
     [("Kernzone", "World Heritage site"), ("Bufferzone", "Buffer zone")]),
    ("faith", "Faith and charity", "https://api.data.amsterdam.nl/v1/monumenten/monumenten/",
     [("worship", "Church"), ("synagogue", "Synagogue"), ("hofje", "Hofje")]),
    ("styles", "Architecture styles", "https://linkeddata.cultureelerfgoed.nl", [("as", "Amsterdam School")]),
    ("architects", "Architects", "https://maps.amsterdam.nl/open_geodata/", [("as", "Amsterdam School architects")]),
    ("housing", "Housing Act homes", "https://maps.amsterdam.nl/open_geodata/",
     [("woningwet", "Housing association, built 1901–1940")]),
    ("planned", "The planned city", "https://api.data.amsterdam.nl/v1/beschermdestadsdorpsgezichten/",
     [("Plan Zuid", "Plan Zuid"), ("Western garden cities", "Western garden cities")]),
    ("war", "Under fire, 1940–1945", "https://maps.amsterdam.nl/open_geodata/",
     [("bomb", "Bombs, shells and gunfire"), ("damage", "Damage nearby")]),
    ("noord1943", "The raid on Noord, 17 July 1943", "https://api.data.amsterdam.nl/v1/ontplofbare_oorlogsresten/",
     [("rebuilt", "Built after 1943"), ("stood", "Standing before 1943")]),
    ("wallart", "Art on the walls", "https://maps.amsterdam.nl/wandkunst/",
     [("top", "Of top value"), ("valuable", "Valuable")]),
    ("arcam", "Prize-winning architecture", "https://maps.amsterdam.nl/open_geodata/",
     [("won", "Winner"), ("nominated", "Nominated")]),
    ("heritage", "Protected heritage", "https://api.data.amsterdam.nl/v1/monumenten/monumenten/",
     [("Rijksmonument", "National monument"), ("Gemeentelijk monument", "Municipal monument")]),
]


def add_extra(b, q):
    """The extra buildings as rows of b and q, shaped as fixture_city.city() makes them. → (b, q, {key: bag})."""
    rows, parts, keys = [], [], {}
    n = len(b)
    for key, (_, ps, year, _, _) in EXTRA.items():
        bag = f"{363100000000000 + n:016d}"
        n += 1
        ident = f"NL.IMBAG.Pand.{bag}"
        geoms = [(fc.rect(cx, cz, w, d), h) for cx, cz, w, d, h in ps]
        top = max(h for _, h in geoms)
        rows.append(dict(identificatie=ident, oorspronkelijkbouwjaar=year, year=year, date_flag=0,
                         period=period_index(year), height=float(top), floors=max(1, round(top / 3.2)), floors_src=1,
                         monument=None, b3_h_maaiveld=0.5, geometry=shapely.union_all([g for g, _ in geoms]), key=key))
        for k, (g, h) in enumerate(geoms):
            parts.append(dict(identificatie=ident, b3_pand_deel_id=k, b3_dd_id=0, b3_h_min=0.5 + h * 0.6,
                              b3_h_50p=0.5 + h * 0.85, b3_h_70p=0.5 + h * 0.9, b3_h_max=0.5 + h, geometry=g))
        keys[key] = bag
    b = gpd.GeoDataFrame(pd.concat([b, gpd.GeoDataFrame(rows, crs=28992)], ignore_index=True), crs=28992)
    q = gpd.GeoDataFrame(pd.concat([q, gpd.GeoDataFrame(parts, crs=28992)], ignore_index=True), crs=28992)
    return b, q, keys


def attributes(b, landmarks, extra):
    """Layer groups, notes, names, photos and facts for the enriched fixture: the files s05, s06 and s11 write."""
    b = b.copy()
    bag = b.identificatie.str.slice(-16)
    c = b.geometry.centroid
    x, z = c.x - fc.DAM[0], -(c.y - fc.DAM[1])
    y = b.year
    house = b.key.isna() if "key" in b else pd.Series(True, index=b.index)
    house &= ~bag.isin(extra.values())
    idx = np.arange(len(b))

    # one house in five has an estimated year (s02's placeholders); the year is never told for those
    b.loc[house & (idx % 5 == 4), "date_flag"] = 2

    g = {}  # (layer, group) -> boolean mask
    ring = house & x.between(-500, 300) & z.between(-290, 240)
    g["unesco", "Kernzone"] = ring.copy()
    g["unesco", "Kernzone"][bag.isin([landmarks["church_w"], landmarks["church_z"], landmarks["tiny"]])] = True
    golden = ring & y.between(1600, 1700)
    g["gables", "trap"] = golden & (y < 1630)
    g["gables", "hals"] = golden & y.between(1630, 1669)
    g["gables", "klok"] = golden & (y >= 1670)
    north = house & z.between(-345, -255) & y.between(1600, 1900)
    g["trade", "pakhuis"] = north
    old_north = north & (y < 1700)
    company = list(bag[old_north].iloc[[3, 17]]) if old_north.sum() > 17 else []
    g["trade", "company"] = bag.isin(company)
    g["faith", "worship"] = bag.isin([landmarks["church_w"], landmarks["church_z"]])
    g["faith", "hofje"] = golden & (idx % 29 == 3)
    south = house & (z > 260) & x.between(-650, 650)
    g["styles", "as"] = south & y.between(1914, 1940)
    g["architects", "as"] = south & y.between(1914, 1940) & (idx % 3 == 0)
    g["housing", "woningwet"] = south & y.between(1901, 1940)
    g["planned", "Plan Zuid"] = house & (z > 260)
    g["planned", "Western garden cities"] = house & (x < -600)
    postwar = house & y.between(1945, 1975)
    g["war", "bomb"] = postwar & (x < -100) & (idx % 2 == 0)
    g["war", "damage"] = postwar & (x < -100) & (idx % 2 == 1)
    g["noord1943", "rebuilt"] = postwar & (x > 400) & (z < -300)
    art = postwar & (idx % 4 == 0)
    g["wallart", "top"] = art & (idx % 8 == 0)
    g["wallart", "valuable"] = art & (idx % 8 == 4)
    listed = (ring & (y < 1750)) | bag.isin([landmarks[k] for k in ("church_w", "church_z", "station", "museum")])
    g["heritage", "Rijksmonument"] = listed
    for key, (*_, groups) in EXTRA.items():
        for lg in groups:
            g[lg] = g.get(lg, pd.Series(False, index=b.index)) | (bag == extra[key])
    listed = g["heritage", "Rijksmonument"]
    b["monument"] = np.where(listed & (idx % 2 == 0), (100000 + idx).astype(str), None)

    catalogue, mask, bit = [], np.zeros(len(b), dtype=np.uint64), 0
    for lid, title, url, groups in CATALOGUE:
        gs = []
        for key, label in groups:
            m = g.get((lid, key), pd.Series(False, index=b.index)).to_numpy(bool)
            mask[m] |= np.uint64(1) << np.uint64(bit)
            gs.append(dict(key=key, label=label, label_nl=label, bit=bit, count=int(m.sum())))
            bit += 1
        catalogue.append(dict(id=lid, title=title, source=dict(label=title, url=url), groups=gs, notes={}))
    bits = pd.DataFrame(dict(identificatie=b.identificatie, lay0=(mask & np.uint64(0xFFFFFFFF)).astype(np.uint32),
                             lay1=(mask >> np.uint64(32)).astype(np.uint32)))
    wallart = next(L for L in catalogue if L["id"] == "wallart")
    for i in np.flatnonzero(art.to_numpy()):
        wallart["notes"][bag.iat[i]] = dict(story=f"“Fixture relief {i}”, a relief by A. Maker, {y.iat[i] + 2}.",
                                            story_nl=f"“Fixture relief {i}”, reliëf van A. Maker, {y.iat[i] + 2}.")

    # Wikidata items: the landmarks, the extras, and named houses (one Amsterdam School block spans two buildings)
    wiki, index, facts = [], {}, {}

    def item(bags_, label, architects=(), styles=(), photo=True, article=True):
        k = len(wiki)
        url = WIKI + label.replace(" ", "_") if article else None
        wiki.append(dict(label=label, label_nl=label, wiki=dict(lang="nl", url=url, extract=None) if url else None,
                         wiki_nl=None, architects=list(architects), styles=list(styles),
                         image=dict(thumb=PHOTO, page=url, artist="Fixture", license="CC0") if photo else None))
        for x_ in bags_:
            index[x_] = k
        return url

    for key, bg in landmarks.items():
        item([bg], fc.LANDMARKS[key][0], photo=key != "tiny")
    for key, bg in extra.items():
        name, _, _, arch, groups = EXTRA[key]
        item([bg], name, [arch] if arch else [], ["Amsterdamse school"] if AS in groups else [])
    as_houses = bag[g["styles", "as"] & house].tolist()
    for j in range(0, min(len(as_houses), 24), 3):
        group = as_houses[j:j + (2 if j == 0 else 1)]
        item(group, f"Fixture block {j // 3 + 1}", [AS_ARCHITECTS[(j // 3) % 4]], ["Amsterdamse school"])
    old = bag[golden].tolist()
    for j in range(0, min(len(old), 40), 5):
        item([old[j]], f"Fixture house {j // 5 + 1}", photo=j % 10 == 0)
    for j, bg in enumerate(bag[g["faith", "hofje"]].tolist()[:4]):
        item([bg], f"Fixture hofje {j + 1}", photo=j % 2 == 0)
    for j, bg in enumerate(company):
        item([bg], ["Fixture East India House", "Fixture West India House"][j])
    # named post-war buildings and warehouses, scattered over each theme's pool (a fixed draw), so the named-stop
    # rule has a choice everywhere; half without a photo, as many Wikidata items are
    scatter = np.random.default_rng(7)
    pw = bag[postwar & (g["war", "bomb"] | g["war", "damage"] | g["noord1943", "rebuilt"] | art
                        | g["planned", "Western garden cities"])].tolist()
    ware = [x_ for x_ in bag[g["trade", "pakhuis"]].tolist() if x_ not in index]
    for label, pool_, n_ in (("Fixture rebuilt block", pw, 16), ("Fixture warehouse", ware, 12)):
        for j, i in enumerate(sorted(scatter.choice(len(pool_), min(n_, len(pool_)), replace=False))):
            item([pool_[i]], f"{label} {j + 1}", photo=j % 2 == 0)
    src = WIKI + "Fixture"
    facts[landmarks["church_w"]] = dict(en="A made-up fact: its tower is the tallest in the fixture city's west.",
                                        nl="Een verzonnen feit: de toren is de hoogste in het westen van de teststad.",
                                        source=src)
    if old:
        facts[old[0]] = dict(en="A made-up fact about a fixture canal house.",
                             nl="Een verzonnen feit over een grachtenpand in de teststad.", source=src)
    if as_houses:
        facts[as_houses[0]] = dict(en="A made-up fact: the fixture's first Amsterdam School block.",
                                   nl="Een verzonnen feit: het eerste blok van de Amsterdamse School in de teststad.",
                                   source=src)
    return b, bits, catalogue, wiki, index, facts


def enrich(b, q, landmarks):
    """The hook for fixture_city.main: extra buildings, and the files the quest builder reads."""
    b, q, extra = add_extra(b, q)
    b, bits, catalogue, wiki, index, facts = attributes(b, landmarks, extra)
    files = {"data/layers.parquet": bits,
             "data/wiki_index.parquet": pd.DataFrame(dict(bag=list(index), wk=list(index.values()))),
             "web/data/layers.json": catalogue, "web/data/wiki.json": wiki, "web/data/facts.json": facts}
    return b, q, files


def city():
    """The enriched fixture in memory, as a questgen City, plus the landmark and extra BAG ids."""
    from pipeline.quest_routes import heights_from
    from pipeline.questgen.city import City

    b, q, landmarks = fc.city()
    b, q, extra = add_extra(b, q)
    b, bits, catalogue, wiki, index, facts = attributes(b, landmarks, extra)
    c = City.from_frames(b.drop(columns="key"), bits, catalogue, wiki, index, facts, heights=heights_from(b, q))
    return c, dict(landmarks, **extra)


def main(root):
    fc.main(root, enrich=enrich)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ams-qg")
