import {fuzzyScore} from './file-search.mjs';

export function fileReferences(text){
  return [...text.matchAll(/(?<![\p{L}\p{N}_@])@(?:"([^"\n]+)"|([^\s<>"`]+))/gu)].flatMap(m=>{
    const path=m[1]||m[2].replace(/[.,;:!?]+$/,'');
    if(!path||path.startsWith('/')||path.split('/').includes('..')||/[\\\x00-\x1f]/.test(path))return [];
    const raw=m[1]?m[0]:'@'+path;return [{path,from:m.index,to:m.index+raw.length,raw}];
  });
}
export function linkFileReferences(host){
  const walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('a,code,pre,button,.md-math')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
  const nodes=[];let n;while((n=walker.nextNode()))nodes.push(n);
  for(const node of nodes){const refs=fileReferences(node.data);if(!refs.length)continue;const fragment=document.createDocumentFragment();let at=0;
    for(const ref of refs){fragment.append(node.data.slice(at,ref.from));const link=document.createElement('a');link.dataset.fileReference=ref.path;link.href='#file-'+encodeURIComponent(ref.path);link.textContent=ref.raw;link.title='Open '+ref.path;fragment.append(link);at=ref.to;}fragment.append(node.data.slice(at));node.replaceWith(fragment);
  }
}
export function mountFileMentions({api,error}){
  let popup=null,field=null,query=null,results=[],index=0,request=0;
  function close(){request++;popup?.remove();popup=null;field?.removeAttribute('aria-controls');field?.removeAttribute('aria-activedescendant');field=null;}
  function choose(path){if(!field?.isConnected)return close();const target=field,selection=query;const value=/\s/.test(path)?'@"'+path+'"':'@'+path;target.setRangeText(value+' ',selection.from,selection.to,'end');close();target.focus();target.dispatchEvent(new Event('input',{bubbles:true}));}
  function render(){
    if(!popup||!field.isConnected)return close();popup.replaceChildren();
    results.forEach((path,i)=>{const b=document.createElement('button');b.type='button';b.id='file-mention-'+i;b.setAttribute('role','option');b.setAttribute('aria-selected',String(i===index));b.textContent=path;b.onpointerdown=e=>{e.preventDefault();choose(path);};popup.append(b);});
    if(!results.length)popup.textContent='No matching files';
    field.setAttribute('aria-activedescendant',results.length?'file-mention-'+index:'');
    const r=field.getBoundingClientRect();popup.style.width=Math.min(380,innerWidth-16)+'px';popup.style.left=Math.max(8,Math.min(r.left,innerWidth-popup.offsetWidth-8))+'px';popup.style.top=Math.max(8,Math.min(r.bottom+4,innerHeight-popup.offsetHeight-8))+'px';
    popup.querySelector('[aria-selected=true]')?.scrollIntoView({block:'nearest'});
  }
  document.addEventListener('input',async event=>{
    if(!event.target.matches('#comment-body,.reply-form textarea,#edit-comment-body'))return;
    const target=event.target,at=target.selectionStart,match=/(?:^|\s)@("[^"\n]*|[^\s@]*)$/.exec(target.value.slice(0,at));
    if(!match)return close();close();field=target;query={from:at-match[1].length-1,to:at};const current=++request;
    await new Promise(resolve=>setTimeout(resolve,120));if(current!==request)return;
    try{const data=await api('workspace');if(current!==request||!target.isConnected)return;
      const search=match[1].replace(/^"/,'');results=data.files.map(path=>({path,score:fuzzyScore(path,search)})).filter(r=>r.score!==null).sort((a,b)=>b.score-a.score||a.path.localeCompare(b.path)).slice(0,30).map(r=>r.path);index=0;
      popup=document.createElement('div');popup.id='file-mentions';popup.className='file-mentions';popup.setAttribute('role','listbox');popup.setAttribute('aria-label','File references');(target.closest('dialog')||document.body).append(popup);field.setAttribute('aria-controls',popup.id);render();
    }catch(e){if(current===request){close();error(e.message);}}
  });
  document.addEventListener('keydown',e=>{if(!popup||e.target!==field)return;if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();e.stopImmediatePropagation();index=(index+(e.key==='ArrowDown'?1:-1)+Math.max(results.length,1))%Math.max(results.length,1);render();}if(e.key==='Enter'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();e.stopImmediatePropagation();if(results[index])choose(results[index]);}if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close();}},true);
  document.addEventListener('pointerdown',e=>{if(popup&&!popup.contains(e.target)&&e.target!==field)close();});document.addEventListener('focusin',e=>{if(popup&&e.target!==field&&!popup.contains(e.target))close();});window.addEventListener('resize',close);
}
