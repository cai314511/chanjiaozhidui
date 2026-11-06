import {state,e,fmt,api,post,put,on,navigate,dialog,closeDialog,heading,button,empty,toast,splitList} from './core.js';
import {dictateInto} from './voice.js';

let search={q:'',track:'',page:1},searchVersion=0,guide=null;
window.addEventListener('identity-reset',()=>{search={q:'',track:'',page:1};searchVersion++;guide=null;document.querySelector('#exploration-dialog')?.close();});

export async function discoveryHome(){
 if(!state.user)return `<section class="discovery-hero"><span class="eyebrow">智链产教 · 连接兴趣与机会</span><h1>从你感兴趣的事，<br>找到值得探索的方向。</h1><p>搜索赛道、企业与职业，或让几张问题卡片陪你整理思路。</p><div class="inline">${button('开始探索','register','','primary')}${button('登录工作空间','login')}</div></section><div class="roles">${[['student','学生成长空间','探索方向，记录经历，展示自己的作品。'],['employer','企业工作台','登记赛道，发布岗位，了解人才。'],['university','高校决策中心','连接产业资料与人才培养。']].map(([role,title,text])=>`<button class="role-card" data-action="enter-role" data-id="${role}"><h3>${title}</h3><p>${text}</p></button>`).join('')}</div>`;
 const tracks=await api('/market/tracks');
 return heading(state.user.role==='student'?'找到你的下一种可能':'探索赛道、企业与人才','从本地产业资料和平台发布的岗位开始。',state.user.role==='employer'?button('公司与赛道设置','company-settings','','primary'):'')+
 `<section class="panel discovery-search"><span class="eyebrow">自由搜索 · 按赛道发现</span><h3>想探索什么？从这里开始</h3><form id="discovery-form"><div class="discovery-input"><input name="q" type="search" value="${e(search.q)}" list="track-options" placeholder="输入企业、赛道、职业，或说说你的想法" maxlength="100" autocomplete="off" aria-label="搜索企业、赛道或职业"><datalist id="track-options">${tracks.map(t=>`<option value="${e(t.name)}"></option>`).join('')}</datalist><button type="button" class="btn" data-action="discovery-voice">◉ 语音输入</button><button type="submit" class="btn primary">搜索探索</button></div><div class="discovery-options"><label>按赛道筛选<select name="track"><option value="">全部赛道</option>${tracks.map(t=>`<option value="${e(t.name)}" ${search.track===t.name?'selected':''}>${e(t.name)} · ${fmt(t.count)}</option>`).join('')}</select></label>${state.user.role==='student'?button('还没想好？帮我探索','exploration-start','','gold-btn'):''}${search.track&&state.user.role==='student'?button('收藏这个赛道','favorite-track',search.track):''}</div></form><p class="hint">可直接输入，不必先选行业。历史招聘标注来源与月份；平台新岗位单独标识。</p></section>
 <div id="discovery-results" aria-live="polite"><p class="hint">正在查找企业与岗位…</p></div>`;
}

function historicalCard(j){
 return `<article class="discovery-job"><div><span class="tag">${j.type==='live'?'平台发布':'本地历史资料'}</span><h4>${e(j.title)}</h4><p>${e(j.company)} · ${e(j.city||'城市未注明')} · ${e(j.published||j.month||'')}</p><p class="hint">${j.salary?fmt(j.salary[0])+'–'+fmt(j.salary[1])+' 元/月':'薪资未注明'}</p></div>${j.type==='live'&&state.jobs.some(k=>k.id===j.id)?button('查看岗位','job-detail',j.id,'small'):button('查看企业','market-company',j.company_id,'small')}</article>`;
}
async function loadResults(){
 const host=document.querySelector('#discovery-results');if(!host)return;
 const version=++searchVersion,epoch=state.sessionEpoch,query={...search};
 let data;
 try{data=await api('/market/search?'+new URLSearchParams(query));}catch(error){if(host.isConnected&&version===searchVersion&&epoch===state.sessionEpoch)host.innerHTML=empty('检索未完成',error.message);return;}
 if(!host.isConnected||version!==searchVersion||epoch!==state.sessionEpoch)return;
 const pages=Math.max(1,Math.ceil(Math.max(data.total_companies,data.total_jobs)/data.page_size));
 host.innerHTML=`<section class="panel"><div class="section-head"><div><h3>相关企业</h3><p>${fmt(data.total_companies)} 家匹配企业</p></div>${query.track&&state.user.role==='student'?button('收藏 '+query.track,'favorite-track',query.track,'small'):''}</div><div class="discovery-companies">${data.companies.map(c=>`<article class="discovery-company"><div class="company-symbol">${e(c.name.slice(0,1))}</div><span class="tag">${c.registered?'平台已入驻':'本地资料收录'}</span><h4>${e(c.name)}</h4><div class="chips">${c.tracks.map(t=>`<button class="tag track-chip" data-action="explore-track" data-id="${e(t)}">${e(t)}</button>`).join('')}</div><p class="hint">${fmt(c.history_count)} 条历史公告 · ${fmt(c.live_count)} 个平台岗位</p><div class="inline">${button('查看企业','market-company',c.id,'small')}${state.user.role==='student'?button('收藏企业','favorite-company',c.id,'small'):''}</div></article>`).join('')||empty(data.total_companies?'本页没有其他企业':'还没有匹配的企业',data.total_companies?'相关岗位继续列在下方。':'试试其他关键词或清除赛道筛选。')}</div><div class="inline pagination">${data.page>1?button('上一页','market-page',data.page-1):''}<span class="hint">第 ${data.page} / ${pages} 页 · 企业与岗位同步翻页</span>${data.page<pages?button('下一页','market-page',data.page+1):''}</div></section>
 <section class="panel"><h3>相关岗位</h3><p class="hint">${fmt(data.total_jobs)} 条检索结果；下列历史条目供研究探索，正在招聘的平台岗位以发布标识为准。</p>${data.jobs.map(historicalCard).join('')||empty('暂未找到岗位','可先收藏感兴趣的企业或赛道，留意平台后续发布。')}</section>`;
}

export async function bindDiscovery(){
 const form=document.querySelector('#discovery-form');if(!form)return;
 form.addEventListener('submit',event=>{event.preventDefault();search={...Object.fromEntries(new FormData(form)),page:1};loadResults();});
 form.track.addEventListener('change',()=>{search={...Object.fromEntries(new FormData(form)),page:1};loadResults();});
 await loadResults();
 if(state.user?.role==='student'&&!state.user.administrator&&form.isConnected){const epoch=state.sessionEpoch,progress=await api('/me/exploration');if(epoch===state.sessionEpoch&&form.isConnected&&!progress.seen&&!new URLSearchParams(location.search).has('student'))await startGuide(progress);}
}
on('discovery-voice',el=>{const target=document.querySelector('#discovery-form [name=q]');if(target)dictateInto(target,el).catch(error=>toast(error.message));});
on('explore-track',el=>{search={q:'',track:el.dataset.id,page:1};navigate('home');});
on('market-page',async el=>{search.page=Number(el.dataset.id);await loadResults();document.querySelector('#discovery-results')?.scrollIntoView({block:'start'});});
on('market-company',async el=>{
 const epoch=state.sessionEpoch,c=await api('/market/companies/'+encodeURIComponent(el.dataset.id));if(epoch!==state.sessionEpoch)return;
 dialog(c.name,`<span class="tag">${c.registered?'平台已入驻':'本地资料收录'}</span><div class="chips">${c.tracks.map(t=>`<span class="tag">${e(t)}</span>`).join('')}</div><p>${e(c.description||'从本地招聘资料整理的企业信息。')}</p>${state.user.role==='student'?button('收藏企业','favorite-company',c.id,'gold-btn'):''}<h3>平台发布的岗位</h3>${(c.jobs||[]).map(historicalCard).join('')||'<p class="hint">该企业暂未在平台发布岗位。</p>'}<h3>历史招聘资料</h3>${(c.historical_jobs||[]).map(j=>`<details><summary>${e(j.title)} · ${e(j.city)} · ${e(j.published||j.month||'')}</summary><p class="pre">${e(j.description||'')}</p><p class="hint">${e(JSON.stringify(j.provenance||j.source||''))}</p></details>`).join('')||'<p class="hint">暂无已收录历史公告。</p>'}`);
});
on('favorite-company',async el=>{await post('/me/favorites',{type:'company',target_id:el.dataset.id});toast('已加入我的企业收藏');});
on('favorite-track',async el=>{await post('/me/favorites',{type:'track',target_id:el.dataset.id});toast('已加入我的赛道收藏');});

const questions=[
 {key:'interests',title:'哪些事情让你愿意多花一点时间？',subtitle:'可以多选。还不确定也没关系。',options:['技术与创造','商业与管理','人与服务','艺术与表达','科学与健康','还不确定']},
 {key:'tasks',title:'如果参与一个项目，你更想试试哪一部分？',subtitle:'选你愿意尝试的事，不要求已经熟练。',options:['写代码与做产品','分析数据和规律','设计制作与动手','沟通策划与组织','研究实验与探索','暂时没有偏好']},
 {key:'environment',title:'你愿意先看看哪些工作场景？',subtitle:'方向可以随时调整。',options:['科技研发','金融与商业','制造与新能源','医疗与健康','文化与服务','想多了解一些']},
];
async function startGuide(progress=null){
 if(state.user?.role!=='student')return;
 const epoch=state.sessionEpoch,data=progress||await api('/me/exploration');if(epoch!==state.sessionEpoch)return;
 guide={epoch,index:0,answers:data.answers||{},text:data.text||'',busy:false};
 let modal=document.querySelector('#exploration-dialog');
 if(!modal){modal=document.createElement('dialog');modal.id='exploration-dialog';modal.className='exploration-dialog';document.body.append(modal);modal.addEventListener('cancel',()=>{window.dispatchEvent(new Event('dictation-stop'));guide=null;});modal.addEventListener('close',()=>window.dispatchEvent(new Event('dictation-stop')));}
 paintGuide();if(!modal.open)modal.showModal();
 await put('/me/exploration',{seen:true,answers:guide.answers,text:guide.text});
}
function paintGuide(){
 if(!guide)return;const q=questions[guide.index],selected=guide.answers[q.key]||[],modal=document.querySelector('#exploration-dialog');
 modal.innerHTML=`<div class="guide-top"><span class="eyebrow">一点点发现你 · ${guide.index+1} / ${questions.length}</span><button type="button" class="icon-btn" data-action="explore-skip" aria-label="跳过探索">×</button></div><div class="guide-progress">${questions.map((_,i)=>`<i class="${i<=guide.index?'active':''}"></i>`).join('')}</div><h2>${q.title}</h2><p>${q.subtitle}</p><div class="guide-options">${q.options.map(option=>`<button type="button" class="guide-option ${selected.includes(option)?'selected':''}" aria-pressed="${selected.includes(option)}" data-action="guide-select" data-id="${e(option)}">${e(option)}<span>${selected.includes(option)?'✓':'＋'}</span></button>`).join('')}</div><div class="field"><label>还想补充什么？<textarea id="guide-text" maxlength="2000" data-input-help="1" placeholder="也可以说说你做过、喜欢或不喜欢的事">${e(guide.text)}</textarea></label></div><div class="inline">${button('◉ 语音补充','guide-voice','','small')}<span class="hint">语音在本机转写，可修改文字。</span></div><p id="guide-error" class="error-text"></p><div class="guide-bottom">${guide.index?button('上一步','guide-back'):button('先自己看看','explore-skip')}<button class="btn primary" data-action="guide-next">${guide.index===questions.length-1?'看看适合探索的方向':'继续下一张'}</button></div>`;
 if(!matchMedia('(prefers-reduced-motion:reduce)').matches)modal.animate([{opacity:.4,transform:'translateY(18px) scale(.97)'},{opacity:1,transform:'none'}],{duration:350,easing:'cubic-bezier(.16,1,.3,1)'});
}
function captureGuide(){if(guide)guide.text=document.querySelector('#guide-text')?.value??guide.text;window.dispatchEvent(new Event('dictation-stop'));}
function recordingGuide(){if(document.querySelector('#exploration-dialog .recording')){toast('请先停止录音，确认转写后再继续');return true;}return false;}
function recommendationEvidence(item){
 if(typeof item.evidence==='string')return item.evidence;
 const evidence=item.evidence||{},examples=(evidence.examples||[]).map(v=>v.company+' · '+v.title).join('；');
 return `本地资料关联 ${fmt(evidence.company_count||item.company_count||0)} 家企业。${examples?'可先了解：'+examples:'可以从相关企业和岗位进一步了解。'}`;
}
on('exploration-start',()=>startGuide());
on('guide-select',el=>{if(!guide||recordingGuide())return;captureGuide();const key=questions[guide.index].key,values=guide.answers[key]||[];guide.answers[key]=values.includes(el.dataset.id)?values.filter(v=>v!==el.dataset.id):[...values,el.dataset.id];paintGuide();});
on('guide-voice',el=>{dictateInto(document.querySelector('#guide-text'),el).catch(error=>toast(error.message));});
on('guide-back',()=>{if(!guide||recordingGuide())return;captureGuide();guide.index=Math.max(0,guide.index-1);paintGuide();});
on('explore-skip',()=>{captureGuide();const current=guide;guide=null;document.querySelector('#exploration-dialog')?.close();if(current)put('/me/exploration',{seen:true,answers:current.answers,text:current.text}).catch(error=>toast(error.message));});
on('guide-next',async el=>{
 if(!guide||guide.busy||recordingGuide())return;captureGuide();const current=guide;current.busy=true;el.disabled=true;
 try{
  await put('/me/exploration',{seen:true,answers:current.answers,text:current.text});if(guide!==current)return;
  if(current.index<questions.length-1){current.index++;current.busy=false;paintGuide();return;}
  const result=await post('/market/recommend',{answers:current.answers,text:current.text});if(guide!==current||current.epoch!==state.sessionEpoch)return;
  document.querySelector('#exploration-dialog').innerHTML=`<div class="guide-top"><span class="eyebrow">先探索，再慢慢确定</span><button class="icon-btn" data-action="explore-skip" aria-label="关闭建议">×</button></div><h2>这些方向，值得先了解一下</h2><p class="hint">${e(result.basis)}</p>${result.recommendations.map(r=>`<article class="guide-recommendation"><h3>${e(r.track)}</h3><p>${e(r.reason)}</p><p class="hint">${e(recommendationEvidence(r))}</p><div class="inline">${button('查看企业与岗位','guide-explore',r.track,'primary')}${button('收藏方向','favorite-track',r.track)}</div></article>`).join('')||empty('先从自由搜索开始','目前的回答还没有对应到足够的本地资料，可以补充信息或直接搜索。')}<div class="guide-bottom">${button('重新探索','exploration-start')}${button('先自己看看','explore-skip')}</div>`;
 }catch(error){const target=document.querySelector('#guide-error');if(target)target.textContent=error.message;else toast(error.message);}finally{if(guide===current)current.busy=false;if(el.isConnected)el.disabled=false;}
});
on('guide-explore',el=>{captureGuide();guide=null;document.querySelector('#exploration-dialog').close();search={q:'',track:el.dataset.id,page:1};navigate('home');});

export function installCompanyRegistration(form){
 if(!form.role)return;
 const wrapper=document.createElement('section');wrapper.id='registration-tracks';form.role.closest('.field').after(wrapper);
 let tracks=[];
 const paint=()=>{wrapper.hidden=form.role.value!=='employer';wrapper.innerHTML=`<h3>公司的赛道</h3><p class="hint">可多选，也可填写新赛道。综合性企业可登记多个业务方向。</p><div class="track-picker"><input id="company-track-input" type="text" list="company-track-list" maxlength="100" placeholder="输入或选择赛道"><datalist id="company-track-list">${tracks.map(t=>`<option value="${e(t.name)}"></option>`).join('')}</datalist><button type="button" class="btn" id="add-company-track">添加赛道</button></div><div class="chips" id="company-track-chips"></div><input type="hidden" name="company_tracks" value="[]">`;wrapper.querySelector('#add-company-track').onclick=()=>{const input=wrapper.querySelector('input'),chosen=JSON.parse(form.company_tracks.value),value=input.value.trim();if(value&&!chosen.includes(value)&&chosen.length<20)chosen.push(value);form.company_tracks.value=JSON.stringify(chosen);input.value='';paintChips(chosen);};};
 const paintChips=chosen=>{wrapper.querySelector('#company-track-chips').innerHTML=chosen.map(t=>`<button type="button" class="tag" data-track-remove="${e(t)}">${e(t)} ×</button>`).join('');wrapper.querySelectorAll('[data-track-remove]').forEach(el=>{el.onclick=()=>{const next=chosen.filter(t=>t!==el.dataset.trackRemove);form.company_tracks.value=JSON.stringify(next);paintChips(next);};});};
 paint();form.role.addEventListener('change',paint);
 api('/market/tracks').then(values=>{tracks=values;if(wrapper.isConnected){const chosen=JSON.parse(form.company_tracks.value);paint();form.company_tracks.value=JSON.stringify(chosen);paintChips(chosen);}}).catch(error=>{if(wrapper.isConnected)wrapper.insertAdjacentHTML('beforeend',`<p class="hint">赛道列表暂未载入，可自行输入：${e(error.message)}</p>`);});
}

on('company-settings',async()=>{
 const data=await api('/company/profile'),tracks=await api('/market/tracks');
 dialog('公司与赛道设置',`<form id="company-settings-form"><div class="field"><label>公司名称<input name="name" value="${e(data.name)}" required maxlength="200"></label></div><div class="field"><label>赛道，可多选填写，以逗号分隔<textarea name="tracks" required maxlength="2000" list="settings-tracks">${e(data.tracks.join('，'))}</textarea></label></div><div class="chips">${tracks.slice(0,16).map(t=>`<button type="button" class="tag" data-add-track="${e(t.name)}">＋ ${e(t.name)}</button>`).join('')}</div><div class="field"><label>公司介绍<textarea name="description" maxlength="5000">${e(data.description)}</textarea></label></div><p class="error-text" id="company-settings-error"></p><button class="btn primary" type="submit">保存公司信息</button></form>`);
 const form=document.querySelector('#company-settings-form');form.querySelectorAll('[data-add-track]').forEach(el=>{el.onclick=()=>{form.tracks.value=[...new Set([...splitList(form.tracks.value),el.dataset.addTrack])].join('，');};});
 form.onsubmit=async event=>{event.preventDefault();try{await put('/company/profile',{name:form.elements.namedItem('name').value,tracks:splitList(form.tracks.value),description:form.description.value});closeDialog();toast('公司赛道已更新');navigate('home');}catch(error){document.querySelector('#company-settings-error').textContent=error.message;}};
});
