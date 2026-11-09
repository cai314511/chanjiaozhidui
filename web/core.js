export const state = {user:null,demo:false,publicDemo:false,sessionEpoch:0,health:{},route:'home',industry:'',jobs:[],applications:[],documents:[],profile:null,messages:[],agentContext:{},agentDraft:null};
export const sessionRequests = new Set();
export function resetIdentity(){state.publicDemo=false;state.pendingProfileDraft=null;sessionStorage.removeItem('publicDemo');state.sessionEpoch++;window.dispatchEvent(new Event('identity-reset'));for(const controller of sessionRequests)controller.abort();sessionRequests.clear();state.messages=[];state.agentContext={};state.agentDraft=null;state.profile=null;document.querySelector('#agent-drawer').hidden=true;}
export const actions = {};
export const on = (name, fn) => { actions[name] = fn; };
export const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const num = value => Number(value || 0);
export const fmt = value => Number(value ?? 0).toLocaleString('zh-CN',{maximumFractionDigits:1});
export const money = value => '¥'+fmt(value);
export const roleNames = {employer:'企业端',student:'学生端',university:'高校端'};
Object.defineProperty(roleNames,'admin',{value:'管理员',enumerable:false});
export const statusNames = {eligible:'核验完成',pending:'待核实',excluded:'必要条件未满足'};
let toastTimer;
export function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),5000);}
export async function api(path,options={}){
  const epoch=state.sessionEpoch;
  const headers={...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers};
  if(state.user)headers['X-Workspace-ID']=state.user.id;
  const response=await fetch('/api'+path,{credentials:'same-origin',...options,headers});
  const data=await response.json();
  if(epoch!==state.sessionEpoch)throw new DOMException('账号会话已变化','AbortError');
  if(!response.ok){const detail=data.detail;const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(v=>v.loc.slice(1).join('.')+'：'+v.msg).join('；'):'请求失败';throw new Error(message);}
  return data;
}
export const post=(path,data,options={})=>api(path,{method:'POST',body:JSON.stringify(data),...options});
export const put=(path,data)=>api(path,{method:'PUT',body:JSON.stringify(data)});
export function navigate(route){state.route=route;window.dispatchEvent(new Event('navigate'));}
export function dialog(title,body){const el=document.querySelector('#modal');document.querySelector('#modal-content').innerHTML=`<div class="dialog-head"><h2>${e(title)}</h2><button class="icon-btn" data-action="close-modal" aria-label="关闭">×</button></div>${body}`;if(!el.open)el.showModal();}
export function closeDialog(){document.querySelector('#modal').close();}
export function field(label,name,value='',type='text',extra=''){
  const control=type==='textarea'?`<textarea name="${e(name)}" ${extra}>${e(value)}</textarea>`:`<input name="${e(name)}" type="${e(type)}" value="${e(value)}" ${extra}>`;
  return `<div class="field"><label>${e(label)}${control}</label></div>`;
}
export function select(label,name,values,current=''){return `<div class="field"><label>${e(label)}<select name="${e(name)}">${values.map(v=>`<option value="${e(v)}" ${v===current?'selected':''}>${e(v)}</option>`).join('')}</select></label></div>`;}
export const check=(label,name,checked=false)=>`<label class="check"><input type="checkbox" name="${e(name)}" ${checked?'checked':''}><span>${e(label)}</span></label>`;
export function empty(title,text,button=''){return `<div class="empty"><div class="empty-icon">◇</div><h3>${e(title)}</h3><p>${e(text)}</p>${button}</div>`;}
export function heading(title,subtitle='',action=''){return `<div class="section-head"><div><h2>${e(title)}</h2>${subtitle?`<p>${e(subtitle)}</p>`:''}</div>${action}</div>`;}
export function badge(status){return `<span class="tag ${status==='eligible'?'green':status==='excluded'?'red':'blue'}">${e(statusNames[status]||status)}</span>`;}
export function button(text,action,id='',klass=''){return `<button class="btn ${e(klass)}" data-action="${e(action)}" data-id="${e(id)}">${e(text)}</button>`;}
export const splitList=value=>String(value||'').split(/[，,、\n]/).map(s=>s.trim()).filter(Boolean);
export function values(form){return Object.fromEntries(new FormData(form));}
export function getJob(id){return state.jobs.find(j=>j.id===id);}
export async function refresh(){
  if(!state.user)return;
  if(state.user.role==='admin'){state.jobs=[];state.documents=[];state.applications=[];return;}
  const requests=[api('/jobs'),api('/documents')];
  if(state.user.role!=='university')requests.push(api('/applications'));
  const result=await Promise.all(requests);state.jobs=result[0];state.documents=result[1];state.applications=result[2]||[];
}
export function paintBars(root=document){root.querySelectorAll('[data-bar]').forEach(el=>{el.style.width=Math.max(0,Math.min(100,num(el.dataset.bar)))+'%';});}
export function renderError(err){toast(err.message);}
