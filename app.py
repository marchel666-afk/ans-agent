from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends
from fastapi.responses import FileResponse
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
from core.security import get_token
import asyncio, os
app=FastAPI(title="ANS Agent"); router=ModelRouter(); sessions=SessionStore(); events=EventBus(); approvals=ApprovalManager(); github=GitHubService(); WORKSPACE=os.path.abspath(os.getenv("ANS_WORKSPACE","./workspace")); AUTH_TOKEN=get_token()
def auth(authorization:str|None=Header(default=None)):
 if authorization!=f"Bearer {AUTH_TOKEN}": raise HTTPException(401,"Unauthorized")
@app.get("/health")
def health(): return {"status":"ok","service":"ans-agent"}
@app.get("/models")
def models(_:None=Depends(auth)):
 o=Orchestrator(router,WORKSPACE); return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable,"available":bool(o.adapters.get(m.model) or o.adapters.get(m.provider))} for m in router.registry.models]
@app.post("/route")
def route(req:RouteRequest,_:None=Depends(auth)): return router.choose(req.role,requires_tools=req.requires_tools,prefer_free=req.prefer_free).__dict__
@app.get("/sessions")
def list_sessions(_:None=Depends(auth)): return [{"id":s.id,"task":s.task,"mode":s.mode,"events":len(s.events)} for s in sessions.list()]
@app.get("/memory")
def get_memory(project:str="default",_:None=Depends(auth)): return {"project":project,"memory":ProjectMemory(sessions,project).get_context()}
@app.post("/memory")
async def save_memory(project:str,key:str,value:str,_:None=Depends(auth)): ProjectMemory(sessions,project).remember(key,value); return {"ok":True}
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
 item=approvals.decide(sid,req.allow); return {"ok":True,"approved":bool(item)}
@app.post("/run")
async def run(req:RunRequest,_:None=Depends(auth)):
 if not req.task.strip(): raise HTTPException(400,"task is required")
 if req.mode not in {"chat","agent","autopilot","best_of_n"}: raise HTTPException(400,"invalid mode")
 s=sessions.get(req.session_id) if req.session_id else sessions.create(req.task,req.mode)
 def emit(k,m,**d): item={"kind":k,"message":m,**d}; s.emit(k,m,**d); sessions.emit(s.id,k,m,**d); events.publish(s.id,item)
 emit("run.started","Task accepted",mode=req.mode)
 try:
  if req.mode=="best_of_n": result=BestOfN(Orchestrator(router,WORKSPACE,emit=emit)).run(req.task)
  else: result=Orchestrator(router,WORKSPACE,emit=emit).run(req.task,req.mode,max(1,min(req.max_iterations,30)))
  emit("run.completed","Run completed",status=result.get("status","completed")); return {"session_id":s.id,**result}
 except Exception as e: emit("run.failed",str(e)); raise HTTPException(500,str(e))
@app.get("/")
def index(): return FileResponse("web/index.html")
