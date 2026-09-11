from .adapters import ClaudeCodeAdapter, ProviderError
from .tools import Workspace

class WorkspaceExecutor:
    def __init__(self,workspace): self.workspace=Workspace(workspace); self.claude=ClaudeCodeAdapter()
    def execute(self,task,step):
        context="\n".join(self.workspace.list())
        prompt=f"You are the coding executor. Work directly in the provided project.\nTASK: {task}\nSTEP: {step}\nPROJECT FILES:\n{context}\n\nUse your coding-agent tools/terminal to inspect, edit and test the project. Do not merely describe changes. Return a concise report."
        return self.claude.complete(prompt).text
