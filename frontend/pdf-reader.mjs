import {mountPDFContents} from './pdf-bookmarks.mjs';

export async function mountPDF(host,contents,session,{token,api,onPassage,onError,onSelection}){
  const pdfjs=await import('/static/pdfjs.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc='/static/pdf.worker.mjs';
  const loading=pdfjs.getDocument({url:'/api/binary?'+new URLSearchParams({path:session.path}),httpHeaders:{'X-Looking-Glass-Token':token},
    cMapUrl:'/static/pdf-cmaps/',cMapPacked:true,standardFontDataUrl:'/static/pdf-fonts/',wasmUrl:'/static/pdf-wasm/',isEvalSupported:false});
  let pdf;
  try{pdf=await loading.promise;}catch(error){await loading.destroy();throw new Error('Unable to display this PDF: '+error.message);}
  if(!host.isConnected){await loading.destroy();return ()=>{};}
  const wrapper=document.createElement('div');wrapper.className='pdf-reader';host.append(wrapper);
  const pages=new Map();let disposed=false,threads=[],active=null,signature='';
  const resize=new ResizeObserver(entries=>{for(const {target,contentRect} of entries){const page=pages.get(Number(target.dataset.page));if(page)page.sheet.style.transform=`scale(${contentRect.width/page.width})`;}});
  function paint(){
    const next=JSON.stringify([threads.map(({id,resolved,render_anchor})=>({id,resolved,render_anchor})),active]);if(signature===next)return;signature=next;
    for(const page of pages.values()){
      page.marks.replaceChildren();page.links.replaceChildren();
      for(const thread of threads){const anchor=thread.render_anchor;if(anchor.page!==page.number)continue;
        for(const [x,y,w,h] of anchor.rects){const mark=document.createElement('div');mark.className='pdf-passage'+(thread.resolved?' resolved':'')+(thread.id===active?' active':'');Object.assign(mark.style,{left:x*100+'%',top:y*100+'%',width:w*100+'%',height:h*100+'%'});page.marks.append(mark);}
        const link=document.createElement('button');link.className='pdf-thread-link';link.textContent='#'+thread.id;link.setAttribute('aria-label','Open PDF discussion '+thread.id);link.onclick=()=>onPassage([thread.id]);page.links.append(link);
      }
    }
  }
  async function render(page){
    if(disposed||page.rendered)return;page.rendered=true;
    try{
      const viewport=page.source.getViewport({scale:1}),ratio=Math.min(devicePixelRatio||1,2);
      const canvas=document.createElement('canvas');canvas.width=Math.ceil(viewport.width*ratio);canvas.height=Math.ceil(viewport.height*ratio);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';page.sheet.prepend(canvas);
      page.task=page.source.render({canvasContext:canvas.getContext('2d'),viewport,transform:[ratio,0,0,ratio,0,0]});await page.task.promise;
      if(disposed)return;
      page.layer=new pdfjs.TextLayer({textContentSource:page.source.streamTextContent(),container:page.text,viewport});await page.layer.render();
      if(!page.text.textContent.trim()){const note=document.createElement('span');note.className='pdf-scan-note';note.textContent='No selectable text on this page';page.links.append(note);}
      page.node.dataset.ready='true';
    }catch(error){if(!disposed&&error.name!=='RenderingCancelledException')onError('Unable to render PDF page '+page.number+': '+error.message);}
  }
  const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting)render(pages.get(Number(entry.target.dataset.page)));},{root:host,rootMargin:'800px'});
  for(let number=1;number<=pdf.numPages;number++){
    const source=await pdf.getPage(number),viewport=source.getViewport({scale:1});
    const node=document.createElement('section');node.className='pdf-page';node.dataset.page=number;node.setAttribute('aria-label','PDF page '+number);node.style.width=viewport.width+'px';node.style.aspectRatio=viewport.width+'/'+viewport.height;
    const sheet=document.createElement('div');sheet.className='pdf-sheet';sheet.style.width=viewport.width+'px';sheet.style.height=viewport.height+'px';sheet.style.setProperty('--total-scale-factor','1');
    const text=document.createElement('div');text.className='textLayer';
    const marks=document.createElement('div');marks.className='pdf-marks';sheet.append(marks,text);
    const links=document.createElement('div');links.className='pdf-page-links';links.setAttribute('aria-label','Discussions on page '+number);
    node.append(sheet,links);wrapper.append(node);
    const page={number,node,sheet,text,marks,links,source,width:viewport.width,rendered:false};pages.set(number,page);resize.observe(node);observer.observe(node);
    text.addEventListener('click',event=>{
      if(window.getSelection()?.toString())return;
      const bounds=sheet.getBoundingClientRect(),x=(event.clientX-bounds.left)/bounds.width,y=(event.clientY-bounds.top)/bounds.height;
      const ids=threads.filter(thread=>thread.render_anchor.page===number&&thread.render_anchor.rects.some(([a,b,w,h])=>x>=a&&x<=a+w&&y>=b&&y<=b+h)).map(thread=>thread.id);
      if(ids.length)onPassage(ids);
    });
  }
  const jump=async number=>{const page=pages.get(number);if(!page)return;page.node.scrollIntoView({block:'start',behavior:'instant'});await render(page);};
  function zoom(direction=0){session.pdfZoom=Math.max(.5,Math.min(3,(session.pdfZoom||1)+direction*.2));for(const page of pages.values()){page.node.style.width=page.width*session.pdfZoom+'px';page.node.style.maxWidth=`calc(100% * ${session.pdfZoom})`;}}
  zoom();
  const disposeContents=mountPDFContents(contents,session,{api,jump,onError});
  const selection=()=>{
    const selected=window.getSelection();if(!selected?.rangeCount||selected.isCollapsed)return null;
    const range=selected.getRangeAt(0),element=node=>node.nodeType===Node.TEXT_NODE?node.parentElement:node;
    const layer=element(range.startContainer)?.closest('.textLayer');
    if(!layer||!wrapper.contains(layer)||!layer.contains(range.endContainer))return null;
    const page=pages.get(Number(layer.closest('.pdf-page').dataset.page)),bounds=page.sheet.getBoundingClientRect(),rects=[];
    const walker=document.createTreeWalker(layer,NodeFilter.SHOW_TEXT);let node;
    while((node=walker.nextNode())){
      if(!node.textContent.trim()||!range.intersectsNode(node))continue;
      const part=document.createRange();part.selectNodeContents(node);if(node===range.startContainer)part.setStart(node,range.startOffset);if(node===range.endContainer)part.setEnd(node,range.endOffset);
      for(const rect of part.getClientRects()){
        const x=Math.max(0,(rect.left-bounds.left)/bounds.width),y=Math.max(0,(rect.top-bounds.top)/bounds.height);
        const w=Math.min(1-x,rect.width/bounds.width),h=Math.min(1-y,rect.height/bounds.height);if(w>0&&h>0)rects.push([x,y,w,h]);
      }
    }
    const quote=selected.toString().trim();if(!quote||!rects.length)return null;
    return {pdf_anchor:{page:page.number,quote,rects},quote,rect:range.getBoundingClientRect()};
  };
  const changed=()=>onSelection();document.addEventListener('selectionchange',changed);
  if(session.pdfScroll){host.scrollTop=session.pdfScroll.top;host.scrollLeft=session.pdfScroll.left;}
  const dispose=()=>{session.pdfScroll={top:host.scrollTop,left:host.scrollLeft};disposed=true;observer.disconnect();resize.disconnect();disposeContents();document.removeEventListener('selectionchange',changed);for(const page of pages.values()){page.task?.cancel();page.layer?.cancel();}loading.destroy();wrapper.remove();};
  return Object.assign(dispose,{selection,jump,zoom,highlight(items,id){threads=items.filter(thread=>thread.path===session.path&&thread.anchor_kind==='pdf'&&thread.anchor_status==='attached'&&thread.render_anchor?.version===session.version);active=id;paint();}});
}
