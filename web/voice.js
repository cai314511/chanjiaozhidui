import {state,e,api,post,on,toast,dialog,closeDialog,refresh,navigate,button} from './core.js';
import {openAssistant} from './assistant.js';
import {ContinuousTranscriber} from './transcription.js';
import {arrangeVoice} from './voice-layout.js';

let active=null,stream=null,recording=false,playback,playbackUrl;
let lastVoice=0,automaticTimer,peer=null,pollTimer,signalCursor=0;
let dictation=null,callStream=null;
let liveTranscriber=null,playbackContext=null,playbackFrame;
let playbackGeneration=0,finishPlayback=null;
let waterOrb=null;
let captureEpoch=0;
function cancelPlayback(){playbackGeneration++;playback?.pause();finishPlayback?.();finishPlayback=null;cancelAnimationFrame(playbackFrame);playbackContext?.close();playbackContext=null;waterOrb?.setVolume(0)}
const modal=()=>document.querySelector('#modal');
function valid(session){return active===session&&state.sessionEpoch===session.epoch&&modal().open;}
function setStatus(mode,text){const stage=document.querySelector('.droplet-stage');if(stage)stage.dataset.mode=mode;waterOrb?.setMode(mode);const el=document.querySelector('#voice-status');if(el)el.textContent=text;const mic=document.querySelector('#voice-mic');if(mic){mic.setAttribute('aria-pressed',String(mode==='listening'));mic.setAttribute('aria-label',mode==='listening'?'停止录音':'开始录音')}}
async function checkedFetch(path,body,session){const response=await fetch('/api'+path,{method:'POST',credentials:'same-origin',headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body instanceof FormData?body:JSON.stringify(body)});if(!valid(session))throw new DOMException('访谈已关闭','AbortError');if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'语音请求失败');}return response;}
export function stopVoice(){
 waterOrb?.dispose();waterOrb=null;
 liveTranscriber?.cancel();liveTranscriber=null;cancelPlayback();
 stopDictation();
 if(active?.callId&&active.data.mode==='human'){const session=active;fetch('/api/interviews/'+session.data.id+'/leave',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({call_id:session.callId}),keepalive:true}).catch(()=>{console.info('通话已在本机结束，离开状态未同步');});}
 recording=false;clearTimeout(automaticTimer);clearTimeout(pollTimer);
 stream?.getTracks().forEach(track=>track.stop());stream=null;
 playback?.pause();if(playbackUrl)URL.revokeObjectURL(playbackUrl);playbackUrl=null;
 peer?.close();peer=null;callStream?.getTracks().forEach(track=>track.stop());callStream=null;active=null;modal().classList.remove('voice-dialog');
}
modal().addEventListener('close',stopVoice);
window.addEventListener('navigate',stopVoice);
window.addEventListener('identity-reset',stopVoice);
document.addEventListener('visibilitychange',()=>{if(document.hidden){captureEpoch++;if(recording)pauseRecording();stopDictation();}});
window.addEventListener('dictation-stop',stopDictation);
async function localSpeak(text,session){
 if(!valid(session))return;
 if(recording)await pauseRecording();
 cancelPlayback();const generation=playbackGeneration;setStatus('thinking','正在准备语音');
 const response=await checkedFetch('/voice/speak',{text:text.slice(0,1800)},session);
 const blob=await response.blob();if(!valid(session)||generation!==playbackGeneration)return;
 if(playbackUrl)URL.revokeObjectURL(playbackUrl);playbackUrl=URL.createObjectURL(blob);playback=new Audio(playbackUrl);
 try{
  playbackContext=new AudioContext();await playbackContext.resume();if(generation!==playbackGeneration)return;
  const analyser=playbackContext.createAnalyser();analyser.fftSize=256;
  playbackContext.createMediaElementSource(playback).connect(analyser);analyser.connect(playbackContext.destination);
  const samples=new Uint8Array(256);cancelAnimationFrame(playbackFrame);
  const animate=()=>{if(!valid(session)||playback.paused)return;analyser.getByteTimeDomainData(samples);const level=Math.sqrt(samples.reduce((s,v)=>s+((v-128)/128)**2,0)/samples.length);waterOrb?.setVolume(Math.min(1,level*8));playbackFrame=requestAnimationFrame(animate)};
  const ended=new Promise(resolve=>{finishPlayback=resolve;playback.onended=resolve;playback.onerror=resolve;});
  await playback.play();if(generation!==playbackGeneration)return;setStatus('speaking','正在回答');animate();await ended;
 }
 catch(err){if(generation!==playbackGeneration||err.name==='AbortError')return;if(valid(session)){setStatus('idle','浏览器尚未允许播报，请点击“重播问题”');return;}}
 if(valid(session)&&generation===playbackGeneration){finishPlayback=null;setStatus('idle','轮到你了，可以开始讲述');if(document.querySelector('#voice-auto')?.checked&&!session.data.completed)await startRecording(session);}
}
function paint(session){
 const list=document.querySelector('#voice-messages');if(!list)return;
 list.innerHTML=session.data.messages.map(m=>`<div class="message ${m.role==='user'?'user':''}"><small>${m.role==='user'?'你的回答':session.data.mode==='human'?'会话记录':'面试官'}</small>${e(m.text)}</div>`).join('');list.scrollTop=list.scrollHeight;
 if(session.data.mode==='preset'&&session.data.completed&&state.user.role==='student'&&!document.querySelector('#preset-review')){
  const answers=session.data.messages.filter(m=>m.role==='user');
  const panel=document.createElement('form');panel.id='preset-review';
  panel.innerHTML=`<h3>核对回答并提交企业复核</h3><p class="hint">请逐题核对。提交后将替换本岗位测评回答，原回答与复核保留历史，本次需要企业重新复核。</p>${session.data.questions.map((q,index)=>`<label class="field">${e(q.title)}<textarea data-question="${e(q.id)}" required maxlength="15000">${e(answers.find(m=>m.question_id===q.id)?.text||answers[index]?.text||'')}</textarea></label>`).join('')}<label class="check"><input type="checkbox" required id="preset-confirm"><span>我已核对，确认将这些回答提交给当前岗位企业复核</span></label><button class="btn primary" type="submit">确认提交企业复核</button><p class="hint" id="preset-submit-status" role="status"></p>`;
  list.after(panel);
  panel.onsubmit=async event=>{
   event.preventDefault();if(session.submitting||!panel.reportValidity())return;
   session.submitting=true;const btn=panel.querySelector('[type=submit]');btn.disabled=true;
   try{
    if(!session.data.job_version)throw new Error('此历史会话缺少岗位版本，请重新开始预设面试');
    const values=Object.fromEntries([...panel.querySelectorAll('[data-question]')].map(input=>[input.dataset.question,input.value.trim()]));
    await post('/applications/'+session.data.application_id+'/answers',{job_version:session.data.job_version,answers:values});
    if(!valid(session))return;
    document.querySelector('#preset-submit-status').textContent='已提交企业复核';document.querySelector('#voice-error').textContent='';await refresh();
   }catch(err){if(valid(session))showError(err)}finally{session.submitting=false;if(btn.isConnected)btn.disabled=false;}
  };
 }
}
async function openSession(data){
 stopVoice();active={data,epoch:state.sessionEpoch};const session=active;
 dialog(data.mode==='profile'?'聊聊你的经历':data.mode==='human'?'企业真人面试':'岗位语音面试',`<div class="interview-layout"><div><div class="droplet-stage" data-mode="idle"><div class="droplet" aria-hidden="true"></div></div><div id="voice-status" class="voice-status" role="status">${data.mode==='human'?'等待双方接通':'已准备好，本地识别与播报'}</div><div class="voice-controls"><button class="mic-button" id="voice-mic" aria-label="开始或停止录音">◉</button><button class="btn" id="voice-replay">重播问题</button>${data.mode==='human'?'<button class="btn" id="human-connect">接通音频</button>':''}</div><p class="voice-state-note">${data.mode==='human'?'真人音频直接连接双方设备':'音频在本机处理 · 转写可修改'}</p><label class="check"><input type="checkbox" id="voice-auto"><span>连续对话：停顿后自动发送本轮转写</span></label>${['ai','profile'].includes(data.mode)?'<label class="check"><input type="checkbox" id="voice-consent"><span>同意将本次核对的转写发给 DeepSeek，用于面试追问</span></label>':''}</div><div><div id="voice-messages" class="voice-messages" aria-live="polite"></div><div class="field"><label>本轮实时转写，可直接修改<textarea id="voice-transcript" class="voice-transcript" placeholder="开始说话，识别结果会出现在这里…" maxlength="6000"></textarea></label></div><div class="inline"><button class="btn primary" id="voice-send">确认并回答</button><button class="btn" id="voice-summary">整理为个人介绍</button></div><p class="hint" id="voice-error"></p></div></div><audio id="remote-audio" autoplay controls hidden></audio>`);
 modal().classList.add('voice-dialog');arrangeVoice(modal());paint(session);
 const interactionRoot=modal().querySelector('.interview-layout');
 interactionRoot.addEventListener('pointerdown',()=>session.interacted=true,{once:true});
 interactionRoot.addEventListener('keydown',()=>session.interacted=true,{once:true});
 const preview=document.createElement('p');preview.id='voice-interim';preview.className='transcript-interim';preview.setAttribute('aria-live','polite');document.querySelector('#voice-transcript').closest('.field').append(preview);
 document.querySelector('#voice-mic').onclick=()=>{(recording?pauseRecording():startRecording(session)).catch(showError)};
 document.querySelector('#voice-send').onclick=()=>sendTurn(session).catch(showError);
 document.querySelector('#voice-replay').onclick=()=>localSpeak(session.data.messages.filter(m=>m.role==='assistant').at(-1)?.text||'你好',session).catch(showError);
 document.querySelector('#voice-summary').onclick=()=>{
  if(state.user.role!=='student'){toast('个人介绍仅对学生开放');return;}
  const transcript=session.data.messages.map(m=>(m.role==='user'?'我：':'访谈：')+m.text).join('\n');
  closeDialog();openAssistant({mode:'profile'});const textarea=document.querySelector('#agent-form [name=message]');if(textarea)textarea.value='请根据以下访谈整理我的经历与职业画像，未知信息保持空白，提供待确认草稿：\n'+transcript;
 };
 try{const {WaterOrb}=await import('./water-orb.js');if(!valid(session))return;const stage=document.querySelector('.droplet-stage');waterOrb=new WaterOrb(stage);waterOrb.setMode(stage.dataset.mode||'idle');stage.addEventListener('water-error',event=>showError(new Error(event.detail)),{once:true})}catch(err){if(valid(session))showError(new Error('三维水滴无法启动，请检查浏览器硬件加速。语音与文字功能仍可使用。'))}
 if(!valid(session))return;
 if(data.mode==='human')document.querySelector('#human-connect').onclick=()=>connectHuman(session).catch(showError);
 else if(!session.interacted&&!recording&&!session.gettingStream&&!session.finishing&&!session.sending&&document.querySelector('.droplet-stage').dataset.mode!=='error')localSpeak(data.messages.filter(m=>m.role==='assistant').at(-1).text,session).catch(showError);
}
function showError(err){if(err.name==='AbortError')return;const target=document.querySelector('#voice-error');if(target)target.textContent=err.message;setStatus('error',err.name==='NotAllowedError'?'麦克风权限未开启，请允许访问后重试':'本轮操作未完成，可以重试');}
async function obtainStream(session){if(stream)return stream;const epoch=captureEpoch,acquired=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});if(!valid(session)||document.hidden||epoch!==captureEpoch){acquired.getTracks().forEach(track=>track.stop());throw new DOMException('访谈已关闭或暂停','AbortError');}stream=acquired;return acquired;}
async function startRecording(session){
 if(!valid(session)||document.hidden||recording||session.gettingStream||session.finishing)return;
 session.gettingStream=true;cancelPlayback();try{await obtainStream(session);}finally{session.gettingStream=false;}if(!valid(session))return;
 recording=true;lastVoice=performance.now();document.querySelector('#voice-mic')?.classList.add('recording');setStatus('listening','正在聆听 · 转写会分段显示');
 liveTranscriber=new ContinuousTranscriber({
  onInterim:text=>{if(valid(session))document.querySelector('#voice-interim').textContent=text?'正在识别：'+text:''},
  onFinal:text=>{if(valid(session)){const input=document.querySelector('#voice-transcript');input.value+=(input.value?'\n':'')+text;input.dispatchEvent(new Event('input',{bubbles:true}));scheduleAutomatic(session)}},
  onVolume:level=>{if(valid(session)){waterOrb?.setVolume(level);if(level>.1)lastVoice=performance.now()}},
  onError:err=>{pauseRecording().catch(showError);showError(err)}
 });
 await liveTranscriber.start(stream);
}
function scheduleAutomatic(session){
 clearTimeout(automaticTimer);if(!valid(session)||!document.querySelector('#voice-auto')?.checked||!recording)return;
 automaticTimer=setTimeout(()=>{if(!valid(session))return;if(!liveTranscriber?.pending&&!liveTranscriber?.rotating&&performance.now()-lastVoice>1600&&document.querySelector('#voice-transcript')?.value.trim())sendTurn(session).catch(showError);else scheduleAutomatic(session);},700);
}
async function pauseRecording(){
 const session=active;if(session?.finishing)return session.finishing;
 recording=false;clearTimeout(automaticTimer);const current=liveTranscriber;
 document.querySelector('#voice-mic')?.classList.remove('recording');setStatus('idle','正在确认最后一段转写');
 const finish=current?.stop()||Promise.resolve();if(session)session.finishing=finish;
 try{await finish}finally{if(session)session.finishing=null;if(active===session){liveTranscriber=null;stream=null;setStatus('idle','录音已暂停，核对转写后可以提交')}}
}
async function sendTurn(session){
 if(!valid(session)||session.sending)return;
 const consent=document.querySelector('#voice-consent')?.checked||false;
 if(['ai','profile'].includes(session.data.mode)&&!consent){document.querySelector('.voice-settings').open=true;throw new Error('请确认允许将转写发送给 DeepSeek 面试官');}
 session.sending=true;const btn=document.querySelector('#voice-send'),input=document.querySelector('#voice-transcript');btn.disabled=true;
 try{
  await pauseRecording();if(!valid(session))return;
  if(!valid(session)||!input.isConnected)return;
  const text=input.value.trim();if(!text)throw new Error('请先讲述或输入本轮回答');
  setStatus('thinking','正在整理回答并准备下一问');
  const result=await post('/interviews/'+session.data.id+'/turn',{text,revision:session.data.revision,consent});if(!valid(session))return;session.data=result;input.value='';paint(session);document.querySelector('#voice-error').textContent='';await localSpeak(result.messages.at(-1).text,session);
 }
 finally{session.sending=false;if(btn.isConnected)btn.disabled=false;}
}
on('voice-intro',async()=>{
 if(!state.user){toast('请登录后开始交谈');return;}
 if(state.user.role!=='student'){openAssistant({mode:state.user.role==='employer'?'job':'curriculum'});toast('可以通过助手的本地语音按钮说明目标');return;}
 const data=await post('/interviews',{mode:'profile'});await openSession(data);
});
on('interview',async el=>{
 const applicationId=el.dataset.id;
 if(state.user.role==='employer'){const sessions=await api('/interviews');dialog('面试会话',sessions.filter(s=>s.application_id===applicationId).map(s=>`<div class="document"><div><h4>${s.mode==='human'?'真人面试':s.mode==='preset'?'预设问题':'AI面试'}</h4><small>${e(s.created.slice(0,16))}</small></div>${button('进入会话','join-interview',s.id)}</div>`).join('')||'<p class="hint">等待学生创建面试会话。学生可以在投递记录中选择真人面试。</p>');return;}
 dialog('选择面试方式',`<div class="voice-options">${[['ai','AI 面试官','围绕岗位与经历追问，语音本地处理，转写确认后交给 DeepSeek。'],['preset','企业预设问题','按企业提供的问题回答，可用语音或文字。'],['human','真人面试官','创建会话后等待企业加入，双方直接进行音频交流。']].map(([mode,title,description])=>`<button class="btn" data-action="start-interview" data-id="${mode}" data-application="${e(applicationId)}"><strong>${title}</strong><span>${description}</span></button>`).join('')}</div>`);
});
on('start-interview',async el=>{const data=await post('/interviews',{mode:el.dataset.id,application_id:el.dataset.application});await openSession(data);});
on('join-interview',async el=>openSession(await api('/interviews/'+el.dataset.id)));

async function sendSignal(session,kind,payload){
 const callId=session.callId;
 const send=async()=>{
  if(!valid(session)||session.callId!==callId)throw new DOMException('通话已关闭','AbortError');
  const result=await post('/interviews/'+session.data.id+'/signal',{revision:session.data.revision,call_id:callId,kind,payload});
  if(valid(session)&&session.callId===callId)session.data=result;
  return result;
 };
 const pending=(session.signalQueue||Promise.resolve()).then(send);
 session.signalQueue=pending.catch(()=>{});return pending;
}
async function connectHuman(session){
 if(peer||session.connecting)return;
 session.connecting=true;let acquired;
 try{acquired=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});}finally{session.connecting=false;}
 if(!valid(session)){acquired.getTracks().forEach(track=>track.stop());return;}
 callStream=acquired;
 peer=new RTCPeerConnection({iceServers:[]});callStream.getTracks().forEach(track=>peer.addTrack(track,callStream));
 const pc=peer,pending=[];signalCursor=0;
 const localCandidates=[];let descriptionSent=false;
 const publishCandidates=async()=>{descriptionSent=true;for(const candidate of localCandidates.splice(0))await sendSignal(session,'candidate',candidate);};
 pc.onicecandidate=event=>{if(!event.candidate||!valid(session)||peer!==pc)return;if(!descriptionSent)localCandidates.push(event.candidate.toJSON());else sendSignal(session,'candidate',event.candidate.toJSON()).catch(showError);};
 pc.ontrack=event=>{const audio=document.querySelector('#remote-audio');audio.hidden=false;audio.srcObject=event.streams[0];audio.play().catch(showError);};
 pc.onconnectionstatechange=()=>{if(valid(session)){if(pc.connectionState==='connected')document.querySelector('#voice-error').textContent='';setStatus(pc.connectionState==='connected'?'speaking':'idle',pc.connectionState==='connected'?'真人音频已接通':pc.connectionState==='failed'?'音频连接失败，请检查网络和浏览器权限':'正在连接企业面试官');}};
 const caller=session.data.owner===state.user.id;
 if(caller){session.data=await api('/interviews/'+session.data.id);session.callId=crypto.randomUUID();const offer=await pc.createOffer();await pc.setLocalDescription(offer);await sendSignal(session,'offer',pc.localDescription.toJSON());await publishCandidates();}
 const poll=async()=>{
  if(!valid(session)||pc.signalingState==='closed')return;
  try{const latest=await api('/interviews/'+session.data.id);session.data=latest;
   if((session.callId&&!latest.call_id)||(caller&&latest.call_id!==session.callId)){setStatus('idle','通话已结束，可以重新接通');pc.close();peer=null;callStream?.getTracks().forEach(track=>track.stop());callStream=null;session.callId=null;return;}
   if(!caller&&session.callId!==latest.call_id){session.callId=latest.call_id;signalCursor=0;pending.length=0;}
   for(const signal of latest.signals.slice(signalCursor)){
    if(signal.actor===state.user.id||signal.call_id!==session.callId)continue;
    if(signal.kind==='leave'){setStatus('idle','对方面试官已离开');pc.close();return;}
    if(signal.kind==='offer'&&!caller){await pc.setRemoteDescription(signal.payload);const answer=await pc.createAnswer();await pc.setLocalDescription(answer);await sendSignal(session,'answer',pc.localDescription.toJSON());await publishCandidates();}
    else if(signal.kind==='answer'&&caller&&pc.signalingState==='have-local-offer')await pc.setRemoteDescription(signal.payload);
    else if(signal.kind==='candidate')pending.push(signal.payload);
   }
   signalCursor=latest.signals.length;
   if(pc.remoteDescription){while(pending.length)await pc.addIceCandidate(pending.shift());}
   if(valid(session))pollTimer=setTimeout(poll,900);
  }catch(err){showError(err);stopVoice();}
 };await poll();
}

function stopDictation(){if(!dictation)return;const value=dictation;dictation=null;value.cancelled=true;clearTimeout(value.timer);value.live?.cancel();value.stream?.getTracks().forEach(track=>track.stop());value.preview?.remove();restoreDictation(value);value.hooks.onMode?.('idle');}
function restoreDictation(value){if(value.trigger.isConnected){value.trigger.disabled=false;value.trigger.textContent='◉ 语音输入';value.trigger.classList.remove('recording');value.trigger.onclick=event=>{event.stopPropagation();dictateInto(value.textarea,value.trigger,value.hooks).catch(err=>{value.hooks.onError?.(err);toast(err.message)});};}}
export async function dictateInto(textarea,trigger,hooks={}){
 if(recording||peer||dictation){toast('请先停止当前录音');return;}
 const value={epoch:state.sessionEpoch,textarea,trigger,hooks,cancelled:false};dictation=value;
 trigger.disabled=true;
 try{value.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});}catch(err){if(dictation===value){dictation=null;restoreDictation(value)}throw err;}
 if(dictation!==value||value.epoch!==state.sessionEpoch||!textarea.isConnected){value.stream.getTracks().forEach(track=>track.stop());return;}
 const usable=()=>!value.cancelled&&value.epoch===state.sessionEpoch&&textarea.isConnected;
 value.preview=document.createElement('p');value.preview.className='transcript-interim';value.preview.setAttribute('aria-live','polite');textarea.after(value.preview);
 value.live=new ContinuousTranscriber({onInterim:text=>{if(usable())value.preview.textContent=text?'正在识别：'+text:''},onFinal:text=>{if(usable()){textarea.value+=(textarea.value?'\n':'')+text;textarea.dispatchEvent(new Event('input',{bubbles:true}))}},onVolume:level=>{if(usable())hooks.onVolume?.(level)},onError:err=>{stopDictation();hooks.onError?.(err);toast(err.message)}});
 const stop=async()=>{
  if(value.stopping||value.cancelled)return;value.stopping=true;clearTimeout(value.timer);trigger.disabled=true;trigger.textContent='正在确认转写…';hooks.onMode?.('transcribing');
  let failure;
  try{await value.live.stop()}catch(err){failure=err;toast(err.message)}finally{if(dictation===value)dictation=null;value.preview.remove();restoreDictation(value);if(!value.cancelled){if(failure)hooks.onError?.(failure);else hooks.onMode?.('idle')}}
 };
 trigger.textContent='停止录音';trigger.classList.add('recording');trigger.disabled=false;trigger.onclick=event=>{event.stopPropagation();stop()};
 try{await value.live.start(value.stream);if(!usable()||value.stopping||dictation!==value){value.live.cancel();return}hooks.onMode?.('listening');value.timer=setTimeout(stop,60000)}catch(err){if(dictation===value)stopDictation();throw err}
}
