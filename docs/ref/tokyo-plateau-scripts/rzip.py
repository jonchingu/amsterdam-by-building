"""Read a remote zip via HTTP range requests. usage: rzip.py URL list | rzip.py URL get NAME OUT"""
import io, sys, zipfile, urllib.request
class R(io.RawIOBase):
    def __init__(s, url):
        s.url=url; s.p=0
        s.n=int(urllib.request.urlopen(urllib.request.Request(url,method="HEAD")).headers["Content-Length"])
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.p
    def seek(s,o,w=0):
        s.p = o if w==0 else s.p+o if w==1 else s.n+o; return s.p
    def readinto(s,b):
        if s.p>=s.n: return 0
        end=min(s.p+len(b),s.n)-1
        req=urllib.request.Request(s.url,headers={"Range":f"bytes={s.p}-{end}"})
        d=urllib.request.urlopen(req).read(); b[:len(d)]=d; s.p+=len(d); return len(d)
if __name__=='__main__':
    url=sys.argv[1]
    z=zipfile.ZipFile(io.BufferedReader(R(url),buffer_size=1<<20))
    if sys.argv[2]=="list":
        for i in z.infolist(): print(i.file_size, i.compress_size, i.filename)
    else:
        with z.open(sys.argv[3]) as f, open(sys.argv[4],"wb") as o:
            while True:
                d=f.read(1<<20)
                if not d: break
                o.write(d)
    