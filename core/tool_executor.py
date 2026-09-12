import json
from .tools import Workspace
class ToolExecutor:
    def __init__(self,root): self.ws=Workspace(root)
    def execute(self,name,args):
        if name=="read_file": return {"ok":True,"content":self.ws.read(args["path"])}
        if name=="write_file": return {"ok":True,"path":self.ws.write(args["path"],args["content"])}
        if name=="list_files": return {"ok":True,"files":self.ws.list(args.get("path","."))}
        if name=="terminal": return {"ok":True,**self.ws.run(args["command"],min(int(args.get("timeout",120)),300))}
        if name=="git_status": return self.ws.git("status --short")
        if name=="git_diff": return {"diff":self.ws.git("diff --no-ext-diff")}
        raise ValueError("Unknown tool: "+name)
