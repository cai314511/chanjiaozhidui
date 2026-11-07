import {state,e,fmt,api,post,on,toast,button,navigate,closeDialog,sessionRequests} from './core.js';
import {jobEditor} from './workflows.js';
import {profilePage,bindProfile} from './product.js';
import {dictateInto} from './voice.js';
import {createAgentVisual} from './agent-visual.js';

let panel=null;
export function closeAssistant(){
 const current=panel;panel=null;
 if(current){current.closed=true;current.controller?.abort();current.visual.dispose();current.observer.disconnect()}
 window.dispatchEvent(new Event('dictation-stop'));
 document.querySelector('#agent-drawer').hidden=true;
}
window.addEventListener('identity-reset',closeAssistant);
window.addEventListener('navigate',closeAssistant);

const names={inspect_authorized_materials:'检索授权资料',calculate_matching:'读取确定性匹配结果',inspect_model_rules:'核对模型与约束规则'};
export function openAssistant(context={}){
 closeAssistant();
 if(state.publicDemo){toast('公开演示模式使用本地计算；外网模型调用请完成报备联调后退出此模式操作');return;}
 if(!state.user){toast('请先登录后使用智能助手');return;}
 state.agentContext=context;
 const drawer=document.querySelector('#agent-drawer');drawer.hidden=false;
 const modes=state.user.role==='employer'?[['chat','综合分析'],['job','解析JD与岗位目标'],['assessment','辅助分析测评']]:state.user.role==='student'?[['chat','职业与匹配分析'],['profile','解析个人材料']]:[['chat','培养诊断'],['curriculum','培养方案建议']];
 drawer.innerHTML=`<div class="drawer-head"><h3>✧ 智链产教</h3><button class="icon-btn" data-action="close-agent" aria-label="关闭助手">×</button></div><small>已授权资料检索 · 工具计算 · 人工确认</small><div class="agent-messages" id="agent-messages">${state.messages.length?'':'<p class="hint">可以分析岗位、整理能力证据或解释匹配结果。资料由你选择，评分草稿需要确认。</p>'}</div><form id="agent-form"><div class="field"><label>分析任务<select name="mode">${modes.map(([k,v])=>`<option value="${k}" ${k===context.mode?'selected':''}>${v}</option>`).join('')}</select></label></div><details><summary>选择发送给模型的资料</summary>${state.documents.length?state.documents.map(d=>`<label class="check"><input type="checkbox" name="doc_${d.id}"><span>${e(d.name)}</span></label>`).join(''):'<p class="hint">可先在资料库上传文档。</p>'}<label class="check"><input type="checkbox" name="send_documents"><span>同意将所选文档正文发送给 DeepSeek</span></label></details><p class="hint">发送内容包括本次问题${state.user.role==='student'?'、你的个人画像':''}${context.application_id?'、所选投递的画像和测评回答':''}。可先检查资料正文，避免提交无关个人信息。</p><div class="field"><label>输入问题<textarea name="message" placeholder="描述你的分析目标…" required maxlength="10000"></textarea></label></div><button type="submit" class="btn primary wide">发送并开始分析</button></form>`;
 const visualHost=document.createElement('div');visualHost.className='agent-orb-wrap';visualHost.innerHTML='<div class="agent-orb-stage" data-mode="idle" aria-hidden="true"><div class="agent-orb-fallback" hidden></div></div><p id="agent-orb-status" class="agent-orb-status" role="status" aria-live="polite"></p>';
 drawer.querySelector('.agent-messages').before(visualHost);
 const current={closed:false,visual:createAgentVisual(drawer),controller:null};panel=current;
 current.observer=new MutationObserver(()=>{if(drawer.hidden&&panel===current)closeAssistant()});current.observer.observe(drawer,{attributes:true,attributeFilter:['hidden']});
 const speech=document.createElement('button');speech.type='button';speech.className='btn small agent-speech';speech.textContent='◉ 语音输入';
 const hooks={onMode:mode=>{if(panel===current&&!current.controller)current.visual.show(mode)},onVolume:level=>current.visual.volume(level),onError:err=>{if(panel===current)current.visual.show('error',err.name==='NotAllowedError'?'麦克风权限未开启，可继续打字提问':err.message)}};
 speech.onclick=()=>dictateInto(drawer.querySelector('#agent-form [name=message]'),speech,hooks).catch(err=>{hooks.onError(err);toast(err.message)});drawer.querySelector('#agent-form textarea').after(speech);
 paintMessages();
 drawer.scrollTop=0;
 drawer.querySelector('#agent-form').addEventListener('submit',async event=>{
  event.preventDefault();if(current.controller)return;
  const form=event.currentTarget,text=form.message.value.trim(),mode=form.mode.value;if(!text)return;
  if(speech.classList.contains('recording')||speech.disabled){toast('请先停止录音并核对转写，再提交问题');return;}
  const ids=state.documents.filter(d=>form.elements['doc_'+d.id]?.checked).map(d=>d.id);
  if(ids.length&&!form.send_documents.checked){toast('请先确认发送所选文档正文');return;}
  const epoch=state.sessionEpoch,userId=state.user.id,controller=new AbortController();current.controller=controller;sessionRequests.add(controller);
  const valid=()=>panel===current&&!current.closed&&state.sessionEpoch===epoch&&state.user?.id===userId;
  const btn=form.querySelector('[type=submit]');btn.disabled=true;speech.disabled=true;btn.textContent='正在检索资料并分析…';current.visual.show('thinking');state.messages.push({role:'user',text});paintMessages();
  try{
   const result=await post('/agent/run',{message:text,mode,document_ids:ids,send_documents:form.send_documents?.checked||false,...Object.fromEntries(Object.entries(state.agentContext).filter(([k])=>k!=='mode'))},{signal:controller.signal});
   if(!valid())return;state.messages.push({role:'assistant',text:result.message,result});state.agentDraft=result.draft;paintMessages();form.message.value='';current.visual.show('idle');
  }catch(err){if(valid()&&err.name!=='AbortError'){state.messages.push({role:'error',text:err.message});paintMessages();current.visual.show('error')}}
  finally{sessionRequests.delete(controller);current.controller=null;if(valid()){btn.disabled=false;speech.disabled=false;btn.textContent='发送并开始分析'}}
 });
}
function paintMessages(){const target=document.querySelector('#agent-messages');if(!target)return;target.innerHTML=state.messages.map((m,index)=>`<div class="message ${m.role==='user'?'user':''}">${e(m.text)}${m.result?`<div class="trace">${m.result.trace.map(t=>`<div>✓ ${e(names[t.tool]||t.tool)}${t.arguments.section?' · '+e({overview:'授权范围',documents:'所选文档',job:'岗位',profile:'个人画像',application:'投递与测评',insights:'高校汇总'}[t.arguments.section]||t.arguments.section):''}</div>`).join('')}</div><small>${e(m.result.model)} · ${fmt(m.result.elapsed)} 秒 · AI结果待确认</small>${m.result.draft?button('检查并填写到表单','apply-draft',String(index),'small'):''}`:''}</div>`).join('');target.scrollTop=target.scrollHeight;}
on('open-agent',()=>openAssistant());on('close-agent',closeAssistant);
on('job-assistant',()=>{closeDialog();openAssistant({mode:'job'});});
on('agent-assessment',el=>{closeDialog();openAssistant({application_id:el.dataset.id,mode:'assessment'});});
on('apply-draft',async el=>{const draft=state.messages[Number(el.dataset.id)]?.result?.draft;if(!draft)return;if(state.user.role==='employer'){jobEditor(draft);}else if(state.user.role==='student'){document.querySelector('#agent-drawer').hidden=true;state.pendingProfileDraft=draft;navigate('profile');toast('已整理为待确认介绍，请检查后保存');}});
