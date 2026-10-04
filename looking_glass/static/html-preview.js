// Runs inside the opaque-origin report. Never receives application credentials.
const send = (type, data={}) => parent.postMessage({lookingGlass:config.channel,type,...data},config.parentOrigin);
let threads=[], active=null, ranges=new Map(), selected=null, timer=0;
const excluded='script,style,noscript,template,textarea,input,select,[hidden],[data-looking-glass-overlay]';
function textMap(){
  const nodes=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  let text='';
  while(walker.nextNode()){
    const node=walker.currentNode,element=node.parentElement;
    if(!element||element.closest(excluded))continue;
    let visible=true;
    for(let ancestor=element;ancestor;ancestor=ancestor.parentElement){const style=getComputedStyle(ancestor);if(style.display==='none'||style.visibility==='hidden'){visible=false;break;}}
    if(!visible)continue;
    nodes.push({node,from:text.length,to:text.length+node.length});text+=node.data;
  }
  return {text,nodes};
}
function rangeFor(map,from,to){
  const first=map.nodes.find(n=>n.to>from),last=map.nodes.find(n=>n.to>=to&&n.from<to);
  if(!first||!last)return null;
  const range=document.createRange();range.setStart(first.node,from-first.from);range.setEnd(last.node,to-last.from);return range;
}
function offset(map,node,offset){
  if(node.nodeType===Node.TEXT_NODE){const item=map.nodes.find(n=>n.node===node);return item?item.from+offset:null;}
  const point=document.createRange();point.setStart(node,offset);point.collapse(true);
  for(const item of map.nodes){const end=document.createRange();end.setStart(item.node,item.node.length);end.collapse(true);if(point.compareBoundaryPoints(Range.START_TO_START,end)<=0){const start=document.createRange();start.setStart(item.node,0);start.collapse(true);if(point.compareBoundaryPoints(Range.START_TO_START,start)<=0)return item.from;}}
  return map.text.length;
}
function capture(){
  const selection=getSelection();if(!selection||selection.isCollapsed||!selection.rangeCount){selected=null;send('selection',{selection:null});return;}
  const range=selection.getRangeAt(0),map=textMap(),from=offset(map,range.startContainer,range.startOffset),to=offset(map,range.endContainer,range.endOffset);
  if(from===null||to===null||to<=from||!map.text.slice(from,to).trim()){selected=null;send('selection',{selection:null});return;}
  const rect=range.getBoundingClientRect();
  selected={anchor:{quote:map.text.slice(from,to),prefix:map.text.slice(Math.max(0,from-48),from),suffix:map.text.slice(to,to+48)},rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom}};
  send('selection',{selection:selected});
}
function locate(map,anchor){
  const candidates=[];let at=0;
  while(anchor.quote&&(at=map.text.indexOf(anchor.quote,at))>=0){candidates.push(at);at++;}
  const supported=candidates.filter(at=>(!anchor.prefix||map.text.slice(Math.max(0,at-anchor.prefix.length),at)===anchor.prefix)&&(!anchor.suffix||map.text.slice(at+anchor.quote.length,at+anchor.quote.length+anchor.suffix.length)===anchor.suffix));
  const from=supported.length===1?supported[0]:candidates.length===1?candidates[0]:null;
  return from===null?null:rangeFor(map,from,from+anchor.quote.length);
}
const style=document.createElement('style');style.textContent='::highlight(looking-glass-passages){background:#a84dff30;text-decoration:underline #9935ee}::highlight(looking-glass-active){background:#a84dff60}';document.head.append(style);
function paint(){
  const map=textMap(),statuses=[];ranges=new Map();
  for(const thread of threads){const range=locate(map,thread.render_anchor);if(range)ranges.set(thread.id,range);statuses.push({id:thread.id,attached:!!range});}
  if(window.CSS?.highlights){CSS.highlights.set('looking-glass-passages',new Highlight(...threads.filter(t=>!t.resolved).map(t=>ranges.get(t.id)).filter(Boolean)));CSS.highlights.set('looking-glass-active',new Highlight(...(ranges.has(active)?[ranges.get(active)]:[])));}
  send('anchors',{statuses});
}
window.addEventListener('message',event=>{
  if(event.source!==parent||event.origin!==config.parentOrigin||event.data?.lookingGlass!==config.channel)return;
  const message=event.data;
  if(message.type==='threads'){threads=message.threads;active=message.active;paint();}
  if(message.type==='jump'){
    active=message.id;paint();const range=ranges.get(active);if(!range)return;
    const element=range.startContainer.parentElement;element?.scrollIntoView({block:'center',behavior:'smooth'});
  }
});
document.addEventListener('selectionchange',()=>{clearTimeout(timer);timer=setTimeout(capture,100);});
document.addEventListener('pointerup',()=>setTimeout(capture,0));
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.altKey&&!event.shiftKey&&event.key.toLowerCase()==='z'){event.preventDefault();event.stopPropagation();send('zen');return;}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='p'){event.preventDefault();event.stopPropagation();send('quick-open');}
},true);
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)){capture();if(selected){event.preventDefault();send('comment');}}});
document.addEventListener('click',event=>{
  if(!getSelection()?.isCollapsed||event.target.closest('a,button,input,textarea,select'))return;
  for(const [id,range] of ranges){if(threads.find(t=>t.id===id)?.resolved)continue;for(const rect of range.getClientRects())if(event.clientX>=rect.left&&event.clientX<=rect.right&&event.clientY>=rect.top&&event.clientY<=rect.bottom){send('thread',{id});return;}}
});
let mutationTimer=0;
new MutationObserver(()=>{clearTimeout(mutationTimer);mutationTimer=setTimeout(()=>{paint();capture();},150);}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','style','hidden']});
window.addEventListener('scroll',()=>{if(selected)capture();},true);
window.addEventListener('resize',()=>{paint();if(selected)capture();});
send('ready');
