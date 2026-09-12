import re, threading
SAFE={"read_file","list_files","git_status","git_diff"}
DANGEROUS_RE=re.compile(r"(^|[;&|])(rm|rmdir|del|format|sudo|shutdown|reboot|mkfs)\b|\b(git push|git reset --hard|docker rm|kubectl delete)\b",re.I)
class ApprovalManager:
 def requires_confirmation(self,name,args,autonomous=False):
  level=self.classify(name,args)
  return level=="dangerous" or (level=="moderate" and not autonomous)
 def __init__(self,emit=None): self.pending={}; self.approved={}; self.emit=emit or (lambda *a,**k:None); self.cv=threading.Condition()
 def classify(self,name,args):
  if name in SAFE:return "safe"
  if name=="terminal" and DANGEROUS_RE.search(args.get("command","")):return "dangerous"
  return "moderate"
 def request(self,sid,name,args):
  level=self.classify(name,args)
  if level=="safe":return True
  key=(sid,name,repr(sorted(args.items())))
  with self.cv:
   if self.approved.pop(key,False): return True
   self.pending[sid]={"tool":name,"args":args,"level":level,"key":key}
   self.emit("approval.required",f"Approval required for {name}",tool=name,args=args,level=level)
   return False
 def wait_for(self,sid,name,args,timeout=1800):
  key=(sid,name,repr(sorted(args.items())))
  with self.cv:
   end=__import__("time").time()+timeout
   while not self.approved.pop(key,False):
    remaining=end-__import__("time").time()
    if remaining<=0:
     self.pending.pop(sid,None); self.emit("approval.timeout",name,tool=name); return False
    self.cv.wait(remaining)
   self.pending.pop(sid,None); return True
 def decide(self,sid,allow):
  with self.cv:
   item=self.pending.get(sid)
   if item and allow:self.approved[item["key"]]=True
   if item and not allow:self.pending.pop(sid,None)
   if item:self.emit("approval."+("granted" if allow else "denied"),item["tool"],tool=item["tool"])
   self.cv.notify_all()
  return item if allow else None
