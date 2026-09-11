from core.router import ModelRouter

r=ModelRouter()
for role in ("planner","researcher","architect","executor","tester","reviewer","judge"):
    m=r.choose(role,requires_tools=role in {"executor","tester"})
    print(f"{role:12} -> {m.provider}/{m.model}")
