"""Provider adapters.

Adapters are deliberately thin. Claude Code is executed as a local CLI so the
user's existing Claude Code environment can be used. API providers are exposed
through OpenAI-compatible HTTP endpoints.
"""
from dataclasses import dataclass
import os, subprocess, json, urllib.request

@dataclass
class ProviderResponse:
    text: str
    raw: object | None = None

class ProviderError(RuntimeError): pass

class ClaudeCodeAdapter:
    name="anthropic/claude-code"
    def complete(self,prompt,**kwargs):
        cmd=["claude","-p",prompt]
        try:
            p=subprocess.run(cmd,cwd=kwargs.get("cwd"),text=True,capture_output=True,timeout=kwargs.get("timeout",180))
        except FileNotFoundError as e:
            raise ProviderError("Claude Code CLI not found. Install Claude Code and make 'claude' available in PATH.") from e
        if p.returncode: raise ProviderError(p.stderr.strip() or f"claude exited with {p.returncode}")
        return ProviderResponse(p.stdout.strip())

class OpenAICompatibleAdapter:
    def __init__(self,name,base_url,api_key_env,model=None):
        self.name=name; self.base_url=base_url.rstrip("/"); self.api_key_env=api_key_env; self.model=model
    def complete(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        payload=json.dumps({"model":kwargs.get("model",self.model),"messages":[{"role":"user","content":prompt}],"temperature":kwargs.get("temperature",0.2)}).encode()
        req=urllib.request.Request(self.base_url+"/chat/completions",data=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        try:
            with urllib.request.urlopen(req,timeout=kwargs.get("timeout",120)) as r: data=json.load(r)
        except Exception as e: raise ProviderError(f"{self.name}: {e}") from e
        try: return ProviderResponse(data["choices"][0]["message"]["content"],data)
        except (KeyError,IndexError) as e: raise ProviderError(f"{self.name}: malformed response") from e

def build_adapters():
    out={"claude-code":ClaudeCodeAdapter()}
    if os.getenv("OPENAI_API_KEY"): out["openai"]=OpenAICompatibleAdapter("openai","https://api.openai.com/v1","OPENAI_API_KEY",os.getenv("OPENAI_MODEL","gpt-5"))
    if os.getenv("GEMINI_API_KEY"): out["gemini"]=OpenAICompatibleAdapter("google","https://generativelanguage.googleapis.com/v1beta/openai","GEMINI_API_KEY",os.getenv("GEMINI_MODEL","gemini-2.5-flash"))
    if os.getenv("OPENROUTER_API_KEY"): out["openrouter"]=OpenAICompatibleAdapter("openrouter","https://openrouter.ai/api/v1","OPENROUTER_API_KEY",os.getenv("OPENROUTER_MODEL","openrouter/free"))
    return out
