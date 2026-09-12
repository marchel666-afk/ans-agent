from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from core.router import ModelRouter
from core.orchestrator import Orchestrator
from core.session import SessionStore
from core.git import GitWorkspace
from core.best_of_n import BestOfN
import os
app=FastAPI(title="ANS Agent"); router=ModelRouter(); orchestrator=Orchestrator(router); sessions=SessionStore(); WORKSPACE=os.getenv("ANS_WORKSPACE","./workspace")
class RouteRequest(BaseModel): role:str; requires_tools:bool=False; prefer_free:bool=False
class RunRequest(BaseModel): task:str; mode:str="agent"; max_iterations:int=30; session_id:str|None=None
@app.get("/health")
def health(): return {"status":"ok","service":"ans-agent"}
@app.get("/models")
def models(): return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable,"available":bool(orchestrator.adapters.get(m.model) or orchestrator.adapters.get(m.provider))} for m in router.registry.models]
@app.post("/route")
def route(req:RouteRequest):
 m=router.choose(req.role,requires_tools=req.requires_tools,prefer_free=req.prefer_free); return {"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable}
@app.get("/sessions")
def list_sessions(): return [{"id":s.id,"task":s.task,"mode":s.mode,"events":len(s.events)} for s in sessions.list()]
@app.get("/sessions/{sid}")
def get_session(sid:str):
 s=sessions.get(sid)
 if not s: raise HTTPException(404,"session not found")
 return s.__dict__
@app.get("/workspace/status")
def workspace_status(): return GitWorkspace(WORKSPACE).status()
@app.get("/workspace/diff")
def workspace_diff(): return {"diff":GitWorkspace(WORKSPACE).diff()}
@app.post("/run")
def run(req:RunRequest):
 if not req.task.strip(): raise HTTPException(400,"task is required")
 if req.mode not in {"chat","agent","autopilot","best_of_n"}: raise HTTPException(400,"invalid mode")
 s=sessions.get(req.session_id) if req.session_id else sessions.create(req.task,req.mode); s.emit("run.started","Run started",mode=req.mode)
 try:
  result=BestOfN(orchestrator).run(req.task) if req.mode=="best_of_n" else orchestrator.run(req.task,req.mode,max(1,min(req.max_iterations,30)))
  s.emit("run.completed","Run completed",status=result.get("status","completed")); return {"session_id":s.id,**result}
 except Exception as e:
  s.emit("run.failed",str(e)); raise HTTPException(500,str(e))
@app.get("/")
def index(): return FileResponse("web/index.html")
