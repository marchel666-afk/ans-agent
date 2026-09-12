import os, subprocess, json
class BrowserError(RuntimeError): pass
class BrowserTool:
 def __init__(self,root): self.root=root
 def open(self,url,timeout=30):
  if not url.startswith(("http://","https://")): raise BrowserError("Only http(s) URLs are allowed")
  try:
   p=subprocess.run(["python","-m","playwright","screenshot",url,"/tmp/ans-agent.png"],text=True,capture_output=True,timeout=timeout)
   if p.returncode: raise BrowserError(p.stderr.strip() or "Playwright failed")
   return {"ok":True,"screenshot":"/tmp/ans-agent.png"}
  except FileNotFoundError as e: raise BrowserError("Install Playwright to enable browser tools") from e
