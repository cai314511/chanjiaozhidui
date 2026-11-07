import {state,api,on,e,button,dialog,toast,actions,heading,empty} from './core.js';

export async function universityMaterialsPage(){
 const documents=await api('/documents');
 return heading('本校培养资料库','管理课程表、培养方案、教务导出及培养评估依据。')+universityInputHub()+`<section class="panel"><h3>本校已保存资料</h3>${documents.map(d=>`<article class="document"><div><h4>${e(d.name)}</h4><small>${e(d.university_material||'培养参考资料')} · ${e(d.created?.slice(0,10)||'')}</small></div>${button('查看正文','document',d.id,'small')}</article>`).join('')||empty('尚无本校资料','先导入本校课程表或培养方案，建立可追溯的教学依据。')}</section>`;
}

export function universityInputHub(){return `<div class="input-hub">${button('上传本校课程','university-import','courses')}${button('上传培养方案','university-import','program')}${button('导入教务系统课程表','university-import','teaching')}${button('查看本校课程库','university-course-library')}${button('研判需求与培养缺口','route','home')}</div>`;}
on('university-import',el=>{
 const kind=el.dataset.id||'courses',labels={courses:'上传本校课程',program:'上传本校培养方案',teaching:'导入教务系统课程表'};
 dialog(labels[kind],`<form id="university-import-form"><input type="hidden" name="kind" value="${e(kind)}"><div class="field"><label>选择本校资料<input type="file" name="file" accept=".csv,.xlsx,.json,.pdf,.docx,.txt,.md" required></label></div><p>教务系统请先导出CSV或XLSX，再在这里导入。无需提供教务系统账号密码。</p><p class="hint">课程表识别：课程代码、课程名称、学分、总学时、能力标签（多项用分号分隔）。JSON可提供courses数组或program.courses。缺失学分、学时保持缺失，能力标签由本校确认。PDF与Word作为培养依据存入本校资料库，不自动编造课程映射。</p><p class="hint">单份最大12MB，每批最多2000门。相同课程代码更新当前课程，其他课程保留。</p><p class="error-text" id="university-import-error"></p><button class="btn primary" type="submit">校验并导入本校资料</button></form>`);
 const form=document.querySelector('#university-import-form');
 form.onsubmit=async event=>{event.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;try{const result=await api('/university/materials/import',{method:'POST',body:new FormData(form)});toast(result.message);document.querySelector('#university-import-error').textContent=result.message;}catch(error){document.querySelector('#university-import-error').textContent=error.message;}finally{if(btn.isConnected)btn.disabled=false;}};
});
on('university-course-library',async()=>{
 const data=await api('/university/courses');
 dialog('本校课程库',`<p class="hint">${data.courses.length} 门已导入课程。仅当前高校账号可访问。</p>${data.courses.map(c=>`<article class="document"><div><h4>${e(c.name)}</h4><p class="hint">${e(c.code)} · ${c.credits??'学分待补'} 学分 · ${c.hours??'学时待补'} 学时</p><p>${e(c.skills.join('、')||'尚未确认能力标签')}</p></div>${state.route==='curriculum'?button('作为候选方案','university-course-candidate',c.code,'small'):''}</article>`).join('')||'<p>先导入本校课程表，建立课程与能力标签对应关系。</p>'}`);
});
on('university-course-candidate',async el=>{
 const data=await api('/university/courses'),course=data.courses.find(c=>c.code===el.dataset.id);if(!course)return;
 const before=document.querySelectorAll('.course-card').length;
 actions['add-course']();
 const cards=document.querySelectorAll('.course-card');if(cards.length<=before)return;
 const card=cards[cards.length-1];card.querySelector('[name=course-name]').value=course.name;
 if(course.credits!==null)card.querySelector('[name=course-credits]').value=course.credits;
 card.insertAdjacentHTML('afterbegin',`<p class="hint">课程表原总学时：${course.hours??'未提供'}。授课、学生新增学习、师资及实验室投入需按本次调整分别确认。</p>`);
 document.querySelector('#modal').close();toast('已填入课程名称及学分，请确认本次调整的资源课时与预期能力改善。');
});
on('university-demand-gaps',async()=>{
 const data=await api('/university/intelligence'),available=data.skills.filter(s=>s.gap!==null&&s.gap!==undefined);
 if(!available.length){toast('暂缺可核实的本校能力差距，请先补充本校汇总和岗位目标等级。');return;}
 if(document.querySelectorAll('.course-card').length){toast('请先处理当前候选方案，再更新缺口。');return;}
 document.querySelector('#gap-rows').innerHTML=available.map(s=>`<tr class="gap-row"><td><input name="gap-skill" value="${e(s.name)}" required aria-label="技能名称"></td><td><input name="gap-value" type="number" min="0" max="5" step="0.1" value="${Math.round(s.gap*10)/10}" required aria-label="能力缺口"></td><td><input name="gap-weight" type="number" min="0" step="0.1" value="1" required aria-label="缺口优先权重"></td><td>${button('移除','remove-row','','small')}</td></tr>`).join('');
 toast('已采用当前本校与平台岗位可比较的能力差距。');
});

export function bindUniversityCourses(){
 if(state.user?.role!=='university'||state.route!=='curriculum')return;
 const first=document.querySelector('#curriculum-form .panel');
 if(first&&!first.querySelector('[data-action=university-demand-gaps]'))first.insertAdjacentHTML('beforeend',button('采用需求研判中的本校能力差距','university-demand-gaps'));
 const target=document.querySelector('#course-cards');if(target&&!document.querySelector('[data-action=university-course-library]'))target.insertAdjacentHTML('afterend',button('从本校课程库选择候选方案','university-course-library'));
}
