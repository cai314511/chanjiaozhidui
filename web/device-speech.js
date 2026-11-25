// Linux 服务器无 SAPI 时，使用访问者设备的离线中文语音，不调用云端朗读服务。
function availableVoice(synthesis){
 const voices=synthesis.getVoices().filter(voice=>voice.localService===true&&/^zh(?:[-_]|$)/i.test(voice.lang));
 return voices.find(voice=>/^zh[-_](CN|Hans)/i.test(voice.lang))||voices[0];
}

function waitForVoice(synthesis,signal){
 const current=availableVoice(synthesis);if(current)return Promise.resolve(current);
 return new Promise((resolve,reject)=>{
  const finish=(voice,error)=>{clearTimeout(timer);synthesis.removeEventListener('voiceschanged',changed);signal.removeEventListener('abort',aborted);error?reject(error):resolve(voice)};
  const changed=()=>{const voice=availableVoice(synthesis);if(voice)finish(voice)};
  const aborted=()=>finish(null,new DOMException('播报已取消','AbortError'));
  const timer=setTimeout(()=>finish(null,new Error('此设备没有可用的本地中文语音，请安装系统中文语音包后点击“重播问题”；也可继续录音或文字回答。')),4000);
  synthesis.addEventListener('voiceschanged',changed);signal.addEventListener('abort',aborted,{once:true});
  if(signal.aborted)aborted();else changed();
 });
}

export class DeviceSpeech {
 cancel(){this.controller?.abort();this.controller=null}
 async speak(text,onStart){
  this.cancel();
  const synthesis=window.speechSynthesis;
  if(!synthesis||!window.SpeechSynthesisUtterance)throw new Error('此浏览器不支持设备朗读，请使用支持中文语音的浏览器；也可继续录音或文字回答。');
  const controller=new AbortController();this.controller=controller;const {signal}=controller;
  try{
   const voice=await waitForVoice(synthesis,signal);
   if(signal.aborted)throw new DOMException('播报已取消','AbortError');
   await new Promise((resolve,reject)=>{
    const utterance=new SpeechSynthesisUtterance(text);utterance.voice=voice;utterance.lang=voice.lang;utterance.rate=1;
    let completed=false,timer;
    const finish=error=>{if(completed)return;completed=true;clearTimeout(timer);signal.removeEventListener('abort',aborted);utterance.onstart=utterance.onend=utterance.onerror=null;error?reject(error):resolve()};
    const aborted=()=>{finish(new DOMException('播报已取消','AbortError'));synthesis.cancel()};
    utterance.onstart=()=>{clearTimeout(timer);timer=setTimeout(()=>{finish(new Error('中文播报超时，请点击“重播问题”重试。'));synthesis.cancel()},300000);onStart?.()};
    utterance.onend=()=>finish();
    utterance.onerror=event=>{
     const blocked=event.error==='not-allowed';
     const error=new Error(blocked?'浏览器尚未允许播报，请点击“重播问题”':'设备中文播报失败，请检查系统中文语音包后点击“重播问题”；也可继续录音或文字回答。');
     if(blocked)error.name='NotAllowedError';finish(error);
    };
    signal.addEventListener('abort',aborted,{once:true});
    timer=setTimeout(()=>{finish(new Error('设备未能启动中文播报，请点击“重播问题”重试。'));synthesis.cancel()},10000);
    try{synthesis.speak(utterance)}catch(error){finish(error)}
   });
  }finally{if(this.controller===controller)this.controller=null}
 }
}
