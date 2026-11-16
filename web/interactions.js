import {dismissDialog} from './core.js';

export function installInteractions({closeAssistant}){
 let press=null;
 const outside=(element,event)=>{const box=element.getBoundingClientRect();return event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom};
 document.addEventListener('pointerdown',event=>{
  press=null;if(event.button!==0)return;
  const modal=event.target instanceof HTMLDialogElement?event.target:null;
  if(modal?.open&&modal.id!=='exploration-dialog'&&outside(modal,event)){press=modal;return;}
  if(document.querySelector('dialog[open]'))return;
  const drawer=document.querySelector('#agent-drawer');
  if(!drawer.hidden&&!drawer.contains(event.target)&&!event.target.closest('#agent-toggle'))press=drawer;
 });
 document.addEventListener('pointercancel',()=>{press=null});
 document.addEventListener('click',event=>{
  const target=press;press=null;
  if(target&&outside(target,event)){
   if(target.id==='modal')dismissDialog();
   else if(target.id==='agent-drawer')closeAssistant();
   else if(target instanceof HTMLDialogElement)target.close();
  }
  document.querySelectorAll('.agent-options[open]').forEach(details=>{if(!details.contains(event.target))details.open=false});
  const sidebar=document.querySelector('#sidebar.open');
  if(sidebar&&!sidebar.contains(event.target)&&!event.target.closest('[data-action=mobile-menu]'))sidebar.classList.remove('open');
 },true);
 document.querySelector('#modal').addEventListener('cancel',event=>{event.preventDefault();dismissDialog()});
 document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&!event.isComposing&&!document.querySelector('dialog[open]')){
   const options=document.querySelector('.agent-options[open]');if(options){options.open=false;event.preventDefault();return;}
   if(!document.querySelector('#agent-drawer').hidden){event.preventDefault();closeAssistant();return;}
  }
  if(event.defaultPrevented||event.key!=='Enter'||event.shiftKey||event.ctrlKey||event.altKey||event.metaKey||event.isComposing||event.keyCode===229)return;
  if(!matchMedia('(hover: hover) and (pointer: fine)').matches)return;
  const control=event.target;if(!(control instanceof HTMLTextAreaElement))return;
  if(control.id==='voice-transcript'){
   event.preventDefault();if(!event.repeat)document.querySelector('#voice-send:not(:disabled)')?.click();return;
  }
  if(!control.matches('#agent-form textarea,#direct-message-form textarea,[data-enter-send]'))return;
  const form=control.form,submit=form?.querySelector('button[type=submit],input[type=submit],button.primary:not([type])');
  if(!submit)return;event.preventDefault();if(!event.repeat&&!submit.disabled)form.requestSubmit(submit);
 });
}
