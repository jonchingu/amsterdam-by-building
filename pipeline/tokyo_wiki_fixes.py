"""Wikidata matches set by hand, checked against the map and the item's article.

FIXES maps a Wikidata item to the PLATEAU building id (建物ID) it describes, or to None to leave it out.
Add an entry when tokyo_s02_wiki puts an item on the wrong building; say why in a comment.

COMPLETED gives the year the present building was finished, for the card, the Era colouring and the layers' stories.
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

# Year the present building was finished, where Wikidata's date belongs to the institution, the shrine's founding or an
# earlier building on the site, or is missing. None: no reliable year for the building; the card keeps Wikidata's date
# as "built or founded", the layers give none. Written without access to Wikipedia from the cloud environment, so check
# an entry before relying on it.
COMPLETED: dict[str, int | None] = {
    "Q1047097": 2009,   # Nezu Museum: Kuma's building; the museum opened in 1941
    "Q11249110": 2007,  # Suntory Museum of Art, in Tokyo Midtown; the museum dates from 1961
    "Q11524973": 1974,  # Tokio Marine Nichido Building; the company's first building here was 1918
    "Q48521463": 2003,  # Baisō-in: Kuma's rebuilding; the temple dates from 1643
    "Q11635471": 2010,  # Akagi Shrine: Kuma's rebuilding
    "Q3329598": 1927,   # Okura Museum of Art (Okura Shūkokan); the museum was founded in 1917
    "Q943255": 1934,    # Tsukiji Hongan-ji: Itō Chūta's hall; the temple dates from 1617
    "Q743773": 1933,    # Teien Art Museum: the Prince Asaka residence; the museum opened in 1983
    "Q1359908": 1969,   # National Museum of Modern Art: the building in Kitanomaru; the museum dates from 1952
    "Q477675": 1961,    # National Diet Library, main building; the library dates from 1948
    "Q115212362": 1938, # Minato City Local History Museum: the former Institute of Public Health
    "Q11533289": 1941,  # Hayashi Fumiko Memorial Hall: her house; the museum opened in 1992
    "Q11465792": 1937,  # Hilltop Hotel: built as a house; the hotel opened in 1954
    "Q11561694": 1980,  # Shoto Museum of Art
    "Q386246": 1964,    # Nippon Budōkan
    "Q183536": 1958,    # Tokyo Tower: finished in December 1958
    "Q555255": 1909,    # Akasaka Palace
    "Q135552735": 1970, # Kuwait Embassy
    "Q994171": 1966,    # Imperial Theatre: the present building; the first opened in 1911
    "Q11337851": 2019,  # The Okura Tokyo: rebuilt; the first hotel opened in 1962
    "Q11473108": None,  # Taro Okamoto Memorial Museum: his house and studio; the museum opened in 1998
    "Q287165": None,    # Meiji Jingū: founded 1920, its main buildings rebuilt after 1945
    "Q11646485": None,  # Kotohira-gū, Toranomon
    "Q3342690": None,   # Nogi Shrine
    "Q242803": None,    # Yasukuni Shrine
    "Q3503320": None,   # Suitengū
    "Q11607671": None,  # Prime Minister's residence
    "Q4410425": None,   # Shinbashi Enbujō: rebuilt since 1922
    "Q84713925": None,  # Shinjuku Gyo-en greenhouse: rebuilt since 1958
    "Q3011415": None,   # DN Tower 21
}
