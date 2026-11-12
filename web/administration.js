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
