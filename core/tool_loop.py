import json
TOOLS='Available tools:\n- read_file {path}\n- write_file {path,content}\n- list_files {path?}\n- terminal {command,timeout?}\n- git_status {}\n- git_diff {}\nWhen a tool is needed, output exactly one JSON line.'
class ToolLoop:
    def __init__(self,adapter,executor,emit=None): self.adapter=adapter; self.executor=executor; self.emit=emit or (lambda *a,**k:None)
    def run(self,prompt,max_steps=20):
        current=prompt+"\n\n"+TOOLS
        for i in range(max_steps):
            answer=self.adapter.complete(current).text.strip()
            try:
                line=next(x for x in answer.splitlines() if x.strip().startswith("{") and x.strip().endswith("}")); obj=json.loads(line)
            except Exception: return answer
            if "tool" not in obj: return answer
            self.emit("tool.call",obj["tool"],args=obj.get("args",{}))
            try: result=self.executor.execute(obj["tool"],obj.get("args",{}))
            except Exception as e: result={"ok":False,"error":str(e)}
            self.emit("tool.result",obj["tool"],result=result)
            current=prompt+"\n\n"+TOOLS+"\n\nTOOL RESULT:\n"+json.dumps(result,ensure_ascii=False)[:20000]
        return "Tool loop stopped at maximum steps."
