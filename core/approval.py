import re
SAFE={"read_file","list_files","git_status","git_diff"}
MODERATE={"write_file","terminal"}
DANGEROUS_RE=re.compile(r"(^|[;&|])(rm|rmdir|del|format|sudo|shutdown|reboot|mkfs)\b|\b(git push|git reset --hard|docker rm|kubectl delete)\b",re.I)
class ApprovalManager:
    def __init__(self,emit=None): self.pending={}; self.emit=emit or (lambda *a,**k:None)
    def classify(self,name,args):
        if name in SAFE:return "safe"
        if name=="terminal" and DANGEROUS_RE.search(args.get("command","")):return "dangerous"
        return "moderate"
    def request(self,sid,name,args):
        level=self.classify(name,args)
        if level=="safe":return True
        self.pending[sid]={"tool":name,"args":args,"level":level}
        self.emit("approval.required",f"Approval required for {name}",tool=name,args=args,level=level)
        return False
    def decide(self,sid,allow):
        item=self.pending.pop(sid,None)
        if item:self.emit("approval."+("granted" if allow else "denied"),item["tool"],tool=item["tool"]); return item if allow else None
