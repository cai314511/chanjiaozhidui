import {state} from './core.js';

const roles={student:'学习成长精灵',employer:'企业合作精灵',university:'高校培养精灵'};
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const images=new Map();
let current=null,observer=null,requestVersion=0;

function load(role){
 if(!images.has(role))images.set(role,new Promise(resolve=>{
  const image=new Image();
  image.onload=()=>resolve(true);
  image.onerror=()=>resolve(false);
  image.src=`/assets/mascots/${role}.png`;
 }));
 return images.get(role);
}

function setCell(layer,cell){
 layer.className=`mascot-pose mascot-cell-${cell}`;
}

function stopHome(){
 if(!current)return;
 const old=current;current=null;
 clearTimeout(old.timer);cancelAnimationFrame(old.frame);
 old.stage.getAnimations({subtree:true}).forEach(animation=>animation.cancel());
 old.stage.remove();old.host.classList.remove('has-role-mascot');
}

function schedule(controller){
 clearTimeout(controller.timer);
 if(current!==controller||document.hidden||reduced.matches)return;
 controller.timer=setTimeout(()=>advance(controller),3000);
}

function advance(controller){
 if(current!==controller||!controller.stage.isConnected)return;
 const next=controller.pose%9+1,from=controller.layers[controller.front],to=controller.layers[1-controller.front];
 setCell(to,next);to.style.opacity='0';
 controller.pose=next;controller.stage.dataset.pose=String(next);
 const start=performance.now();
 function blend(now){
  if(current!==controller)return;
  const elapsed=Math.max(0,Math.min(1,(now-start)/560));
  const mix=elapsed*elapsed*(3-2*elapsed);
  from.style.opacity=String(1-mix);to.style.opacity=String(mix);
  if(elapsed<1)controller.frame=requestAnimationFrame(blend);
  else controller.frame=null;
 }
 controller.front=1-controller.front;
 controller.frame=requestAnimationFrame(blend);
 schedule(controller);
}

function mount(host,role){
 const stage=document.createElement('div');
 stage.className=`role-mascot-stage mascot-${role}`;
 stage.dataset.mascotRole=role;stage.dataset.pose='1';stage.dataset.motion=reduced.matches?'reduced':'running';
 stage.setAttribute('aria-hidden','true');
 stage.innerHTML='<div class="mascot-aura"></div><div class="mascot-rail"></div><div class="mascot-arrival"><div class="mascot-body"><div class="mascot-pose mascot-cell-1"></div><div class="mascot-pose mascot-cell-1"></div></div></div><span class="mascot-shadow"></span>';
 host.classList.add('has-role-mascot');host.append(stage);
 const layers=[...stage.querySelectorAll('.mascot-pose')];layers[0].style.opacity='1';layers[1].style.opacity='0';
 const controller={host,stage,role,layers,pose:1,front:0,timer:null,frame:null};
 current=controller;schedule(controller);
 if(document.hidden)visibility();
}

function reconcile(){
 const role=state.user?.role;
 const host=state.route==='home'&&roles[role]?document.querySelector('.discovery-search,.intel-hero'):null;
 if(current&&(current.host!==host||current.role!==role))stopHome();
 if(!host||current||!images.has(role))return;
 const epoch=state.sessionEpoch;
 load(role).then(ready=>{
  if(ready&&!current&&host.isConnected&&state.route==='home'&&state.user?.role===role&&epoch===state.sessionEpoch)mount(host,role);
 });
}

export function bindRoleMascots(){
 const role=state.user?.role,entry=document.querySelector('#agent-toggle'),version=++requestVersion,epoch=state.sessionEpoch;
 if(!entry)return;
 if(!roles[role]){
  delete entry.dataset.mascotRole;delete entry.dataset.mascotReady;
  entry.classList.remove('mascot-entry');entry.textContent='✦';entry.removeAttribute('title');stopHome();
 }else{
  // 身份切换时先撤下旧角色，异步结果只允许回写当前身份。
  if(entry.dataset.mascotRole!==role){entry.textContent='✦';entry.classList.remove('mascot-entry');}
  entry.dataset.mascotRole=role;entry.title=roles[role]+' · 打开智能助手';
  load(role).then(ready=>{
   if(version!==requestVersion||epoch!==state.sessionEpoch||state.user?.role!==role)return;
   entry.dataset.mascotReady=String(ready);entry.classList.toggle('mascot-entry',ready);
   entry.innerHTML=ready?`<span class="mascot-entry-art mascot-${role}" aria-hidden="true"><span class="mascot-pose mascot-cell-0"></span></span><span class="mascot-entry-label" aria-hidden="true">聊一聊</span>`:'✦';
   reconcile();
  });
 }
 if(!observer){
  observer=new MutationObserver(reconcile);
  observer.observe(document.querySelector('#app'),{childList:true,subtree:true});
 }
 reconcile();
}

function visibility(){
 const controller=current;if(!controller)return;
 clearTimeout(controller.timer);cancelAnimationFrame(controller.frame);controller.frame=null;
 // 在不可见时收束叠化；恢复后从已展示的姿态继续，不追赶隐藏期间的轮播。
 controller.layers.forEach((layer,index)=>{layer.style.opacity=index===controller.front?'1':'0';});
 controller.stage.getAnimations({subtree:true}).forEach(animation=>document.hidden?animation.pause():animation.play());
 controller.stage.dataset.motion=reduced.matches?'reduced':document.hidden?'paused':'running';
 if(!document.hidden)schedule(controller);
}

window.addEventListener('navigate',stopHome);
window.addEventListener('identity-reset',()=>{requestVersion++;stopHome();bindRoleMascots();});
document.addEventListener('visibilitychange',visibility);
reduced.addEventListener('change',()=>{stopHome();reconcile();});
