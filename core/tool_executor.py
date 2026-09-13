from .tools import Workspace
from . import web
class ToolExecutor:
    def __init__(self,root): self.ws=Workspace(root); self.job=None; self.manager=None
    def execute(self,name,args):
        if self.manager and hasattr(self.manager,"record_tool"): self.manager.record_tool(name,args)
        if name=="read_file": return {"ok":True,"content":self.ws.read(args["path"])}
        if name=="write_file": return {"ok":True,"path":self.ws.write(args["path"],args["content"])}
        if name=="append_file": return {"ok":True,"path":self.ws.append(args["path"],args["content"])}
        if name=="replace_in_file": return {"ok":True,**self.ws.replace_in_file(args["path"],args["old"],args["new"])}
        if name=="list_files": return {"ok":True,"files":self.ws.list(args.get("path","."))}
        if name=="search": return {"ok":True,"hits":self.ws.search(args["query"],args.get("path","."))}
        if name=="web_search": return {"ok":True,**web.web_search(args["query"],int(args.get("limit",5)))}
        if name=="web_fetch": return {"ok":True,**web.web_fetch(args["url"])}
        if name=="terminal": return {"ok":True,**self.ws.run(args["command"],min(int(args.get("timeout",120)),300))}
        if name=="git_status": return {"ok":True,**self.ws.git("status --short")}
        if name=="git_diff": return {"ok":True,**self.ws.git("diff --no-ext-diff")}
        if name=="git_branch": return {"ok":True,**self.ws.git("branch --show-current")}
        if name=="git_log": return {"ok":True,**self.ws.git("log -8 --oneline")}
        raise ValueError("Unknown tool: "+name)
