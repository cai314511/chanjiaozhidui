import {state,api,on,e,button,dialog,toast,actions,heading,empty,navigate} from './core.js';

export async function universityMaterialsPage(){
 const documents=await api('/documents');
 return heading('本校培养资料库','管理课程表、培养方案、教务导出及培养评估依据。')+universityInputHub()+`<section class="panel"><h3>本校已保存资料</h3>${documents.map(d=>`<article class="document"><div><h4>${e(d.name)}</h4><small>${e(d.university_material||'培养参考资料')} · ${e(d.created?.slice(0,10)||'')}</small></div>${button('查看正文','document',d.id,'small')}</article>`).join('')||empty('尚无本校资料','先导入本校课程表或培养方案，建立可追溯的教学依据。')}</section>`;
}

export function universityInputHub(){return `<div class="input-hub">${button('上传本校课程','university-import','courses')}${button('上传培养方案','university-import','program')}${button('导入教务系统课程表','university-import','teaching')}${button('查看本校课程库','university-course-library')}${button('研判需求与培养缺口','route','home')}</div>`;}
on('university-import',el=>{
 const kind=el.dataset.id||'courses',labels={courses:'上传本校课程',program:'上传本校培养方案',teaching:'导入教务系统课程表'};
 dialog(labels[kind],`<form id="university-import-form"><input type="hidden" name="kind" value="${e(kind)}"><div class="field"><label>选择本校资料<input type="file" name="file" accept=".csv,.xlsx,.json,.pdf,.docx,.txt,.md" required></label></div><p>直接上传教务导出的全校 XLSX 课表，自动读取各校区工作表并按课程代码归并教学班。</p><p class="hint">支持“课程 / 课名 / 课程名称”“课程代码 / 课程编号”等常见字段，以及表头前的标题与空行。保留开课院系、校区、学年学期和教学班数量。没有提供的学时、技能标签保持空缺；不同教学班的学分或学时冲突时，按工作表和行号提示。</p><p class="hint">单份最大12MB，XLSX最多30000条课程安排、10000门不同课程。CSV使用UTF-8；JSON可提供courses或program.courses。相同课程代码更新当前课程，其他课程保留。PDF与Word保存为参考正文。</p><p class="error-text" id="university-import-error" role="status"></p><div id="university-import-recognition" aria-live="polite"></div><button class="btn primary" type="submit">识别课程并存入数据库</button></form>`);
 const form=document.querySelector('#university-import-form');
 form.onsubmit=async event=>{event.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;form.querySelector('#university-import-error').textContent='';form.querySelector('#university-import-recognition').innerHTML='';try{const result=await api('/university/materials/import',{method:'POST',body:new FormData(form)});toast(result.message);form.querySelector('#university-import-error').textContent=result.message;form.querySelector('#university-import-error').style.color='var(--green)';const info=result.recognition;if(info)form.querySelector('#university-import-recognition').innerHTML=`<div class="readonly"><strong>识别完成 · ${result.imported_courses} 门课程</strong><p>${info.sheets.length} 个工作表 · ${info.data_rows} 条课程安排 · 合并 ${info.merged_rows} 条重复课程安排</p>${info.sheets.map(s=>`<p>${e(s.name)}：${s.data_rows} 条，表头位于第 ${s.header_row} 行</p>`).join('')}<p>未提供学时 ${info.missing_hours} 门 · 未确认技能 ${info.missing_skills} 门</p>${info.skipped_sheets.map(s=>`<p>${e(s.name)}：${e(s.reason)}，未导入该页</p>`).join('')}</div><div class="inline" style="margin:16px 0">${button('查看已入库课程','university-course-library')}<a class="btn" href="/api/university/courses/export">导出课程 XLSX</a></div>`;if(state.route==='university')navigate('university');}catch(error){form.querySelector('#university-import-error').style.color='var(--red)';form.querySelector('#university-import-error').textContent=error.message;}finally{if(btn.isConnected)btn.disabled=false;}};
});
on('university-course-library',async()=>{
 const data=await api('/university/courses');
 dialog('本校课程库',`<div class="inline"><p class="hint">${data.courses.length} 门已入库课程，仅本校账号可访问。</p><a class="btn small" href="/api/university/courses/export">导出 XLSX</a></div><div class="field"><label>搜索课程、代码、院系或校区<input id="university-course-search" type="search" placeholder="例如：计量经济学 / 课程代码"></label></div><p id="university-course-count" class="hint" role="status"></p><div id="university-course-results"></div><div class="inline"><button type="button" class="btn small" id="university-course-prev">上一页</button><span id="university-course-page" class="hint"></span><button type="button" class="btn small" id="university-course-next">下一页</button></div>`);
 let page=0;
 const modal=document.querySelector('#modal'),search=modal.querySelector('#university-course-search');
 function paint(){const term=search.value.trim().toLocaleLowerCase(),matches=data.courses.filter(c=>[c.name,c.code,...(c.departments||[]),...(c.campuses||[]),...(c.skills||[])].join(' ').toLocaleLowerCase().includes(term));const pages=Math.max(1,Math.ceil(matches.length/40));page=Math.min(page,pages-1);modal.querySelector('#university-course-count').textContent=`找到 ${matches.length} 门课程`;modal.querySelector('#university-course-results').innerHTML=matches.slice(page*40,(page+1)*40).map(c=>`<article class="document"><div style="min-width:0;flex:1"><h4>${e(c.name)}</h4><p class="hint">${e(c.code)} · ${c.credits==null?'学分待补':c.credits+' 学分'} · ${c.hours==null?'学时待补':c.hours+' 学时'}${c.section_count!=null?' · '+c.section_count+' 个教学班':''}</p><p class="hint">${e([...(c.departments||[]),...(c.campuses||[])].join(' · '))}</p><p class="hint">${e(c.skills.join('、')||'尚未确认能力标签')}</p></div>${state.route==='curriculum'?button('作为候选方案','university-course-candidate',c.code,'small'):''}</article>`).join('')||'<p class="hint">暂无匹配课程，可更换关键词或先导入课表。</p>';modal.querySelector('#university-course-page').textContent=`${page+1} / ${pages} 页`;modal.querySelector('#university-course-prev').disabled=page===0;modal.querySelector('#university-course-next').disabled=page===pages-1;}
 search.oninput=()=>{page=0;paint();};modal.querySelector('#university-course-prev').onclick=()=>{page--;paint();};modal.querySelector('#university-course-next').onclick=()=>{page++;paint();};paint();
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
