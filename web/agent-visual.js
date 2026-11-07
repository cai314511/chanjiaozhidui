// 面板拥有自己的渲染实例；异步加载与关闭通过同一个生命周期校验。
export function createAgentVisual(drawer){
 const host=drawer.querySelector('.agent-orb-stage'),label=drawer.querySelector('#agent-orb-status');
 let orb=null,disposed=false,mode='idle';
 const labels={idle:'准备好了，随时聊聊',listening:'正在倾听',transcribing:'正在确认转写',thinking:'正在思考',error:'本次操作未完成，可以重试'};
 const show=(next,text)=>{if(disposed)return;mode=next;host.dataset.mode=next;label.textContent=text||labels[next];orb?.setMode(next==='transcribing'?'thinking':next)};
 const volume=level=>{if(disposed)return;host.dataset.volume=String(level);orb?.setVolume(level)};
 const fallback=()=>{if(!disposed){orb?.dispose();orb=null;host.dataset.render='fallback';host.innerHTML='<div class="agent-orb-fallback"></div>'}};
 host.addEventListener('water-error',fallback);
 import('./water-orb.js').then(({WaterOrb})=>{
  if(disposed)return;
  try{orb=new WaterOrb(host,{appearance:'assistant'});orb.setMode(mode)}catch(error){fallback()}
 }).catch(fallback);
 show('idle');
 return {show,volume,dispose(){if(disposed)return;disposed=true;host.removeEventListener('water-error',fallback);orb?.dispose();orb=null;host.querySelectorAll('canvas').forEach(canvas=>canvas.remove());host.dataset.render='disposed'}};
}
