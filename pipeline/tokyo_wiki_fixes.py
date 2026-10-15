"""Wikidata matches set by hand, checked against the map and the item's article.

FIXES maps a Wikidata item to the PLATEAU building id (建物ID) it describes, or to None to leave it out.
Add an entry when tokyo_s02_wiki puts an item on the wrong building; say why in a comment.
"""
FIXES: dict[str, str | None] = {
    # Tokyo Station: the point falls on a platform roof; the Marunouchi station building is the 320 m long,
    # 37 m high block on the west side (PLATEAU files it under the police box in front, 丸の内警察署東京駅前交番).
    "Q283196": "13101-bldg-871",
    # Ōoku, the shogun's inner quarters at Edo Castle: gone since the Meiji era; the point lands on a shed.
    "Q1064983": None,
    # Kyu Shiba Rikyu Garden is a garden, not the 3 m hut inside it.
    "Q3266874": None,
}
