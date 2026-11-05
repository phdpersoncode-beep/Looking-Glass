import {markdown} from './markdown-math.mjs';
import {tokenPositions} from './markdown-source.mjs';

export const imageID = source => /^[a-z][\w+.-]*:/i.test(source||'') ? null : source?.match(/(?:^|\/)\.looking-glass\/images\/([a-f0-9]{64})_/i)?.[1] || null;
export const imageLink = image => `.looking-glass/images/${image.id}_${encodeURIComponent(image.name)}`;
let lastImageSource=null,lastImageRanges=[];
export function imageRanges(source) {
  if(source===lastImageSource)return lastImageRanges;
  const tokens=markdown.lexer(source),positions=tokenPositions(tokens,source),ranges=[];
  markdown.walkTokens(tokens,token=>{if(['image','wikiImage'].includes(token.type)){const p=positions.get(token);if(p)ranges.push({...p,href:token.href,alt:token.text||''});}});
  lastImageSource=source;lastImageRanges=ranges;return ranges;
}
const button=(label,action)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-label',label);b.onclick=action;return b;};

export function createImageTools({token,api,context,comment,focus,error,changed,renamed}) {
  const references=new Map();
  async function request(route,method='GET',data) {
    const response=await fetch('/api/'+route,{method,headers:{'X-Looking-Glass-Token':token},body:data});
    if(!response.ok)throw new Error((await response.json()).error);
    return response;
  }
  const run=fn=>(...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>error(e.message));
  async function upload(file) {const form=new FormData();form.append('file',file,file.name||'screenshot.png');return (await request('images','POST',form)).json();}
  async function load(id,original=false){return URL.createObjectURL(await (await request(`images/${id}/content${original?'?original=1':''}`)).blob());}
  async function rename(id,reference){if(reference)references.set(id,reference);const meta=await api('images/'+id),name=prompt('Rename image',meta.name);if(name===null)return;const saved=await api('images/'+id,'PATCH',{version:meta.version,name});renamed?.(id,references.get(id),saved);changed(id);}
  async function editor(id) {
    let meta=await api('images/'+id),current=await load(id),original=await load(id,true);
    const dialog=document.createElement('dialog');dialog.className='image-editor';dialog.setAttribute('aria-label','Annotate image');
    const toolbar=document.createElement('div');toolbar.className='image-toolbar';
    const stage=document.createElement('div');stage.className='image-stage';
    const base=new Image(),originalImage=new Image(),canvas=document.createElement('canvas'),ink=document.createElement('canvas'),ctx=ink.getContext('2d');
    base.src=current;originalImage.src=original;await Promise.all([base.decode(),originalImage.decode()]);canvas.width=ink.width=base.naturalWidth;canvas.height=ink.height=base.naturalHeight;
    if(canvas.width*canvas.height>40000000){URL.revokeObjectURL(current);URL.revokeObjectURL(original);throw new Error('Image is too large to annotate (40 megapixels maximum).');}
    ctx.drawImage(base,0,0);stage.append(canvas);const status=document.createElement('p');status.setAttribute('role','status');
    let lastErase=null,tool='pen',drawing=false,history=[ctx.getImageData(0,0,ink.width,ink.height)],at=0,dirty=false,busy=false;
    function draw(){const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);c.drawImage(ink,0,0);}
    function buttons(){undo.disabled=at===0;redo.disabled=at===history.length-1;pen.setAttribute('aria-pressed',String(tool==='pen'));eraser.setAttribute('aria-pressed',String(tool==='eraser'));note.setAttribute('aria-pressed',String(tool==='comment'));}
    function snapshot(){history=history.slice(0,at+1);history.push(ctx.getImageData(0,0,ink.width,ink.height));if(history.length>Math.max(2,Math.min(20,Math.floor(64000000/(ink.width*ink.height*4)))))history.shift();at=history.length-1;dirty=true;buttons();}
    const pen=button('Red pen',()=>{tool='pen';buttons();}),eraser=button('Eraser',()=>{tool='eraser';buttons();}),note=button('Comment',()=>{tool='comment';buttons();});
    const undo=button('Undo',()=>{if(at){ctx.putImageData(history[--at],0,0);dirty=true;draw();buttons();}}),redo=button('Redo',()=>{if(at<history.length-1){ctx.putImageData(history[++at],0,0);dirty=true;draw();buttons();}});
    const close=()=>{if(!busy&&(!dirty||confirm('Discard unsaved image annotations?')))dialog.close();};
    const save=button('Save image',run(async()=>{
      if(busy)return;busy=true;save.disabled=true;
      try{const blob=await new Promise(resolve=>canvas.toBlob(resolve,meta.media_type,.95));if(!blob)throw new Error('Unable to encode image.');const form=new FormData();form.append('file',blob,meta.name);form.append('version',meta.version);meta=await (await request('images/'+id,'PATCH',form)).json();dirty=false;changed(id);dialog.close();}catch(e){status.textContent=e.message;throw e;}finally{busy=false;save.disabled=false;}
    }));
    const restore=button('Restore original',run(async()=>{if(!confirm('Restore the original image? Comments will be retained.'))return;meta=await api('images/'+id,'PATCH',{version:meta.version,restore:true});dirty=false;changed(id);dialog.close();}));
    toolbar.append(pen,eraser,undo,redo,note,save,restore,button('Close',close));dialog.append(toolbar,stage,status);document.body.append(dialog);dialog.showModal();draw();buttons();
    const point=e=>{const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};};
    function erase(p){
      const x=p.x*canvas.width,y=p.y*canvas.height,previous=lastErase||{x,y},radius=ctx.lineWidth/2;
      const steps=Math.max(1,Math.ceil(Math.hypot(x-previous.x,y-previous.y)/Math.max(1,radius/2)));
      ctx.save();ctx.beginPath();
      for(let i=0;i<=steps;i++){const px=previous.x+(x-previous.x)*i/steps,py=previous.y+(y-previous.y)*i/steps;ctx.moveTo(px+radius,py);ctx.arc(px,py,radius,0,Math.PI*2);}
      ctx.clip();ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(originalImage,0,0,canvas.width,canvas.height);ctx.restore();ctx.beginPath();ctx.moveTo(x,y);lastErase={x,y};
    }
    canvas.onpointerdown=e=>{
      if(e.button!==0)return;e.preventDefault();const p=point(e);
      if(tool==='comment'){commentBox(stage,id,p,dialog);return;}
      drawing=true;lastErase=null;canvas.setPointerCapture(e.pointerId);ctx.globalCompositeOperation='source-over';ctx.strokeStyle='#e32636';ctx.lineWidth=(tool==='eraser'?20:3)*canvas.width/canvas.getBoundingClientRect().width;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(p.x*canvas.width,p.y*canvas.height);ctx.lineTo(p.x*canvas.width+.01,p.y*canvas.height);if(tool==='eraser')erase(p);else ctx.stroke();draw();
    };
    canvas.onpointermove=e=>{if(!drawing)return;const p=point(e);ctx.lineTo(p.x*canvas.width,p.y*canvas.height);if(tool==='eraser')erase(p);else ctx.stroke();draw();};
    canvas.onpointerup=()=>{if(drawing){drawing=false;snapshot();}};canvas.onpointercancel=canvas.onpointerup;
    dialog.oncancel=e=>{e.preventDefault();close();};dialog.onclose=()=>{URL.revokeObjectURL(current);URL.revokeObjectURL(original);dialog.remove();};
    markers(stage,id,dialog);
  }
  function commentBox(host,id,p,dialog=null,thread=null){
    host.querySelector('.image-comment-box')?.remove();const box=document.createElement('div');box.className='image-comment-box';
    const text=document.createElement('textarea');text.placeholder=thread?'Reply to image thread':'Comment on image';text.setAttribute('aria-label',text.placeholder);
    if(thread){const body=document.createElement('div');body.textContent=thread.messages.map(m=>`${m.author}: ${m.body}`).join('\n');box.append(body);}
    const feedback=document.createElement('p');feedback.setAttribute('role','alert');
    const submit=button(thread?'Reply':'Add comment',run(async()=>{submit.disabled=true;try{await comment(id,p,text.value,thread);box.remove();markers(host,id,dialog);}catch(e){feedback.textContent=e.message;}finally{submit.disabled=false;}}));
    box.append(text,feedback,submit,button('Cancel',()=>box.remove()));host.append(box);text.focus();
  }
  function markers(host,id,dialog=null){
    host.querySelectorAll(':scope > .image-comment-marker').forEach(el=>el.remove());
    for(const thread of context().threads.filter(t=>t.image_annotation?.image_id===id&&t.anchor_status==='attached')){
      const p=thread.image_annotation,b=button('▣',()=>{commentBox(host,id,p,dialog,thread);if(!dialog)focus(thread.id);});b.className='image-comment-marker';b.title='Image thread #'+thread.id;b.setAttribute('aria-label',b.title);b.style.left=(p.x*100)+'%';b.style.top=(p.y*100)+'%';b.classList.toggle('resolved',thread.resolved);host.append(b);
    }
  }
  function mount(img){
    if(img.closest('.markdown-image'))return;
    const src=img.getAttribute('src'),owner=context();let id=imageID(src);
    const wrap=document.createElement('span');wrap.className='markdown-image';img.replaceWith(wrap);wrap.append(img);
    let url;const dispose=()=>{if(url)URL.revokeObjectURL(url);};
    const observer=new MutationObserver(()=>{if(!wrap.isConnected){dispose();observer.disconnect();}});queueMicrotask(()=>observer.observe(document.body,{childList:true,subtree:true}));
    run(async()=>{
      if(!id&&/\.(?:png|jpe?g)$/i.test(src||'')&&!/^(?:https?:|data:|blob:|\/)/i.test(src||'')){
        const path=new URL(decodeURIComponent(src),'https://workspace/'+owner.path).pathname.slice(1);
        const meta=await api('images/import','POST',{path});id=meta.id;
      }
      if(id){references.set(id,src);url=await load(id);img.src=url;wrap.dataset.imageId=id;
        if(owner.readonly)return;
        const pencil=button('✎',run(()=>editor(id)));pencil.className='image-pencil';pencil.title='Annotate image';pencil.setAttribute('aria-label','Annotate image');wrap.append(pencil);wrap.oncontextmenu=e=>{e.preventDefault();run(()=>rename(id))();};markers(wrap,id);
      }else if(!/^(?:https?:|data:|blob:|\/)/i.test(src||'')){
        const path=new URL(decodeURIComponent(src),'https://workspace/'+owner.path).pathname.slice(1);
        url=URL.createObjectURL(await (await request('binary?'+new URLSearchParams({path}))).blob());img.src=url;
      }
      if(!wrap.isConnected)dispose();
    })();
  }
  function refresh(id){for(const wrap of document.querySelectorAll('.markdown-image[data-image-id]')){if(!id||wrap.dataset.imageId===id){markers(wrap,wrap.dataset.imageId);if(id){const img=wrap.querySelector('img');wrap.replaceWith(img);img.setAttribute('src',references.get(id)||`.looking-glass/images/${id}_image.png`);mount(img);}}}}
  return {upload,mount,refresh,rename,editor,reference:id=>references.get(id)};
}
