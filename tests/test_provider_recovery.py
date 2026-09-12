from core.router import ModelRouter
from core.types import ModelCandidate
import tempfile, os, time


def test_expired_cooldown_is_recovered():
    with tempfile.TemporaryDirectory() as d:
        db=os.path.join(d,"r.db")
        r=ModelRouter()
        r.db=db
        with __import__("sqlite3").connect(db) as c:
            c.execute("CREATE TABLE provider_health(model TEXT PRIMARY KEY, failures INTEGER, cooldown_until REAL, category TEXT, updated_at REAL)")
            c.execute("INSERT INTO provider_health VALUES(?,?,?,?,?)",("m",1,time.time()-1,"timeout",time.time()))
        r.failures={"m":(1,time.time()-1,"timeout")}
        r.rank("planner")
        with __import__("sqlite3").connect(db) as c:
            assert c.execute("SELECT 1 FROM provider_health WHERE model='m'").fetchone() is None
