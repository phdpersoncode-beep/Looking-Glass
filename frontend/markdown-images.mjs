import {loadImage} from './image-loading.mjs';
import {imageCaption} from './image-size.mjs';
import {iconButton} from './icons.mjs';
import {confirmAction,requestText} from './dialogs.mjs';
import {markdown} from './markdown-math.mjs';
import {tokenPositions} from './markdown-source.mjs';

export const imageID = source => /^[a-z][\w+.-]*:/i.test(source||'') ? null : source?.match(/(?:^|\/)\.looking-glass\/images\/([a-f0-9]{64})_/i)?.[1] || null;
// Resolve the encoded URL before decoding filename delimiters such as # and ?.
export const imagePath=(source,documentPath)=>decodeURIComponent(new URL(source,'https://workspace/'+documentPath).pathname).slice(1);
export const imageLink = image => `.looking-glass/images/${image.id}_${encodeURIComponent(image.name)}`;
let lastImageSource=null,lastImageRanges=[];
export function imageRanges(source) {
  if(source===lastImageSource)return lastImageRanges;
  const tokens=markdown.lexer(source),positions=tokenPositions(tokens,source),ranges=[];
  markdown.walkTokens(tokens,token=>{if(['image','wikiImage'].includes(token.type)){const p=positions.get(token);if(p)ranges.push({...p,href:token.href,alt:token.text||''});}});
  lastImageSource=source;lastImageRanges=ranges;return ranges;
}
const symbols={'Red pen':'pen',Eraser:'eraser',Comment:'comment',Undo:'undo',Redo:'redo','Save image':'check','Restore original':'restore',Close:'close',Reply:'send','Add comment':'send',Cancel:'close'};
const button=(label,action)=>iconButton(label,symbols[label]||'comment',action);

export function createImageTools({token,api,context,comment,focus,error,changed,renamed,remove,move,resized,editSource,removeComment}) {
  const references=new Map();
  async function request(route,method='GET',data) {
    const response=await fetch('/api/'+route,{method,headers:{'X-Looking-Glass-Token':token},body:data});
    if(!response.ok)throw new Error((await response.json()).error);
    return response;
  }
  const run=fn=>(...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>error(e.message));
  async function upload(file) {const form=new FormData();form.append('file',file,file.name||'screenshot.png');return (await request('images','POST',form)).json();}
  async function load(id,original=false){return URL.createObjectURL(await (await request(`images/${id}/content${original?'?original=1':''}`)).blob());}
  async function rename(id,reference){
    if(reference)references.set(id,reference);const meta=await api('images/'+id);
    await requestText({title:'Rename image',value:meta.name,onSubmit:async name=>{
      const saved=await api('images/'+id,'PATCH',{version:meta.version,name});renamed?.(id,references.get(id),saved);changed(id);
    }});
  }
  async function editor(id) {
    let meta=await api('images/'+id),current=await load(id),original=await load(id,true);
    const dialog=document.createElement('dialog');dialog.className='image-editor';dialog.setAttribute('aria-label','Annotate image');
    const toolbar=document.createElement('div');toolbar.className='image-toolbar';
    const workspace=document.createElement('div');workspace.className='image-editor-workspace';
    const viewport=document.createElement('div');viewport.className='image-editor-viewport';
    const stage=document.createElement('div');stage.className='image-stage';viewport.append(stage);
    const comments=document.createElement('div');comments.className='image-comments';comments.hidden=true;workspace.append(viewport,comments);
    const base=new Image(),originalImage=new Image(),canvas=document.createElement('canvas'),ink=document.createElement('canvas'),ctx=ink.getContext('2d');
    await Promise.all([loadImage(base,current),loadImage(originalImage,original)]);canvas.width=ink.width=base.naturalWidth;canvas.height=ink.height=base.naturalHeight;
    if(canvas.width*canvas.height>40000000){URL.revokeObjectURL(current);URL.revokeObjectURL(original);throw new Error('Image is too large to annotate (40 megapixels maximum).');}
    ctx.drawImage(base,0,0);stage.append(canvas);const status=document.createElement('p');status.setAttribute('role','status');
    let lastErase=null,tool='pen',drawing=false,history=[ctx.getImageData(0,0,ink.width,ink.height)],at=0,dirty=false,busy=false;
    function draw(){const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.drawImage(ink,0,0);}
    function buttons(){undo.disabled=at===0;redo.disabled=at===history.length-1;pen.setAttribute('aria-pressed',String(tool==='pen'));eraser.setAttribute('aria-pressed',String(tool==='eraser'));note.setAttribute('aria-pressed',String(tool==='comment'));}
    function snapshot(){history=history.slice(0,at+1);history.push(ctx.getImageData(0,0,ink.width,ink.height));if(history.length>Math.max(2,Math.min(20,Math.floor(64000000/(ink.width*ink.height*4)))))history.shift();at=history.length-1;dirty=true;buttons();}
    const pen=button('Red pen',()=>{tool='pen';buttons();}),eraser=button('Eraser',()=>{tool='eraser';buttons();}),note=button('Comment',()=>{tool='comment';buttons();});
    const undo=button('Undo',()=>{if(at){ctx.putImageData(history[--at],0,0);dirty=true;draw();buttons();}}),redo=button('Redo',()=>{if(at<history.length-1){ctx.putImageData(history[++at],0,0);dirty=true;draw();buttons();}});
    const close=run(async()=>{if(!busy&&(!dirty||await confirmAction({title:'Discard annotations?',message:'Your unsaved drawing changes will be discarded.',confirmLabel:'Discard annotations',symbol:'trash',danger:true})))dialog.close();});
    const save=button('Save image',run(async()=>{
      if(busy)return;busy=true;save.disabled=true;
      try{const blob=await new Promise(resolve=>canvas.toBlob(resolve,meta.media_type,.95));if(!blob)throw new Error('Unable to encode image.');const form=new FormData();form.append('file',blob,meta.name);form.append('version',meta.version);meta=await (await request('images/'+id,'PATCH',form)).json();dirty=false;changed(id);dialog.close();}catch(e){status.textContent=e.message;throw e;}finally{busy=false;save.disabled=false;}
    }));
    const restore=button('Restore original',run(async()=>{if(busy)return;busy=true;restore.disabled=true;try{if(!await confirmAction({title:'Restore original image?',message:'Drawing changes will be removed. Comments will be retained.',confirmLabel:'Restore original',symbol:'restore'}))return;meta=await api('images/'+id,'PATCH',{version:meta.version,restore:true});dirty=false;changed(id);dialog.close();}catch(e){status.textContent=e.message;}finally{busy=false;restore.disabled=false;}}));
    toolbar.append(pen,eraser,undo,redo,note,save,restore,button('Close',close));dialog.append(toolbar,workspace,status);document.body.append(dialog);dialog.showModal();draw();buttons();
    const fit=()=>{const scale=Math.min(1,Math.max(1,viewport.clientWidth-48)/canvas.width,Math.max(1,viewport.clientHeight-48)/canvas.height);canvas.style.width=(canvas.width*scale)+'px';canvas.style.height=(canvas.height*scale)+'px';};
    const resize=new ResizeObserver(fit);resize.observe(viewport);fit();
    const point=e=>{const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};};
    function erase(p){
      const x=p.x*canvas.width,y=p.y*canvas.height,previous=lastErase||{x,y},radius=ctx.lineWidth/2;
      const steps=Math.max(1,Math.ceil(Math.hypot(x-previous.x,y-previous.y)/Math.max(1,radius/2)));
      ctx.save();ctx.beginPath();
      for(let i=0;i<=steps;i++){const px=previous.x+(x-previous.x)*i/steps,py=previous.y+(y-previous.y)*i/steps;ctx.moveTo(px+radius,py);ctx.arc(px,py,radius,0,Math.PI*2);}
      ctx.clip();ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(originalImage,0,0,canvas.width,canvas.height);ctx.restore();ctx.beginPath();ctx.moveTo(x,y);lastErase={x,y};
    }
    canvas.onpointerdown=e=>{
      if(e.button!==0||busy)return;e.preventDefault();const p=point(e);
      if(tool==='comment'){commentBox(stage,id,p,dialog);return;}
      drawing=true;lastErase=null;canvas.setPointerCapture(e.pointerId);ctx.globalCompositeOperation='source-over';ctx.strokeStyle='#e32636';ctx.lineWidth=(tool==='eraser'?20:3)*canvas.width/canvas.getBoundingClientRect().width;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(p.x*canvas.width,p.y*canvas.height);ctx.lineTo(p.x*canvas.width+.01,p.y*canvas.height);if(tool==='eraser')erase(p);else ctx.stroke();draw();
    };
    canvas.onpointermove=e=>{if(!drawing)return;const p=point(e);ctx.lineTo(p.x*canvas.width,p.y*canvas.height);if(tool==='eraser')erase(p);else ctx.stroke();draw();};
    canvas.onpointerup=()=>{if(drawing){drawing=false;snapshot();}};canvas.onpointercancel=canvas.onpointerup;
    dialog.oncancel=e=>{e.preventDefault();close();};dialog.onclose=()=>{resize.disconnect();URL.revokeObjectURL(current);URL.revokeObjectURL(original);dialog.remove();};
    markers(stage,id,dialog);
  }
  function commentBox(host,id,p,dialog=null,thread=null){
    const panel=dialog?.querySelector('.image-comments')||host;
    panel.querySelector('.image-comment-box')?.remove();panel.hidden=false;
    const box=document.createElement('form');box.className='image-comment-box';box.noValidate=true;box.setAttribute('aria-label',thread?'Image thread':'Image comment');
    const text=document.createElement('textarea');text.placeholder=thread?'Reply to image thread':'Comment on image';text.setAttribute('aria-label',text.placeholder);text.required=true;text.title='Ctrl+Enter / ⌘+Enter to send';
    const feedback=document.createElement('p');feedback.setAttribute('role','alert');
    let busy=false;
    const dismiss=()=>{if(busy)return;box.remove();if(dialog)panel.hidden=true;};
    const setBusy=value=>{busy=value;text.readOnly=value;box.querySelectorAll('button').forEach(b=>b.disabled=value);};
    const submit=button(thread?'Reply':'Add comment');submit.type='submit';
    const cancel=button('Cancel',dismiss),actions=document.createElement('div');actions.className='dialog-actions';actions.append(cancel,submit);
    const messages=document.createElement('div');messages.className='image-comment-messages';
    async function erase(message=null){
      if(busy)return;setBusy(true);feedback.textContent='';
      try{
        const whole=!message,last=thread.messages.length===1;
        if(!await confirmAction({title:whole?'Delete image thread?':'Delete image comment?',message:whole?'This thread and all its comments will be deleted.':last?'This comment and its image marker will be removed.':'This comment will be deleted. The other comments will be kept.',confirmLabel:whole?'Delete thread':'Delete comment',symbol:'trash',danger:true}))return;
        const remaining=await removeComment(thread.id,message?.id);
        setBusy(false);
        if(remaining){thread=remaining;renderMessages();}else dismiss();
        markers(host,id,dialog);
      }catch(e){feedback.textContent=e.message;}
      finally{setBusy(false);}
    }
    function renderMessages(){
      messages.replaceChildren();if(!thread)return;
      if(thread.messages.length>1){const heading=document.createElement('div');heading.className='image-comment-heading';const label=document.createElement('span');label.textContent='Thread #'+thread.id;heading.append(label,iconButton('Delete image thread','trash',()=>erase()));messages.append(heading);}
      for(const message of thread.messages){
        const row=document.createElement('div');row.className='image-comment-message';row.dataset.message=message.id;
        const heading=document.createElement('div');heading.className='image-comment-heading';const author=document.createElement('strong');author.textContent=message.author;
        const body=document.createElement('p');body.textContent=message.body;
        heading.append(author,iconButton('Delete image comment','trash',()=>erase(message)));row.append(heading,body);messages.append(row);
      }
    }
    renderMessages();if(thread)box.append(messages);
    box.onsubmit=async event=>{
      event.preventDefault();if(busy)return;if(!text.value.trim()){feedback.textContent='Write a comment before sending.';text.focus();return;}setBusy(true);feedback.textContent='';
      try{await comment(id,p,text.value,thread);setBusy(false);dismiss();markers(host,id,dialog);}
      catch(e){feedback.textContent=e.message;}
      finally{setBusy(false);}
    };
    text.onkeydown=event=>{
      if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!event.isComposing){event.preventDefault();event.stopPropagation();box.requestSubmit();}
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();dismiss();}
    };
    box.append(text,feedback,actions);panel.append(box);text.focus();
  }
  function markers(host,id,dialog=null){
    const threads=context().threads.filter(t=>t.image_annotation?.image_id===id&&t.anchor_status==='attached');
    const existing=new Map([...host.querySelectorAll(':scope > .image-comment-marker')].map(b=>[Number(b.dataset.thread),b]));
    for(const thread of threads){
      let b=existing.get(thread.id);existing.delete(thread.id);
      if(!b){
        b=button('Image thread #'+thread.id);b.className='image-comment-marker';b.dataset.thread=thread.id;b.title='Image thread #'+thread.id+' · Ctrl+click to move';
        let drag=null,ignoreClick=false;
        const place=p=>{b.style.left=(p.x*100)+'%';b.style.top=(p.y*100)+'%';};
        const mode=enabled=>{b.classList.toggle('drag-mode',enabled);b.setAttribute('aria-pressed',String(enabled));};mode(false);
        b.onclick=event=>{
          event.stopPropagation();if(ignoreClick){ignoreClick=false;return;}
          if(event.ctrlKey){mode(!b.classList.contains('drag-mode'));return;}
          if(b.classList.contains('drag-mode'))return;
          commentBox(host,id,b._thread.image_annotation,dialog,b._thread);if(!dialog)focus(b._thread.id);
        };
        b.onpointerdown=event=>{
          if(event.button!==0||!b.classList.contains('drag-mode')||b._moving)return;
          event.preventDefault();event.stopPropagation();const rect=host.getBoundingClientRect();
          drag={x:event.clientX,y:event.clientY,rect,point:{...b._thread.image_annotation},thread:b._thread};b._dragging=true;ignoreClick=false;b.setPointerCapture(event.pointerId);
        };
        b.onpointermove=event=>{
          if(!drag)return;
          drag.next={x:Math.max(0,Math.min(1,drag.point.x+(event.clientX-drag.x)/drag.rect.width)),y:Math.max(0,Math.min(1,drag.point.y+(event.clientY-drag.y)/drag.rect.height))};place(drag.next);
        };
        const finish=(event,cancel=false)=>{
          if(!drag)return;const current=drag;drag=null;b._dragging=false;
          const moved=Math.hypot(event.clientX-current.x,event.clientY-current.y)>2;
          ignoreClick=moved;if(cancel||moved)mode(false);
          if(cancel||!moved||!current.next){place(current.point);return;}
          b._moving=true;
          run(async()=>{try{await move(id,current.thread,current.next);}catch(e){place(current.point);throw e;}finally{b._moving=false;markers(host,id,dialog);}})();
        };
        b.onpointerup=event=>finish(event);b.onpointercancel=event=>finish(event,true);
        b.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();if(drag){place(drag.point);drag=null;b._dragging=false;ignoreClick=true;}mode(false);}};
        host.append(b);
      }
      b._thread=thread;b.classList.toggle('resolved',thread.resolved);
      if(!b._dragging&&!b._moving){const p=thread.image_annotation;b.style.left=(p.x*100)+'%';b.style.top=(p.y*100)+'%';}
    }
    for(const b of existing.values())b.remove();
  }
  function resizeHandle(wrap,img){
    const handle=iconButton('Resize image','resize');handle.classList.add('image-resize');handle.setAttribute('role','slider');handle.setAttribute('aria-valuemin','40');handle.setAttribute('aria-valuemax','4000');
    let drag=null;
    const setWidth=width=>{width=Math.round(Math.max(40,Math.min(4000,width)));wrap.style.width=width+'px';handle.setAttribute('aria-valuenow',width);return width;};
    const revert=()=>{wrap.style.width=drag.original;drag=null;};
    handle.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();drag={x:event.clientX,width:wrap.getBoundingClientRect().width,original:wrap.style.width};handle.setPointerCapture(event.pointerId);};
    handle.onpointermove=event=>{if(drag)drag.next=setWidth(drag.width+2*(event.clientX-drag.x));};
    handle.onpointerup=()=>{if(!drag)return;const current=drag;if(!current.next||Math.abs(current.next-current.width)<2){revert();return;}drag=null;run(async()=>{try{await resized(wrap,current.next);}catch(e){wrap.style.width=current.original;throw e;}})();};
    handle.onpointercancel=()=>{if(drag)revert();};
    handle.onkeydown=event=>{
      if(event.key==='Escape'&&drag){event.preventDefault();event.stopPropagation();revert();}
      if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();event.stopPropagation();const width=setWidth(wrap.getBoundingClientRect().width+(event.key==='ArrowRight'?10:-10));run(()=>resized(wrap,width))();}
    };
    img.addEventListener('load',()=>handle.setAttribute('aria-valuenow',Math.round(wrap.getBoundingClientRect().width)),{once:true});
    wrap.append(handle);
  }
  function mount(img){
    if(img.closest('.markdown-image'))return;
    const src=img.getAttribute('src'),owner=context();owner.readonly||=!!img.closest('.comment-markdown');let id=imageID(src);
    // Reserve layout while the replacement image request loads.
    const wrap=document.createElement('span');wrap.className='markdown-image';wrap.style.visibility='hidden';if(owner.readonly)wrap.dataset.imageReadonly='';img._displayCaption??=img.alt;const caption=imageCaption(img._displayCaption);if(caption.width)wrap.style.width=caption.width+'px';img.alt=caption.alt;img.draggable=false;img.replaceWith(wrap);const pixels=document.createElement('span');pixels.className='image-pixels';pixels.append(img);wrap.append(pixels);
    let url;const dispose=()=>{if(url)URL.revokeObjectURL(url);};
    const observer=new MutationObserver(()=>{if(!wrap.isConnected){dispose();observer.disconnect();}});queueMicrotask(()=>observer.observe(document.body,{childList:true,subtree:true}));
    run(async()=>{
      if(!id&&/\.(?:png|jpe?g)$/i.test(src||'')&&!/^(?:https?:|data:|blob:|\/)/i.test(src||'')){
        const path=imagePath(src,owner.path);
        const meta=await api('images/import','POST',{path});id=meta.id;
      }
      if(id){references.set(id,src);url=await load(id);await loadImage(img,url);wrap.style.visibility='';wrap.dataset.imageId=id;
        if(owner.readonly)return;
        const controls=document.createElement('span');controls.className='image-actions';
        const pencil=iconButton('Annotate image','pen',run(()=>editor(id)));pencil.classList.add('image-pencil');
        const trash=iconButton('Delete image','trash',run(()=>remove(wrap)));trash.classList.add('image-delete');controls.append(pencil,trash);if(owner.mode==='live'){const source=iconButton('Edit image source','code',()=>editSource(wrap));controls.append(source);}wrap.append(controls);wrap.oncontextmenu=e=>{e.preventDefault();run(()=>rename(id))();};markers(pixels,id);
      }else if(!/^(?:https?:|data:|blob:|\/)/i.test(src||'')){
        const path=imagePath(src,owner.path);
        url=URL.createObjectURL(await (await request('binary?'+new URLSearchParams({path}))).blob());await loadImage(img,url);
      }
      wrap.style.visibility='';
      if(!owner.readonly){
        resizeHandle(wrap,img);
        if(owner.mode==='live'&&!wrap.querySelector('.image-actions')){const controls=document.createElement('span');controls.className='image-actions';controls.append(iconButton('Edit image source','code',()=>editSource(wrap)));wrap.append(controls);}
      }
      if(!wrap.isConnected)dispose();
    })();
  }
  function refresh(id){for(const wrap of document.querySelectorAll('.markdown-image[data-image-id]:not([data-image-readonly])')){if(!id||wrap.dataset.imageId===id){markers(wrap.querySelector('.image-pixels'),wrap.dataset.imageId);if(id){const img=wrap.querySelector('img');wrap.replaceWith(img);img.setAttribute('src',references.get(id)||`.looking-glass/images/${id}_image.png`);mount(img);}}}}
  return {upload,mount,refresh,rename,editor,reference:id=>references.get(id)};
}
