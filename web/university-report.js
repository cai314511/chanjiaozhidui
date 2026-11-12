import {state,api,e,heading,button} from './core.js';
import {universityChartLibrary} from './university-intelligence.js';

let prepared=null,active=null;
const colors={before:'#9caeaa',after:'#217d70',target:'#b9934e',pessimistic:'#b87969'};
const amount=(value,digits=1)=>value==null?'待补充':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:digits});

function dispose(){
 if(!active)return;
 const previous=active;active=null;previous.observer?.disconnect();previous.charts.forEach(chart=>chart.dispose());
}
window.addEventListener('navigate',dispose);
window.addEventListener('identity-reset',()=>{dispose();prepared=null;});

function metricValue(value,unit,missing='待补充'){return value==null?`<span class="report-missing">${missing}</span>`:`${amount(value)}<small>${unit}</small>`;}
function metricCards(data,scenario){
 return data.metrics.map((original,index)=>{
  const metric={...original},year=scenario.years.at(-1);
  if(year&&metric.id==='match')metric.after=year.match_after;
  if(year&&metric.id==='enrollment')metric.after=year.admissions_after;
  if(scenario.coverage_after!=null&&metric.id==='coverage')metric.after=scenario.coverage_after;
  const delta=metric.before!=null&&metric.after!=null?metric.after-metric.before:null;
  const change=delta==null?(metric.id==='related'?'调整后需毕业跟踪':'补齐依据后计算'):metric.unit==='%'?`${delta>0?'+':''}${amount(delta)} 个百分点`:metric.id==='cost'?`本轮新增投入`:`${delta>0?'+':''}${amount(delta)} ${metric.unit}`;
  return `<article class="report-metric" data-metric="${metric.id}"><div class="report-metric-top"><span>0${index+1}</span><span>${e(metric.label)}</span></div><div class="report-before"><span>当前</span><strong>${metricValue(metric.before,metric.unit)}</strong></div><div class="report-after"><span>${metric.id==='related'?'调整后':scenario.name+'方案'}</span><strong>${metricValue(metric.after,metric.unit,metric.id==='related'?'待跟踪':'待测算')}</strong></div><p class="report-delta">${change}</p><p class="report-metric-note">${e(metric.note)}</p></article>`;
 }).join('');
}
function chartCard(id,kicker,title,description,extra='',details=''){
 return `<section class="report-panel ${extra}"><span class="report-kicker">${kicker}</span><h3>${title}</h3><p class="report-description">${description}</p><div class="report-chart" data-report-chart="${id}" role="img" aria-label="${title}"></div>${details}</section>`;
}
function courseText(course,all){
 return `<div class="report-course-line"><strong>${e(course.name)}</strong><span>${amount(course.credits)} 学分 · ${amount(course.hours)} 学时</span><small>先修：${(course.prerequisites||[]).map(id=>e(all.find(c=>c.id===id)?.name||id)).join('、')||'未设置'}</small></div>`;
}
function teachingModules(action){
 const hours=action.added.reduce((sum,course)=>sum+(course.hours||0),0);
 if(!hours)return '';
 const skills=Object.keys(action.skill_delta),focus=skills.join('、')||'课程目标能力';
 const practices=skills.map(name=>{
  if(/SQL|数据库/i.test(name))return '建立数据表、编写查询并核对结果';
  if(/Python|编程|程序/i.test(name))return '完成可运行代码、数据处理脚本与错误检查';
  if(/数据|统计|计量/.test(name))return '完成数据清洗、统计分析与可视化解释';
  if(/产品|设计/.test(name))return '整理需求、绘制原型并记录用户测试反馈';
  if(/沟通|协作|团队/.test(name))return '安排团队分工、评审汇报与协作复盘';
  return `完成${name}的操作练习并保留过程证据`;
 });
 const a=Math.floor(hours*.125),b=Math.floor(hours*.25),c=Math.floor(hours*.375),d=hours-a-b-c;
 const modules=[['方法与基础',a,`明确${focus}的目标和评价标准，开展课前任务，识别现有能力起点。`],['分项训练',b,practices.join('；')+'。'],['综合项目',c,`围绕相关岗位设计完整任务，将${focus}连接到一份可展示的作品或研究报告。`],['评审与改进',d,'提交作品、过程记录和个人贡献说明，完成答辩与一次修订，按相同标准复测。']];
 return `<div class="report-module-plan"><div class="report-module-heading"><h5>建议教学模块</h5><small>新增模块合计 ${amount(hours)} 学时 · 供任课教师确认</small></div><div>${modules.map(([name,value,text])=>`<section><span>${amount(value)} 学时</span><h6>${name}</h6><p>${e(text)}</p></section>`).join('')}</div></div>`;
}
function recommendations(data){
 if(!data.actions.length){
  const gaps=data.skills.filter(s=>s.before!=null&&s.before<s.target).sort((a,b)=>(b.target-b.before)-(a.target-a.before));
  return `<div class="report-next-step"><h4>${gaps.length?'从已识别能力缺口开始安排课程':'先接入培养方案与课程依据'}</h4><p>${gaps.length?gaps.slice(0,4).map(s=>`${e(s.name)}：本校 ${amount(s.before)} 级 → 岗位目标 ${amount(s.target)} 级`).join('；'):'上传本校课程、培养方案和本专业能力评估，建立课程、技能与资源之间的对应关系。'}</p><p>在课程库选择具体课程，确认先修关系、学分、学时、教师与实验室投入，再填写项目考核和预期能力改善。</p>${button('从本校课程库选择','university-course-library')}${button('填写培养调整方案','route','decision','primary')}</div>`;
 }
 return `<div class="report-actions">${data.actions.map((action,index)=>{
  const kinds={add:'新增课程',modify:'重构课程',delete:'精简课程',merge:'整合课程'};
  const courses=[...(action.removed||[]),...(action.added||[])];
  return `<article class="report-action"><div class="report-action-head"><span class="report-action-number">${String(index+1).padStart(2,'0')}</span><div><span class="report-kicker">${e(kinds[action.kind]||'课程调整')} · ${e(action.status)}</span><h4>${e((action.added||[]).map(c=>c.name).join('、')||(action.removed||[]).map(c=>c.name).join('、'))}</h4></div><span class="report-cost">¥ ${amount(action.cost,0)}</span></div><p>${e(action.reason)}</p><div class="report-action-columns"><div><span class="report-label">调整前</span>${action.removed.map(c=>courseText(c,data.courses_before)).join('')||'<p class="report-description">当前课程结构中无该新增模块</p>'}</div><div><span class="report-label accent">调整后</span>${action.added.map(c=>courseText(c,[...data.courses_before,...data.courses_after,...courses])).join('')||'<p class="report-description">移除后将学习时间重新分配至保留课程</p>'}</div></div><div class="report-gain-list">${Object.entries(action.skill_delta).map(([name,value])=>`<span>${e(name)} <b>${value>0?'+':''}${amount(value)} 级</b></span>`).join('')}</div>${teachingModules(action)}<div class="report-teaching"><div><h5>怎么实施</h5><p>第一学年完成课程大纲、先修检查与师资安排；第二学年小班试行，使用同一评分标准记录课前和课后表现；第三学年纳入方向项目与企业任务；第四学年结合毕业去向复盘。</p></div><div><h5>怎么验收</h5><p>围绕${e(Object.keys(action.skill_delta).join('、')||'课程学习目标')}设置可提交的项目作品、过程记录与答辩。任课教师核对能力等级，专业负责人核对学分学时与实际投入。</p></div></div><details><summary>查看能力增益依据与实施条件</summary><p>${e(action.evidence)}</p><p>以上能力增益为方案输入，按课程考核更新。正式实施前由本校确认教学大纲、开课学期、预算与师资安排。</p></details></article>`;
 }).join('')}</div>`;
}
function yearTable(scenario){
 if(!scenario.years.length)return '<p class="report-description">补齐预测输入后，逐年展示调整与不调整两条路径。</p>';
 return `<div class="table-wrap"><table><thead><tr><th>年份</th><th>不调整匹配度</th><th>调整后匹配度</th><th>不调整就业率</th><th>调整后就业率</th><th>招生人数</th></tr></thead><tbody>${scenario.years.map(y=>`<tr><td>${y.year}</td><td>${amount(y.match_before)}%</td><td>${amount(y.match_after)}%</td><td>${y.employment_before==null?'待补充':amount(y.employment_before*100)+'%'}</td><td>${y.employment_after==null?'待补充':amount(y.employment_after*100)+'%'}</td><td>${amount(y.admissions_after,0)}</td></tr>`).join('')}</tbody></table></div>`;
}
function scenarioSummary(data,scenario){
 const assumption=scenario.assumptions;
 const note=assumption?`需求年增长 ${amount(assumption.demand_growth*100)}% · 技能增益系数 ${amount(assumption.skill_gain_factor,2)} · 情景概率 ${amount(assumption.probability*100)}%`:'尚未设置需求变化、技能增益和情景概率';
 return `<div><span class="report-label">正在查看 · ${e(scenario.name)}情景</span><p>${e(scenario.description)}</p></div><p>${note}<small>${data.forecast_status==='ready'?`课程效果延迟 ${data.implementation_lag} 年 · 招生影响毕业供给延迟 ${data.admissions_delay_years} 年`:'完成一次专业调整决策后显示四年推演'}</small></p>`;
}

export async function universityReportPage(){
 const epoch=state.sessionEpoch;
 const data=await api('/university/report');
 if(epoch!==state.sessionEpoch)return '';
 prepared={data,epoch};
 const base=data.scenarios.find(s=>s.name==='基准'),match=data.metrics.find(m=>m.id==='match');
 const improvement=match.before!=null&&match.after!=null?match.after-match.before:null;
 const mainAction=data.actions[0];
 const conclusion=improvement!=null?`基准方案匹配度可提升 ${amount(improvement)} 个百分点`:mainAction?'从课程实践着手，补齐培养与岗位之间的连接':'先连接课程、学生与岗位，形成培养判断';
 const totalCredits=data.courses_before.reduce((n,c)=>n+(c.credits||0),0);
 const totalHours=data.courses_before.reduce((n,c)=>n+(c.hours||0),0);
 const skillSummary=`<details><summary>学生能力汇总 · ${data.student_skills.length} 项</summary>${data.student_skills.length?`<div class="table-wrap"><table><thead><tr><th>技能</th><th>本校等级均值</th><th>样本数</th></tr></thead><tbody>${data.student_skills.map(s=>`<tr><td>${e(s.name)}</td><td>${amount(s.level,2)}</td><td>${s.count}</td></tr>`).join('')}</tbody></table></div><p>没有岗位目标等级时，仍保留本校能力证据，匹配度与覆盖度等待可比较的目标。</p>`:'<p>等待每项技能至少5名本校学生提供记录。</p>'}</details>`;
 return `<div class="university-report" id="university-report">
 ${heading('高校培养诊断','将证据、培养调整和四年情景，整理成一份可阅读的报告。',button('更新报告','reload','','small'))}
 <section class="report-hero"><div class="report-hero-copy"><span class="report-kicker">培养诊断报告 / 四年培养周期</span><div class="report-status"><i></i>${data.feasible?'方案已通过资源约束测算':'依据当前已接入资料诊断'}</div><h2>${conclusion}</h2><p>${e(data.program?.name||state.user.name+'培养方案')} ${data.program?'· '+e(data.program.region):''}</p><p class="report-hero-detail">${mainAction?'优先行动：'+e(mainAction.reason):'导入本校课表，建立课程库，再结合本专业岗位目标与能力证据制定调整方案。'}</p><div class="inline">${button('导入全校课表','university-import','teaching','primary')}${button('查看课程库','university-course-library')}${button('调整方案与假设','route','decision')}</div></div><div class="report-cycle" aria-label="四年培养闭环"><div class="report-cycle-inner"><small>培养与反馈</small><strong>4<span>年</span></strong><p>课程 · 实践 · 毕业跟踪</p></div><span class="report-orbit a">课程重构</span><span class="report-orbit b">岗位连接</span><span class="report-orbit c">结果复盘</span></div></section>
 <div class="report-source-strip"><span>${e(data.metrics_scope)}</span><span>${data.source.created_at?'测算于 '+e(data.source.created_at.slice(0,10)):'本次读取 '+e(data.generated_at.slice(0,10))}</span><span>${data.program?'当前招生 '+data.program.current_seats+' 人':'尚未登记本专业招生规模'}</span><span>全校课程库 ${amount(data.catalog.total,0)} 门</span></div>
 <div class="report-section-title"><div><span class="report-kicker">01 / 评价总览</span><h3>五个维度，先看调整带来什么</h3></div><span class="report-description">当前依据 → 方案测算</span></div>
 <div class="report-metrics" id="report-metrics">${metricCards(data,base)}</div>
 <div class="report-section-title"><div><span class="report-kicker">02 / 情景推演</span><h3>同一份培养方案，放进三种未来</h3></div><span class="report-description">点击情景，联动查看四年结果</span></div>
 <div class="report-scenarios" aria-label="选择预测情景">${data.scenarios.map(s=>`<button class="report-scenario" type="button" data-report-scenario="${s.name}" aria-pressed="${s.name==='基准'}"><span class="report-scenario-emoji" aria-hidden="true">${s.emoji}</span><div><strong>${s.name}<small>${s.name==='基准'?'默认情景':s.name==='乐观'?'把握增长机会':'保留调整余地'}</small></strong><p>${s.description}</p></div><span class="report-scenario-check" aria-hidden="true">✓</span></button>`).join('')}</div>
 <div class="report-scenario-summary" id="report-scenario-summary">${scenarioSummary(data,base)}</div>
 <section class="report-panel report-forecast"><div class="report-chart-head"><div><span class="report-kicker">四年预测 / 调整与不调整对比</span><h3 id="report-forecast-caption">基准情景 · 专业与岗位匹配度</h3></div><div class="report-chart-switch" aria-label="选择预测指标"><button type="button" data-forecast-metric="match" aria-pressed="true">培养匹配</button><button type="button" data-forecast-metric="employment" aria-pressed="false">就业率</button><button type="button" data-forecast-metric="admissions" aria-pressed="false">招生规模</button></div></div><p class="report-description">实线为调整方案，虚线为不调整路径。悬停查看逐年结果。</p><div class="report-chart forecast-chart" data-report-chart="forecast" role="img" aria-label="四年培养情景预测"></div><p class="report-chart-foot">${data.forecast_status==='ready'?e(data.forecast_basis)+'；课程效果依照设定延迟生效。':e(data.forecast_reason)}</p><details><summary>查看逐年数据与指标口径</summary><div id="report-year-table">${yearTable(base)}</div><p>就业率按就业人数占毕业生人数计算；专业对口率单独依赖对口就业跟踪。情景参数为显式假设。</p></details></section>
 <div class="report-chart-grid">${chartCard('skills','能力结构 / 0—5级','把能力缺口看清楚','对照岗位目标、本校能力与调整方案。技能增益按课程方案假设计算。','',skillSummary)}${chartCard('resources','资源投入 / 约束内调整','让改善与投入一起被看见','条形表示占已登记资源上限的比例，悬停查看金额或课时。')}</div>
 <div class="report-section-title"><div><span class="report-kicker">03 / 课程与培养行动</span><h3>把诊断落到具体课程和教学安排</h3></div><span class="report-description">${data.actions.length} 项${data.feasible?'已测算课程动作':'待确认培养建议'}</span></div>
 ${recommendations(data)}
 <section class="report-panel report-roadmap"><span class="report-kicker">04 / 四年实施路径</span><h3>从课程试行到毕业反馈，逐年推进</h3><div class="report-roadmap-grid">${[['01','第一学年','课程准备','核对岗位与课程映射，确定先修、教学大纲、预算和师资，建立能力基线。'],['02','第二学年','小班试行','开展课程项目与阶段考核，记录实际课时和资源支出，按学生意愿推进方向分流。'],['03','第三学年','实践衔接','将课程成果转入校企项目与实习任务，按企业反馈调整项目难度和技能训练。'],['04','第四学年','毕业复盘','跟踪毕业去向、专业对口就业和实施成本，将实际结果回填下一轮培养调整。']].map(([n,year,title,text])=>`<article><span>${n}</span><small>${year}</small><h4>${title}</h4><p>${text}</p></article>`).join('')}</div></section>
 <section class="report-panel report-catalog"><div><span class="report-kicker">全校课程资产 / 与单专业方案分别管理</span><h3>${amount(data.catalog.total,0)} 门课程已进入本校课程库</h3><p>已确认技能映射 ${amount(data.catalog.mapped,0)} 门 · 未提供学时 ${amount(data.catalog.missing_hours,0)} 门。课表未提供的字段保持空缺。</p></div><div class="inline">${button('导入课程','university-import','teaching')}${button('浏览与搜索','university-course-library')}<a class="btn" href="/api/university/courses/export">导出课程 XLSX</a></div></section>
 <details class="report-panel report-method"><summary>课程明细、数据来源与测算依据</summary><p>${e(data.source.title||'当前岗位与本校授权学生汇总')} · ${e(data.source.assumptions||'尚未设置四年情景参数。')}</p><p>本专业原方案 ${data.courses_before.length} 门课程，${amount(totalCredits)} 学分、${amount(totalHours)} 学时；全校课程库按导入文件另行归并，不直接计入本专业方案。</p><div class="table-wrap"><table><thead><tr><th>原方案课程</th><th>学分</th><th>学时</th><th>调整后状态</th></tr></thead><tbody>${data.courses_before.map(c=>`<tr><td>${e(c.name)}</td><td>${c.credits}</td><td>${c.hours}</td><td>${data.courses_after.length?(data.courses_after.some(a=>a.id===c.id)?'保留 / 更新':'移除 / 整合'):'尚未测算'}</td></tr>`).join('')}</tbody></table></div>${data.source.provenance.map(p=>`<p><strong>${e(p.source?.title||'已登记来源')}</strong> · ${e(p.source?.scope||'')}<small class="hash">${e(p.sha256||'')}</small></p>`).join('')}<p>能力汇总遵守至少5人展示规则。课程收益、需求增长与资源容量使用已登记假设；专业对口率的调整后数值等待毕业跟踪。所有图表使用本地 ECharts Canvas。</p>${data.source.run_id?`<a class="btn small" href="/api/competition/runs/${encodeURIComponent(data.source.run_id)}/export?format=md">导出测算报告正文</a>`:''}<p class="report-school-code">本校入校码：${e(state.user.school_code||'')} · 学生自愿填写后加入本校汇总。</p></details>
 </div>`;
}

function emptyChart(host,title,text){host.innerHTML=`<div class="report-chart-empty"><span aria-hidden="true">◌</span><strong>${e(title)}</strong><p>${e(text)}</p></div>`;}
function chart(controller,id,option){
 const host=controller.root.querySelector(`[data-report-chart="${id}"]`);
 const existing=controller.library.getInstanceByDom(host);
 const instance=existing||controller.library.init(host,null,{renderer:'canvas'});
 if(!existing)controller.charts.push(instance);
 instance.setOption({animation:!matchMedia('(prefers-reduced-motion:reduce)').matches,animationDuration:650,textStyle:{fontFamily:'Microsoft YaHei, sans-serif',color:'#4f6e66'},...option},true);
}
const grid={left:12,right:20,top:48,bottom:15,containLabel:true};
const legend={top:3,right:0,itemWidth:16,itemHeight:8,textStyle:{fontSize:11,color:'#61776e'}};
const axis={axisLine:{show:false},axisTick:{show:false},axisLabel:{color:'#789087',fontSize:11},splitLine:{lineStyle:{color:'#5c8b7215'}}};
const tooltip={trigger:'axis',backgroundColor:'#fffffff0',borderColor:'#c2d7ce',padding:13,textStyle:{color:'#264e43',fontSize:12},extraCssText:'border-radius:14px;box-shadow:0 12px 30px #214c4320;backdrop-filter:blur(14px)'};
function drawForecast(controller){
 const s=controller.data.scenarios.find(s=>s.name===controller.scenario),host=controller.root.querySelector('[data-report-chart=forecast]');
 const labels={match:'专业与岗位匹配度',employment:'就业率',admissions:'招生规模'},key=controller.metric;
 controller.root.querySelector('#report-forecast-caption').textContent=`${s.name}情景 · ${labels[key]}`;
 if(!s.years.length){emptyChart(host,'四年预测等待完整依据',controller.data.forecast_reason);return;}
 const percentage=key!=='admissions',scale=key==='employment'?100:1;
 const before=s.years.map(y=>y[key+'_before']==null?null:Number((y[key+'_before']*scale).toFixed(3)));
 const after=s.years.map(y=>y[key+'_after']==null?null:Number((y[key+'_after']*scale).toFixed(3)));
 const color=s.name==='悲观'?colors.pessimistic:colors.after;
 chart(controller,'forecast',{grid:{...grid,top:55,bottom:20,left:18},legend:{...legend,data:['不调整','调整方案']},tooltip:{...tooltip,valueFormatter:v=>amount(v)+(percentage?'%':' 人')},
  xAxis:{...axis,type:'category',boundaryGap:false,data:s.years.map(y=>y.year+'年')},yAxis:{...axis,type:'value',min:percentage?0:undefined,max:percentage?100:undefined,axisLabel:{...axis.axisLabel,formatter:percentage?'{value}%':'{value}人'}},
  series:[{name:'不调整',type:'line',smooth:.25,symbol:'circle',symbolSize:7,data:before,lineStyle:{width:2,type:'dashed',color:colors.before},itemStyle:{color:colors.before}},
   {name:'调整方案',type:'line',smooth:.25,symbol:'circle',symbolSize:9,data:after,lineStyle:{width:3.5,color},itemStyle:{color,borderColor:'#fff',borderWidth:2},areaStyle:{color:new controller.library.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color+'30'},{offset:1,color:color+'02'}])},
    markPoint:{symbol:'circle',symbolSize:12,data:[{coord:[3,after[3]],value:after[3]}],label:{show:false},itemStyle:{color}}}]
 });
 host.setAttribute('aria-label',`${s.name}情景四年${labels[key]}，不调整 ${before.map(v=>amount(v)).join('、')}；调整后 ${after.map(v=>amount(v)).join('、')}`);
}
function drawSkills(controller){
 const scenario=controller.data.scenarios.find(s=>s.name===controller.scenario);
 const rows=controller.data.skills.filter(s=>s.before!=null).slice(0,8).map(s=>({...s,after:scenario.skill_levels[s.name]??s.after})),host=controller.root.querySelector('[data-report-chart=skills]');
 if(!rows.length){emptyChart(host,controller.data.sample_count==null?'等待足够的本校样本':'等待可比较的能力证据','岗位需设置目标等级，每项能力需至少5名本校学生有记录。');return;}
 if(rows.length>=3){
  chart(controller,'skills',{legend:{...legend,data:['岗位目标','当前能力','调整方案']},tooltip:{...tooltip,trigger:'item'},radar:{center:['50%','55%'],radius:'62%',splitNumber:5,nameGap:9,axisName:{color:'#496b61',fontSize:11},indicator:rows.map(r=>({name:r.name,max:5})),splitArea:{areaStyle:{color:['#ffffff10','#ffffff40']}},splitLine:{lineStyle:{color:'#48735d20'}},axisLine:{lineStyle:{color:'#48735d20'}}},series:[{type:'radar',symbolSize:5,data:[{name:'岗位目标',value:rows.map(s=>s.target),lineStyle:{color:colors.target,type:'dashed',width:2},itemStyle:{color:colors.target},areaStyle:{opacity:0}},{name:'当前能力',value:rows.map(s=>s.before),lineStyle:{color:colors.before,width:2},itemStyle:{color:colors.before},areaStyle:{color:colors.before,opacity:.06}},...(rows.some(s=>s.after!=null)?[{name:'调整方案',value:rows.map(s=>s.after),lineStyle:{color:colors.after,width:2.5},itemStyle:{color:colors.after},areaStyle:{color:colors.after,opacity:.17}}]:[])]}]});
 }else{
  chart(controller,'skills',{grid,legend,tooltip,xAxis:{...axis,type:'value',max:5},yAxis:{...axis,type:'category',data:rows.map(r=>r.name)},series:[['岗位目标','target',colors.target],['当前能力','before',colors.before],['调整方案','after',colors.after]].map(([name,key,color])=>({name,type:'bar',barMaxWidth:16,data:rows.map(r=>r[key]),itemStyle:{color,borderRadius:[0,5,5,0]}}))});
 }
 host.setAttribute('aria-label',rows.map(s=>`${s.name}，目标${s.target}，当前${s.before}，调整${s.after??'待测算'}`).join('；'));
}
function drawResources(controller){
 const rows=controller.data.resources,host=controller.root.querySelector('[data-report-chart=resources]');
 if(!rows.length){emptyChart(host,'等待培养资源与调整预算','导入本专业培养配置，登记教师、实验室课时与预算上限。');return;}
 chart(controller,'resources',{grid:{...grid,top:55,bottom:30},legend:{...legend,data:['当前占用','方案占用']},tooltip:{...tooltip,formatter:params=>params.map(p=>{const row=rows[p.dataIndex],value=p.seriesIndex===0?row.before:row.after;return `${p.marker}${e(p.seriesName)}：${amount(value)} ${row.unit} / 上限 ${amount(row.limit)} ${row.unit}`;}).join('<br>')},xAxis:{...axis,type:'value',max:Math.max(100,...rows.map(r=>r.limit?Math.ceil((r.after||r.before)/r.limit*100):0)),axisLabel:{...axis.axisLabel,formatter:'{value}%'}},yAxis:{...axis,type:'category',inverse:true,data:rows.map(r=>r.label)},series:[['当前占用','before',colors.before],['方案占用','after',colors.after]].map(([name,key,color])=>({name,type:'bar',barMaxWidth:17,barGap:'45%',data:rows.map(r=>r[key]==null||r.limit===0?null:Number((r[key]/r.limit*100).toFixed(2))),itemStyle:{color,borderRadius:[0,6,6,0]},label:{show:true,position:'right',fontSize:11,color:'#59766a',formatter:p=>p.value==null?'':p.value+'%'}}))});
 host.setAttribute('aria-label',rows.map(r=>`${r.label}：当前${r.before}，方案${r.after??'待测算'}，上限${r.limit}${r.unit}`).join('；'));
}
function updateScenario(controller,name){
 controller.scenario=name;
 const scenario=controller.data.scenarios.find(s=>s.name===name);
 controller.root.querySelectorAll('[data-report-scenario]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.reportScenario===name)));
 controller.root.querySelector('#report-metrics').innerHTML=metricCards(controller.data,scenario);
 controller.root.querySelector('#report-scenario-summary').innerHTML=scenarioSummary(controller.data,scenario);
 controller.root.querySelector('#report-year-table').innerHTML=yearTable(scenario);
 drawForecast(controller);drawSkills(controller);
}
export async function bindUniversityReport(){
 const root=document.querySelector('#university-report');
 if(!root||!prepared||prepared.epoch!==state.sessionEpoch)return;
 dispose();
 const controller={root,data:prepared.data,scenario:'基准',metric:'match',charts:[],library:null};active=controller;
 try{
  controller.library=await universityChartLibrary();
  if(active!==controller||!root.isConnected)return;
  drawForecast(controller);drawSkills(controller);drawResources(controller);
  controller.observer=new ResizeObserver(()=>{if(active===controller)controller.charts.forEach(chart=>chart.resize());});
  controller.observer.observe(root);
  root.querySelectorAll('[data-report-scenario]').forEach(el=>el.onclick=()=>updateScenario(controller,el.dataset.reportScenario));
  root.querySelectorAll('[data-forecast-metric]').forEach(el=>el.onclick=()=>{controller.metric=el.dataset.forecastMetric;root.querySelectorAll('[data-forecast-metric]').forEach(b=>b.setAttribute('aria-pressed',String(b===el)));drawForecast(controller);});
 }catch(error){if(active===controller)root.querySelectorAll('[data-report-chart]').forEach(host=>emptyChart(host,'图表加载未完成',error.message));}
}
