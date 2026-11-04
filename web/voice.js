import {state,e,api,post,on,toast,dialog,closeDialog,refresh,navigate,button} from './core.js';
import {openAssistant} from './assistant.js';

let active=null,stream=null,recorder=null,recording=false,chunkTimer,volumeFrame,audioContext,playback,playbackUrl;
let recognitionQueue=Promise.resolve(),chunksPending=0,lastVoice=0,automaticTimer,peer=null,pollTimer,signalCursor=0,stopped=false;
let dictation=null,callStream=null;
const modal=()=>document.querySelector('#modal');
function valid(session){return active===session&&state.sessionEpoch===session.epoch&&modal().open;}
function setStatus(mode,text){const stage=document.querySelector('.droplet-stage');if(stage)stage.dataset.mode=mode;const el=document.querySelector('#voice-status');if(el)el.textContent=text;}
async function checkedFetch(path,body,session){const response=await fetch('/api'+path,{method:'POST',credentials:'same-origin',headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body instanceof FormData?body:JSON.stringify(body)});if(!valid(session))throw new DOMException('访谈已关闭','AbortError');if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'语音请求失败');}return response;}
export function stopVoice(){
 stopDictation();
 if(active?.callId&&active.data.mode==='human'){const session=active;fetch('/api/interviews/'+session.data.id+'/leave',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({call_id:session.callId}),keepalive:true}).catch(()=>{console.info('通话已在本机结束，离开状态未同步');});}
 stopped=true;recording=false;clearTimeout(chunkTimer);clearTimeout(automaticTimer);clearTimeout(pollTimer);cancelAnimationFrame(volumeFrame);
 if(recorder?.state==='recording')recorder.stop();stream?.getTracks().forEach(track=>track.stop());stream=null;
 audioContext?.close();audioContext=null;playback?.pause();if(playbackUrl)URL.revokeObjectURL(playbackUrl);playbackUrl=null;
 peer?.close();peer=null;callStream?.getTracks().forEach(track=>track.stop());callStream=null;active=null;modal().classList.remove('voice-dialog');
}
modal().addEventListener('close',stopVoice);
window.addEventListener('navigate',stopVoice);
window.addEventListener('identity-reset',stopVoice);
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(recording)pauseRecording();stopDictation();}});
window.addEventListener('dictation-stop',stopDictation);
async function localSpeak(text,session){
 if(!valid(session))return;
 playback?.pause();setStatus('speaking','面试官正在回答');
 const response=await checkedFetch('/voice/speak',{text:text.slice(0,1800)},session);
 const blob=await response.blob();if(!valid(session))return;
 if(playbackUrl)URL.revokeObjectURL(playbackUrl);playbackUrl=URL.createObjectURL(blob);playback=new Audio(playbackUrl);
 try{await playback.play();await new Promise(resolve=>{playback.onended=resolve;playback.onerror=resolve;});}
 catch(err){if(valid(session)){setStatus('idle','浏览器尚未允许播报，请点击“重播问题”');return;}}
 if(valid(session)){setStatus('idle','轮到你了，可以开始讲述');if(document.querySelector('#voice-auto')?.checked&&!session.data.completed)await startRecording(session);}
}
function paint(session){
 const list=document.querySelector('#voice-messages');if(!list)return;
 list.innerHTML=session.data.messages.map(m=>`<div class="message ${m.role==='user'?'user':''}"><small>${m.role==='user'?'你的回答':session.data.mode==='human'?'会话记录':'面试官'}</small>${e(m.text)}</div>`).join('');list.scrollTop=list.scrollHeight;
}
async function openSession(data){
 stopVoice();stopped=false;active={data,epoch:state.sessionEpoch};const session=active;
 dialog(data.mode==='profile'?'聊聊你的经历':data.mode==='human'?'企业真人面试':'岗位语音面试',`<div class="interview-layout"><div><div class="droplet-stage" data-mode="idle"><div class="droplet" aria-hidden="true"></div></div><div id="voice-status" class="voice-status" role="status">${data.mode==='human'?'等待双方接通':'已准备好，本地识别与播报'}</div><div class="voice-controls"><button class="mic-button" id="voice-mic" aria-label="开始或停止录音">◉</button><button class="btn" id="voice-replay">重播问题</button>${data.mode==='human'?'<button class="btn" id="human-connect">接通音频</button>':''}</div><p class="voice-state-note">${data.mode==='human'?'真人音频直接连接双方设备':'音频在本机处理 · 转写可修改'}</p><label class="check"><input type="checkbox" id="voice-auto"><span>连续对话：停顿后自动发送本轮转写</span></label>${['ai','profile'].includes(data.mode)?'<label class="check"><input type="checkbox" id="voice-consent"><span>同意将本次核对的转写发给 DeepSeek，用于面试追问</span></label>':''}</div><div><div id="voice-messages" class="voice-messages" aria-live="polite"></div><div class="field"><label>本轮实时转写，可直接修改<textarea id="voice-transcript" class="voice-transcript" placeholder="开始说话，识别结果会出现在这里…" maxlength="6000"></textarea></label></div><div class="inline"><button class="btn primary" id="voice-send">确认并回答</button><button class="btn" id="voice-summary">整理为个人介绍</button></div><p class="hint" id="voice-error"></p></div></div><audio id="remote-audio" autoplay controls hidden></audio>`);
 modal().classList.add('voice-dialog');paint(session);
 document.querySelector('#voice-mic').onclick=()=>recording?pauseRecording():startRecording(session).catch(showError);
 document.querySelector('#voice-send').onclick=()=>sendTurn(session).catch(showError);
 document.querySelector('#voice-replay').onclick=()=>localSpeak(session.data.messages.filter(m=>m.role==='assistant').at(-1)?.text||'你好',session).catch(showError);
 document.querySelector('#voice-summary').onclick=()=>{
  if(state.user.role!=='student'){toast('个人介绍仅对学生开放');return;}
  const transcript=session.data.messages.map(m=>(m.role==='user'?'我：':'访谈：')+m.text).join('\n');
  closeDialog();openAssistant({mode:'profile'});const textarea=document.querySelector('#agent-form [name=message]');if(textarea)textarea.value='请根据以下访谈整理我的经历与职业画像，未知信息保持空白，提供待确认草稿：\n'+transcript;
 };
 if(data.mode==='human')document.querySelector('#human-connect').onclick=()=>connectHuman(session).catch(showError);
 else localSpeak(data.messages.filter(m=>m.role==='assistant').at(-1).text,session).catch(showError);
}
function showError(err){if(err.name==='AbortError')return;const target=document.querySelector('#voice-error');if(target)target.textContent=err.message;setStatus('idle','本轮操作未完成，可以重试');}
async function obtainStream(session){if(stream)return stream;const acquired=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});if(!valid(session)){acquired.getTracks().forEach(track=>track.stop());throw new DOMException('访谈已关闭','AbortError');}stream=acquired;return acquired;}
async function startRecording(session){
 if(!valid(session)||recording||session.gettingStream)return;
 session.gettingStream=true;playback?.pause();try{await obtainStream(session);}finally{session.gettingStream=false;}if(!valid(session))return;
 recording=true;lastVoice=performance.now();document.querySelector('#voice-mic')?.classList.add('recording');setStatus('listening','正在聆听 · 转写会分段显示');
 if(!audioContext){audioContext=new AudioContext();const source=audioContext.createMediaStreamSource(stream),analyser=audioContext.createAnalyser();analyser.fftSize=256;source.connect(analyser);const values=new Uint8Array(analyser.fftSize);
  const tick=()=>{if(!valid(session)||!recording)return;analyser.getByteTimeDomainData(values);const rms=Math.sqrt(values.reduce((sum,v)=>sum+((v-128)/128)**2,0)/values.length);document.querySelector('.droplet')?.style.setProperty('--volume',Math.min(1,rms*7));if(rms>.018)lastVoice=performance.now();volumeFrame=requestAnimationFrame(tick);};tick();
 }
 startChunk(session);
}
function startChunk(session){
 if(!recording||!valid(session))return;
 const segments=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=event=>{if(event.data.size)segments.push(event.data);};
 recorder.onstop=()=>{
  const blob=new Blob(segments,{type:recorder.mimeType});
  if(valid(session)&&blob.size>150&&chunksPending<4){chunksPending++;recognitionQueue=recognitionQueue.then(async()=>{
   if(!valid(session))return;
   const form=new FormData();form.append('file',blob,'speech.webm');const response=await checkedFetch('/voice/transcribe',form,session);const result=await response.json();
   if(valid(session)&&result.text){const input=document.querySelector('#voice-transcript');input.value+=(input.value?'，':'')+result.text;}
  }).catch(showError).finally(()=>{chunksPending--;scheduleAutomatic(session);});}
  else if(valid(session)&&chunksPending>=4){pauseRecording();showError(new Error('本机识别尚未完成，录音已暂停，请等待后继续'));}
  if(recording&&valid(session))startChunk(session);
 };recorder.start();chunkTimer=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop();},4500);
}
function scheduleAutomatic(session){
 clearTimeout(automaticTimer);if(!valid(session)||!document.querySelector('#voice-auto')?.checked||!recording)return;
 automaticTimer=setTimeout(()=>{if(!valid(session))return;if(chunksPending===0&&performance.now()-lastVoice>1600&&document.querySelector('#voice-transcript')?.value.trim())sendTurn(session).catch(showError);else scheduleAutomatic(session);},700);
}
function pauseRecording(){recording=false;clearTimeout(chunkTimer);clearTimeout(automaticTimer);cancelAnimationFrame(volumeFrame);let finished=Promise.resolve();if(recorder?.state==='recording'){finished=new Promise(resolve=>recorder.addEventListener('stop',resolve,{once:true}));recorder.stop();}stream?.getTracks().forEach(t=>t.stop());stream=null;audioContext?.close();audioContext=null;document.querySelector('#voice-mic')?.classList.remove('recording');setStatus('idle','录音已暂停，核对转写后可以提交');return finished;}
async function sendTurn(session){
 if(!valid(session)||session.sending)return;
 const consent=document.querySelector('#voice-consent')?.checked||false;
 if(['ai','profile'].includes(session.data.mode)&&!consent){throw new Error('请确认允许将转写发送给 DeepSeek 面试官');}
 session.sending=true;const btn=document.querySelector('#voice-send'),input=document.querySelector('#voice-transcript');btn.disabled=true;
 try{
  await pauseRecording();if(!valid(session))return;
  await recognitionQueue;if(!valid(session)||!input.isConnected)return;
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
 for(let attempt=0;attempt<3;attempt++){
  if(!valid(session))return;
  const latest=await api('/interviews/'+session.data.id);
  try{return await post('/interviews/'+session.data.id+'/signal',{revision:latest.revision,call_id:session.callId,kind,payload});}
  catch(err){if(!err.message.includes('已更新')||attempt===2)throw err;}
 }
}
async function connectHuman(session){
 if(peer||session.connecting)return;
 session.connecting=true;let acquired;
 try{acquired=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});}finally{session.connecting=false;}
 if(!valid(session)){acquired.getTracks().forEach(track=>track.stop());return;}
 callStream=acquired;
 peer=new RTCPeerConnection({iceServers:[]});callStream.getTracks().forEach(track=>peer.addTrack(track,callStream));
 const pc=peer,pending=[];signalCursor=0;
 const localCandidates=[];let offerSent=false;
 pc.onicecandidate=event=>{if(!event.candidate)return;if(session.data.owner===state.user.id&&!offerSent)localCandidates.push(event.candidate.toJSON());else sendSignal(session,'candidate',event.candidate.toJSON()).catch(showError);};
 pc.ontrack=event=>{const audio=document.querySelector('#remote-audio');audio.hidden=false;audio.srcObject=event.streams[0];audio.play().catch(showError);};
 pc.onconnectionstatechange=()=>{if(valid(session))setStatus(pc.connectionState==='connected'?'speaking':'idle',pc.connectionState==='connected'?'真人音频已接通':pc.connectionState==='failed'?'音频连接失败，请检查网络和浏览器权限':'正在连接企业面试官');};
 const caller=session.data.owner===state.user.id;
 if(caller){session.callId=crypto.randomUUID();const offer=await pc.createOffer();await pc.setLocalDescription(offer);await sendSignal(session,'offer',pc.localDescription.toJSON());offerSent=true;for(const candidate of localCandidates)await sendSignal(session,'candidate',candidate);}
 const poll=async()=>{
  if(!valid(session)||pc.signalingState==='closed')return;
  try{const latest=await api('/interviews/'+session.data.id);session.data=latest;
   if((session.callId&&!latest.call_id)||(caller&&latest.call_id!==session.callId)){setStatus('idle','通话已结束，可以重新接通');pc.close();peer=null;callStream?.getTracks().forEach(track=>track.stop());callStream=null;session.callId=null;return;}
   if(!caller&&session.callId!==latest.call_id){session.callId=latest.call_id;signalCursor=0;pending.length=0;}
   for(const signal of latest.signals.slice(signalCursor)){
    if(signal.actor===state.user.id||signal.call_id!==session.callId)continue;
    if(signal.kind==='leave'){setStatus('idle','对方面试官已离开');pc.close();return;}
    if(signal.kind==='offer'&&!caller){await pc.setRemoteDescription(signal.payload);const answer=await pc.createAnswer();await pc.setLocalDescription(answer);await sendSignal(session,'answer',pc.localDescription.toJSON());}
    else if(signal.kind==='answer'&&caller&&pc.signalingState==='have-local-offer')await pc.setRemoteDescription(signal.payload);
    else if(signal.kind==='candidate')pending.push(signal.payload);
   }
   signalCursor=latest.signals.length;
   if(pc.remoteDescription){while(pending.length)await pc.addIceCandidate(pending.shift());}
   if(valid(session))pollTimer=setTimeout(poll,900);
  }catch(err){showError(err);stopVoice();}
 };await poll();
}

function stopDictation(){if(!dictation)return;const value=dictation;dictation=null;value.cancelled=true;clearTimeout(value.timer);if(value.recorder?.state==='recording')value.recorder.stop();value.stream?.getTracks().forEach(track=>track.stop());restoreDictation(value);}
function restoreDictation(value){if(value.trigger.isConnected){value.trigger.disabled=false;value.trigger.textContent='◉ 语音输入';value.trigger.classList.remove('recording');value.trigger.onclick=event=>{event.stopPropagation();dictateInto(value.textarea,value.trigger).catch(err=>toast(err.message));};}}
export async function dictateInto(textarea,trigger){
 if(recording||peer||dictation){toast('请先停止当前录音');return;}
 const value={epoch:state.sessionEpoch,textarea,trigger,cancelled:false};dictation=value;
 try{value.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});}catch(err){if(dictation===value)dictation=null;throw err;}
 if(dictation!==value||value.epoch!==state.sessionEpoch||!textarea.isConnected){value.stream.getTracks().forEach(track=>track.stop());return;}
 const localRecorder=new MediaRecorder(value.stream),parts=[];value.recorder=localRecorder;trigger.textContent='停止并转写';trigger.classList.add('recording');
 const stop=()=>{clearTimeout(value.timer);if(localRecorder.state==='recording')localRecorder.stop();};trigger.onclick=event=>{event.stopPropagation();stop();};
 localRecorder.ondataavailable=event=>parts.push(event.data);
 localRecorder.onstop=async()=>{
  value.stream.getTracks().forEach(track=>track.stop());if(dictation===value)dictation=null;
  if(value.cancelled||value.epoch!==state.sessionEpoch||!textarea.isConnected){restoreDictation(value);return;}
  trigger.disabled=true;trigger.textContent='本地转写中…';
  try{const data=new FormData();data.append('file',new Blob(parts,{type:localRecorder.mimeType}),'speech.webm');const result=await api('/voice/transcribe',{method:'POST',body:data});if(!value.cancelled&&value.epoch===state.sessionEpoch&&textarea.isConnected)textarea.value+=(textarea.value?'\n':'')+result.text;}catch(err){if(!value.cancelled)toast(err.message);}finally{restoreDictation(value);}
 };localRecorder.start();value.timer=setTimeout(stop,60000);
}
