import {state,actions,api,post,on,e,fmt,button,heading,empty,dialog,closeDialog,refresh,navigate,resetIdentity,toast} from './core.js';
import {companyBrand,bindCompanyBrands} from './company-brand.js';
import {workflowPanel} from './recruiting-workflow.js';
import {universityChartLibrary} from './university-intelligence.js';

const statuses={draft:'草稿',published:'招聘中',paused:'已暂停',closed:'已结束'};
const stages={new:'新投递',reviewing:'评估中',interview:'面试中',offer:'意向沟通（阶段标签）',declined:'暂不合适'};
let charts=[],observer=null,chartSequence=0,messageTimer=null,selectedThread=null,qualificationFilter='',jobQualificationFilter='',candidateJob='',demoChanging=false;
function dispose(){chartSequence++;charts.forEach(c=>c.dispose());charts=[];observer?.disconnect();observer=null;clearTimeout(messageTimer);}
window.addEventListener('navigate',dispose);
window.addEventListener('identity-reset',()=>{dispose();selectedThread=null;qualificationFilter='';candidateJob='';});

async function changeDemo(path,body={}){
 if(demoChanging)return;
 demoChanging=true;
 const toolbar=document.querySelector('.demo-toolbar');
 if(toolbar){toolbar.setAttribute('aria-busy','true');toolbar.querySelectorAll('button').forEach(b=>b.disabled=true);}
 const status=toolbar?.querySelector('.demo-status');
 if(status)status.textContent='正在切换…';
 else toast(path==='enter'?'正在准备演示空间…':'正在更新演示空间…');
 let changed=false;
 try{
  const signal=AbortSignal.timeout(25000);
  const result=await post('/demo/'+path,body,{signal});
  changed=true;
  resetIdentity();state.user=null;state.jobs=[];state.applications=[];state.documents=[];
  state.demo=result.active;
  try{state.user=await api('/auth/me',{signal});await refresh({signal});}catch(error){if(state.demo)throw error;}
  closeDialog();document.querySelector('#app').dataset.identity='';navigate('home');
 }catch(error){
  if(changed){
   closeDialog();document.querySelector('#page-content').innerHTML=
    `<div class="panel"><h3>工作空间暂未加载完成</h3>${button('重新连接','demo-reconnect','','primary')}</div>`;
  }
  throw error.name==='TimeoutError'?new Error('连接超时，请重新打开演示空间或稍后重试。'):error;
 }finally{
  demoChanging=false;
  if(toolbar){toolbar.removeAttribute('aria-busy');toolbar.querySelectorAll('button').forEach(b=>b.disabled=false);}
  if(status)status.textContent='';
 }
}
on('demo-reconnect',()=>location.reload());
on('demo-enter',()=>changeDemo('enter'));
on('demo-exit',()=>changeDemo('exit'));
on('demo-role',el=>changeDemo('switch',{role:el.dataset.id}));
on('demo-reset',()=>dialog('重置体验',`<p>当前体验中的岗位、投递和聊天操作将从初始内容重新开始。正式账号及资料不受影响。</p><div class="inline">${button('返回','close-modal')}${button('确认重置','demo-reset-confirm','','primary')}</div>`));
on('demo-reset-confirm',()=>changeDemo('reset'));
const formalLogout=actions.logout;
on('logout',el=>state.demo?changeDemo('exit'):formalLogout(el));

export function demoToolbar(){
 return state.demo?`<div class="demo-toolbar"><span class="demo-label">演示空间</span><div class="demo-roles">${[['student','学生'],['employer','企业'],['university','高校']].map(([r,n])=>`<button class="${state.user?.role===r?'selected':''}" data-action="demo-role" data-id="${r}">${n}</button>`).join('')}</div><span class="demo-status" role="status"></span>${button('重置体验','demo-reset','','small')}${button('退出演示','demo-exit','','small')}</div>`:'';
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
 return `<header class="intel-hero recruiting-hero"><div><h2>${e(company.name||'企业招聘中心')}</h2>
 <p>复核投递证据，按岗位名额和招聘预算生成建议名单。</p><div class="inline">
 ${button('制定招聘计划','route','allocation','primary')}${button('查看候选人','route','applications')}${button('发布新岗位','new-job')}</div></div></header>
 <div class="metrics">${stat('招聘中岗位',jobs.filter(j=>(j.status||'published')==='published').length,'当前开放投递')}${stat('候选人才',candidates.length,'按学生去重')}${stat('收到投递',apps.length,'跨岗位投递记录')}${stat('双向意向',state.applications.filter(a=>!a.withdrawn&&a.student_chosen&&a.employer_chosen).length,'双方均已选择')}</div>
 <div class="recruiting-grid"><section class="panel"><h3>招聘阶段分布</h3><div class="recruiting-chart" data-recruit-chart="stages" role="img" aria-label="招聘阶段分布"></div></section>
 <section class="panel"><h3>岗位投递与双向选择</h3><div class="recruiting-chart" data-recruit-chart="jobs" role="img" aria-label="岗位投递情况"></div></section></div>
 <div id="recruit-chart-data" hidden data-stages="${e(JSON.stringify(Object.entries(stages).map(([k,name])=>({name,value:apps.filter(a=>a.stage===k).length}))))}"
 data-jobs="${e(JSON.stringify(jobs.map(j=>({name:j.title,count:apps.filter(a=>a.job_id===j.id).length,chosen:state.applications.filter(a=>!a.withdrawn&&a.job_id===j.id&&a.employer_chosen&&a.student_chosen).length}))))}"></div>`;
}

export function employerJobs(){
 return heading('岗位管理','集中管理本公司的岗位发布、测评要求和招聘进展。',button('发布新岗位','new-job','','primary'))+`<div class="recruiting-job-list">${state.jobs.map(j=>{const apps=state.applications.filter(a=>a.job_id===j.id);return `<article class="panel job-card"><div class="section-head"><div><span class="tag">${statuses[j.status||'published']}</span><h3>${e(j.title)}</h3><p>${e(j.city)} · ${e(j.work_mode)} · ${fmt(j.salary_min)}–${fmt(j.salary_max)} 元/月</p></div><strong class="recruiting-count">${apps.length}<small>份投递</small></strong></div><p>${e(j.description.slice(0,150))}</p><div class="chips">${j.requirements.map(r=>`<span class="tag">${e(r.skill)}</span>`).join('')}</div><div class="inline">${button('编辑岗位','edit-job',j.id,'small')}${button('招聘偏好','weight-job',j.id,'small')}${button('查看该岗投递','candidate-job',j.id,'small')}<label class="recruit-status">发布状态<select data-job-status="${e(j.id)}">${Object.entries(statuses).map(([k,n])=>`<option value="${k}" ${(j.status||'published')===k?'selected':''}>${n}</option>`).join('')}</select></label></div></article>`;}).join('')||empty('发布第一个岗位','填写岗位职责、能力要求和招聘名额。',button('发布岗位','new-job'))}</div>`;
}

function candidateCard(c){
 return `<article class="recruit-candidate"><div class="inline"><span class="avatar">${e(c.name.slice(0,1))}</span><div><h4>${e(c.name)}</h4><p class="hint">${e(c.school)} · ${e(c.major)}</p></div>${c.favorite?'<span class="tag">已收藏</span>':''}</div><p>${e(c.career.slice(0,90))}</p><div class="inline">${button('主页与简历','candidate-detail',c.id,'small primary')}${button(c.favorite?'取消收藏':'收藏人才',c.favorite?'candidate-unstar':'candidate-star',c.id,'small')}${button('联系','contact-person',c.id,'small')}</div></article>`;
}

export async function candidatesPage(favorites=false){
 const all=await api('/recruiting/candidates?qualification_status='+encodeURIComponent(qualificationFilter));
 const items=all.map(c=>({...c,applications:c.applications.filter(a=>!candidateJob||candidateJob===a.job_id)}))
  .filter(c=>c.applications.length&&(!favorites||c.favorite));
 const filter=`<div class="toolbar"><label>岗位<select id="candidate-job-filter"><option value="">全部岗位</option>
 ${state.jobs.map(job=>`<option value="${e(job.id)}" ${candidateJob===job.id?'selected':''}>${e(job.title)}</option>`).join('')}</select></label>
 <label>毕业与学历资格<select id="qualification-filter">${[['','全部资格状态'],['eligible','符合'],['excluded','不符合'],['pending','待核实']].map(([v,n])=>`<option value="${v}" ${qualificationFilter===v?'selected':''}>${n}</option>`).join('')}</select></label></div>`;
 const cards=items.map(c=>`<div class="recruiting-candidate-record">${candidateCard(c)}<div class="qualification-summary">${c.applications.map(a=>`<div class="candidate-job-row">
 <strong>${e(a.title)}</strong><small>${stages[a.stage]} · ${{eligible:'招聘条件已核验',excluded:'必要条件不符合',pending:'待复核'}[a.match.status]}</small>
 <p class="hint">毕业与学历：${{eligible:'符合',excluded:'不符合',pending:'待核实'}[a.qualification.status]} ${e(a.qualification.reasons.join('；'))}</p>
 <div class="inline">${button('测评复核','review',a.id,'small')}${button('双向匹配','application-detail',a.id,'small')}${button('邀约与正式意向','application-workflow',a.id,'small')}</div></div>`).join('')}</div></div>`).join('');
 return heading(favorites?'人才收藏':'候选人管理','',favorites?button('全部候选人','route','applications','small'):button('制定招聘计划','route','allocation','primary'))+filter+`<div class="recruiting-candidates">${cards||empty(favorites?'当前筛选下没有收藏的人才':'暂无符合筛选的候选人','可以调整筛选条件。')}</div>`;
}
on('candidate-job',el=>{candidateJob=el.dataset.id;qualificationFilter='';navigate('applications');});

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
 const candidateFilter=document.querySelector('#candidate-job-filter');
 candidateFilter?.addEventListener('change',()=>{candidateJob=candidateFilter.value;navigate(state.route);});
 bindCompanyBrands(document.querySelector('#page-content'));
 if(state.user?.role==='student'&&state.route==='jobs'){
  const epoch=state.sessionEpoch,rows=await api('/recruiting/job-qualifications');if(epoch!==state.sessionEpoch||state.route!=='jobs')return;
  const toolbar=document.querySelector('#page-content .toolbar');
  toolbar?.insertAdjacentHTML('beforeend',`<label>毕业与学历资格<select id="student-qualification-filter">${[['','全部'],['eligible','符合'],['excluded','不符合'],['pending','待核实']].map(([v,n])=>`<option value="${v}" ${jobQualificationFilter===v?'selected':''}>${n}</option>`).join('')}</select></label>`);
  const applyFilter=()=>document.querySelectorAll('#page-content .job-card').forEach(card=>{const ident=card.querySelector('[data-action="student-match"]')?.dataset.id,q=rows[ident];if(!q)return;card.hidden=!!jobQualificationFilter&&q.status!==jobQualificationFilter;});
  document.querySelectorAll('#page-content .job-card').forEach(card=>{const ident=card.querySelector('[data-action="student-match"]')?.dataset.id,q=rows[ident];if(q)card.querySelector('.job-description')?.insertAdjacentHTML('afterend',`<p class="qualification-summary"><strong>毕业与学历资格：${{eligible:'符合',excluded:'不符合',pending:'待核实'}[q.status]}</strong> ${e(q.reasons.join('；')||'该岗位未限制毕业与学历资格')}</p>`);});
  document.querySelector('#student-qualification-filter')?.addEventListener('change',event=>{jobQualificationFilter=event.target.value;applyFilter();});applyFilter();
 }
 document.querySelector('#qualification-filter')?.addEventListener('change',event=>{qualificationFilter=event.target.value;navigate(state.route);});
 document.querySelectorAll('#page-content [data-action="application-detail"]').forEach(el=>{if(!el.parentElement.querySelector('[data-action="application-workflow"]'))el.insertAdjacentHTML('afterend',button('邀约与正式意向','application-workflow',el.dataset.id,'small'));});
 if(state.user&&['student','employer'].includes(state.user.role)&&['messages','applications','home'].includes(state.route)){
  const epoch=state.sessionEpoch,target=document.querySelector('#page-content'),route=state.route,marker=document.createElement('div');target.append(marker);
  const panel=await workflowPanel();
  if(epoch!==state.sessionEpoch||route!==state.route||!marker.isConnected)return;
  marker.outerHTML=panel;
 }
 const allocation=document.querySelector('#allocation-form');
 if(state.demo&&allocation&&!allocation.elements.salary.value){
  allocation.elements.salary.value=150000;
  allocation.elements.training.value=20000;
  allocation.elements.mentor.value=240;
 }
 document.querySelectorAll('[data-job-status]').forEach(select=>{
  if(select.dataset.bound)return;
  select.dataset.bound='true';
  select.addEventListener('change',async()=>{
   const previous=state.jobs.find(job=>job.id===select.dataset.jobStatus)?.status||'published';
   select.disabled=true;
   try{await post('/recruiting/jobs/'+select.dataset.jobStatus+'/status',{status:select.value});await refresh();navigate(state.route);}
   catch(error){select.value=previous;toast(error.message);}
   finally{select.disabled=false;}
  });
 });
 document.querySelectorAll('[data-application-stage]').forEach(s=>s.addEventListener('change',async()=>{try{await post('/recruiting/applications/'+s.dataset.applicationStage+'/stage',{stage:s.value});await refresh();toast('招聘阶段已更新');}catch(err){toast(err.message);}}));
 const form=document.querySelector('#direct-message-form');if(form){await loadMessages();form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;try{await post('/conversations/'+selectedThread+'/messages',{text:form.elements.text.value});form.reset();await loadMessages();}catch(err){toast(err.message);}finally{button.disabled=false;}});}
 const data=document.querySelector('#recruit-chart-data');
 if(data&&!data.dataset.chartsBound){
  data.dataset.chartsBound='true';
  renderRecruitingCharts(data).catch(error=>console.warn('招聘图表未完成',error));
 }
}
async function renderRecruitingCharts(data){
 const sequence=chartSequence;
 const hosts=[...document.querySelectorAll('[data-recruit-chart]')].map(host=>{
  const stages=host.dataset.recruitChart==='stages';
  const rows=JSON.parse(stages?data.dataset.stages:data.dataset.jobs).filter(row=>stages?row.value:row.count||row.chosen);
  host.innerHTML=rows.length?`<ul class="recruit-chart-summary">${rows.map(row=>`<li>${e(row.name)} · ${stages?row.value+' 份':row.count+' 份投递 / '+row.chosen+' 条双向意向'}</li>`).join('')}</ul>`:empty('暂无招聘数据','收到有效投递后展示岗位进展。');
  return {host,rows,stages};
 }).filter(entry=>entry.rows.length);
 if(!hosts.length)return;
 let library;
 try{library=await universityChartLibrary();}catch(error){console.warn(error.message);return;}
 if(!data.isConnected||sequence!==chartSequence)return;
 const palette=['#247b69','#719f97','#bd9c49','#436d79','#c0d4ce'];
 for(const {host} of hosts){
  host.replaceChildren();
  const chart=library.init(host,null,{renderer:'canvas'});charts.push(chart);
  if(host.dataset.recruitChart==='stages')chart.setOption({color:palette,tooltip:{trigger:'item'},legend:{bottom:0},series:[{type:'pie',radius:['45%','72%'],center:['50%','44%'],itemStyle:{borderRadius:9,borderColor:'#f5faf5',borderWidth:4},label:{formatter:'{b}\n{c}份'},data:JSON.parse(data.dataset.stages),animationDuration:950}]});
  else{const rows=JSON.parse(data.dataset.jobs);chart.setOption({color:[palette[0],palette[2]],tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},legend:{bottom:0},grid:{left:25,right:15,top:20,bottom:65,containLabel:true},xAxis:{type:'category',data:rows.map(r=>r.name),axisLabel:{rotate:25,fontSize:10}},yAxis:{type:'value',minInterval:1},series:[{name:'收到投递',type:'bar',barMaxWidth:24,data:rows.map(r=>r.count),itemStyle:{borderRadius:[5,5,0,0]}},{name:'双向意向',type:'bar',barMaxWidth:24,data:rows.map(r=>r.chosen),itemStyle:{borderRadius:[5,5,0,0]}}]});}
 }
 observer=new ResizeObserver(()=>charts.forEach(c=>c.resize()));document.querySelectorAll('[data-recruit-chart]').forEach(h=>observer.observe(h));
}
