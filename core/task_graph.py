from dataclasses import dataclass, field
from typing import Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

@dataclass
class TaskNode:
    id: str
    title: str
    deps: set[str] = field(default_factory=set)
    status: str = "pending"
    result: Any = None

class TaskGraph:
    def __init__(self, titles):
        self.nodes={f"step-{i+1}":TaskNode(f"step-{i+1}",t,set()) for i,t in enumerate(titles)}
        ids=list(self.nodes)
        for i in range(1,len(ids)):
            self.nodes[ids[i]].deps.add(ids[i-1])

    def ready(self):
        done={n.id for n in self.nodes.values() if n.status=="done"}
        return [n for n in self.nodes.values() if n.status=="pending" and n.deps <= done]

    def complete(self,node_id,result):
        n=self.nodes[node_id]; n.status="done"; n.result=result

    def fail(self,node_id,result):
        n=self.nodes[node_id]; n.status="failed"; n.result=result

    def snapshot(self):
        return [{"id":n.id,"title":n.title,"deps":sorted(n.deps),"status":n.status} for n in self.nodes.values()]

    def run_parallel(self,fn,max_workers=3):
        results={}
        while True:
            ready=self.ready()
            if not ready: break
            with ThreadPoolExecutor(max_workers=min(max_workers,len(ready))) as pool:
                futures={pool.submit(fn,n):n for n in ready}
                for future in as_completed(futures):
                    n=futures[future]
                    try:
                        results[n.id]=future.result(); self.complete(n.id,results[n.id])
                    except Exception as e:
                        self.fail(n.id,str(e)); results[n.id]=str(e)
                        return results
        return results
