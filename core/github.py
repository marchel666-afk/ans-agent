import os, json, urllib.request, urllib.error
class GitHubService:
 def __init__(self,token=None):
  self.token=token or os.getenv("GITHUB_TOKEN"); self.base="https://api.github.com"
 def enabled(self): return bool(self.token and self.repo())
 def repo(self): return os.getenv("GITHUB_REPO","").strip()
 def _request(self,method,path,payload=None):
  if not self.token: raise RuntimeError("GITHUB_TOKEN is not configured")
  req=urllib.request.Request(self.base+path,method=method,headers={"Authorization":"Bearer "+self.token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
  data=json.dumps(payload).encode() if payload is not None else None
  try:
   with urllib.request.urlopen(req,data=data,timeout=20) as r:return json.loads(r.read().decode())
  except urllib.error.HTTPError as e: raise RuntimeError(f"GitHub API {e.code}: {e.read().decode()[:1000]}")
 def config(self): return {"enabled":self.enabled(),"repo":self.repo(),"default_branch":os.getenv("GITHUB_BASE_BRANCH","main")}
 def branches(self): return self._request("GET",f"/repos/{self.repo()}/branches?per_page=100")
 def pulls(self,state="open"): return self._request("GET",f"/repos/{self.repo()}/pulls?state={state}&per_page=50")
 def create_pr(self,head,base,title,body="",draft=True): return self._request("POST",f"/repos/{self.repo()}/pulls",{"title":title,"head":head,"base":base,"body":body,"draft":draft})
 def issue(self,title,body=""): return self._request("POST",f"/repos/{self.repo()}/issues",{"title":title,"body":body})
