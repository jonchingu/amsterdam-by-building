"""Build a quest from a theme and preview it, or write it into the quest set.

    python -m pipeline.questgen --list-themes
    python -m pipeline.questgen --theme amsterdam-school --stops 6 --seed 1              # readable preview
    python -m pipeline.questgen --theme amsterdam-school --seed 1 --json                 # the quest as JSON
    python -m pipeline.questgen --theme churches-towers --start dam --within 1500 --write --save

Run from the folder that holds data/ and web/data/ (the repository after a pipeline run), or pass --root.
--write puts the quest into web/data/quests.json; --save also keeps its spec in pipeline/questgen/specs.json, so
s13_quests rebuilds it on every run. A quest is written only when it passes s13's checks and its route is clear.
"""
import argparse
import json
import os
import sys

from .build import SPECS, STAGES, BuildError, build, describe, save_spec, validate, write_quest
from .registry import ORDERS, PLANNERS, SELECTORS, SOURCES, THEMES, WRITERS


def list_themes(city=None):
    for name, th in THEMES:
        n = f"  {int(th.require.mask(city.df).sum())} candidates" if city is not None else ""
        print(f"{name:20s} level {th.level}, {th.stops} stops, within {2 * th.radius:.0f} m{n}")
        print(f"{'':20s} {th.title['en']}: requires {th.require}")
        if th.prefer:
            print(f"{'':20s} prefers " + ", ".join(f"{c} ×{w:g}" for c, w in th.prefer))
    print()
    for label, reg in (("source", SOURCES), ("select", SELECTORS), ("order", ORDERS), ("route", PLANNERS),
                       ("steps", WRITERS)):
        print(f"--{label:7s} " + ", ".join(f"{n}{' (default)' if n == STAGES[label] else ''}" for n in reg.names()))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline.questgen", description=__doc__.split("\n\n")[0])
    ap.add_argument("--list-themes", action="store_true", help="list the themes and every stage's modules")
    ap.add_argument("--theme")
    ap.add_argument("--stops", type=int, help="number of stops (default: the theme's)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--start", help="where the walk begins: dam, x,z (metres from the Dam, x east, z south) or bag:<id>")
    ap.add_argument("--within", type=float, help="metres around the start (or the Dam) the stops must lie in")
    ap.add_argument("--id", help="quest id (default gen-<theme>-<seed>)")
    for stage, default in STAGES.items():
        ap.add_argument(f"--{stage}", default=default, help=f"{stage} module (default {default})")
    ap.add_argument("--root", help="folder with data/ and web/data/ (default: here)")
    ap.add_argument("--json", action="store_true", help="print the quest as JSON instead of text")
    ap.add_argument("--out", help="also write the quest JSON to this file")
    ap.add_argument("--write", action="store_true", help="put the quest into web/data/quests.json")
    ap.add_argument("--save", action="store_true", help="keep its spec (see --specs) for s13_quests to rebuild")
    ap.add_argument("--specs", default=str(SPECS), help=f"spec file for --save (default {SPECS})")
    a = ap.parse_args(argv)
    a.specs = os.path.abspath(a.specs)
    if a.root:
        os.chdir(a.root)

    from .city import City

    if a.list_themes:
        list_themes(City.load() if os.path.exists("data/buildings.parquet") else None)
        return 0
    if not a.theme:
        ap.error("--theme is required (see --list-themes)")
    city = City.load()
    try:
        quest = build(a.theme, a.stops, a.seed, city, a.start, a.within, a.id,
                      **{k: getattr(a, k) for k in STAGES})
    except (BuildError, RuntimeError, ValueError) as e:
        print(f"{a.theme}: {e}", file=sys.stderr)
        return 1
    problems = validate(quest, city)
    print(json.dumps(quest, ensure_ascii=False, indent=1) if a.json else describe(quest, city))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(quest, f, ensure_ascii=False, indent=1)
    if problems:
        print("\n".join(["", "problems:"] + problems), file=sys.stderr)
        return 1
    print("checks: ok", file=sys.stderr)
    if a.write:
        n = write_quest(quest)
        print(f"wrote {quest['id']} into web/data/quests.json ({n} quests)", file=sys.stderr)
    if a.save:
        save_spec(quest, a.specs)
        print(f"saved its spec in {a.specs}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
