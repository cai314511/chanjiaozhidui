import {e,navigate,on} from './core.js';

let capsule,lastTop=0,pointFrame;
const fine=matchMedia('(hover:hover) and (pointer:fine)'),reduced=matchMedia('(prefers-reduced-motion:reduce)');
export function updateGlass(){
 const nav=document.querySelector('.nav'),active=nav?.querySelector('button.active');if(!nav||!active)return;
 capsule=nav.querySelector('.nav-capsule');
 if(!capsule){capsule=document.createElement('span');capsule.className='nav-capsule';capsule.ariaHidden='true';nav.prepend(capsule);}
 const top=active.offsetTop;capsule.style.height=active.offsetHeight+'px';capsule.style.transform=`translateY(${top}px)`;
 if(!reduced.matches)capsule.animate([{transform:`translateY(${lastTop}px)`},{transform:`translateY(${top}px)`}],{duration:360,easing:'cubic-bezier(.2,.75,.2,1)'});
 lastTop=top;
 document.querySelectorAll('#page-content .panel,#page-content .card,#page-content .metric,#page-content .job-card').forEach(el=>el.classList.add('liquid-card'));
}
document.addEventListener('pointermove',event=>{
 if(!fine.matches||reduced.matches)return;
 const card=event.target.closest('.liquid-card');if(!card)return;cancelAnimationFrame(pointFrame);
 pointFrame=requestAnimationFrame(()=>{const rect=card.getBoundingClientRect();card.style.setProperty('--mx',event.clientX-rect.left+'px');card.style.setProperty('--my',event.clientY-rect.top+'px');card.classList.add('pointer-lit');});
});
document.addEventListener('pointerout',event=>{const card=event.target.closest('.liquid-card');if(card&&!card.contains(event.relatedTarget))card.classList.remove('pointer-lit');});

let selected=0,commands=[];
function filterCommands(query){
 commands=[...document.querySelectorAll('.nav button[data-id]')].map(el=>({id:el.dataset.id,text:el.textContent.trim()})).filter(v=>v.text.toLowerCase().includes(query.toLowerCase()));selected=0;
 document.querySelector('#command-results').innerHTML=commands.length?commands.map((item,index)=>{
  const pos=item.text.toLowerCase().indexOf(query.toLowerCase());
  const label=query?e(item.text.slice(0,pos))+'<mark>'+e(item.text.slice(pos,pos+query.length))+'</mark>'+e(item.text.slice(pos+query.length)):e(item.text);
  return `<button role="option" aria-selected="${index===0}" data-command="${e(item.id)}">${label}<span>↵</span></button>`;
 }).join(''):'<p class="hint">没有找到相关功能</p>';
}
function openCommands(){const modal=document.querySelector('#command-panel');if(modal.open)return;modal.showModal();modal.querySelector('input').value='';filterCommands('');modal.querySelector('input').focus();}
function choose(){if(commands[selected]){document.querySelector('#command-panel').close();navigate(commands[selected].id);}}
export function installGlass(){
 const modal=document.createElement('dialog');modal.id='command-panel';modal.innerHTML='<label class="command-label">搜索工作空间<input type="search" placeholder="想要做什么？" autocomplete="off" aria-controls="command-results"></label><div id="command-results" role="listbox"></div><small>↑ ↓ 选择　↵ 打开　Esc 关闭</small>';document.body.append(modal);
 modal.querySelector('input').addEventListener('input',event=>filterCommands(event.target.value));
 modal.addEventListener('click',event=>{const el=event.target.closest('[data-command]');if(el){modal.close();navigate(el.dataset.command);}});
 modal.addEventListener('keydown',event=>{
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();if(!commands.length)return;selected=(selected+(event.key==='ArrowDown'?1:-1)+commands.length)%commands.length;modal.querySelectorAll('[role=option]').forEach((el,i)=>el.setAttribute('aria-selected',i===selected));modal.querySelectorAll('[role=option]')[selected]?.scrollIntoView({block:'nearest'});}
  if(event.key==='Enter'){event.preventDefault();choose();}
 });
 document.addEventListener('keydown',event=>{if(event.altKey&&event.code==='Space'){event.preventDefault();modal.open?modal.close():openCommands();}});
 on('commands',openCommands);
}
