/* ANS Агент — интерфейс: агент + прямой чат + файлы + модели + история диалогов. */
const $=id=>document.getElementById(id);
let token=localStorage.getItem('ans_token')||'';
let currentSession=null,currentJob=null,socket=null;
let chatHistory=[],chatSession=null,modelPoolCache=[];
let agentActivity=null,agentFinal=null;
const authHeaders=()=>token?{'Authorization':'Bearer '+token}:{};

/* ---------- вход по токену ---------- */
function showLogin(msg){$('loginError').textContent=msg||'';$('loginModal').classList.remove('hidden');const t=$('loginToken');if(t){t.value='';t.focus();}}
function hideLogin(){$('loginModal').classList.add('hidden');}
async function doLogin(){
  const t=($('loginToken').value||'').trim();
  if(!t){$('loginError').textContent='Введите токен.';return;}
  $('loginBtn').disabled=true;$('loginError').textContent='Проверка…';
  try{
    const r=await fetch('/auth/check',{headers:{'Authorization':'Bearer '+t}});
    if(r.ok){token=t;localStorage.setItem('ans_token',token);hideLogin();$('loginError').textContent='';boot();}
    else{$('loginError').textContent='Неверный токен. Проверьте data/auth.token на сервере.';}
  }catch(e){$('loginError').textContent='Сервер недоступен: '+e.message;}
  finally{$('loginBtn').disabled=false;}
}
function logout(){token='';localStorage.removeItem('ans_token');if(socket)try{socket.close();}catch(_){}showLogin('Вы вышли. Введите токен для входа.');}

async function api(url,opts={}){
  opts.headers={...(opts.headers||{}),...authHeaders()};
  let r=await fetch(url,opts);
  if(r.status===401){showLogin('Требуется вход.');}
  return r;
}

/* ---------- markdown (безопасный) ---------- */
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function md(src){
  src=String(src==null?'':src);
  const blocks=[];
  src=src.replace(/```([\s\S]*?)```/g,(m,c)=>{blocks.push(c);return '  '+(blocks.length-1)+'  ';});
  let h=esc(src);
  h=h.replace(/`([^`\n]+)`/g,'<code>$1</code>');
  h=h.replace(/^\s*###\s+(.*)$/gm,'<h4>$1</h4>').replace(/^\s*##\s+(.*)$/gm,'<h3>$1</h3>').replace(/^\s*#\s+(.*)$/gm,'<h2>$1</h2>');
  h=h.replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<i>$2</i>');
  h=h.replace(/\n/g,'<br>');
  h=h.replace(/ (\d+) /g,(m,i)=>'<pre class="code">'+esc(blocks[+i])+'</pre>');
  return h;
}

/* ---------- навигация ---------- */
const TITLES={agent:'Агент',chat:'Чат',workspace:'Файлы',models:'Модели',sessions:'Диалоги'};
function setView(name){
  document.querySelectorAll('.view').forEach(v=>v.hidden=v.dataset.view!==name);
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===name));
  $('viewTitle').textContent=TITLES[name]||name;
  if(name==='chat')fillModelSelectors();
  if(name==='models'){loadModelPool();renderModelManager();}
  if(name==='workspace'){loadFiles();loadGit();loadDiff();loadLearning();refreshCircuits();}
  if(name==='sessions')loadSessions();
  if(window.innerWidth<=800)$('sidebar').classList.remove('open');
}
document.querySelectorAll('.nav').forEach(n=>n.addEventListener('click',()=>setView(n.dataset.view)));
function toggleSidebar(){$('sidebar').classList.toggle('open');}

/* ---------- агент ---------- */
function threadClear(id,placeholder){$(id).innerHTML='<div class="empty">'+placeholder+'</div>';}
function scrollEl(el){el.scrollTop=el.scrollHeight;}
function bubble(threadId,role,html){
  const t=$(threadId);const e=t.querySelector('.empty');if(e)e.remove();
  const wrap=document.createElement('div');wrap.className='msg '+role;
  const who=document.createElement('div');who.className='msg-role';who.textContent=role==='user'?'Вы':'ANS';
  const body=document.createElement('div');body.className='msg-body';body.innerHTML=html;
  wrap.append(who,body);t.appendChild(wrap);scrollEl(t);return body;
}
function newAgent(){currentSession=null;currentJob=null;if(socket)try{socket.close();}catch(_){}threadClear('agentThread','Опиши задачу — агент составит план и выполнит её инструментами.');$('runstatus').textContent='ОЖИДАНИЕ';}
async function startAgent(){
  const t=$('agentInput').value.trim();if(!t)return;
  $('agentInput').value='';$('agentInput').style.height='auto';
  currentSession=null;
  bubble('agentThread','user',md(t));
  const body=bubble('agentThread','assistant','');
  const act=document.createElement('div');act.className='agent-activity';
  const fin=document.createElement('div');fin.className='agent-final';
  body.append(act,fin);agentActivity=act;agentFinal=fin;
  $('runstatus').textContent='РАБОТАЕТ';
  try{
    const r=await api('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:t,mode:$('agentMode').value,max_iterations:30,profile:$('profile').value,policy:$('policy').value,budget:$('budget').value?Number($('budget').value):null,workspace:(($('agentWorkspace')||{}).value||'').trim()||null})});
    const x=await r.json();if(!r.ok)throw Error(x.detail||'запуск не удался');
    currentSession=x.session_id;currentJob=x.job_id;connect(x.session_id);pollJob();load();
  }catch(e){actLine('error','⚠ '+e.message);$('runstatus').textContent='ОШИБКА';}
}
function actLine(kind,text){
  if(!agentActivity)return;
  const d=document.createElement('div');d.className='act act-'+kind;d.innerHTML=text;
  agentActivity.appendChild(d);scrollEl($('agentThread'));
}
function agentEvent(x){
  const k=x.kind||'',m=x.message;
  if(k==='run.started')actLine('info','▸ Задача принята ('+(x.mode||'agent')+')');
  else if(k==='profile.selected')actLine('info','▸ Профиль: '+esc(String(m)));
  else if(k==='task.graph'){let n=null;try{const p=typeof m==='string'?JSON.parse(m):m;n=Array.isArray(p)?p.length:(p&&p.nodes?Object.keys(p.nodes).length:null);}catch(_){}actLine('plan','🗺 План'+(n?': '+n+' шаг(ов)':' составлен'));}
  else if(k==='provider.selected')actLine('model','→ '+esc(String(m))+(x.role?' · '+x.role:''));
  else if(k==='step.started')actLine('step','● '+esc(String(m)));
  else if(k==='tool.call')actLine('tool','🔧 '+esc(String(m))+' '+esc(JSON.stringify(x.args||{}).slice(0,160)));
  else if(k==='tool.result')actLine('toolres','&nbsp;&nbsp;↳ '+esc(JSON.stringify(x.result||x.message||{}).slice(0,200)));
  else if(k==='review')actLine('review','🔎 '+esc(String(m).slice(0,300)));
  else if(k==='step.passed')actLine('ok','✓ '+esc(String(m)));
  else if(k==='repair.requested')actLine('warn','↻ правка: '+esc(String(m).slice(0,200)));
  else if(k==='provider.failed')actLine('err','⚠ '+(x.provider||'')+': '+esc(String(m).slice(0,200)));
  else if(k==='run.completed')actLine('info','✅ Прогон завершён ('+(x.status||'')+')');
  else if(k==='run.failed')actLine('error','⚠ '+esc(String(m)));
  else if(k==='approval.waiting'||k==='approval.required'){$('approvalText').textContent=m||'Требуется подтверждение';$('approval').classList.remove('hidden');}
}
function connect(sid){
  if(socket)try{socket.close();}catch(_){}
  const proto=location.protocol==='https:'?'wss://':'ws://';
  socket=new WebSocket(proto+location.host+'/ws/'+sid+'?token='+encodeURIComponent(token));
  socket.onmessage=e=>{let x;try{x=JSON.parse(e.data);}catch(_){return;}agentEvent(x);};
}
async function pollJob(){
  if(!currentJob)return;
  try{
    const x=await(await api('/jobs/'+currentJob)).json();
    $('runstatus').textContent=({queued:'В ОЧЕРЕДИ',running:'РАБОТАЕТ',waiting:'ОЖИДАНИЕ',completed:'ГОТОВО',failed:'ОШИБКА',cancelled:'ОСТАНОВЛЕНО'}[x.status]||(x.status||'').toUpperCase());
    if(['queued','running','waiting'].includes(x.status)){setTimeout(pollJob,1000);return;}
    renderAgentFinal(x);load();
  }catch(e){setTimeout(pollJob,1500);}
}
function renderAgentFinal(job){
  if(!agentFinal)return;const res=job.result||{};
  if(job.status==='failed'){agentFinal.innerHTML='<div class="final-bad">⚠ Не удалось: '+esc(job.error||'')+'</div>';return;}
  const st=res.status||job.status;const done=(res.completed||[]);const obs=(res.observations||[]);
  let html='';
  if(res.summary)html+='<div class="final-summary">'+md(res.summary)+'</div>';
  const badge=st==='cancelled'?'⏹ остановлено':st==='completed'?'✅ завершено':'◑ '+st;
  html+='<div class="'+(st==='cancelled'?'final-bad':'final-good')+'">'+badge+' · шагов: '+(res.iterations??'—')+'</div>';
  if(done.length)html+='<div class="final-steps">'+done.map(s=>'✓ '+esc(s)).join('<br>')+'</div>';
  if(Array.isArray(obs)&&obs.length)html+='<details class="final-obs"><summary>Детали ('+obs.length+')</summary><pre class="code">'+esc(obs.slice(-12).join('\n\n')).slice(0,6000)+'</pre></details>';
  agentFinal.innerHTML=html;scrollEl($('agentThread'));
}
async function cancelJob(){if(currentJob)await api('/jobs/'+currentJob+'/cancel',{method:'POST'});}
async function decide(allow){if(!currentSession)return;await api('/approvals/'+currentSession,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({allow})});$('approval').classList.add('hidden');}

/* ---------- прямой чат ---------- */
function newChat(){chatHistory=[];chatSession=null;threadClear('chatThread','Прямой диалог с выбранной моделью — без инструментов.');}
async function sendChat(){
  const inp=$('chatInput');const msg=inp.value.trim();if(!msg)return;
  inp.value='';inp.style.height='auto';
  bubble('chatThread','user',md(msg));
  const sel=$('chatModel').value;let body={message:msg,history:chatHistory,session_id:chatSession};
  if(sel){const [p,m]=sel.split('|');body.provider=p;body.model=m;}
  chatHistory.push({role:'user',content:msg});
  const b=bubble('chatThread','assistant','▍');let acc='';
  try{
    const r=await api('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok||!r.body){const e=await r.json().catch(()=>({}));b.innerHTML=md('⚠️ '+(e.detail||('HTTP '+r.status)));return;}
    const reader=r.body.getReader(),dec=new TextDecoder();let buf='';
    while(true){const {value,done}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});let idx;
      while((idx=buf.indexOf('\n\n'))>=0){const chunk=buf.slice(0,idx);buf=buf.slice(idx+2);const line=chunk.split('\n').find(l=>l.startsWith('data:'));if(!line)continue;let ev;try{ev=JSON.parse(line.slice(5).trim());}catch(_){continue;}
        if(ev.type==='start'){chatSession=ev.session_id;if(ev.provider)b.dataset.model=ev.provider+'/'+ev.model;}
        else if(ev.type==='provider'){b.dataset.model=ev.provider+'/'+ev.model;}
        else if(ev.type==='delta'){acc+=ev.content;b.innerHTML=md(acc);scrollEl($('chatThread'));}
        else if(ev.type==='error'){acc+='\n\n⚠️ '+ev.error;b.innerHTML=md(acc);}
      }
    }
  }catch(e){b.innerHTML=md(acc+'\n\n⚠️ '+e.message);}
  if(!acc)b.innerHTML=md('(пустой ответ)');
  chatHistory.push({role:'assistant',content:acc});load();
}

/* ---------- textarea ---------- */
function autoGrow(el){if(!el)return;el.addEventListener('input',()=>{el.style.height='auto';el.style.height=Math.min(el.scrollHeight,180)+'px';});el.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();el.id==='agentInput'?startAgent():sendChat();}});}

/* ---------- пул моделей ---------- */
function modelOptions(){return modelPoolCache.map(m=>({label:m.provider+'/'+m.model+(m.free?' · беспл.':'')+(m.available?'':' · офлайн'),value:m.provider+'|'+m.model}));}
function fillModelSelectors(){const sel=$('chatModel');if(sel){const cur=sel.value;sel.innerHTML='<option value="">Авто (роутер)</option>'+modelOptions().map(o=>'<option value="'+o.value+'">'+o.label+'</option>').join('');sel.value=cur;}}
async function loadModelPool(){
  try{modelPoolCache=await(await api('/model-pool')).json();}catch(e){modelPoolCache=[];}
  fillModelSelectors();
  const box=$('models');if(box)box.innerHTML=modelPoolCache.map(m=>'<div class="model"><span>'+m.provider+'/'+m.model+' <small>'+m.roles.join(', ')+'</small></span><span><button class="mini" onclick="testModel(\''+encodeURIComponent(m.provider)+'\',\''+encodeURIComponent(m.model)+'\')">Тест</button> <b class="'+(m.free?'free':'')+'">'+(m.available?'ГОТОВА':'НАСТРОЙКА')+'</b></span></div>').join('');
}
async function refreshModels(){await api('/model-pool/refresh',{method:'POST'});loadModelPool();}
async function testModel(p,m){const x=await(await api('/model-pool/test/'+p+'/'+m,{method:'POST'})).json();alert(x.provider+'/'+x.model+': '+(x.available?'ГОТОВА':'НЕДОСТУПНА')+(x.response?'\n'+x.response:'')+(x.error?'\n'+x.error:''));}
async function renderModelManager(){
  const ms=modelPoolCache.length?modelPoolCache:await(await api('/model-pool')).json();const el=$('modelManager');if(!el)return;
  el.innerHTML=ms.map((m,i)=>{const s=m.stats||{};return '<div class="model-card '+(m.available?'':'disabled')+'"><div class="model-meta"><b>'+m.provider+'/'+m.model+'</b><span>'+(m.free?'БЕСПЛ. ':'')+(m.available?'ГОТОВА':'НАСТРОЙКА')+'</span></div><small>'+m.roles.join(' · ')+'</small><div class="model-stats">Успех '+((s.success_rate||0)*100).toFixed(1)+'% · Задержка '+(s.latency||0).toFixed(1)+'с · Сбои '+(s.fail||0)+'</div><div class="model-actions"><label>Приоритет <input id="pri'+i+'" type="number" value="'+m.priority+'"></label><button class="mini" onclick="saveModel('+i+')">Сохранить</button></div></div>';}).join('');
}
async function saveModel(i){const m=modelPoolCache[i];const priority=Number($('pri'+i).value);await api('/model-pool/'+encodeURIComponent(m.provider)+'/'+encodeURIComponent(m.model),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({priority})});await loadModelPool();renderModelManager();}
async function discoverModels(){const x=await(await api('/model-pool/discover',{method:'POST'})).json();alert('OpenRouter: добавлено моделей — '+(x.added||0));await loadModelPool();renderModelManager();}

/* ---------- файлы ---------- */
async function loadFiles(){try{const x=await(await api('/workspace/files')).json();$('files').innerHTML=x.files.map(f=>'<div class="file" data-path="'+encodeURIComponent(f)+'">'+f+'</div>').join('');document.querySelectorAll('#files .file').forEach(el=>el.onclick=()=>openFile(decodeURIComponent(el.dataset.path)));}catch(e){$('files').textContent='Рабочая область недоступна';}}
async function openFile(path){try{const x=await(await api('/workspace/file?path='+encodeURIComponent(path))).json();$('filename').textContent=x.path;$('filecontent').value=x.content;}catch(e){$('filecontent').value='Не удалось прочитать файл';}}
async function loadGit(){try{$('git').textContent=(await(await api('/workspace/status')).json()).stdout||'Дерево чистое';}catch(e){$('git').textContent='Рабочая область недоступна';}}
async function loadDiff(){try{const x=await(await api('/workspace/diff')).json();const d=x.diff;$('diff').textContent=typeof d==='string'?(d||'Нет изменений'):JSON.stringify(d,null,2);}catch(e){$('diff').textContent='Рабочая область недоступна';}}
async function loadLearning(){try{const rows=await(await api('/learning')).json();$('learning').innerHTML=rows.length?rows.map(r=>'<div class="model-row"><b>'+r.model+'</b> · '+r.role+' · '+(r.success_rate*100).toFixed(1)+'% · '+r.latency.toFixed(1)+'с · '+r.tasks+' задач</div>').join(''):'История задач пока пуста.';}catch(e){$('learning').textContent='Недоступно';}}
async function refreshCircuits(){try{const r=await(await api('/circuit-breakers')).json();const box=$('circuitBreakers');if(!box)return;box.innerHTML='<div class="hint">Предохранители</div>';Object.entries(r.circuits||{}).forEach(([m,v])=>{const d=document.createElement('div');d.className='circuit '+v.state.replace('-','');d.textContent=m+' · '+v.state+(v.cooldown_remaining?' · '+v.cooldown_remaining+'с':'');box.appendChild(d);});}catch(e){}}

/* ---------- история диалогов ---------- */
function replayAgent(sess){
  const ev=sess.events||[];
  const task=sess.task||(ev.find(e=>e.kind==='run.started')?'':'')||'(без названия)';
  bubble('agentThread','user',md(task));
  const body=bubble('agentThread','assistant','');
  const act=document.createElement('div');act.className='agent-activity';
  const fin=document.createElement('div');fin.className='agent-final';
  body.append(act,fin);agentActivity=act;agentFinal=fin;
  ev.forEach(e=>{if(e.kind!=='run.started')agentEvent(e);});
  const last=[...ev].reverse().find(e=>e.kind==='run.completed');
  if(last){fin.innerHTML='<div class="final-good">✅ Диалог из истории ('+(last.status||'завершён')+')</div>';}
}
function replayChat(sess){
  const ev=sess.events||[];
  chatHistory=[];chatSession=sess.id;
  threadClear('chatThread','');
  ev.forEach(e=>{
    if(e.kind==='chat.user'){bubble('chatThread','user',md(e.message));chatHistory.push({role:'user',content:e.message});}
    else if(e.kind==='chat.assistant'){bubble('chatThread','assistant',md(e.message));chatHistory.push({role:'assistant',content:e.message});}
  });
}
async function openSession(id){
  try{
    const sess=await(await api('/sessions/'+id)).json();
    const ev=sess.events||[];
    const isChat=(sess.mode==='chat')||ev.some(e=>e.kind==='chat.user');
    if(isChat){newChat();replayChat(sess);setView('chat');}
    else{if(socket)try{socket.close();}catch(_){}threadClear('agentThread','');currentSession=sess.id;currentJob=null;replayAgent(sess);setView('agent');}
  }catch(e){alert('Не удалось открыть диалог: '+e.message);}
}
async function loadSessions(){try{const ss=await(await api('/sessions')).json();const box=$('sessionList');if(box){box.innerHTML=ss.slice().reverse().map(s=>'<div class="file session-item" data-id="'+s.id+'" title="'+s.id+'">['+(s.mode==='chat'?'чат':'агент')+'] '+esc(s.task||s.id)+' <small>· '+s.events+' соб.</small></div>').join('')||'Диалогов пока нет.';box.querySelectorAll('.session-item').forEach(el=>el.onclick=()=>openSession(el.dataset.id));}}catch(e){const box=$('sessionList');if(box)box.textContent='Недоступно';}}

/* ---------- диагностика / состояние ---------- */
function openSetup(){$('setupModal').classList.remove('hidden');runDiagnostics();}
function closeSetup(){$('setupModal').classList.add('hidden');}
const CHECK_NAMES={workspace:'Рабочая область',git:'Git',claude_code:'Claude Code (CLI)',anthropic:'Claude (API)',openai:'OpenAI',gemini:'Gemini',groq:'Groq',openrouter:'OpenRouter',ollama:'Ollama (локально)',github:'GitHub',job_persistence:'Хранилище задач',jobs:'Задачи',api:'API'};
async function runDiagnostics(){const el=$('setupChecks');el.textContent='Проверка…';try{const d=await(await api('/diagnostics')).json();el.innerHTML=Object.entries(d.checks||{}).map(([k,v])=>'<div class="setup-row"><b>'+(CHECK_NAMES[k]||k)+'</b><span class="'+(v?'ok':'error')+'">'+(v?'ГОТОВО':'НАСТРОИТЬ')+'</span></div>').join('')+(d.ok?'<p class="ok">Ядро готово к работе.</p>':'<p class="error">Не готовы: рабочая область, хранилище или ни одного провайдера.</p>');}catch(e){el.textContent='Нужен вход или сервер недоступен.';}}
async function load(){
  try{const h=await fetch('/health');const ok=h.ok&&(await h.json()).status==='ok';$('health').textContent=ok?'● ОНЛАЙН':'● ОФЛАЙН';$('health').className='status '+(ok?'ok':'error');}catch(e){$('health').textContent='● ОФЛАЙН';}
  try{await loadModelPool();}catch(e){}
  try{const ss=await(await api('/sessions')).json();const box=$('sessions');if(box){box.innerHTML=ss.slice(-8).reverse().map(s=>'<div class="recent-item" data-id="'+s.id+'" title="'+esc(s.task||s.id)+'">'+esc(s.task||s.id)+'</div>').join('');box.querySelectorAll('.recent-item').forEach(el=>el.onclick=()=>openSession(el.dataset.id));}}catch(e){}
}

/* ---------- запуск ---------- */
function boot(){
  autoGrow($('agentInput'));autoGrow($('chatInput'));
  load();
}
async function init(){
  if(!token){showLogin();return;}
  try{
    const r=await fetch('/auth/check',{headers:{'Authorization':'Bearer '+token}});
    if(r.ok){hideLogin();boot();}
    else{showLogin('Токен устарел. Введите заново.');}
  }catch(e){boot();}
}
const _lt=$('loginToken');if(_lt)_lt.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();doLogin();}});
init();
