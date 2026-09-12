from pathlib import Path
import json
class ProjectMemory:
    def __init__(self,root): self.path=Path(root)/".ans-memory.json"
    def load(self):
        if not self.path.exists(): return {"facts":[],"decisions":[],"notes":[]}
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:return {"facts":[],"decisions":[],"notes":[]}
    def save(self,data): self.path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
