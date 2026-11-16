import {state,e,fmt,api,post,on,toast,button,navigate,closeDialog,sessionRequests} from './core.js';
import {jobEditor} from './workflows.js';
import {profilePage,bindProfile} from './product.js';
import {dictateInto} from './voice.js';
import {createAgentVisual} from './agent-visual.js';

let panel=null;const composerDrafts=new Map();
export function closeAssistant(){
 const current=panel;panel=null;
 if(current){const input=document.querySelector('#agent-form textarea');if(input&&current.draftKey){composerDrafts.set(current.draftKey,{text:input.value,mode:document.querySelector('#agent-form [name=mode]')?.value});if(composerDrafts.size>20)composerDrafts.delete(composerDrafts.keys().next().value)}current.closed=true;current.controller?.abort();current.visual.dispose();current.observer.disconnect()}
 window.dispatchEvent(new Event('dictation-stop'));
 document.querySelector('#agent-drawer').hidden=true;
}
window.addEventListener('identity-reset',()=>{closeAssistant();composerDrafts.clear()});
window.addEventListener('navigate',closeAssistant);

const names={inspect_authorized_materials:'检索授权资料',calculate_matching:'读取确定性匹配结果',inspect_model_rules:'核对模型与约束规则'};
export function openAssistant(context={}){
 closeAssistant();
 if(state.publicDemo){toast('公开演示模式使用本地计算；外网模型调用请完成报备联调后退出此模式操作');return;}
 if(!state.user){toast('请先登录后使用智能助手');return;}
 state.agentContext=context;
 const drawer=document.querySelector('#agent-drawer');drawer.hidden=false;
 const modes=state.user.role==='employer'?
  [['chat','聊天咨询','讨论招聘流程、岗位职责和人才需求；缺少材料时先给通用建议。'],['job','岗位草稿','结合你的岗位说明或所选资料整理草稿，核对后再填写、发布。'],['assessment','测评建议','依据已授权的题目和回答整理复核建议，最终评价由企业确认。']]:state.user.role==='student'?
  [['chat','聊天咨询','聊职业方向、求职准备和学习问题，不上传材料也可以先提问。'],['profile','个人材料','结合你输入的经历或所选文档整理个人介绍，确认后再填写画像。'],['assessment','面试复盘','结合题目、回答和经历分析准备方向；没有材料时提示如何补充。']]:
  [['chat','聊天咨询','讨论培养目标、课程和资源准备；先给通用建议，再核对本校依据。'],['curriculum','培养建议','依据所选培养资料提出课程与资源调整建议；正式测算请进入培养方案向导。']];
 const draftKey=state.user.id+':'+JSON.stringify(context),saved=composerDrafts.get(draftKey);
 let selected=modes.find(mode=>mode[0]===(context.mode||saved?.mode))||modes[0];
 drawer.innerHTML=`<div class="drawer-head"><h3>✧ 智链产教</h3><button class="icon-btn" data-action="close-agent" aria-label="关闭助手">×</button></div><small>已授权资料检索 · 工具计算 · 人工确认</small><div class="agent-messages" id="agent-messages" role="log" aria-label="对话记录" aria-live="polite"></div><form id="agent-form"><div class="field agent-compose-field"><label>输入问题<textarea name="message" placeholder="输入问题，或用语音聊聊…" required maxlength="10000" rows="2"></textarea></label></div><div class="agent-composer-actions"><button type="submit" class="btn primary">发送并开始分析</button></div><details class="agent-options"><summary>分析任务与资料授权</summary><div class="agent-options-body"><div class="field"><label>分析任务<select name="mode">${modes.map(([k,v])=>`<option value="${k}" ${k===context.mode?'selected':''}>${v}</option>`).join('')}</select></label></div><p class="hint">选择发送给模型的资料</p>${state.documents.length?state.documents.map(d=>`<label class="check"><input type="checkbox" name="doc_${d.id}"><span>${e(d.name)}</span></label>`).join(''):'<p class="hint">可先在资料库上传文档。</p>'}<label class="check"><input type="checkbox" name="send_documents"><span>同意将所选文档正文发送给 DeepSeek</span></label><p class="hint">发送内容包括本次问题${state.user.role==='student'?'、你的个人画像':''}${context.application_id?'、所选投递的画像和测评回答':''}。可先检查正文，避免提交无关个人信息。</p></div></details></form>`;
 const oldMode=drawer.querySelector('[name=mode]'),modeField=document.createElement('input');modeField.type='hidden';modeField.name='mode';modeField.value=selected[0];oldMode.closest('.field').replaceWith(modeField);
 const navigation=document.createElement('section');navigation.className='agent-mode-navigation';navigation.innerHTML=`<div class="agent-mode-tabs" role="tablist" aria-label="助手模式">${modes.map(([key,title])=>`<button type="button" role="tab" data-agent-mode="${key}" aria-selected="${key===selected[0]}" aria-controls="agent-mode-description" tabindex="${key===selected[0]?0:-1}">${title}</button>`).join('')}</div><p id="agent-mode-description" role="tabpanel"></p>`;drawer.querySelector('.drawer-head').after(navigation);
 const visualHost=document.createElement('div');visualHost.className='agent-orb-wrap';visualHost.innerHTML='<div class="agent-orb-stage" data-mode="idle" aria-hidden="true"><div class="agent-orb-fallback" hidden></div></div><p id="agent-orb-status" class="agent-orb-status" role="status" aria-live="polite"></p>';
 navigation.after(visualHost);
 const current={closed:false,visual:createAgentVisual(drawer),controller:null,draftKey};panel=current;
 current.observer=new MutationObserver(()=>{if(drawer.hidden&&panel===current)closeAssistant()});current.observer.observe(drawer,{attributes:true,attributeFilter:['hidden']});
 const speech=document.createElement('button');speech.type='button';speech.className='btn small agent-speech';speech.textContent='◉ 语音输入';
 const hooks={onMode:mode=>{if(panel===current&&!current.controller)current.visual.show(mode)},onVolume:level=>current.visual.volume(level),onError:err=>{if(panel===current)current.visual.show('error',err.name==='NotAllowedError'?'麦克风权限未开启，可继续打字提问':err.message)}};
 speech.onclick=()=>dictateInto(drawer.querySelector('#agent-form [name=message]'),speech,hooks).catch(err=>{hooks.onError(err);toast(err.message)});drawer.querySelector('.agent-composer-actions').prepend(speech);
 const modeButtons=[...navigation.querySelectorAll('[role=tab]')];
 const chooseMode=key=>{
  if(current.controller||speech.disabled||speech.classList.contains('recording')){toast('请先完成当前回复或停止录音，再切换模式');return;}
  selected=modes.find(mode=>mode[0]===key)||modes[0];modeField.value=selected[0];
  modeButtons.forEach(button=>{const active=button.dataset.agentMode===key;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
  navigation.querySelector('#agent-mode-description').textContent=selected[2];
  drawer.querySelector('#agent-form textarea').placeholder=selected[0]==='chat'?'直接说说你的问题，或从目标聊起…':selected[0]==='profile'?'描述你做过的项目、承担的任务和结果…':selected[0]==='job'?'描述岗位职责、能力要求和招聘安排…':selected[0]==='curriculum'?'说明培养目标、现有课程和资源约束…':'描述需要复盘的题目、回答和具体经历…';
  const welcome=drawer.querySelector('.agent-welcome');if(welcome)welcome.innerHTML=`<span>✧</span><strong>${e(selected[1])}</strong><p>${e(selected[2])}</p>`;
 };
 modeButtons.forEach((button,index)=>{button.addEventListener('click',()=>chooseMode(button.dataset.agentMode));button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?modes.length-1:(index+(event.key==='ArrowRight'?1:-1)+modes.length)%modes.length;chooseMode(modes[next][0]);modeButtons[next].focus()});});
 paintMessages();
 if(!state.messages.length)drawer.querySelector('#agent-messages').innerHTML='<div class="agent-welcome"><span>✧</span><strong>从你的问题开始</strong><p>打字或语音都可以。<br>我会结合已授权的资料，陪你一起分析。</p></div>';
 chooseMode(selected[0]);
 if(saved?.text)drawer.querySelector('#agent-form textarea').value=saved.text;
 if(!state.health.agent_configured){const note=document.createElement('p');note.className='agent-service-note';note.textContent='当前服务器尚未配置 DeepSeek，请联系管理员。切换模式不会恢复服务。';visualHost.after(note);}
 drawer.scrollTop=0;
 drawer.querySelector('#agent-form textarea').focus({preventScroll:true});
 const form=drawer.querySelector('#agent-form');
 form.querySelector('[type=submit]').textContent='发送消息';
 form.querySelector('.agent-options summary').textContent='资料授权与引用范围';
 const keyboardHint=document.createElement('small');keyboardHint.className='agent-keyboard-hint';keyboardHint.textContent='Enter 发送 · Shift+Enter 换行';form.querySelector('.agent-composer-actions').after(keyboardHint);
 drawer.querySelector('#agent-form').addEventListener('submit',async event=>{
  event.preventDefault();if(current.controller)return;
  const form=event.currentTarget,text=form.message.value.trim(),mode=form.mode.value;if(!text)return;
  if(speech.classList.contains('recording')||speech.disabled){toast('请先停止录音并核对转写，再提交问题');return;}
  const ids=state.documents.filter(d=>form.elements['doc_'+d.id]?.checked).map(d=>d.id);
  if(ids.length&&!form.send_documents.checked){toast('请先确认发送所选文档正文');return;}
  const epoch=state.sessionEpoch,userId=state.user.id,controller=new AbortController();current.controller=controller;sessionRequests.add(controller);
  const valid=()=>panel===current&&!current.closed&&state.sessionEpoch===epoch&&state.user?.id===userId;
  const btn=form.querySelector('[type=submit]');btn.disabled=true;speech.disabled=true;modeButtons.forEach(button=>button.disabled=true);btn.textContent='正在思考并回复…';current.visual.show('thinking');state.messages.push({role:'user',text});paintMessages();
  try{
   const result=await post('/agent/run',{message:text,mode,document_ids:ids,send_documents:form.send_documents?.checked||false,...Object.fromEntries(Object.entries(state.agentContext).filter(([k])=>k!=='mode'))},{signal:controller.signal});
   if(!valid())return;state.messages.push({role:'assistant',text:result.message,result});state.agentDraft=result.draft;paintMessages();form.message.value='';current.visual.show('idle');
  }catch(err){if(valid()&&err.name!=='AbortError'){state.messages.push({role:'error',text:err.message});paintMessages();current.visual.show('error')}}
  finally{sessionRequests.delete(controller);current.controller=null;if(valid()){btn.disabled=false;speech.disabled=false;modeButtons.forEach(button=>button.disabled=false);btn.textContent='发送消息'}}
 });
}
function paintMessages(){const target=document.querySelector('#agent-messages');if(!target)return;target.innerHTML=state.messages.map((m,index)=>`<div class="message ${m.role==='user'?'user':''}">${e(m.text)}${m.result?`<div class="trace">${m.result.trace.map(t=>`<div>✓ ${e(names[t.tool]||t.tool)}${t.arguments.section?' · '+e({overview:'授权范围',documents:'所选文档',job:'岗位',profile:'个人画像',application:'投递与测评',insights:'高校汇总'}[t.arguments.section]||t.arguments.section):''}</div>`).join('')}</div><small>${e(m.result.model)} · ${fmt(m.result.elapsed)} 秒 · AI结果待确认</small>${m.result.draft?button('检查并填写到表单','apply-draft',String(index),'small'):''}`:''}</div>`).join('');target.scrollTop=target.scrollHeight;}
on('open-agent',()=>openAssistant());on('close-agent',closeAssistant);
on('job-assistant',()=>{closeDialog();openAssistant({mode:'job'});});
on('agent-assessment',el=>{closeDialog();openAssistant({application_id:el.dataset.id,mode:'assessment'});});
on('apply-draft',async el=>{const draft=state.messages[Number(el.dataset.id)]?.result?.draft;if(!draft)return;if(state.user.role==='employer'){jobEditor(draft);}else if(state.user.role==='student'){document.querySelector('#agent-drawer').hidden=true;state.pendingProfileDraft=draft;navigate('profile');toast('已整理为待确认介绍，请检查后保存');}});
