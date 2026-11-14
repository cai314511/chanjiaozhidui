import {e,toast} from './core.js';

// 导出只复制当前已展示的快照与情景，不发起重算。
export function exportUniversityReport(controller){
 const {root,data,scenario}=controller;
 const copy=root.cloneNode(true);
 copy.querySelectorAll('[data-action],.report-chart-switch,.report-school-code').forEach(node=>node.remove());
 copy.querySelectorAll('[data-report-scenario]').forEach(node=>{if(node.dataset.reportScenario!==scenario)node.remove();});
 copy.querySelectorAll('details').forEach(node=>node.open=true);
 copy.querySelectorAll('[data-report-chart]').forEach(host=>{
  const original=root.querySelector(`[data-report-chart="${host.dataset.reportChart}"]`);
  const chart=controller.library?.getInstanceByDom(original);
  if(!chart)return;
  const image=document.createElement('img');
  image.className='report-static-chart';image.alt=original.getAttribute('aria-label')||'报告图表';
  image.src=chart.getDataURL({type:'png',pixelRatio:2,backgroundColor:'#ffffff'});
  host.replaceChildren(image);host.style.height='auto';
 });
 let styles='';
 for(const sheet of document.styleSheets){
  try{styles+=Array.from(sheet.cssRules,rule=>rule.cssText).join('\n');}catch{/* 跨源样式不参与独立报告。 */}
 }
 const values=value=>value==null?'待补充':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:3});
 const resources=`<section class="report-panel report-export-resources"><h3>资源投入明细</h3><table><thead><tr><th>资源</th><th>当前</th><th>方案</th><th>上限</th></tr></thead><tbody>${data.resources.map(row=>`<tr><td>${e(row.label)}</td><td>${values(row.before)} ${e(row.unit)}</td><td>${values(row.after)} ${e(row.unit)}</td><td>${values(row.limit)} ${e(row.unit)}</td></tr>`).join('')}</tbody></table></section>`;
 const printStyles=`
 html,body{height:auto!important;overflow:visible!important;background:white!important;color:#254e44}body{display:block!important;margin:0!important;padding:24px!important;font-family:'Microsoft YaHei',sans-serif}.report-export-shell{max-width:1120px;margin:auto}.report-export-toolbar{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:16px 0 24px;font-size:16px}.report-export-toolbar button,.report-export-toolbar a{font:inherit;cursor:pointer;padding:10px 18px;border:1px solid #217d70;border-radius:8px;background:white;color:#217d70}.report-static-chart{display:block;width:100%;height:auto}.report-chart{min-height:0!important}.report-metric,.report-panel,.report-action{break-inside:avoid;backdrop-filter:none!important}.report-export-resources table{width:100%}.report-executive{break-inside:avoid}.report-export-meta{font-size:14px}.report-method{overflow-wrap:anywhere}
 body::before,body::after{display:none!important}.report-chart{height:auto!important}
 @media print{@page{size:A4;margin:12mm}body{padding:0!important}.report-export-toolbar{display:none!important}.report-hero{grid-template-columns:1fr!important;padding:18px!important}.report-cycle{display:none!important}.report-metrics{grid-template-columns:repeat(2,minmax(0,1fr))!important}.report-chart-grid{display:block!important}.report-chart-grid .report-panel{margin-bottom:14px!important}.report-panel{box-shadow:none!important}.report-section-title{break-after:avoid;page-break-after:avoid}.report-section-title+*{break-before:avoid;page-break-before:avoid}.report-metrics,.report-actions{display:block!important}.report-metric,.report-action{margin-bottom:12px!important}.report-static-chart{max-height:100mm;object-fit:contain}.report-source-strip{margin-bottom:12px!important}.report-version{break-inside:avoid}a{color:inherit!important}.table-wrap{overflow:visible!important}table{width:100%!important}.report-export-shell{max-width:none!important}}
 `;
 const html=`<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${e(data.source.title||'高校培养诊断报告')} · ${e(scenario)}情景</title><style>${styles}${printStyles}</style></head><body><main class="report-export-shell"><div class="report-export-toolbar"><button type="button" data-print-report>打印 / 另存为 PDF</button><a data-save-report download="高校培养诊断_${e(scenario)}.html">保存独立 HTML</a></div><p class="report-export-meta" data-export-scenario="${e(scenario)}">已固定 ${e(scenario)}情景 · 导出时点 ${e(new Date().toLocaleString('zh-CN'))}</p>${copy.outerHTML}${resources}<details><summary>测算记录标识</summary><p>${e(data.source.run_id||data.source.optimization_id||'尚未测算')}</p></details></main><script>document.querySelector('[data-print-report]').onclick=async()=>{await Promise.all(Array.from(document.images,image=>image.decode()));await document.fonts.ready;window.print();};document.querySelector('[data-save-report]').onclick=function(){this.href=URL.createObjectURL(new Blob(['<!doctype html>'+document.documentElement.outerHTML],{type:'text/html;charset=utf-8'}));};</script></body></html>`;
 const target=window.open('','_blank');
 if(!target){toast('请允许本页打开报告打印窗口，再点击导出。');return;}
 const preview=new DOMParser().parseFromString(html,'text/html');
 preview.querySelectorAll('style,script').forEach(node=>node.remove());
 target.opener=null;target.document.open();target.document.write('<!doctype html>'+preview.documentElement.outerHTML);target.document.close();
 // 打印窗口继承站点 CSP；使用浏览器 CSSOM 与事件绑定保持同一安全策略。
 const sheet=new target.CSSStyleSheet();sheet.replaceSync(styles+printStyles);target.document.adoptedStyleSheets=[sheet];
 target.document.querySelector('[data-save-report]').href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));
 target.document.querySelector('[data-print-report]').onclick=async()=>{
  await Promise.all(Array.from(target.document.images,image=>image.decode()));
  await target.document.fonts.ready;target.print();
 };
}
