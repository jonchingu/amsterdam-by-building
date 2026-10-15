"""Fetch PLATEAU 3D Tiles (no textures) for Tokyo's 23 wards from the G-Spatial Information Center mirror.

Project PLATEAU, MLIT Japan, 2020 Tokyo 23 wards (dataset plateau-tokyo23ku-3dtiles-2020). Licence: PLATEAU Site Policy
section 3, compatible with CC BY 4.0: free to use, credit "3D都市モデル（Project PLATEAU）国土交通省".

    uv run python -m pipeline.tokyo_s00_fetch              # the central wards
    uv run python -m pipeline.tokyo_s00_fetch all          # all 23 wards, ~1 GB
    uv run python -m pipeline.tokyo_s00_fetch 13104 13113  # by ward code
"""
import sys
import zipfile
from pathlib import Path

import requests

BASE = ("https://gsic-opendata.s3.ap-northeast-1.amazonaws.com/national-gov/mlit/city-bureau/3d-city-model/2020/"
        "plateau-tokyo23ku-3dtiles-2020/Tokyo23ku3DTiles/{code}_{slug}_notexture_2.zip")
RAW = Path("data/tokyo")

# code: (slug, English name, Japanese name)
WARDS = {
    "13101": ("chiyoda-ku", "Chiyoda", "千代田区"), "13102": ("chuo-ku", "Chūō", "中央区"),
    "13103": ("minato-ku", "Minato", "港区"), "13104": ("shinjuku-ku", "Shinjuku", "新宿区"),
    "13105": ("bunkyo-ku", "Bunkyō", "文京区"), "13106": ("taito-ku", "Taitō", "台東区"),
    "13107": ("sumida-ku", "Sumida", "墨田区"), "13108": ("koto-ku", "Kōtō", "江東区"),
    "13109": ("shinagawa-ku", "Shinagawa", "品川区"), "13110": ("meguro-ku", "Meguro", "目黒区"),
    "13111": ("ota-ku", "Ōta", "大田区"), "13112": ("setagaya-ku", "Setagaya", "世田谷区"),
    "13113": ("shibuya-ku", "Shibuya", "渋谷区"), "13114": ("nakano-ku", "Nakano", "中野区"),
    "13115": ("suginami-ku", "Suginami", "杉並区"), "13116": ("toshima-ku", "Toshima", "豊島区"),
    "13117": ("kita-ku", "Kita", "北区"), "13118": ("arakawa-ku", "Arakawa", "荒川区"),
    "13119": ("itabashi-ku", "Itabashi", "板橋区"), "13120": ("nerima-ku", "Nerima", "練馬区"),
    "13121": ("adachi-ku", "Adachi", "足立区"), "13122": ("katsushika-ku", "Katsushika", "葛飾区"),
    "13123": ("edogawa-ku", "Edogawa", "江戸川区"),
}
CENTRAL = ["13101", "13102", "13103", "13104", "13113"]


def ward_dir(code: str) -> Path:
    return RAW / f"{code}_{WARDS[code][0]}_notexture"


def fetch(code: str):
    if (ward_dir(code) / "tileset.json").exists():
        print(code, WARDS[code][1], "already there")
        return
    RAW.mkdir(parents=True, exist_ok=True)
    url = BASE.format(code=code, slug=WARDS[code][0])
    archive = RAW / url.rsplit("/", 1)[1]
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(archive, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            # Archive entries are untrusted: only plain relative paths under the ward folder.
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in {archive}: {name}")
        z.extractall(RAW)
    archive.unlink()
    print(code, WARDS[code][1], "fetched")


def codes_from(args):
    if not args:
        return CENTRAL
    if args == ["all"]:
        return list(WARDS)
    unknown = [a for a in args if a not in WARDS]
    if unknown:
        sys.exit(f"unknown ward codes: {unknown}; known: {', '.join(WARDS)}")
    return args


if __name__ == "__main__":
    for c in codes_from(sys.argv[1:]):
        fetch(c)
