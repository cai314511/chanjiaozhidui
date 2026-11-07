import {state} from './core.js';

const roles={student:'学习成长精灵',employer:'企业合作精灵',university:'高校培养精灵'};
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const images=new Map();
let current=null,entryController=null,observer=null,requestVersion=0;

function audience(){return state.user?state.user.role:'guest';}
async function loadPool(target){
 const pool=target==='guest'?Object.keys(roles):roles[target]?[target]:[];
 const ready=await Promise.all(pool.map(load));
 return pool.filter((role,index)=>ready[index]);
}
function sample(pool){return pool[Math.floor(Math.random()*pool.length)];}

function load(role){
 if(!images.has(role))images.set(role,new Promise(resolve=>{
  const image=new Image();
  image.onload=()=>resolve(true);
  image.onerror=()=>resolve(false);
  image.src=`/assets/mascots/${role}.png`;
 }));
 return images.get(role);
}

function setCell(layer,cell,role){
 // 两层各自持有图集，跨角色切换也保留正在淡出的原形象。
 layer.className=`mascot-pose mascot-cell-${cell} mascot-${role}`;
}

function stop(controller){
 if(!controller)return;
 clearTimeout(controller.timer);cancelAnimationFrame(controller.frame);
 controller.stage.getAnimations({subtree:true}).forEach(animation=>animation.cancel());
}

function stopHome(){
 if(!current)return;
 const old=current;current=null;
 stop(old);
 old.stage.remove();old.host.classList.remove('has-role-mascot');
}
function stopEntry(){stop(entryController);entryController=null;}
function active(controller){return controller===current||controller===entryController;}

function schedule(controller){
 clearTimeout(controller.timer);
 if(!active(controller)||document.hidden||reduced.matches)return;
 if(controller.kind==='entry'&&(controller.audience!=='guest'||controller.pool.length<2))return;
 controller.timer=setTimeout(()=>advance(controller),3000);
}

function advance(controller){
 if(!active(controller)||!controller.stage.isConnected)return;
 let choice={role:controller.role,pose:controller.pose%9+1};
 if(controller.audience==='guest'){
  const poses=controller.kind==='entry'?[0]:[1,2,3,4,5,6,7,8,9];
  const options=controller.pool.flatMap(role=>poses.map(pose=>({role,pose})))
   .filter(item=>item.role!==controller.role||item.pose!==controller.pose);
  if(!options.length)return;
  choice=sample(options);
 }
 const from=controller.layers[controller.front],to=controller.layers[1-controller.front];
 setCell(to,choice.pose,choice.role);to.style.opacity='0';
 controller.pose=choice.pose;controller.role=choice.role;
 controller.stage.dataset.pose=String(choice.pose);controller.stage.dataset.mascotRole=choice.role;
 if(controller.kind==='hero')controller.stage.className=`role-mascot-stage mascot-${choice.role}`;
 const start=performance.now();
 function blend(now){
  if(!active(controller))return;
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

function mount(host,target,pool){
 const role=target==='guest'?sample(pool):target;
 const stage=document.createElement('div');
 stage.className=`role-mascot-stage mascot-${role}`;
 stage.dataset.mascotRole=role;stage.dataset.pose='1';stage.dataset.motion=reduced.matches?'reduced':'running';
 stage.dataset.mascotAudience=target;
 stage.setAttribute('aria-hidden','true');
 stage.innerHTML='<div class="mascot-aura"></div><div class="mascot-rail"></div><div class="mascot-arrival"><div class="mascot-body"><div class="mascot-pose mascot-cell-1"></div><div class="mascot-pose mascot-cell-1"></div></div></div><span class="mascot-shadow"></span>';
 host.classList.add('has-role-mascot');host.append(stage);
 const layers=[...stage.querySelectorAll('.mascot-pose')];
 layers.forEach((layer,index)=>{setCell(layer,1,role);layer.style.opacity=index?'0':'1';});
 const controller={kind:'hero',host,stage,role,audience:target,pool,layers,pose:1,front:0,timer:null,frame:null};
 current=controller;schedule(controller);
 if(document.hidden)visibility();
}

function reconcile(){
 const target=audience();
 const host=state.route==='home'&&(target==='guest'||roles[target])?document.querySelector(target==='guest'?'.discovery-hero':'.discovery-search,.intel-hero'):null;
 if(current&&(current.host!==host||current.audience!==target))stopHome();
 if(!host||current)return;
 const epoch=state.sessionEpoch;
 loadPool(target).then(pool=>{
  if(pool.length&&!current&&host.isConnected&&state.route==='home'&&audience()===target&&epoch===state.sessionEpoch)mount(host,target,pool);
 });
}

export function bindRoleMascots(){
 const target=audience(),entry=document.querySelector('#agent-toggle'),version=++requestVersion,epoch=state.sessionEpoch;
 if(!entry)return;
 if(target!=='guest'&&!roles[target]){
  stopEntry();delete entry.dataset.mascotAudience;
  delete entry.dataset.mascotRole;delete entry.dataset.mascotReady;
  entry.classList.remove('mascot-entry');entry.textContent='✦';entry.removeAttribute('title');stopHome();
 }else{
  // 同一身份重绘不重启入口轮播；身份变化立即撤下旧角色。
  if(entryController&&(entryController.audience!==target||entryController.epoch!==epoch))stopEntry();
  if(!entryController){
   entry.textContent='✦';entry.classList.remove('mascot-entry');delete entry.dataset.mascotRole;
  }
  entry.dataset.mascotAudience=target;
  entry.title=target==='guest'?'登录后与精灵交流':roles[target]+' · 打开智能助手';
  loadPool(target).then(pool=>{
   if(version!==requestVersion||epoch!==state.sessionEpoch||audience()!==target)return;
   const ready=pool.length>0;
   entry.dataset.mascotReady=String(ready);entry.classList.toggle('mascot-entry',ready);
   if(ready&&!entryController){
    const role=target==='guest'?sample(pool):target;
    entry.innerHTML='<span class="mascot-entry-art" aria-hidden="true"><span class="mascot-pose"></span><span class="mascot-pose"></span></span><span class="mascot-entry-label" aria-hidden="true">聊一聊</span>';
    const layers=[...entry.querySelectorAll('.mascot-pose')];
    layers.forEach((layer,index)=>{setCell(layer,0,role);layer.style.opacity=index?'0':'1';});
    entry.dataset.mascotRole=role;entry.dataset.pose='0';
    entryController={kind:'entry',stage:entry,role,audience:target,pool,epoch,layers,pose:0,front:0,timer:null,frame:null};
    schedule(entryController);if(document.hidden)visibility();
   }
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
 for(const controller of [current,entryController].filter(Boolean)){
 clearTimeout(controller.timer);cancelAnimationFrame(controller.frame);controller.frame=null;
 // 在不可见时收束叠化；恢复后从已展示的姿态继续，不追赶隐藏期间的轮播。
 controller.layers.forEach((layer,index)=>{layer.style.opacity=index===controller.front?'1':'0';});
 controller.stage.getAnimations({subtree:true}).forEach(animation=>document.hidden?animation.pause():animation.play());
 controller.stage.dataset.motion=reduced.matches?'reduced':document.hidden?'paused':'running';
 if(!document.hidden)schedule(controller);
 }
}

window.addEventListener('navigate',stopHome);
window.addEventListener('identity-reset',()=>{requestVersion++;stopHome();stopEntry();bindRoleMascots();});
document.addEventListener('visibilitychange',visibility);
reduced.addEventListener('change',()=>{stopHome();stopEntry();bindRoleMascots();});
