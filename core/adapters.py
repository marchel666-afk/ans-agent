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
        if kwargs.get("model") and kwargs["model"] not in {"claude-code", "default", "claude"}: cmd.extend(["--model", str(kwargs["model"])])
        try:
            p=subprocess.run(cmd,cwd=kwargs.get("cwd"),text=True,capture_output=True,timeout=kwargs.get("timeout",180))
        except FileNotFoundError as e:
            raise ProviderError("Claude Code CLI not found. Install Claude Code and make 'claude' available in PATH.") from e
        if p.returncode:
            error = (p.stderr or p.stdout).strip()
            lower = error.lower()
            if "weekly limit" in lower or "hit your weekly limit" in lower or "usage limit" in lower:
                raise ProviderError("Claude Code weekly usage limit reached. Claude reports that the limit has been reached; wait for the reset or configure another provider.")
            raise ProviderError(error or f"claude exited with {p.returncode}")
        return ProviderResponse(p.stdout.strip())
    def stream(self,prompt,**kwargs):
        # Claude Code CLI returns the whole answer; surface it as one chunk so the
        # /chat streaming contract holds for every provider.
        yield self.complete(prompt,**kwargs).text

class OpenAICompatibleAdapter:
    def __init__(self,name,base_url,api_key_env,model=None):
        self.name=name; self.base_url=base_url.rstrip("/"); self.api_key_env=api_key_env; self.model=model
    def complete(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        requested=kwargs.get("model")
        aliases={"gpt","openai","gemini","google","openrouter/free"}
        model=self.model if requested in aliases else (requested or self.model)
        payload=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"temperature":kwargs.get("temperature",0.2)}).encode()
        req=urllib.request.Request(self.base_url+"/chat/completions",data=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        try:
            with urllib.request.urlopen(req,timeout=kwargs.get("timeout",120)) as r: data=json.load(r)
        except Exception as e: raise ProviderError(f"{self.name}: {e}") from e
        try: return ProviderResponse(data["choices"][0]["message"]["content"],data)
        except (KeyError,IndexError) as e: raise ProviderError(f"{self.name}: malformed response") from e
    def stream(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        requested=kwargs.get("model")
        aliases={"gpt","openai","gemini","google","openrouter/free"}
        model=self.model if requested in aliases else (requested or self.model)
        payload=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"temperature":kwargs.get("temperature",0.2),"stream":True}).encode()
        req=urllib.request.Request(self.base_url+"/chat/completions",data=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        try:
            r=urllib.request.urlopen(req,timeout=kwargs.get("timeout",120))
        except Exception as e: raise ProviderError(f"{self.name}: {e}") from e
        with r:
            for raw in r:
                line=(raw.decode("utf-8","ignore") if isinstance(raw,bytes) else str(raw)).strip()
                if not line or not line.startswith("data:"): continue
                data=line[5:].strip()
                if data=="[DONE]": break
                try: obj=json.loads(data)
                except Exception: continue
                try: delta=obj["choices"][0]["delta"].get("content")
                except (KeyError,IndexError,AttributeError): delta=None
                if delta: yield delta

class OllamaAdapter:
    name="ollama/local"
    def __init__(self,base_url=None,model=None):
        self.base_url=(base_url or os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434")).rstrip("/")
        self.model=model or os.getenv("OLLAMA_MODEL","")
        # Ollama is local; do not route loopback traffic through HTTP proxies.
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _open(self, request, timeout):
        # Keep pytest/integration monkeypatches working while production traffic
        # to local Ollama bypasses HTTP(S) proxy environment variables.
        opener = urllib.request.urlopen
        if getattr(opener, "__module__", "") != "urllib.request":
            return opener(request, timeout=timeout)
        return self.opener.open(request, timeout=timeout)
    def _model(self, requested=None):
        if requested and requested not in {"local", "ollama"}:
            return requested
        if self.model:
            return self.model
        try:
            with self._open(urllib.request.Request(self.base_url+"/api/tags"), timeout=2) as r: data=json.load(r)
            models=data.get("models") or []
            if models and models[0].get("name"): return models[0]["name"]
        except Exception:
            pass
        return "llama3.2"
    def complete(self,prompt,**kwargs):
        model=self._model(kwargs.get("model"))
        payload=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"stream":False}).encode()
        req=urllib.request.Request(self.base_url+"/api/chat",data=payload,headers={"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        try:
            with self._open(req, timeout=kwargs.get("timeout",120)) as r: data=json.load(r)
        except Exception as e:
            raise ProviderError(f"{self.name}: {e}") from e
        try: return ProviderResponse(data["message"]["content"],data)
        except (KeyError,TypeError) as e: raise ProviderError(f"{self.name}: malformed response") from e
    def stream(self,prompt,**kwargs):
        model=self._model(kwargs.get("model"))
        payload=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"stream":True}).encode()
        req=urllib.request.Request(self.base_url+"/api/chat",data=payload,headers={"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        try:
            r=self._open(req, timeout=kwargs.get("timeout",120))
        except Exception as e:
            raise ProviderError(f"{self.name}: {e}") from e
        with r:
            for raw in r:
                line=(raw.decode("utf-8","ignore") if isinstance(raw,bytes) else str(raw)).strip()
                if not line: continue
                try: obj=json.loads(line)
                except Exception: continue
                chunk=(obj.get("message") or {}).get("content") if isinstance(obj,dict) else None
                if chunk: yield chunk
                if isinstance(obj,dict) and obj.get("done"): break

def build_adapters():
    out={"claude-code":ClaudeCodeAdapter(), "ollama":OllamaAdapter()}
    if os.getenv("OPENAI_API_KEY"): out["openai"]=OpenAICompatibleAdapter("openai","https://api.openai.com/v1","OPENAI_API_KEY",os.getenv("OPENAI_MODEL","gpt-5"))
    if os.getenv("GEMINI_API_KEY"): out["gemini"]=OpenAICompatibleAdapter("google","https://generativelanguage.googleapis.com/v1beta/openai","GEMINI_API_KEY",os.getenv("GEMINI_MODEL","gemini-2.5-flash"))
    if os.getenv("OPENROUTER_API_KEY"): out["openrouter"]=OpenAICompatibleAdapter("openrouter","https://openrouter.ai/api/v1","OPENROUTER_API_KEY",os.getenv("OPENROUTER_MODEL","openrouter/free"))
    return out
