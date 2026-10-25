"""Checks for the quest builder (pipeline/questgen) on the enriched fixture city. Runs with pytest, or on its own:

    uv run python tests/test_questgen.py          # every stage on its own, then end to end through the CLI

The end-to-end test writes the fixture city to a temporary folder, builds a quest per theme with the CLI, writes them
into its quests.json, and checks them with s13's checks and against every building's height.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from functools import cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
import questgen_fixture as qf  # noqa: E402
from pipeline import quest_routes as qr  # noqa: E402
from pipeline.periods import PERIODS  # noqa: E402
from pipeline.questgen import build as B  # noqa: E402
from pipeline.questgen.order import length, loop, walk  # noqa: E402
from pipeline.questgen.registry import ORDERS, PLANNERS, SELECTORS, SOURCES, THEMES, WRITERS, Registry  # noqa: E402
from pipeline.questgen.select import SelectionError, notability, top_k  # noqa: E402
from pipeline.questgen import steps as St  # noqa: E402
from pipeline.questgen.steps import SRC_BAG, nl_name, period_span  # noqa: E402
from pipeline.questgen.themes import Group, Has, Monument, Near, Taller, Text, Years  # noqa: E402
from pipeline.s13_quests import check_quest, check_step  # noqa: E402


@cache
def fixture():
    return qf.city()


def candidates(theme, area=None):
    city, _ = fixture()
    return SOURCES.get("attributes")(THEMES.get(theme), city, area)


def rng(seed=1):
    return np.random.default_rng([seed, 1])


# ---------- the building directory ----------
def test_city_directory():
    city, keys = fixture()
    df = city.df
    assert df.key.is_unique
    block = df[df.name_en == "Fixture block 1"]
    assert len(block) == 1 and len(block.bags.iloc[0]) == 2, "one Wikidata item, two buildings, one checkpoint"
    assert all(len(r.bags) == 1 for r in df[df.name_en.isna()].itertuples())
    for col in ("name_en", "image", "wiki_url", "fact"):
        assert all(v is None or isinstance(v, (str, dict)) for v in df[col]), col
    assert (df.exact == df.date_flag.isin([0, 3, 5])).all() and (~df.exact).any()
    assert {"g:styles:as", "g:faith:worship", "g:unesco:Kernzone"} <= set(df.columns)
    tower = df[df.bags.map(lambda b: keys["tower"] in b)].iloc[0]
    assert tower.prominence > 5 and tower.height > 250
    assert city.group_label("g:faith:worship")["en"] == "Church"
    assert city.bag_years[keys["church_w"]] == 1631


# ---------- registries and themes ----------
def test_registries():
    assert {"amsterdam-school", "golden-age-canals", "churches-towers", "post-war-rebuild"} <= set(THEMES.names())
    assert SOURCES.names() == ["attributes"] and "balanced" in SELECTORS.names() and "walk" in ORDERS.names()
    assert {"flyover", "none"} <= set(PLANNERS.names()) and "facts" in WRITERS.names()
    try:
        SELECTORS.get("nope")
    except ValueError as e:
        assert "balanced" in str(e)
    else:
        raise AssertionError("unknown names must fail")
    r = Registry("thing")
    r.register("a", 1)
    try:
        r.register("a", 2)
    except ValueError:
        pass
    else:
        raise AssertionError("a name registers once")


def test_conditions():
    city, _ = fixture()
    df = city.df
    old = Years(1600, 1700).mask(df)
    assert (df[old].year.between(1600, 1700)).all()
    assert (Years(1600, 1700, exact=True).mask(df) == old & df.exact).all()
    assert ((Taller(50) | Monument()).mask(df) == (df.height >= 50) | df.monument).all()
    assert (~Has("name")).mask(df).sum() == df.name_en.isna().sum()
    assert Group("war:*").mask(df).sum() == (df["g:war:bomb"] | df["g:war:damage"]).sum()
    assert Group("nolayer:x").mask(df).sum() == 0, "a missing layer finds nothing"
    assert Text("fixture block").mask(df).sum() == (df.name_en.fillna("").str.startswith("Fixture block")).sum()
    assert "built 1600–1700" in str(Years(1600, 1700) & Group("unesco:Kernzone"))


def test_sourcing_follows_each_theme():
    city, keys = fixture()
    for name, th in THEMES:
        c = candidates(name)
        assert len(c) >= th.stops, f"{name}: {len(c)} candidates in the fixture"
        assert th.require.mask(c).all() and c.fit.between(0, 1).all()
    a = candidates("amsterdam-school")
    assert a.year.between(1910, 1945).all()
    ch = candidates("churches-towers")
    w = ch[ch["g:faith:worship"]]
    assert len(w) >= 4 and all(n["en"] == "church" for n in w.noun)
    assert ch[ch["g:faith:synagogue"]].noun.iloc[0]["en"] == "synagogue"
    g = candidates("golden-age-canals")
    trap = g[g["g:gables:trap"] & ~g["g:trade:pakhuis"]]
    assert len(trap) and all("stepped gable" in n["en"] for n in trap.noun)
    assert all(n["en"] == "warehouse" for n in g[g["g:trade:pakhuis"]].noun), "a warehouse is a warehouse, gable or not"
    near = candidates("golden-age-canals", Near(-300, 0, 200))
    assert 0 < len(near) < len(g) and (np.hypot(near.x + 300, near.z) <= 200).all()


# ---------- selection ----------
def stops_ok(s, th):
    xz = s[["x", "z"]].to_numpy()
    D = np.hypot(*(xz[:, None] - xz[None]).transpose(2, 0, 1))
    off = D[~np.eye(len(s), dtype=bool)]
    return s.key.is_unique and off.min() >= th.gap and off.max() <= 2 * th.radius


def test_selection():
    th = THEMES.get("golden-age-canals")
    c = candidates(th.id)
    s = SELECTORS.get("balanced")(c, 6, th, rng(1))
    assert len(s) == 6 and stops_ok(s, th)
    again = SELECTORS.get("balanced")(c, 6, th, rng(1))
    assert list(s.key) == list(again.key), "same seed, same stops"
    other = {tuple(SELECTORS.get("balanced")(c, 6, th, rng(k)).key) for k in range(2, 7)}
    assert len(other | {tuple(s.key)}) > 1, "seeds give different quests"
    assert notability(s).mean() > notability(c).mean(), "notable stops first"
    assert len(set(s.period)) > 1 or len(set(s.year)) > 1
    near = SELECTORS.get("balanced")(c, 5, th, rng(1), start=(300.0, 200.0))
    far = SELECTORS.get("balanced")(c, 5, th, rng(1), start=(-500.0, -280.0))
    d = lambda S, p: np.hypot(S.x - p[0], S.z - p[1]).mean()
    assert d(near, (300, 200)) < d(far, (300, 200)), "a start pulls the stops towards it"
    n = SELECTORS.get("notable")(c, 4, th, rng(1))
    assert len(n) == 4 and n.key.is_unique
    try:
        SELECTORS.get("balanced")(c.head(3), 6, th, rng(1))
    except SelectionError:
        pass
    else:
        raise AssertionError("too few candidates must fail")


def overlap(sets):
    pairs = [(a, b) for i, a in enumerate(sets) for b in sets[i + 1:]]
    return sum(len(a & b) / len(a | b) for a, b in pairs) / len(pairs)


def test_top_k_sampling():
    gains = np.array([1.0, 0.95, 0.9, 0.85, 0.8, 0.2])
    idx = np.arange(10, 16)
    picks = {top_k(np.random.default_rng(s), idx, gains, k=4, margin=0.25) for s in range(200)}
    assert picks == {10, 11, 12, 13}, "only the k best"
    picks = {top_k(np.random.default_rng(s), idx, gains, k=4, margin=0.07) for s in range(200)}
    assert picks == {10, 11}, "and only those within the margin of the best"
    assert top_k(np.random.default_rng(3), idx, gains) == top_k(np.random.default_rng(3), idx, gains), "seeded"
    assert {top_k(np.random.default_rng(s), idx, gains, k=1) for s in range(20)} == {10}


def test_roles_fill_their_slots():
    city, _ = fixture()
    by = {b: r for r in city.df.itertuples() for b in r.bags}
    th = THEMES.get("churches-towers")
    for seed in range(1, 6):
        q = B.build("churches-towers", None, seed, city, route="none")
        roles = [s.get("role") for s in q["steps"]]
        assert sorted(r for r in roles if r) == sorted(r.name for r in th.roles if r.default), roles
        for s in q["steps"]:
            r = by[s["bags"][0]]
            if s.get("role"):
                role = next(x for x in th.roles if x.name == s["role"])
                assert role.cond.mask(city.df[city.df.key == r.key]).all(), (s["role"], r.year)
            assert r.height < 60 or r.year < 1900 or r._asdict().get("g:faith:worship"), "no modern tower by default"
    q = B.build("churches-towers", 4, 1, city, roles=["medieval", "counterpoint"], route="none")
    tower = [by[s["bags"][0]] for s in q["steps"] if s.get("role") == "counterpoint"]
    assert len(tower) == 1 and tower[0].year >= 1950 and tower[0].height >= 60, "the counterpoint, only when asked"
    assert sum(s.get("role") == "medieval" for s in q["steps"]) == 1 and q["generated"]["roles"] == ["medieval",
                                                                                                    "counterpoint"]
    assert B.build_spec(dict(id=q["id"], **q["generated"]), city) == q
    plain = B.build("churches-towers", None, 1, city, roles=[], route="none")
    assert all("role" not in s for s in plain["steps"]), "--no-roles: the old behaviour"
    try:
        B.build("churches-towers", None, 1, city, roles=["baroque"])
    except B.BuildError as e:
        assert "medieval" in str(e)
    else:
        raise AssertionError("an unknown role must fail")
    # a role with no candidates (no church within 300 m of here) is skipped, and the stops come from the rest
    q = B.build("golden-age-canals", 4, 1, city, start="-100,-100", within=300, route="none")
    assert len(q["steps"]) == 4 and "church" not in [s.get("role") for s in q["steps"]]


def test_variety_across_seeds():
    city, _ = fixture()
    for name, _ in THEMES:
        sets = [frozenset(s["bags"][0] for s in B.build(name, None, k, city, route="none")["steps"])
                for k in range(1, 6)]
        assert overlap(sets) <= 0.4, f"{name}: stops overlap {overlap(sets):.2f} across seeds 1–5"
        kinds = {tuple(s["kind"] for s in B.build(name, None, k, city, route="none")["steps"]) for k in range(1, 6)}
        assert len(kinds) > 1, f"{name}: the order of step kinds follows the seed"


def test_no_far_outlier():
    city, _ = fixture()
    by = {b: r for r in city.df.itertuples() for b in r.bags}
    for name in ("amsterdam-school", "golden-age-canals", "post-war-rebuild", "warehouses"):
        for k in range(1, 6):
            rs = [by[s["bags"][0]] for s in B.build(name, None, k, city, route="none")["steps"]]
            xz = np.array([(r.x, r.z) for r in rs])
            D = np.hypot(*(xz[:, None] - xz[None]).transpose(2, 0, 1)) + np.diag(np.full(len(rs), np.inf))
            nn = np.sort(D.min(1))
            assert nn[-1] <= max(250, 2 * nn[-2]), f"{name} {k}: a stop {nn[-1]:.0f} m from the rest"


def test_height_choice_spread():
    seen, ratios = set(), set()
    for seed in range(60):
        for h in (15, 22, 40, 85, 260):
            opts = St.height_options(h, np.random.default_rng([seed, h]))
            if opts is None:
                continue
            assert opts[0] == h and len(set(opts)) == 3 and min(opts) > 0
            seen.add(sorted(opts).index(h))
            ratios.add(tuple(round(x / h, 1) for x in opts[1:]))
    assert seen == {0, 1, 2}, "the right height is lowest, middle or highest"
    assert len(ratios) > 10, "the wrong heights spread by the seed"


def test_start_point():
    city, keys = fixture()
    by = {b: r for r in city.df.itertuples() for b in r.bags}
    w = by[keys["church_w"]]
    found = False
    for seed in range(1, 15):
        q = B.build("churches-towers", None, seed, city, start=f"bag:{keys['church_w']}", route="none")
        rs = [by[s["bags"][0]] for s in q["steps"]]
        assert all(np.hypot(r.x - w.x, r.z - w.z) >= THEMES.get("churches-towers").gap for r in rs), \
            "the start building is never a stop, nor anything within gap of it"
        s = q["steps"][0]
        if s["kind"] == "find":
            found = True
            assert s["hints"][0]["en"].endswith("of Westerkerk.") and s["hints"][0]["nl"].endswith("de Westerkerk.")
            (d, _), (c, _) = St.direction((w.x, w.z), (rs[0].x, rs[0].z))
            assert f"{d} {c} of" in s["hints"][0]["en"], "measured from the start, not the Dam"
    assert found
    r = candidates("churches-towers").iloc[0]
    step = St.write_step("find", r, dict(xy=(r.x + 100, r.z), en="the start", nl="het startpunt"))
    assert step["hints"][0]["en"] == "It is about 100 m west of the start."


def test_zero_and_bad_arguments():
    city, _ = fixture()
    for kw, word in ((dict(stops=0), "--stops 0"), (dict(stops=1), "--stops 1"), (dict(within=0), "--within 0"),
                     (dict(within=-5), "--within -5")):
        try:
            B.build("churches-towers", city=city, route="none", **kw)
        except B.BuildError as e:
            assert word in str(e), e
        else:
            raise AssertionError(f"{kw} must fail")


def test_dutch_articles():
    assert nl_name("Westerkerk") == "de Westerkerk" and nl_name("Scheepvaarthuis") == "het Scheepvaarthuis"
    assert nl_name("Centraal Station", cap=True) == "Het Centraal Station"
    assert nl_name("Noorderkerk (fixture)") == "de Noorderkerk (fixture)"
    assert nl_name("De Bazel") == "De Bazel" and nl_name("Het Schip") == "Het Schip"
    assert nl_name("Fixture block 3") == "Fixture block 3" and nl_name("Rijksmuseum") == "het Rijksmuseum"
    city, _ = fixture()
    q = B.build("churches-towers", None, 1, city, route="none")
    texts = [s.get("riddle", s.get("ask"))["nl"] for s in q["steps"]]
    assert any(" de " in t.lower() for t in texts if "kerk" in t.lower()), texts


# ---------- ordering ----------
def test_ordering():
    line = np.array([[400.0, 0], [0, 0], [300, 0], [100, 0], [200, 0]])
    o = walk(line)
    assert [line[i, 0] for i in o] in ([0, 100, 200, 300, 400], [400, 300, 200, 100, 0])
    o = walk(line, start=(450.0, 10.0))
    assert [line[i, 0] for i in o] == [400, 300, 200, 100, 0], "the walk begins next to the start"
    # nearest neighbour alone crosses itself here; 2-opt undoes it
    pts = np.array([[0, 0], [10, 1], [20, 0], [20, 30], [10, 29], [0, 30]], dtype=float)
    D = np.hypot(*(pts[:, None] - pts[None]).transpose(2, 0, 1))
    tour = loop(pts)
    assert sorted(tour) == list(range(6))
    assert length(D, tour, True) <= 2 * 20 + 2 * 30 + 4
    assert walk(pts) == walk(pts), "deterministic"


# ---------- route planning ----------
def test_route_planners():
    city, keys = fixture()
    steps = [[keys["church_w"]], [keys["tiny"]], [keys["church_z"]]]
    route = PLANNERS.get("flyover").plan(steps, city)
    assert PLANNERS.get("flyover").check(route, city) == [] and not qr.clips(route, city.heights)
    assert [a["step"] for a in route if "step" in a] == [0, 1, 2]
    assert PLANNERS.get("none").plan(steps, city) is None

    class Straight:  # another planner plugs in by name
        name = "test-straight"

        def plan(self, steps, city):
            return [dict(p=[city.df[city.df.bags.map(lambda b: s[0] in b)].x.iloc[0], 400.0, 0.0], step=k)
                    for k, s in enumerate(steps)]

        def check(self, route, city):
            return []

    if "test-straight" not in PLANNERS.names():
        PLANNERS.register("test-straight", Straight())
    q = B.build("churches-towers", 3, 1, city, route="test-straight")
    assert len(q["route"]) == 3 and q["generated"]["route"] == "test-straight" and B.validate(q, city) == []


# ---------- step writing ----------
def test_steps_say_only_what_the_data_holds():
    city, _ = fixture()
    by = {b: r for r in city.df.itertuples() for b in r.bags}
    kinds = set()
    for name, _ in THEMES:
        for seed in (1, 2):
            q = B.build(name, None, seed, city, route="none")
            assert check_quest(q, city.bag_years) == [], name
            prev = None
            for s in q["steps"]:
                r = by[s["bags"][0]]
                kinds.add(s["kind"])
                text = json.dumps({k: v for k, v in s.items() if k not in ("bags", "sources", "clue")})
                if not r.exact:
                    assert str(r.year) not in text, f"{name}: an estimated year is told: {text}"
                if s["kind"] == "year":
                    assert r.exact and s["year"] == r.year
                if s["kind"] == "where":
                    assert r.name_en and r.image and s["clue"]["thumb"] == r.image["thumb"]
                if s["kind"] == "choice":
                    right = s["options"][0]["en"]
                    if s["ask"]["en"].startswith("Who designed"):
                        assert right in r.architects and all(o["en"] not in r.architects for o in s["options"][1:])
                        assert r.wiki_url in s["sources"]
                    elif s["ask"]["en"].startswith("In which period"):
                        _, _, lo, hi, _ = PERIODS[r.period]
                        assert r.exact and lo <= r.year <= hi and s["options"][0] == period_span(r.period)
                        assert name != "amsterdam-school", "one period only: the theme gives it away"
                    elif s["ask"]["en"].startswith("Which of these"):
                        assert r.exact and s["options"][0]["en"] in s["reveal"]["en"].split(";")[0]
                    else:
                        assert right == f"About {round(r.height)} m" and SRC_BAG in s["sources"]
                if s["kind"] == "find":
                    hint = s["hints"][0]["en"]
                    ref = prev if prev is not None else (0.0, 0.0)
                    bearing = math.degrees(math.atan2(r.x - ref[0], -(r.z - ref[1]))) % 360
                    word = hint.split(" m ")[-1].split(" of ")[0] if " m " in hint else hint.split(" km ")[-1].split(" of ")[0]
                    compass = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
                    assert word == compass[int(round(bearing / 45)) % 8], (hint, bearing)
                fact = r.fact["en"] if r.fact else (r.stories[0]["en"] if r.stories else None)
                if fact:
                    assert fact in s["reveal"]["en"], "a fact or story is told word for word"
                prev = (r.x, r.z)
            assert len({s["kind"] for s in q["steps"]}) > 1, f"{name}: one kind only"
    assert kinds == {"find", "where", "year", "choice"}


def test_build_is_deterministic():
    city, _ = fixture()
    a = B.build("amsterdam-school", 5, 4, city)
    b = B.build("amsterdam-school", 5, 4, city)
    assert a == b and a["id"] == "gen-amsterdam-school-4" and a["generated"]["seed"] == 4
    assert B.validate(a, city) == []
    assert B.build_spec(dict(id=a["id"], **a["generated"]), city) == a


# ---------- s13's checks, shared by hand-written and generated quests ----------
def test_s13_checks():
    from pipeline.quests import QUESTS

    photo = dict(thumb="x.jpg")
    for q in QUESTS:  # the hand-written quests, resolved as s13 resolves them, pass the shared checks
        steps = [dict({k: v for k, v in s.items() if k not in ("at", "checks") and v is not None}, bags=["1"],
                      **({"clue": photo} if s.get("clue") == "today" else {})) for s in q["steps"]]
        assert check_quest(dict(q, steps=steps)) == [], q["id"]
    year = dict(kind="year", ask=dict(en="When?", nl="Wanneer?"), year=1700, reveal=dict(en="1700.", nl="1700."),
                bags=["1"])
    assert check_step(year, {"1": 1700}) == [] and check_step(year, {"1": 1701}) == []
    assert "map says [1800]" in check_step(year, {"1": 1800})[0]
    assert check_step(dict(year, ask=dict(en="When?")))
    assert check_step(dict(kind="where", riddle=year["ask"], reveal=year["reveal"], bags=["1"]))
    assert check_step(dict(kind="choice", ask=year["ask"], reveal=year["reveal"], bags=["1"],
                           options=[dict(en="a", nl="a"), dict(en="a", nl="b")]))


# ---------- end to end ----------
def test_end_to_end_cli():
    root, here = Path(tempfile.mkdtemp(prefix="questgen-")), os.getcwd()
    try:
        end_to_end(root)
    finally:
        os.chdir(here)
        shutil.rmtree(root, ignore_errors=True)


def end_to_end(root):
    qf.main(root)
    env = dict(os.environ, PYTHONPATH=str(REPO))
    run = lambda *a: subprocess.run([sys.executable, "-m", "pipeline.questgen", "--root", str(root), *a], env=env,
                                    capture_output=True, text=True)
    r = run("--list-themes")
    assert r.returncode == 0 and "amsterdam-school" in r.stdout and "candidates" in r.stdout, r.stderr
    specs = root / "specs.json"
    for name in THEMES.names():
        r = run("--theme", name, "--seed", "1", "--write", "--save", "--specs", str(specs))
        assert r.returncode == 0, f"{name}: {r.stdout[-500:]} {r.stderr[-2000:]}"
        assert "checks: ok" in r.stderr
    r = run("--theme", "churches-towers", "--stops", "3", "--seed", "2", "--start", "dam", "--within", "900", "--json")
    assert r.returncode == 0, r.stderr
    q = json.loads(r.stdout)
    assert len(q["steps"]) == 3 and q["generated"]["within"] == 900
    assert run("--theme", "skyline", "--stops", "40").returncode == 1, "too many stops fails cleanly"
    for bad in (("--stops", "0"), ("--within", "0")):
        r = run("--theme", "skyline", *bad)
        assert r.returncode == 1 and " ".join(bad) in r.stderr and "skyline: skyline" not in r.stderr, r.stderr
    r = run("--theme", "churches-towers", "--seed", "2")
    assert r.returncode == 0 and "role: medieval" in r.stdout, "the preview shows each stop's role"
    r = run("--theme", "churches-towers", "--no-roles", "--json")
    assert r.returncode == 0 and all("role" not in s for s in json.loads(r.stdout)["steps"])

    os.chdir(root)
    from pipeline.questgen.city import City

    city = City.load(".")
    H = qr.load_heights()
    quests = json.loads((root / "web/data/quests.json").read_text())
    gen = [q for q in quests if q.get("generated")]
    assert len(gen) == len(THEMES.names()) and {"fixture", "fixture-where"} <= {q["id"] for q in quests}
    for q in gen:
        assert B.validate(q, city) == [], q["id"]
        assert not qr.clips(q["route"], H), f"{q['id']}: the route clears every building"
    # s13 rebuilds the saved specs: the same quests, without their routes (it plans those for the whole set)
    from pipeline import s13_quests

    B.SPECS, saved = specs, B.SPECS
    try:
        problems = []
        again = s13_quests.generated(city.bag_years, problems)
    finally:
        B.SPECS = saved
    assert problems == [] and [q["id"] for q in again] == [q["id"] for q in gen]
    assert all(a["steps"] == g["steps"] for a, g in zip(again, gen))
    r = subprocess.run([sys.executable, "-m", "pipeline.s13_quests", "--routes-only"], env=env, capture_output=True,
                       text=True)
    assert r.returncode == 0 and r.stdout.count("legs clear") == len(quests), r.stdout + r.stderr


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
