import hashlib

class ProjectMemory:
    def __init__(self,store,project="default"):
        self.store=store
        self.project=project
    def get_context(self):
        m=self.store.memories(self.project)
        if not m: return "No stored project memory."
        return "\n".join(f"- {k}: {v}" for k,v in m.items())
    def remember(self,key,value):
        self.store.save_memory(self.project,key,value)
    def remember_result(self,task,result):
        key="task:"+hashlib.sha256(task.encode("utf-8")).hexdigest()[:16]
        self.remember(key,str(result)[:8000])

class AgentMemory(ProjectMemory):
    def search_relevant(self,task,limit=10):
        context=self.get_context()
        return [{"content":context,"score":1}] if context and context!="No stored project memory." else []
    def put(self,key,value):
        self.remember(key,value)
    def prompt_context(self,task,limit=8):
        return self.get_context()
