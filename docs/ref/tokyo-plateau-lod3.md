# Tokyo PLATEAU: what the 2023 and 2025 per-ward models add

Survey of the Tokyo Metropolitan Government's per-ward 3D city models (都市の3Dデジタルマップ / 3D都市モデル（Project PLATEAU）),
read on 2026-10-15 by streaming every `bldg:Building` from the published CityGML zips.
Page with the map and links: https://claude.ai/artifact/PAE9d2zizFc2GCmF9jcsVV (private; copy in `tokyo-lod3-survey.html`).

## Findings

- **LOD3 exists in one district only.** 102 buildings, all between Toranomon Hills and Shimbashi (Minato), about 600 × 1,000 m
  (lat 35.6634–35.6691, lon 139.7469–139.7577). Chiyoda and Chūō files repeat some of them because each ward file is cut along
  1 km mesh squares that cross the ward boundary.
- **LOD4: one building, 2023 only.** Tokyo Port City Takeshiba is LOD4 in `13103_minato-ku_pref_2023_citygml_1_op.zip`;
  the same building is LOD2 in the 2025 release and in the 2023 `citygml_2` zip.
- **No construction years.** Zero buildings carry `bldg:yearOfConstruction` in any of the six files.
- **Famous LOD1 boxes stay boxes in 2025.** Within 60 m of each landmark: Yoyogi National Gymnasium (国立代々木競技場), Spiral,
  Omotesando Hills, Prada Aoyama, Tod's Omotesando, Nezu Museum and Nippon Budokan are LOD1. Tokyo International Forum,
  Kabuki-za, Shizuoka Press, 21_21 Design Sight, Cocoon Tower and Fuji TV are LOD2.
- LOD2.0 vs LOD2.2 can't be told apart by geometry tags: every building is one solid with no `BuildingPart`.

## Counts (highest geometry LOD per building)

| Catalogue entry | Buildings | LOD1 | LOD2 | LOD3 | LOD4 |
|---|---:|---:|---:|---:|---:|
| 3D都市モデル（Project PLATEAU）港区（2025年度） | 51,170 | 28,588 | 22,480 | 102 | 0 |
| 3D都市モデル（Project PLATEAU）千代田区（2025年度） | 38,743 | 10,827 | 27,895 | 21 (same) | 0 |
| 3D都市モデル（Project PLATEAU）中央区（2025年度） | 37,025 | 7,876 | 29,073 | 76 (same) | 0 |
| 3D都市モデル（Project PLATEAU）新宿区（2025年度） | 100,663 | 92,346 | 8,317 | 0 | 0 |
| 3D都市モデル（Project PLATEAU）渋谷区（2025年度） | 90,544 | 83,160 | 7,384 | 0 | 0 |
| 3D都市モデル（Project PLATEAU）港区（2023年度） | 53,783 | 28,904 | 24,776 | 102 | 1 |
| Five wards 2025, unique by gml:id | 253,749 | 184,209 | 69,438 | 102 | 0 |

## Key buildings

| Building | gml:id | Height | Mesh file | 2025 | 2023 |
|---|---|---:|---|---|---|
| Toranomon Hills Station Tower | `bldg_fbf728df-a130-4f36-88e4-7267715cbf34` | 264.6 m | `53394509_bldg_6697_op.gml` | LOD3 | LOD3 |
| Toranomon Hills Mori Tower (虎ノ門ヒルズ) | `bldg_96c9d242-0fc6-4364-aeae-c21102718c35` | 256.7 m | `53394509_bldg_6697_op.gml` | LOD3 | LOD3 |
| Toranomon Hills Residential Tower | `bldg_70d240ff-cce9-408b-99c4-51c90077e09f` | 221.8 m | `53393599_bldg_6697_op.gml` | LOD3 | LOD3 |
| Toranomon Hills Business Tower | `bldg_b292bc75-5708-4a3b-a7ba-7166c829d25a` | 184.0 m | `53394600_bldg_6697_op.gml` | LOD3 | LOD3 |
| Tokyo Port City Takeshiba (2025 name: ソフトバンク株式会社(本社)) | `bldg_a9f2c24c-1602-4cea-9a51-8535a3509c90` | 207.1 m | `53393680_bldg_6697_op.gml` | LOD2 | LOD4 |

Only Mori Tower is named in the data; the other three towers are matched by height.

## Where the data lives

- Catalogue (CKAN API): `https://www.geospatial.jp/ckan/api/3/action/package_show?id=plateau-13103-minato-ku-2025`
  (also `-2023`, and `plateau-13101-chiyoda-ku-2025`, `plateau-13102-chuo-ku-2025`, `plateau-13104-shinjuku-ku-2025`,
  `plateau-13113-shibuya-ku-2025`). License CC BY 4.0.
- Files on `assets.cms.plateau.reearth.io` (must be on the environment's allowed hosts):
  - Minato 2025 CityGML, 2.0 GB: `assets/ea/d75459-6d62-4a1f-8081-317603bd5f8d/13103_minato-ku_pref_2025_citygml_1_op.zip`
  - Minato 2025 3D Tiles + MVT, 1.7 GB: `assets/cf/5d6607-8fa9-4139-bafd-fb82fd56a3d8/13103_minato-ku_pref_2025_3dtiles_mvt_1_op.zip`
  - Minato 2023 CityGML part 1 (has the LOD4): `assets/1c/5076d0-bba2-4968-8112-4c2af3929a42/13103_minato-ku_pref_2023_citygml_1_op.zip`
- The zips support HTTP range requests, so single members can be read without downloading the whole archive.
- 3D Tiles: `..._bldg_3dtiles_13103_minato-ku_lod3` is textured (WebP), Draco-compressed b3dm with `CESIUM_RTC`; glTF is y-up.
  LOD3 buildings sit in leaf tiles `data13, 16, 17, 18, 28, 29, 30, 39, 40, 41, 44` (~40 MB). Towers: `data17`, `data18`, `data44`.

## Viewers

- PLATEAU VIEW (https://plateauview.mlit.go.jp/) streams these same 3D Tiles from the same CMS.
  Its search also offers **虎ノ門ヒルズのBIMモデル**, a use-case layer more detailed than the LOD3 tiles (seen 2026-10-15).
  That BIM layer is not in the geospatial.jp catalogue; its source wasn't reachable from the cloud session.
- A BIM-derived **LOD4** model that *is* downloadable: 【dt23-05】 Keio Plaza Hotel, Shinjuku
  (`https://www.geospatial.jp/ckan/dataset/plateau-dt23-05`, ~30 MB CityGML, sample data from an MLIT trial).
- Tokyo's 2024 aerial LiDAR (東京都デジタルツイン実現プロジェクト 区部点群データ, `tokyopc-23ku-2024`) is viewable at
  https://3dview.tokyo-digitaltwin.metro.tokyo.lg.jp/ and downloadable per 1/500 sheet from `gic-tokyo.s3.ap-northeast-1.amazonaws.com`.

## Method

Each building file was streamed out of the remote zip with range requests and parsed with `lxml.iterparse`.
A building's LOD is the highest `lodN*` geometry element anywhere under it. Location is the first coordinate of its first
`posList`, so it is one footprint vertex, not a centroid.

## 3D view on the page

The page's "Toranomon in 3D" section shows the 11 LOD3 leaf tiles from the Minato 2025 textured LOD3 tileset, with three.js r147.
`tokyo-plateau-scripts/retile.py` turns each b3dm into a plain GLB: it drops `CESIUM_RTC`, adds one node matrix into a local
frame (origin 35.6660 N, 139.7505 E, ellipsoid height 40 m; x east, y up, z south), and writes the per-building attributes
to `buildings.json`. Draco geometry and WebP textures pass through unchanged. Artifacts don't serve `.glb`, so the page loads
each tile as base64 text (`tiles/dataN.glb.txt`, 53 MB in all) and ships Draco's JS decoder beside it. The tiles aren't
committed here; the copy of the page in this folder needs them next to it to show the 3D view.

Scripts (`tokyo-plateau-scripts/`): `rzip.py` lists a remote zip or extracts one member over range requests; `scan.py`
writes one JSON line per building (LOD, height, name, year, location); `b3dm.py` reads b3dm headers and batch tables.
