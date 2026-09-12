from .tools import Workspace
class GitWorkspace:
    def __init__(self,root): self.ws=Workspace(root)
    def status(self): return self.ws.git("status --short")
    def diff(self): return self.ws.git("diff --no-ext-diff")
    def log(self): return self.ws.git("log -8 --oneline")
