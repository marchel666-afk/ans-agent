from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.router import ModelRouter
from core.orchestrator import Orchestrator
from core.session import SessionStore
from core.git import GitWorkspace
from core.best_of_n import BestOfN
from core.events import EventBus
from core.tools import Workspace
from core.approval import ApprovalManager
from core.memory import ProjectMemory
from core.github import GitHubService
from core.jobs import JobManager
from core.security import get_token
from core.profiles import ProfileRegistry
import asyncio, os, subprocess

app=FastAPI(title="ANS Agent")
app.mount("/web", StaticFiles(directory="web"), name="web")
router=ModelRouter(); sessions=SessionStore(); events=EventBus(); approvals=ApprovalManager()
github=GitHubService(); jobs=JobManager(); profiles=ProfileRegistry(); WORKSPACE=os.path.abspath(os.getenv("ANS_WORKSPACE","./workspace")); AUTH_TOKEN=get_token()

def bootstrap_workspace():
    # Only bootstrap the default/explicitly missing workspace; never alter an existing project.
    if not os.path.isdir(WORKSPACE):
        os.makedirs(WORKSPACE, exist_ok=True)
        try:
            subprocess.run(["git","init"],cwd=WORKSPACE,check=True,capture_output=True,text=True)
        except Exception:
            pass

bootstrap_workspace()

class RouteRequest(BaseModel):
    role:str
    requires_tools:bool=False
    prefer_free:bool=False
class RunRequest(BaseModel):
    task:str
    mode:str="agent"
    max_iterations:int=30
    session_id:str|None=None
    profile:str="developer"
    timeout_seconds:int=3600
    policy:str="balanced"
    budget:float|None=None
class ApprovalRequest(BaseModel):
    allow:bool
class BranchRequest(BaseModel): name:str
class CommitRequest(BaseModel): message:str
class PRRequest(BaseModel): head:str; base:str|None=None; title:str; body:str=""; draft:bool=True

def auth(authorization:str|None=Header(default=None)):
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(401,"Unauthorized")

def guarded_path(path:str):
    Workspace(WORKSPACE)._path(path)
    return path

@app.get("/startup")
def startup(_:None=Depends(auth)):
    o=Orchestrator(router,WORKSPACE)
    a=o.adapters
    checks={
      "api":True,
      "workspace":os.path.isdir(WORKSPACE),
      "git":os.path.isdir(os.path.join(WORKSPACE,".git")),
      "claude_code":bool(a.get("claude-code")),
      "openai":bool(a.get("openai")),
      "gemini":bool(a.get("gemini")),
      "openrouter":bool(a.get("openrouter")),
      "ollama":bool(a.get("ollama")),
      "github":github.enabled(),
      "jobs":os.path.exists(jobs.db_path),
    }
    routing_ready=bool(router.rank("planner")) and bool(router.rank("executor",requires_tools=True))
    return {"ready":checks["workspace"] and checks["jobs"] and routing_ready,"checks":checks,"routing":{"planner":bool(router.rank("planner")),"executor":bool(router.rank("executor",requires_tools=True))}}

@app.get("/health")
def health():
    return {"status":"ok","service":"ans-agent","workspace":os.path.isdir(WORKSPACE),"github":github.enabled(),"jobs":"sqlite"}

@app.get("/diagnostics")
def diagnostics(_:None=Depends(auth)):
    adapters=Orchestrator(router,WORKSPACE).adapters
    checks={"workspace":os.path.isdir(WORKSPACE),"claude_code":bool(adapters.get("claude-code")),"openai":bool(adapters.get("openai")),"gemini":bool(adapters.get("gemini")),"openrouter":bool(adapters.get("openrouter")),"ollama":bool(adapters.get("ollama")),"github":github.enabled(),"job_persistence":os.path.exists(jobs.db_path)}
    routing_ready=bool(router.rank("planner")) and bool(router.rank("executor",requires_tools=True))
    return {"ok":checks["workspace"] and checks["job_persistence"] and routing_ready,"checks":checks,"routing":{"planner":bool(router.rank("planner")),"executor":bool(router.rank("executor",requires_tools=True))}}

@app.get("/profiles")
def profiles_list(_:None=Depends(auth)): return profiles.all()

@app.get("/models")
def models(_:None=Depends(auth)):
    o=Orchestrator(router,WORKSPACE)
    return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,
             "tool_capable":m.tool_capable,
             "available":router._available(m)}
            for m in router.registry.models]

@app.post("/model-pool/benchmark/{provider}/{model:path}")
def benchmark_role(provider:str,model:str,role:str="planner",_:None=Depends(auth)):
    adapter=Orchestrator(router,WORKSPACE).adapters.get(provider)
    if not adapter: raise HTTPException(400,"provider unavailable")
    try: return router.role_benchmark(provider,model,adapter,role)
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/model-pool/benchmark-all/{provider}/{model:path}")
def benchmark_model(provider:str,model:str,_:None=Depends(auth)):
    adapter=Orchestrator(router,WORKSPACE).adapters.get(provider)
    if not adapter: raise HTTPException(400,"provider unavailable")
    try: return router.benchmark_model(provider,model,adapter)
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/model-pool/discover")
def discover_models(_:None=Depends(auth)):
    try: return router.discover_openrouter()
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/model-pool/refresh")
def refresh_model_pool(_:None=Depends(auth)): return router.refresh_free_pool()

@app.get("/merge-status/{sid}")
def merge_status(sid:str,_:None=Depends(auth)):
    s=sessions.get(sid)
    if not s: raise HTTPException(404,"session not found")
    return {"session_id":sid,"events":[e for e in s.events if e.get("kind") in ("merge.check","merge.completed","merge.failed")]}

@app.get("/task-graph/{sid}")
def task_graph(sid:str,_:None=Depends(auth)):
    s=sessions.get(sid)
    if not s: raise HTTPException(404,"session not found")
    return {"session_id":sid,"events":[e for e in s.events if e.get("kind")=="task.graph"]}

@app.get("/cost-estimate/{provider}/{model}")
def cost_estimate(provider:str,model:str,input_tokens:int=4000,output_tokens:int=2000,_:None=Depends(auth)):
    m=next((x for x in router.registry.models if x.provider==provider and x.model==model),None)
    if not m: raise HTTPException(404,"model not found")
    return {"provider":provider,"model":model,"estimated_cost":router.cost_estimate(m,input_tokens,output_tokens)}

@app.get("/learning")
def learning(role:str|None=None,_:None=Depends(auth)): return router.learning_view(role)

@app.get("/circuit-breakers")
def circuit_breakers(_:None=Depends(auth)):
    return {"circuits": router.circuit_view()}

@app.get("/model-pool")
def model_pool(_:None=Depends(auth)): return router.pool()

@app.patch("/model-pool/{provider}/{model:path}")
def update_model(provider:str,model:str,req:dict,_:None=Depends(auth)):
    try: return router.update_model(provider,model,req)
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/model-pool/test/{provider}/{model:path}")
def test_model(provider:str,model:str,_:None=Depends(auth)):
    try: return router.test_model(provider,model)
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/route")
def route(req:RouteRequest,_:None=Depends(auth)):
    return router.choose(req.role,requires_tools=req.requires_tools,prefer_free=req.prefer_free).__dict__

@app.get("/jobs/{jid}")
def get_job(jid:str,_:None=Depends(auth)):
    j=jobs.get(jid)
    if not j: raise HTTPException(404,"job not found")
    return j.__dict__

@app.post("/jobs/{jid}/cancel")
def cancel_job(jid:str,_:None=Depends(auth)):
    if not jobs.cancel(jid): raise HTTPException(409,"job cannot be cancelled")
    return {"ok":True}

@app.get("/sessions")
def list_sessions(_:None=Depends(auth)):
    return [{"id":s.id,"task":s.task,"mode":s.mode,"events":len(s.events)} for s in sessions.list()]

@app.get("/sessions/{sid}")
def get_session(sid:str,_:None=Depends(auth)):
    s=sessions.get(sid)
    if not s: raise HTTPException(404,"session not found")
    return s.__dict__

@app.get("/memory")
def get_memory(project:str="default",_:None=Depends(auth)):
    return {"project":project,"memory":ProjectMemory(sessions,project).get_context()}

@app.post("/memory")
async def save_memory(project:str,key:str,value:str,_:None=Depends(auth)):
    ProjectMemory(sessions,project).remember(key,value); return {"ok":True}

@app.get("/workspace/branch")
def workspace_branch(_:None=Depends(auth)): return GitWorkspace(WORKSPACE).branch()

@app.post("/workspace/branch")
def workspace_create_branch(req:BranchRequest,_:None=Depends(auth)):
    try:return GitWorkspace(WORKSPACE).create_branch(req.name)
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/workspace/commit")
def workspace_commit(req:CommitRequest,_:None=Depends(auth)):
    try:return GitWorkspace(WORKSPACE).commit(req.message)
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/workspace/push")
def workspace_push(_:None=Depends(auth)):
    try:return GitWorkspace(WORKSPACE).push()
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/github/pr")
def github_pr(req:PRRequest,_:None=Depends(auth)):
    try:return github.create_pr(req.head,req.base or os.getenv("GITHUB_BASE_BRANCH","main"),req.title,req.body,req.draft)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/github")
def github_config(_:None=Depends(auth)): return github.config()

@app.get("/github/branches")
def github_branches(_:None=Depends(auth)):
    try:return github.branches()
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/github/pulls")
def github_pulls(state:str="open",_:None=Depends(auth)):
    try:return github.pulls(state)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/approvals/{sid}")
def get_approval(sid:str,_:None=Depends(auth)): return approvals.pending.get(sid)

@app.post("/approvals/{sid}")
def decide_approval(sid:str,req:ApprovalRequest,_:None=Depends(auth)):
    item=approvals.decide(sid,req.allow)
    return {"ok":True,"approved":bool(item)}

@app.get("/workspace/files")
def workspace_files(_:None=Depends(auth)): return {"files":Workspace(WORKSPACE).list()}

@app.get("/workspace/file")
def workspace_file(path:str,_:None=Depends(auth)):
    try:return {"path":path,"content":Workspace(WORKSPACE).read(guarded_path(path))}
    except Exception as e: raise HTTPException(400,str(e))

@app.get("/workspace/status")
def workspace_status(_:None=Depends(auth)): return GitWorkspace(WORKSPACE).status()

@app.get("/workspace/diff")
def workspace_diff(_:None=Depends(auth)): return {"diff":GitWorkspace(WORKSPACE).diff()}

@app.post("/run")
async def run(req:RunRequest,_:None=Depends(auth)):
    if not req.task.strip(): raise HTTPException(400,"task is required")
    if req.mode not in {"chat","agent","autopilot","best_of_n"}: raise HTTPException(400,"invalid mode")
    s=sessions.get(req.session_id) if req.session_id else sessions.create(req.task,req.mode)
    def emit(k,m,**d):
        item={"kind":k,"message":m,**d}; s.emit(k,m,**d); sessions.emit(s.id,k,m,**d); events.publish(s.id,item)
    emit("run.started","Task accepted",mode=req.mode,policy=req.policy,budget=req.budget)
    try:
        orch=Orchestrator(router,WORKSPACE,emit=emit,approval=approvals,session_id=s.id)
        orch.memory=ProjectMemory(sessions, "default")
        orch.job_manager=jobs
        profile=profiles.get(req.profile)
        orch.profile=profile
        def worker(job):
            orch.job=job
            orch.job_manager=jobs
            if job.cancel_requested: return {"status":"cancelled"}
            if req.mode=="best_of_n": result=BestOfN(orch).run(req.task)
            else: result=orch.run(req.task,req.mode,max(1,min(req.max_iterations,30)),policy=req.policy,budget=req.budget)
            emit("run.completed","Run completed",status=result.get("status","completed"))
            return result
        job=jobs.submit(s.id,worker,timeout_seconds=req.timeout_seconds)
        orch.job=job
        return {"session_id":s.id,"job_id":job.id,"status":job.status}
    except Exception as e:
        emit("run.failed",str(e)); raise HTTPException(500,str(e))

@app.websocket("/ws/{sid}")
async def ws(websocket:WebSocket,sid:str):
    token=websocket.query_params.get("token")
    if token != AUTH_TOKEN:
        await websocket.close(code=1008); return
    await websocket.accept(); q=events.subscribe(sid)
    try:
        s=sessions.get(sid)
        if s:
            for e in s.events: await websocket.send_json(e)
        while True: await websocket.send_json(await q.get())
    except (WebSocketDisconnect,asyncio.CancelledError): pass
    finally:
        if sid in events.queues and q in events.queues[sid]: events.queues[sid].remove(q)

@app.get("/")
def index(): return FileResponse("web/index.html")
