"""Step writing: each ordered stop becomes one quest step, in English and Dutch, from the data alone.

Nothing is invented. A step may say only what the directory holds for its building:
  - a year only when it is exact (BAG as recorded, an RCE year or a Wikidata inception; never an estimate),
  - its height (the 3D BAG roof the map draws), where it lies from the last stop (measured on the map),
  - its name, photo, architect from Wikidata and Commons,
  - a noun the theme takes from a context-layer group ('church' for the faith layer's churches),
  - a checked 'Did you know' fact (s11_facts) or a layer story in both languages (s05_layers), word for word.
A choice's wrong options are other values of the same kind (another architect in the data, another period, another
height), so they are wrong by construction; the right one is first, as quests.py writes them.

Which kind each stop gets: the kinds its data allows (where: a name and a photo; year: an exact year; choice: an
architect, an exact year or a height worth asking), the least used so far first, then the theme's own order, never
the same kind twice running when another is possible.
"""
import math

import numpy as np

from ..periods import PERIODS
from .registry import WRITERS

SRC_BAG = "https://3dbag.nl"
SRC_RCE = "https://monumentenregister.cultureelerfgoed.nl"
COMPASS = [("north", "noorden"), ("north-east", "noordoosten"), ("east", "oosten"), ("south-east", "zuidoosten"),
           ("south", "zuiden"), ("south-west", "zuidwesten"), ("west", "westen"), ("north-west", "noordwesten")]


def T(en, nl):
    return dict(en=en, nl=nl)


def distance(m):
    if m < 1000:
        d = max(50, int(round(m / 50.0)) * 50)
        return f"{d} m", f"{d} m"
    km = f"{m / 1000:.1f}"
    return f"{km} km", f"{km.replace('.', ',')} km"


def direction(frm, to):
    """'about 350 m north-east of …' from one point to another in the local frame (x east, z south)."""
    dx, dz = to[0] - frm[0], to[1] - frm[1]
    i = int(round((math.degrees(math.atan2(dx, -dz)) % 360) / 45)) % 8
    return distance(math.hypot(dx, dz)), COMPASS[i]


def year_source(r):
    if r.date_flag in (3, 4):
        return SRC_RCE
    if r.date_flag == 5 and r.wiki_url:
        return r.wiki_url
    return SRC_BAG


def extra(r):
    """The checked fact or the first layer story, with its source: (en, nl, source) or None."""
    if isinstance(r.fact, dict):
        return r.fact["en"], r.fact["nl"], r.fact.get("source")
    if r.stories:
        s = r.stories[0]
        return s["en"], s["nl"], s.get("source")
    return None


def tail(r, en, nl, src):
    """Sentences en/nl with the fact or story appended; its source joins src."""
    e = extra(r)
    if e:
        en, nl = f"{en} {e[0]}", f"{nl} {e[1]}"
        if e[2]:
            src.add(e[2])
    return T(en, nl)


def period_span(i):
    _, _, a, b, _ = PERIODS[i]
    if i == 0:
        return T(f"before {b + 1}", f"voor {b + 1}")
    return T(f"{a}–{b}", f"{a}–{b}") if b < 2100 else T(f"since {a}", f"sinds {a}")


def named(r):
    return r.name_en if isinstance(r.name_en, str) else None


def choices(r, pool, seed):
    """The choice questions this building supports: [(ask-en, ask-nl, options, reveal-en, reveal-nl, sources)].
    The wrong options depend on the seed and the building only."""
    rng = np.random.default_rng([seed, int(r.primary)])
    out = []
    this_en = named(r) or f"this {r.noun['en']}"
    this_nl = (r.name_nl or r.name_en) if named(r) else r.noun["this_nl"]
    if r.architects and r.wiki_url:
        others = sorted({a for a in pool["architects"] if a not in r.architects})
        if len(others) >= 2:
            wrong = list(rng.choice(others, 2, replace=False))
            a = r.architects[0]
            out.append((f"Who designed {this_en}?", f"Wie ontwierp {this_nl}?", [T(x, x) for x in [a] + wrong],
                        f"{a}, as Wikidata records.", f"{a}, volgens Wikidata.", {r.wiki_url}))
    if r.exact:
        far = [i for i in range(len(PERIODS)) if abs(i - r.period) >= 2]
        if len(far) >= 2:
            wrong = sorted(rng.choice(far, 2, replace=False))
            out.append((f"When was {this_en} built?", f"Wanneer werd {this_nl} gebouwd?",
                        [period_span(i) for i in [r.period] + wrong],
                        f"Built in {r.year}.", f"Gebouwd in {r.year}.", {year_source(r)}))
    if r.height >= 15:
        h = int(round(r.height))
        opts = [h, int(5 * round(h * 0.5 / 5)), int(5 * round(h * 1.8 / 5))]
        if len(set(opts)) == 3 and min(opts) > 0:
            out.append((f"How tall is {this_en}?", f"Hoe hoog is {this_nl}?",
                        [T(f"About {x} m", f"Ongeveer {x} m") for x in opts],
                        f"About {h} m to the roof, as the 3D BAG measures it.",
                        f"Ongeveer {h} m tot het dak, zoals de 3D BAG het meet.", {SRC_BAG}))
    return out


def kinds_for(r, pool, seed):
    k = {"find"}
    if named(r) and r.image:
        k.add("where")
    if r.exact:
        k.add("year")
    if choices(r, pool, seed):
        k.add("choice")
    return k


def assign(stops, theme, pool, seed):
    used, last, out = {}, None, []
    for _, r in stops.iterrows():
        ok = kinds_for(r, pool, seed)
        rank = lambda k: (used.get(k, 0), k == last and len(ok) > 1, theme.kinds.index(k) if k in theme.kinds else 9)
        k = min(sorted(ok), key=rank)
        used[k] = used.get(k, 0) + 1
        last = k
        out.append(k)
    return out


def clue(r):
    img = r.image
    return dict(thumb=img["thumb"], page=img.get("page"), artist=img.get("artist"), license=img.get("license"))


def write_step(kind, r, prev, pool, seed):
    """One step for stop r; prev is the last stop's (x, z), or None for the first (then the Dam is the reference)."""
    name_en, name_nl = (r.name_en, r.name_nl or r.name_en) if named(r) else (None, None)
    noun = r.noun
    src = set()
    if r.wiki_url and name_en:
        src.add(r.wiki_url)
    built = r.exact
    if kind == "where":
        reveal = tail(r, f"{name_en}." + (f" Built in {r.year}." if built else ""),
                      f"{name_nl}." + (f" Gebouwd in {r.year}." if built else ""), src)
        if built:
            src.add(year_source(r))
        return dict(kind="where", riddle=T(f"Where is {name_en}?", f"Waar staat {name_nl}?"), reveal=reveal,
                    clue=clue(r), bags=list(r.bags), sources=sorted(src))
    if kind == "year":
        src.add(year_source(r))
        ask = (T(f"{name_en}: when was it built?", f"{name_nl}: wanneer werd het gebouwd?") if name_en
               else T(f"When was this {noun['en']} built?", f"Wanneer werd {noun['this_nl']} gebouwd?"))
        reveal = tail(r, f"In {r.year}.", f"In {r.year}.", src)
        return dict(kind="year", ask=ask, year=int(r.year), reveal=reveal, bags=list(r.bags), sources=sorted(src))
    if kind == "choice":
        qs = choices(r, pool, seed)
        ask_en, ask_nl, options, rev_en, rev_nl, s = qs[0]
        src |= s
        return dict(kind="choice", ask=T(ask_en, ask_nl), options=options, reveal=tail(r, rev_en, rev_nl, src),
                    bags=list(r.bags), sources=sorted(src))
    # find
    src.add(SRC_BAG)
    photo = bool(r.image)
    this = "this" if photo else "a"
    if built:
        src.add(year_source(r))
        riddle = T(f"Find {this} {noun['en']} from {r.year}.",
                   f"Zoek {noun['this_nl'] if photo else 'een ' + noun['nl']} uit {r.year}.")
    else:
        riddle = T(f"Find {this} {noun['en']}, about {round(r.height)} m tall.",
                   f"Zoek {noun['this_nl'] if photo else 'een ' + noun['nl']} van ongeveer {round(r.height)} m hoog.")
    (d_en, d_nl), (c_en, c_nl) = direction(prev if prev is not None else (0.0, 0.0), (r.x, r.z))
    where_from = ("the last stop", "de vorige stop") if prev is not None else ("the Dam", "de Dam")
    hints = [T(f"It is about {d_en} {c_en} of {where_from[0]}.",
               f"Het staat ongeveer {d_nl} ten {c_nl} van {where_from[1]}.")]
    if built:
        hints.append(T(f"It is about {round(r.height)} m tall.", f"Het is ongeveer {round(r.height)} m hoog."))
    if name_en:
        rev_en, rev_nl = f"It is {name_en}.", f"Het is {name_nl}."
    else:
        rev_en = f"This one: about {round(r.height)} m tall" + (f", built in {r.year}." if built else ".")
        rev_nl = f"Deze: ongeveer {round(r.height)} m hoog" + (f", gebouwd in {r.year}." if built else ".")
    step = dict(kind="find", riddle=riddle, hints=hints, reveal=tail(r, rev_en, rev_nl, src), bags=list(r.bags),
                sources=sorted(src))
    if photo:
        step["clue"] = clue(r)
    return step


@WRITERS.register("facts")
def write(stops, theme, city, rng):
    """Steps for the stops in their order (stops: sourcing's rows, with `noun`)."""
    pool = dict(architects=sorted({a for aa in city.df.architects for a in aa}))
    seed = int(rng.integers(2 ** 31))
    kinds = assign(stops, theme, pool, seed)
    out, prev = [], None
    for k, (_, r) in zip(kinds, stops.iterrows()):
        out.append(write_step(k, r, prev, pool, seed))
        prev = (r.x, r.z)
    return out
