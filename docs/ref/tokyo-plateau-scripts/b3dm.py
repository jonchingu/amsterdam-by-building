import struct, json, sys
def read(path):
    b = open(path, "rb").read()
    _, _, L, ftj, ftb, btj, btb = struct.unpack("<4sIIIIII", b[:28])
    o = 28; ft = json.loads(b[o:o+ftj]); o += ftj
    ftbin = b[o:o+ftb]; o += ftb
    bt = json.loads(b[o:o+btj]) if btj else {}; o += btj
    btbin = b[o:o+btb]; o += btb
    return ft, bt, btbin, b[o:]
def bt_scalar(bt, btbin, key, n):
    v = bt.get(key)
    if isinstance(v, list): return v
    if not v: return None
    fmt = {"DOUBLE": "d", "BYTE": "b", "UNSIGNED_BYTE": "B", "INT": "i", "UNSIGNED_INT": "I", "FLOAT": "f", "SHORT": "h", "UNSIGNED_SHORT": "H"}[v["componentType"]]
    return list(struct.unpack_from("<%d%s" % (n, fmt), btbin, v["byteOffset"]))
