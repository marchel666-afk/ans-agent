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

# --- native tool-calling helpers -------------------------------------------
# The agent loop keeps a provider-neutral "normalized" message list; each
# adapter's chat() translates it to the provider's wire format:
#   {"role":"system"|"user","content":str}
#   {"role":"assistant","content":str,"tool_calls":[{"id","name","args"}]}
#   {"role":"tool","tool_call_id":str,"name":str,"content":str}
import re as _re
def _extract_json_obj(text):
    for line in (text or "").splitlines():
        line=line.strip().strip("`").strip()
        if line.startswith("{") and line.endswith("}"):
            try: return json.loads(line)
            except Exception: pass
    m=_re.search(r"\{.*\}",text or "",_re.S)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None

def _to_openai_messages(messages):
    out=[]
    for m in messages:
        role=m.get("role")
        if role=="assistant" and m.get("tool_calls"):
            out.append({"role":"assistant","content":m.get("content") or "",
                        "tool_calls":[{"id":tc["id"],"type":"function",
                                       "function":{"name":tc["name"],"arguments":json.dumps(tc.get("args") or {},ensure_ascii=False)}}
                                      for tc in m["tool_calls"]]})
        elif role=="tool":
            out.append({"role":"tool","tool_call_id":m.get("tool_call_id"),"content":m.get("content") or ""})
        else:
            out.append({"role":role,"content":m.get("content") or ""})
    return out

def _to_anthropic(messages):
    system=[]; out=[]
    for m in messages:
        role=m.get("role")
        if role=="system":
            if m.get("content"): system.append(m["content"]); continue
        if role=="tool":
            block={"type":"tool_result","tool_use_id":m.get("tool_call_id"),"content":m.get("content") or ""}
            if out and out[-1]["role"]=="user" and isinstance(out[-1]["content"],list):
                out[-1]["content"].append(block)
            else:
                out.append({"role":"user","content":[block]})
        elif role=="assistant":
            content=[]
            if m.get("content"): content.append({"type":"text","text":m["content"]})
            for tc in (m.get("tool_calls") or []):
                content.append({"type":"tool_use","id":tc["id"],"name":tc["name"],"input":tc.get("args") or {}})
            out.append({"role":"assistant","content":content or [{"type":"text","text":""}]})
        else:  # user / system-as-user fallback
            out.append({"role":"user","content":[{"type":"text","text":m.get("content") or ""}]})
    return "\n\n".join(system), out

def _jsonline_chat(complete_fn, messages, tools, **kwargs):
    """Fallback native-chat for providers without function-calling (CLI/Ollama):
    serialize the conversation + tool catalogue and expect one JSON tool line."""
    from .tool_schema import catalogue_text
    parts=[]
    for m in messages:
        role=m.get("role")
        if role=="system": parts.append(m.get("content") or "")
        elif role=="user": parts.append("USER: "+(m.get("content") or ""))
        elif role=="assistant":
            if m.get("content"): parts.append("ASSISTANT: "+m["content"])
            for tc in (m.get("tool_calls") or []): parts.append("ASSISTANT_TOOL: "+tc["name"]+" "+json.dumps(tc.get("args") or {},ensure_ascii=False))
        elif role=="tool": parts.append("TOOL_RESULT("+(m.get("name") or "")+"): "+(m.get("content") or "")[:2000])
    prompt=("\n\n".join(parts)+
            "\n\nДоступные инструменты:\n"+catalogue_text()+
            "\n\nВыведи РОВНО одну строку JSON: {\"tool\":\"<имя>\",\"args\":{...}}. "
            "Когда задача выполнена — {\"tool\":\"finish\",\"args\":{\"summary\":\"...\"}}.")
    text=complete_fn(prompt,**kwargs).text.strip()
    obj=_extract_json_obj(text)
    if obj and obj.get("tool"):
        return {"text":"","tool_calls":[{"id":"call_1","name":obj["tool"],"args":obj.get("args") or {}}],"raw":text}
    return {"text":text,"tool_calls":[],"raw":text}

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
    def chat(self,messages,**kwargs):
        # No native tool-calling; fall back to the JSON-line protocol.
        return _jsonline_chat(self.complete,messages,None,**kwargs)

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
    def chat(self,messages,**kwargs):
        from .tool_schema import anthropic_tools
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        system,msgs=_to_anthropic(messages)
        body={"model":model,"max_tokens":kwargs.get("max_tokens",4096),"messages":msgs,"tools":anthropic_tools()}
        if system: body["system"]=system
        req=urllib.request.Request(self.base_url+"/messages",data=json.dumps(body,ensure_ascii=False).encode(),headers=self._headers(key))
        try:
            with urllib.request.urlopen(req,timeout=kwargs.get("timeout",180)) as r: data=json.load(r)
        except Exception as e: raise ProviderError(f"anthropic: {e}") from e
        text="".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
        calls=[{"id":b.get("id"),"name":b.get("name"),"args":b.get("input") or {}}
               for b in data.get("content",[]) if b.get("type")=="tool_use"]
        return {"text":text,"tool_calls":calls,"raw":data}
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
    def chat(self,messages,**kwargs):
        # Native OpenAI-style tool-calling used by the unified agent loop.
        from .tool_schema import openai_tools
        key=os.getenv(self.api_key_env)
        if not key: raise ProviderError(f"Missing {self.api_key_env}")
        model=self._resolve(kwargs.get("model"))
        conv=_to_openai_messages(messages)
        def build(m):
            body={"model":m,"messages":conv,"temperature":kwargs.get("temperature",0.3),
                  "tools":openai_tools(),"tool_choice":"auto"}
            return json.dumps(body,ensure_ascii=False).encode()
        data=None
        for attempt in (1,2):
            try:
                req=urllib.request.Request(self.base_url+"/chat/completions",data=build(model),
                                           headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":"ANS-Agent/1.0"})
                with urllib.request.urlopen(req,timeout=kwargs.get("timeout",180)) as r: data=json.load(r)
                break
            except HTTPError as e:
                if e.code in (400,404) and attempt==1:
                    try: model=self._auto_model(key); continue
                    except Exception: pass
                raise ProviderError(f"{self.name}: {e}") from e
            except Exception as e:
                raise ProviderError(f"{self.name}: {e}") from e
        try: msg=data["choices"][0]["message"]
        except (KeyError,IndexError,TypeError) as e: raise ProviderError(f"{self.name}: malformed response") from e
        calls=[]
        for tc in (msg.get("tool_calls") or []):
            fn=tc.get("function") or {}
            try: a=json.loads(fn.get("arguments") or "{}")
            except Exception: a={}
            calls.append({"id":tc.get("id") or ("call_"+str(len(calls)+1)),"name":fn.get("name"),"args":a})
        return {"text":msg.get("content") or "","tool_calls":calls,"raw":data}
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
    def chat(self,messages,**kwargs):
        # Local models: JSON-line tool protocol (no native function-calling).
        return _jsonline_chat(self.complete,messages,None,**kwargs)

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
