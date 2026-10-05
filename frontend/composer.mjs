// Clipboard paste uses the native paste event: no clipboard permission prompt.
export function createComposers({token,api,onError}){
  const drafts=new Map(),limit=64*1024*1024;
  const key=form=>form.id==='comment-form'?'new':'reply:'+form.closest('.thread').dataset.thread;
  const forms=()=>document.querySelectorAll('#comment-form,.reply-form');
  function render(form){
    const draft=drafts.get(key(form)),files=draft?.files||[],host=form.querySelector('.pending-files');
    host.replaceChildren();host.hidden=!files.length;form.querySelector('textarea').required=!files.length;
    form.dataset.sending=draft?.sending?'true':'false';
    form.querySelectorAll('.attach-trigger,.attach-files,button[type=submit]').forEach(button=>button.disabled=!!draft?.sending);
    files.forEach((item,index)=>{
      const chip=document.createElement('div');chip.className='pending-file';
      if(item.url){const img=document.createElement('img');img.src=item.url;img.alt='';chip.append(img);}
      const name=document.createElement('button');name.type='button';name.textContent=item.name;name.title='Rename before sending';name.disabled=!!draft?.sending;
      name.onclick=()=>{const next=prompt('Attachment name',item.name);if(next===null)return;if(!next.trim()||next.length>255||/[\\/\x00-\x1f]/.test(next)){onError('Use a filename without slashes or control characters.');return;}item.name=next.trim();render(form);};
      const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Remove pending '+item.name);remove.disabled=!!draft?.sending;
      remove.onclick=()=>{if(item.url)URL.revokeObjectURL(item.url);files.splice(index,1);render(form);};chip.append(name,remove);host.append(chip);
    });
  }
  function clear(form){const id=key(form),draft=drafts.get(id);for(const item of draft?.files||[])if(item.url)URL.revokeObjectURL(item.url);drafts.delete(id);render(form);}
  function status(form,text,error=false){const field=form.querySelector('.composer-status');field.textContent=text;field.hidden=!text;field.classList.toggle('error',error);}
  function queue(form,files,clipboard=false){
    const id=key(form),draft=drafts.get(id)||{files:[],sending:false};
    if(draft.sending)throw new Error('Wait for this comment to finish sending.');
    if(draft.files.length+files.length>16)throw new Error('Attach at most 16 files per comment.');
    if([...draft.files.map(item=>item.file),...files].reduce((n,file)=>n+file.size,0)>limit)throw new Error('Attachments in one comment are limited to 64 MiB.');
    for(const [index,file] of files.entries()){
      const extension=({'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/gif':'gif'})[file.type]||'png';
      draft.files.push({file,name:clipboard?`screenshot-${Date.now()}-${index+1}.${extension}`:file.name,url:file.type.startsWith('image/')?URL.createObjectURL(file):null});
    }
    drafts.set(id,draft);render(form);status(form,'');
  }
  function setSending(form,value){const id=key(form),draft=drafts.get(id)||{files:[]};draft.sending=value;drafts.set(id,draft);for(const current of forms())if(key(current)===id)render(current);if(!value&&!draft.files.length)drafts.delete(id);}
  async function post(route,data,form){
    const files=drafts.get(key(form))?.files||[];
    if(!files.length)return api(route,'POST',data);
    const body=new FormData();body.append('data',JSON.stringify(data));for(const item of files)body.append('files',item.file,item.name);
    const result=await fetch('/api/'+route,{method:'POST',headers:{'X-Looking-Glass-Token':token},body});
    const payload=await result.json();if(!result.ok){const error=new Error(payload.error||'Unable to send attachments');error.status=result.status;throw error;}return payload;
  }
  function receive(form,files,clipboard=false){try{queue(form,files,clipboard);}catch(error){status(form,error.message,true);onError(error.message);}}
  document.addEventListener('click',event=>{const button=event.target.closest('.attach-trigger');if(button){event.preventDefault();button.closest('form').querySelector('.attach-files').click();}});
  document.addEventListener('change',event=>{if(event.target.matches('.attach-files')){const input=event.target;receive(input.closest('form'),[...input.files]);input.value='';}});
  document.addEventListener('paste',event=>{
    const form=event.target.closest?.('#comment-form,.reply-form');if(!form||!event.target.matches('textarea'))return;
    const files=[...(event.clipboardData?.items||[])].filter(item=>item.kind==='file'&&item.type.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean);
    if(files.length){event.preventDefault();receive(form,files,true);}
  });
  document.addEventListener('keydown',event=>{if(event.target.matches('.reply-form textarea')&&(event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();event.target.closest('form').requestSubmit();}});
  function prune(ids){for(const [id,draft] of drafts)if(id.startsWith('reply:')&&!ids.has(Number(id.slice(6)))){for(const item of draft.files)if(item.url)URL.revokeObjectURL(item.url);drafts.delete(id);}}
  return {render,clear,status,setSending,post,prune,hasPending:()=>[...drafts.values()].some(d=>d.files.length),isSending:form=>!!drafts.get(key(form))?.sending};
}
