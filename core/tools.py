"""Safe local workspace tools used by ANS orchestration."""
from pathlib import Path
import subprocess

class Workspace:
    def __init__(self, root): self.root=Path(root).resolve()
    def _path(self, path):
        p=(self.root/path).resolve()
        if p!=self.root and self.root not in p.parents: raise ValueError("Path escapes workspace")
        return p
    def read(self,path): return self._path(path).read_text(encoding="utf-8")
    def write(self,path,content):
        p=self._path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding="utf-8"); return str(p.relative_to(self.root))
    def list(self,path="."):
        return [str(p.relative_to(self.root)) for p in self._path(path).rglob("*") if p.is_file()][:500]
    def search(self,query,path=".",max_hits=100):
        base=self._path(path); hits=[]
        files=[base] if base.is_file() else base.rglob("*")
        for p in files:
            if not p.is_file(): continue
            try: text=p.read_text(encoding="utf-8")
            except Exception: continue
            for n,line in enumerate(text.splitlines(),1):
                if query in line:
                    hits.append({"file":str(p.relative_to(self.root)),"line":n,"text":line.strip()[:200]})
                    if len(hits)>=max_hits: return hits
        return hits
    def run(self,command,timeout=120):
        p=subprocess.run(command,cwd=self.root,shell=True,text=True,capture_output=True,timeout=timeout)
        return {"returncode":p.returncode,"stdout":p.stdout[-12000:],"stderr":p.stderr[-12000:]}
    def git(self,args): return self.run("git "+args)
