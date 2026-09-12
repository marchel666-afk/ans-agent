from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from core.router import ModelRouter
from core.orchestrator import Orchestrator
from core.session import SessionStore
from core.git import GitWorkspace
from core.best_of_n import BestOfN
from core.events import EventBus
from core.tools import Workspace
import os, asyncio
app=FastAPI(title="ANS Agent"); router=ModelRouter(); orchestrator=Orchestrator(router); sessions=SessionStore(); events=EventBus(); WORKSPACE=os.getenv("ANS_WORKSPACE","./workspace")
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
@app.get("/workspace/files")
def workspace_files(): return {"files":Workspace(WORKSPACE).list()}
@app.get("/workspace/file")
def workspace_file(path:str):
 try:return {"path":path,"content":Workspace(WORKSPACE).read(path)}
 except Exception as e: raise HTTPException(400,str(e))
@app.get("/workspace/status")
def workspace_status(): return GitWorkspace(WORKSPACE).status()
@app.get("/workspace/diff")
def workspace_diff(): return {"diff":GitWorkspace(WORKSPACE).diff()}
@app.websocket("/ws/{sid}")
async def ws(websocket:WebSocket,sid:str):
 await websocket.accept(); q=events.subscribe(sid)
 try:
  for e in sessions.get(sid).events if sessions.get(sid) else []: await websocket.send_json(e)
  while True: await websocket.send_json(await q.get())
 except (WebSocketDisconnect,asyncio.CancelledError): pass
 finally:
  if sid in events.queues and q in events.queues[sid]: events.queues[sid].remove(q)
@app.post("/run")
async def run(req:RunRequest):
 if not req.task.strip(): raise HTTPException(400,"task is required")
 if req.mode not in {"chat","agent","autopilot","best_of_n"}: raise HTTPException(400,"invalid mode")
 s=sessions.get(req.session_id) if req.session_id else sessions.create(req.task,req.mode)
 def emit(kind,message,**data):
  item={"kind":kind,"message":message,**data}; s.emit(kind,message,**data); events.publish(s.id,item)
 emit("run.started","Task accepted",mode=req.mode)
 try:
  emit("router","Selecting models")
  if req.mode=="best_of_n":
   emit("best_of_n","Generating competing solutions"); result=BestOfN(orchestrator).run(req.task)
  else:
   emit("planner","Building execution plan"); result=orchestrator.run(req.task,req.mode,max(1,min(req.max_iterations,30)))
  emit("run.completed","Run completed",status=result.get("status","completed")); return {"session_id":s.id,**result}
 except Exception as e:
  emit("run.failed",str(e)); raise HTTPException(500,str(e))
@app.get("/")
def index(): return FileResponse("web/index.html")
