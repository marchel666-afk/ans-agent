import re
from .git import GitWorkspace
class GitAgent:
 def __init__(self,root,emit=None): self.git=GitWorkspace(root); self.emit=emit or (lambda *a,**k:None)
 def feature_branch(self,task_id):
  name="agent/"+re.sub(r"[^a-z0-9-]+","-",task_id.lower()).strip("-")[:70]
  self.emit("git.branch","Creating feature branch",branch=name)
  return self.git.create_branch(name)
 def verify(self,command="pytest -q"):
  self.emit("tests.started",command); result=self.git.test(command); self.emit("tests.completed",result); return result
 def commit(self,message):
  self.emit("git.commit","Creating commit",message=message); return self.git.commit(message)
 def push(self):
  self.emit("git.push","Push requested"); return self.git.push()
