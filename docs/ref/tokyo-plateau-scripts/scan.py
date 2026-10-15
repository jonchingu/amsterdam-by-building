"""Stream one CityGML bldg file from a remote zip; emit one JSON line per Building."""
import io, sys, json, zipfile, re
sys.path.insert(0, sys.argv[4])
from rzip import R
from lxml import etree
url, name, out = sys.argv[1], sys.argv[2], sys.argv[3]
z = zipfile.ZipFile(io.BufferedReader(R(url), buffer_size=4 << 20))
LODRE = re.compile(r"\}lod(\d)")
def local(t): return t.rsplit("}", 1)[-1]
with z.open(name) as f, open(out, "w") as o:
    for ev, el in etree.iterparse(f, events=("end",), huge_tree=True):
        if local(el.tag) != "Building" or local(el.getparent().tag) == "consistsOfBuildingPart":
            continue
        if local(el.getparent().tag) not in ("cityObjectMember",):
            continue
        rec = {"id": el.get("{http://www.opengis.net/gml}id"), "file": name.split("/")[-1][:8]}
        lods = set(); parts = 0; pos = None
        for d in el.iter():
            if not isinstance(d.tag, str): continue
            t = local(d.tag)
            m = LODRE.search(d.tag)
            if m: lods.add(int(m.group(1)))
            if t == "BuildingPart": parts += 1
            elif t == "name" and "name" not in rec and d.text: rec["name"] = d.text.strip()
            elif t == "yearOfConstruction": rec["year"] = d.text
            elif t == "measuredHeight": rec["h"] = d.text
            elif t == "usage" and "usage" not in rec: rec["usage"] = d.text
            elif t == "buildingStructureType": rec["struct"] = d.text
            elif t in ("posList", "pos") and pos is None and d.text:
                v = d.text.split(); pos = (float(v[0]), float(v[1]))
        rec["lods"] = sorted(lods); rec["parts"] = parts; rec["pos"] = pos
        o.write(json.dumps(rec, ensure_ascii=False) + "\n")
        el.clear()
        while el.getprevious() is not None: del el.getparent()[0]
