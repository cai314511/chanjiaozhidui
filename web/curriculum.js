import {state,e,fmt,money,api as serverApi,post as serverPost,on,button,field,heading,empty,num,values,toast,dialog} from './core.js';

function servicePath(path){return state.user.role==='student'?path.replace('/university/','/student/'):path;}
const api=path=>serverApi(servicePath(path));
const post=(path,data)=>serverPost(servicePath(path),data);

function gapRow(skill='',gap='',weight=1){return `<tr class="gap-row"><td><input name="gap-skill" value="${e(skill)}" required aria-label="技能名称"></td><td><input name="gap-value" type="number" min="0" max="5" step="0.1" value="${gap}" required aria-label="能力缺口"></td><td><input name="gap-weight" type="number" min="0" step="0.1" value="${weight}" required aria-label="缺口优先权重"></td><td>${button('移除','remove-row','','small')}</td></tr>`;}
function readGaps(){const gaps={},weights={};document.querySelectorAll('.gap-row').forEach(row=>{const skill=row.querySelector('[name=gap-skill]').value.trim();if(!skill)throw new Error('请先填写技能名称');if(skill in gaps)throw new Error('技能名称不能重复');gaps[skill]=num(row.querySelector('[name=gap-value]').value);weights[skill]=num(row.querySelector('[name=gap-weight]').value);});return {gaps,weights};}
function courseCard(skills){const id=crypto.randomUUID().slice(0,8);return `<article class="course-card" data-course-id="${id}"><div class="inline"><h3>培养方案 ${document.querySelectorAll('.course-card').length+1}</h3><span class="grow"></span>${button('移除方案','remove-course','','small')}</div>${field('课程 / 实践 / 专业方向调整名称','course-name','','text','required')}<div class="grid3">${field('预算投入（元）','course-cost','','number','required min="0"')}${field('新增学分','course-credits','','number','required min="0" step="0.5"')}${field('师资课时','course-teacher_hours','','number','required min="0"')}${field('实验室课时','course-lab_hours','','number','required min="0"')}${field('学生学习课时','course-study_hours','','number','required min="0"')}${field('完成时间（月）','course-months','','number','required min="0" max="120" step="0.5"')}</div><p class="hint">预期能力增益（等级变化，0–5）。这是本次方案测算的输入假设，请填写有课程目标依据的估计。</p><div class="gains-grid">${skills.map(skill=>`<div class="field"><label>${e(skill)}<input type="number" data-gain="${e(skill)}" min="0" max="5" step="0.1" value="0" required></label></div>`).join('')}</div></article>`;}
export async function curriculumPage(){const plans=await api('/university/plans');return heading('资源约束下的培养方案优化','比较课程与实践组合的能力改善，同时检查每项资源上限。',button('使用本校汇总缺口','use-insights'))+`<form id="curriculum-form"><div class="panel"><h3>01 · 明确能力缺口与优先级</h3><p class="hint">可使用本校汇总，也可录入经过审核的培养方案评估。相同技能的多门课程收益按缺口上限计算。</p><div class="table-wrap"><table><thead><tr><th>技能</th><th>缺口等级（0–5）</th><th>优先权重</th><th>操作</th></tr></thead><tbody id="gap-rows">${gapRow()}</tbody></table></div>${button('＋ 添加缺口','add-gap')}</div><div class="panel"><h3>02 · 设置可投入资源</h3><div class="grid3">${field('总预算（元）','limit-cost','','number','required min="0"')}${field('可增加学分上限','limit-credits','','number','required min="0" step="0.5"')}${field('师资总课时上限','limit-teacher_hours','','number','required min="0"')}${field('实验室总课时上限','limit-lab_hours','','number','required min="0"')}${field('学生新增学习课时上限','limit-study_hours','','number','required min="0"')}${field('调整期限（月）','limit-months','','number','required min="0" max="120" step="0.5"')}</div></div><div class="panel"><h3>03 · 建立候选培养方案</h3><p class="hint">先填写能力缺口，再添加方案。修改技能后请重新建立方案，保证能力增益对应当前技能。</p><div id="course-cards"></div>${button('＋ 添加课程或实践方案','add-course')}</div><div class="form-actions"><button type="submit" class="btn primary">计算可行的最优组合</button></div></form><div id="curriculum-result"></div><div class="panel"><h3>历史测算</h3>${plans.length?plans.map(p=>`<div class="document"><div><h4>${e(p.created.slice(0,19))}</h4><small>选中 ${p.result.selected.length} 项 · 加权改善 ${fmt(p.result.benefit)}</small></div>${button('查看测算','plan-detail',p.id,'small')}</div>`).join(''):empty('尚无测算记录','完成计算后，输入假设与结果一并保存。')}</div>`;}
export async function bindCurriculum(){
 const form=document.querySelector('#curriculum-form');if(!form)return;
 if(state.user.role==='student'){
  document.querySelector('.section-head h2').textContent='我的学习方案优化';
  document.querySelector('.section-head p').textContent='在个人预算、学习时间与期限内，比较弥补能力缺口的学习组合。';
  document.querySelector('[data-action="use-insights"]').hidden=true;
  for(const key of ['credits','teacher_hours','lab_hours']){const input=form.querySelector('[name="limit-'+key+'"]');input.value=0;input.closest('.field').hidden=true;}
  const profile=await serverApi('/profile');if(!form.isConnected)return;
  for(const [key,resource] of [['cost','budget'],['study_hours','study_hours'],['months','months']])form.querySelector('[name="limit-'+key+'"]').value=profile.resources?.[resource]??0;
 }
 if(state.demo){
  const plans=await api('/university/plans');if(!form.isConnected)return;
  const saved=plans[0]?.input;
  if(saved){
   document.querySelector('#gap-rows').innerHTML=Object.entries(saved.gaps).map(([skill,gap])=>gapRow(skill,gap,saved.weights[skill])).join('');
   for(const [key,value] of Object.entries(saved.limits))form.querySelector('[name="limit-'+key+'"]').value=value;
   const host=document.querySelector('#course-cards');
   for(const course of saved.courses){
    host.insertAdjacentHTML('beforeend',courseCard(Object.keys(saved.gaps)));
    const card=host.lastElementChild;card.dataset.courseId=course.id;
    card.querySelector('[name=course-name]').value=course.name;
    for(const key of ['cost','credits','teacher_hours','lab_hours','study_hours','months']){
     const input=card.querySelector('[name="course-'+key+'"]');input.value=course[key];
     if(state.user.role==='student'&&['credits','teacher_hours','lab_hours'].includes(key))input.closest('.field').hidden=true;
    }
    card.querySelectorAll('[data-gain]').forEach(input=>input.value=course.gains[input.dataset.gain]);
   }
   document.querySelector('#curriculum-result').innerHTML=resultHtml(plans[0].result,saved.courses);
  }
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();
  try{const {gaps,weights}=readGaps(),d=values(form);const limits=Object.fromEntries(['cost','credits','teacher_hours','lab_hours','study_hours','months'].map(k=>[k,num(d['limit-'+k])]));
   const courses=[...form.querySelectorAll('.course-card')].map(card=>{const c={id:card.dataset.courseId,name:card.querySelector('[name=course-name]').value,gains:{}};for(const k of ['cost','credits','teacher_hours','lab_hours','study_hours','months'])c[k]=num(card.querySelector('[name=course-'+k+']').value);for(const el of card.querySelectorAll('[data-gain]'))c.gains[el.dataset.gain]=num(el.value);if(Object.keys(c.gains).sort().join('|')!==Object.keys(gaps).sort().join('|'))throw new Error('技能列表已改变，请重新建立候选方案');return c;});
   if(!courses.length)throw new Error('请添加至少一个候选方案');const result=await post('/university/optimize',{gaps,weights,courses,limits});document.querySelector('#curriculum-result').innerHTML=resultHtml(result,courses);toast('方案计算完成，输入与结果已保存');
  }catch(err){toast(err.message);}
 });
}
function resultHtml(result,courses){const labels={cost:'预算',credits:'学分',teacher_hours:'师资课时',lab_hours:'实验室课时',study_hours:'学生学习课时'};return `<section class="panel"><h3>可行培养方案组合</h3><p class="hint">${e(result.assumption||'基于录入的情景假设计算')} · 加权能力改善 ${fmt(result.benefit)}</p>${result.selected.length?result.selected.map(id=>`<p class="pre">✓ ${e(courses.find(c=>c.id===id)?.name||id)}</p>`).join(''):empty('当前条件下没有正收益方案','请检查资源上限、期限以及方案的能力增益。')}<div class="table-wrap"><table><thead><tr><th>资源</th><th>使用量</th></tr></thead><tbody>${Object.entries(result.used).map(([k,v])=>`<tr><td>${labels[k]}</td><td>${k==='cost'?money(v):fmt(v)}</td></tr>`).join('')}</tbody></table></div><h4 class="small-title">调整后剩余缺口</h4><div class="chips">${Object.entries(result.remaining).map(([k,v])=>`<span class="tag">${e(k)}：${fmt(v)}</span>`).join('')}</div></section>`;}
on('add-gap',()=>document.querySelector('#gap-rows').insertAdjacentHTML('beforeend',gapRow()));
on('add-course',()=>{const {gaps}=readGaps();if(!Object.keys(gaps).length)throw new Error('请先录入能力缺口');document.querySelector('#course-cards').insertAdjacentHTML('beforeend',courseCard(Object.keys(gaps)));if(state.user.role==='student'){const card=document.querySelector('.course-card:last-child');for(const key of ['credits','teacher_hours','lab_hours']){const input=card.querySelector('[name="course-'+key+'"]');input.value=0;input.closest('.field').hidden=true;}}});
on('remove-course',el=>el.closest('.course-card').remove());
on('use-insights',async()=>{const data=await api('/university/insights');if(data.suppressed||!data.skills?.length){toast('当前没有满足聚合条件的技能数据，请录入已审核的培养缺口');return;}if(document.querySelectorAll('.course-card').length){toast('请先移除已有候选方案，再更新技能列表');return;}document.querySelector('#gap-rows').innerHTML=data.skills.map(s=>gapRow(s.skill,s.gap,1)).join('');});
on('plan-detail',async el=>{const plans=await api('/university/plans');const plan=plans.find(p=>p.id===el.dataset.id);dialog('培养方案测算记录',resultHtml(plan.result,plan.input.courses)+`<h3>原始资源上限</h3>${Object.entries(plan.input.limits).map(([k,v])=>`<p class="hint">${e({cost:'预算',credits:'学分',teacher_hours:'师资课时',lab_hours:'实验室课时',study_hours:'学习课时',months:'期限（月）'}[k])}：${fmt(v)}</p>`).join('')}`);});
