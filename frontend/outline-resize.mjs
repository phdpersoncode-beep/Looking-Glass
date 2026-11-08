export function mountOutlineResize(host,{storageKey,changed=()=>{}}){
  const handle=document.createElement('div');handle.className='outline-resize';handle.tabIndex=0;
  for(const [name,value] of Object.entries({role:'separator','aria-label':'Resize Python outline','aria-orientation':'vertical','aria-controls':host.id}))handle.setAttribute(name,value);
  handle.title='Drag to resize outline · double-click to reset';host.append(handle);
  let width=Number(localStorage.getItem(storageKey))||190,drag=null;
  const limits=()=>({min:140,max:Math.max(140,Math.min(600,host.parentElement.clientWidth*(innerWidth<=1100?.8:1)-(innerWidth<=1100?0:260)))});
  function size(){const {min,max}=limits(),value=Math.round(Math.max(min,Math.min(max,width)));host.parentElement.style.setProperty('--outline-width',value+'px');handle.setAttribute('aria-valuemin',min);handle.setAttribute('aria-valuemax',Math.floor(max));handle.setAttribute('aria-valuenow',value);changed();}
  const save=()=>localStorage.setItem(storageKey,String(width));
  function finish(cancel=false){if(!drag)return;if(cancel)width=drag.width;drag=null;document.body.classList.remove('outline-resizing');size();save();}
  handle.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();e.stopPropagation();handle.focus({preventScroll:true});drag={x:e.clientX,width:host.getBoundingClientRect().width};handle.setPointerCapture(e.pointerId);document.body.classList.add('outline-resizing');};
  handle.onpointermove=e=>{if(!drag)return;const {min,max}=limits();width=Math.max(min,Math.min(max,drag.width+drag.x-e.clientX));size();};
  handle.onpointerup=()=>finish();handle.onpointercancel=()=>finish(true);handle.onlostpointercapture=()=>finish();
  handle.onkeydown=e=>{if(e.key==='Escape'&&drag){e.preventDefault();e.stopPropagation();finish(true);return;}if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();e.stopPropagation();const {min,max}=limits();width=e.key==='Home'?min:e.key==='End'?max:Math.max(min,Math.min(max,Number(handle.getAttribute('aria-valuenow'))+(e.key==='ArrowLeft'?20:-20)));size();save();};
  handle.ondblclick=()=>{width=190;size();save();};
  window.addEventListener('resize',size);new ResizeObserver(size).observe(host.parentElement);host.addEventListener('toggle',size);size();
}
