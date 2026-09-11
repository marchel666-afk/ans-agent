from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from core.router import ModelRouter
from core.orchestrator import Orchestrator
app=FastAPI(title="ANS Agent"); router=ModelRouter(); orchestrator=Orchestrator(router)
class RouteRequest(BaseModel): role:str; requires_tools:bool=False; prefer_free:bool=False
class RunRequest(BaseModel): task:str; mode:str="agent"; max_iterations:int=30
@app.get("/health")
def health(): return {"status":"ok","service":"ans-agent"}
@app.get("/models")
def models(): return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable,"available":bool(orchestrator.adapters.get(m.model) or orchestrator.adapters.get(m.provider))} for m in router.registry.models]
@app.post("/route")
def route(req:RouteRequest):
 m=router.choose(req.role,requires_tools=req.requires_tools,prefer_free=req.prefer_free); return {"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable}
@app.post("/run")
def run(req:RunRequest):
 if not req.task.strip(): raise HTTPException(400,"task is required")
 if req.mode not in {"chat","agent","autopilot","best_of_n"}: raise HTTPException(400,"invalid mode")
 try: return orchestrator.run(req.task,req.mode,max(1,min(req.max_iterations,30)))
 except Exception as e: raise HTTPException(500,str(e))
@app.get("/")
def index(): return FileResponse("web/index.html")
