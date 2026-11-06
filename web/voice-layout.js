export function arrangeVoice(modal) {
 const root=modal.querySelector('.interview-layout');
 const stage=root.querySelector('.droplet-stage'),status=root.querySelector('.voice-status');
 const messages=root.querySelector('.voice-messages'),field=root.querySelector('.field');
 const actions=field.nextElementSibling,error=root.querySelector('#voice-error');
 const controls=root.querySelector('.voice-controls'),note=root.querySelector('.voice-state-note');
 const checks=[...root.querySelectorAll('.check')];
 const settings=document.createElement('details');settings.className='voice-settings';
 const summary=document.createElement('summary');summary.textContent='对话设置与授权';settings.append(summary,...checks);
 const footer=document.createElement('footer');footer.className='voice-footer';footer.append(controls,actions,note,settings);
 const conversation=document.createElement('section');conversation.className='voice-conversation';
 const history=document.createElement('button');history.type='button';history.className='voice-history';history.textContent='查看对话记录';history.setAttribute('aria-expanded','false');
 history.onclick=()=>{const expanded=messages.classList.toggle('show-history');history.setAttribute('aria-expanded',String(expanded));history.textContent=expanded?'返回当前对话':'查看对话记录';messages.scrollTop=messages.scrollHeight};
 conversation.append(messages,history,field,error);
 root.replaceChildren(stage,status,conversation,footer);
 modal.querySelector('.dialog-head h2').textContent='智链产教 · 语音空间';
 const microphone=modal.querySelector('#voice-mic');
 microphone.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>';
 microphone.setAttribute('aria-pressed','false');
 const label=field.querySelector('label');label.firstChild.textContent='你的回答';
 field.querySelector('textarea').placeholder='点击麦克风，开始讲述…';
 stage.setAttribute('role','img');stage.setAttribute('aria-label','随语音变化的三维液态水滴');
}
