"""The quest builder: theme → candidates → stops → order → steps → route, one registered module per stage.

    quest = build("amsterdam-school", stops=6, seed=1, city=City.load())

The quest has the shape s13_quests writes to quests.json, plus `generated`: the spec it was built from, so it can be
rebuilt. validate() runs s13's own checks on it, and the planner's check on its route.

A saved spec (specs.json, next to this file) is rebuilt by s13_quests on every run of the pipeline.
"""
import json
import math
from pathlib import Path

import numpy as np

from . import order as _order, route as _route, select as _select, steps as _steps, themes as _themes  # noqa: F401
from .registry import ORDERS, PLANNERS, SELECTORS, SOURCES, THEMES, WRITERS
from .themes import Near, T

SPECS = Path(__file__).with_name("specs.json")
QUESTS = Path("web/data/quests.json")
STAGES = dict(source="attributes", select="balanced", order="walk", route="flyover", steps="facts")


class BuildError(RuntimeError):
    pass


def parse_start(start, city):
    """'dam', 'x,z' (metres from the Dam, x east, z south) or 'bag:<BAG id>' → (x, z); None stays None."""
    if start is None or isinstance(start, (tuple, list)):
        return tuple(start) if start is not None else None
    if start == "dam":
        return (0.0, 0.0)
    if start.startswith("bag:"):
        bag = start[4:].zfill(16)
        hit = city.df[city.df.bags.map(lambda bs: bag in bs)]
        if hit.empty:
            raise BuildError(f"no building {bag}")
        return (float(hit.x.iloc[0]), float(hit.z.iloc[0]))
    try:
        x, z = (float(v) for v in start.split(","))
    except ValueError:
        raise BuildError(f"start {start!r}: use dam, x,z or bag:<id>")
    return (x, z)


def start_label(start, city):
    """What the first hint measures from: {en, nl}."""
    if start == "dam":
        return dict(en="the Dam", nl="de Dam")
    if isinstance(start, str) and start.startswith("bag:"):
        bag = start[4:].zfill(16)
        hit = city.df[city.df.bags.map(lambda bs: bag in bs)]
        if len(hit) and isinstance(hit.name_en.iloc[0], str):
            from .steps import nl_name
            return dict(en=hit.name_en.iloc[0], nl=nl_name(hit.name_nl.iloc[0] or hit.name_en.iloc[0]))
    return dict(en="the start", nl="het startpunt")


def build(theme, stops=None, seed=1, city=None, start=None, within=None, id=None, roles=None, **stages):
    """A quest from a theme. start: where the walk begins (see parse_start); within: metres around the start (or the
    Dam) that the stops must lie in; roles: the theme's roles to fill by name (None: its default ones, []: none).
    stages: source, select, order, route, steps by registered name."""
    st = dict(STAGES, **{k: v for k, v in stages.items() if v})
    th = THEMES.get(theme)
    n = th.stops if stops is None else int(stops)
    if n < 2:
        raise BuildError(f"--stops {n}: a quest needs two stops or more")
    if within is not None and not float(within) > 0:
        raise BuildError(f"--within {within}: give a distance in metres above 0, or leave it out")
    try:
        active = th.pick_roles(None if roles is None else list(roles))
    except ValueError as e:
        raise BuildError(str(e))
    xy = parse_start(start, city)
    area = Near(*(xy or (0.0, 0.0)), float(within)) if within else None
    rng = lambda stage: np.random.default_rng([int(seed), stage])
    cands = SOURCES.get(st["source"])(th, city, area, roles=active)
    if len(cands) < n:
        raise BuildError(f"{len(cands)} candidates for {n} stops")
    chosen = SELECTORS.get(st["select"])(cands, n, th, rng(1), start=xy, roles=active)
    chosen = chosen.iloc[ORDERS.get(st["order"])(chosen[["x", "z"]].to_numpy(), xy)].reset_index(drop=True)
    ref = dict(xy=xy, **start_label(start, city)) if xy is not None else None
    steps = WRITERS.get(st["steps"])(chosen, th, city, rng(2), start=ref, cands=cands)
    quest = dict(id=id or f"gen-{theme}-{seed}", level=th.level, title=th.title,
                 intro=T(f"{th.intro['en']} {n} stops, picked from the map's own data.",
                         f"{th.intro['nl']} {n} stops, gekozen uit de gegevens van de kaart."),
                 steps=steps,
                 generated=dict(theme=theme, stops=n, seed=int(seed), start=start if isinstance(start, str) else xy,
                                within=within, roles=None if roles is None else list(roles), **st))
    route = PLANNERS.get(st["route"]).plan([s["bags"] for s in steps], city)
    if route is not None:
        quest["route"] = route
    return quest


def build_spec(spec, city, **override):
    """Rebuild a saved quest from its spec (a quest's `generated`, plus its id)."""
    spec = dict(spec, **override)
    keys = ("theme", "stops", "seed", "start", "within", "id", "roles", *STAGES)
    return build(city=city, **{k: spec.get(k) for k in keys})


def validate(quest, city):
    """Problems with a built quest: s13's checks on the quest and its steps, and the route planner's on its route."""
    from ..s13_quests import check_quest

    out = check_quest(quest, city.bag_years)
    if not quest.get("generated"):
        out.append(f"{quest.get('id')}: not marked as generated")
    planner = PLANNERS.get(quest.get("generated", {}).get("route", "flyover"))
    if "route" in quest:
        out += [f"{quest['id']} route: {p}" for p in planner.check(quest["route"], city)]
        framed = sorted(a["step"] for a in quest["route"] if "step" in a)
        if framed != list(range(len(quest["steps"]))):
            out.append(f"{quest['id']} route: frames steps {framed} of {len(quest['steps'])}")
    elif planner.name != "none":
        out.append(f"{quest['id']}: no route")
    return out


# ---------- the quest set ----------
def load_specs(path=SPECS):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def save_spec(quest, path=SPECS):
    """Keep the quest's spec, so s13_quests rebuilds it on every run (replaces a spec with the same id)."""
    specs = [s for s in load_specs(path) if s.get("id") != quest["id"]]
    specs.append(dict(id=quest["id"], **quest["generated"]))
    Path(path).write_text(json.dumps(specs, ensure_ascii=False, indent=1) + "\n")


def write_quest(quest, path=QUESTS):
    """Put the quest into quests.json, replacing one with the same id."""
    path = Path(path)
    quests = json.loads(path.read_text()) if path.exists() else []
    quests = [q for q in quests if q.get("id") != quest["id"]] + [quest]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(quests, ensure_ascii=False, separators=(",", ":")))
    return len(quests)


# ---------- preview ----------
def describe(quest, city):
    """The quest as readable text: every stop, what the player sees and what the answer is."""
    wanted = {b for s in quest["steps"] for b in s["bags"]}
    by_bag = {}
    for r in city.df[city.df.bags.map(lambda bs: not wanted.isdisjoint(bs))].itertuples():
        for b in r.bags:
            by_bag[b] = r
    g = quest["generated"]
    lines = [f"{quest['id']}  level {quest['level']}  {quest['title']['en']} / {quest['title']['nl']}",
             f"  generated: theme {g['theme']}, {g['stops']} stops, seed {g['seed']}"
             + (f", start {g['start']}" if g.get("start") is not None else "")
             + (f", within {g['within']} m" if g.get("within") else "")
             + (f", roles {','.join(g['roles']) or 'none'}" if g.get("roles") is not None else "")
             + f"; {g['source']} → {g['select']} → {g['order']} → {g['steps']} → {g['route']}",
             f"  {quest['intro']['en']}", ""]
    roles = {r.name: r for r in THEMES.get(g["theme"]).roles}
    prev, walk = None, 0.0
    for i, s in enumerate(quest["steps"]):
        r = by_bag.get(s["bags"][0])
        name = (r.name_en if r is not None and r.name_en else "unnamed")
        hop = math.hypot(r.x - prev[0], r.z - prev[1]) if prev and r is not None else 0.0
        walk += hop
        where = f"({r.x:.0f}, {r.z:.0f})" if r is not None else ""
        yr = f"{r.year}{'' if r.exact else ' est.'}" if r is not None else ""
        h = f"{r.height:.0f} m" if r is not None else ""
        lines.append(f"{i + 1}. {s['kind']:6s} {name}  [{', '.join(s['bags'])}]  {where} {yr} {h}"
                     + (f"  +{hop:.0f} m" if hop else ""))
        role = s.get("role")
        lines.append(f"     role: {role} ({roles[role].label['en']})" if role in roles
                     else "     role: any (the theme's pool)")
        for k in ("riddle", "ask"):
            if k in s:
                lines.append(f"     {s[k]['en']}")
        for h_ in s.get("hints", []):
            lines.append(f"     hint: {h_['en']}")
        if "options" in s:
            lines.append("     options: " + " | ".join(o["en"] for o in s["options"]) + "  (first is right)")
        if "year" in s:
            lines.append(f"     answer: {s['year']}")
        if s.get("clue"):
            lines.append(f"     photo: {s['clue']['thumb'][:80]}")
        lines.append(f"     reveal: {s['reveal']['en']}")
        lines.append(f"     sources: {', '.join(s['sources'])}")
        prev = (r.x, r.z) if r is not None else prev
    lines.append("")
    lines.append(f"walk between stops: {walk / 1000:.2f} km")
    if "route" in quest:
        R = quest["route"]
        lines.append(f"route ({g['route']}): {len(R)} anchors, {len(R) - 1} legs, top {max(a['p'][1] for a in R):.0f} m")
    return "\n".join(lines)
