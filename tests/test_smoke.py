from pathlib import Path

def test_core_files_exist():
    required=['app.py','run.py','core/router.py','core/orchestrator.py','core/tool_executor.py','web/index.html','web/app.js']
    for p in required: assert Path(p).exists(), p

def test_workspace_boundary(tmp_path):
    from core.tools import Workspace
    ws=Workspace(tmp_path)
    ws.write('ok.txt','x')
    assert ws.read('ok.txt')=='x'
    try: ws.read('../escape.txt')
    except ValueError: pass
    else: raise AssertionError('workspace escape was allowed')
