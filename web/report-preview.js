// 独立预览使用真实地址；打印或取消均停留在报告，不跳转到空白页。
document.addEventListener('click',async event=>{
 const back=event.target.closest('[data-return-report]');
 if(back){if(window.opener&&!window.opener.closed){window.opener.focus();window.close();}else location.assign('/');return;}
 const print=event.target.closest('[data-print-report]');if(!print)return;
 const status=document.querySelector('[data-report-preview-status]');print.disabled=true;
 try{
  const results=await Promise.allSettled(Array.from(document.images,image=>image.decode()));
  if(results.some(result=>result.status==='rejected'))throw new Error('部分图表未加载，请返回后重新导出');
  await document.fonts.ready;window.print();if(status)status.textContent='打印完成或取消后，可点击“返回诊断报告”继续使用系统。';
 }catch(error){if(status)status.textContent='打印未完成：'+error.message;}
 finally{print.disabled=false;}
});
