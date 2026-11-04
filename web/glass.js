import {state,e,navigate,on,toast} from './core.js';

let capsule, lastTop=0, focused=null, dock=null, focusToken=0;
const fine=matchMedia('(hover:hover) and (pointer:fine)'), reduced=matchMedia('(prefers-reduced-motion:reduce)');
export function updateGlass(){
 const nav=document.querySelector('.nav'), active=nav?.querySelector('button.active');
 if(!nav||!active)return;
 capsule=nav.querySelector('.nav-capsule');
 if(!capsule){capsule=document.createElement('span');capsule.className='nav-capsule';capsule.ariaHidden='true';nav.prepend(capsule);}
 const top=active.offsetTop,height=active.offsetHeight;
 capsule.style.height=height+'px';capsule.style.transform=`translateY(${top}px)`;
 if(!reduced.matches)capsule.animate([{transform:`translateY(${lastTop}px) scaleY(1)`},{transform:`translateY(${(top+lastTop)/2}px) scaleY(1.28)`},{transform:`translateY(${top}px) scaleY(.94)`},{transform:`translateY(${top}px) scaleY(1)`}],{duration:520,easing:'cubic-bezier(.2,.75,.2,1)'});
 lastTop=top;
 document.querySelectorAll('#page-content .panel,#page-content .card,#page-content .metric,#page-content .job-card').forEach(el=>{
  el.classList.add('liquid-card');
  if(!el.querySelector(':scope > .expand-module')){
   const title=el.querySelector('h2,h3,.metric-label')?.textContent;
   if(title){const btn=document.createElement('button');btn.className='expand-module';btn.type='button';btn.ariaLabel='展开'+title;btn.textContent='↗';btn.addEventListener('click',()=>expand(el));el.prepend(btn);}
  }
 });
}
let pointFrame;
document.addEventListener('pointermove',event=>{
 if(!fine.matches||reduced.matches)return;
 const card=event.target.closest('.liquid-card');if(!card)return;
 cancelAnimationFrame(pointFrame);
 pointFrame=requestAnimationFrame(()=>{const rect=card.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
  card.style.setProperty('--mx',x+'px');card.style.setProperty('--my',y+'px');
  card.style.setProperty('--rx',Math.max(-4,Math.min(4,(.5-y/rect.height)*5))+'deg');
  card.style.setProperty('--ry',Math.max(-4,Math.min(4,(x/rect.width-.5)*5))+'deg');card.classList.add('pointer-lit');
 });
});
document.addEventListener('pointerout',event=>{const card=event.target.closest('.liquid-card');if(card&&!card.contains(event.relatedTarget)){card.classList.remove('pointer-lit');card.style.setProperty('--rx','0deg');card.style.setProperty('--ry','0deg');}});

function expand(el){
 if(focused?.el===el)return;
 if(focused)closeFocus(true);
 const items=[...document.querySelectorAll('#page-content .liquid-card')].filter(c=>c.querySelector('h2,h3,.metric-label'));
 const rect=el.getBoundingClientRect(), placeholder=document.createElement('div');placeholder.style.height=rect.height+'px';el.before(placeholder);
 const stage=document.querySelector('#focus-stage');stage.hidden=false;stage.append(el);el.classList.add('expanded-module');
 focused={el,placeholder,rect,trigger:document.activeElement};focusToken++;
 document.body.classList.add('module-focused');
 document.querySelector('#app').inert=true;
 dock=document.querySelector('#module-dock');dock.replaceChildren();
 for(const item of items){const btn=document.createElement('button');btn.className='dock-item'+(item===el?' active':'');const title=item.querySelector('h2,h3,.metric-label').textContent;btn.title=title;btn.setAttribute('aria-label',title);const preview=document.createElement('span');preview.className='dock-preview';preview.ariaHidden='true';const clone=item.cloneNode(true);clone.removeAttribute('id');clone.querySelectorAll('[id]').forEach(node=>node.removeAttribute('id'));clone.querySelectorAll('input,button,select,textarea,video,audio,img').forEach(node=>node.remove());clone.classList.remove('expanded-module');preview.append(clone);btn.append(preview,document.createTextNode(title));btn.onclick=()=>expand(item);dock.append(btn);}
 const close=document.createElement('button');close.className='dock-close';close.textContent='收回 ×';close.onclick=()=>closeFocus();dock.append(close);
 const destination=el.getBoundingClientRect();
 if(!reduced.matches)el.animate([{transform:`translate(${rect.left-destination.left}px,${rect.top-destination.top}px) scale(${rect.width/destination.width},${rect.height/destination.height})`,borderRadius:'26px',opacity:.8},{transform:'none',opacity:1}],{duration:420,easing:'cubic-bezier(.16,1,.3,1)'});
 close.focus();
}
export function closeFocus(immediate=false){
 if(!focused)return;
 const value=focused,token=++focusToken;focused=null;
 const restore=()=>{value.placeholder.replaceWith(value.el);value.el.classList.remove('expanded-module');if(token===focusToken){document.querySelector('#focus-stage').hidden=true;document.body.classList.remove('module-focused');document.querySelector('#app').inert=false;dock?.replaceChildren();}if(value.trigger?.isConnected)value.trigger.focus();};
 if(immediate||reduced.matches){restore();return;}
 const now=value.el.getBoundingClientRect(),target=value.placeholder.getBoundingClientRect();
 value.el.animate([{transform:'none',opacity:1},{transform:`translate(${target.left-now.left}px,${target.top-now.top}px) scale(${target.width/now.width},${target.height/now.height})`,opacity:.6}],{duration:230,easing:'cubic-bezier(.4,0,.8,.3)'}).finished.then(restore);
}
window.addEventListener('navigate',()=>closeFocus(true));
function openCommands(){
 const modal=document.querySelector('#command-panel');if(modal.open)return;
 modal.showModal();modal.querySelector('input').value='';filterCommands('');modal.querySelector('input').focus();
}
let selected=0, commands=[];
function filterCommands(query){
 commands=[...document.querySelectorAll('.nav button[data-id]')].map(el=>({id:el.dataset.id,text:el.textContent.trim()})).filter(v=>v.text.toLowerCase().includes(query.toLowerCase()));selected=0;
 const target=document.querySelector('#command-results');target.innerHTML=commands.length?commands.map((item,index)=>{
  const position=item.text.toLowerCase().indexOf(query.toLowerCase());const label=query?e(item.text.slice(0,position))+'<mark>'+e(item.text.slice(position,position+query.length))+'</mark>'+e(item.text.slice(position+query.length)):e(item.text);
  return `<button role="option" aria-selected="${index===0}" data-command="${e(item.id)}">${label}<span>↵</span></button>`;
 }).join(''):'<p class="hint">没有找到相关功能</p>';
}
function chooseCommand(){if(!commands[selected])return;document.querySelector('#command-panel').close();navigate(commands[selected].id);}
export function installGlass(){
 document.addEventListener('click',event=>{if(event.target.closest('button,a,input,textarea,select,label,summary,form,#module-dock,#focus-stage'))return;const card=event.target.closest('.liquid-card');if(card?.querySelector(':scope > .expand-module')&&!window.getSelection()?.toString())expand(card);});
 const dialog=document.createElement('dialog');dialog.id='command-panel';dialog.innerHTML='<label class="command-label">搜索工作空间<input type="search" placeholder="想要做什么？" autocomplete="off" aria-controls="command-results"></label><div id="command-results" role="listbox"></div><small>↑ ↓ 选择　↵ 打开　Esc 关闭</small>';document.body.append(dialog);
 dialog.querySelector('input').addEventListener('input',event=>filterCommands(event.target.value));
 dialog.addEventListener('click',event=>{const btn=event.target.closest('[data-command]');if(btn){dialog.close();navigate(btn.dataset.command);}});
 dialog.addEventListener('keydown',event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(!commands.length)return;selected=(selected+(event.key==='ArrowDown'?1:-1)+commands.length)%commands.length;dialog.querySelectorAll('[role=option]').forEach((el,i)=>el.setAttribute('aria-selected',i===selected));dialog.querySelectorAll('[role=option]')[selected]?.scrollIntoView({block:'nearest'});}if(event.key==='Enter'){event.preventDefault();chooseCommand();}});
 document.addEventListener('keydown',event=>{if(event.altKey&&event.code==='Space'){event.preventDefault();dialog.open?dialog.close():openCommands();}if(event.key==='Escape')closeFocus();});
 on('commands',openCommands);
 const stage=document.createElement('section');stage.id='focus-stage';stage.hidden=true;stage.setAttribute('aria-label','模块详情');stage.setAttribute('role','dialog');stage.setAttribute('aria-modal','true');document.body.append(stage);
 const bar=document.createElement('nav');bar.id='module-dock';bar.setAttribute('aria-label','模块缩略条');document.body.append(bar);
}
