import {state,api,e,fmt,heading,button,empty,on} from './core.js';

const palette=['#247b69','#bd9c49','#71af9d','#d4c48f','#436d79','#a6c8ba'];
let selected={track:'',city:''},prepared=null,active=null,pageSequence=0,libraryPromise=null;

function dispose(){
 if(!active)return;
 const previous=active;active=null;previous.sequence++;
 clearTimeout(previous.timer);previous.resize?.disconnect();previous.mutations?.disconnect();
 previous.charts.forEach(chart=>chart.dispose());previous.charts=[];
}
window.addEventListener('navigate',dispose);
window.addEventListener('identity-reset',()=>{dispose();prepared=null;selected={track:'',city:''};pageSequence++;});
document.addEventListener('visibilitychange',()=>{
 if(!active)return;
 clearTimeout(active.timer);
 if(!document.hidden)refresh(active);
});

function library(){
 if(window.echarts)return Promise.resolve(window.echarts);
 if(libraryPromise)return libraryPromise;
 libraryPromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='/assets/vendor/echarts/echarts.min.js';script.async=true;
  script.onload=()=>window.echarts?resolve(window.echarts):reject(new Error('图表运行库加载后不可用'));
  script.onerror=()=>{script.remove();libraryPromise=null;reject(new Error('本地图表运行库加载失败，请刷新页面重试'));};
  document.head.append(script);
 });return libraryPromise;
}
function optionList(values,value,label){const list=[...new Set([...(values||[]),...(value?[value]:[])])];return `<option value="">${label}</option>`+list.map(item=>`<option value="${e(item)}" ${value===item?'selected':''}>${e(item)}</option>`).join('');}
function valueLabel(value){return value===null||value===undefined?'样本不足':fmt(value);}
function chartPanel(id,title,subtitle,wide=false){return `<section class="intel-panel ${wide?'intel-wide':''}"><div class="intel-chart-heading"><span class="intel-kicker">${e(id.toUpperCase())}</span><h3>${title}</h3><p>${subtitle}</p></div><div class="intel-chart" data-intel-chart="${id}" role="img" aria-label="${title}"></div></section>`;}
function content(data){
 const s=data.summary||{},meta=data.source_meta||{};
 return `<header class="intel-hero"><div><span class="intel-kicker">INDUSTRY × EDUCATION · 高校产业与人才观察</span><h2>从企业需求，看见培养的下一步</h2><p>结合历史招聘样本、平台真实岗位与本校能力证据，观察需求结构和人才供给。</p></div><span class="intel-signal"><i></i>每60秒更新平台数据</span></header>
 <form id="university-intel-filter" class="intel-filter"><label>产业赛道<select name="track">${optionList(data.filters?.tracks,selected.track,'全部赛道')}</select></label><label>工作城市<select name="city">${optionList(data.filters?.cities,selected.city,'全部城市')}</select></label><button type="submit" class="btn primary">联动分析</button>${button('刷新数据','university-intel-refresh','','small')}<span id="university-intel-status" aria-live="polite">统计更新于 ${e(formatTime(data.generated_at))}</span></form>
 <div class="intel-metrics">${[['历史相关公告',s.historical_postings,'历史样本，非当前空缺'],['平台真实岗位',s.live_postings,'来自企业当前发布'],['相关企业',s.companies,'所选范围内企业'],['本校学生样本',s.student_count,data.student_suppressed?'小样本已隐藏':'已纳入本校分析']].map(([label,value,note])=>`<article><span>${label}</span><strong>${valueLabel(value)}</strong><small>${note}</small></article>`).join('')}</div>
 <div class="intel-basis"><span>历史观察期：${e(data.history_period||'尚无可用历史样本')}</span><span>已读取 ${fmt(meta.scanned_rows||0)} 条原始记录</span><span>当前筛选：${e(selected.track||'全部赛道')} · ${e(selected.city||'全部城市')}</span></div>
 <div class="intel-grid">${chartPanel('trend','需求沿时间的变化','按原始发布日期的月份汇总；点击图例或拖动缩放查看观察期。',true)}${chartPanel('sectors','产业需求的结构','赛道关联公告条数；点击柱形可联动筛选全页。')}${chartPanel('skills','企业正在寻找什么能力','历史公告与平台岗位分别计数，比较技能提及频次。')}${chartPanel('radar','能力目标与本校证据','使用0—5级的真实岗位目标与本校学生能力均值；仅展示达到样本要求的维度。')}${chartPanel('coverage','从技能需求连接课程','课程中已明确映射到该技能的课程数量；缺少映射不计为零。')}${chartPanel('network','产业与技能的需求网络','连线表示历史公告中的赛道—技能同现次数，可拖动节点及滚轮缩放。',true)}${chartPanel('goals','本校学生正在走向哪里','仅显示达到最小样本要求的职业目标分组。',true)}</div>
 <section class="intel-panel intel-next"><div><span class="intel-kicker">从观察到培养行动</span><h3>把课程依据接入，再比较调整方案</h3><p>用本校课程与技能映射核对覆盖关系，结合明确的教学资源和岗位目标制定方案。</p></div><div class="inline">${button('导入本校课程','university-import','courses','primary')}${button('本校课程库','university-course-library')}${button('培养方案优化','route','curriculum')}${button('专业调整决策','route','decision')}</div></section>
 <details class="intel-panel intel-method"><summary>统计范围、来源与样本说明</summary><ul>${(data.notes||[]).map(note=>`<li>${e(note)}</li>`).join('')}</ul><p>历史资料由本机导入，不代表实时全市场招聘需求。平台岗位和本校数据按当前服务记录更新。</p>${(meta.sources||[]).map(source=>`<p><strong>${e(source.name)}</strong> · ${fmt(source.scanned_rows||0)} 条读取记录</p><p class="hash">SHA-256 ${e(source.sha256||'未提供')}</p>`).join('')}<p>图表：本地 Apache ECharts 6.0.0 · Canvas 渲染。</p></details>`;
}
function formatTime(value){if(!value)return '尚未生成';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString('zh-CN',{hour12:false});}

export async function universityIntelligencePage(){
 const sequence=++pageSequence,epoch=state.sessionEpoch;
 const data=await api('/university/intelligence?'+new URLSearchParams({...selected}));
 if(sequence!==pageSequence||epoch!==state.sessionEpoch)return '';
 prepared={data,epoch};
 return `<div id="university-intelligence" class="university-intelligence">${content(data)}</div>`;
}
function stillCurrent(controller){return active===controller&&controller.epoch===state.sessionEpoch&&controller.root.isConnected;}
function schedule(controller){clearTimeout(controller.timer);if(stillCurrent(controller)&&!document.hidden)controller.timer=setTimeout(()=>refresh(controller),60000);}
async function refresh(controller){
 if(!stillCurrent(controller))return;
 clearTimeout(controller.timer);const sequence=++controller.sequence;
 const status=controller.root.querySelector('#university-intel-status');status.textContent='正在更新统计…';controller.root.setAttribute('aria-busy','true');
 try{
  const data=await api('/university/intelligence?'+new URLSearchParams({...selected}));
  if(!stillCurrent(controller)||sequence!==controller.sequence)return;
  controller.charts.forEach(chart=>chart.dispose());controller.charts=[];
  controller.root.innerHTML=content(data);await paint(controller,data);
 }catch(error){if(stillCurrent(controller)&&sequence===controller.sequence)controller.root.querySelector('#university-intel-status').textContent='本次更新未完成：'+error.message;}
 finally{if(stillCurrent(controller)&&sequence===controller.sequence){controller.root.removeAttribute('aria-busy');schedule(controller);}}
}
function base(){return {color:palette,backgroundColor:'transparent',animation:!matchMedia('(prefers-reduced-motion: reduce)').matches,animationDuration:850,animationDurationUpdate:650,textStyle:{fontFamily:'Microsoft YaHei, sans-serif',color:'#365c50'},tooltip:{trigger:'axis',renderMode:'richText',backgroundColor:'#fffdf4',borderColor:'#c3af73',textStyle:{color:'#244e40'}},grid:{left:24,right:26,top:36,bottom:32,containLabel:true}};}
function axis(type='category'){return {type,axisLine:{lineStyle:{color:'#aac6b7'}},axisTick:{show:false},axisLabel:{color:'#557568',fontSize:11,hideOverlap:true},splitLine:{show:type==='value',lineStyle:{color:'rgba(66,116,95,.1)',type:'dashed'}}};}
function noData(host,title,detail){host.innerHTML=empty(title,detail);host.classList.add('intel-no-data');}
function chart(controller,echarts,id,option,click){
 const host=controller.root.querySelector(`[data-intel-chart="${id}"]`);host.classList.remove('intel-no-data');
 const instance=echarts.init(host,null,{renderer:'canvas',devicePixelRatio:Math.min(window.devicePixelRatio||1,2)});
 instance.setOption({...base(),...option});if(click)instance.on('click',click);controller.charts.push(instance);
}
async function paint(controller,data){
 const sequence=controller.sequence,echarts=await library();if(!stillCurrent(controller)||sequence!==controller.sequence)return;
 const host=id=>controller.root.querySelector(`[data-intel-chart="${id}"]`);
 const trend=data.trend||[];
 if(trend.length)chart(controller,echarts,'trend',{grid:{left:24,right:26,top:45,bottom:62,containLabel:true},legend:{top:4,textStyle:{color:'#557568'}},xAxis:{...axis(),data:trend.map(row=>row.month),boundaryGap:false},yAxis:{...axis('value'),name:'公告条数',minInterval:1},dataZoom:[{type:'inside',start:0,end:100},{type:'slider',height:17,bottom:5,borderColor:'transparent',fillerColor:'rgba(55,137,110,.13)',handleStyle:{color:'#bd9c49'}}],series:[{name:'历史岗位公告',type:'line',smooth:.3,symbol:'circle',symbolSize:7,lineStyle:{width:3},itemStyle:{borderWidth:2,borderColor:'#fffdf4'},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(36,123,105,.27)'},{offset:1,color:'rgba(36,123,105,.015)'}])},data:trend.map(row=>row.postings)}]});
 else noData(host('trend'),'当前范围没有历史趋势','调整赛道或城市，或等待接入历史招聘资料。');
 const sectors=(data.sectors||[]).slice(0,10).reverse();
 if(sectors.length)chart(controller,echarts,'sectors',{xAxis:{...axis('value'),minInterval:1},yAxis:{...axis(),data:sectors.map(row=>row.name),axisLabel:{...axis().axisLabel,width:90,overflow:'truncate'}},series:[{name:'关联公告',type:'bar',barMaxWidth:20,showBackground:true,backgroundStyle:{color:'rgba(36,123,105,.045)',borderRadius:6},itemStyle:{borderRadius:[0,6,6,0]},data:sectors.map((row,i)=>({value:row.postings,itemStyle:{color:palette[i%palette.length]}}))}]},params=>{
  if(!(data.filters?.tracks||[]).includes(params.name))return;selected.track=params.name;refresh(controller);
 });else noData(host('sectors'),'暂无产业结构统计','当前筛选没有可用公告。');
 const skills=(data.skills||[]).slice(0,10).reverse();
 if(skills.length)chart(controller,echarts,'skills',{legend:{top:0,textStyle:{color:'#557568'},data:['历史公告提及','平台岗位提及']},xAxis:{...axis('value'),minInterval:1},yAxis:{...axis(),data:skills.map(row=>row.name),axisLabel:{...axis().axisLabel,width:85,overflow:'truncate'}},series:[{name:'历史公告提及',type:'bar',barMaxWidth:12,itemStyle:{borderRadius:4},data:skills.map(row=>row.postings)},{name:'平台岗位提及',type:'bar',barMaxWidth:12,itemStyle:{borderRadius:4},data:skills.map(row=>row.live_postings)}]});
 else noData(host('skills'),'暂无技能需求证据','公告或平台岗位还没有可统计的技能。');
 const levels=(data.skills||[]).filter(row=>Number.isFinite(row.student_level)&&Number.isFinite(row.target_level)).slice(0,7);
 if(levels.length>=3)chart(controller,echarts,'radar',{tooltip:{trigger:'item',renderMode:'richText'},legend:{bottom:0,textStyle:{color:'#557568'}},radar:{radius:'62%',center:['50%','47%'],indicator:levels.map(row=>({name:row.name,max:5})),axisName:{color:'#426b59',fontSize:11},splitArea:{areaStyle:{color:['rgba(36,123,105,.02)','rgba(36,123,105,.055)']}}},series:[{type:'radar',symbolSize:5,data:[{name:'岗位能力目标',value:levels.map(row=>row.target_level),areaStyle:{opacity:.1}},{name:'本校能力均值',value:levels.map(row=>row.student_level),areaStyle:{opacity:.17}}]}]});
 else noData(host('radar'),'本校能力证据尚未形成可比维度','需要至少3个同时具备真实岗位能力目标和足够本校学生样本的技能维度。缺失等级不绘制为零。');
 const coverage=(data.coverage||[]).filter(row=>Number.isFinite(row.course_count)).slice(0,12).reverse();
 if(coverage.length)chart(controller,echarts,'coverage',{xAxis:{...axis('value'),minInterval:1,name:'课程数'},yAxis:{...axis(),data:coverage.map(row=>row.skill),axisLabel:{...axis().axisLabel,width:85,overflow:'truncate'}},series:[{name:'映射课程',type:'bar',barMaxWidth:22,itemStyle:{color:'#71af9d',borderRadius:5},data:coverage.map(row=>row.course_count)}]});
 else noData(host('coverage'),'尚未接入课程与技能映射','导入本校课程并核对技能映射后，这里展示已有课程覆盖。');
 const links=(data.links||[]).filter(link=>link.value>0).slice(0,65),nodes=[...new Set(links.flatMap(link=>[link.source,link.target]))];
 if(links.length)chart(controller,echarts,'network',{tooltip:{trigger:'item',renderMode:'richText'},legend:{top:0,data:['产业赛道','岗位技能'],textStyle:{color:'#557568'}},series:[{type:'graph',layout:'force',roam:true,draggable:true,force:{repulsion:190,edgeLength:[75,150],gravity:.08},label:{show:true,fontSize:11,color:'#345c4c'},edgeLabel:{show:false},lineStyle:{color:'source',curveness:.15,opacity:.25},emphasis:{focus:'adjacency',lineStyle:{opacity:.8,width:4}},categories:[{name:'产业赛道'},{name:'岗位技能'}],data:nodes.map(name=>({name,category:name.startsWith('赛道：')?0:1,symbolSize:name.startsWith('赛道：')?39:25,label:{formatter:name.replace(/^(赛道|技能)：/,'')}})),links:links.map(link=>({...link,lineStyle:{width:Math.min(6,1+Math.log10(link.value+1))}}))}]});
 else noData(host('network'),'暂无产业与技能的共现关系','关系图只使用原始历史公告中的实际关联。');
 const goals=(data.student_goals||[]).slice(0,10);
 if(goals.length)chart(controller,echarts,'goals',{xAxis:{...axis(),data:goals.map(row=>row.name),axisLabel:{...axis().axisLabel,width:95,overflow:'truncate'}},yAxis:{...axis('value'),minInterval:1,name:'学生人数'},series:[{name:'本校学生职业目标',type:'bar',barMaxWidth:42,itemStyle:{borderRadius:[6,6,0,0],color:'#bd9c49'},data:goals.map(row=>row.count)}]});
 else noData(host('goals'),'暂未形成可展示的本校目标分组','达到最小样本量的分组才会展示，保护个人职业意向。');
}

export async function bindUniversityIntelligence(){
 const root=document.querySelector('#university-intelligence');if(!root||active?.root===root||!prepared)return;
 dispose();const controller={root,epoch:state.sessionEpoch,sequence:0,charts:[],timer:null,resize:null,mutations:null};active=controller;
 root.addEventListener('submit',event=>{if(event.target.id!=='university-intel-filter')return;event.preventDefault();selected={track:event.target.elements.track.value,city:event.target.elements.city.value};refresh(controller);});
 root.addEventListener('change',event=>{if(!event.target.closest('#university-intel-filter'))return;const form=event.target.form;selected={track:form.elements.track.value,city:form.elements.city.value};refresh(controller);});
 controller.resize=new ResizeObserver(()=>{if(stillCurrent(controller))controller.charts.forEach(instance=>instance.resize());});controller.resize.observe(root);
 controller.mutations=new MutationObserver(()=>{if(!root.isConnected&&active===controller)dispose();});controller.mutations.observe(root.parentElement,{childList:true});
 try{await paint(controller,prepared.data);}catch(error){if(stillCurrent(controller))root.querySelector('#university-intel-status').textContent=error.message;}
 schedule(controller);
}
on('university-intel-refresh',()=>active&&refresh(active));
