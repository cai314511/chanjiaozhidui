import {state,api,e,fmt,toast,dialog,sessionRequests} from './core.js';

export function installAgentFiles(form,current,savedIds=[]){
 const epoch=state.sessionEpoch,valid=()=>!current.closed&&epoch===state.sessionEpoch;
 const body=form.querySelector('.agent-options-body');
 const list=document.createElement('div');list.className='agent-document-list';
 body.querySelectorAll('input[name^=doc_]').forEach(input=>list.append(input.closest('label')));body.prepend(list);
 const attached=document.createElement('section');attached.className='agent-attachments';attached.hidden=true;
 const chips=document.createElement('div');chips.className='agent-file-list';
 const consent=form.querySelector('[name=send_documents]').closest('label');consent.classList.add('agent-file-consent');
 attached.append(chips,consent);form.querySelector('.agent-compose-field').before(attached);
 const upload=document.createElement('button');upload.type='button';upload.className='btn small agent-upload';upload.textContent='＋';upload.setAttribute('aria-label','上传文件');upload.title='上传 TXT、MD、CSV、DOCX、PDF、XLSX，单个不超过12MB';
 const input=document.createElement('input');input.type='file';input.multiple=true;input.hidden=true;input.accept='.txt,.md,.csv,.docx,.pdf,.xlsx';
 const status=document.createElement('small');status.className='agent-upload-status';status.setAttribute('role','status');status.hidden=true;
 form.querySelector('.agent-composer-actions').prepend(upload);form.append(input);attached.after(status);
 let busy=false;
 const selected=()=>state.documents.filter(doc=>form.elements['doc_'+doc.id]?.checked);
 const update=()=>{
  const docs=selected();attached.hidden=!docs.length;
  chips.innerHTML=docs.map(doc=>`<div class="agent-file-chip"><span title="${e(doc.name)}">${e(doc.name)}</span><button type="button" data-preview="${e(doc.id)}" aria-label="查看文件正文" title="查看文件正文">▤</button><button type="button" data-remove="${e(doc.id)}" aria-label="移除附件" title="不在本次对话中使用">×</button></div>`).join('');
  if(!docs.length)consent.querySelector('input').checked=false;
 };
 list.addEventListener('change',event=>{if(selected().length>5){event.target.checked=false;toast('一次最多选择5份文件');}consent.querySelector('input').checked=false;update()});
 attached.addEventListener('click',async event=>{
  const remove=event.target.closest('[data-remove]'),preview=event.target.closest('[data-preview]');
  if(remove){form.elements['doc_'+remove.dataset.remove].checked=false;consent.querySelector('input').checked=false;update();return;}
  if(!preview)return;
  try{const doc=await api('/documents/'+encodeURIComponent(preview.dataset.preview));if(!valid())return;dialog('文件正文 · '+doc.name,`<p class="hint">当前仅在服务器提取；确认授权并发送消息后才会传给 DeepSeek。</p><div class="agent-document-preview">${doc.blocks.map(block=>`<p><small>${e(block.location)}</small><br>${e(block.text)}</p>`).join('')}</div>`);}catch(err){if(valid())toast('正文读取失败：'+err.message)}
 });
 upload.onclick=()=>{if(current.controller){toast('请等待当前回复完成');return;}input.click()};
 input.onchange=async()=>{
  if(busy||!input.files.length)return;
  const files=[...input.files];input.value='';
  if(selected().length+files.length>5){toast('一次最多选择5份文件，请移除附件后再上传');return;}
  if(files.some(file=>file.size>12*1024*1024)){toast('单个文件不得超过12MB');return;}
  if(files.some(file=>!(/\.(txt|md|csv|docx|pdf|xlsx)$/i).test(file.name))){toast('支持 TXT、MD、CSV、DOCX、PDF、XLSX');return;}
  busy=true;upload.disabled=true;status.hidden=false;
  const controller=new AbortController();current.uploadController=controller;sessionRequests.add(controller);
  try{
   for(const file of files){
    status.textContent='正在上传并提取：'+file.name;
    const data=new FormData();data.append('file',file);
    const doc=await api('/documents',{method:'POST',body:data,signal:controller.signal});if(!valid())return;
    const {blocks,...summary}=doc;state.documents.push(summary);
    const label=document.createElement('label');label.className='check';label.innerHTML=`<input type="checkbox" name="doc_${e(doc.id)}" checked><span>${e(doc.name)}</span>`;list.append(label);
    consent.querySelector('input').checked=false;update();status.textContent='已提取 '+fmt(doc.characters)+' 字；请核对并确认发送正文。';
   }
  }catch(err){if(valid()&&err.name!=='AbortError'){status.textContent='上传未完成：'+err.message;toast(status.textContent)}}
  finally{busy=false;sessionRequests.delete(controller);if(current.uploadController===controller)current.uploadController=null;if(valid())upload.disabled=false;}
 };
 savedIds.forEach(id=>{if(form.elements['doc_'+id])form.elements['doc_'+id].checked=true});update();
 return {get busy(){return busy},selectedIds:()=>selected().map(doc=>doc.id)};
}
