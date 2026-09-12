import os
class GitHubService:
 def __init__(self,token=None): self.token=token or os.getenv("GITHUB_TOKEN")
 def enabled(self): return bool(self.token)
 def repo(self): return os.getenv("GITHUB_REPO","")
 def config(self): return {"enabled":self.enabled(),"repo":self.repo(),"default_branch":os.getenv("GITHUB_BASE_BRANCH","main")}
