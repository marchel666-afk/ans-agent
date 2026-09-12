import ast
from pathlib import Path

def test_core_modules_compile():
    for p in [Path("core/orchestrator.py"),Path("core/jobs.py"),Path("core/router.py")]:
        ast.parse(p.read_text(encoding="utf-8"))
