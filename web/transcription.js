// 保持录音容器完整，以累计片段提供滚动预览，结束一段后确认正文。
export class ContinuousTranscriber {
 constructor({onInterim=()=>{},onFinal=()=>{},onError=()=>{},onVolume=()=>{}}={}) {
  Object.assign(this,{onInterim,onFinal,onError,onVolume});this.cancelled=false;this.running=false;
 }
 async start(stream) {
  this.stream=stream;this.running=true;this.context=new AudioContext();await this.context.resume();
  if(this.cancelled||!this.running){this.release();return;}
  this.analyser=this.context.createAnalyser();this.analyser.fftSize=1024;
  this.context.createMediaStreamSource(stream).connect(this.analyser);
  this.values=new Uint8Array(1024);this.begin();this.meter();
 }
 begin() {
  this.parts=[];this.started=performance.now();this.lastSpeech=this.started;this.heard=false;
  this.recorder=new MediaRecorder(this.stream);
  this.recorder.ondataavailable=e=>{if(e.data.size)this.parts.push(e.data)};
  this.recorder.start(200);
  this.timer=setInterval(()=>this.preview(),1400);
 }
 meter() {
  if(!this.running)return;
  this.analyser.getByteTimeDomainData(this.values);
  const rms=Math.sqrt(this.values.reduce((s,v)=>s+((v-128)/128)**2,0)/this.values.length);
  this.onVolume(Math.min(1,rms*9));
  if(rms>.012){this.heard=true;this.lastSpeech=performance.now()}
  const elapsed=performance.now()-this.started;
  if(!this.rotating&&(elapsed>18000||(this.heard&&elapsed>2400&&performance.now()-this.lastSpeech>1000))){
   this.rotating=true;this.rotation=this.finishSegment().catch(e=>{this.cancel();this.onError(e)}).finally(()=>this.rotating=false);
  }
  this.frame=requestAnimationFrame(()=>this.meter());
 }
 async recognize(blob) {
  const form=new FormData();form.append('file',blob,'speech.webm');
  this.controller=new AbortController();
  const response=await fetch('/api/voice/transcribe',{method:'POST',credentials:'same-origin',body:form,signal:this.controller.signal});
  const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'本地转写失败');
  return result.text||'';
 }
 preview() {
  if(this.pending||this.rotating||!this.running||!this.heard||!this.parts.length)return;
  const blob=new Blob(this.parts,{type:this.recorder.mimeType});
  this.pending=this.recognize(blob).then(text=>{if(!this.cancelled)this.onInterim(text)}).catch(e=>{
   if(!this.cancelled){this.onError(e);this.cancel()}
  }).finally(()=>this.pending=null);
 }
 async finishSegment() {
  const segment=this.recorder;
  clearInterval(this.timer);
  if(this.recorder.state==='recording')await new Promise(resolve=>{this.recorder.addEventListener('stop',resolve,{once:true});this.recorder.stop()});
  const blob=new Blob(this.parts,{type:this.recorder.mimeType}),heard=this.heard;
  if(this.running&&this.rotating&&!this.cancelled)this.begin();
  await this.pending;if(this.cancelled)return;
  if(heard&&blob.size){const text=await this.recognize(blob);if(!this.cancelled){this.onInterim('');if(text)this.onFinal(text)}}
  this.completedRecorder=segment;
 }
 async stop() {
  this.running=false;cancelAnimationFrame(this.frame);clearInterval(this.timer);
  // 麦克风已取得但AudioContext仍在初始化时，也必须立即结束捕获。
  if(!this.recorder){this.cancelled=true;this.release();return;}
  const needsFinal=this.rotating;
  const stopped=this.recorder.state==='recording'?new Promise(resolve=>{this.recorder.addEventListener('stop',resolve,{once:true});this.recorder.stop()}):Promise.resolve();
  this.stream?.getTracks().forEach(t=>t.stop());
  try {await stopped;if(needsFinal)await this.rotation;if(!this.cancelled&&this.completedRecorder!==this.recorder)await this.finishSegment()} finally {this.release()}
 }
 release() {this.stream?.getTracks().forEach(t=>t.stop());if(this.context?.state!=='closed')this.context?.close();this.onVolume(0)}
 cancel() {this.cancelled=true;this.running=false;clearInterval(this.timer);cancelAnimationFrame(this.frame);this.controller?.abort();if(this.recorder?.state==='recording')this.recorder.stop();this.release()}
}
