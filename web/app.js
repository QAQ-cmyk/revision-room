const $ = (selector) => document.querySelector(selector);
const staticDemo = window.REVISION_ROOM_DEMO || null;
const state = {token: '', active: null, report: null, view: 'report', history: [], selected: null, filter: 'all', busy: false, ai: {profiles:[],presets:[],defaultId:'codex'}, codex:{}, settingsBusy:false, mode:'game', uploads:[]};
const reviewerName = r => r?.visualProvider || 'Codex';
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames = {running:'评审进行中',queued:'等待检查',complete:'评审完成',partial:'画面评审未完成',error:'检查未完成',cancelled:'已停止',interrupted:'检查已中断'};
const severityNames = {high:'优先处理',medium:'建议修改',low:'细节优化'};
const findingStates = {open:'待处理',planned:'已安排',retest:'待复测'};
const buildLabel = name => /^Build_Opening_Candidate\d+$/.test(name || '') ? `开场候选 ${name.match(/\d+$/)[0]}` : name || '';
function evidenceText(value,r) {
  return escape(value).replace(/(?:opening|systems|uploads)\/[\w-]+/g,id=>{
    const shot=r.screenshots.find(s=>s.id===id);
    return shot ? `<button class="inline-evidence" data-shot="${escape(id)}" aria-label="查看截图：${escape(shot.label)}">${escape(shot.label)}</button>` : id;
  });
}
const dateText = value => value ? new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '';
const evidenceUrl = (report, path) => staticDemo ? window.REVISION_ROOM_IMAGES[path] : report.isDemo ? `/demo/${path.split('/').map(encodeURIComponent).join('/')}` : `/evidence/${encodeURIComponent(report.id)}/${path.split('/').map(encodeURIComponent).join('/')}`;
let pollTimer, toastTimer;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Revision-Token':state.token}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '连接失败，请重试');
  return data;
}
function showError(message = '') { $('#error').hidden = !message; $('#error').textContent = message; }
function toast(message) {
  $('#toast').textContent = message; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 3500);
}
function setBusy(busy) {
  state.busy = busy;
  for (const id of ['start','pick','build','game-path','use-vision','reviewer','ai-settings','start-images','choose-shots','project-name','game-context','image-files','view-demo','web-start','web-route','web-url','web-preset']) $(`#${id}`).disabled = busy || !!state.active;
  document.querySelectorAll('[data-mode],[data-remove-upload]').forEach(el=>el.disabled=busy || !!state.active);
  $('#start-images').disabled ||= !state.uploads.length;
  $('#choose-review').disabled = $('#start-images').disabled;
  $('#export-prompt').disabled = $('#start-images').disabled;
  $('#start').disabled ||= !$('#game-path').value.trim();
  $('#web-start').disabled ||= !state.webAvailable;
  $('#cancel').hidden = !state.active;
  $('#cancel').disabled = busy;
}
function setPath(path) { $('#game-path').value = path; setBusy(state.busy); }
function setView(view) {
  state.view = view;
  document.querySelectorAll('[data-view]').forEach(button => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-current', button.dataset.view === view ? 'page' : 'false'); });
  render();
}
function elapsed() {
  if (!state.report) return;
  const seconds = Math.max(0, Math.floor(((state.report.endedAt ? new Date(state.report.endedAt) : Date.now()) - new Date(state.report.createdAt))/1000));
  $('#elapsed').textContent = `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;
}
function renderProgress() {
  const r = state.report;
  const running = r && ['running','queued'].includes(r.status);
  $('#progress').hidden = !running;
  if (!running) return;
  $('#progress-label').textContent = r.stage;
  const labels=r.mode==='web' ? r.route.steps.map(s=>s.label) : r.mode==='screenshots' ? ['准备画面','AI 看图'] : ['准备','开场试玩','系统检查','存档复查','AI 看图'];
  const step=r.mode==='screenshots' ? (r.step>=4?1:0) : r.step;
  $('#steps').innerHTML = labels.map((label,index) => `<li class="${index < step ? 'done' : index === step ? 'current' : ''}"><span>${index < step ? '✓' : index+1}</span>${escape(label)}</li>`).join('');
  $('#progress-detail').textContent = r.mode==='web' ? '每一步会保存画面和操作结果。遇到失败时可查看最后一张截图。' : r.step === 4 ? '所选 AI 正在审阅本轮画面。截图已保存在本机，完成后会显示对应建议。' : '游戏窗口会自动打开和关闭。请等待这轮操作结束，避免手动操作正在检查的游戏。';
  elapsed();
}
function reportHeader(r) {
  const checked = r.checks.reduce((sum,c) => sum+c.checks.length,0);
  const errors = r.checks.reduce((sum,c) => sum+c.errors.length,0);
  const completed = r.status === 'complete';
  const exports = !r.isDemo && !['running','queued'].includes(r.status) ? `<div class="export-actions">${r.mode==='web' ? '<button class="text-button" id="replay-web">载入路线复测 ↗</button>' : ''}<a class="text-button" href="/api/runs/${encodeURIComponent(r.id)}/markdown" download>导出清单 ↓</a><a class="text-button" href="/api/runs/${encodeURIComponent(r.id)}/bundle" download>保存证据包 ↓</a></div>` : '';
  return `${r.isDemo ? '<p class="demo-banner">示例报告 · 场景和建议为预置演示内容，不是实际 AI 调用结果。无需密钥，可自由查看。</p>' : ''}<div class="section-heading"><div><p class="eyebrow">本轮检查 · ${escape(dateText(r.createdAt))} · ${escape(buildLabel(r.buildName))}</p><h2>${escape(r.name)} <span class="status-tag ${completed ? 'done' : ''}">${escape(statusNames[r.status] || r.status)}</span></h2></div>${exports}</div>
  <div class="report-summary"><p>${escape(r.summary)}</p>${r.visualError ? `<p class="notice">${escape(reviewerName(r))}：${escape(r.visualError)}。本轮试玩记录和截图仍可查看。</p>` : ''}${r.error ? `<p class="notice">${escape(r.error)}</p>` : ''}</div>
  <div class="metrics"><div><span>${r.mode==='screenshots' ? '评审方式' : '自动检查'}</span><strong>${r.mode==='screenshots' ? '看图' : checked}<small>${r.mode==='screenshots' ? '' : ' 项通过'}</small></strong><p>${r.mode==='screenshots' ? '仅截图评审 · 未运行游戏' : errors ? `${errors} 项错误，请查看下方证据` : `${r.checks.length} / ${r.mode==='web' ? r.route.steps.length : 4} 组流程已有结果`}</p></div><div><span>修改建议</span><strong>${r.visual || r.mode==='web' ? r.findings.length : '—'}<small>${r.visual || r.mode==='web' ? ' 条' : ''}</small></strong><p>${r.mode==='web' ? '来自当前路线的检查结果' : r.visual ? '每条建议均附证据与复测方式' : r.visionRequested ? '等待 AI 画面评审' : '本轮未启用画面评审'}</p></div><div><span>证据画面</span><strong>${r.screenshots.length}<small> 张</small></strong><p>${r.visual ? `${escape(reviewerName(r))} 已审阅 ${r.visual.inspected_screenshots.length} 张选定画面` : '来自本轮独立试玩'}</p></div><div class="version-metric"><span>游戏版本</span><strong>${escape(buildLabel(r.buildName))}</strong><p>${r.mode==='web' ? '独立浏览器' : r.mode==='screenshots' ? '截图证据' : '独立存档'} · ${escape(r.visualModel || (r.reviewerId==='external' ? '导入已有评审' : '本机检查'))}</p></div></div>`;
}
function shotMarkup(r, shot, finding) {
  if (!shot) return `<div class="no-shot">截图将在试玩完成后出现。</div>`;
  const region = finding?.region;
  const box = region ? `<span class="annotation" style="left:${region.x}%;top:${region.y}%;width:${region.w}%;height:${region.h}%" aria-hidden="true"><span>观察区域</span></span>` : '';
  return `<button class="evidence-image" data-shot="${escape(shot.id)}" aria-label="放大查看：${escape(shot.label)}"><img src="${evidenceUrl(r,shot.path)}" alt="${escape(shot.label)}的游戏截图" loading="lazy">${box}<span class="zoom-hint">点击查看原图 ↗</span></button><div class="evidence-caption"><strong>${escape(shot.label)}</strong><span>${shot.width} × ${shot.height} · ${region ? '标注区域，可查看原图核对' : '本轮记录画面'}</span></div>`;
}
function renderReport(r) {
  const candidates = r.findings.filter(f => state.filter === 'all' || f.kind === state.filter || f.severity === state.filter);
  if (!candidates.some(f=>f.id === state.selected)) state.selected = candidates[0]?.id || null;
  const selected = r.findings.find(f=>f.id===state.selected);
  const shot = r.screenshots.find(s=>s.id===selected?.screenshot_id) || r.screenshots.find(s=>s.id==='opening/01_opening') || r.screenshots[0];
  const findings = candidates.length ? candidates.map((f,index) => `<article class="finding ${f.id===state.selected ? 'selected' : ''}" id="${escape(f.id)}"><div class="finding-top"><span class="priority ${escape(f.severity)}">${escape(severityNames[f.severity])}</span><span class="source">${f.kind==='visual' ? (f.confidence==='medium' ? `${escape(reviewerName(r))} · 需进一步确认` : `${escape(reviewerName(r))} · 画面观察`) : '自动运行检查'}</span></div><button class="finding-title" data-select="${escape(f.id)}" ${f.screenshot_id ? 'title="查看对应证据画面"' : ''}><span>${String(index+1).padStart(2,'0')}</span><h3>${escape(f.title)}</h3>${f.screenshot_id ? '<b aria-hidden="true">↗</b>' : ''}</button><p class="observation">${escape(f.observation)}</p><dl><div><dt>影响</dt><dd>${escape(f.impact)}</dd></div><div><dt>怎么改</dt><dd>${escape(f.recommendation)}</dd></div><div><dt>怎么复测</dt><dd>${escape(f.verify)}</dd></div></dl><div class="finding-foot">${f.screenshot_id ? `<button class="text-button" data-select="${escape(f.id)}">查看画面证据 ↗</button>` : `<a class="text-button" href="${evidenceUrl(r,f.evidence)}" target="_blank" rel="noopener">查看运行记录 ↗</a>`}<label class="finding-state"><span class="sr-only">${escape(f.title)}处理状态</span><select ${r.isDemo?'disabled':''} data-finding="${escape(f.id)}">${Object.entries(findingStates).map(([value,label])=>`<option value="${value}" ${value===f.state ? 'selected' : ''}>${label}</option>`).join('')}</select></label></div></article>`).join('') : `<div class="no-findings"><span aria-hidden="true">${r.visual ? '✓' : '◌'}</span><h3>${r.mode==='web' ? '查看逐步试玩记录' : r.visual ? '此范围没有修改建议' : '画面建议尚未生成'}</h3><p>${r.mode==='web' ? '展开下方步骤查看操作结果，或进入证据画面查看每一步的截图。' : r.visual ? '这不代表游戏没有问题；可以结合原图和检查边界继续判断。' : r.visionRequested ? 'AI 完成阅读后，建议会和对应画面一起出现在这里。' : '本轮只进行了自动检查。开启上方画面评审选项，再运行一轮即可查看画面建议。'}</p></div>`;
  const checks = r.checks.map(c=>`<details class="check-detail"><summary><span class="check-icon ${c.passed ? 'pass' : 'fail'}">${c.passed ? '✓' : '!'}</span><strong>${escape(c.label)}</strong><span>${c.checks.length} 项通过${c.errors.length ? ` / ${c.errors.length} 项错误` : ''}</span></summary><p class="muted">${escape(c.scope)}</p>${c.errors.length ? `<ul class="check-errors">${c.errors.map(t=>`<li>${escape(t)}</li>`).join('')}</ul>` : ''}<ul class="check-list">${c.checks.map(t=>`<li>${escape(t)}</li>`).join('')}</ul><a class="text-button" href="${evidenceUrl(r,c.evidence)}" target="_blank" rel="noopener">查看原始检查记录 ↗</a></details>`).join('');
  return `${reportHeader(r)}<div class="section-heading compact"><h2>画面与修改建议</h2><div class="filters" role="group" aria-label="筛选修改建议">${[['all','全部'],['high','优先处理'],['visual','画面'],['runtime','运行']].map(([key,label])=>`<button data-filter="${key}" class="${state.filter===key?'active':''}" aria-pressed="${state.filter===key}">${label}</button>`).join('')}</div></div><div class="review-grid"><div class="evidence-column"><div class="evidence-card">${shotMarkup(r,shot,selected?.screenshot_id===shot?.id ? selected : null)}</div>${r.visual?.strengths?.length ? `<section class="strengths"><h3>可以保留的部分</h3><ul>${r.visual.strengths.map(s=>`<li>${evidenceText(s,r)}</li>`).join('')}</ul></section>` : ''}<p class="evidence-note">${r.isDemo ? '预置示意场景与解说。' : '建议来自本轮截图。'}本轮解说来源：${escape(reviewerName(r))}。请结合原图确认，改完后重新检查。</p></div><div class="findings">${findings}</div></div><section class="check-section"><div class="section-heading compact"><h2>自动检查记录</h2><span class="muted small">通过的步骤，不等于整个游戏已合格</span></div>${checks || (r.mode==='screenshots' ? '<p class="muted">本轮仅导入截图，没有执行自动试玩或功能检查。</p>' : '<p class="muted">第一组试玩结束后，检查记录会出现在这里。</p>')}</section><details class="coverage"><summary>本轮能看什么，还不能判断什么</summary><ul>${[...r.coverage,...(r.visual?.limitations||[])].map(s=>`<li>${escape(s)}</li>`).join('')}</ul></details>`;
}
function renderGallery(r) {
  return `<div class="section-heading"><div><p class="eyebrow">本轮画面记录</p><h2>证据画面 <span class="muted">${r.screenshots.length}</span></h2></div><span class="muted small">${escape(buildLabel(r.buildName))}</span></div><p class="muted gallery-intro">点击任意画面查看原图。带「已审阅」标记的画面已交给 ${escape(reviewerName(r))}；其余留作运行证据。</p><div class="gallery">${r.screenshots.map((s,index)=>`<button class="shot-card" data-shot="${escape(s.id)}"><div><img src="${evidenceUrl(r,s.path)}" alt="${escape(s.label)}" loading="lazy">${r.visual?.inspected_screenshots.includes(s.id) ? '<span class="reviewed">已审阅</span>' : ''}</div><span><b>${String(index+1).padStart(2,'0')}</b><strong>${escape(s.label)}</strong><small>${s.width} × ${s.height}</small></span></button>`).join('') || '<div class="no-findings">还没有截图。试玩结束后会自动加入这里。</div>'}</div>`;
}
function renderHistory() {
  return `<div class="section-heading"><div><p class="eyebrow">每次检查都有记录</p><h2>检查历史</h2></div><span class="muted small">${state.history.length} 次本机记录</span></div><div class="history-list">${state.history.map(r=>`<button class="history-item" data-run="${escape(r.id)}"><div><span class="status-tag ${r.status==='complete'?'done':''}">${escape(statusNames[r.status]||r.status)}</span><span class="muted small">${escape(dateText(r.createdAt))}</span></div><h3>${escape(r.name)} <small>${escape(buildLabel(r.buildName))}</small></h3><p>${escape(r.summary)}</p><span class="text-button">查看这次检查 ↗</span></button>`).join('') || '<div class="no-findings"><h3>还没有检查记录</h3><p>导入游戏截图，或选择已适配游戏，开始第一次评审。</p></div>'}</div>`;
}
const emptyHTML = $('#content').innerHTML;
function render() {
  $('#shot-count').textContent = state.report?.screenshots.length || 0;
  renderProgress();
  $('#content').innerHTML = state.view === 'history' ? renderHistory() : state.report ? (state.view === 'gallery' ? renderGallery(state.report) : renderReport(state.report)) : emptyHTML;
}
async function loadReport(id, changeView=false) {
  const next = await api(`/api/runs/${encodeURIComponent(id)}`);
  const changed = JSON.stringify(next) !== JSON.stringify(state.report);
  state.report = next;
  if (changeView) {state.selected=null; state.filter='all'; setView('report');}
  else if (changed) render();
  else renderProgress();
}
async function refresh() {
  clearTimeout(pollTimer);
  try {
    const result = await api('/api/history');
    state.active = result.active; state.history = result.history;
    if (state.report && ['running','queued'].includes(state.report.status)) await loadReport(state.report.id);
    else if (state.view === 'history') render();
    setBusy(state.busy);
    $('#connection').textContent = '已连接本机';
  } catch (e) {$('#connection').textContent='连接中断 · 正在重试'; showError(e.message);}
  pollTimer=setTimeout(refresh, state.active ? 2000 : 8000);
}
async function initialize() {
  if (staticDemo) {
    state.report=staticDemo; render();
    $('.intake').hidden=true; $('[data-view="history"]').hidden=true;
    $('.local-badge').textContent='交互示例 · 无需密钥';
    $('#connection').textContent='离线示例';
    $('.rail-bottom p').textContent='自制示意场景 · 无网络请求';
    $('.lead').textContent='点击问题查看对应画面，体验从观察、修改建议到复测标准的完整流程。';
    return;
  }
  setBusy(true);
  try {
    const data = await api('/api/bootstrap');
    state.webAvailable=!!data.webplayAvailable; fillRoute("moss");
    state.token=data.token; state.active=data.active; state.history=data.history; state.codex=data.codex || {}; state.ai=data.ai || state.ai;
    $('#build').innerHTML = data.builds.length ? data.builds.map((b,index)=>`<option value="${escape(b.path)}">星潮漂流 · ${escape(buildLabel(b.name))}${index===0 ? ' · 最近更新' : ''}</option>`).join('') : '<option value="">请选择游戏程序</option>';
    setPath(data.builds[0]?.path || '');
    updateReviewers(); setCaptureMode(data.builds.length ? 'game' : state.webAvailable ? 'web' : 'screenshots');
    $('#connection').textContent='已连接本机';
    if (data.active || data.history[0]) await loadReport(data.active || data.history[0].id);
    setBusy(false); refresh();
  } catch(e) {showError('无法连接本机工作台：'+e.message+'。请通过「打开修订室」启动。'); $('#connection').textContent='连接失败';}
}

$('#build').addEventListener('change', e=>setPath(e.target.value));
$('#game-path').addEventListener('input', ()=>setBusy(false));
$('#pick').addEventListener('click', async()=>{
  showError(); setBusy(true);
  try {const data=await api('/api/pick',{}); if(data.path) {setPath(data.path); $('.path-details').setAttribute('open',''); if(![...$('#build').options].some(o=>o.value===data.path)) $('#build').add(new Option('已选择的游戏',data.path)); $('#build').value=data.path;}}
  catch(e){showError(e.message);} finally {setBusy(false);}
});
$('#start').addEventListener('click', async()=>{
  showError(); setBusy(true);
  try {const result=await api('/api/start',{path:$('#game-path').value.trim(),vision:$('#use-vision').checked,reviewer:$('#reviewer').value}); state.active=result.id; await loadReport(result.id,true); refresh();}
  catch(e){showError(e.message);} finally {setBusy(false);}
});
$('#cancel').addEventListener('click',async()=>{
  setBusy(true);
  try {await api('/api/cancel',{id:state.active}); toast('正在停止检查，证据会保留。已提交的 API 请求可能仍由服务商处理。');}
  catch(e){showError(e.message);} finally {setBusy(false);}
});
document.addEventListener('click', async event=>{
  const button=event.target.closest('button'); if(!button)return;
  if(button.dataset.mode) setCaptureMode(button.dataset.mode);
  if(button.dataset.removeUpload!==undefined) {state.uploads.splice(Number(button.dataset.removeUpload),1);renderUploads();}
  if(button.dataset.view) setView(button.dataset.view);
  if(button.dataset.filter) {state.filter=button.dataset.filter;render();}
  if(button.dataset.select) {state.selected=button.dataset.select;render(); if(innerWidth<1050) $('.evidence-card').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});}
  if(button.dataset.run) {try{await loadReport(button.dataset.run,true);}catch(e){showError(e.message);}}
  if(button.dataset.shot) {
    const shot=state.report?.screenshots.find(s=>s.id===button.dataset.shot); if(!shot)return;
    $('#lightbox-title').textContent=shot.label;
    $('#lightbox-image').src=evidenceUrl(state.report,shot.path); $('#lightbox-image').alt=shot.label;
    $('#lightbox-caption').textContent=`${shot.width} × ${shot.height} · ${state.report.buildName} · ${dateText(state.report.createdAt)}`;
    $('#lightbox').showModal();
  }
});
$('#content').addEventListener('change',async event=>{
  const select=event.target.closest('[data-finding]'); if(!select)return;
  select.disabled=true;
  try {await api('/api/finding',{id:state.report.id,finding:select.dataset.finding,state:select.value}); const f=state.report.findings.find(f=>f.id===select.dataset.finding);f.state=select.value;toast('已保存处理状态。修订后请重新检查。');}
  catch(e){showError(e.message); select.value=state.report.findings.find(f=>f.id===select.dataset.finding).state;} finally {select.disabled=false;}
});
$('#close-lightbox').addEventListener('click',()=>$('#lightbox').close());
$('#lightbox').addEventListener('click',event=>{if(event.target===$('#lightbox')) $('#lightbox').close();});
function setCaptureMode(mode) {
  state.mode=mode;
  document.querySelectorAll('[data-mode]').forEach(el=>{el.classList.toggle('active',el.dataset.mode===mode);el.setAttribute('aria-pressed',String(el.dataset.mode===mode));});
  document.querySelectorAll('.game-only').forEach(el=>el.hidden=mode!=='game');
  $('#image-intake').hidden=mode!=='screenshots';
  $('#intake-title').textContent=mode==='screenshots' ? '让 AI 看看你的游戏' : '放入要检查的游戏';
  $('#mode-description').textContent=mode==='screenshots' ? '适用于任何游戏 · 用画面定位值得修改的地方' : '已接入《星潮漂流》Windows 版 · 其他游戏可用截图评审';
  $('#mode-safety').textContent=mode==='screenshots' ? '原图不变 · 评审副本保存在本机' : '新建独立存档 · 只读游戏文件';
  $('#web-intake').hidden=mode!=='web';
  for(const selector of ['.reviewer-row','.intake-foot','#send-notice']) $(selector).hidden=mode==='web';
  if(mode==='web'){
    $('#intake-title').textContent='复测一条游戏路线';
    $('#mode-description').textContent='按步骤实际操作，每一步都留下截图。';
    $('#web-hint').textContent=state.webAvailable?'使用本机 Edge · 无需 AI 密钥':'请使用 Windows 便携包，或安装 requirements-web.txt 中的依赖。';
  }
  reviewerStatus();setBusy(state.busy);
}
function renderUploads() {
  $('#upload-preview').innerHTML=state.uploads.map((s,i)=>`<div class="upload-thumb"><img src="data:image/png;base64,${s.data}" alt="${escape(s.name)}"><button data-remove-upload="${i}" aria-label="移除截图 ${escape(s.name)}">×</button><span>${escape(s.name)}</span></div>`).join('');
  setBusy(state.busy);
}
async function addImages(files) {
  if(state.active || state.busy)return;
  showError();setBusy(true);
  try {
    if(state.uploads.length+files.length>10)throw new Error('最多导入 10 张截图，请先移除不需要的画面。');
    const added=[];
    for(const file of files) {
      if(!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size>20*1024*1024)throw new Error(`${file.name}：请选择小于 20 MB 的 PNG、JPG 或 WebP 图片。`);
      let bitmap;
      try {bitmap=await createImageBitmap(file);}catch{throw new Error(`${file.name}：图片无法读取，请换一张截图。`);}
      try {
        const ratio=Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
        const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*ratio);canvas.height=Math.round(bitmap.height*ratio);
        if(canvas.width<100 || canvas.height<100)throw new Error(`${file.name}：图片太小，请选择完整游戏截图。`);
        canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);
        added.push({name:file.name.slice(0,200),data:canvas.toDataURL('image/png').split(',')[1]});
      } finally {bitmap.close();}
    }
    if([...state.uploads,...added].reduce((sum,s)=>sum+s.data.length,0)>32*1024*1024)throw new Error('评审副本总大小超过 24 MB，请减少图片数量。');
    state.uploads.push(...added);renderUploads();
  } catch(e){showError(e.message);}finally{setBusy(false);$('#image-files').value='';}
}
$('#choose-shots').addEventListener('click',()=>$('#image-files').click());
$('#image-files').addEventListener('change',e=>addImages([...e.target.files]));
for(const type of ['dragenter','dragover']) $('#choose-shots').addEventListener(type,e=>{e.preventDefault();$('#choose-shots').classList.add('dragging');});
for(const type of ['dragleave','drop']) $('#choose-shots').addEventListener(type,e=>{e.preventDefault();$('#choose-shots').classList.remove('dragging');if(type==='drop')addImages([...e.dataTransfer.files]);});
$('#export-prompt').addEventListener('click',()=>{
  const names=state.uploads.map(image=>image.name);
  const request=[
    '请逐张核对随附的游戏截图，返回一个 JSON 对象。只报告有截图支持的问题，每条建议给出具体复测方法。',
    '游戏名称　'+$('#project-name').value,
    '希望检查　'+($('#game-context').value.trim() || '初次游玩的界面与引导'),
    '截图文件名　'+JSON.stringify(names),
    '顶层字段必须为 summary（总结字符串）、strengths 和 limitations（字符串数组）、inspected_screenshots（实际审阅的完整文件名数组）、findings（0 至 8 条建议）。',
    '每条建议包含 severity（high、medium 或 low）、confidence（high 或 medium）、title、observation、impact、recommendation、verify、screenshot_id（已审阅的文件名）和 region。',
    'region 示例 {"x":10,"y":20,"w":30,"h":15}。以原图左上角为原点，四个值分别是左边距、上边距、宽和高，单位为整图百分比。请框住对应的证据。',
    '把推测和可见现象区分开。没有充分证据时允许 findings 为空。仅输出 JSON，以 UTF-8 保存为 .json 文件。'
  ].join('\n');
  const url=URL.createObjectURL(new Blob([request],{type:'text/plain;charset=utf-8'}));
  const link=document.createElement('a');
  link.href=url;link.download='修订室-截图评审要求.txt';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('#choose-review').addEventListener('click',()=>$('#review-file').click());
$('#review-file').addEventListener('change',async event=>{
  const file=event.target.files[0];
  if(!file)return;
  showError();setBusy(true);
  try {
    if(file.size>1024*1024)throw new Error('评审 JSON 不得超过 1 MB。');
    let review;
    try {review=JSON.parse(await file.text());} catch {throw new Error('无法读取评审 JSON，请检查文件格式。');}
    const result=await api('/api/import-review',{name:$('#project-name').value.trim(),context:$('#game-context').value,images:state.uploads,review});
    state.uploads=[];renderUploads();await loadReport(result.id,true);refresh();
    $('#content').scrollIntoView({block:'start'});toast('已导入评审，可以逐条核对原图。');
  } catch(e){showError(e.message);} finally {event.target.value='';setBusy(false);}
});
$('#start-images').addEventListener('click',async()=>{
  if(!$('#project-name').value.trim()){showError('请填写游戏或版本名称。');$('#project-name').focus();return;}
  showError();setBusy(true);
  try{const result=await api('/api/import',{name:$('#project-name').value.trim(),context:$('#game-context').value,images:state.uploads,reviewer:$('#reviewer').value});state.active=result.id;state.uploads=[];renderUploads();await loadReport(result.id,true);refresh();}
  catch(e){showError(e.message);}finally{setBusy(false);}
});
$('#view-demo').addEventListener('click',async()=>{
  try{state.report=await api('/api/demo');state.selected=null;state.filter='all';setView('report');$('#content').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
  catch(e){showError(e.message);}
});
function updateReviewers() {
  $('#reviewer').innerHTML = '<option value="codex">Codex · 本机登录</option>' + state.ai.profiles.map(p=>`<option value="${escape(p.id)}">${escape(p.name)} · ${escape(p.model)}</option>`).join('');
  $('#reviewer').value = state.ai.defaultId || 'codex';
  if (!$('#reviewer').value) $('#reviewer').value='codex';
  reviewerStatus();
}
function reviewerStatus() {
  const profile=state.ai.profiles.find(p=>p.id===$('#reviewer').value), codex=state.codex;
  $('#model-status').textContent=profile ? `API · ${profile.name} · ${profile.model}` : codex.loggedIn ? `✓ Codex 已登录 · ${codex.model || '默认模型'}` : codex.message || 'Codex 状态未知';
  $('#model-status').classList.toggle('unavailable',!profile && !codex.loggedIn);
  $('#send-notice').textContent=state.mode==='game' && !$('#use-vision').checked ? '本轮只执行本机检查，不向 AI 发送截图。' : profile ? `选定截图与检查摘要将发送至 ${new URL(profile.baseUrl).host}，使用此接口的 API 额度。` : '选定截图与检查摘要将交给已登录的 Codex，使用现有账户额度。';
}
function profilePicker(selected='') {
  $('#profile-edit').innerHTML='<option value="">＋ 添加新接口</option>'+state.ai.profiles.map(p=>`<option value="${escape(p.id)}">${escape(p.name)} · ${escape(p.model)}</option>`).join('');
  $('#profile-edit').value=selected;
}
function settingsResult(message='',error=false) {
  $('#ai-result').hidden=!message; $('#ai-result').textContent=message; $('#ai-result').classList.toggle('error',error);
}
function applyPreset() {
  const p=state.ai.presets.find(x=>x.id===$('#ai-preset').value); if(!p)return;
  $('#ai-name').value=p.name; $('#ai-url').value=p.baseUrl; $('#ai-protocol').value=p.protocol;
  $('#ai-token-param').value=p.tokenParam; $('#ai-model').value=''; $('#ai-key').value=''; $('#ai-no-key').checked=false; $('#ai-key').disabled=false;
  $('#preset-hint').textContent=p.hint || '填写基础地址，无需在末尾加 /chat/completions 或 /messages。';
  settingsResult();
}
function fillProfile() {
  $('#profile-form').reset(); settingsResult();
  const p=state.ai.profiles.find(x=>x.id===$('#profile-edit').value);
  $('#delete-profile').hidden=!p;
  if(p) {
    for(const [id,key] of [['ai-preset','preset'],['ai-name','name'],['ai-url','baseUrl'],['ai-model','model'],['ai-protocol','protocol'],['ai-token-param','tokenParam'],['ai-tokens','maxTokens']]) $(`#${id}`).value=p[key];
    $('#ai-no-key').checked=p.noKey; $('#ai-key').disabled=p.noKey;
    $('#preset-hint').textContent=state.ai.presets.find(x=>x.id===p.preset)?.hint || '更换地址或接口格式时，需要重新填写密钥。';
  } else applyPreset();
  $('#key-hint').textContent=p?.hasKey ? '已加密保存。留空保留原密钥；输入新密钥可替换。' : '使用当前 Windows 账户加密保存；不会写进报告或浏览器存储。';
  $('#ai-key').placeholder=p?.hasKey ? '已保存 · 留空不修改' : '粘贴此服务商的 API 密钥';
}
function profileDraft() {
  return {id:$('#profile-edit').value,name:$('#ai-name').value.trim(),preset:$('#ai-preset').value,baseUrl:$('#ai-url').value.trim(),model:$('#ai-model').value.trim(),protocol:$('#ai-protocol').value,tokenParam:$('#ai-token-param').value,maxTokens:Number($('#ai-tokens').value),apiKey:$('#ai-key').value.trim(),noKey:$('#ai-no-key').checked};
}
function settingsBusy(busy) {
  state.settingsBusy=busy; $('#ai-dialog').setAttribute('aria-busy',String(busy));
  $('#profile-form').querySelectorAll('input,select,button').forEach(el=>el.disabled=busy);
  $('#profile-edit').disabled=busy; if(!busy) $('#ai-key').disabled=$('#ai-no-key').checked;
}
$('#ai-settings').addEventListener('click',()=>{
  if(state.settingsBusy){$('#ai-dialog').showModal();return;}
  $('#ai-preset').innerHTML=state.ai.presets.map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('');
  profilePicker($('#reviewer').value==='codex' ? '' : $('#reviewer').value); fillProfile(); $('#ai-dialog').showModal();
});
$('#close-ai').addEventListener('click',()=>$('#ai-dialog').close());
$('#ai-dialog').addEventListener('close',()=>{$('#ai-key').value='';});
$('#profile-edit').addEventListener('change',fillProfile);
$('#ai-preset').addEventListener('change',applyPreset);
$('#ai-no-key').addEventListener('change',()=>{$('#ai-key').disabled=$('#ai-no-key').checked; if($('#ai-no-key').checked)$('#ai-key').value='';});
$('#use-vision').addEventListener('change',reviewerStatus);
$('#reviewer').addEventListener('change',async()=>{
  reviewerStatus(); const value=$('#reviewer').value; setBusy(true);
  try {await api('/api/profiles/select',{id:value}); state.ai.defaultId=value;}
  catch(e){$('#reviewer').value=state.ai.defaultId;reviewerStatus();showError(e.message);} finally{setBusy(false);}
});
$('#profile-form').addEventListener('submit',async e=>{
  e.preventDefault(); const draft=profileDraft(); settingsBusy(true); settingsResult();
  try {state.ai=await api('/api/profiles/save',draft); $('#ai-key').value='';updateReviewers();profilePicker(state.ai.savedId);fillProfile();settingsResult('已加密保存并选用此接口。可以先测试看图，再开始自动评审。');}
  catch(e){settingsResult(e.message,true);} finally{settingsBusy(false);}
});
$('#test-profile').addEventListener('click',async()=>{
  if(!$('#profile-form').reportValidity())return;
  const draft=profileDraft(); settingsBusy(true); settingsResult('正在发送测试图并等待模型识别，通常需要几秒至一分钟…');
  try {const result=await api('/api/profiles/test',draft);settingsResult(result.message+' 本次测试不会保存未保存的配置。');}
  catch(e){settingsResult(e.message,true);} finally{settingsBusy(false);}
});
$('#delete-profile').addEventListener('click',async()=>{
  if(!confirm('移除此接口配置和本机保存的密钥？历史报告会保留。'))return;
  settingsBusy(true);
  try{state.ai=await api('/api/profiles/delete',{id:$('#profile-edit').value});updateReviewers();profilePicker();fillProfile();settingsResult('已移除接口配置。');}
  catch(e){settingsResult(e.message,true);}finally{settingsBusy(false);}
});
const exampleRoutes = {
  moss: {name:'苔港 · 打开与关闭背包', viewport:[1280,720], steps:[
    {label:'核对当前任务', action:'text', selector:'.quest strong', text:'修复北岸灯塔'},
    {label:'按 Tab 打开背包', action:'key', key:'Tab'},
    {label:'核对背包标题', action:'text', selector:'.inventory h1', text:'旅行背包'},
    {label:'按 Esc 收起背包', action:'key', key:'Escape'},
    {label:'确认拾取提示重新可见', action:'visible', selector:'.reward'}
  ]},
  rust: {name:'Rustfire · 入场、移动与暂停', viewport:[1280,720], steps:[
    {label:'核对泵站入口', action:'text', selector:'#action', text:'进入泵站'},
    {label:'进入关卡', action:'click', selector:'#action'},
    {label:'向右行进', action:'hold', key:'d', ms:380},
    {label:'暂停游戏', action:'key', key:'Escape'},
    {label:'确认暂停菜单出现', action:'text', selector:'#headline', text:'已暂停'}
  ]},
  custom: {name:'我的游戏 · 开场', viewport:[1280,720], steps:[{label:'记录开场',action:'capture'}]}
};
function fillRoute(key) {
  const old = $('#web-url').value;
  $('#web-route').value=JSON.stringify(exampleRoutes[key],null,2);
  $('#web-url').value=key==='moss' ? location.origin+'/demo/practice.html' : key==='rust' ? 'http://127.0.0.1:4173/pilot/index.html' : (old || 'http://127.0.0.1:8000/');
}
$('#web-preset').addEventListener('change',e=>fillRoute(e.target.value));
$('#web-start').addEventListener('click',async()=>{
  showError();
  let route;
  try { route=JSON.parse($('#web-route').value); } catch {showError('操作步骤的 JSON 格式有误，请检查引号和逗号。');return;}
  setBusy(true);
  try {
    const result=await api('/api/web-play',{url:$('#web-url').value.trim(),route});
    state.active=result.id;
    await loadReport(result.id,true);
    refresh();
  } catch(e){showError(e.message);} finally {setBusy(false);}
});
$('#content').addEventListener('click',e=>{
  if(!e.target.closest('#replay-web') || state.active || !state.report?.route) return;
  setCaptureMode('web');
  $('#web-preset').value='custom';
  $('#web-url').value=state.report.url;
  $('#web-route').value=JSON.stringify(state.report.route,null,2);
  $('#web-start').focus();
  $('.intake').scrollIntoView({block:'start'});
});

if (!staticDemo) setInterval(elapsed,1000);
initialize();
