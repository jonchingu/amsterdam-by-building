"""Resolve every quest step to its buildings and check it (web/data/quests.json).

A step is dropped, and its quest with it, when: an article lacks a checked string; a story or address is not found;
a year step's year is not the map's year for the building (within one year); a photo clue has no photo.

Every quest then gets its flyover route (quest_routes.py): anchors the app flies through the quest's buildings. A
route leg that still passes through a building after the planner's fixes fails the build.
`python -m pipeline.s13_quests --routes-only` re-plans the routes of an existing quests.json without the checks.

Quests the quest builder generated and saved (pipeline/questgen/specs.json) are rebuilt from the map's data on every
run and go through the same checks (check_step, check_quest) and the same route planning.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from .quest_routes import load_heights, plan
from .quests import QUESTS


OUT = Path("web/data/quests.json")


KINDS = {"find": ("riddle", "reveal"), "year": ("ask", "year", "reveal"),
         "choice": ("ask", "options", "reveal"), "where": ("riddle", "reveal", "clue")}


def _text(t):
    return isinstance(t, dict) and all(isinstance(t.get(k), str) and t[k].strip() for k in ("en", "nl"))


def check_step(s, years=None, here="step"):
    """Problems with one resolved step (it has its `bags`): its shape, and a year step's year against the map's.

    years: {BAG id: the map's year}; without it the year is not compared (e.g. before the data is loaded)."""
    kind = s.get("kind")
    if kind not in KINDS:
        return [f"{here}: unknown kind {kind!r}"]
    out = [f"{here}: no {k}" for k in KINDS[kind] if s.get(k) in (None, "", [])]
    if out:
        return out
    if not s.get("bags"):
        out.append(f"{here}: no buildings")
    for k in ("riddle", "ask", "reveal"):
        if k in s and not _text(s[k]):
            out.append(f"{here}: {k} needs en and nl")
    if kind == "find" and not (isinstance(s.get("hints"), list) and all(_text(h) for h in s["hints"])):
        out.append(f"{here}: a hint needs en and nl")
    if kind == "choice":
        if len(s["options"]) < 2 or not all(_text(o) for o in s["options"]):
            out.append(f"{here}: a choice needs two or more options in en and nl")
        elif len({o["en"] for o in s["options"]}) < len(s["options"]):
            out.append(f"{here}: two options are the same")
    if kind == "where" or s.get("clue") == "today":
        if not (isinstance(s.get("clue"), dict) and s["clue"].get("thumb")):
            out.append(f"{here}: no photo")
    if kind == "year" and years is not None:
        ys = sorted({int(years[x]) for x in s["bags"] if x in years})
        if not any(abs(y - s["year"]) <= 1 for y in ys):
            out.append(f"{here}: map says {ys}, step says {s['year']}")
    return out


def check_quest(q, years=None):
    """Problems with one resolved quest: its fields and every step (check_step)."""
    out = [f"{q.get('id')}: no {k}" for k in ("id", "level", "title", "intro", "steps") if not q.get(k)]
    if out:
        return out
    if q["level"] not in (1, 2, 3):
        out.append(f"{q['id']}: level {q['level']}")
    for k in ("title", "intro"):
        if not _text(q[k]):
            out.append(f"{q['id']}: {k} needs en and nl")
    for i, s in enumerate(q["steps"]):
        out += check_step(s, years, f"{q['id']} {i + 1}")
    return out


def add_routes(quests):
    """A flyover route per quest, planned on the buildings' heights. Raises when a leg can't be cleared."""
    H = load_heights()
    for q in quests:
        try:
            q["route"] = plan([s["bags"] for s in q["steps"]], H)
        except (RuntimeError, ValueError) as e:
            raise SystemExit(f"{q['id']}: route: {e}")
        legs = len(q["route"]) - 1
        print(f'{q["id"]:10s} route: {len(q["route"])} anchors, {legs} legs clear')


def generated(years, problems):
    """The quests the quest builder saved (questgen/specs.json), rebuilt on today's data and checked as the rest."""
    from .questgen.build import SPECS, build_spec, load_specs
    from .questgen.city import City

    specs = load_specs(SPECS)
    if not specs:
        return []
    city, out = City.load(), []
    for spec in specs:
        try:
            q = build_spec(spec, city, route="none")
        except Exception as e:  # a theme that no longer finds its stops is reported, not fatal
            problems.append(f"generated {spec.get('id') or spec.get('theme')}: {e}")
            continue
        bad = check_quest(q, years)
        problems += bad
        if not bad:
            out.append(q)
        print(f'{q["id"]:10s} level {q["level"]}  generated, {len(q["steps"])} steps')
    return out


def main():
    if "--routes-only" in sys.argv:
        quests = json.loads(OUT.read_text())
        add_routes(quests)
        OUT.write_text(json.dumps(quests, ensure_ascii=False, separators=(",", ":")))
        return
    from .s08_curated import article, geocode, wikidata_bags

    b = pd.read_parquet("data/buildings.parquet", columns=["identificatie", "year", "date_flag", "height"])
    b["bag"] = b.identificatie.str.slice(-16)
    by = b.set_index("bag")
    years = by.year.to_dict()
    curated = {L["id"]: L for L in json.load(open("data/curated.json"))}
    wiki = json.load(open("web/data/wiki.json"))
    wk = pd.read_parquet("data/wiki_index.parquet").set_index("bag").wk
    label = lambda bag, lang="en": (wiki[wk[bag]].get("label" if lang == "en" else "label_nl") if bag in wk.index else None)

    def where(at):
        kind, _, ref = at.partition(":")
        if kind == "wd":
            return sorted(wikidata_bags().get(article(ref)[1], set()))
        if kind == "story":
            layer, address = ref.split(":", 1)
            return sorted({e["bag"] for e in curated.get(layer, {}).get("entries", []) if e["address"] == address})
        if kind == "addr":
            bag, _ = geocode(ref)
            return [bag] if bag else []
        if kind == "rule" and ref == "oldest":
            exact = b[b.date_flag == 0]
            return sorted(exact[exact.year == exact.year.min()].bag)
        raise ValueError(at)

    out, problems = [], []
    for q in QUESTS:
        steps = []
        for i, s in enumerate(q["steps"]):
            here = f'{q["id"]} {i + 1}'
            bags = [x for x in where(s["at"]) if x in by.index]
            if not bags:
                problems.append(f"{here}: nothing at {s['at']}")
                continue
            missing = [(ref, c) for ref, cs in s["checks"] for c in cs if c.lower() not in article(ref)[0].lower()]
            if missing:
                problems.append(f"{here}: {missing}")
                continue
            step = {k: v for k, v in s.items() if k not in ("checks", "at") and v is not None}
            step["bags"] = bags
            step["sources"] = sorted({article(ref)[1] for ref, _ in s["checks"]})
            if s["at"].startswith("story:"):
                layer, address = s["at"][6:].split(":", 1)
                e = next(e for e in curated[layer]["entries"] if e["address"] == address)
                step["sources"] = sorted(set(step["sources"]) | {e["source"]})
            if s.get("clue") == "today":
                img = next((wiki[wk[x]]["image"] for x in bags if x in wk.index and wiki[wk[x]].get("image")), None)
                if not img:
                    problems.append(f"{here}: no photo")
                    continue
                step["clue"] = dict(thumb=img["thumb"], page=img.get("page"), artist=img.get("artist"),
                                    license=img.get("license"))
            bad = check_step(step, years, here)
            if bad:
                problems += bad
                continue
            steps.append(step)
        if len(steps) == len(q["steps"]):
            out.append(dict({k: v for k, v in q.items() if k != "steps"}, steps=steps))
        print(f'{q["id"]:10s} level {q["level"]}  {len(steps)}/{len(q["steps"])}')
    out += generated(years, problems)
    for p in problems:
        print("problem:", p)
    add_routes(out)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(len(out), "quests")


if __name__ == "__main__":
    main()
