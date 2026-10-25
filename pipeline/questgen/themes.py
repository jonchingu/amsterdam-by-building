"""Themes and sourcing: what a quest is about, as filters and scores over the building directory (city.py).

A theme is data: `require` says which buildings may be a checkpoint, `prefer` weighs the ones that fit best, and
`nouns` names a checkpoint in a riddle only where the data says so (a building in the 'Church' group of the faith
layer is a church; anything else is a building). Conditions combine with & | ~.

Add a theme with THEMES.register(Theme(...)). The group keys are the context layers' (layers.py, s05_layers):
g:<layer id>:<group key>, or <layer id>:* for any group of a layer.
"""
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .registry import SOURCES, THEMES


def T(en, nl):
    return dict(en=en, nl=nl)


def N(en, nl, het=False):
    """A noun for riddles. het: Dutch neuter, so 'dit gebouw' but 'deze kerk'."""
    return dict(en=en, nl=nl, this_nl=("dit " if het else "deze ") + nl)


# ---------- conditions ----------
class Cond:
    def mask(self, df) -> pd.Series:
        raise NotImplementedError

    def __and__(self, o):
        return All(self, o)

    def __or__(self, o):
        return Any(self, o)

    def __invert__(self):
        return Not(self)


def _false(df):
    return pd.Series(False, index=df.index)


@dataclass(frozen=True)
class Years(Cond):
    lo: int
    hi: int
    exact: bool = False

    def mask(self, df):
        m = df.year.between(self.lo, self.hi)
        return m & df.exact if self.exact else m

    def __str__(self):
        return f"built {self.lo}–{self.hi}" + (" (exact year)" if self.exact else "")


@dataclass(frozen=True)
class Group(Cond):
    key: str  # "layer:group" or "layer:*"

    def mask(self, df):
        layer, group = self.key.split(":", 1)
        cols = [c for c in df.columns if c.startswith(f"g:{layer}:")] if group == "*" else [f"g:{self.key}"]
        cols = [c for c in cols if c in df]
        return df[cols].any(axis=1) if cols else _false(df)

    def __str__(self):
        return f"in {self.key}"


@dataclass(frozen=True)
class Taller(Cond):
    metres: float

    def mask(self, df):
        return df.height >= self.metres

    def __str__(self):
        return f"≥ {self.metres:g} m"


@dataclass(frozen=True)
class Monument(Cond):
    def mask(self, df):
        return df.monument.astype(bool)

    def __str__(self):
        return "monument"


@dataclass(frozen=True)
class Text(Cond):
    """A regular expression over the names, styles and architects Wikidata gives (case-insensitive)."""
    pattern: str

    def mask(self, df):
        rx = re.compile(self.pattern, re.I)
        txt = (df.name_en.fillna("") + "|" + df.name_nl.fillna("") + "|" + df.styles.map("|".join) + "|"
               + df.architects.map("|".join))
        return txt.map(lambda s: bool(rx.search(s)))

    def __str__(self):
        return f"text /{self.pattern}/"


@dataclass(frozen=True)
class Has(Cond):
    """name, photo, fact, story, wiki, architect"""
    what: str

    def mask(self, df):
        col = dict(name="name_en", photo="image", fact="fact", wiki="wiki_url")
        if self.what in col:
            return df[col[self.what]].notna()
        if self.what == "story":
            return df.stories.map(bool)
        if self.what == "architect":
            return df.architects.map(bool)
        raise ValueError(self.what)

    def __str__(self):
        return f"has {self.what}"


@dataclass(frozen=True)
class Near(Cond):
    x: float
    z: float
    r: float

    def mask(self, df):
        return np.hypot(df.x - self.x, df.z - self.z) <= self.r

    def __str__(self):
        return f"within {self.r:g} m of ({self.x:g}, {self.z:g})"


@dataclass(frozen=True)
class All(Cond):
    conds: tuple

    def __init__(self, *conds):
        object.__setattr__(self, "conds", conds)

    def mask(self, df):
        m = pd.Series(True, index=df.index)
        for c in self.conds:
            m &= c.mask(df)
        return m

    def __str__(self):
        return " and ".join(f"({c})" if isinstance(c, Any) else str(c) for c in self.conds)


@dataclass(frozen=True)
class Any(Cond):
    conds: tuple

    def __init__(self, *conds):
        object.__setattr__(self, "conds", conds)

    def mask(self, df):
        m = _false(df)
        for c in self.conds:
            m |= c.mask(df)
        return m

    def __str__(self):
        return " or ".join(str(c) for c in self.conds)


@dataclass(frozen=True)
class Not(Cond):
    cond: Cond

    def mask(self, df):
        return ~self.cond.mask(df)

    def __str__(self):
        return f"not ({self.cond})"


# ---------- themes ----------
BUILDING = N("building", "gebouw", het=True)


@dataclass(frozen=True)
class Theme:
    id: str
    title: dict
    intro: dict
    require: Cond
    prefer: tuple = ()               # (Cond, weight)
    nouns: tuple = ()                # (Cond, N(...)): the first that holds names the checkpoint in riddles
    kinds: tuple = ("find", "year", "choice", "where")  # step kinds, most wanted first
    level: int = 2
    stops: int = 6
    radius: float = 1200.0           # the stops lie within twice this of each other
    gap: float = 60.0                # and at least this far apart
    noun: dict = field(default_factory=lambda: BUILDING)


AS = ("Amsterdamse school", "Amsterdam School")

for theme in [
    Theme("amsterdam-school", T("Amsterdam School", "Amsterdamse School"),
          T("Brick that bends round corners, towers on housing blocks, windows like portholes: the Amsterdam School "
            "built the city's new districts between the wars.",
            "Baksteen die om de hoek buigt, torens op woonblokken, ramen als patrijspoorten: de Amsterdamse School "
            "bouwde tussen de oorlogen de nieuwe wijken van de stad."),
          require=Years(1910, 1945) & (Group("styles:as") | Group("architects:as") | Text("|".join(AS))),
          prefer=((Group("planned:Plan Zuid"), 1.0), (Group("housing:woningwet"), 1.0), (Monument(), 1.0),
                  (Has("architect"), 1.0)),
          kinds=("find", "choice", "year", "where")),
    Theme("golden-age-canals", T("Golden Age canals", "Grachten van de Gouden Eeuw"),
          T("Merchants' houses on the canal ring, dug and built up in the seventeenth century. Read their age in "
            "their gables.",
            "Koopmanshuizen aan de grachtengordel, gegraven en bebouwd in de zeventiende eeuw. Lees hun leeftijd af "
            "aan hun gevels."),
          require=Group("unesco:Kernzone") & Years(1600, 1700),
          prefer=((Group("gables:*"), 1.5), (Monument(), 1.0), (Has("fact"), 1.0), (Has("name"), 1.0)),
          nouns=((Group("faith:worship"), N("church", "kerk")),
                 (Group("gables:trap"), N("house with a stepped gable", "huis met een trapgevel", het=True)),
                 (Group("gables:hals"), N("house with a neck gable", "huis met een halsgevel", het=True)),
                 (Group("gables:klok"), N("house with a bell gable", "huis met een klokgevel", het=True)),
                 (Group("trade:pakhuis"), N("warehouse", "pakhuis", het=True))),
          kinds=("year", "find", "choice", "where"), radius=900.0, gap=40.0),
    Theme("churches-towers", T("Churches and towers", "Kerken en torens"),
          T("Spires, domes and towers: the landmarks the city has steered by for centuries.",
            "Spitsen, koepels en torens: de bakens waar de stad al eeuwen op koerst."),
          require=(Group("faith:worship") | Group("faith:synagogue")
                   | Text(r"\b(kerk|church|toren|tower|kapel|chapel|synago\w*|basiliek|basilica)\b")),
          prefer=((Taller(40), 2.0), (Monument(), 1.0), (Has("fact"), 1.0), (Has("photo"), 1.0)),
          nouns=((Group("faith:synagogue"), N("synagogue", "synagoge")),
                 (Group("faith:worship"), N("church", "kerk"))),
          kinds=("where", "find", "year", "choice"), level=1, stops=5, radius=1600.0, gap=120.0),
    Theme("post-war-rebuild", T("Rebuilding after the war", "Herbouw na de oorlog"),
          T("Where bombs fell, and where the city built anew after 1945: new blocks, garden cities and the art the "
            "city set into their walls.",
            "Waar bommen vielen, en waar de stad na 1945 opnieuw bouwde: nieuwe blokken, tuinsteden en de kunst die "
            "de stad in hun muren zette."),
          require=Years(1945, 1975) & (Group("noord1943:rebuilt") | Group("war:*") | Group("wallart:*")
                                      | Group("planned:Western garden cities")),
          prefer=((Group("noord1943:rebuilt"), 2.0), (Group("wallart:top"), 1.5), (Group("wallart:*"), 1.0),
                  (Has("story"), 1.0)),
          kinds=("find", "year", "choice", "where"), level=2, stops=5, radius=1500.0),
    Theme("warehouses", T("Warehouses and the companies", "Pakhuizen en de compagnieën"),
          T("Amsterdam stored the goods of the world in its houses: warehouses with hoisting beams and shutters, "
            "and the buildings of the East and West India Companies.",
            "Amsterdam sloeg de goederen van de wereld op in zijn huizen: pakhuizen met hijsbalken en luiken, en de "
            "gebouwen van de Oost- en West-Indische Compagnie."),
          require=Group("trade:*"),
          prefer=((Group("trade:company"), 2.0), (Has("fact"), 1.0), (Has("name"), 1.0), (Monument(), 0.5)),
          nouns=((Group("trade:pakhuis"), N("warehouse", "pakhuis", het=True)),),
          kinds=("find", "year", "choice", "where"), stops=5, radius=1000.0, gap=50.0),
    Theme("skyline", T("The new skyline", "De nieuwe skyline"),
          T("Towers from the Bijlmer to the Zuidas and across the IJ: the city grew up as well as out.",
            "Torens van de Bijlmer tot de Zuidas en over het IJ: de stad groeide de hoogte in, niet alleen de breedte."),
          require=Years(1965, 2100) & Taller(60),
          prefer=((Taller(100), 2.0), (Has("name"), 1.0), (Has("photo"), 1.0), (Group("arcam:*"), 1.0)),
          kinds=("choice", "where", "find", "year"), level=1, stops=5, radius=2500.0, gap=150.0),
]:
    THEMES.register(theme.id, theme)


# ---------- sourcing ----------
@SOURCES.register("attributes")
def from_attributes(theme, city, area=None):
    """Every checkpoint the theme requires (within the area, a Cond, if given), with `fit` in [0, 1] from the
    theme's preferences and the `noun` the data supports."""
    df = city.df
    m = theme.require.mask(df)
    if area is not None:
        m &= area.mask(df)
    c = df[m].copy()
    total = sum(w for _, w in theme.prefer)
    c["fit"] = sum(w * p.mask(c).astype(float) for p, w in theme.prefer) / total if total else 1.0
    noun = pd.Series([theme.noun] * len(c), index=c.index, dtype=object)
    for cond, n in reversed(theme.nouns):  # the first that holds wins
        hit = cond.mask(c)
        noun[hit] = [n] * int(hit.sum())
    c["noun"] = noun
    return c
