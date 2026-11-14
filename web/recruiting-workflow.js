import {state,api,post,on,e,fmt,button,empty,dialog,closeDialog,toast,refresh,navigate,field} from './core.js';

const invitationLabels={sent:'待学生确认',reschedule_requested:'待对方确认改期',confirmed:'面试已确认',declined:'已拒绝',cancelled:'已取消'};
const offerLabels={sent:'待学生回应',accepted:'学生已接受 · 已预留名额',hired:'企业已确认录用',declined:'学生已拒绝',revoked:'企业已撤销'};
const activeInvitation=i=>!i.withdrawn&&!['declined','cancelled'].includes(i.status);
function invitationCard(i){
 const waiting=i.waiting_for===state.user.id,active=activeInvitation(i);
 return `<article class="panel workflow-record" data-workflow-revision="${e(i.revision)}"><div class="section-head"><h4>${e(i.student_name||'')} · ${e(i.job_title||'岗位面试')}</h4><span class="tag">${invitationLabels[i.status]}</span></div><p>${e(new Date(i.starts_at).toLocaleString('zh-CN',{timeZone:i.timezone}))} · ${e(i.timezone)} · ${i.duration_minutes}分钟</p><p class="space-prose">${e(i.instructions)}</p><div class="inline">${active&&waiting?button('接受安排','invitation-accept',i.id,'small primary')+button('拒绝安排','invitation-decline',i.id,'small'):''}${active?button('申请改期','invitation-reschedule',i.id,'small')+button('取消邀约','invitation-cancel',i.id,'small'):''}${active&&i.status==='confirmed'&&i.interview_id?button('进入双方面试室','join-interview',i.interview_id,'primary'):''}</div></article>`;
}
function offerCard(o){
 const employer=state.user.role==='employer',active=!o.withdrawn;
 return `<article class="panel workflow-record" data-workflow-revision="${e(o.revision)}"><div class="section-head"><h4>${e(o.student_name||'')} · ${e(o.job_title||'正式意向')}</h4><span class="tag">${offerLabels[o.status]}</span></div><p class="space-prose">${e(o.message)}</p><p class="hint">岗位规则版本 v${o.job_version} · 接受意向后预留名额，企业确认后计入录用。</p><div class="inline">${active&&!employer&&o.status==='sent'?button('接受正式意向','offer-accept',o.id,'small primary')+button('拒绝正式意向','offer-decline',o.id,'small'):''}${active&&!employer&&o.status==='accepted'?button('放弃已接受意向','offer-decline',o.id,'small'):''}${active&&employer&&o.status==='accepted'?button('确认录用','offer-confirm',o.id,'small primary'):''}${active&&employer&&['sent','accepted','hired'].includes(o.status)?button('撤销并释放名额','offer-revoke',o.id,'small danger'):''}</div></article>`;
}
export async function workflowPanel(applicationId=''){
 const data=await api('/recruiting/workflow');
 const invitations=data.invitations.filter(i=>!applicationId||i.application_id===applicationId),offers=data.offers.filter(i=>!applicationId||i.application_id===applicationId);
 return `<section class="recruiting-workflow"><div class="section-head"><h3>面试邀约与正式意向</h3>${applicationId&&state.user.role==='employer'?`<div class="inline">${button('发送面试邀约','invite-candidate',applicationId,'small primary')}${button('发出正式意向','offer-candidate',applicationId,'small')}</div>`:''}</div>${state.user.role==='employer'?`<p class="hint">已预留名额 ${offers.filter(o=>o.status==='accepted').length} · 已确认录用 ${offers.filter(o=>o.status==='hired').length}</p>`:''}${invitations.map(invitationCard).join('')}${offers.map(offerCard).join('')}${!invitations.length&&!offers.length?empty('暂无待处理安排','企业发出邀约或正式意向后，双方可以在这里确认并跟进。'):''}</section>`;
}
on('application-workflow',async el=>dialog('招聘进展',await workflowPanel(el.dataset.id)));

function zonedParts(date,zone){
 return Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(date).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
}
function wallTime(date,zone){
 const p=zonedParts(date,zone);return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function offsetAt(date,zone){
 const p=zonedParts(date,zone);return (Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second)-date.getTime())/60000;
}
function timeFields(i={}){
 const d=i.starts_at?new Date(i.starts_at):new Date(Date.now()+86400000),zone=i.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone||'Asia/Shanghai';
 const local=wallTime(d,zone),original=`required data-original-instant="${e(i.starts_at||'')}" data-original-zone="${e(zone)}" data-original-wall="${e(local)}"`;
 return `<div class="grid2">${field('面试开始时间（所选时区）','starts_at',local,'datetime-local',original)}${field('时区','timezone',zone,'text','required')}${field('时长（分钟）','duration_minutes',i.duration_minutes||30,'number','required min="5" max="480"')}</div>${field('面试说明','instructions',i.instructions||'','textarea','maxlength="4000"')}`;
}
function invitationPayload(form){
 const input=form.elements.starts_at,local=input.value,zone=form.elements.timezone.value.trim();
 let startsAt=input.dataset.originalInstant;
 if(!startsAt||zone!==input.dataset.originalZone||local!==input.dataset.originalWall){
  const reference=new Date(local+'Z');
  // 转换前后的偏移都参与校验，只有能还原所选墙上时间的瞬间才有效。
  const offsets=new Set([-36,0,36].map(hours=>offsetAt(new Date(reference.getTime()+hours*3600000),zone)));
  const candidates=[...offsets].filter(offset=>wallTime(new Date(reference.getTime()-offset*60000),zone)===local);
  if(!candidates.length)throw new Error('该时区不存在这个时间（夏令时跳转），请选择其他时间。');
  if(candidates.length>1)throw new Error('该时区存在重复时刻（夏令时回拨），请选择不歧义的时间。');
  const offset=candidates[0],sign=offset>=0?'+':'-',absolute=Math.abs(offset),suffix=sign+String(Math.floor(absolute/60)).padStart(2,'0')+':'+String(absolute%60).padStart(2,'0');
  startsAt=local+':00'+suffix;
 }
 return {starts_at:startsAt,timezone:zone,duration_minutes:Number(form.elements.duration_minutes.value),instructions:form.elements.instructions.value};
}
function bindWorkflowForm(callback){
 const form=document.querySelector('#workflow-form');
 form.addEventListener('submit',async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;try{await callback(form);await refresh();closeDialog();navigate(state.route);toast('招聘安排已更新');}catch(error){form.querySelector('.error-text').textContent=error.message;}finally{submit.disabled=false;}});
}
on('invite-candidate',el=>{dialog('发送站内面试邀约',`<form id="workflow-form">${timeFields()}<p class="hint">学生接受后，双方可以进入同一个面试室。邀约只发送到站内。</p><p class="error-text" role="alert"></p><button class="btn primary" type="submit">发出邀约</button></form>`);bindWorkflowForm(form=>post('/recruiting/applications/'+el.dataset.id+'/invitations',invitationPayload(form)));});
on('invitation-reschedule',async el=>{const data=await api('/recruiting/workflow'),i=data.invitations.find(i=>i.id===el.dataset.id);dialog('申请改期',`<form id="workflow-form">${timeFields(i)}<p class="hint">对方接受新安排后，生成新的面试室。</p><p class="error-text" role="alert"></p><button class="btn primary" type="submit">提交改期安排</button></form>`);bindWorkflowForm(form=>post('/recruiting/invitations/'+i.id+'/respond',{action:'reschedule',proposal:invitationPayload(form),revision:i.revision}));});
on('offer-candidate',el=>{dialog('发出正式录用意向',`<form id="workflow-form">${field('意向说明与条件','message','','textarea','required maxlength="4000"')}<p class="hint">学生接受后系统预留岗位名额。企业随后确认录用；列表阶段标签不代表正式录用。</p><p class="error-text" role="alert"></p><button class="btn primary" type="submit">发出正式意向</button></form>`);bindWorkflowForm(form=>post('/recruiting/applications/'+el.dataset.id+'/offers',{message:form.elements.message.value}));});
for(const [prefix,actions] of [['invitation',['accept','decline','cancel']],['offer',['accept','decline','confirm','revoke']]])for(const action of actions)on(prefix+'-'+action,async el=>{await post('/recruiting/'+(prefix==='offer'?'offers':'invitations')+'/'+el.dataset.id+'/respond',{action,revision:el.closest('[data-workflow-revision]').dataset.workflowRevision});await refresh();dialog('招聘安排已更新',await workflowPanel());});

function candidatePlan(c){return `<article class="workflow-plan-candidate"><strong>${e(c.student_name)} · ${e(c.job_title)}</strong><span class="tag">${c.selected?'建议入选':'未选中'}</span><p class="hint">${e(c.reasons.join('；')||'双方选择且证据核验通过')}</p><p class="hint">技能缺口：${e(c.skill_gaps.map(g=>g.skill+' '+(g.gap===null?'待核实':g.gap+'级')).join('；')||'暂无可核验技能')}</p></article>`;}
function budgetSummary(plan){
 if(plan.budget_scope!=='total')return '<p class="hint">历史计划采用新增预算口径；重新计算将按企业总预算生成新版本。</p>';
 const labels={salary:'月度薪资（元）',training:'培训（元）',mentor:'导师（课时）'};
 return `${plan.status==='overcommitted'?`<p class="error-text" role="alert">既有承诺已超过企业总预算，暂停新增分配。缺额：${Object.entries(plan.budget_shortfall).filter(([,v])=>v>0).map(([k,v])=>e(labels[k])+' '+fmt(v)).join('；')}。请增加预算或处理原意向，系统不会自动撤销录用。</p>`:''}<div class="table-wrap"><table><thead><tr><th>资源</th><th>企业总预算</th><th>既有承诺</th><th>可用于新增</th><th>新增建议</th><th>合计占用</th></tr></thead><tbody>${Object.entries(labels).map(([k,label])=>`<tr><td>${e(label)}</td><td>${fmt(plan.budget[k])}</td><td>${fmt(plan.committed[k])}</td><td>${fmt(plan.remaining_budget[k])}</td><td>${fmt(plan.result.used[k])}</td><td>${fmt(plan.total_used[k])}</td></tr>`).join('')}</tbody></table></div><details><summary>查看已接受意向与已录用承诺（${plan.commitments.length}人）</summary>${plan.commitments.map(c=>`<p>${e(c.student_name)} · ${e(c.job_title)} · ${c.status==='hired'?'已录用':'已接受'} · 原岗位版本 v${c.job_version}：薪资 ${fmt(c.resources.salary)}、培训 ${fmt(c.resources.training)}、导师 ${fmt(c.resources.mentor)}课时</p>`).join('')||'<p>暂无既有承诺</p>'}</details>`;
}
function planCard(plan){return `<section class="panel"><div class="section-head"><h3>招聘计划 v${plan.version}</h3><span class="tag">${plan.stale?'来源已变化 · 请重新计算':'当前来源版本'}</span></div>${budgetSummary(plan)}<p>新增建议入选 ${plan.result.selected.length} 人；新增占用薪资 ${fmt(plan.result.used.salary)}、培训 ${fmt(plan.result.used.training)}、导师 ${fmt(plan.result.used.mentor)}课时。</p><p class="hint">岗位剩余名额：${plan.jobs.map(j=>e(j.title)+' '+j.capacity).join('；')||'暂无开放岗位'}</p>${plan.candidates.map(candidatePlan).join('')||empty('暂无候选人','有效投递后可计算计划。')}<p class="hint">计划仅提供分配建议；录用需要通过正式意向和企业确认。</p></section>`;}
export async function loadPlans(){
 const host=document.querySelector('#allocation-result');if(!host)return;
 const epoch=state.sessionEpoch,plans=await api('/recruiting/plans');if(!host.isConnected||epoch!==state.sessionEpoch)return;
 const form=document.querySelector('#allocation-form');
 if(plans.length)for(const key of ['salary','training','mentor'])if(!form.elements[key].value)form.elements[key].value=plans[0].budget[key];
 host.innerHTML=`${plans.length>1?`<section class="panel"><h3>比较两个计划版本</h3><div class="inline"><label>原版本<select id="plan-left">${plans.map((p,i)=>`<option value="${p.id}" ${i===1?'selected':''}>v${p.version}</option>`).join('')}</select></label><label>新版本<select id="plan-right">${plans.map(p=>`<option value="${p.id}">v${p.version}</option>`).join('')}</select></label>${button('比较版本','compare-plans','','primary')}</div></section><div id="plan-comparison"></div>`:''}${plans.map(planCard).join('')||empty('暂无已保存计划','填写资源上限后计算，计划和候选依据会按版本保存。')}`;
}
export function bindPersistentAllocation(){
 const form=document.querySelector('#allocation-form');if(!form)return;
 form.querySelector('h3').textContent='企业招聘总预算';
 for(const [key,label] of Object.entries({salary:'企业月度薪资总预算（元）',training:'企业培训总预算（元）',mentor:'企业导师课时总上限'}))form.elements[key].closest('label').firstChild.textContent=label;
 form.querySelector('.hint').textContent='先扣除已接受意向与已录用的承诺，再分配剩余预算。承诺按原岗位版本的薪资上限及培训、导师投入保留；撤销后释放，不重复计入同一人。';
 form.querySelector('[type=submit]').textContent='计算并保存新版本';
 form.addEventListener('submit',async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;try{await post('/recruiting/plans',Object.fromEntries(['salary','training','mentor'].map(k=>[k,Number(form.elements[k].value)])));await loadPlans();toast('招聘计划新版本已保存');}catch(error){toast(error.message);}finally{submit.disabled=false;}});
 loadPlans().catch(error=>toast(error.message));
}
on('compare-plans',async()=>{const result=await api('/recruiting/plans/compare?left='+encodeURIComponent(document.querySelector('#plan-left').value)+'&right='+encodeURIComponent(document.querySelector('#plan-right').value));document.querySelector('#plan-comparison').innerHTML=`<section class="panel"><h3>v${result.left.version} → v${result.right.version}</h3><p>${Object.entries(result.budget_changes).map(([k,v])=>({salary:'薪资',training:'培训',mentor:'导师'}[k])+': '+fmt(v.before)+' → '+fmt(v.after)).join('；')||'预算保持一致'}</p><h4>新增入选</h4>${result.added.map(candidatePlan).join('')||'<p class="hint">无</p>'}<h4>移出建议</h4>${result.removed.map(candidatePlan).join('')||'<p class="hint">无</p>'}<details><summary>查看两版全部候选人、岗位、名额与未选原因</summary>${planCard(result.left)}${planCard(result.right)}</details></section>`;});
