import {confirmAction,requestText} from './dialogs.mjs';

export function mountExplorer(host,{root,api,change,error}){
  let menu=null,drag=null,hovered=null,hoverTimer=null;
  const close=()=>{menu?.remove();menu=null;};
  const run=fn=>(...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>error(e.message));
  const selected=target=>{const file=target.closest('.file-entry'),folder=target.closest('.file-folder>summary');return file?file.dataset.path:folder?.parentElement.dataset.directory;};
  async function mutate(path,options){const info=await api('explorer?'+new URLSearchParams({path}));await change(info,options);}
  host.addEventListener('contextmenu',event=>{
    const path=selected(event.target);if(!path)return;event.preventDefault();close();
    menu=document.createElement('div');menu.className='explorer-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','File actions');
    for(const [label,action] of [
      ['Rename',()=>requestText({title:'Rename file or folder',value:path.split('/').pop(),onSubmit:async name=>{if(!name||/[\\/]/.test(name))throw new Error('Use a name without slashes.');await mutate(path,{destination:path.split('/').slice(0,-1).concat(name).join('/')});}})],
      ['Delete',async()=>{if(await confirmAction({title:'Delete file or folder?',message:path+' will be moved to the workspace trash. Discussions and review history are retained.',confirmLabel:'Delete',symbol:'trash',danger:true}))await mutate(path,{delete:true});}],
      ['Copy relative path',()=>navigator.clipboard.writeText(path)],
      ['Copy absolute path',()=>navigator.clipboard.writeText(root.replace(/\/$/,'')+'/'+path)]
    ]){const b=document.createElement('button');b.type='button';b.setAttribute('role','menuitem');b.textContent=label;b.onclick=run(()=>{close();return action();});menu.append(b);}
    document.body.append(menu);menu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-menu.offsetWidth-8))+'px';menu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))+'px';menu.firstChild.focus();
    menu.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close();}if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const items=[...menu.children],at=items.indexOf(document.activeElement);items[(at+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}};
  });
  document.addEventListener('pointerdown',e=>{if(menu&&!menu.contains(e.target))close();});window.addEventListener('resize',close);
  host.addEventListener('dragstart',e=>{drag=selected(e.target);if(!drag)return;e.dataTransfer.setData('application/x-looking-glass-path',drag);e.dataTransfer.effectAllowed='move';close();});
  const destination=target=>target.closest('.file-folder>summary')?.parentElement.dataset.directory||target.closest('.file-entry')?.dataset.path.split('/').slice(0,-1).join('/')||target.closest('.file-folder')?.dataset.directory||'';
  host.addEventListener('dragover',e=>{if(!drag)return;e.preventDefault();const folder=e.target.closest('.file-folder>summary');if(folder!==hovered){clearTimeout(hoverTimer);hovered=folder;if(folder&&!folder.parentElement.open)hoverTimer=setTimeout(()=>{if(drag&&folder.isConnected&&!folder.parentElement.open)folder.click();},650);}e.dataTransfer.dropEffect='move';host.querySelectorAll('.drop-target').forEach(el=>el.classList.remove('drop-target'));(e.target.closest('.file-folder>summary,.file-entry')||host).classList.add('drop-target');});
  const clear=()=>{clearTimeout(hoverTimer);hovered=null;host.classList.remove('drop-target');host.querySelectorAll('.drop-target').forEach(el=>el.classList.remove('drop-target'));drag=null;};
  host.addEventListener('dragend',clear);
  host.addEventListener('drop',e=>{if(!drag)return;e.preventDefault();const path=drag,folder=destination(e.target),target=(folder?folder+'/':'')+path.split('/').pop();clear();if(path!==target)run(()=>mutate(path,{destination:target}))();});
}
