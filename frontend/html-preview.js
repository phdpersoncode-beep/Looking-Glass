import {htmlTextMap} from './html-text-map.mjs';
// Runs inside the opaque-origin report. Never receives application credentials.
const send = (type, data={}) => parent.postMessage({lookingGlass:config.channel,type,...data},config.parentOrigin);
let threads=[], active=null, ranges=new Map(), selected=null;
let sourceBindings=new WeakMap(),sourceText='';
function bindSource(mapping){
  sourceBindings=new WeakMap();sourceText=mapping.source;
  const elements=new Map(),childCounts=new WeakMap();
  for(const element of document.querySelectorAll('['+mapping.attribute+']')){
    const id=element.getAttribute(mapping.attribute);
    elements.set(id,elements.has(id)?null:element);
  }
  for(const record of mapping.records){
    let node=record.id===null?document.body:elements.get(record.id);
    for(const index of record.path)node=node?.childNodes[index];
    if(node?.nodeType!==Node.TEXT_NODE||node.data!==record.text)continue;
    if(!childCounts.has(node.parentNode))childCounts.set(node.parentNode,[...node.parentNode.childNodes].filter(n=>!n.matches?.('[data-looking-glass-overlay]')).length);
    if(childCounts.get(node.parentNode)!==record.siblings)continue;
    const item={...record,node,map:undefined};sourceBindings.set(node,item);
  }
}
function sourceMap(node){
  const item=sourceBindings.get(node);
  if(!item||!node.isConnected||node.data!==item.text)return null;
  if(item.map===undefined)item.map=htmlTextMap(sourceText.slice(item.from,item.to),item.from,item.text);
  return item.map;
}
function sourceSelection(map,from,to){
  let start=null,end=null;
  for(const item of map.nodes){
    if(item.to<=from||item.from>=to)continue;
    const mapping=sourceMap(item.node);if(!mapping)return null;
    const a=Math.max(0,from-item.from),b=Math.min(item.node.length,to-item.from);
    const first=mapping.starts[a],last=mapping.ends[b-1];
    // CSS/DOM reordering and generated mixed selections have no single safe
    // contiguous source range. Keep them explicitly rendered-only.
    if(first===undefined||last===undefined||end!==null&&first<end)return null;
    if(start===null)start=first;end=last;
  }
  return start===null?null:{from:start,to:end};
}
function sourceRanges(map,from,to){
  const found=[];
  for(const item of map.nodes){
    const record=sourceBindings.get(item.node);
    if(!record||record.to<=from||record.from>=to)continue;
    const mapping=sourceMap(item.node);if(!mapping)continue;
    let start=-1,end=-1;
    for(let i=0;i<item.node.length;i++)if(mapping.ends[i]>from&&mapping.starts[i]<to){if(start<0)start=i;end=i+1;}
    if(start>=0){const range=document.createRange();range.setStart(item.node,start);range.setEnd(item.node,end);found.push(range);}
  }
  return found;
}
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
function capture(requestId){
  const selection=getSelection();if(!selection||selection.isCollapsed||!selection.rangeCount){selected=null;send('selection',{selection:null,requestId});return;}
  const range=selection.getRangeAt(0),map=textMap(),from=offset(map,range.startContainer,range.startOffset),to=offset(map,range.endContainer,range.endOffset);
  if(from===null||to===null||to<=from||!map.text.slice(from,to).trim()){selected=null;send('selection',{selection:null,requestId});return;}
  const rect=range.getBoundingClientRect();
  selected={source:sourceSelection(map,from,to),anchor:{quote:map.text.slice(from,to),prefix:map.text.slice(Math.max(0,from-48),from),suffix:map.text.slice(to,to+48)},rect:{left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom}};
  send('selection',{selection:selected,requestId});
}
function locate(map,anchor){
  const candidates=[];let at=0;
  while(anchor.quote&&(at=map.text.indexOf(anchor.quote,at))>=0){candidates.push(at);at++;}
  const supported=candidates.filter(at=>(!anchor.prefix||map.text.slice(Math.max(0,at-anchor.prefix.length),at)===anchor.prefix)&&(!anchor.suffix||map.text.slice(at+anchor.quote.length,at+anchor.quote.length+anchor.suffix.length)===anchor.suffix));
  const from=supported.length===1?supported[0]:candidates.length===1?candidates[0]:null;
  return from===null?null:rangeFor(map,from,from+anchor.quote.length);
}
const style=document.createElement('style');style.textContent='::selection{background:#b84dff45;color:inherit}::highlight(looking-glass-passages){background:#a84dff30;text-decoration:underline #9935ee}::highlight(looking-glass-active){background:#a84dff60}';document.head.append(style);
function paint(){
  const map=textMap(),statuses=[];ranges=new Map();
  for(const thread of threads){const matches=thread.source?sourceRanges(map,thread.source.from,thread.source.to):[locate(map,thread.render_anchor)].filter(Boolean);if(matches.length)ranges.set(thread.id,matches);if(!thread.source)statuses.push({id:thread.id,attached:!!matches.length});}
  if(window.CSS?.highlights){CSS.highlights.set('looking-glass-passages',new Highlight(...threads.filter(t=>!t.resolved).flatMap(t=>ranges.get(t.id)||[])));CSS.highlights.set('looking-glass-active',new Highlight(...(ranges.get(active)||[])));}
  send('anchors',{statuses});
}
window.addEventListener('message',event=>{
  if(event.source!==parent||event.origin!==config.parentOrigin||event.data?.lookingGlass!==config.channel)return;
  const message=event.data;
  if(message.type==='clear-selection'||message.type==='jump'){getSelection()?.removeAllRanges();capture();}
  if(message.type==='capture')capture(message.requestId);
  if(message.type==='initialize'){bindSource(message.mapping);paint();capture();}
  if(message.type==='threads'){threads=message.threads;active=message.active;paint();}
  if(message.type==='jump'){
    active=message.id;paint();const range=ranges.get(active)?.[0];if(!range){send('unmapped',{id:active});return;}
    const element=range.startContainer.parentElement;element?.scrollIntoView({block:'center',behavior:'smooth'});
  }
});
document.addEventListener('selectionchange',()=>capture());
document.addEventListener('pointerup',()=>setTimeout(capture,0));
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.altKey&&!event.shiftKey&&event.key.toLowerCase()==='z'){event.preventDefault();event.stopPropagation();send('zen');return;}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='p'){event.preventDefault();event.stopPropagation();send('quick-open');}
},true);
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)){capture();if(selected){event.preventDefault();send('comment');}}});
document.addEventListener('click',event=>{
  if(!getSelection()?.isCollapsed||event.target.closest('a,button,input,textarea,select'))return;
  for(const [id,matches] of ranges){if(threads.find(t=>t.id===id)?.resolved)continue;for(const range of matches)for(const rect of range.getClientRects())if(event.clientX>=rect.left&&event.clientX<=rect.right&&event.clientY>=rect.top&&event.clientY<=rect.bottom){send('thread',{id});return;}}
});
let mutationTimer=0;
new MutationObserver(()=>{clearTimeout(mutationTimer);mutationTimer=setTimeout(()=>{paint();capture();},150);}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['class','style','hidden']});
window.addEventListener('scroll',()=>{if(selected)capture();},true);
window.addEventListener('resize',()=>{paint();if(selected)capture();});
send('ready');
