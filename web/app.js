import {state,actions,e,roleNames,api,on,navigate,refresh,toast,paintBars,sessionRequests} from './core.js';
import {jobs,applications,documentsPage,allocationPage,universityPage,auth} from './views.js';
import {bindAllocation,bindJobActions} from './workflows.js';
import {profilePage,bindProfile,weightsPage,loadWeights,guidancePage,appendPortfolio,inputHub,installInputHelpers} from './product.js';
import {installGlass,updateGlass} from './glass.js';
import './voice.js';
import {curriculumPage,bindCurriculum} from './curriculum.js';
import {openAssistant,closeAssistant} from './assistant.js';
import {researchDataPage,decisionPage,rulesPage,bindCompetition} from './competition.js';
import {administrationPage,schoolProfilePanel} from './administration.js';
import {evidencePage,evidenceTeaser,bindEvidence} from './evidence.js';
import {discoveryHome,bindDiscovery} from './discovery.js';
import {mySpacePage,publishedStudentsPage,bindMySpace} from './my-space.js';
import {universityInputHub,bindUniversityCourses,universityMaterialsPage} from './university-courses.js';
import {universityIntelligencePage,bindUniversityIntelligence} from './university-intelligence.js';
import {bindRoleMascots} from './role-mascots.js';

const routes={home:['◇','研究首页'],jobs:['▱','岗位与能力'],profile:['♧','我的能力画像'],applications:['▤','投递与双向选择'],weights:['≋','能力权重实验室'],allocation:['▦','招聘资源分配'],university:['⌂','高校培养诊断'],curriculum:['◈','培养方案优化'],documents:['▧','资料与证据库'],model:['⊙','评分与决策依据']};
Object.assign(routes,{research:['▧','产业资料管理'],decision:['◈','专业调整决策'],rules:['▤','管理与审查']});
routes.home[1]='工作空间';routes.weights[1]='招聘偏好';routes.model[1]='使用帮助';
routes.admin=['⌘','统一管理入口'];
routes.evidence=['▥','产业数据支撑'];
routes['my-space']=['♧','我的'];routes.students=['♧','学生主页'];routes.home[1]='探索首页';
function allowed(){const role=state.user?.role;routes.home[1]=role==='university'?'需求研判中心':'探索首页';routes.documents[1]=role==='university'?'本校培养资料库':'资料与证据库';routes.jobs[1]=role==='university'?'岗位需求证据':'岗位与能力';if(role==='admin')return ['admin','home','students','evidence','model'];if(state.publicDemo&&role==='university')return ['home','evidence','research','decision','rules','model'];routes.curriculum[1]=role==='student'?'学习方案优化':'培养方案优化';return ['home',...(role==='employer'?['jobs','weights','applications','allocation']:role==='student'?['my-space','profile','jobs','applications','curriculum']:role==='university'?['university','research','decision','rules','jobs','curriculum']:[]),...(role?['students','evidence','documents']:[]),'model'];}
function shell(){return `<div class="shell"><aside class="sidebar" id="sidebar"><a class="brand" href="#home" data-action="route" data-id="home"><span class="monogram">链</span><div><h2>智链产教</h2><small>连接产业与人才成长</small></div></a><div class="nav-label">${state.user?roleNames[state.user.role]+' / 工作空间':'探索 / 产教协同'}</div><nav class="nav" aria-label="主导航">${allowed().map(k=>`<button class="${state.route===k?'active':''}" data-action="route" data-id="${k}"><span class="nav-icon">${routes[k][0]}</span>${routes[k][1]}</button>`).join('')}</nav><div class="sidebar-foot"><div class="status"><span class="dot ${state.health.agent_configured?'live':'off'}"></span>${state.health.agent_configured?'DeepSeek · 已配置':'DeepSeek · 待配置'}</div><small>发现方向 · 展示经历 · 双向选择</small><div class="account"><span class="avatar">${state.user?e(state.user.name.slice(0,1)):'访'}</span><div class="account-info"><strong>${state.user?e(state.user.name):'访客'}</strong><small>${state.user?roleNames[state.user.role]:'登录后进入工作空间'}</small></div><button class="logout" data-action="${state.user?'logout':'login'}">${state.user?'退出':'登录'}</button></div></div></aside><main class="main"><header class="topbar"><div class="inline"><button class="mobile-menu" data-action="mobile-menu" aria-label="切换导航">☰</button><span class="breadcrumb">智链产教　/　${routes[state.route]?.[1]||'探索首页'}</span></div><div class="topbar-right"><span class="tag">产业 × 人才成长</span>${state.user?'<span class="status"><span class="dot live"></span>本地工作空间</span>':'<button class="text-button" data-action="register">注册 / 登录 ↗</button>'}</div></header><div class="page" id="page-content"><div class="loading">正在读取工作空间</div></div><footer class="footnote"><span>智链产教 · 基于岗位技能证据与资源约束的高校专业调整决策系统</span><span>兴趣探索 → 双向选择 → 培养决策</span></footer></main></div>`;}
let renderSequence=0;
async function render(){
 const sequence=++renderSequence;
 bindRoleMascots();
 if(state.user?.role==='admin'&&state.route==='home')state.route='admin';
 if(!allowed().includes(state.route))state.route='home';
 const identity=state.user?.id||'guest';
 if(document.querySelector('#app').dataset.identity!==identity||!document.querySelector('.shell')){
  document.querySelector('#app').innerHTML=shell();document.querySelector('#app').dataset.identity=identity;
  document.querySelector('.nav [data-id="model"]')?.replaceChildren(document.createTextNode('⊙　使用帮助'));
  document.querySelector('.sidebar-foot>small').textContent='发现方向 · 了解彼此 · 双向选择';
  document.querySelector('.topbar-right').insertAdjacentHTML('afterbegin','<button class="btn small" data-action="commands" aria-label="搜索功能">⌕ 搜索功能</button>');
 }
 document.querySelectorAll('.nav button').forEach(el=>el.classList.toggle('active',el.dataset.id===state.route));
 document.querySelector('.breadcrumb').textContent='智链产教　/　'+(routes[state.route]?.[1]||'工作空间');
 if((state.user?.role==='admin'||state.user?.administrator)&&!document.querySelector('.admin-toolbar'))document.querySelector('.topbar-right').insertAdjacentHTML('afterbegin',`<div class="admin-toolbar inline"><span class="tag">管理员${state.user.administrator?' · 当前：'+e(state.user.name):''}</span><button class="btn small" data-action="admin-switch">切换工作空间</button>${state.user.administrator?'<button class="btn small" data-action="admin-return">返回管理入口</button>':''}</div>`);
 if(!state.user&&!document.querySelector('[data-action=admin-login]'))document.querySelector('.topbar-right').insertAdjacentHTML('beforeend','<button class="btn small" data-action="admin-login">管理员入口</button>');
 if(state.user?.role==='university'&&!document.querySelector('[data-action="demo-toggle"]'))document.querySelector('.sidebar-foot').insertAdjacentHTML('afterbegin',`<button class="btn small wide" data-action="demo-toggle">${state.publicDemo?'退出公开演示':'进入公开演示模式'}</button>`);
 if(state.publicDemo){document.querySelector('.account-info strong').textContent='展示账号';document.querySelector('.avatar').textContent='展';}
 try{
  let html;
  switch(state.route){
   case'admin':html=await administrationPage();break;
   case'home':html=state.user?.role==='university'?await universityIntelligencePage():await discoveryHome()+await evidenceTeaser();break;
   case'my-space':html=await mySpacePage();break;
   case'students':html=await publishedStudentsPage();break;
   case'evidence':html=await evidencePage();break;
   case'jobs':html=jobs();break;
   case'profile':html=await profilePage(state.pendingProfileDraft||null);state.pendingProfileDraft=null;break;
   case'applications':html=applications();break;
   case'weights':html=weightsPage();break;
   case'allocation':html=allocationPage();break;
   case'university':html=await schoolProfilePanel()+await universityPage();break;
   case'curriculum':html=await curriculumPage();break;
   case'documents':html=state.user?.role==='university'?await universityMaterialsPage():await documentsPage();break;
   case'research':html=await evidenceTeaser()+await researchDataPage();break;
   case'decision':html=await decisionPage();break;
   case'rules':html=await rulesPage();break;
   default:html=guidancePage();
  }
  if(sequence!==renderSequence)return;
  document.querySelector('#page-content').innerHTML=html;
  bindRoleMascots();
  bindProfile();bindAllocation();bindJobActions();bindCompetition();await bindCurriculum();await bindEvidence();bindMySpace();await bindDiscovery();
  if(state.user&&!state.publicDemo&&['jobs','university','curriculum','decision','research'].includes(state.route))document.querySelector('#page-content .section-head')?.insertAdjacentHTML('afterend',state.user.role==='university'?universityInputHub():inputHub());
  bindUniversityCourses();
  await bindUniversityIntelligence();
  if(state.route==='documents'&&state.user.role!=='university')await appendPortfolio();
  if(sequence!==renderSequence)return;
  if(sequence!==renderSequence)return;
  if(state.route==='weights'){
   const select=document.querySelector('#weight-select');
   if(select){
    if(state.selectedWeight){select.value=state.selectedWeight;state.selectedWeight=null;}
    await loadWeights(select.value);
    select.addEventListener('change',()=>loadWeights(select.value).catch(err=>toast(err.message)));
   }
  }
  document.querySelector('#industry-filter')?.addEventListener('change',event=>{state.industry=event.target.value;render();});
  updateGlass();paintBars();window.scrollTo({top:0});
  document.querySelector('#sidebar').classList.remove('open');
  const page=document.querySelector('#page-content');if(!matchMedia('(prefers-reduced-motion:reduce)').matches)page.animate([{opacity:0,transform:'translateY(12px) scale(.985)',filter:'blur(3px)'},{opacity:1,transform:'none',filter:'none'}],{duration:400,easing:'cubic-bezier(.16,1,.3,1)'});
 }catch(err){
  if(sequence===renderSequence)document.querySelector('#page-content').innerHTML=`<div class="empty"><h3>读取未完成</h3><p>${e(err.message)}</p><button class="btn" data-action="reload">重新读取</button></div>`;
 }
}
on('route',el=>navigate(el.dataset.id));on('mobile-menu',()=>document.querySelector('#sidebar').classList.toggle('open'));on('reload',async()=>{await refresh();render();});
on('demo-toggle',()=>{state.publicDemo=!state.publicDemo;document.querySelector('#app').dataset.identity='';sessionStorage.setItem('publicDemo',state.publicDemo?'1':'0');state.sessionEpoch++;window.dispatchEvent(new Event('identity-reset'));for(const controller of sessionRequests)controller.abort();sessionRequests.clear();state.messages=[];state.agentContext={};document.querySelector('#agent-drawer').hidden=true;navigate('rules');toast(state.publicDemo?'展示模式已开启，个人业务页面已收起':'已退出公开演示模式');});
document.addEventListener('click',async event=>{const el=event.target.closest('[data-action]');if(!el)return;event.preventDefault();const fn=actions[el.dataset.action];if(!fn)return;const original=el.disabled;if(el.tagName==='BUTTON')el.disabled=true;try{await fn(el);}catch(err){toast(err.message);}finally{if(el.isConnected&&el.tagName==='BUTTON')el.disabled=original;}});
document.addEventListener('pointermove',event=>{const card=event.target.closest('.glow');if(card){const box=card.getBoundingClientRect();card.style.setProperty('--mx',event.clientX-box.left+'px');card.style.setProperty('--my',event.clientY-box.top+'px');}});
document.querySelector('#agent-toggle').addEventListener('click',()=>{const drawer=document.querySelector('#agent-drawer');if(drawer.hidden)openAssistant();else closeAssistant();});
window.addEventListener('navigate',render);
window.addEventListener('open-student-page',event=>{if(state.user&&actions['student-page'])actions['student-page']({dataset:{id:event.detail}}).catch(error=>toast(error.message));});
async function boot(){try{state.health=await api('/health');}catch(err){toast('服务连接失败：'+err.message);}try{state.user=await api('/auth/me');state.publicDemo=state.user.role==='university'&&sessionStorage.getItem('publicDemo')==='1';await refresh();}catch(err){state.user=null;}await render();const student=new URLSearchParams(location.search).get('student');if(student&&state.user&&actions['student-page'])await actions['student-page']({dataset:{id:student}});}
installGlass();installInputHelpers();boot();
