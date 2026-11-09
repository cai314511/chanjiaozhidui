import {state,api,e,fmt,on,toast,button,heading,empty,field,splitList,dialog} from './core.js';

let assets={documents:[],portfolio:[]};
let currentPage=null;
let previewSequence=0;
let pendingUploads=0;
window.addEventListener('identity-reset',()=>{assets={documents:[],portfolio:[]};currentPage=null;previewSequence++;pendingUploads=0;});

function localURL(value){
 const text=String(value||'');
 return /^\/api\/[A-Za-z0-9/_?=&.%~-]+$/.test(text)?text:'';
}
function websiteURL(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:'';}catch{return '';}}
function avatar(page){const src=localURL(page.avatar_url);return src?`<img class="space-avatar" src="${e(src)}" alt="${e(page.display_name||'学生')}的头像">`:`<span class="space-avatar space-initial" aria-hidden="true">${e((page.display_name||'我').slice(0,1))}</span>`;}
function tags(values){return (values||[]).map(value=>`<span class="tag">${e(value)}</span>`).join('');}
function selected(form,name){return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(input=>input.value);}
function selection(name,items,ids){return items.length?items.map(item=>`<label class="space-material"><input type="checkbox" name="${name}" value="${e(item.id)}" ${(ids||[]).includes(item.id)?'checked':''}><span><strong>${e(item.name)}</strong><small>${name==='document_ids'?'资料正文':e(item.mime||'作品')}</small></span>${button('预览','space-own-material',item.id,'small')}</label>`).join(''):'<p class="hint">上传后可在这里选择。只有勾选并发布的材料会展示在公开主页。</p>';}
function statusHTML(page){return page?.published?`<span class="tag green">已发布</span><span class="hint">公开版本更新于 ${e(String(page.published.published_at||'').slice(0,10))}</span>${button('复制主页链接','space-copy-link',page.published.id,'small')}`:'<span class="tag">尚未发布</span><span class="hint">当前内容仅保存在你的草稿中。</span>';}
function linkFields(links){return [...(links||[]),{title:'',url:''}].map(link=>`<div class="space-link-row">${field('链接名称','link_title',link.title,'text','maxlength="100" placeholder="如：项目网站"')}${field('网站地址','link_url',link.url,'url','maxlength="2000" placeholder="https://"')}</div>`).join('');}

function favoritesHTML(items){return items.length?items.map(item=>`<div class="space-follow"><div><span class="tag">${item.type==='company'?'企业':'赛道'}</span><strong>${e(item.name)}</strong></div>${button('查看',item.type==='company'?'market-company':'explore-track',item.target_id,'small')}${button('取消收藏','space-unfollow',`${item.type}/${item.target_id}`,'small')}</div>`).join(''):empty('还没有收藏','在企业与赛道探索中收藏感兴趣的方向。',button('去发现','route','home'));}
function feedHTML(feed){const jobs=feed.jobs||[];return jobs.length?`<p class="hint">来自已收藏的企业与赛道 · 共 ${fmt(feed.total??jobs.length)} 个站内真实岗位</p>${jobs.map(job=>`<article class="space-feed-item"><div><span class="eyebrow">${e(job.company||'企业岗位')}</span><h4>${e(job.title)}</h4><p class="hint">${e(job.city||'城市未注明')} · ${Array.isArray(job.salary)?`${fmt(job.salary[0])}–${fmt(job.salary[1])} 元/月`:'薪资待沟通'}</p><div class="chips">${tags(job.tracks)}</div></div>${button('查看企业','market-company',job.company_id,'small')}</article>`).join('')}`:empty('还没有新的岗位动态','收藏企业或赛道后，这里展示相应的站内真实岗位。');}

export async function mySpacePage(){
 const [page,documents,portfolio,favorites,feed]=await Promise.all([api('/me/page'),api('/documents'),api('/portfolio'),api('/me/favorites'),api('/me/feed')]);
 assets={documents,portfolio};currentPage=page;
 const draft=page.draft||{};
 return heading('我的主页','把经历、兴趣和作品整理成自己的名片。',button('查看能力画像','route','profile'))+`<div class="space-layout"><aside class="space-sidebar"><section class="panel space-identity"><div id="space-avatar-preview">${avatar(draft)}</div><span class="eyebrow">MY SPACE · 我的名片</span><h3>${e(draft.display_name||state.user?.name||'介绍一下自己')}</h3><p>${e(draft.headline||'写下一句话，让机会了解你。')}</p><label class="btn space-upload">从相册选择头像<input id="space-avatar-upload" type="file" accept="image/jpeg,image/png,image/webp" hidden></label><p class="hint">JPEG、PNG、WEBP；头像上传后仍需发布才会展示给他人。</p><div id="space-public-status" class="space-status">${statusHTML(page)}</div></section><section class="panel"><h3>我关注的方向</h3><div id="space-favorites">${favoritesHTML(favorites)}</div></section></aside><div class="space-main"><form id="my-space-form"><section class="panel space-editor"><div class="section-head"><div><span class="eyebrow">个人介绍</span><h3>让经历有自己的样子</h3></div><span class="tag">草稿</span></div><div class="grid2">${field('展示姓名','display_name',draft.display_name||state.user?.name||'','text','required maxlength="80"')}${field('一句话介绍','headline',draft.headline,'text','maxlength="200"')}</div>${field('关于我','bio',draft.bio,'textarea','maxlength="5000" rows="4" placeholder="介绍你关心的问题、做过的项目或正在探索的方向。"')}<div class="grid2">${field('学校','school',draft.school,'text','maxlength="200"')}${field('专业','major',draft.major,'text','maxlength="200"')}${field('学历 / 在读阶段','education',draft.education,'text','maxlength="200"')}${field('兴趣，逗号分隔','interests',(draft.interests||[]).join('，'),'text','maxlength="1000"')}</div>${field('特长，逗号分隔','strengths',(draft.strengths||[]).join('，'),'text','maxlength="1000"')}${field('学习与经历背景','background',draft.background,'textarea','maxlength="5000" rows="4"')}</section><section class="panel"><h3>个人网站与项目链接</h3><p class="hint">可添加个人网站、项目主页或公开作品链接，访问时会在新窗口打开。</p><div id="space-links">${linkFields(draft.links)}</div>${button('再加一个链接','space-add-link','','small')}</section><section class="panel"><h3>简历与资料</h3><p class="hint">勾选希望公开的资料正文。请先检查其中的联系方式及其他个人信息。</p><div id="space-documents">${selection('document_ids',documents,draft.document_ids)}</div><label class="btn space-upload">上传简历 / 资料<input id="space-document-upload" type="file" accept=".pdf,.docx,.txt,.md,.csv,.xlsx" hidden></label><p class="hint">支持 PDF、DOCX、TXT、MD、CSV、XLSX，最大12MB。展示提取后的正文。</p></section><section class="panel"><h3>作品与演示视频</h3><div id="space-portfolio">${selection('portfolio_ids',portfolio,draft.portfolio_ids)}</div><label class="btn space-upload">上传作品 / 视频<input id="space-portfolio-upload" type="file" accept=".mp4,.webm,.mp3,.wav,.png,.jpg,.jpeg,.txt" hidden></label><p class="hint">视频、音频、图片或 TXT，最大60MB。上传后勾选并发布，才会出现在公开主页。</p></section><section class="panel space-publish"><h3>公开给机会看见</h3><p>点击发布后，主页介绍、头像和勾选的简历、作品会对站内学生、企业和高校三端可见。未勾选的个人资料继续保持私有。</p><div class="space-actions"><button type="submit" class="btn primary">保存草稿</button>${button('保存并预览主页','space-preview')}${button('保存并发布主页','space-publish','','gold-btn')}${button('撤回公开主页','space-withdraw')}</div><p id="space-message" class="hint" aria-live="polite"></p></section></form><section class="panel"><div class="section-head"><div><span class="eyebrow">FOLLOWING · 岗位动态</span><h3>关注的机会，有了新进展</h3></div>${button('探索企业与赛道','route','home','small')}</div><div id="space-feed">${feedHTML(feed)}</div></section></div></div>`;
}

function pageBody(page){
 const links=(page.links||[]).filter(link=>websiteURL(link.url));
 return `<article class="student-page-preview"><header class="space-cover"><div>${avatar(page)}</div><div><span class="eyebrow">学生主页</span><h2>${e(page.display_name||'学生')}</h2><p>${e(page.headline)}</p><div class="chips">${tags([page.school,page.major,page.education].filter(Boolean))}</div></div></header>${page.bio?`<section><h3>关于我</h3><p class="space-prose">${e(page.bio)}</p></section>`:''}${page.background?`<section><h3>学习与经历背景</h3><p class="space-prose">${e(page.background)}</p></section>`:''}<div class="grid2"><section><h3>兴趣</h3><div class="chips">${tags(page.interests)||'<p class="hint">尚未填写</p>'}</div></section><section><h3>特长</h3><div class="chips">${tags(page.strengths)||'<p class="hint">尚未填写</p>'}</div></section></div>${links.length?`<section><h3>个人网站与项目</h3><div class="space-public-links">${links.map(link=>`<a class="btn" href="${e(websiteURL(link.url))}" target="_blank" rel="noopener noreferrer">${e(link.title||'个人网站')} ↗</a>`).join('')}</div></section>`:''}${(page.documents||[]).length?`<section><h3>简历与资料</h3>${page.documents.map(doc=>`<div class="space-public-document"><strong>${e(doc.name)}</strong>${button('查看正文','space-public-document',doc.url,'small')}</div>`).join('')}</section>`:''}${(page.portfolio||[]).length?`<section><h3>作品与视频</h3><div class="space-public-media">${page.portfolio.map(mediaHTML).join('')}</div></section>`:''}</article>`;
}
function mediaHTML(item){
 const url=localURL(item.url);let media='';
 if(url){if(item.mime?.startsWith('video/'))media=`<video controls preload="metadata" src="${e(url)}"></video>`;else if(item.mime?.startsWith('audio/'))media=`<audio controls preload="metadata" src="${e(url)}"></audio>`;else if(item.mime?.startsWith('image/'))media=`<img loading="lazy" src="${e(url)}" alt="${e(item.name)}">`;else media=`<a class="btn small" href="${e(url)}" target="_blank" rel="noopener noreferrer">打开作品 ↗</a>`;}
 return `<article class="space-media-card"><h4>${e(item.name)}</h4>${media||'<p class="hint">作品暂不可访问</p>'}</article>`;
}
export async function publishedStudentsPage(){
 const students=await api('/students');
 if(state.user?.role==='employer'){
  const candidates=await api('/recruiting/candidates'),ids=new Set(candidates.map(c=>c.id));
  return heading('学生主页','查看意向学生的主页、授权简历与作品。')+`<div class="student-directory">${candidates.map(c=>`<article class="panel student-card"><span class="space-avatar space-initial">${e(c.name.slice(0,1))}</span><div><span class="eyebrow">${e(c.school)}</span><h3>${e(c.name)}</h3><p>${e(c.career)}</p><span class="tag">已投递本公司岗位</span></div><div class="inline">${button('主页与简历','candidate-detail',c.id,'primary')}${button(c.favorite?'取消收藏':'收藏人才',c.favorite?'candidate-unstar':'candidate-star',c.id,'small')}${button('联系','contact-person',c.id,'small')}</div></article>`).join('')}${students.filter(s=>!ids.has(s.id)).map(s=>`<article class="panel student-card">${avatar(s)}<div><h3>${e(s.display_name)}</h3><p>${e(s.headline)}</p></div>${button('查看公开主页','student-page',s.id)}</article>`).join('')||empty('等待学生发布或投递','学生提交投递后，授权的主页与简历会出现在这里。')}</div>`;
 }
 return heading('学生主页','从真实经历与作品，认识每个人的兴趣和方向。')+`<div class="student-directory">${students.length?students.map(student=>`<article class="panel student-card">${avatar(student)}<div><span class="eyebrow">${e(student.school||'学生主页')}</span><h3>${e(student.display_name||'学生')}</h3><p>${e(student.headline||student.major||'探索新的方向')}</p><div class="chips">${tags((student.interests||[]).slice(0,4))}</div></div>${button('查看主页','student-page',student.id,'primary')}</article>`).join(''):empty('还没有发布的学生主页','学生保存并发布自己的主页后，会展示在这里。')}</div>`;
}

function payload(form){
 const values=Object.fromEntries(new FormData(form));
 const titles=[...form.querySelectorAll('[name=link_title]')],urls=[...form.querySelectorAll('[name=link_url]')];
 const links=urls.map((input,i)=>({title:titles[i].value.trim(),url:input.value.trim()})).filter(link=>link.url);
 if(links.some(link=>!websiteURL(link.url)))throw new Error('网站地址需为有效的 HTTP 或 HTTPS 链接，且不能含账号密码。');
 links.forEach(link=>{if(!link.title)link.title=new URL(link.url).hostname;});
 return Object.fromEntries(['display_name','headline','bio','school','major','education','background'].map(key=>[key,values[key]||'']).concat([['interests',splitList(values.interests)],['strengths',splitList(values.strengths)],['links',links],['document_ids',selected(form,'document_ids')],['portfolio_ids',selected(form,'portfolio_ids')]]));
}
async function saveDraft(form){
 if(!form.reportValidity())return null;
 const result=await api('/me/page',{method:'PUT',body:JSON.stringify(payload(form))});
 if(!form.isConnected)return null;
 currentPage=result.draft?result:{draft:result,published:currentPage?.published};
 document.querySelector('#space-message').textContent='草稿已保存；公开版本在点击发布后更新。';
 return currentPage;
}
async function withForm(action){
 const form=document.querySelector('#my-space-form');if(!form)return;
 if(form.dataset.busy==='1')return;
 if(pendingUploads){document.querySelector('#space-message').textContent='资料正在上传，请在上传完成后保存或发布。';return;}
 form.dataset.busy='1';
 const epoch=state.sessionEpoch;
 const buttons=[...form.querySelectorAll('button')];buttons.forEach(btn=>{btn.disabled=true;});
 try{await action(form,epoch);}catch(error){if(epoch===state.sessionEpoch&&form.isConnected)document.querySelector('#space-message').textContent=error.message;}finally{if(epoch===state.sessionEpoch&&form.isConnected){form.dataset.busy='0';buttons.forEach(btn=>{btn.disabled=false;});}}
}
function draftSnapshot(page){const d=page.draft||{};return {...d,documents:assets.documents.filter(item=>(d.document_ids||[]).includes(item.id)).map(item=>({...item,url:'/api/documents/'+item.id})),portfolio:assets.portfolio.filter(item=>(d.portfolio_ids||[]).includes(item.id)).map(item=>({...item,url:'/api/portfolio/'+item.id+'/file'}))};}
async function upload(input,path,kind){
 if(!input.files[0])return;
 const epoch=state.sessionEpoch,form=document.querySelector('#my-space-form'),body=new FormData();body.append('file',input.files[0]);input.disabled=true;
 pendingUploads++;
 try{
  const result=await api(path,{method:'POST',body});if(epoch!==state.sessionEpoch||!input.isConnected)return;
  if(kind==='avatar'){
   currentPage.draft.avatar_url=result.avatar_url;document.querySelector('#space-avatar-preview').innerHTML=avatar(currentPage.draft);
  }else{
   const values=selected(form,kind==='documents'?'document_ids':'portfolio_ids');
   const items=await api(kind==='documents'?'/documents':'/portfolio');if(epoch!==state.sessionEpoch||!input.isConnected)return;
   assets[kind]=items;values.push(result.id);
   document.querySelector(kind==='documents'?'#space-documents':'#space-portfolio').innerHTML=selection(kind==='documents'?'document_ids':'portfolio_ids',items,values);
  }
  document.querySelector('#space-message').textContent='上传成功。检查所选材料后保存并发布，才会更新公开主页。';
 }catch(error){if(epoch===state.sessionEpoch&&input.isConnected)toast(error.message);}finally{if(epoch===state.sessionEpoch){pendingUploads=Math.max(0,pendingUploads-1);if(input.isConnected){input.disabled=false;input.value='';}}}
}
export function bindMySpace(){
 const form=document.querySelector('#my-space-form');if(!form||form.dataset.bound)return;form.dataset.bound='1';
 for(const name of ['headline','school','major'])form.elements[name].maxLength=160;
 form.addEventListener('submit',event=>{event.preventDefault();withForm(async()=>{if(await saveDraft(form))toast('主页草稿已保存');});});
 document.querySelector('#space-avatar-upload').addEventListener('change',event=>upload(event.target,'/me/avatar','avatar'));
 document.querySelector('#space-document-upload').addEventListener('change',event=>upload(event.target,'/documents','documents'));
 document.querySelector('#space-portfolio-upload').addEventListener('change',event=>upload(event.target,'/portfolio','portfolio'));
}
on('space-add-link',()=>{document.querySelector('#space-links')?.insertAdjacentHTML('beforeend',linkFields([]));});
on('space-preview',()=>withForm(async form=>{const page=await saveDraft(form);if(page)dialog('主页草稿预览',`<p class="hint">这是已保存的草稿预览，尚未发布的内容仅你可见。</p>${pageBody(draftSnapshot(page))}`);}));
on('space-publish',()=>withForm(async(form,epoch)=>{
 if(!await saveDraft(form))return;
 await api('/me/page/publish',{method:'POST'});if(epoch!==state.sessionEpoch||!form.isConnected)return;
 currentPage=await api('/me/page');if(epoch!==state.sessionEpoch||!form.isConnected)return;
 document.querySelector('#space-public-status').innerHTML=statusHTML(currentPage);document.querySelector('#space-message').textContent='主页已发布，介绍与所选材料现对站内三端可见。';toast('主页已发布');
}));
on('space-withdraw',()=>withForm(async(form,epoch)=>{
 await api('/me/page/publish',{method:'DELETE'});if(epoch!==state.sessionEpoch||!form.isConnected)return;
 currentPage={...currentPage,published:null};document.querySelector('#space-public-status').innerHTML=statusHTML(currentPage);document.querySelector('#space-message').textContent='公开主页已撤回，草稿和个人资料继续保留。';
}));
on('student-page',async el=>{const sequence=++previewSequence,page=await api('/students/'+encodeURIComponent(el.dataset.id));if(sequence!==previewSequence)return;dialog(page.display_name||'学生主页',`<div class="space-public-links">${button('复制主页链接','space-copy-link',page.id,'small')}</div>${pageBody(page)}`);});
on('space-copy-link',async el=>{
 const url=new URL('/',location.origin);url.searchParams.set('student',el.dataset.id);
 try{await navigator.clipboard.writeText(url.href);toast('主页链接已复制，站内用户登录后可查看');}
 catch{dialog('主页链接',`<p class="hint">复制此链接，站内用户登录后可查看。</p><input class="control" aria-label="公开主页链接" value="${e(url.href)}" readonly>`);}
});
on('space-public-document',async el=>{
 const url=localURL(el.dataset.id);if(!url)throw new Error('资料地址无效');
 const sequence=++previewSequence,doc=await api(url.slice(4));if(sequence!==previewSequence)return;
 dialog(doc.name||'资料正文',`<p class="hint">这里展示文档提取后的正文。</p>${(doc.blocks||[]).map(block=>`<section><p class="hint">${e(block.location||block.page||'')}</p><p class="space-prose">${e(block.text)}</p></section>`).join('')||empty('暂无可提取正文','这份资料尚未提取出可展示的文本。')}`);
});
on('space-own-material',async el=>{
 const item=assets.documents.find(doc=>doc.id===el.dataset.id);
 if(item){const sequence=++previewSequence,doc=await api('/documents/'+encodeURIComponent(item.id));if(sequence!==previewSequence)return;dialog(doc.name,`<p class="hint">私有资料预览；发布时仅公开勾选的材料。</p>${(doc.blocks||[]).map(block=>`<p class="space-prose">${e(block.text)}</p>`).join('')||empty('暂无正文','当前文档没有可提取文本。')}`);}
 else{const work=assets.portfolio.find(item=>item.id===el.dataset.id);if(work)dialog(work.name,mediaHTML({...work,url:'/api/portfolio/'+work.id+'/file'}));}
});
on('space-unfollow',async el=>{
 const epoch=state.sessionEpoch,value=el.dataset.id,separator=value.indexOf('/');
 const type=value.slice(0,separator),id=value.slice(separator+1);if(separator<0||!['company','track'].includes(type)||!id)return;
 await api('/me/favorites/'+type+'/'+encodeURIComponent(id),{method:'DELETE'});
 const [favorites,feed]=await Promise.all([api('/me/favorites'),api('/me/feed')]);if(epoch!==state.sessionEpoch||!el.isConnected)return;
 document.querySelector('#space-favorites').innerHTML=favoritesHTML(favorites);document.querySelector('#space-feed').innerHTML=feedHTML(feed);
});
