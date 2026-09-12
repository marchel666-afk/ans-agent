from .tools import Workspace
import re
class GitWorkspace:
 def __init__(self,root): self.ws=Workspace(root)
 def status(self): return self.ws.git("status --short")
 def diff(self): return self.ws.git("diff --no-ext-diff")
 def log(self): return self.ws.git("log -8 --oneline")
 def branch(self): return self.ws.git("branch --show-current")
 def branches(self): return self.ws.git("branch --format='%(refname:short)'")
 def create_branch(self,name):
  if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}",name): raise ValueError("Invalid branch name")
  return self.ws.git("switch -c "+name)
 def checkout(self,name):
  if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}",name): raise ValueError("Invalid branch name")
  return self.ws.git("switch "+name)
 def test(self,command): return self.ws.run(command,300)
 def commit(self,message):
  if not message.strip(): raise ValueError("Commit message required")
  return self.ws.run("git add -A && git commit -m "+__import__("shlex").quote(message),120)
 def push(self,branch=None):
  b=branch or self.branch()["stdout"].strip()
  return self.ws.run("git push -u origin "+__import__("shlex").quote(b),180)
