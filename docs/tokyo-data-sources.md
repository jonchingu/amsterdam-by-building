# Tokyo data sources, compared with Amsterdam

Amsterdam, building by building, rests on a construction year for every building. For Tokyo that is out of reach
for now. PLATEAU's 2020 model of the 23 wards has no construction year at all, and the newer releases are hosted on
`assets.cms.plateau.reearth.io`, which the cloud environment's network policy blocks. Tokyo can therefore not be
coloured by age building by building. What it can get is a year for the well-known buildings, from Wikidata, and
several Amsterdam-style colourings straight from PLATEAU.

Reachability was tested from the cloud environment this pipeline was built in; a local machine can reach more.

| Amsterdam feature | Tokyo equivalent | Reachable from the cloud environment? | How it joins to a building |
|---|---|---|---|
| Names, photos, Wikipedia (`s06_wiki`) | Wikidata. Over the five central wards: 3,130 buildings, towers and stations, of which 1,442 match a PLATEAU building: 638 with a year, 1,221 with a photo, 252 with an architect, 1,335 with a building type, 50 with an architectural style, 493 with an official website, 900 with a Commons photo category. | ✅ Wikidata's query service. Wikipedia and Commons are blocked, but the browser loads Commons photos itself, so the pipeline only needs file names. | The building whose footprint contains the Wikidata coordinate, or the nearest within 40 m. A Wikidata height or floor count that disagrees ranks a candidate lower. Stations only match inside a footprint. Done by `tokyo_s02_wiki`; wrong matches are corrected by hand in `tokyo_wiki_fixes.py`. |
| Construction year and periods | Wikidata's inception or opening date, for landmarks only (Yusen Building 1923, Tokyo Tower 1957). For temples and shrines it is the founding year, so the viewer says "Built or founded". | ⚠️ Landmarks only | Same join as above. The viewer's Era colouring uses the reigns: Edo and earlier, Meiji, Taishō, early and postwar Shōwa, Heisei, Reiwa. |
| Floors colouring | PLATEAU floors above ground (地上階数) | ✅ In the downloaded tiles | Already per building |
| Energy-label colouring | Flood depth under the assumed maximum rainfall (想定最大規模), per river basin: Arakawa, Kanda, Jōnan rivers, Kōtō inner rivers. Also fire-prevention zones (防火・準防火地域), height districts (高度地区) and steep-slope landslide zones. Amsterdam has nothing like these. | ✅ In the downloaded tiles | Already per building, exported by `tokyo_s01_buildings` |
| Context layers (`layers.py`) | Use and structure, plus district plans (地区計画, 124 in the five central wards) | ✅ In the downloaded tiles | Already per building |
| Protected heritage layer | Built: heritage designations from Wikidata (P1435), grouped as National Treasure, Important Cultural Property, Registered Tangible Cultural Property, Tokyo Metropolis, ward, other. 38 matched buildings carry one; most of the 257 designated items in central Tokyo are museum objects, not buildings. Still open: Tokyo's own lists (72 cultural-property datasets on the Tokyo Metropolitan open-data catalog, 都選定歴史的建造物). | ✅ Wikidata; ✅ `catalog.data.metro.tokyo.lg.jp` responds | Wikidata: the same join as names. The city's lists give addresses, and no Japanese address geocoder is reachable from the cloud environment. |
| Wikipedia extracts on the card | Built: the viewer fetches the article summary in the visitor's browser (English first, else Japanese) and falls back to Wikidata's one-line description. 1,029 matched buildings have an article, 1,356 a description. | ✅ in the browser; the pipeline cannot fetch Wikipedia from the cloud environment | Wikidata's sitelinks |
| Curated stories, facts, quests | Hand-written, as in Amsterdam, checked against Japanese Wikipedia | ⚠️ The check step cannot fetch Wikipedia from the cloud environment | Wikidata id or name |
| Archive photos (Stadsarchief) | The national image portal (ジャパンサーチ) and the National Diet Library digital collections | ❌ Both blocked | n/a |

## Notes

- **PLATEAU names are sometimes tenants.** The 83 m Grand Hyatt Tokyo is filed under the police box on its ground
  floor (麻布警察署六本木六丁目交番), and Tokyo Midtown under a police post. The viewer shows the Wikidata name
  first and gives PLATEAU's as "Listed in PLATEAU as …".
- **Tokyo Station** is the same: its Wikidata point lands on a platform roof, and PLATEAU files the Marunouchi
  station building under the police box in front of it. `tokyo_wiki_fixes.py` pins the item to the right building.
- **Demolished buildings** are left out of the Wikidata query (items with a dissolved or demolished date, P576).
- **Newer PLATEAU releases** would be the next source to try for construction years. They need
  `assets.cms.plateau.reearth.io` allowed in the environment's network settings; whether Tokyo's newer models carry a
  year is not yet confirmed.

## Sources and licences

- 3D都市モデル（Project PLATEAU）東京都23区（2020年度）, MLIT: PLATEAU Site Policy, compatible with CC BY 4.0
- Wikidata: CC0
- Wikipedia summaries: CC BY-SA, credited and linked on the card
- Wikimedia Commons photos: each under its own licence, linked from the card
- Tokyo Metropolitan Government open data: CC BY 4.0
