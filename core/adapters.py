"""Provider adapters.

Adapters are deliberately thin. Claude Code is executed as a local CLI so the
user's existing Claude Code environment can be used. API providers are exposed
through OpenAI-compatible HTTP endpoints.
"""
from dataclasses import dataclass
import os, subprocess, json, urllib.request
from urllib.error import HTTPError

@dataclass
class ProviderResponse:
    text: str
    raw: object | None = None

class ProviderError(RuntimeError): pass

# --- model auto-selection ---------------------------------------------------
# Provider model catalogues change over time (Groq/OpenRouter rename or retire
# models), so a hardcoded model name can start returning 404. These helpers pick
# a sensible *chat* model from a provider's live /models list as a self-healing
# fallback when the configured name is rejected.
_BAD_MODEL_HINTS=("whisper","tts","orpheus","guard","safety","moderation","embed",
                  "rerank","-vl",":vl","content-safety","prompt-guard","image",
                  "vision","diffusion","flux","audio","transcrib")
_GOOD_MODEL_HINTS=(("gpt-oss",60),("instruct",35),("llama",28),("qwen",26),
                   ("gemma",22),("nemotron",22),("mistral",20),("deepseek",20),
                   ("compound",18),("-it",15),("chat",12))
def _score_model(mid,prefer_free=False):
    low=mid.lower()
    if any(b in low for b in _BAD_MODEL_HINTS): return -1
    s=0
    for kw,w in _GOOD_MODEL_HINTS:
        if kw in low: s+=w
    if prefer_free:
        s+= 40 if low.endswith(":free") else -15
    for bad in ("mini","nano","-xs","-2b","-1b","-3b"):
        if bad in low: s-=6
    return s
def _pick_model(ids,prefer_free=False):
    ranked=sorted(((_score_model(i,prefer_free),i) for i in ids),reverse=True)
    if ranked and ranked[0][0]>0: return ranked[0][1]
    return ids[0] if ids else None

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

class AnthropicAdapter:
    """Native Anthropic Messages API adapter (https://api.anthropic.com/v1/messages).

    Anthropic's API is *not* OpenAI-compatible (different endpoint, auth header and
    response shape), so it gets its own adapter. Used only when ANTHROPIC_API_KEY is
    set; local Claude Code (CLI) remains a separate provider for dev machines.
    """
    def __init__(self,model=None,api_key_env="ANTHROPIC_API_KEY"):
        self.name="anthropic"
        self.api_key_env=api_key_env
        self.model=model or os.getenv("ANTHROPIC_MODEL","claude-sonnet-4-5")
        self.base_url=os.getenv("ANTHROPIC_BASE_URL","https://api.anthropic.com/v1").rstrip("/")
        self.version=os.getenv("ANTHROPIC_VERSION","2023-06-01")
    def _resolve(self,requested):
        aliases={"anthropic","claude","claude-code","default"}
        return self.model if (not requested or requested in aliases) else requested
    def _headers(self,key):
        return {"x-api-key":key,"anthropic-version":self.version,"content-type":"application/json","User-Agent":"ANS-Agent/1.0"}
    def complete(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        payload=json.dumps({"model":model,"max_tokens":kwargs.get("max_tokens",4096),
                            "messages":[{"role":"user","content":prompt}]}).encode()
        req=urllib.request.Request(self.base_url+"/messages",data=payload,headers=self._headers(key))
        try:
            with urllib.request.urlopen(req,timeout=kwargs.get("timeout",120)) as r: data=json.load(r)
        except Exception as e: raise ProviderError(f"anthropic: {e}") from e
        try:
            text="".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
            return ProviderResponse(text,data)
        except (KeyError,TypeError) as e: raise ProviderError("anthropic: malformed response") from e
    def stream(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        payload=json.dumps({"model":model,"max_tokens":kwargs.get("max_tokens",4096),
                            "messages":[{"role":"user","content":prompt}],"stream":True}).encode()
        req=urllib.request.Request(self.base_url+"/messages",data=payload,headers=self._headers(key))
        try:
            r=urllib.request.urlopen(req,timeout=kwargs.get("timeout",120))
        except Exception as e: raise ProviderError(f"anthropic: {e}") from e
        with r:
            for raw in r:
                line=(raw.decode("utf-8","ignore") if isinstance(raw,bytes) else str(raw)).strip()
                if not line or not line.startswith("data:"): continue
                data=line[5:].strip()
                if not data or data=="[DONE]": continue
                try: obj=json.loads(data)
                except Exception: continue
                if obj.get("type")=="content_block_delta":
                    delta=(obj.get("delta") or {}).get("text")
                    if delta: yield delta

class OpenAICompatibleAdapter:
    # model names that mean "use the adapter's configured default"
    ALIASES={"gpt","openai","gemini","google","openrouter","openrouter/free","groq","default","auto"}
    def __init__(self,name,base_url,api_key_env,model=None):
        self.name=name; self.base_url=base_url.rstrip("/"); self.api_key_env=api_key_env
        self.model=model; self._resolved=None
    def _resolve(self,requested):
        # An already auto-resolved model wins; otherwise honour an explicit
        # request, falling back to the configured default for aliases/empties.
        if self._resolved: return self._resolved
        if not requested or requested in self.ALIASES: return self.model
        return requested
    def _list_models(self,key,timeout=10):
        req=urllib.request.Request(self.base_url+"/models",headers={"Authorization":"Bearer "+key,"User-Agent":"ANS-Agent/1.0"})
        with urllib.request.urlopen(req,timeout=timeout) as r: data=json.load(r)
        return [m.get("id") for m in (data.get("data") or []) if m.get("id")]
    def _auto_model(self,key):
        # Called when the configured model is rejected: pick a live chat model.
        ids=self._list_models(key)
        pick=_pick_model(ids,prefer_free=(self.name=="openrouter"))
        if not pick: raise ProviderError(f"{self.name}: no usable chat model available")
        self._resolved=pick
        return pick
    def _payload(self,model,prompt,kwargs,stream):
        body={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":kwargs.get("temperature",0.2)}
        if stream: body["stream"]=True
        return json.dumps(body).encode()
    def _open(self,model,prompt,key,kwargs,stream):
        req=urllib.request.Request(self.base_url+"/chat/completions",data=self._payload(model,prompt,kwargs,stream),
                                   headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
        return urllib.request.urlopen(req,timeout=kwargs.get("timeout",120))
    def complete(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        for attempt in (1,2):
            try:
                with self._open(model,prompt,key,kwargs,False) as r: data=json.load(r)
                break
            except HTTPError as e:
                # Bad/retired model name -> resolve a live one and retry once.
                if e.code in (400,404) and attempt==1:
                    try: model=self._auto_model(key); continue
                    except Exception: pass
                raise ProviderError(f"{self.name}: {e}") from e
            except Exception as e:
                raise ProviderError(f"{self.name}: {e}") from e
        try: return ProviderResponse(data["choices"][0]["message"]["content"],data)
        except (KeyError,IndexError) as e: raise ProviderError(f"{self.name}: malformed response") from e
    def stream(self,prompt,**kwargs):
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        r=None
        for attempt in (1,2):
            try:
                r=self._open(model,prompt,key,kwargs,True); break
            except HTTPError as e:
                if e.code in (400,404) and attempt==1:
                    try: model=self._auto_model(key); continue
                    except Exception: pass
                raise ProviderError(f"{self.name}: {e}") from e
            except Exception as e:
                raise ProviderError(f"{self.name}: {e}") from e
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
    # Native Anthropic API (Claude) — used when a key is present; falls back to the
    # local Claude Code CLI on dev machines that have it.
    if os.getenv("ANTHROPIC_API_KEY"): out["anthropic"]=AnthropicAdapter(os.getenv("ANTHROPIC_MODEL","claude-sonnet-4-5"))
    if os.getenv("OPENAI_API_KEY"): out["openai"]=OpenAICompatibleAdapter("openai","https://api.openai.com/v1","OPENAI_API_KEY",os.getenv("OPENAI_MODEL","gpt-5"))
    if os.getenv("GEMINI_API_KEY"): out["gemini"]=OpenAICompatibleAdapter("google","https://generativelanguage.googleapis.com/v1beta/openai","GEMINI_API_KEY",os.getenv("GEMINI_MODEL","gemini-2.5-flash"))
    if os.getenv("OPENROUTER_API_KEY"): out["openrouter"]=OpenAICompatibleAdapter("openrouter","https://openrouter.ai/api/v1","OPENROUTER_API_KEY",os.getenv("OPENROUTER_MODEL","openrouter/free"))
    # Groq — free tier, extremely fast inference (OpenAI-compatible endpoint).
    if os.getenv("GROQ_API_KEY"): out["groq"]=OpenAICompatibleAdapter("groq","https://api.groq.com/openai/v1","GROQ_API_KEY",os.getenv("GROQ_MODEL","openai/gpt-oss-20b"))
    return out
