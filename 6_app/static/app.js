const $=s=>document.querySelector(s);const fmt=n=>n==null?'—':'$'+Math.round(n).toLocaleString();
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function j(u,o){const r=await fetch(u,o);return r.json()}
let AGENT=null,ACCT=null,GCONV=null;
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));b.classList.add('on');
  $('#console').style.display=b.dataset.v==='console'?'grid':'none';$('#genieView').style.display=b.dataset.v==='genie'?'block':'none'});

async function init(){const a=await j('/api/agents');$('#agent').innerHTML=a.map(x=>`<option value="${x.agent_id}">${esc(x.agent_name)} · ${x.region}</option>`).join('');
  $('#agent').onchange=e=>load(e.target.value);load(a[0].agent_id);
  $('#gsugg').innerHTML=['Which West region accounts have less than 45 days of runway?','How much overdue receivable is stuck in high-risk accounts by agent?','Which industries have the highest average shortfall probability?']
    .map(s=>`<button>${s}</button>`).join('');$('#gsugg').querySelectorAll('button').forEach(b=>b.onclick=()=>genie(b.textContent));}

async function load(id){AGENT=id;const d=await j('/api/portfolio?agent_id='+id);const s=d.summary,t=s.ml_tiers;
  $('#sum').innerHTML=`${s.accounts} accounts · <span class="pill High">${t.High} High</span> <span class="pill Watch">${t.Watch} Watch</span> · ${fmt(s.overdue_ar_total)} overdue AR`;
  $('#list').innerHTML=d.accounts.map(a=>`<div class="acct" data-id="${a.account_id}"><div><b>${esc(a.business_name)}</b><br><small>${a.account_id} · ${esc(a.industry)} · runway ${Math.round(a.runway_days)}d</small></div>
    <div style="text-align:right"><span class="pill ${a.risk_tier}">${a.risk_tier} ${Math.round(a.shortfall_prob*100)}%</span><br><small>${fmt(a.overdue_ar)} overdue</small></div></div>`).join('');
  document.querySelectorAll('.acct').forEach(e=>e.onclick=()=>pick(e.dataset.id));if(d.accounts[0])pick(d.accounts[0].account_id);}

async function pick(id){ACCT=id;document.querySelectorAll('.acct').forEach(e=>e.classList.toggle('sel',e.dataset.id===id));
  const d=await j('/api/account/'+id),h=d.health;$('#msgs').innerHTML='';const od={};d.invoices.filter(i=>i.status==='overdue').forEach(i=>od[i.customer_name]=(od[i.customer_name]||0)+i.amount);
  const wi=Object.entries(od).sort((a,b)=>b[1]-a[1]).map(([c,a])=>`<button data-c="${esc(c)}">Collect ${esc(c)} (${fmt(a)})</button>`).join('')||'<span class="muted">No overdue invoices.</span>';
  $('#detail').innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center"><div><h2 style="margin:0">${h.account_id}</h2><div style="font-size:20px;font-weight:650">${esc(h.business_name)}</div>
    <div class="muted">${esc(h.industry)} · ${h.region} · ${h.plan_tier} plan · revenue ${h.revenue_band}</div></div><span class="pill ${h.risk_tier}" style="font-size:13px">${h.risk_tier} risk</span></div>
  <div class="kpis" style="margin-top:12px"><div class="kpi"><b>${fmt(h.current_balance)}</b><span>Bank balance</span></div><div class="kpi"><b style="color:var(--hi)">${fmt(h.overdue_ar)}</b><span>Overdue AR · ${h.overdue_ar_count} invoices</span></div>
    <div class="kpi"><b>${Math.round(h.runway_days)} days</b><span>Cash runway</span></div><div class="kpi"><b>${fmt(h.net_monthly)}</b><span>Net cash / month</span></div></div>
  <div><b>ML 60-day shortfall probability: ${Math.round(h.shortfall_prob*100)}%</b> <span class="muted">· model v${h.model_version} · driver: ${esc(h.primary_driver)}</span><div class="meter"><i style="width:${h.shortfall_prob*100}%"></i></div></div>
  ${d.briefing?`<div class="brief"><b>Next best action (Claude batch briefing)</b><br>${esc(d.briefing)}</div>`:''}
  <h2 style="margin-top:12px">What-if: re-score live on the ML serving endpoint</h2><div class="btns" id="wi">${wi}</div><div id="wir"></div>
  <h2 style="margin-top:12px">Log an action (writes to Lakebase)</h2><div class="btns">${['send_ar_reminders','offer_payment_plan','offer_financing','schedule_bills','call_owner'].map(a=>`<button data-a="${a}">${a.replaceAll('_',' ')}</button>`).join('')}</div>
  <div id="acts" class="muted">${d.actions.map(a=>`✓ ${a.action_type.replaceAll('_',' ')} — ${new Date(a.created_at).toLocaleString()}`).join('<br>')||'No actions logged yet.'}</div>
  <h2 style="margin-top:14px">Unpaid invoices</h2><table><tr><th>Customer</th><th>Amount</th><th>Due</th><th>Status</th></tr>${d.invoices.map(i=>`<tr><td>${esc(i.customer_name)}</td><td>${fmt(i.amount)}</td><td>${i.due_date}</td><td><span class="pill ${i.status==='overdue'?'High':'Watch'}">${i.status}</span></td></tr>`).join('')}</table>
  <h2 style="margin-top:14px">Bills due</h2><table><tr><th>Vendor</th><th>Amount</th><th>Due</th><th>Status</th></tr>${d.bills.map(b=>`<tr><td>${esc(b.vendor_name)}</td><td>${fmt(b.amount)}</td><td>${b.due_date}</td><td>${b.status}</td></tr>`).join('')}</table>
  <h2 style="margin-top:14px">Agent notes</h2>${d.notes.map(n=>`<div class="muted">${n.created_date} — ${esc(n.note_text)}</div>`).join('')}`;
  $('#wi').querySelectorAll('button').forEach(b=>b.onclick=async()=>{$('#wir').textContent='Scoring…';const r=await j('/api/whatif',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:id,customer:b.dataset.c})});
    $('#wir').innerHTML=r.error?esc(r.error):`<div class="brief">If <b>${esc(r.collect_from)}</b> pays ${fmt(r.collected)} (${r.invoices} invoices): shortfall risk <b>${Math.round(r.before.shortfall_prob*100)}% → ${Math.round(r.after.shortfall_prob*100)}%</b>, runway <b>${r.before.runway_days} → ${r.after.runway_days} days</b>, balance ${fmt(r.before.current_balance)} → ${fmt(r.after.current_balance)} <span class="muted">· ${r.endpoint} · ${r.latency_ms} ms</span></div>`});
  $('#detail').querySelectorAll('.btns:not(#wi) button').forEach(b=>b.onclick=async()=>{await j('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:id,agent_id:AGENT,action_type:b.dataset.a,note:'logged from copilot console'})});pick(id)});
  $('#sugg').innerHTML=['Why is this account at risk?','Should the owner cut staff or chase receivables?','Draft a friendly reminder plan for the overdue invoices','Owner SSN is 123-45-6789, can you check their credit?'].map(s=>`<button>${s}</button>`).join('');
  $('#sugg').querySelectorAll('button').forEach(b=>b.onclick=()=>ask(b.textContent));}

function add(box,cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;$(box).appendChild(d);$(box).scrollTop=1e9;return d}
async function ask(text){if(!text||!ACCT)return;add('#msgs','me',esc(text));const w=add('#msgs','bot','Thinking…');
  const r=await j('/api/copilot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account_id:ACCT,question:text})});
  if(r.blocked){w.className='msg blk';w.innerHTML=`<b>Blocked by PII policy</b> — detected ${r.pii_entities.join(', ')}. Nothing was sent to the model; the attempt was logged (redacted) to the audit table.<br><span class="muted">${esc(r.redacted)}</span>`;return}
  w.innerHTML=r.error?('Error: '+esc(r.error)):esc(r.answer)+`<div class="muted" style="font-size:11px;margin-top:6px">${r.model} · ${r.latency_ms} ms · grounded on Lakebase facts${r.similar&&r.similar.length?' · similar: '+r.similar.map(s=>esc(s.business_name)).join(', '):''}</div>`}
async function genie(text){if(!text)return;add('#gmsgs','me',esc(text));const w=add('#gmsgs','bot','Genie is thinking…');
  const r=await j('/api/genie',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,conversation_id:GCONV})});GCONV=r.conversation_id;
  w.innerHTML=`${esc(r.text||'')}${r.columns.length?`<table style="margin-top:8px"><tr>${r.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr>${r.rows.slice(0,20).map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</table>`:''}${r.sql?`<details><summary class="muted">SQL</summary><code>${esc(r.sql)}</code></details>`:''}`}
$('#send').onclick=()=>{ask($('#q').value);$('#q').value=''};$('#q').onkeydown=e=>{if(e.key==='Enter')$('#send').click()};
$('#gsend').onclick=()=>{genie($('#gq').value);$('#gq').value=''};$('#gq').onkeydown=e=>{if(e.key==='Enter')$('#gsend').click()};
init();
