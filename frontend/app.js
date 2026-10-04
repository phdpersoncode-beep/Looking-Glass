import {formatJSON} from './json-format.mjs';
import {basicSetup} from 'codemirror';
import {EditorState, StateEffect, StateField, Compartment, Text, RangeSet} from '@codemirror/state';
import {EditorView, Decoration, ViewPlugin, keymap, WidgetType, gutter, GutterMarker} from '@codemirror/view';
import {Chunk} from '@codemirror/merge';
import {TaskList, Table} from '@lezer/markdown';
import {undo, redo, indentWithTab, isolateHistory} from '@codemirror/commands';
import {openSearchPanel} from '@codemirror/search';
import {markdown} from '@codemirror/lang-markdown';
import {python} from '@codemirror/lang-python';
import {html} from '@codemirror/lang-html';
import {json} from '@codemirror/lang-json';
import {StreamLanguage, syntaxTree, syntaxHighlighting, HighlightStyle, ensureSyntaxTree, foldable, foldEffect, unfoldAll} from '@codemirror/language';
import {shell} from '@codemirror/legacy-modes/mode/shell';
import {tags,highlightTree,classHighlighter} from '@lezer/highlight';
import {marked} from 'marked';
import DOMPurify from 'dompurify';
import * as THREE from 'three';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {SVGRenderer} from 'three/addons/renderers/SVGRenderer.js';

const $ = selector => document.querySelector(selector);
const token = $('meta[name=looking-glass-token]').content;
const root = $('.root-label').textContent;
const tabs = new Map();
let expandedFolders=new Set();try{expandedFolders=new Set(JSON.parse(localStorage.getItem('looking-glass-folders:'+root)||'[]'));}catch{}
let quickPaths=[],quickMatches=[],quickIndex=0;
let active = null, view = null, cleanup = () => {}, currentThreads = [], activeThread = null, pending = null;
let polling = false, saving = false, switching = false, refreshNumber = 0, queuedFile = null;
let selectingText = false, selectionFrame = 0, postingComment = false;
let jsonlSearch = null;
let renderedPreview=null,renderedSelection=null,renderedJump=null;
function previewMessage(type,data={}){const preview=renderedPreview;if(preview?.ready)preview.frame.contentWindow.postMessage({lookingGlass:preview.channel,type,...data},'*');}
function previewThreads(){previewMessage('threads',{threads:currentThreads.filter(t=>t.path===active&&t.anchor_kind==='rendered').map(t=>({id:t.id,render_anchor:t.render_anchor,resolved:t.resolved})),active:activeThread});}
let fontStep = Math.max(-4,Math.min(12,Number(localStorage.getItem('looking-glass-font-step'))||0));
function applyFontSize(){document.documentElement.style.setProperty('--document-font-size',(14+fontStep)+'px');document.documentElement.style.setProperty('--prose-font-size',(18+fontStep)+'px');document.documentElement.style.setProperty('--document-font-step',fontStep+'px');view?.requestMeasure();}
const themeSlot = new Compartment(), liveSlot = new Compartment(), gitSlot=new Compartment();
const selectionSettled = StateEffect.define();
const baselineEffect=StateEffect.define();
const diffConfig={scanLimit:1000,timeout:50};
const gitField=StateField.define({
  create:()=>({base:null,chunks:[]}),
  update(value,tr){
    for(const effect of tr.effects)if(effect.is(baselineEffect)){
      const base=effect.value===null?null:Text.of(effect.value.replace(/\r\n/g,'\n').split('\n'));
      if(base===value.base||(base&&value.base&&base.eq(value.base)))return value;
      return {base,chunks:base?Chunk.build(base,tr.state.doc,diffConfig):[]};
    }
    return tr.docChanged&&value.base?{base:value.base,chunks:Chunk.updateB(value.chunks,value.base,tr.state.doc,tr.changes,diffConfig)}:value;
  }
});
class GitMarker extends GutterMarker {
  constructor(kind,removed=false){super();this.kind=kind;this.removed=removed;}
  eq(other){return this.kind===other.kind&&this.removed===other.removed;}
  toDOM(){const el=document.createElement('span');el.className='git-marker '+this.kind+(this.removed?' removed':'');el.title=(this.kind==='added'?'Added line':this.kind==='changed'?'Changed line':'Removed lines')+(this.removed&&this.kind?' · Removed lines':'')+' since last commit';el.setAttribute('aria-label',el.title);return el;}
}
const gitGutter=gutter({class:'git-gutter',renderEmptyElements:true,initialSpacer:()=>new GitMarker(''),markers(v){
  const {base,chunks}=v.state.field(gitField),doc=v.state.doc,markers=new Map();if(!base)return RangeSet.empty;
  const put=(pos,kind,removed=false)=>{const existing=markers.get(pos);markers.set(pos,new GitMarker(kind||existing?.kind||'',removed||existing?.removed||false));};
  for(const chunk of chunks){
    const first=doc.lineAt(Math.min(chunk.fromB,doc.length));
    if(chunk.fromB===chunk.toB){put(first.from,'',true);continue;}
    const last=doc.lineAt(Math.min(chunk.toB-1,doc.length));
    const oldCount=chunk.fromA===chunk.toA?0:base.lineAt(Math.min(chunk.toA-1,base.length)).number-base.lineAt(chunk.fromA).number+1;
    for(let number=first.number;number<=last.number;number++)put(doc.line(number).from,number-first.number<oldCount?'changed':'added');
    if(oldCount>last.number-first.number+1)put(last.from,'',true);
  }
  return RangeSet.of([...markers].sort((a,b)=>a[0]-b[0]).map(([pos,marker])=>marker.range(pos)));
},lineMarkerChange:u=>u.docChanged||u.transactions.some(t=>t.effects.some(e=>e.is(baselineEffect)))});
const spansEffect = StateEffect.define();
const spanField = StateField.define({
  create: () => [],
  update(spans, tr) {
    spans = spans.map(s => ({...s, from:tr.changes.mapPos(s.from,1), to:tr.changes.mapPos(s.to,-1)})).filter(s => s.from < s.to);
    for(const effect of tr.effects) if(effect.is(spansEffect)) spans = effect.value;
    return spans;
  },
  provide: field => EditorView.decorations.from(field, spans => Decoration.set(spans.map(s => Decoration.mark({class:'passage-highlight' + (s.id === activeThread?' focused-highlight':''), attributes:{'data-anchor':String(s.id)}}).range(s.from,s.to)),true))
});
const colors = HighlightStyle.define([
  {tag:tags.keyword,color:'#ad5ded'}, {tag:tags.string,color:'#4a9c80'},
  {tag:tags.number,color:'#c68b45'}, {tag:tags.comment,color:'#858392',fontStyle:'italic'},
  {tag:tags.propertyName,color:'#639bb5'}, {tag:tags.function(tags.variableName),color:'#8b72dc'}
]);
const theme = () => EditorView.theme({
  '&':{height:'100%',color:'var(--text)',backgroundColor:'var(--paper)'},
  '.cm-scroller':{fontFamily:'var(--mono)',fontSize:'var(--document-font-size)',lineHeight:'1.7'},
  '.cm-content':{padding:'32px 0'},
  '.cm-line':{padding:'0 28px'},
  '.cm-gutters':{backgroundColor:'var(--paper)',color:'var(--muted)',border:'none'},
  '.cm-activeLine, .cm-activeLineGutter':{backgroundColor:'var(--active-line)'},
  '.cm-cursor':{borderLeftColor:'var(--purple)'},
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground':{backgroundColor:'var(--selection)'},
  '.cm-searchMatch':{backgroundColor:'var(--selection)',outline:'1px solid var(--purple)'},
  '.cm-panels':{backgroundColor:'var(--panel)',color:'var(--text)'},
  '.cm-panel input, .cm-panel button':{color:'var(--text)',background:'var(--paper)'}
},{dark:document.documentElement.dataset.theme === 'dark'});

class MarkdownTable extends WidgetType {
  constructor(source,from){super();this.source=source;this.from=from;}
  eq(other){return this.source===other.source&&this.from===other.from;}
  toDOM(v){const el=document.createElement('div');el.className='md-table';el.innerHTML=DOMPurify.sanitize(marked.parse(this.source));el.title='Click to edit table source';el.onmousedown=event=>{event.preventDefault();v.dispatch({selection:{anchor:this.from}});v.focus();};return el;}
  ignoreEvent(){return true;}
}
function tableDecorations(state){
  const ranges=[],selection=state.selection.main;
  syntaxTree(state).iterate({enter(node){
    if(node.name!=='Table')return;
    if(selection.from<=node.to&&selection.to>=node.from)return false;
    ranges.push(Decoration.replace({block:true,widget:new MarkdownTable(state.sliceDoc(node.from,node.to),node.from)}).range(node.from,node.to));return false;
  }});
  return Decoration.set(ranges,true);
}
const liveTables=StateField.define({create:tableDecorations,update:(_value,tr)=>tableDecorations(tr.state),provide:field=>EditorView.decorations.from(field)});
class Bullet extends WidgetType {toDOM(){const el=document.createElement('span');el.textContent='• ';return el;}}
class TaskCheckbox extends WidgetType {
  constructor(checked,from){super();this.checked=checked;this.from=from;}
  eq(other){return other.checked===this.checked&&other.from===this.from;}
  toDOM(v){const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='md-task-checkbox';checkbox.checked=this.checked;checkbox.setAttribute('aria-label',this.checked?'Mark task incomplete':'Mark task complete');checkbox.onmousedown=event=>event.preventDefault();checkbox.onchange=()=>{v.dispatch({changes:{from:this.from+1,to:this.from+2,insert:checkbox.checked?'x':' '}});v.focus();};return checkbox;}
  ignoreEvent(){return true;}
}
function liveDecorations(v, activeRange) {
  const ranges=[], doc=v.state.doc;
  const {from:activeFrom,to:activeTo}=activeRange;
  syntaxTree(v.state).iterate({
    enter(node){
      const name=node.name, a=node.from, b=node.to;
      if(b<=a) return;
      const line=doc.lineAt(a), isActive=line.from<=activeTo && line.to>=activeFrom;
      if(/^ATXHeading[1-6]$/.test(name)) ranges.push(Decoration.line({class:'md-heading md-h'+name.slice(-1)}).range(line.from));
      if(name==='FencedCode'){const last=doc.lineAt(b);for(let number=line.number;number<=last.number;number++)ranges.push(Decoration.line({class:number===line.number||number===last.number?'md-code-fence':'md-code-block'}).range(doc.line(number).from));}
      if(name==='Blockquote') ranges.push(Decoration.line({class:'md-quote'}).range(line.from));
      if(name==='StrongEmphasis') ranges.push(Decoration.mark({class:'md-strong'}).range(a,b));
      if(name==='Emphasis') ranges.push(Decoration.mark({class:'md-emphasis'}).range(a,b));
      if(name==='InlineCode'||name==='CodeText') ranges.push(Decoration.mark({class:'md-code'}).range(a,b));
      if(name==='Link') ranges.push(Decoration.mark({class:'md-link'}).range(a,b));
      if(isActive) return;
      if(['HeaderMark','EmphasisMark','CodeMark','CodeInfo','QuoteMark','LinkMark'].includes(name) && doc.lineAt(b).number===line.number)
        ranges.push(Decoration.replace({}).range(a,b));
      if(name==='URL' && doc.lineAt(b).number===line.number) ranges.push(Decoration.replace({}).range(a,b));
      if(name==='TaskMarker')ranges.push(Decoration.replace({widget:new TaskCheckbox(doc.sliceString(a+1,a+2).toLowerCase()==='x',a)}).range(a,b));
      if(name==='ListMark'){const task=/^\s*\[[ xX]\]\s/.test(doc.sliceString(b,line.to));ranges.push(Decoration.replace({widget:task?undefined:new Bullet()}).range(a,b));}
    }
  });
  return Decoration.set(ranges,true);
}
const liveMarkdown = ViewPlugin.fromClass(class {
  constructor(v){const line=v.state.doc.lineAt(v.state.selection.main.head);this.activeRange={from:line.from,to:line.to};this.decorations=liveDecorations(v,this.activeRange);}
  update(u){
    if(u.docChanged)this.activeRange={from:u.changes.mapPos(this.activeRange.from),to:u.changes.mapPos(this.activeRange.to)};
    // Revealing syntax during a drag moves the text under the pointer. Only
    // expose a new active line once a collapsed caret has settled.
    const expose=!selectingText&&u.state.selection.main.empty&&(u.selectionSet||u.transactions.some(t=>t.effects.some(e=>e.is(selectionSettled))));
    if(expose){const line=u.state.doc.lineAt(u.state.selection.main.head);this.activeRange={from:line.from,to:line.to};}
    if(u.docChanged||expose||u.viewportChanged)this.decorations=liveDecorations(u.view,this.activeRange);
  }
},{decorations:v=>v.decorations});

function notify(message,error=false) {$('#notice').textContent=message;$('#notice').classList.toggle('error',error);}
async function api(route,method='GET',data) {
  const result=await fetch('/api/'+route,{method,headers:{'X-Looking-Glass-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  const payload=await result.json();
  if(!result.ok){const e=new Error(payload.error||'Request failed');e.status=result.status;throw e;}
  return payload;
}
async function binary(path){const r=await fetch('/api/binary?'+new URLSearchParams({path}),{headers:{'X-Looking-Glass-Token':token}});if(!r.ok)throw new Error((await r.json()).error);return r.arrayBuffer();}
function guard(fn){return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>notify(e.message,true));}
const toUnits=(text,points)=>Array.from(text).slice(0,points).join('').replace(/\r\n/g,'\n').length;
const selectionPoints=(state,units)=>Array.from(state.sliceDoc(0,units)).length;
const ext=path=>path.split('.').pop().toLowerCase();
const isImage=path=>['png','jpg','jpeg','svg'].includes(ext(path));
function entry(){return active?tabs.get(active):null;}
function remember(){localStorage.setItem('looking-glass-tabs:'+root,JSON.stringify({active,tabs:[...tabs.values()].map(e=>({path:e.path,pinned:e.pinned,mode:e.mode}))}));}
function syncState(){const e=entry();if(e&&view){e.state=view.state;e.content=view.state.sliceDoc();}}
function spansFor(threads,text){return threads.filter(t=>t.path===active&&t.anchor_kind!=='rendered'&&t.anchor_status==='attached'&&!t.resolved).map(t=>({id:t.id,from:toUnits(text,t.start),to:toUnits(text,t.end)})).filter(s=>s.from<s.to&&s.to<=text.length);}

function selectionLocation(){
  if(renderedPreview&&renderedSelection){const frame=renderedPreview.frame.getBoundingClientRect(),rect=renderedSelection.rect;const coords={left:frame.left+rect.left,right:frame.left+rect.right,top:frame.top+rect.top,bottom:frame.top+rect.bottom};if(coords.bottom<frame.top||coords.top>frame.bottom)return null;return {coords,bounds:frame,from:0,to:0};}
  if(!view||view.state.selection.main.empty)return null;
  const {head,from,to}=view.state.selection.main;
  const coords=view.coordsAtPos(head,head===to?-1:1),bounds=view.scrollDOM.getBoundingClientRect();
  if(!coords||coords.bottom<bounds.top||coords.top>bounds.bottom||coords.left<bounds.left||coords.left>bounds.right)return null;
  return {coords,bounds,from,to};
}
function placeNearSelection(element,location){
  const {coords,bounds}=location,width=element.offsetWidth,height=element.offsetHeight;
  const left=Math.max(8,Math.min(coords.left,Math.min(bounds.right,innerWidth)-width-8));
  let top=coords.bottom+8;
  if(top+height>Math.min(bounds.bottom,innerHeight)-8)top=coords.top-height-8;
  element.style.left=left+'px';element.style.top=Math.max(8,Math.min(top,innerHeight-height-8))+'px';
}
function scheduleSelectionTools(){
  cancelAnimationFrame(selectionFrame);
  selectionFrame=requestAnimationFrame(()=>{
    const button=$('#selection-tools');
    const location=selectionLocation();
    button.hidden=!location||selectingText||$('#comment-dialog').open;
    if(!button.hidden){
      const span=view?.state.field(spanField).find(s=>s.from<location.to&&s.to>location.from);
      const show=$('#selection-thread');show.hidden=!span;show.dataset.thread=span?.id||'';
      placeNearSelection(button,location);
    }
  });
}
function closeComment(){if($('#comment-dialog').open)$('#comment-dialog').close();}

function renderTabs(){
  $('#tabs').replaceChildren();
  [...tabs.values()].sort((a,b)=>Number(b.pinned)-Number(a.pinned)).forEach(e=>{
    const tab=document.createElement('div');tab.className='tab'+(e.path===active?' selected':'');tab.dataset.path=e.path;
    const open=document.createElement('button');open.className='tab-name';open.title=e.path;open.textContent=(e.pinned?'⌖ ':'')+e.path.split('/').pop()+(e.dirty?' •':'');open.onclick=guard(()=>openFile(e.path));
    const pin=document.createElement('button');pin.className='tab-control';pin.title=e.pinned?'Unpin tab':'Pin tab';pin.setAttribute('aria-label',pin.title);pin.textContent=e.pinned?'◆':'◇';pin.onclick=()=>{e.pinned=!e.pinned;renderTabs();remember();};
    const close=document.createElement('button');close.className='tab-control';close.title='Close tab';close.setAttribute('aria-label','Close '+e.path);close.textContent='×';close.onclick=guard(()=>closeTab(e.path));
    tab.append(open,pin,close);
    tab.oncontextmenu=ev=>{ev.preventDefault();showTabMenu(e,ev.clientX,ev.clientY);};
    $('#tabs').append(tab);
  });
  $$('.file-entry').forEach(b=>b.classList.toggle('selected',b.dataset.path===active));
}
function revealFile(path){const file=$$('.file-entry').find(b=>b.dataset.path===path);for(let folder=file?.closest('.file-folder');folder;folder=folder.parentElement.closest('.file-folder'))folder.open=true;}
const $$=selector=>[...document.querySelectorAll(selector)];
function showTabMenu(e,x,y){
  $('.tab-menu')?.remove();const menu=document.createElement('div');menu.className='tab-menu';menu.style.left=x+'px';menu.style.top=y+'px';
  const others=document.createElement('button');others.textContent='Close other tabs';others.onclick=guard(async()=>{menu.remove();for(const name of [...tabs.keys()])if(name!==e.path&&!tabs.get(name).pinned)await closeTab(name);});menu.append(others);document.body.append(menu);setTimeout(()=>document.addEventListener('click',()=>menu.remove(),{once:true}),0);
}
async function closeTab(path){
  const e=tabs.get(path);if(e.dirty&&!confirm('Discard unsaved edits in '+path+'?'))return;
  if(path===active){closeComment();syncState();view?.destroy();view=null;cleanup();cleanup=()=>{};active=null;}
  tabs.delete(path);remember();renderTabs();
  if(!active&&tabs.size)await openFile([...tabs.keys()].at(-1));
  else if(!active){$('#surface').innerHTML='<div class="welcome"><h1>Open a file to begin.</h1></div>';$('#threads').replaceChildren();currentThreads=[];$('#thread-count').textContent='0';updateToolbar();await refreshThreads();}
}

const shellLanguage=StreamLanguage.define(shell);
function codeLanguage(info){switch(info.trim().split(/\s+/)[0].toLowerCase()){
  case 'py':case 'python':return python().language;
  case 'sh':case 'bash':case 'shell':return shellLanguage;
  case 'json':return json().language;
  case 'html':case 'htm':return html().language;
  default:return null;
}}
function highlightMarkdown(preview){
  for(const block of preview.querySelectorAll('pre code')){
    const language=codeLanguage(block.className.replace(/^language-/,''));if(!language)continue;
    const source=block.textContent,fragment=document.createDocumentFragment();let at=0;
    highlightTree(language.parser.parse(source),classHighlighter,(from,to,classes)=>{
      if(from>at)fragment.append(document.createTextNode(source.slice(at,from)));
      const span=document.createElement('span');span.className=classes;span.textContent=source.slice(from,to);fragment.append(span);at=to;
    });
    if(at<source.length)fragment.append(document.createTextNode(source.slice(at)));
    block.replaceChildren(fragment);
  }
}
function language(path){switch(ext(path)){case'md':case'markdown':return markdown({extensions:[TaskList,Table],codeLanguages:codeLanguage});case'py':return python();case'sh':case'bash':return shellLanguage;case'html':case'htm':return html();case'json':return json();default:return [];}}
function makeState(e){
  const prose=['md','markdown','txt'].includes(ext(e.path));
  return EditorState.create({doc:e.content,extensions:[EditorState.lineSeparator.of(e.diskContent.includes('\r\n')?'\r\n':'\n'),basicSetup,language(e.path),syntaxHighlighting(colors),spanField,gitField,gitSlot.of([]),
    themeSlot.of(theme()),liveSlot.of(['md','markdown'].includes(ext(e.path))&&e.mode==='live'?[liveMarkdown,liveTables]:[]),
    ...(prose?[EditorView.lineWrapping,EditorView.theme({'.cm-scroller':{fontFamily:'var(--prose)',fontSize:'var(--prose-font-size)'},'.cm-content':{maxWidth:'850px',margin:'0 auto',width:'100%'},'.cm-lineNumbers, .cm-foldGutter':{display:'none'}})]:[]),
    keymap.of([{key:'Mod-s',run:()=>{guard(saveActive)();return true;}},{key:'Mod-Enter',run:()=>{guard(startComment)();return true;}},{key:'Mod-f',run:openSearchPanel},{key:'Mod-h',run:openSearchPanel},indentWithTab]),
    EditorView.updateListener.of(u=>{if(u.docChanged){e.content=u.state.sliceDoc();e.dirty=e.content!==e.diskContent;e.state=u.state;updateToolbar();renderTabs();}if(u.selectionSet)updateToolbar();if(u.selectionSet||u.docChanged||u.viewportChanged||u.geometryChanged)scheduleSelectionTools();}),
    EditorView.domEventHandlers({click:event=>{const mark=event.target.closest?.('[data-anchor]');if(mark&&view?.state.selection.main.empty&&event.detail===1){showThread(Number(mark.dataset.anchor));return true;}return false;}})
  ]});
}

async function openFile(path){
  if(switching){queuedFile=path;return;}switching=true;
  try{
    if(active===path)return;
    closeComment();
    syncState();
    let e=tabs.get(path);
    if(!e){
      const type=ext(path);
      const file=type==='stl'||isImage(path)?{content:'',version:null}:await api('file?'+new URLSearchParams({path}));
      e={path,...file,diskContent:file.content,dirty:false,conflict:null,pinned:false,state:null,mode:type==='md'||type==='markdown'?'live':type==='html'||type==='htm'?'rendered':'source'};
      tabs.set(path,e);
    }
    view?.destroy();view=null;cleanup();cleanup=()=>{};active=path;activeThread=null;currentThreads=[];
    $('#surface').replaceChildren();renderTabs();revealFile(path);updateToolbar();remember();
    if(isImage(path))await mountImage(e);
    else if(ext(path)==='stl')await mountSTL(e);
    else if(ext(path)==='jsonl')mountJSONL(e);
    else mountDocument(e);
    await refreshThreads();notify('');
  }finally{switching=false;if(queuedFile){const next=queuedFile;queuedFile=null;queueMicrotask(()=>guard(()=>openFile(next))());}}
}
function mountDocument(e){
  closeComment();
  renderedPreview=null;renderedSelection=null;renderedJump=null;
  $('#surface').replaceChildren();
  if(e.mode==='rendered'){
    const frame=document.createElement('iframe');frame.id='html-preview';frame.title='Isolated HTML report';frame.setAttribute('sandbox','allow-scripts allow-forms allow-modals');
    // A separate preview capability grants no application API access. The
    // iframe and response sandbox both enforce an opaque report origin.
    guard(async()=>{const preview=await api('preview','POST',{path:e.path,content:e.content});if(frame.isConnected){renderedPreview={frame,path:e.path,channel:preview.url.split('/').pop(),ready:false};frame.src=preview.url;}})();
    cleanup=()=>{renderedPreview=null;renderedSelection=null;renderedJump=null;};
    $('#surface').append(frame);
  }else if(e.mode==='preview'){
    const preview=document.createElement('div');preview.className='markdown-preview';preview.innerHTML=DOMPurify.sanitize(marked.parse(e.content));highlightMarkdown(preview);$('#surface').append(preview);
  }else{
    const parent=document.createElement('div');parent.id='editor';if(['md','markdown','txt'].includes(ext(e.path)))parent.className='prose-editor';$('#surface').append(parent);view=new EditorView({state:e.state||makeState(e),parent});
    view.dispatch({effects:[themeSlot.reconfigure(theme()),liveSlot.reconfigure(['md','markdown'].includes(ext(e.path))&&e.mode==='live'?[liveMarkdown,liveTables]:[])]});
    guard(refreshBaseline)();
  }
  updateToolbar();
}
async function refreshBaseline(){const editor=view,path=active;if(!editor)return;const baseline=await api('git/baseline?'+new URLSearchParams({path}));if(view===editor&&active===path)editor.dispatch({effects:[baselineEffect.of(baseline.content),gitSlot.reconfigure(baseline.content===null?[]:gitGutter)]});}
function updateToolbar(){
  const e=entry(), type=e?ext(e.path):'', viewer=['stl','jsonl'].includes(type)||isImage(e?.path||'');
  $('#json-fold-controls').hidden=type!=='json';
  $('#download-file').hidden=!['html','htm','jsonl'].includes(type);
  $('#document-name').textContent=e?.path||'Open a file';$('#dirty').textContent=e?.dirty?' · Unsaved':'';
  $('#save').disabled=!e||viewer||!e.dirty||saving;$('#annotate').disabled=!e||viewer||!(renderedPreview?renderedSelection:view&&!view.state.selection.main.empty);
  const mode=$('#mode');const modes=type==='md'||type==='markdown'?[['live','Live Markdown'],['source','Raw source'],['preview','Reading preview']]:type==='html'||type==='htm'?[['rendered','Rendered HTML'],['source','HTML source']]:[['source',viewer?'Viewer':'Source']];
  if(mode.dataset.path!==active){mode.replaceChildren(...modes.map(([value,label])=>{const opt=document.createElement('option');opt.value=value;opt.textContent=label;return opt;}));mode.dataset.path=active||'';}
  const html=type==='html'||type==='htm', toggle=$('#html-toggle');
  mode.hidden=!e||modes.length===1||html;if(e)mode.value=e.mode;
  toggle.hidden=!e||!html;toggle.querySelectorAll('span').forEach(s=>s.classList.toggle('active',s.dataset.mode===e?.mode));
  $('#file-info').textContent=e?(viewer?type.toUpperCase()+' viewer':Array.from(e.content).length.toLocaleString()+' characters · UTF-8'):'Choose a file from the sidebar';
  $('#conflict').hidden=!e?.conflict;
  if(e?.conflict)$('#conflict span').textContent=e.conflict.deleted?'This file was deleted or became unavailable on disk. Copy your draft before closing it.':'Changed on disk. Your unsaved edits are preserved. Compare and merge before saving.';
  scheduleSelectionTools();
}
async function saveActive(){
  const e=entry();if(!e||!e.dirty)return e;if(e.conflict)throw new Error('Resolve the external change before saving.');syncState();saving=true;updateToolbar();
  const content=e.content;
  try{
    const saved=await api('file','PUT',{path:e.path,content,version:e.version});e.diskContent=content;e.version=saved.version;e.dirty=e.content!==content;
    if(e.path===active)await refreshThreads();notify('Saved to disk');renderTabs();return e;
  }catch(error){if(error.status===409){const disk=await api('file?'+new URLSearchParams({path:e.path}));e.conflict=disk;}throw error;}
  finally{saving=false;updateToolbar();}
}

function threadScope(){return $('#thread-scope').checked?'all':'file';}
async function refreshThreads(){
  const e=entry(),scope=threadScope();
  if(scope==='file'&&(!e||['stl','jsonl'].includes(ext(e.path))||isImage(e.path))){currentThreads=[];$('#threads').innerHTML='<div class="empty-discussions">This viewer has no annotations.</div>';$('#thread-count').textContent='0';return;}
  const path=active,generation=++refreshNumber;
  const threads=await api('threads'+(scope==='file'?'?'+new URLSearchParams({path}):''));
  if(active!==path||scope!==threadScope()||generation!==refreshNumber)return;
  if(scope==='all')threads.sort((a,b)=>(a.path>b.path)-(a.path<b.path)||a.start-b.start||a.id-b.id);
  currentThreads=threads;$('#thread-count').textContent=threads.filter(t=>!t.resolved).length;
  previewThreads();
  if(view&&e&&!e.dirty)view.dispatch({effects:spansEffect.of(spansFor(threads,e.content))});
  await window.htmx.ajax('GET','/fragments/threads?'+new URLSearchParams({path:path||'',scope,active:activeThread||''}),{target:'#threads',swap:'innerHTML'});
  filterThreads();
}
function filterThreads(){$$('.thread').forEach(t=>{t.hidden=t.dataset.resolved==='true'&&!$('#show-resolved').checked;t.classList.toggle('active',Number(t.dataset.thread)===activeThread);const reply=t.querySelector('.reply-form');if(reply)reply.hidden=Number(t.dataset.thread)!==activeThread;});}
function showThread(id){
  activeThread=id;filterThreads();
  previewThreads();
  if(view)view.dispatch({effects:spansEffect.of(view.state.field(spanField))});
  $('.thread[data-thread="'+id+'"]')?.scrollIntoView({block:'nearest'});
}
async function jump(id,target=null){
  let t=target||currentThreads.find(t=>t.id===id);if(!t)return;
  if(t.path!==active){showThread(id);try{await openFile(t.path);}catch(error){notify(error.message,true);return;}}
  t=currentThreads.find(item=>item.id===id)||t;
  showThread(id);
  if(t.anchor_kind==='rendered'){
    if(entry().mode!=='rendered'){syncState();view?.destroy();view=null;entry().mode='rendered';mountDocument(entry());remember();}
    renderedJump=id;
    previewMessage('jump',{id});return;
  }
  if(t.anchor_status!=='attached'){notify('This passage needs reattachment. Select the new passage and click “Attach to selection”.');return;}
  if(!view){entry().mode='source';mountDocument(entry());view.dispatch({effects:spansEffect.of(spansFor(currentThreads,entry().content))});}
  const span=view.state.field(spanField).find(s=>s.id===id);
  if(entry().dirty&&!span){notify('Save your draft before navigating to this passage. Its local anchor is unavailable.');return;}
  const from=span?.from??toUnits(entry().content,t.start),to=span?.to??toUnits(entry().content,t.end);
  if(to<=view.state.doc.length){view.dispatch({selection:{anchor:from,head:to},effects:EditorView.scrollIntoView(from,{y:'center'})});view.focus();}
  $('.thread[data-thread="'+id+'"]')?.scrollIntoView({block:'nearest'});
}
let navigationQueue=Promise.resolve();
function navigate(direction){
  navigationQueue=navigationQueue.catch(()=>{}).then(async()=>{
    const threads=(await api('threads')).filter(t=>!t.resolved||$('#show-resolved').checked).sort((a,b)=>(a.path>b.path)-(a.path<b.path)||a.start-b.start||a.id-b.id);
    if(!threads.length)return;
    let at=threads.findIndex(t=>t.id===activeThread);
    if(at<0){const local=threads.map((t,i)=>t.path===active?i:-1).filter(i=>i>=0);at=local.length?(direction>0?local[0]:local.at(-1)):(direction>0?0:threads.length-1);}
    else at=(at+direction+threads.length)%threads.length;
    await jump(threads[at].id,threads[at]);
  });return navigationQueue;
}
async function startComment(){
  const e=entry();if(!e)return;
  if(renderedPreview&&renderedSelection)pending={path:e.path,render_anchor:renderedSelection.anchor,quote:renderedSelection.anchor.quote,content:e.content};
  else{if(!view||view.state.selection.main.empty)return;const {from,to}=view.state.selection.main;pending={path:e.path,start:selectionPoints(view.state,from),end:selectionPoints(view.state,to),quote:view.state.sliceDoc(from,to),content:view.state.sliceDoc()};}
  const location=selectionLocation();
  $('#selected-quote').textContent=pending.quote;$('#comment-body').value='';$('#comment-error').textContent='';$('#comment-dialog').show();
  if(location)placeNearSelection($('#comment-dialog'),location);
  else {$('#comment-dialog').style.left='calc(50% - 160px)';$('#comment-dialog').style.top='30%';}
  scheduleSelectionTools();$('#comment-body').focus();
}
async function submitComment(event){
  event.preventDefault();if(!pending||postingComment)return;
  const selection=pending,body=$('#comment-body').value,author=$('#author').value;
  if(selection.path!==active||selection.content!==(selection.render_anchor?entry()?.content:view?.state.sliceDoc()))throw new Error('The document changed. Select the passage again before commenting.');
  postingComment=true;$('#comment-submit').disabled=true;
  try{
    await saveActive();const e=entry();if(selection!==pending||selection.path!==active||selection.content!==(selection.render_anchor?e.content:view?.state.sliceDoc()))throw new Error('The selected passage changed. Select it again.');
    const result=await api('threads','POST',{path:selection.path,...(selection.render_anchor?{render_anchor:selection.render_anchor}:{start:selection.start,end:selection.end}),version:e.version,body,author});
    if(active===selection.path){closeComment();activeThread=result.id;await refreshThreads();showThread(result.id);view?.focus();}
    notify('Discussion created');
  }finally{postingComment=false;$('#comment-submit').disabled=false;}
}

function collapseJSON(editor){
  if(!editor)return;
  ensureSyntaxTree(editor.state,editor.state.doc.length,200);
  const effects=[];
  for(let i=1;i<=editor.state.doc.lines;i++){const line=editor.state.doc.line(i),range=foldable(editor.state,line.from,line.to);if(range)effects.push(foldEffect.of(range));}
  editor.dispatch({effects});
}
function jsonControls(editor){
  const tools=document.createElement('div');tools.className='json-fold-controls';
  const collapse=document.createElement('button'),expand=document.createElement('button');
  collapse.textContent='Collapse all';expand.textContent='Expand all';collapse.onclick=()=>collapseJSON(editor);expand.onclick=()=>unfoldAll(editor);tools.append(collapse,expand);return tools;
}
function mountJSONL(e){
  const container=document.createElement('div');container.className='jsonl-split';const left=document.createElement('div'),right=document.createElement('div');left.className='jsonl-raw';right.className='jsonl-detail';
  const rawTitle=document.createElement('div');rawTitle.className='viewer-heading';rawTitle.textContent='FULL JSONL · SELECT A ROW';left.append(rawTitle);
  const detailTitle=document.createElement('div');detailTitle.className='viewer-heading';right.append(detailTitle);
  const parent=document.createElement('div');parent.className='json-detail-editor';right.append(parent);
  const detail=new EditorView({state:EditorState.create({extensions:[basicSetup,json(),syntaxHighlighting(colors),theme(),EditorView.editable.of(false),EditorState.readOnly.of(true),EditorView.lineWrapping]}),parent});
  right.insertBefore(jsonControls(detail),parent);
  const lines=e.content.split(/\r?\n/);if(lines.at(-1)==='')lines.pop();
  function select(index){const raw=lines[index];let text;try{text=JSON.stringify(JSON.parse(raw),null,2);detailTitle.textContent='ROW '+(index+1)+' · FORMATTED JSON';}catch(error){text=raw;detailTitle.textContent='ROW '+(index+1)+' · MALFORMED: '+error.message;}detail.dispatch({changes:{from:0,to:detail.state.doc.length,insert:text}});left.querySelectorAll('.jsonl-row').forEach((b,i)=>b.classList.toggle('selected',i===index));}
  lines.forEach((line,index)=>{const button=document.createElement('button');button.className='jsonl-row';button.dataset.row=index;let malformed=false;try{JSON.parse(line);}catch{malformed=true;}if(malformed)button.classList.add('malformed');const number=document.createElement('span');number.className='row-number';number.textContent=(index+1)+(malformed?' !':'');const source=document.createElement('code');source.textContent=line||'[empty line]';button.append(number,source);button.onclick=()=>select(index);left.append(button);});
   const search=document.createElement('div');search.className='jsonl-search';search.hidden=true;
   const input=document.createElement('input');input.placeholder='Find in JSONL…';input.setAttribute('aria-label','Find in JSONL');
   const count=document.createElement('span'),previous=document.createElement('button'),next=document.createElement('button'),close=document.createElement('button');previous.textContent='↑';next.textContent='↓';close.textContent='×';previous.setAttribute('aria-label','Previous match');next.setAttribute('aria-label','Next match');close.setAttribute('aria-label','Close JSONL search');
   let matches=[],at=-1;
   function go(direction){if(!matches.length)return;at=(at+direction+matches.length)%matches.length;const index=matches[at];select(index);left.querySelector('[data-row="'+index+'"]').scrollIntoView({block:'center'});count.textContent=(at+1)+' / '+matches.length;}
   function find(){const query=input.value.toLowerCase();matches=[];at=-1;left.querySelectorAll('.jsonl-row').forEach((row,index)=>{const hit=!!query&&lines[index].toLowerCase().includes(query);row.classList.toggle('jsonl-match',hit);if(hit)matches.push(index);});count.textContent=matches.length?'':'No matches';go(1);}
   input.oninput=find;input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();go(event.shiftKey?-1:1);}if(event.key==='Escape'){event.preventDefault();search.hidden=true;left.focus();}};
   previous.onclick=()=>go(-1);next.onclick=()=>go(1);close.onclick=()=>{search.hidden=true;left.focus();};search.append(input,count,previous,next,close);left.tabIndex=0;left.insertBefore(search,rawTitle.nextSibling);
   jsonlSearch=()=>{search.hidden=false;input.focus();input.select();};
   container.append(left,right);$('#surface').append(container);if(lines.length)select(0);cleanup=()=>{jsonlSearch=null;detail.destroy();};
}
async function mountImage(e){
  const host=document.createElement('div');host.className='image-view';
  const tools=document.createElement('div');tools.className='image-tools';
  const viewport=document.createElement('div');viewport.className='image-viewport';viewport.tabIndex=0;
  const stage=document.createElement('div');stage.className='image-stage';
  const img=document.createElement('img');img.alt=e.path;img.draggable=false;
  const status=document.createElement('div');status.className='image-status';status.setAttribute('role','status');status.textContent='Loading image…';
  stage.append(img);viewport.append(stage);host.append(tools,viewport,status);$('#surface').append(host);
  let scale=1,fitted=true,url,observer;
  const label=document.createElement('span');
  function resize(next){
    const before=scale;scale=Math.max(.01,Math.min(16,next));
    const x=(viewport.scrollLeft+viewport.clientWidth/2)/before,y=(viewport.scrollTop+viewport.clientHeight/2)/before;
    img.style.width=img.naturalWidth*scale+'px';img.style.height=img.naturalHeight*scale+'px';
    stage.style.width=Math.max(viewport.clientWidth,img.naturalWidth*scale)+'px';stage.style.height=Math.max(viewport.clientHeight,img.naturalHeight*scale)+'px';
    viewport.scrollLeft=x*scale-viewport.clientWidth/2;viewport.scrollTop=y*scale-viewport.clientHeight/2;
    label.textContent=Math.round(scale*100)+'% · '+img.naturalWidth+' × '+img.naturalHeight;
  }
  function fit(){fitted=true;resize(Math.min((viewport.clientWidth-32)/img.naturalWidth,(viewport.clientHeight-32)/img.naturalHeight,1));}
  for(const [name,action] of [['Zoom out',()=>{fitted=false;resize(scale/1.25);}],['Zoom in',()=>{fitted=false;resize(scale*1.25);}],['Fit to view',fit],['Actual size',()=>{fitted=false;resize(1);}]] ){
    const button=document.createElement('button');button.textContent=name;button.onclick=action;tools.append(button);
  }
  tools.append(label);
  viewport.addEventListener('wheel',event=>{event.preventDefault();fitted=false;resize(scale*Math.exp(-event.deltaY*.002));},{passive:false});
  let drag=null;
  viewport.onpointerdown=event=>{if(event.button!==0)return;drag={x:event.clientX,y:event.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging');event.preventDefault();};
  viewport.onpointermove=event=>{if(drag){viewport.scrollLeft=drag.left+drag.x-event.clientX;viewport.scrollTop=drag.top+drag.y-event.clientY;}};
  viewport.onpointerup=viewport.onpointercancel=()=>{drag=null;viewport.classList.remove('dragging');};
  cleanup=()=>{observer?.disconnect();if(url)URL.revokeObjectURL(url);};
  try{
    e.version=(await api('stat?'+new URLSearchParams({path:e.path}))).version;
    const buffer=await binary(e.path),type=ext(e.path)==='svg'?'image/svg+xml':ext(e.path)==='png'?'image/png':'image/jpeg';
    url=URL.createObjectURL(new Blob([buffer],{type}));img.src=url;await img.decode();
    status.remove();fit();observer=new ResizeObserver(()=>{if(fitted)fit();else resize(scale);});observer.observe(viewport);
  }catch(error){status.textContent='Unable to display this image: '+error.message;img.hidden=true;tools.querySelectorAll('button').forEach(button=>button.disabled=true);}
}

async function mountSTL(e){
  const host=document.createElement('div');host.className='stl-view';const tools=document.createElement('div');tools.className='stl-tools';const fit=document.createElement('button');fit.textContent='Fit to view';const info=document.createElement('span');info.textContent='Orbit: drag · Pan: right drag · Zoom: scroll';tools.append(fit,info);host.append(tools);$('#surface').append(host);
  const status=document.createElement('div');status.className='stl-status';status.setAttribute('role','status');status.textContent='Loading model…';host.append(status);fit.disabled=true;
  let geometry, material, renderer, controls, observer;
  const dispose=()=>{observer?.disconnect();renderer?.setAnimationLoop?.(null);controls?.dispose();geometry?.dispose();material?.dispose();renderer?.dispose?.();};
  cleanup=dispose;
  try{
  e.version=(await api('stat?'+new URLSearchParams({path:e.path}))).version;
  const buffer=await binary(e.path);geometry=new STLLoader().parse(buffer);
  const count=geometry.attributes.position?.count;
  if(!count||count%3)throw new Error('No complete triangles found in STL.');
  geometry.computeBoundingBox();
  const bounds=geometry.boundingBox;
  if(![...bounds.min.toArray(),...bounds.max.toArray()].every(Number.isFinite))throw new Error('STL contains invalid vertex coordinates.');
  geometry.center();geometry.computeBoundingSphere();
  const radius=geometry.boundingSphere.radius;
  if(!Number.isFinite(radius)||radius<=0)throw new Error('STL has no visible surface.');
  // Keep the scene in a predictable range, even for microscopic or huge models.
  geometry.scale(1/radius,1/radius,1/radius);geometry.computeVertexNormals();geometry.computeBoundingSphere();
  const canvas=document.createElement('canvas');let context=null;
  try{context=canvas.getContext('webgl2',{antialias:true,alpha:true});}catch{}
  if(context){
    try{renderer=new THREE.WebGLRenderer({canvas,context,antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));}catch{context=null;}
  }
  const software=!context;
  if(software){
    renderer=new SVGRenderer();
    // Bound software-rendering work so large files do not freeze the editor.
    const limit=12000,triangles=count/3;
    if(triangles>limit){
      const source=geometry.attributes.position.array,positions=new Float32Array(limit*9);
      for(let i=0;i<limit;i++)positions.set(source.subarray(Math.floor(i*triangles/limit)*9,Math.floor(i*triangles/limit)*9+9),i*9);
      geometry.dispose();geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.computeVertexNormals();
    }
  }
  host.dataset.renderer=software?'software':'webgl';host.append(renderer.domElement);
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(45,1,0.01,1000);
  controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=!software;controls.minDistance=0.05;controls.maxDistance=100;
  material=new THREE.MeshStandardMaterial({color:0x9470c2,metalness:0.08,roughness:0.75,side:THREE.DoubleSide});scene.add(new THREE.Mesh(geometry,material));scene.add(new THREE.AmbientLight(0xffffff,0.65));scene.add(new THREE.HemisphereLight(0xffffff,0x554766,1.25));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(4,7,8);scene.add(light);
  const render=()=>renderer.render(scene,camera);
  function fitView(){const halfFov=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(camera.aspect,1));const distance=1.2/Math.sin(halfFov);camera.position.copy(new THREE.Vector3(2.5,1.7,2.5).normalize().multiplyScalar(distance));controls.target.set(0,0,0);controls.update();render();}
  function resize(){const w=Math.max(host.clientWidth,1),h=Math.max(host.clientHeight,1);renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render();}
  fit.onclick=fitView;resize();fitView();fit.disabled=false;status.remove();
  observer=new ResizeObserver(resize);observer.observe(host);
  if(software)controls.addEventListener('change',render);
  else{
    renderer.setAnimationLoop(()=>{controls.update();render();});
    renderer.domElement.addEventListener('webglcontextlost',()=>{status.textContent='The graphics context was lost. Reopen this file to reload the viewer.';host.append(status);});
    renderer.domElement.addEventListener('webglcontextrestored',()=>status.remove());
  }
  const stats=document.createElement('span');stats.className='stl-stats';stats.textContent=(count/3).toLocaleString()+' triangles';
  if(software)stats.textContent+=' · Software preview'+(count/3>12000?' · detail reduced to 12,000 triangles':'');
  host.append(stats);
  }catch(error){dispose();status.textContent='Unable to display this STL: '+error.message;fit.disabled=true;notify(error.message,true);}
}

async function poll(){
  if(polling||saving||switching||document.hidden)return;polling=true;
  try{
    for(const e of [...tabs.values()]){
      try{
        const requestedVersion=e.version;
        if(ext(e.path)==='stl'||isImage(e.path)){
          const disk=await api('stat?'+new URLSearchParams({path:e.path}));
          if(e.version!==requestedVersion||switching||saving)continue;
          if(disk.version!==e.version){e.version=disk.version;if(e.path===active){cleanup();cleanup=()=>{};$('#surface').replaceChildren();if(isImage(e.path))await mountImage(e);else await mountSTL(e);notify('Reloaded the external viewer change');}}
          continue;
        }
        const disk=await api('file?'+new URLSearchParams({path:e.path}));
        if(e.version!==requestedVersion||switching||saving)continue;
        if(disk.version===e.version)continue;
        if(e.dirty){e.conflict=disk;if(e.path===active)notify('External change detected; your draft is preserved.',true);}
        else{e.content=disk.content;e.diskContent=disk.content;e.version=disk.version;e.state=null;e.conflict=null;if(e.path===active){view?.destroy();view=null;cleanup();cleanup=()=>{};$('#surface').replaceChildren();if(ext(e.path)==='jsonl')mountJSONL(e);else mountDocument(e);notify('Reloaded the external change');}}
      }catch(error){if(error.status===404){e.conflict={deleted:true};if(e.path===active)notify(error.message,true);}else notify(error.message,true);}
    }
    updateToolbar();
    await refreshBaseline();
    // Avoid replacing a reply field while the user is writing.
    if(!$('#threads').contains(document.activeElement)&&!$$('.reply-form textarea').some(t=>t.value))await refreshThreads();
  }catch(e){notify(e.message,true);}finally{polling=false;}
}

async function showGit(){
  const status=await api('git');const host=$('#git-files');host.replaceChildren();$('#git-diff').textContent='';
  if(!status.repository){const p=document.createElement('p');p.textContent='This workspace has no Git repository.';const init=document.createElement('button');init.textContent='Initialize Git in this directory';init.onclick=guard(async()=>{await api('git/init','POST',{});await showGit();});host.append(p,init);}
  else if(!status.files.length)host.textContent='No changes on disk.';
  else status.files.forEach(f=>{const label=document.createElement('label');label.className='git-file';const check=document.createElement('input');check.type='checkbox';check.value=f.path;const text=document.createElement('span');text.textContent=f.status+'  '+f.path;label.append(check,text);host.append(label);});
  $('#checkpoint').disabled=!status.repository;$('#inspect-diff').disabled=!status.files.length;if(!$('#git-dialog').open)$('#git-dialog').showModal();
}
function selectedGit(){return $$('#git-files input:checked').map(c=>c.value);}

document.addEventListener('htmx:configRequest',event=>event.detail.headers['X-Looking-Glass-Token']=token);
window.addEventListener('message',guard(async event=>{
  const preview=renderedPreview,message=event.data;
  if(!preview||event.source!==preview.frame.contentWindow||event.origin!=='null'||message?.lookingGlass!==preview.channel)return;
  if(message.type==='ready'){preview.ready=true;previewThreads();if(renderedJump)previewMessage('jump',{id:renderedJump});}
  if(message.type==='selection'){
    const selection=message.selection;
    renderedSelection=selection&&typeof selection.anchor?.quote==='string'&&selection.anchor.quote.length<=50000&&['left','right','top','bottom'].every(key=>Number.isFinite(selection.rect?.[key]))?selection:null;
    updateToolbar();
  }
  if(message.type==='comment')await startComment();
  if(message.type==='quick-open')await showQuickOpen();
  if(message.type==='thread'&&currentThreads.some(t=>t.id===message.id&&t.anchor_kind==='rendered'))showThread(message.id);
  if(message.type==='anchors'&&Array.isArray(message.statuses)){
    let changed=false;
    for(const status of message.statuses){const thread=currentThreads.find(t=>t.id===status.id&&t.anchor_kind==='rendered');if(!thread||typeof status.attached!=='boolean')continue;
      if(renderedPreview!==preview||!tabs.has(preview.path))return;
      const next=status.attached?'attached':'needs_reattachment';if(thread.anchor_status===next)continue;
      await api('threads/'+thread.id,'PATCH',{render_attached:status.attached,version:tabs.get(preview.path).version});thread.anchor_status=next;changed=true;
    }
    if(changed&&renderedPreview===preview)await refreshThreads();
  }
}));
document.addEventListener('htmx:beforeSwap',event=>{if(event.detail.target.id==='threads'){const query=new URL(event.detail.xhr.responseURL,location.href).searchParams;if(query.get('path')!==(active||'')||query.get('scope')!==threadScope())event.detail.shouldSwap=false;}});
document.addEventListener('htmx:afterSwap',event=>{if(event.detail.target.id==='file-tree'){$$('.file-folder').forEach(folder=>folder.open=expandedFolders.has(folder.dataset.directory));filterFiles();renderTabs();}if(event.detail.target.id==='threads')filterThreads();});
document.addEventListener('toggle',event=>{const folder=event.target;if(!folder.matches?.('.file-folder')||$('#file-filter').value)return;if(folder.open)expandedFolders.add(folder.dataset.directory);else expandedFolders.delete(folder.dataset.directory);localStorage.setItem('looking-glass-folders:'+root,JSON.stringify([...expandedFolders]));},true);
document.addEventListener('htmx:responseError',event=>notify('Sidebar request failed: '+event.detail.xhr.status,true));
function beginSelection(event){
  if(event.button===0&&event.target.closest?.('#editor')){selectingText=true;scheduleSelectionTools();}
}
function settleSelection(){
  if(!selectingText)return;selectingText=false;
  // Let CodeMirror finish its mouse/DOM selection update before revealing syntax.
  const editor=view;
  requestAnimationFrame(()=>{if(view&&view===editor)view.dispatch({effects:selectionSettled.of(null)});scheduleSelectionTools();});
}
// CodeMirror selects through mouse events. Pointer events alone can leave this
// UI's drag state stuck after an interrupted gesture or an out-of-window release.
for(const type of ['pointerdown','mousedown'])document.addEventListener(type,beginSelection,true);
for(const type of ['pointerup','mouseup','pointercancel','dragend'])window.addEventListener(type,settleSelection,true);
for(const type of ['pointermove','mousemove'])window.addEventListener(type,event=>{
  if(selectingText&&(event.buttons&1)===0)settleSelection();
},true);
window.addEventListener('blur',settleSelection);
document.addEventListener('visibilitychange',()=>{if(document.hidden)settleSelection();});
document.addEventListener('scroll',scheduleSelectionTools,true);
window.addEventListener('resize',()=>{scheduleSelectionTools();if($('#comment-dialog').open){const location=selectionLocation();if(location)placeNearSelection($('#comment-dialog'),location);}});
document.addEventListener('keydown',event=>{
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='p'){event.preventDefault();event.stopPropagation();guard(showQuickOpen)();}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='f'&&jsonlSearch&&!document.querySelector('dialog:modal')){event.preventDefault();jsonlSearch();}
  if(event.key==='Escape'&&$('#comment-dialog').open){event.preventDefault();closeComment();view?.focus();}
},true);
document.addEventListener('click',guard(async event=>{
  const file=event.target.closest('.file-entry');if(file)await openFile(file.dataset.path);
  const close=event.target.closest('[data-close]');if(close)close.closest('dialog').close();
  const action=event.target.closest('[data-action]');if(!action)return;
  const id=Number(action.closest('.thread').dataset.thread),t=currentThreads.find(t=>t.id===id);
  if(action.dataset.action.endsWith('-attachment')){
    const attachmentId=Number(action.closest('[data-attachment]').dataset.attachment),item=t.attachments.find(a=>a.id===attachmentId);
    if(action.dataset.action==='rename-attachment'){const name=prompt('Attachment name',item.name);if(name!==null){await api('attachments/'+attachmentId,'PATCH',{name});await refreshThreads();}return;}
    if(action.dataset.action==='delete-attachment'){if(confirm('Remove '+item.name+'?')){await api('attachments/'+attachmentId,'DELETE');await refreshThreads();}return;}
    const response=await fetch('/api/attachments/'+attachmentId,{headers:{'X-Looking-Glass-Token':token}});
    if(!response.ok)throw new Error((await response.json()).error);
    const url=URL.createObjectURL(await response.blob());
    if(action.dataset.action==='preview-attachment'){
      $('#attachment-title').textContent=item.name;$('#attachment-image').src=url;$('#attachment-image').alt=item.name;
      $('#attachment-dialog').addEventListener('close',()=>{URL.revokeObjectURL(url);$('#attachment-image').removeAttribute('src');},{once:true});$('#attachment-dialog').showModal();
    }else{const link=document.createElement('a');link.href=url;link.download=item.name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}return;
  }
  if(action.dataset.action==='jump')await jump(id);
  if(action.dataset.action==='resolve'){await api('threads/'+id,'PATCH',{resolved:!t.resolved});await refreshThreads();}
  if(action.dataset.action==='delete-thread'||action.dataset.action==='delete-message'){
    const whole=action.dataset.action==='delete-thread';if(!confirm(whole?'Delete this thread and all its comments?':'Delete this comment?'))return;
    await api('threads/'+id+(whole?'':'/messages/'+action.dataset.message),'DELETE');await refreshThreads();
    if(!currentThreads.some(t=>t.id===activeThread))activeThread=null;
    if(view)view.dispatch({effects:spansEffect.of(view.state.field(spanField).filter(span=>currentThreads.some(t=>t.id===span.id)))});
    notify(whole?'Thread deleted':'Comment deleted');
  }
  if(action.dataset.action==='reattach'){
    if(t.path!==active){await jump(id);notify('Select the new passage in this file, then attach the thread.');return;}
    if(t.anchor_kind==='rendered'){if(!renderedSelection)throw new Error('Select the new passage in the rendered report first.');await saveActive();await api('threads/'+id,'PATCH',{render_anchor:renderedSelection.anchor,version:entry().version});await refreshThreads();await jump(id);return;}
    if(!view||view.state.selection.main.empty)throw new Error('Select the new passage in the editor first.');const {from,to}=view.state.selection.main;const start=selectionPoints(view.state,from),end=selectionPoints(view.state,to);await saveActive();await api('threads/'+id,'PATCH',{start,end,version:entry().version});await refreshThreads();await jump(id);
  }
}));
document.addEventListener('submit',event=>{
  if(event.target.matches('.reply-form')){event.preventDefault();guard(async()=>{const id=Number(event.target.closest('.thread').dataset.thread);await api('threads/'+id+'/replies','POST',{author:$('#author').value,body:event.target.querySelector('textarea').value});await refreshThreads();notify('Reply added');})();}
});
$('#comment-form').onsubmit=event=>{submitComment(event).catch(error=>{$('#comment-error').textContent=error.message;notify(error.message,true);});};
$('#comment-dialog').addEventListener('close',()=>{if(!$('#comment-dialog').open&&pending?.path)pending=null;scheduleSelectionTools();});
$('#comment-cancel').onclick=()=>{closeComment();view?.focus();};
$('#comment-body').addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();$('#comment-form').requestSubmit();}});
$('#selection-tools').onmousedown=event=>event.preventDefault();
$('#selection-comment').onclick=guard(startComment);
$('#selection-thread').onclick=()=>showThread(Number($('#selection-thread').dataset.thread));
$('#json-format').onclick=guard(()=>{if(!view||ext(active)!=='json')return;const content=formatJSON(view.state.sliceDoc(),view.state.lineBreak);view.dispatch({changes:{from:0,to:view.state.doc.length,insert:content},annotations:isolateHistory.of('full'),userEvent:'input.format'});view.focus();});
$('#json-collapse').onclick=()=>collapseJSON(view);$('#json-expand').onclick=()=>{if(view)unfoldAll(view);};
$('#download-file').onclick=guard(()=>{
  syncState();const e=entry();if(!e||!['html','htm','jsonl'].includes(ext(e.path)))return;
  const type=ext(e.path)==='jsonl'?'application/x-ndjson;charset=utf-8':'text/html;charset=utf-8';
  const url=URL.createObjectURL(new Blob([e.content],{type})),link=document.createElement('a');
  link.href=url;link.download=e.path.split('/').pop();document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('#save').onclick=guard(saveActive);$('#annotate').onclick=guard(startComment);
$('#previous').onclick=guard(()=>navigate(-1));$('#next').onclick=guard(()=>navigate(1));$('#show-resolved').onchange=filterThreads;
$('#thread-scope').checked=localStorage.getItem('looking-glass-thread-scope:'+root)==='all';
$('#thread-scope').onchange=guard(async()=>{localStorage.setItem('looking-glass-thread-scope:'+root,threadScope());await refreshThreads();});
async function setMode(value){const e=entry();syncState();e.mode=value;view?.destroy();view=null;mountDocument(e);await refreshThreads();remember();}
$('#mode').onchange=guard(()=>setMode($('#mode').value));
$('#html-toggle').onclick=guard(()=>setMode(entry().mode==='rendered'?'source':'rendered'));
$('#theme').onclick=()=>{const value=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=value;localStorage.setItem('looking-glass-theme',value);$('#theme').textContent=value==='dark'?'Light mode':'Dark mode';if(view)view.dispatch({effects:themeSlot.reconfigure(theme())});};
$('#font-smaller').onclick=()=>{fontStep=Math.max(-4,fontStep-1);localStorage.setItem('looking-glass-font-step',fontStep);applyFontSize();};
$('#font-larger').onclick=()=>{fontStep=Math.min(12,fontStep+1);localStorage.setItem('looking-glass-font-step',fontStep);applyFontSize();};
applyFontSize();
function filterFiles(){const query=$('#file-filter').value.toLowerCase();$$('.file-entry').forEach(b=>b.hidden=!b.dataset.path.toLowerCase().includes(query));$$('.file-folder').reverse().forEach(folder=>{folder.hidden=!!query&&![...folder.querySelectorAll('.file-entry')].some(b=>!b.hidden);folder.open=query?!folder.hidden:expandedFolders.has(folder.dataset.directory);});}
$('#file-filter').oninput=filterFiles;$('#refresh-files').onclick=()=>window.htmx.trigger('#file-tree','refresh');
const fileResize=$('#file-resize');
let sidebarWidth=Number(localStorage.getItem('looking-glass-sidebar-width'))||$('.file-sidebar').getBoundingClientRect().width;
function sidebarLimits(){return {min:120,max:Math.max(120,Math.min(600,innerWidth-$('.discussion-sidebar').getBoundingClientRect().width-(innerWidth<=800?260:innerWidth<=1100?300:350)))};}
function sizeSidebar(){const {min,max}=sidebarLimits(),width=Math.max(min,Math.min(max,sidebarWidth));document.documentElement.style.setProperty('--file-sidebar-width',width+'px');fileResize.setAttribute('aria-valuemin',min);fileResize.setAttribute('aria-valuemax',Math.floor(max));fileResize.setAttribute('aria-valuenow',Math.round(width));}
function finishResize(){document.body.classList.remove('sidebar-resizing');localStorage.setItem('looking-glass-sidebar-width',String(sidebarWidth));}
fileResize.onpointerdown=event=>{if(event.button!==0)return;event.preventDefault();fileResize.setPointerCapture(event.pointerId);document.body.classList.add('sidebar-resizing');};
fileResize.onpointermove=event=>{if(!fileResize.hasPointerCapture(event.pointerId))return;const {min,max}=sidebarLimits();sidebarWidth=Math.max(min,Math.min(max,event.clientX-$('.workspace').getBoundingClientRect().left));sizeSidebar();};
fileResize.onpointerup=fileResize.onpointercancel=fileResize.onlostpointercapture=finishResize;
fileResize.onkeydown=event=>{const {min,max}=sidebarLimits();if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();sidebarWidth=event.key==='Home'?min:event.key==='End'?max:Math.max(min,Math.min(max,sidebarWidth+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?50:10)));sizeSidebar();finishResize();};
fileResize.ondblclick=()=>{sidebarWidth=225;sizeSidebar();finishResize();};
window.addEventListener('resize',sizeSidebar);sizeSidebar();
$('#collapse-files').onclick=()=>{expandedFolders.clear();localStorage.setItem('looking-glass-folders:'+root,'[]');$('#file-filter').value='';filterFiles();};
function fuzzyScore(path,query){const text=path.toLowerCase();let cursor=0,score=0,previous=-2;for(const character of query.toLowerCase().replace(/\s/g,'')){const index=text.indexOf(character,cursor);if(index<0)return null;score+=index===previous+1?8:0;score+=index===0||'/._-'.includes(text[index-1])?12:0;score-=index-cursor;previous=index;cursor=index+1;}return score-text.length/100;}
function renderQuickResults(){const query=$('#quick-query').value;quickMatches=quickPaths.map(path=>({path,score:fuzzyScore(path,query)})).filter(item=>item.score!==null).sort((a,b)=>b.score-a.score||a.path.localeCompare(b.path)).slice(0,50);quickIndex=Math.min(quickIndex,Math.max(0,quickMatches.length-1));$('#quick-results').replaceChildren(...quickMatches.map((item,index)=>{const button=document.createElement('button');button.textContent=item.path;button.id='quick-option-'+index;button.setAttribute('role','option');button.setAttribute('aria-selected',String(index===quickIndex));button.classList.toggle('selected',index===quickIndex);button.onclick=guard(async()=>{await openFile(item.path);$('#quick-dialog').close();view?.focus();});return button;}));if(!quickMatches.length)$('#quick-results').textContent='No matching files.';$('#quick-query').setAttribute('aria-activedescendant',quickMatches.length?'quick-option-'+quickIndex:'');$('#quick-results .selected')?.scrollIntoView({block:'nearest'});}
async function showQuickOpen(){closeComment();if(!$('#quick-dialog').open)$('#quick-dialog').showModal();$('#quick-query').value='';quickIndex=0;quickPaths=[...new Set([...$$('.file-entry').map(b=>b.dataset.path),...tabs.keys()])];renderQuickResults();$('#quick-query').focus();const workspace=await api('workspace');if($('#quick-dialog').open){quickPaths=[...new Set([...workspace.files,...tabs.keys()])];renderQuickResults();}}
$('#quick-query').oninput=()=>{quickIndex=0;renderQuickResults();};
$('#quick-query').onkeydown=event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();quickIndex=(quickIndex+(event.key==='ArrowDown'?1:-1)+quickMatches.length)%Math.max(1,quickMatches.length);renderQuickResults();}if(event.key==='Enter'){event.preventDefault();$('#quick-results .selected')?.click();}};
$('#agent-open').onclick=guard(async()=>{const result=await api('agent-instructions');$('#agent-instructions').value=result.instructions;$('#agent-dialog').showModal();});
$('#agent-copy').onclick=guard(async()=>{await navigator.clipboard.writeText($('#agent-instructions').value);notify('Agent instructions copied');$('#agent-dialog').close();});
$('#author').value=localStorage.getItem('looking-glass-author')||'Altay';$('#author').onchange=()=>localStorage.setItem('looking-glass-author',$('#author').value);
$('#reload-disk').onclick=guard(async()=>{
  const e=entry();if(!e)return;if(e.dirty&&!confirm('Discard your unsaved edits and reload the current disk file?'))return;const disk=await api('file?'+new URLSearchParams({path:e.path}));e.content=disk.content;e.diskContent=disk.content;e.version=disk.version;e.dirty=false;e.conflict=null;e.state=null;view?.destroy();view=null;mountDocument(e);await refreshThreads();renderTabs();notify('Reloaded from disk');
});
$('#copy-draft').onclick=guard(async()=>{await navigator.clipboard.writeText(entry().content);notify('Draft copied');});
$('#merge-disk').onclick=guard(async()=>{const e=entry();const disk=await api('file?'+new URLSearchParams({path:e.path}));pending={mergePath:e.path,disk};$('#disk-text').textContent=disk.content;$('#merge-text').value=e.content;$('#merge-dialog').showModal();});
$('#accept-merge').onclick=guard(async()=>{const e=entry();if(pending?.mergePath!==e.path)throw new Error('Open the original file to finish merging.');e.version=pending.disk.version;e.diskContent=pending.disk.content;e.content=$('#merge-text').value;e.dirty=e.content!==e.diskContent;e.conflict=null;e.state=null;view?.destroy();view=null;mountDocument(e);$('#merge-dialog').close();pending=null;renderTabs();updateToolbar();notify('Merged draft ready. Save to write it to disk.');});
$('#git-open').onclick=guard(showGit);$('#inspect-diff').onclick=guard(async()=>{const result=await api('git/diff','POST',{paths:selectedGit()});$('#git-diff').textContent=result.diff;});
$('#checkpoint').onclick=guard(async()=>{const paths=selectedGit();if(paths.some(p=>tabs.get(p)?.dirty))throw new Error('Save your edits in the selected files before checkpointing.');const result=await api('git/checkpoint','POST',{paths,message:$('#checkpoint-name').value});await refreshBaseline();$('#git-dialog').close();notify('Checkpoint '+result.commit.slice(0,8)+' created');});
// Dialog errors stay inside the dialog, next to the path the user typed.
const dialogGuard=(error,fn)=>(...args)=>Promise.resolve().then(()=>{$(error).textContent='';return fn(...args);}).catch(e=>{$(error).textContent=e.message;});
$('#file-open').onclick=()=>{$('#file-error').textContent='';$('#file-dialog').showModal();$('#file-path').select();};
$('#file-form').onsubmit=event=>{event.preventDefault();dialogGuard('#file-error',async()=>{const {path}=await api('locate?'+new URLSearchParams({path:$('#file-path').value}));await openFile(path);$('#file-dialog').close();})();};
async function browse(path){
  const listing=await api('directories?'+new URLSearchParams({path}));$('#directory-path').value=listing.path;
  const entries=[...(listing.parent?[['..',listing.parent]]:[]),...listing.directories.map(name=>[name+'/',listing.path.replace(/\/$/,'')+'/'+name])];
  $('#directory-list').replaceChildren(...entries.map(([label,target])=>{const b=document.createElement('button');b.type='button';b.className='directory-entry'+(label.startsWith('.')&&label!=='..'?' hidden-dir':'');b.textContent=label;b.onclick=dialogGuard('#directory-error',()=>browse(target));return b;}));
  $('#directory-list').scrollTop=0;
}
$('#directory-open').onclick=dialogGuard('#directory-error',async()=>{$('#directory-dialog').showModal();await browse(root);});
$('#directory-form').onsubmit=event=>{event.preventDefault();dialogGuard('#directory-error',()=>browse($('#directory-path').value))();};
$('#directory-choose').onclick=dialogGuard('#directory-error',async()=>{
  if([...tabs.values()].some(e=>e.dirty))throw new Error('Save or close unsaved tabs before you switch directories.');
  await api('workspace','POST',{path:$('#directory-path').value});location.reload();
});
window.addEventListener('beforeunload',event=>{if([...tabs.values()].some(e=>e.dirty)){event.preventDefault();event.returnValue='';}});
document.documentElement.dataset.theme=localStorage.getItem('looking-glass-theme')||'light';$('#theme').textContent=document.documentElement.dataset.theme==='dark'?'Light mode':'Dark mode';
// Restore tab metadata only; unsaved text is never silently persisted over disk.
let restored={tabs:[]};try{restored=JSON.parse(localStorage.getItem('looking-glass-tabs:'+root)||'{"tabs":[]}');if(Array.isArray(restored))restored={tabs:restored};}catch{}
guard(async()=>{
  switching=true;
  try{
    const results=await Promise.allSettled((restored.tabs||[]).map(async item=>{
      const type=ext(item.path),file=type==='stl'||isImage(item.path)?{content:'',version:null}:await api('file?'+new URLSearchParams({path:item.path}));
      return {path:item.path,...file,diskContent:file.content,dirty:false,conflict:null,pinned:!!item.pinned,state:null,mode:item.mode||'source'};
    }));
    for(const result of results)if(result.status==='fulfilled')tabs.set(result.value.path,result.value);
  }finally{switching=false;}
  const requested=queuedFile;queuedFile=null;
  if(requested)await openFile(requested);
  else if(tabs.size)await openFile(tabs.has(restored.active)?restored.active:[...tabs.keys()].at(-1));
  renderTabs();if(!active)await refreshThreads();
})();
setInterval(poll,2200);setInterval(()=>{if(!document.hidden)window.htmx.trigger('#file-tree','refresh');},12000);

document.addEventListener('change',guard(async event=>{
  if(!event.target.matches('.attach-files'))return;
  const input=event.target,id=input.closest('.thread').dataset.thread;
  input.disabled=true;
  try{for(const file of input.files){
    const body=new FormData();body.append('file',file);
    const response=await fetch('/api/threads/'+id+'/attachments',{method:'POST',headers:{'X-Looking-Glass-Token':token},body});
    if(!response.ok)throw new Error((await response.json()).error);
  }await refreshThreads();notify('Files attached');}finally{input.disabled=false;input.value='';}
}));
