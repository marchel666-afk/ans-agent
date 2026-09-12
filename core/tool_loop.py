import json
TOOLS='Available tools:\n- read_file {path}\n- write_file {path,content}\n- list_files {path?}\n- terminal {command,timeout?}\n- git_status {}\n- git_diff {}\nWhen a tool is needed, output exactly one JSON line.'
class ToolLoop:
 def __init__(self,adapter,executor,emit=None,approval=None,session_id=None): self.adapter=adapter; self.executor=executor; self.emit=emit or (lambda *a,**k:None); self.approval=approval; self.session_id=session_id
 def run(self,prompt,max_steps=20):
  current=prompt+"\n\n"+TOOLS
  for i in range(max_steps):
   answer=self.adapter.complete(current).text.strip()
   try: obj=json.loads(next(x for x in answer.splitlines() if x.strip().startswith("{") and x.strip().endswith("}")))
   except Exception:return answer
   if "tool" not in obj:return answer
   name,args=obj["tool"],obj.get("args",{})
   if self.approval and not self.approval.request(self.session_id,name,args):
    self.emit("approval.waiting",f"Waiting for approval: {name}",tool=name,args=args)
    if hasattr(self.executor,"job") and self.executor.job: self.executor.job.status="waiting"
    if not self.approval.wait_for(self.session_id,name,args): return "APPROVAL_DENIED_OR_TIMEOUT: "+name
   self.emit("tool.call",name,args=args)
   try: result=self.executor.execute(name,args)
   except Exception as e: result={"ok":False,"error":str(e)}
   self.emit("tool.result",name,result=result)
   current=prompt+"\n\n"+TOOLS+"\n\nTOOL RESULT:\n"+json.dumps(result,ensure_ascii=False)[:20000]
  return "Tool loop stopped at maximum steps."
