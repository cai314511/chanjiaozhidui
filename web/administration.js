import {state,api,post,on,e,roleNames,resetIdentity,refresh,navigate,heading,dialog} from './core.js';

export async function administrationPage(){
 const accounts=await api('/admin/accounts');
 return heading('统一管理入口','选择账号进入对应工作空间，无需重复登录。')+
  `<div class="grid3">${['student','university','employer'].map(role=>`<section class="panel"><h3>${roleNames[role]}</h3><p class="hint">${accounts.filter(a=>a.role===role).length} 个工作空间</p>${accounts.filter(a=>a.role===role).map(a=>`<div class="document"><div><h4>${e(a.name)}</h4><small>${e(a.username)}</small></div><button class="btn" data-action="admin-enter" data-id="${e(a.id)}">进入</button></div>`).join('')}</section>`).join('')}</div>`;
}
async function changeIdentity(next){
 resetIdentity();state.user=next;state.industry='';state.selectedWeight=null;
 state.jobs=[];state.applications=[];state.documents=[];document.querySelector('#app').dataset.identity='';
 await refresh();navigate(next.role==='admin'?'admin':next.role==='student'?'profile':next.role==='university'?'university':'jobs');
}
on('admin-enter',async el=>{const next=await post('/admin/workspace',{user_id:el.dataset.id});document.querySelector('#modal').close();await changeIdentity(next)});
on('admin-return',async()=>changeIdentity(await api('/admin/workspace',{method:'DELETE'})));
on('admin-switch',async()=>dialog('切换工作空间',await administrationPage()));

export async function schoolProfilePanel(){
 const data=await api('/university/profile');if(!data)return '';
 const p=data.program;
 return `<section class="panel"><h3>${e(p.name)}</h3><p class="hint">当前招生 ${p.current_seats} 人 · 计划完成率 ${(p.completion_rate*100).toFixed(0)}% · 地区 ${e(p.region)}</p><div class="table-wrap"><table><thead><tr><th>课程</th><th>学分</th><th>学时</th><th>先修课程</th></tr></thead><tbody>${p.courses.map(c=>`<tr><td>${e(c.name)}</td><td>${c.credits}</td><td>${c.hours}</td><td>${c.prerequisites.map(id=>e(p.courses.find(x=>x.id===id)?.name||id)).join('、')||'无'}</td></tr>`).join('')}</tbody></table></div><p>调整预算 ${p.constraints.budget.toLocaleString()} 元 · 师资 ${p.constraints.teacher_hours_max} 课时 · 实验室 ${p.constraints.lab_hours_max} 课时</p><h4>培养方向</h4><div class="chips">${p.directions.map(d=>`<span class="tag">${e(d.name)} · ${d.capacity}人 · 成绩门槛${d.min_grade}</span>`).join('')}</div><p class="hint">${e(p.split_timing)}</p><h4>学生能力汇总</h4><div class="table-wrap"><table><thead><tr><th>技能</th><th>自述等级均值</th><th>人数</th></tr></thead><tbody>${Object.entries(p.skills).map(([skill,v])=>`<tr><td>${e(skill)}</td><td>${v.level}</td><td>${v.sample_count}</td></tr>`).join('')}</tbody></table></div><p class="hint">能力依据为课程及项目自述，统一考核尚未完成。企业招聘数据尚未录入，岗位需求与匹配结果暂缺。</p><h4>候选调整动作</h4>${data.actions.map(a=>`<p>${e(a.reason)} · ${a.cost.toLocaleString()}元</p>`).join('')}<p class="hint">培养方案及配置文件可在资料与证据库查看、下载，企业资料引入后可用于专业调整决策。</p></section>`;
}
