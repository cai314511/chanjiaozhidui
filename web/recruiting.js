import {state,actions,api,post,on,e,fmt,button,heading,empty,dialog,closeDialog,refresh,navigate,resetIdentity,toast} from './core.js';
import {companyBrand,bindCompanyBrands} from './company-brand.js';

const statuses={draft:'草稿',published:'招聘中',paused:'已暂停',closed:'已结束'};
const stages={new:'新投递',reviewing:'评估中',interview:'面试中',offer:'已发意向',declined:'暂不合适'};
let charts=[],observer=null,chartSequence=0,messageTimer=null,selectedThread=null;
function dispose(){chartSequence++;charts.forEach(c=>c.dispose());charts=[];observer?.disconnect();observer=null;clearTimeout(messageTimer);}
window.addEventListener('navigate',dispose);
window.addEventListener('identity-reset',()=>{dispose();selectedThread=null;});

async function changeDemo(path,body={}){
 await post('/demo/'+path,body);resetIdentity();state.user=null;state.jobs=[];state.applications=[];state.documents=[];
 state.demo=(await api('/demo/status')).active;
 try{state.user=await api('/auth/me');await refresh();}catch(error){if(state.demo)throw error;}
 closeDialog();document.querySelector('#app').dataset.identity='';navigate('home');
}
on('demo-enter',()=>changeDemo('enter'));
on('demo-exit',()=>changeDemo('exit'));
on('demo-role',el=>changeDemo('switch',{role:el.dataset.id}));
on('demo-reset',()=>dialog('重置体验',`<p>当前体验中的岗位、投递和聊天操作将从初始内容重新开始。正式账号及资料不受影响。</p><div class="inline">${button('返回','close-modal')}${button('确认重置','demo-reset-confirm','','primary')}</div>`));
on('demo-reset-confirm',()=>changeDemo('reset'));
const formalLogout=actions.logout;
on('logout',el=>state.demo?changeDemo('exit'):formalLogout(el));

export function demoToolbar(){
 return state.demo?`<div class="demo-toolbar"><span class="demo-label">演示空间</span><div class="demo-roles">${[['student','学生'],['employer','企业'],['university','高校']].map(([r,n])=>`<button class="${state.user?.role===r?'selected':''}" data-action="demo-role" data-id="${r}">${n}</button>`).join('')}</div>${button('重置体验','demo-reset','','small')}${button('退出演示','demo-exit','','small')}</div>`:'';
}

export function employerInputHub(){return `<div class="input-hub">${button('上传JD与招聘资料','upload')}${button('语音讲述岗位','voice-intro')}${button('智能整理岗位要求','job-assistant')}</div>`;}

export async function companyPage(){
 const c=await api('/company/profile'),market=await api('/market/search?q='+encodeURIComponent(c.name));
 const record=market.companies.find(item=>item.name===c.name);
 return heading('公司主页','维护企业介绍与人才发展方向。',button('编辑公司资料','company-settings','','primary'))+`<section class="panel discovery-company">${record?companyBrand(record):''}<span class="eyebrow">COMPANY PROFILE</span><h4>${e(c.name)}</h4><p class="space-prose">${e(c.description||'完善公司介绍，让候选人了解团队。')}</p><div class="chips">${(c.tracks||[]).map(t=>`<span class="tag">${e(t)}</span>`).join('')}</div>${record?button('查看企业公开主页','market-company',record.id,'small'):''}</section>`;
}

function stat(label,value,caption){return `<article class="metric"><span class="metric-label">${label}</span><strong>${fmt(value)}</strong><small>${caption}</small></article>`;}
export async function recruitingHome(){
 const [company,candidates]=await Promise.all([api('/company/profile'),api('/recruiting/candidates')]);
 const apps=candidates.flatMap(c=>c.applications),jobs=state.jobs;
 return `<header class="intel-hero recruiting-hero"><div><span class="intel-kicker">TALENT × OPPORTUNITY · 企业招聘工作台</span><h2>${e(company.name||'企业招聘中心')}</h2><p>从岗位需求到人才选择，把每一次双向了解连接起来。</p><div class="inline">${button('发布新岗位','new-job','','primary')}${button('查看候选人','route','applications')}</div></div></header><div class="metrics">${stat('招聘中岗位',jobs.filter(j=>(j.status||'published')==='published').length,'当前开放投递')}${stat('候选人才',candidates.length,'按学生去重')}${stat('收到投递',apps.length,'跨岗位投递记录')}${stat('双向意向',state.applications.filter(a=>a.student_chosen&&a.employer_chosen).length,'双方均已选择')}</div><div class="recruiting-grid"><section class="panel"><h3>招聘阶段分布</h3><div class="recruiting-chart" data-recruit-chart="stages" role="img" aria-label="招聘阶段分布"></div></section><section class="panel"><h3>岗位投递与双向选择</h3><div class="recruiting-chart" data-recruit-chart="jobs" role="img" aria-label="岗位投递情况"></div></section></div><section class="panel"><div class="section-head"><div><span class="eyebrow">CANDIDATES</span><h3>值得进一步了解的人才</h3></div>${button('全部候选人','route','applications','small')}</div><div class="recruiting-candidates">${candidates.slice(0,4).map(candidateCard).join('')||empty('等待第一份投递','发布岗位后，候选人的授权资料会在这里汇总。')}</div></section><div id="recruit-chart-data" hidden data-stages="${e(JSON.stringify(Object.entries(stages).map(([k,name])=>({name,value:apps.filter(a=>a.stage===k).length}))))}" data-jobs="${e(JSON.stringify(jobs.map(j=>({name:j.title,count:apps.filter(a=>a.job_id===j.id).length,chosen:state.applications.filter(a=>a.job_id===j.id&&a.employer_chosen&&a.student_chosen).length}))))}"></div>`;
}

export function employerJobs(){
 return heading('岗位管理','集中管理本公司的岗位发布、测评要求和招聘进展。',button('发布新岗位','new-job','','primary'))+`<div class="recruiting-job-list">${state.jobs.map(j=>{const apps=state.applications.filter(a=>a.job_id===j.id);return `<article class="panel job-card"><div class="section-head"><div><span class="tag">${statuses[j.status||'published']}</span><h3>${e(j.title)}</h3><p>${e(j.city)} · ${e(j.work_mode)} · ${fmt(j.salary_min)}–${fmt(j.salary_max)} 元/月</p></div><strong class="recruiting-count">${apps.length}<small>份投递</small></strong></div><p>${e(j.description.slice(0,150))}</p><div class="chips">${j.requirements.map(r=>`<span class="tag">${e(r.skill)}</span>`).join('')}</div><div class="inline">${button('编辑岗位','edit-job',j.id,'small')}${button('招聘偏好','weight-job',j.id,'small')}${button('候选人','route','applications','small')}<label class="recruit-status">发布状态<select data-job-status="${e(j.id)}">${Object.entries(statuses).map(([k,n])=>`<option value="${k}" ${(j.status||'published')===k?'selected':''}>${n}</option>`).join('')}</select></label></div></article>`;}).join('')||empty('发布第一个岗位','填写岗位职责、能力要求和招聘名额。',button('发布岗位','new-job'))}</div>`;
}

function candidateCard(c){
 const a=c.applications[0];
 return `<article class="recruit-candidate"><div class="inline"><span class="avatar">${e(c.name.slice(0,1))}</span><div><h4>${e(c.name)}</h4><p class="hint">${e(c.school)} · ${e(c.major)}</p></div>${c.favorite?'<span class="tag">已收藏</span>':''}</div><p>${e(c.career.slice(0,90))}</p><div class="chips">${c.applications.map(a=>`<span class="tag">${e(a.title)} · ${stages[a.stage]}</span>`).join('')}</div><div class="inline">${button('主页与简历','candidate-detail',c.id,'small primary')}${button(c.favorite?'取消收藏':'收藏人才',c.favorite?'candidate-unstar':'candidate-star',c.id,'small')}${button('联系','contact-person',c.id,'small')}</div>${a?`<div class="inline recruiting-quick">${button('测评复核','review',a.id,'small')}${button('双向匹配','application-detail',a.id,'small')}</div>`:''}</article>`;
}

export async function candidatesPage(favorites=false){const all=await api('/recruiting/candidates'),items=favorites?all.filter(c=>c.favorite):all;return heading(favorites?'人才收藏':'候选人管理','按授权投递查看学生主页、项目作品与匹配情况。')+`<div class="recruiting-candidates">${items.map(candidateCard).join('')||empty(favorites?'还没有收藏的人才':'等待候选人投递','学生提交授权材料后，可查看主页、收藏并联系。')}</div>`;}

on('candidate-detail',async el=>{
 const c=await api('/recruiting/candidates/'+el.dataset.id);
 dialog(c.name+' · 主页与简历',`<div class="space-cover"><span class="avatar">${e(c.name.slice(0,1))}</span><div><h2>${e(c.name)}</h2><p>${e(c.school)} · ${e(c.major)}</p><p>${e(c.career)}</p></div></div><h3>项目与实习经历</h3><p class="space-prose">${e(c.experience)}</p><h3>授权简历与作品</h3><div class="inline">${c.documents.map(d=>button(d.name,'space-public-document',d.url,'small')).join('')}${c.portfolio.map(p=>`<a class="btn small" href="${e(p.url)}" target="_blank" rel="noopener noreferrer">${e(p.name)}</a>`).join('')}</div><h3>岗位评估与招聘进度</h3>${state.applications.filter(a=>a.owner===c.id).map(a=>`<div class="rank-item"><span>${e(a.job.title)}</span>${button('查看测评与双向选择','application-detail',a.id,'small')}<select data-application-stage="${e(a.id)}">${Object.entries(stages).map(([s,label])=>`<option value="${s}" ${(a.stage||'new')===s?'selected':''}>${label}</option>`).join('')}</select></div>`).join('')}<div class="form-actions">${button(c.favorite?'取消收藏':'收藏人才',c.favorite?'candidate-unstar':'candidate-star',c.id)}${button('联系并进入私信','contact-person',c.id,'primary')}</div>`);
 bindRecruiting();
 const applicants=state.applications.filter(a=>a.owner===c.id);
 document.querySelectorAll('#modal [data-application-stage]').forEach((select,index)=>{
  const app=applicants[index];
  select.closest('.rank-item').insertAdjacentHTML('afterend',`<div class="inline recruiting-quick">${button('测评复核','review',app.id,'small')}${button('面试会话','interview',app.id,'small')}${button(app.employer_chosen?'取消意向':'选择该学生','choice',app.id,'small primary')}</div>`);
 });
});
for(const [action,method] of [['candidate-star','PUT'],['candidate-unstar','DELETE']])on(action,async el=>{await api('/recruiting/favorites/'+el.dataset.id,{method});closeDialog();navigate(state.route);toast(method==='PUT'?'已收藏人才':'已取消收藏');});
on('contact-person',async el=>{const thread=await post('/conversations',{target_id:el.dataset.id});selectedThread=thread.id;closeDialog();navigate('messages');});

export async function messagesPage(){
 const threads=await api('/conversations');if(!threads.some(t=>t.id===selectedThread))selectedThread=threads[0]?.id;
 return heading('消息中心','围绕岗位、作品和职业发展进行双向沟通。')+`<div class="message-layout"><aside class="panel message-list">${threads.map(t=>`<button class="message-thread ${t.id===selectedThread?'selected':''}" data-action="select-thread" data-id="${e(t.id)}"><strong>${e(t.other.name)} · ${t.other.role==='employer'?'企业':'学生'}</strong><small>${e(t.last_text.slice(0,50))}</small></button>`).join('')||'<p class="hint">联系候选人后，会话会出现在这里。</p>'}</aside><section class="panel message-conversation">${selectedThread?`<div id="direct-messages" class="direct-messages" aria-live="polite"></div><form id="direct-message-form"><label>发送消息<textarea name="text" required maxlength="4000" rows="3" placeholder="交流岗位安排、项目经历或面试时间"></textarea></label><button class="btn primary" type="submit">发送</button></form>`:empty('开始一次沟通','企业可在候选人主页点击“联系”。')}</section></div>`;
}
on('select-thread',el=>{selectedThread=el.dataset.id;navigate('messages');});

async function loadMessages(){
 const host=document.querySelector('#direct-messages'),epoch=state.sessionEpoch,id=selectedThread;if(!host||!id)return;
 const data=await api('/conversations/'+id+'/messages');if(!host.isConnected||epoch!==state.sessionEpoch||id!==selectedThread)return;
 const atBottom=host.scrollHeight-host.scrollTop-host.clientHeight<70;
 host.innerHTML=data.map(m=>`<article class="direct-bubble ${m.sender===state.user.id?'mine':''}"><p>${e(m.text)}</p><small>${e(m.created.slice(5,16).replace('T',' '))}</small></article>`).join('');
 if(atBottom)host.scrollTop=host.scrollHeight;
 clearTimeout(messageTimer);messageTimer=setTimeout(()=>loadMessages().catch(error=>{if(host.isConnected)toast(error.message);}),4000);
}

export async function bindRecruiting(){
 bindCompanyBrands(document.querySelector('#page-content'));
 const allocation=document.querySelector('#allocation-form');
 if(state.demo&&allocation){
  allocation.elements.salary.value=state.jobs.reduce((s,j)=>s+j.salary_max*j.capacity,0);
  allocation.elements.training.value=state.jobs.reduce((s,j)=>s+j.training_cost*j.capacity,0);
  allocation.elements.mentor.value=state.jobs.reduce((s,j)=>s+j.mentor_hours*j.capacity,0);
 }
 document.querySelectorAll('[data-job-status]').forEach(s=>s.addEventListener('change',async()=>{try{await post('/recruiting/jobs/'+s.dataset.jobStatus+'/status',{status:s.value});await refresh();navigate(state.route);}catch(err){toast(err.message);}}));
 document.querySelectorAll('[data-application-stage]').forEach(s=>s.addEventListener('change',async()=>{try{await post('/recruiting/applications/'+s.dataset.applicationStage+'/stage',{stage:s.value});await refresh();toast('招聘阶段已更新');}catch(err){toast(err.message);}}));
 const form=document.querySelector('#direct-message-form');if(form){await loadMessages();form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;try{await post('/conversations/'+selectedThread+'/messages',{text:form.elements.text.value});form.reset();await loadMessages();}catch(err){toast(err.message);}finally{button.disabled=false;}});}
 const data=document.querySelector('#recruit-chart-data');if(!data)return;
 const sequence=chartSequence;
 if(!window.echarts)await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='/assets/vendor/echarts/echarts.min.js';s.onload=resolve;s.onerror=()=>reject(new Error('图表运行库加载失败'));document.head.append(s);});
 if(!data.isConnected||sequence!==chartSequence)return;
 const palette=['#247b69','#719f97','#bd9c49','#436d79','#c0d4ce'];
 for(const host of document.querySelectorAll('[data-recruit-chart]')){
  const chart=window.echarts.init(host,null,{renderer:'canvas'});charts.push(chart);
  if(host.dataset.recruitChart==='stages')chart.setOption({color:palette,tooltip:{trigger:'item'},legend:{bottom:0},series:[{type:'pie',radius:['45%','72%'],center:['50%','44%'],itemStyle:{borderRadius:9,borderColor:'#f5faf5',borderWidth:4},label:{formatter:'{b}\n{c}份'},data:JSON.parse(data.dataset.stages),animationDuration:950}]});
  else{const rows=JSON.parse(data.dataset.jobs);chart.setOption({color:[palette[0],palette[2]],tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},legend:{bottom:0},grid:{left:25,right:15,top:20,bottom:65,containLabel:true},xAxis:{type:'category',data:rows.map(r=>r.name),axisLabel:{rotate:25,fontSize:10}},yAxis:{type:'value',minInterval:1},series:[{name:'收到投递',type:'bar',barMaxWidth:24,data:rows.map(r=>r.count),itemStyle:{borderRadius:[5,5,0,0]}},{name:'双向意向',type:'bar',barMaxWidth:24,data:rows.map(r=>r.chosen),itemStyle:{borderRadius:[5,5,0,0]}}]});}
 }
 observer=new ResizeObserver(()=>charts.forEach(c=>c.resize()));document.querySelectorAll('[data-recruit-chart]').forEach(h=>observer.observe(h));
}
