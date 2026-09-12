from core.tools import Workspace

class WorkspaceService:
    def __init__(self, root):
        self.root=root
        self.ws=Workspace(root)
    def files(self): return self.ws.list()
    def status(self):
        return self.ws.git("status --short")
    def diff(self):
        return self.ws.git("diff --no-ext-diff")
