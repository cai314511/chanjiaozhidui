import {e} from './core.js';

export function companyBrand(company){
 const image=company.logo_status==='verified'&&/^\/api\/company-logos\/[a-f0-9]{24}$/.test(company.logo_url||'');
 return `<div class="company-symbol${image?' has-logo':''}" data-company-brand="${e(company.id)}"><span class="company-initial" ${image?'hidden':''}>${e(company.name.slice(0,1))}</span>${image?`<img src="${e(company.logo_url)}" alt="${e(company.name)} Logo" loading="lazy" decoding="async">`:''}</div>`;
}
export function bindCompanyBrands(root){
 root.querySelectorAll('.company-symbol img').forEach(img=>{
  const fallback=()=>{img.hidden=true;img.closest('.company-symbol').classList.remove('has-logo');img.previousElementSibling.hidden=false};
  img.addEventListener('error',fallback,{once:true});if(img.complete&&!img.naturalWidth)fallback();
 });
}
