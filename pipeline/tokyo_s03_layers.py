"""Resolve Tokyo's context layers (tokyo_layers.py) to their buildings and write the viewer's layer catalogue.

Output: web/data/tokyo/layers.json, a list in the order of tokyo_layers.py:
    {id, section, title, era, text, caveat, source: {label, url}, count,
     groups: [{key, label, count}], members: {PLATEAU id: [group index, ...]}, notes: {PLATEAU id: story}}

    uv run python -m pipeline.tokyo_s03_layers    # after tokyo_s02_wiki
"""
import json
from pathlib import Path

from .tokyo_layers import LAYERS

OUT = Path("web/data/tokyo")


def main():
    index = json.loads((OUT / "buildings.json").read_text())
    cols, wards = index["columns"], index["wards"]
    known = {f"{wards[w][0]}-bldg-{b}" for w, b in zip(cols["ward"], cols["bldg"])}
    catalogue = []
    for L in LAYERS:
        groups = L["groups"]() if callable(L["groups"]) else L["groups"]
        slot = {key: k for k, (key, _) in enumerate(groups)}
        members, notes = {}, {}
        for pid, v in L["source_fn"]().items():
            if pid not in known:
                continue
            for item in v if isinstance(v, list) else [v]:
                key, note = item if isinstance(item, tuple) else (item, None)
                members.setdefault(pid, [])
                if slot[key] not in members[pid]:
                    members[pid].append(slot[key])
                if note and pid not in notes:
                    notes[pid] = note
        counts = [sum(k in m for m in members.values()) for k in range(len(groups))]
        catalogue.append(dict(
            {k: L[k] for k in ("id", "section", "title", "era", "text", "caveat") if L.get(k)},
            source=dict(label=L["source"][0], url=L["source"][1]), count=len(members),
            groups=[dict(key=key, label=label, count=n) for (key, label), n in zip(groups, counts)],
            members=members, notes=notes))
        print(f'{L["id"]:12s} {len(members):5d}', {key: n for (key, _), n in zip(groups, counts)})
    (OUT / "layers.json").write_text(json.dumps(catalogue, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
