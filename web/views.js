import {state,e,fmt,money,roleNames,api,navigate,dialog,field,select,check,empty,heading,badge,button,on,post,closeDialog,values,refresh,paintBars,resetIdentity} from './core.js';

export function home(){
 const logged=!!state.user;
 return `<section class="hero"><div class="eyebrow">产业需求 · 能力证据 · 双向选择</div><h1>让每一份潜力<span class="gold">，</span><br>遇见合适的未来<span class="gold">。</span></h1><p>从真实岗位任务出发，连接企业需求与学生成长。<br>以双向匹配形成选择，以能力证据推动高校培养调整。</p><div class="seal">◇　产教智对 · AI 产品与金融科技　◇</div></section>
 <div class="cards"><article class="card glow industry-card"><div class="card-top"><span>01 / AI 产品</span><span>✧</span></div><div class="industry-icon">◈</div><h2>AI 产品</h2><p>围绕用户洞察、产品设计、模型应用与评估，在真实工作场景中发现能力与机会。</p><div class="chips"><span class="tag">产品思维</span><span class="tag">AI 应用</span><span class="tag">场景验证</span></div><div class="card-bottom"><span>探索岗位与能力要求</span><button class="text-button" data-action="industry" data-id="AI产品">进入工作台 ↗</button></div></article>
 <article class="card glow industry-card"><div class="card-top"><span>02 / 金融科技</span><span>✧</span></div><div class="industry-icon">▱</div><h2>金融科技</h2><p>连接金融业务、数据分析与技术应用，在业务任务和合规要求中建立可追溯的能力画像。</p><div class="chips"><span class="tag">金融业务</span><span class="tag">数据分析</span><span class="tag">风险合规</span></div><div class="card-bottom"><span>探索岗位与能力要求</span><button class="text-button" data-action="industry" data-id="金融科技">进入工作台 ↗</button></div></article></div>
 <div class="roles">${[['employer','01','企业工作台','发布岗位与测评，调整能力权重，寻找适合团队的人才。'],['student','02','学生成长空间','呈现能力与规划，参与场景测评，选择适合自己的岗位。'],['university','03','高校决策中心','汇总培养缺口，在资源约束下比较课程与专业调整方案。']].map(([role,n,title,text])=>`<button class="role-card" data-action="enter-role" data-id="${role}"><span>${n}</span><h3>${title}</h3><p>${text}</p></button>`).join('')}</div>
 ${logged?`<div class="metrics"><div class="metric"><span class="metric-label">站内已发布岗位</span><strong>${state.jobs.length}</strong><small>来自企业实际发布</small></div><div class="metric"><span class="metric-label">我的资料</span><strong>${state.documents.length}</strong><small>正文与来源可查看</small></div><div class="metric"><span class="metric-label">${state.user.role==='university'?'核心行业':'当前授权投递'}</span><strong>${state.user.role==='university'?'02':state.applications.length}</strong><small>${state.user.role==='university'?'AI 产品 / 金融科技':'撤回后立即收回访问授权'}</small></div><div class="metric"><span class="metric-label">匹配模型</span><strong>双向</strong><small>权重可调 · 评分可复算</small></div></div>`:''}
 <div class="steps">${[['01','整理真实资料','岗位、经历与培养方案'],['02','建立能力画像','任务、技能与证据'],['03','完成场景测评','专业表现与行为依据'],['04','进行双向选择','条件、偏好与资源'],['05','优化培养方案','课程、实践与专业方向']].map(([n,t,d])=>`<div class="step"><span>${n}</span><strong>${t}</strong><small>${d}</small></div>`).join('')}</div>`;
}

export function jobs(){
 const employer=state.user.role==='employer';
 const visible=state.jobs.filter(j=>(!employer||j.owner===state.user.id)&&(!state.industry||j.industry===state.industry));
 return heading(employer?'岗位与能力画像':'发现适合你的岗位',employer?'定义岗位目标，发布测评，让筛选有明确依据。':'先查看岗位条件与薪资，再结合自己的能力和偏好评估。',employer?button('＋ 发布岗位','new-job','','primary'):'')+
 `<div class="toolbar"><select class="control" id="industry-filter" aria-label="筛选行业"><option value="">全部行业</option>${['AI产品','金融科技'].map(i=>`<option ${state.industry===i?'selected':''}>${i}</option>`).join('')}</select><span class="grow"></span><small>${visible.length} 个岗位</small></div>`+
 (visible.length?`<div class="job-list">${visible.map(j=>`<article class="job-card"><div class="job-head"><div><h3>${e(j.title)}</h3><small>${e(j.company)} · ${e(j.city)} · ${e(j.work_mode)}</small></div><span class="salary">${money(j.salary_min)}–${money(j.salary_max)}<small> / 月</small></span></div><p class="job-description">${e(j.description.slice(0,250))}</p><div class="chips">${j.requirements.map(r=>`<span class="tag ${r.mandatory?'blue':''}">${e(r.skill)}${r.mandatory?' · 必要':''}</span>`).join('')}</div><div class="job-actions"><small>${e(j.industry)} · ${j.capacity} 个名额</small><span class="push"></span>${button('查看详情','job-detail',j.id)}${employer?button('调整招聘偏好','weight-job',j.id,'gold-btn'):state.user.role==='student'?button('查看双向匹配','student-match',j.id,'primary'):''}</div></article>`).join('')}</div>`:empty('等待企业发布岗位','企业填写真实岗位信息后，学生即可查看、测评和投递。',employer?button('发布第一个岗位','new-job','','primary'):''));
}

export function scoreHtml(result){
 const m=result;
 if(m.provisional===null||m.provisional===undefined)return `<div class="empty"><h3>再了解你一些</h3><p>上传简历或完成一次访谈后，再来看看与这个岗位的匹配程度。</p>${button('聊聊我的经历','voice-intro','','primary')}</div>`;
 const color=m.provisional>80?'high':m.provisional<60?'low':'medium';
 return `<div class="match-art ${color}"><strong>${fmt(m.provisional)}</strong><span>分</span></div><p class="match-caption">与你的双向匹配度</p><div class="inline">${badge(m.status)}</div><p class="hint">${e(m.message||'结合当前材料生成，经历核实后可以更新。')}</p>${button('了解下一步准备','open-agent','','small')}`;
}

export function applications(){
 const employer=state.user.role==='employer';
 return heading(employer?'候选人与双向选择':'我的投递与测评',employer?'仅展示学生主动投递并授权的资料；核实证据后再作出选择。':'投递开放所选材料，撤回后企业立即失去访问权限。')+
 (state.applications.length?state.applications.map(a=>`<article class="job-card"><div class="job-head"><div><h3>${e(a.job.title)}</h3><small>${employer?'候选人 '+e(a.owner.slice(0,8))+' · '+e(a.profile.major||'专业待补充'):e(a.job.company)} · ${e(a.job.city)}</small></div>${badge(a.match.status)}</div><div class="score-strip"><div><span>双向匹配度</span><strong>${a.match.provisional===null?'待了解':fmt(a.match.provisional)}</strong></div><div><span>选择状态</span><strong class="subtle">${a.student_chosen&&a.employer_chosen?'双方已选择':a.employer_chosen?'企业已选择':'等待企业选择'}</strong></div></div><div class="job-actions">${button('查看匹配','application-detail',a.id)}${button(employer?'面试会话':'语音面试','interview',a.id,'gold-btn')}${employer?button('测评复核','review',a.id,'primary'):button('参加测评','answer',a.id,'primary')}${button(employer?(a.employer_chosen?'取消选择':'选择该学生'):(a.student_chosen?'取消选择':'选择该岗位'),'choice',a.id)}${!employer?button('撤回投递','withdraw',a.id,'danger'):''}</div></article>`).join('<div class="divider"></div>'):empty('还没有授权投递',employer?'学生投递后，候选资料、场景回答和双向匹配将显示在这里。':'先上传简历或聊聊经历，再从岗位列表查看匹配并投递。',!employer?button('浏览岗位','go-jobs','','primary'):''));
}

export function weightsPage(){
 const jobs=state.jobs.filter(j=>j.owner===state.user.id);
 return heading('能力权重实验室','调整每项能力的重要性，实时比较候选人的分数与排序。')+(jobs.length?`<div class="toolbar"><select class="control" id="weight-select" aria-label="选择岗位">${jobs.map(j=>`<option value="${j.id}">${e(j.title)} · v${j.version}</option>`).join('')}</select></div><div id="weight-workspace"></div>`:empty('先建立岗位画像','权重来自岗位的具体能力要求。',button('发布岗位','new-job','','primary')));
}

export async function documentsPage(){
 const statuses=await api('/data/status');
 return heading('资料与证据库','先在本地提取正文；主动点击智能分析后，所选正文才会发送至 DeepSeek。',button('＋ 上传资料','upload','','primary'))+
 `<div class="grid2"><div class="panel"><h3>我的资料</h3><p class="hint">支持 DOCX、PDF、TXT、CSV、XLSX，单份不超过12MB。成绩单、培养方案、JD、案例、行业资料均可上传。</p>${state.documents.length?state.documents.map(d=>`<div class="document"><div class="document-icon">${e(d.name.split('.').pop().toUpperCase())}</div><div><h4>${e(d.name)}</h4><small>${fmt(d.characters)} 字符 · ${e(d.created.slice(0,10))}</small></div>${button('查看正文','document',d.id,'small')}</div>`).join(''):empty('暂无资料','上传真实材料，建立可追溯的分析依据。')}</div><div class="panel"><h3>桌面产业数据</h3><p class="hint">下载中的文件保持原状。压缩包完成后，可列出内容并选择单个文件导入，避免一次展开全部数据。</p>${statuses.length?statuses.map(d=>`<div class="document"><div class="document-icon">ZIP</div><div><h4>${e(d.name)}</h4><small>${fmt(d.bytes/1024/1024)} MB · ${e(d.status)}</small></div>${d.readable?button('查看内容','archive',d.name,'small'):'<span class="tag">下载中</span>'}</div>`).join(''):'<p class="hint">桌面暂未发现相关压缩包。</p>'}</div></div>`;
}

export function modelPage(){return heading('评分与决策依据','每次匹配返回原始权重、归一化权重、证据状态与版本，支持复算。')+`<div class="grid2"><article class="panel"><h3>企业如何评价能力</h3><p class="hint">每项能力目标为1–5级，权重由企业设置。超额能力不会补偿其他能力的缺口。</p><div class="model-formula">aᵢ = wᵢ / Σwᵢ<br>uᵢ = min(1, sᵢ / rᵢ)<br>E = 100 × Σaᵢuᵢ</div><p class="hint">自述得到暂定分。已复核证据形成可确认贡献；未核实能力给出上下界与覆盖率。单项权重为零时不计分，必要条件继续生效。</p></article><article class="panel"><h3>学生如何选择岗位</h3><p class="hint">薪资、城市、行业、工作方式与成长目标分别计算适合程度，学生可以自行调整偏好权重。</p><div class="model-formula">S = 100 × Σbⱼvⱼ<br>B = 2ES / (E + S)</div><p class="hint">双向分采用调和平均。双方均为零时结果为零。必要条件独立检查，未满足条件的组合不进入正式分配。</p></article><article class="panel"><h3>行为表现如何获得证据</h3><p class="hint">责任感、好奇心、协作能力等维度使用公开评分标准的场景题或结构化访谈。AI给出证据与评分草稿，企业必须引用已作答题目完成复核。语音文本经学生确认后提交。</p></article><article class="panel"><h3>资源如何影响培养方案</h3><p class="hint">整数规划同时检查预算、学分、师资、实验室、学生学习时间与期限。收益以能力缺口为上限，同一缺口不会因多门课程重复覆盖而无限增加。课程增益由使用者明确录入，属于情景假设。</p></article></div><p class="hint">模型版本 matching-1 · 等级标准：1了解概念，2指导下完成操作，3独立完成常规任务，4解决复杂问题，5设计与创新。</p>`;}

export function allocationPage(){return heading('招聘资源分配','在双方已选择、证据核验完整且必要条件通过的候选对中计算分配建议。')+`<form id="allocation-form" class="panel"><h3>本次招聘资源上限</h3><div class="grid3">${field('月度薪资总预算（元）','salary','','number','min="0" required')}${field('培训总预算（元）','training','','number','min="0" required')}${field('导师可投入总课时','mentor','','number','min="0" required')}</div><p class="hint">每位学生最多分配一个岗位，每个岗位不超过名额。薪资使用岗位薪资上限测算；培训成本与导师课时使用岗位录入值。</p><button class="btn primary" type="submit">计算分配建议</button></form><div id="allocation-result"></div>`;}

export async function universityPage(){
 const data=await api('/university/insights');
 return heading('高校培养诊断','从站内岗位与本校授权资料中识别能力缺口。')+`<div class="panel"><h3>${e(state.user.name)}</h3><p class="hint">将入校码提供给本校学生，学生在个人画像中填写后加入本校汇总。当前为本地注册组织。</p><div class="readonly">入校码：${e(state.user.school_code)}</div></div>`+(data.suppressed?empty('等待足够的本校样本',data.message):`<div class="panel"><h3>培养能力与岗位要求</h3><p class="hint">${e(data.basis)} · 授权样本 ${data.sample_count} 人。单项技能同样要求至少5名学生有记录。</p>${data.skills.length?`<div class="table-wrap"><table><thead><tr><th>技能</th><th>岗位要求均值</th><th>自述供给均值</th><th>缺口</th><th>样本</th></tr></thead><tbody>${data.skills.map(r=>`<tr><td>${e(r.skill)}</td><td>${r.target}</td><td>${r.supply}</td><td>${r.gap}</td><td>${r.count}</td></tr>`).join('')}</tbody></table></div>`:empty('暂无满足展示条件的技能','每项能力需要至少5名本校学生提供记录。')}</div>`)+`<div class="panel"><h3>将缺口转化为培养方案</h3><p class="hint">录入课程或实践项目、预期能力增益与投入资源，比较约束下的最优组合。</p>${button('进入培养方案优化','go-curriculum','','primary')}</div>`;
}

on('industry',async el=>{state.industry=el.dataset.id;if(!state.user){auth('register');return;}navigate('jobs');});
on('enter-role',el=>{if(!state.user){auth('register',el.dataset.id);return;}if(state.user.role!==el.dataset.id){auth('login',el.dataset.id);return;}navigate(state.user.role==='student'?'profile':state.user.role==='employer'?'jobs':'university');});
on('go-jobs',()=>navigate('jobs'));
on('go-curriculum',()=>navigate('curriculum'));
on('close-modal',closeDialog);
on('login',()=>auth('login'));
on('register',()=>auth('register'));
on('logout',async()=>{await post('/auth/logout',{});resetIdentity();state.user=null;state.jobs=[];state.applications=[];state.documents=[];navigate('home');});
on('auth-tab',el=>auth(el.dataset.id));
export function auth(mode='login',role='student'){
 dialog(mode==='register'?'创建产教智对账号':'登录产教智对',`<div class="auth-tabs"><button data-action="auth-tab" data-id="login" class="${mode==='login'?'active':''}">登录</button><button data-action="auth-tab" data-id="register" class="${mode==='register'?'active':''}">注册</button></div><form id="auth-form" data-mode="${mode}">${field('账号（字母、数字或下划线）','username','','text','required autocomplete="username" minlength="3" maxlength="60"')}${field('密码（至少10个字符）','password','','password','required minlength="10" maxlength="128" autocomplete="'+(mode==='register'?'new-password':'current-password')+'"')}${mode==='register'?field('姓名 / 企业 / 高校名称','name','','text','required maxlength="80"')+`<div class="field"><label>账号身份<select name="role">${Object.entries(roleNames).map(([key,value])=>`<option value="${key}" ${key===role?'selected':''}>${value}</option>`).join('')}</select></label></div><p class="hint">注册后身份固定。高校账号创建本地组织并生成入校码；学生可以自行选择是否加入学校汇总。</p>`:''}<p class="error-text" id="auth-error"></p><button type="submit" class="btn primary wide">${mode==='register'?'创建账号并进入':'登录'}</button></form>`);
 document.querySelector('#auth-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget;const btn=form.querySelector('button[type=submit]');btn.disabled=true;try{state.user=await post('/auth/'+mode,values(form));resetIdentity();await refresh();closeDialog();navigate('home');}catch(err){document.querySelector('#auth-error').textContent=err.message;}finally{btn.disabled=false;}});
}
