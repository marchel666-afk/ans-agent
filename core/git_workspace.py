import os, subprocess, re
from pathlib import Path

class GitWorkspaceManager:
    """Creates isolated git worktrees for parallel agents and merges completed work."""
    def __init__(self, repo_dir):
        self.repo=Path(repo_dir).resolve()
        self.root=self.repo/".ans-worktrees"
        self.root.mkdir(exist_ok=True)

    def _run(self,*args):
        return subprocess.run(["git",*args],cwd=self.repo,text=True,capture_output=True,check=True).stdout.strip()

    def create(self, task_id, base="HEAD"):
        safe=re.sub(r"[^a-zA-Z0-9._-]","-",task_id)
        branch=f"ans/{safe}"
        path=self.root/safe
        if path.exists(): return {"branch":branch,"path":str(path)}
        self._run("worktree","add","-b",branch,str(path),base)
        return {"branch":branch,"path":str(path)}

    def status(self, branch):
        return self._run("status","--short","--branch") if branch else ""

    def commit(self,path,message):
        p=Path(path)
        subprocess.run(["git","add","-A"],cwd=p,check=True)
        r=subprocess.run(["git","commit","-m",message],cwd=p,text=True,capture_output=True)
        if r.returncode not in (0,): raise RuntimeError(r.stderr or r.stdout)
        return subprocess.run(["git","rev-parse","HEAD"],cwd=p,text=True,capture_output=True,check=True).stdout.strip()

    def current_branch(self):
        return self._run("branch","--show-current") or "main"

    def can_merge(self,branch,base=None):
        base=base or self.current_branch()
        r=subprocess.run(["git","merge-tree",base,branch],cwd=self.repo,text=True,capture_output=True)
        return {"clean":r.returncode==0,"output":r.stdout[-4000:]}
    def merge(self,branch,base=None):
        base=base or self.current_branch()
        if self.current_branch()!=base: self._run("checkout",base)
        self._run("merge","--no-ff",branch,"-m",f"Merge agent branch {branch}")
        return self._run("rev-parse","HEAD")

    def cleanup_merged(self, base=None):
        base=base or self.current_branch()
        rows=self._run("worktree","list","--porcelain").splitlines()
        removed=[]
        branches=[]
        for i,line in enumerate(rows):
            if line.startswith("branch refs/heads/ans/"):
                b=line.split("refs/heads/",1)[1]
                try:
                    if self._run("merge-base","--is-ancestor",b,base) == "":
                        subprocess.run(["git","worktree","remove","--force",str(self.root/b.removeprefix("ans/"))],cwd=self.repo,check=False)
                        subprocess.run(["git","branch","-D",b],cwd=self.repo,check=False)
                        removed.append(b)
                except Exception: pass
        return removed

    def remove(self,task_id,branch=None,delete_branch=True):
        safe=re.sub(r"[^a-zA-Z0-9._-]","-",task_id)
        path=self.root/safe
        if path.exists(): self._run("worktree","remove","--force",str(path))
        if delete_branch and branch:
            self._run("branch","-D",branch)
