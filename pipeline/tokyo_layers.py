"""Tokyo's context layers: each a set of buildings with a story, in the shape of Amsterdam's layers.py.

A layer has one or more groups, each drawn in its own colour. A source function returns {PLATEAU id: group key},
{PLATEAU id: (group key, story)} or {PLATEAU id: [(group key, story), ...]} for a building in several groups.
tokyo_s03_layers.py turns them into web/data/tokyo/layers.json for the viewer.

Every layer here rests on the Wikidata items matched to PLATEAU buildings by tokyo_s02_wiki.py (CC0).
"""
import json
from functools import cache
from pathlib import Path

from .tokyo_wiki_fixes import COMPLETED

LAYERS = []
WIKI = Path("web/data/tokyo/wiki.json")


def layer(**meta):
    def wrap(fn):
        LAYERS.append(dict(meta, source_fn=fn))
        return fn
    return wrap


@cache
def wiki() -> dict:
    return json.loads(WIKI.read_text())


def buildings() -> dict[str, dict]:
    return wiki()["buildings"]


def year_of(b: dict):
    """The present building's year, when known: tokyo_s02_wiki has applied COMPLETED; a None there means unknown."""
    if b["wd"] in COMPLETED and COMPLETED[b["wd"]] is None:
        return None
    y = b.get("year")
    return y if y and y >= 1868 else None


def name_of(b: dict) -> str:
    return b.get("en") or b.get("ja") or ""


# ---------- layers ----------

@layer(
    id="heritage", section="Architecture", title="Protected heritage", era="All periods",
    text=("Japan protects buildings at three levels. The nation designates National Treasures and Important Cultural "
          "Properties and registers Tangible Cultural Properties; Tokyo Metropolis and each ward keep lists of their "
          "own. Few buildings in central Tokyo came through the 1923 earthquake and the air raids of 1945, so the "
          "protected ones are rare."),
    caveat=("Designations recorded on Wikidata for the buildings matched to it. Tokyo's and the wards' own lists are "
            "not in yet."),
    source=("Wikidata, heritage designation (P1435)", "https://www.wikidata.org/wiki/Property:P1435"),
    groups=lambda: [(str(k), label) for k, label in enumerate(wiki()["heritageLevels"])],
)
def heritage():
    out = {}
    for pid, b in buildings().items():
        if b.get("heritage"):
            best = b["heritage"][0]  # sorted highest level first
            names = "; ".join(f"{en} {ja}" if ja and ja != en else en for en, ja, _ in b["heritage"][:3])
            # The group already names a single national designation; spell it out when there is more to say.
            tell = len(b["heritage"]) > 1 or best[2] >= 3
            out[pid] = (str(best[2]), f"{names}." if tell else None)
    return out


# Architects by their Wikidata id. A building by named architects joins each of their groups; one by a firm alone
# joins the firms. Owners and clients that Wikidata lists as architects are left out.
ARCHITECTS = [
    ("pioneers", "Meiji to early Shōwa architects", {
        "Q1186865", "Q898689", "Q1050457", "Q68214", "Q73673", "Q11248778", "Q11384181", "Q11261704", "Q11515378",
        "Q11366254", "Q8015576", "Q11450218", "Q5676395", "Q8056122", "Q11671637", "Q15059281", "Q54293280",
        "Q11369625", "Q17193360", "Q11518287", "Q136324165", "Q59134809", "Q11360630", "Q1340974",
    }),
    ("modernists", "Postwar modernists", {
        "Q151794", "Q129938", "Q388272", "Q7813199", "Q3297694", "Q2857569", "Q10856322", "Q358502", "Q312827",
        "Q3155639", "Q982551", "Q11470304", "Q11579381", "Q11436810", "Q11533077", "Q11473564", "Q6203216",
        "Q17214681", "Q11482510", "Q79018012", "Q130949346", "Q11385051", "Q3070821", "Q11466867",
    }),
    ("contemporary", "Contemporary Japanese architects", {
        "Q208220", "Q333585", "Q117115854", "Q725462", "Q139882163", "Q1713226", "Q526725", "Q1396719", "Q11496979",
        "Q11496991", "Q11370604", "Q11550012", "Q11411623", "Q60229825", "Q11599093", "Q11393855", "Q11534458",
        "Q9099983",
    }),
    ("abroad", "Architects from abroad", {
        "Q309483", "Q11815494", "Q212487", "Q77311", "Q332610", "Q347215", "Q3184588", "Q98526232", "Q96002089",
        "Q122363", "Q1797462", "Q459464", "Q1999287", "Q70696", "Q125506139", "Q190148", "Q11682592", "Q10329451",
        "Q237412", "Q214317", "Q316413", "Q375674", "Q932801", "Q317164",
    }),
    ("firms", "Design firms and builders", {
        "Q2804130", "Q11509101", "Q3116531", "Q11357096", "Q11369636", "Q1081154", "Q304962", "Q3178370", "Q7496874",
        "Q11309024", "Q1770691", "Q11236098", "Q11527026", "Q11630511", "Q11466063", "Q11285799", "Q11450207",
        "Q11532052", "Q11424955", "Q17212048", "Q85877124", "Q11538717", "Q384730", "Q11527014", "Q11628762",
        "Q11496515", "Q11368479", "Q11643690",
    }),
]
# Wikidata credits these architects on an item whose matched building is not their work.
NOT_THEIRS = {
    "Q283196": {"Q77311", "Q70696"},  # Tokyo Station: Jahn and Sobek designed the GranRoof on the Yaesu side
    "Q269261": {"Q8056122"},  # Sompo Japan Building, finished 1976: Uchida Yoshikazu died in 1972
}


@layer(
    id="architects", section="Architecture", title="Architects", era="1872–today",
    text=("Tokyo's first Western buildings were designed by foreigners such as Ende and Böckmann, and soon by the "
          "Japanese pupils of Josiah Conder: Tatsuno Kingo's Bank of Japan and Tokyo Station, Katayama Tōkuma's Akasaka "
          "Palace. After the war Kenzō Tange and his generation made Tokyo a centre of modern architecture. Today the "
          "large design firms and builders put up most of its towers."),
    caveat=("Architects as Wikidata records them, for the buildings matched to it. Many landmarks are plain blocks "
            "(LOD1) in the PLATEAU model, Yoyogi National Gymnasium among them."),
    source=("Wikidata, architect (P84)", "https://www.wikidata.org/wiki/Property:P84"),
    groups=[(k, label) for k, label, _ in ARCHITECTS],
)
def architects():
    group_of = {q: k for k, _, qs in ARCHITECTS for q in qs}
    out = {}
    for pid, b in buildings().items():
        named = [(en, q) for en, _, q in b.get("architects", []) if q in group_of
                 and q not in NOT_THEIRS.get(b["wd"], ())]
        people = [(en, q) for en, q in named if group_of[q] != "firms"]
        credited = people or named
        if not credited:
            continue
        year = year_of(b)
        story = ", ".join(en for en, _ in credited[:3]) + (f", {year}." if year else ".")
        out[pid] = [(k, story) for k in dict.fromkeys(group_of[q] for _, q in credited)]
    return out


# Awards by Wikidata id. Wikidata records the year received for only a few.
PRIZES = [
    ("aij", "Architectural Institute of Japan Prize", {"Q11508083", "Q18458352"}),
    ("bcs", "BCS Prize", {"Q10854444"}),
    ("gooddesign", "Good Design Award", {"Q724647"}),
    ("other", "Other architecture awards", {"Q17221741", "Q10862323", "Q6048211", "Q11391917", "Q33965099"}),
]


@layer(
    id="prizes", section="Architecture", title="Prize-winning buildings", era="1949–today",
    text=("Japan's architecture prizes go to finished buildings. The Architectural Institute of Japan has given its "
          "prize to a few works a year since 1949; the BCS Prize, since 1960, honours a building together with its "
          "client and its builder; the Good Design Award covers buildings as well as products."),
    caveat="Awards recorded on Wikidata, which lists far fewer than were given.",
    source=("Wikidata, award received (P166)", "https://www.wikidata.org/wiki/Property:P166"),
    groups=[(k, label) for k, label, _ in PRIZES],
)
def prizes():
    group_of = {q: k for k, _, qs in PRIZES for q in qs}
    out = {}
    for pid, b in buildings().items():
        won = [(en, q, year) for en, _, q, year in b.get("awards", []) if q in group_of]
        if not won:
            continue
        story = "; ".join(f"{en} {year}" if year else en for en, _, year in won) + "."
        tell = len(won) > 1 or any(year for *_, year in won) or group_of[won[0][1]] == "other"
        out[pid] = [(k, story if tell else None) for k in dict.fromkeys(group_of[q] for _, q, _ in won)]
    return out
