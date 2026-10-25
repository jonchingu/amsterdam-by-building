"""Step writing: each ordered stop becomes one quest step, in English and Dutch, from the data alone.

Nothing is invented. A step may say only what the directory holds for its building:
  - a year only when it is exact (BAG as recorded, an RCE year or a Wikidata inception; never an estimate),
  - its height (the 3D BAG roof the map draws), where it lies from the last stop or the start (measured on the map),
  - its name, photo, architect from Wikidata and Commons,
  - a noun the theme takes from a context-layer group ('church' for the faith layer's churches),
  - a checked 'Did you know' fact (s11_facts) or a layer story in both languages (s05_layers), word for word.
A choice's wrong options are other values of the same kind (another architect in the data, another period, another
height, an earlier stop of the quest), so they are wrong by construction; the right one is first, as quests.py
writes them, and the app shuffles them.

The choices a stop supports:
  - which of it and two earlier stops was built first (exact years, at least 15 years apart),
  - its period, against the other periods the quest's stops and the theme's pool hold; never when the theme admits
    one period only (an Amsterdam School quest would give the answer away),
  - who designed it (an architect with a Wikipedia article), against two other architects in the data,
  - how tall it is: the true height lowest, middle or highest of the three by the seed, the others spread by it.

Which kind each stop gets: the kinds its data allows (where: a name and a photo; year: an exact year; choice: one of
the above), the least used so far first, then the theme's order shuffled a little by the seed, never the same kind
twice running when another is possible.
"""
import math
import re

import numpy as np

from ..periods import PERIODS
from .registry import WRITERS

SRC_BAG = "https://3dbag.nl"
SRC_RCE = "https://monumentenregister.cultureelerfgoed.nl"
COMPASS = [("north", "noorden"), ("north-east", "noordoosten"), ("east", "oosten"), ("south-east", "zuidoosten"),
           ("south", "zuiden"), ("south-west", "zuidwesten"), ("west", "westen"), ("north-west", "noordwesten")]
DAM = dict(xy=(0.0, 0.0), en="the Dam", nl="de Dam")


def T(en, nl):
    return dict(en=en, nl=nl)


# ---------- Dutch articles for building names ----------
DE = re.compile(r"(kerk|kapel|toren|synagoge|brug|school|beurs|poort|waag|markt|flat|molen|sluis|bank|bibliotheek"
                r"|schouwburg|fabriek|kazerne|bioscoop|zaal)$")
HET = re.compile(r"(huis|museum|station|paleis|gebouw|hofje|theater|hotel|instituut|magazijn|kantoor|blok|complex"
                 r"|schip|bad|park|plein)$")


def nl_article(name):
    """'de', 'het' or '' for a Dutch building name: by its last word, its (…) left out; '' if it has one already."""
    core = re.sub(r"\s*\(.*?\)\s*$", "", name or "").strip()
    if not core or re.match(r"(?i)(de|het|'t|een)\s", core):
        return ""
    last = core.split()[-1].lower()
    return "de" if DE.search(last) else "het" if HET.search(last) else ""


def nl_name(name, cap=False):
    """The name as it reads in a Dutch sentence: 'de Westerkerk', 'het Scheepvaarthuis'; cap for a sentence start."""
    art = nl_article(name)
    if not art:
        return name
    return f"{art.capitalize() if cap else art} {name}"


# ---------- measuring ----------
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


def names(r):
    """(en, nl as in a sentence, nl at a sentence start) for a named stop, else Nones."""
    if not named(r):
        return None, None, None
    nl = r.name_nl or r.name_en
    return r.name_en, nl_name(nl), nl_name(nl, cap=True)


# ---------- choices ----------
def theme_periods(cands):
    """The periods the theme's pool holds (at least a tenth of it each): the periods a player could think of."""
    if cands is None or not len(cands):
        return set()
    pool = cands[cands["general"]] if "general" in cands else cands
    share = pool.period.value_counts(normalize=True)
    return {int(p) for p, f in share.items() if f >= 0.1}


def choices(r, i, rows, pool, seed, eras):
    """The choice questions stop i (row r of rows, the quest's stops in order) supports:
    {type: (ask-en, ask-nl, options, reveal-en, reveal-nl, sources)}. eras: the theme's periods (theme_periods).
    The wrong options depend on the seed, the building and the stops before it only."""
    rng = np.random.default_rng([seed, int(r.primary)])
    out = {}
    en, nl, _ = names(r)
    this_en = en or f"this {r.noun['en']}"
    this_nl = nl or r.noun["this_nl"]

    before = [(j, b) for j, b in enumerate(rows[:i]) if b.exact]
    if r.exact and len(before) >= 2:
        pairs = [(a, b) for x, a in enumerate(before) for b in before[x + 1:]
                 if min(abs(a[1].year - b[1].year), abs(a[1].year - r.year), abs(b[1].year - r.year)) >= 15]
        if pairs:
            (ja, a), (jb, b) = pairs[rng.integers(len(pairs))]
            label = lambda j, s: (T(s.name_en, s.name_nl or s.name_en) if named(s)
                                  else T(f"Stop {j + 1}", f"Stop {j + 1}"))
            here = T(en, r.name_nl or en) if en else T(f"This {r.noun['en']}", r.noun["this_nl"].capitalize())
            opts = [(r.year, here, year_source(r)), (a.year, label(ja, a), year_source(a)),
                    (b.year, label(jb, b), year_source(b))]
            if len({o[1]["en"] for o in opts}) == 3 and len({o[1]["nl"] for o in opts}) == 3:
                opts.sort(key=lambda o: o[0])
                out["oldest"] = ("Which of these was built first?", "Welke hiervan werd het eerst gebouwd?",
                                 [o[1] for o in opts],
                                 "Oldest first: " + "; ".join(f"{o[1]['en']}, {o[0]}" for o in opts) + ".",
                                 "Oudste eerst: " + "; ".join(f"{o[1]['nl']}, {o[0]}" for o in opts) + ".",
                                 {o[2] for o in opts})
    if r.exact and len(eras) > 1:
        quest = {int(b.period) for b in rows if b.exact}
        other = sorted((eras | quest) - {int(r.period)}, key=lambda p: (abs(p - r.period), p))[:2]
        if other:
            out["period"] = (f"In which period was {this_en} built?", f"In welke periode werd {this_nl} gebouwd?",
                             [period_span(p) for p in [int(r.period)] + sorted(other)],
                             f"Built in {r.year}.", f"Gebouwd in {r.year}.", {year_source(r)})
    if r.architects and r.wiki_url:
        others = sorted({a for a in pool["architects"] if a not in r.architects})
        if len(others) >= 2:
            wrong = list(rng.choice(others, 2, replace=False))
            a = r.architects[0]
            out["architect"] = (f"Who designed {this_en}?", f"Wie ontwierp {this_nl}?", [T(x, x) for x in [a] + wrong],
                                f"{a}, as Wikidata records.", f"{a}, volgens Wikidata.", {r.wiki_url})
    if r.height >= 15:
        h = int(round(r.height))
        opts = height_options(h, rng)
        if opts:
            out["height"] = (f"How tall is {this_en}?", f"Hoe hoog is {this_nl}?",
                             [T(f"About {x} m", f"Ongeveer {x} m") for x in opts],
                             f"About {h} m to the roof, as the 3D BAG measures it.",
                             f"Ongeveer {h} m tot het dak, zoals de 3D BAG het meet.", {SRC_BAG})
    return out


def height_options(h, rng):
    """[h, wrong, wrong]: h is the lowest, middle or highest of the three (by the seed), the wrong ones at seeded
    factors, rounded to 5 m and at least 5 m from h and each other. None when they don't come out apart."""
    pos = int(rng.integers(3))
    if pos == 0:  # h lowest
        f = [rng.uniform(1.3, 1.6), rng.uniform(1.8, 2.3)]
    elif pos == 2:  # h highest
        f = [rng.uniform(0.35, 0.5), rng.uniform(0.6, 0.75)]
    else:
        f = [rng.uniform(0.45, 0.7), rng.uniform(1.4, 1.9)]
    wrong = [int(5 * round(h * x / 5)) for x in f]
    vals = [h] + wrong
    if min(vals) <= 0 or min(abs(a - b) for x, a in enumerate(vals) for b in vals[x + 1:]) < 5:
        return None
    return vals


def pick_choice(qs, used, rng):
    """The choice to ask: one not asked yet in this quest, the era ones first (which was built first, then the
    period), else by the seed."""
    types = list(qs)
    era = {"oldest": 0, "period": 1}
    order = {t: (t in used, era.get(t, 2), x) for x, t in enumerate(rng.permutation(types))}
    return min(types, key=lambda t: order[t])


# ---------- kinds ----------
def kinds_for(r, qs):
    k = {"find"}
    if named(r) and r.image:
        k.add("where")
    if r.exact:
        k.add("year")
    if qs:
        k.add("choice")
    return k


def assign(rows, qs, theme, rng):
    """A kind per stop: the least used first, then the theme's order with a seeded nudge, never twice running."""
    prio = {k: theme.kinds.index(k) + rng.uniform(0, 2.5) for k in theme.kinds}
    used, last, out = {}, None, []
    for r, q in zip(rows, qs):
        ok = kinds_for(r, q)
        rank = lambda k: (used.get(k, 0), k == last and len(ok) > 1, prio.get(k, 9))
        k = min(sorted(ok), key=rank)
        used[k] = used.get(k, 0) + 1
        last = k
        out.append(k)
    return out


def clue(r):
    img = r.image
    return dict(thumb=img["thumb"], page=img.get("page"), artist=img.get("artist"), license=img.get("license"))


def write_step(kind, r, ref, choice=None):
    """One step for stop r; ref: {xy, en, nl}, where the hint measures from (the last stop, the start or the Dam);
    choice: the choice question for a choice step."""
    name_en, name_nl, name_nl_cap = names(r)
    noun = r.noun
    src = set()
    if r.wiki_url and name_en:
        src.add(r.wiki_url)
    built = r.exact
    if kind == "where":
        reveal = tail(r, f"{name_en}." + (f" Built in {r.year}." if built else ""),
                      f"{name_nl_cap}." + (f" Gebouwd in {r.year}." if built else ""), src)
        if built:
            src.add(year_source(r))
        step = dict(kind="where", riddle=T(f"Where is {name_en}?", f"Waar staat {name_nl}?"), reveal=reveal,
                    clue=clue(r), bags=list(r.bags), sources=sorted(src))
    elif kind == "year":
        src.add(year_source(r))
        ask = (T(f"{name_en}: when was it built?", f"Wanneer werd {name_nl} gebouwd?") if name_en
               else T(f"When was this {noun['en']} built?", f"Wanneer werd {noun['this_nl']} gebouwd?"))
        reveal = tail(r, f"In {r.year}.", f"In {r.year}.", src)
        step = dict(kind="year", ask=ask, year=int(r.year), reveal=reveal, bags=list(r.bags), sources=sorted(src))
    elif kind == "choice":
        ask_en, ask_nl, options, rev_en, rev_nl, s = choice
        src |= s
        step = dict(kind="choice", ask=T(ask_en, ask_nl), options=options, reveal=tail(r, rev_en, rev_nl, src),
                    bags=list(r.bags), sources=sorted(src))
    else:  # find
        src.add(SRC_BAG)
        photo = bool(r.image)
        this = "this" if photo else "a"
        if built:
            src.add(year_source(r))
            riddle = T(f"Find {this} {noun['en']} from {r.year}.",
                       f"Zoek {noun['this_nl'] if photo else 'een ' + noun['nl']} uit {r.year}.")
        else:
            what_nl = noun["this_nl"] if photo else "een " + noun["nl"]
            riddle = T(f"Find {this} {noun['en']}, about {round(r.height)} m tall.",
                       f"Zoek {what_nl} van ongeveer {round(r.height)} m hoog.")
        (d_en, d_nl), (c_en, c_nl) = direction(ref["xy"], (r.x, r.z))
        hints = [T(f"It is about {d_en} {c_en} of {ref['en']}.",
                   f"Het staat ongeveer {d_nl} ten {c_nl} van {ref['nl']}.")]
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
    role = getattr(r, "role", None)
    if isinstance(role, str):
        step["role"] = role
    return step


@WRITERS.register("facts")
def write(stops, theme, city, rng, start=None, cands=None):
    """Steps for the stops in their order (stops: sourcing's rows, with `noun`, and the selector's `role`).
    start: {xy, en, nl}, where the walk begins (the first hint measures from it), or None (from the Dam).
    cands: the theme's candidates, for the periods a player could think of."""
    pool = dict(architects=sorted({a for aa in city.df.architects for a in aa}))
    seed = int(rng.integers(2 ** 31))
    rows = [r for _, r in stops.iterrows()]
    eras = theme_periods(cands)
    qs = [choices(r, i, rows, pool, seed, eras) for i, r in enumerate(rows)]
    kinds = assign(rows, qs, theme, rng)
    out, ref, used = [], start or DAM, set()
    for k, r, q in zip(kinds, rows, qs):
        choice = None
        if k == "choice":
            t = pick_choice(q, used, rng)
            used.add(t)
            choice = q[t]
        out.append(write_step(k, r, ref, choice))
        ref = dict(xy=(r.x, r.z), en="the last stop", nl="de vorige stop")
    return out
