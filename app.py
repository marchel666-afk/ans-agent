from fastapi import FastAPI
from pydantic import BaseModel
from core.router import ModelRouter

app=FastAPI(title="ANS Agent")
router=ModelRouter()

class RouteRequest(BaseModel):
    role:str
    requires_tools:bool=False
    prefer_free:bool=False

@app.get("/health")
def health(): return {"status":"ok","service":"ans-agent"}

@app.get("/models")
def models():
    return [{"provider":m.provider,"model":m.model,"roles":sorted(m.roles),"free":m.free,"tool_capable":m.tool_capable} for m in router.registry.models]

@app.post("/route")
def route(req:RouteRequest):
    m=router.choose(req.role,requires_tools=req.requires_tools,prefer_free=req.prefer_free)
    return {"provider":m.provider,"model":m.model,"free":m.free,"tool_capable":m.tool_capable}
