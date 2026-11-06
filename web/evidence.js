import {state,api,e,fmt,heading,button,empty,on,dialog} from './core.js';

let filters={q:'',city:'',industry:'',page:1};
let documentFilters={q:'',kind:''};
let jobsSequence=0,documentsSequence=0;
window.addEventListener('identity-reset',()=>{jobsSequence++;documentsSequence++;filters={q:'',city:'',industry:'',page:1};documentFilters={q:'',kind:''};});

function bars(rows){
 const maximum=Math.max(1,...rows.map(r=>r.count));
 return rows.slice(0,10).map(r=>`<div class="evidence-bar"><span>${e(r.name)}</span><div class="bar-track"><i data-bar="${r.count/maximum*100}"></i></div><strong>${fmt(r.count)}</strong></div>`).join('');
}

function salary(row){return row.salary?`${fmt(row.salary[0])}–${fmt(row.salary[1])} 元/月`:'未提供有效双边月薪';}

export async function evidenceTeaser(){
 if(!state.user)return '';
 const summary=await api('/evidence/summary');
 if(!summary.ready)return '';
 return `<section class="panel evidence-teaser"><div><span class="eyebrow">比赛资料 · 已接入</span><h3>从产业数据找到岗位与培养依据</h3><p>${fmt(summary.statistics.total)} 条相关历史公告 · ${fmt(summary.document_count)} 份产业、政策与就业资料</p><p class="hint">2026年文件内样本；每条记录保留出处，薪资、技能和研究结论可核对。</p></div>${button('查看产业数据支撑','route','evidence','primary')}</section>`;
}

export async function evidencePage(){
 const data=await api('/evidence/summary');
 if(!data.ready)return heading('产业数据支撑','招聘、产业、政策与就业资料的可追溯研究依据。')+empty('尚未接入比赛资料','由本机导入脚本完成资料处理后展示。');
 const s=data.statistics;
 return heading('产业数据支撑','从比赛原始资料提取，岗位记录、统计口径与文献出处一起保留。')+
 `<div class="metrics"><div class="metric"><span class="metric-label">相关历史公告 · 去重后</span><strong>${fmt(s.total)}</strong><small>AI 产品与金融科技相关岗位</small></div><div class="metric"><span class="metric-label">读取招聘记录</span><strong>${fmt(data.processing.scanned_rows)}</strong><small>两份2026年CSV全文件</small></div><div class="metric"><span class="metric-label">报价区间中点中位数</span><strong>${s.salary_midpoint_median===null?'缺失':fmt(s.salary_midpoint_median)}</strong><small>元/月 · ${fmt(s.salary_sample)}条有效报价</small></div><div class="metric"><span class="metric-label">研究资料</span><strong>${fmt(data.document_count)}</strong><small>${e(Object.entries(data.document_kinds).map(([k,v])=>k+' '+v).join(' · '))}</small></div></div>
 <section class="panel"><h3>数据范围与计算口径</h3><p>${e(data.processing.scope)}</p><p class="hint">${e(data.processing.method)} ${e(s.salary_basis)}</p><p class="hint">技能仅表示公告提及；缺少等级、已核实招聘人数和本校毕业样本时，相应数值不进入培养优化模型。</p><details><summary>两份原文件与处理记录</summary>${data.processing.sources.map(source=>`<p><strong>${e(source.name)}</strong> · 读取 ${fmt(source.scanned_rows)} 条 · 筛中 ${fmt(source.matched_rows)} 条</p><p class="hint">原始包：${e(source.archive||source.name)}${source.member?' / '+e(source.member):''}</p><p class="hash">SHA-256 ${e(source.sha256)}</p>`).join('')}<p class="hint">内容合并 ${fmt(data.processing.duplicate_rows)} 条；相关公告日期无效 ${fmt(data.processing.invalid_dates)} 条。岗位属于历史研究样本，不提供在线投递。</p></details></section>
 <div class="grid2"><section class="panel"><h3>城市分布 · 公告条数</h3>${bars(s.cities)}</section><section class="panel"><h3>技能关键词 · 公告提及次数</h3>${bars(s.skills)}</section></div>
 <section class="panel"><h3>2026年文件内发布月份</h3><div class="chips">${s.months.map(m=>`<span class="tag">${e(m.name)} · ${fmt(m.count)} 条</span>`).join('')}</div></section>
 <section class="panel"><h3>历史岗位与能力要求</h3><form id="evidence-job-filter" class="evidence-filters"><label>岗位 / 技能<input name="q" value="${e(filters.q)}" maxlength="100" placeholder="如：产品经理、Python、风控"></label><label>城市<select name="city"><option value="">全部城市</option>${s.cities.map(c=>`<option value="${e(c.name)}" ${c.name===filters.city?'selected':''}>${e(c.name)}</option>`).join('')}</select></label><label>方向<select name="industry"><option value="">全部方向</option>${s.industries.map(c=>`<option value="${e(c.name)}" ${c.name===filters.industry?'selected':''}>${e(c.name)}</option>`).join('')}</select></label><button class="btn primary" type="submit">筛选岗位</button></form><div id="evidence-jobs" aria-live="polite"></div></section>
 <section class="panel"><h3>产业、政策与就业证据</h3><form id="evidence-document-filter" class="evidence-filters"><label>正文关键词<input name="q" value="${e(documentFilters.q)}" maxlength="100" placeholder="如：人工智能、月收入、产教融合"></label><label>资料类型<select name="kind"><option value="">全部资料</option>${Object.keys(data.document_kinds).map(k=>`<option value="${e(k)}" ${k===documentFilters.kind?'selected':''}>${e(k)}</option>`).join('')}</select></label><button class="btn primary" type="submit">检索证据</button></form><div id="evidence-documents" aria-live="polite"></div></section>
 <section class="panel"><h3>资料接入清单</h3>${data.inventory.map(i=>`<div class="document"><div><h4>${e(i.name)} <span class="tag">${e(i.status)}</span></h4><p class="hint">${e(i.reason)}</p></div></div>`).join('')}<p class="hint">本次处理：${e(data.created_at.slice(0,10))} · 仅在本机处理，未向外部模型发送资料正文。</p></section>`;
}

async function loadJobs(){
 const host=document.querySelector('#evidence-jobs');if(!host)return;
 const sequence=++jobsSequence;
 let response;
 try{response=await api('/evidence/jobs?'+new URLSearchParams({...filters}));}catch(error){if(host.isConnected&&sequence===jobsSequence)throw error;return;}
 if(!host.isConnected||sequence!==jobsSequence)return;
 host.innerHTML=`<p class="hint">找到 ${fmt(response.total)} 条 · 第 ${response.page} / ${Math.max(1,Math.ceil(response.total/20))} 页</p>`+response.items.map(j=>`<details class="evidence-job"><summary><strong>${e(j.title)}</strong><span>${e(j.city)} · ${e(j.month)} · ${salary(j)}</span></summary><div class="chips"><span class="tag">${e(j.industry)}</span><span class="tag">${e(j.education||'学历未注明')}</span><span class="tag">原经验字段：${e(j.experience||'未注明')}</span>${j.skills.map(s=>`<span class="tag">${e(s)}</span>`).join('')}</div><p class="pre">${e(j.description)}</p><p class="hint">出处：${j.provenance.map(p=>`${e(p.file)} · 原CSV第 ${p.line} 行起`).join('；')}</p></details>`).join('')+(response.total?'':empty('没有匹配记录','调整关键词、方向或城市。'))+`<div class="inline">${response.page>1?button('上一页','evidence-page',response.page-1):''}${response.page*20<response.total?button('下一页','evidence-page',response.page+1):''}</div>`;
}

async function loadDocuments(){
 const host=document.querySelector('#evidence-documents');if(!host)return;
 const sequence=++documentsSequence;
 let docs;
 try{docs=await api('/evidence/documents?'+new URLSearchParams({...documentFilters}));}catch(error){if(host.isConnected&&sequence===documentsSequence)throw error;return;}
 if(!host.isConnected||sequence!==documentsSequence)return;
 host.innerHTML=`<p class="hint">${fmt(docs.length)} 份匹配资料</p>`+docs.map(d=>`<article class="document evidence-document"><div><span class="tag">${e(d.kind)}</span><h4>${e(d.title)}</h4><small>${e(d.status)}${d.pages?' · '+d.pages+'页':''}</small>${d.matches.slice(0,1).map(b=>`<p class="hint evidence-excerpt">${e(b.location)} · ${e(b.text.slice(0,180))}…</p>`).join('')}</div>${button('查看证据','evidence-document',d.id,'small')}</article>`).join('');
}

export async function bindEvidence(){
 const jobs=document.querySelector('#evidence-job-filter');if(!jobs)return;
 jobs.addEventListener('submit',event=>{event.preventDefault();const values=Object.fromEntries(new FormData(jobs));filters={...values,page:1};loadJobs().catch(error=>{if(jobs.isConnected)document.querySelector('#evidence-jobs').textContent=error.message;});});
 const documents=document.querySelector('#evidence-document-filter');
 documents.addEventListener('submit',event=>{event.preventDefault();documentFilters=Object.fromEntries(new FormData(documents));loadDocuments().catch(error=>{if(documents.isConnected)document.querySelector('#evidence-documents').textContent=error.message;});});
 await Promise.all([loadJobs(),loadDocuments()]);
}

on('evidence-page',async el=>{filters.page=Number(el.dataset.id);await loadJobs();document.querySelector('#evidence-job-filter').scrollIntoView({block:'start'});});
on('evidence-document',async el=>{
 const d=await api('/evidence/documents/'+el.dataset.id);
 dialog(d.title,`<p class="hint">${e(d.kind)} · ${e(d.status)}</p><p class="hint">${e(d.basis)}</p><p class="hint">来源定位：比赛数据 / ${e(d.path)}</p><p class="hash">SHA-256 ${e(d.sha256)}</p>${d.blocks.length?d.blocks.map(b=>`<section class="evidence-block"><h4>${e(b.location)}${b.excerpt?' · 节选':''}</h4><p class="pre">${e(b.text)}</p></section>`).join(''):empty('正文需要OCR','已登记文件及指纹，未用空白文本生成统计。')}`);
});
