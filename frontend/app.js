import {basicSetup} from 'codemirror';
import {EditorState, StateEffect, StateField, Compartment} from '@codemirror/state';
import {EditorView, Decoration, ViewPlugin, keymap, WidgetType} from '@codemirror/view';
import {undo, redo, indentWithTab} from '@codemirror/commands';
import {openSearchPanel} from '@codemirror/search';
import {markdown} from '@codemirror/lang-markdown';
import {python} from '@codemirror/lang-python';
import {html} from '@codemirror/lang-html';
import {json} from '@codemirror/lang-json';
import {StreamLanguage, syntaxTree, syntaxHighlighting, HighlightStyle} from '@codemirror/language';
import {shell} from '@codemirror/legacy-modes/mode/shell';
import {tags} from '@lezer/highlight';
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
let active = null, view = null, cleanup = () => {}, currentThreads = [], activeThread = null, pending = null;
let polling = false, saving = false, switching = false, refreshNumber = 0, queuedFile = null;
const themeSlot = new Compartment(), liveSlot = new Compartment();
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
  '.cm-scroller':{fontFamily:'var(--mono)',lineHeight:'1.7'},
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

class Bullet extends WidgetType {toDOM(){const el=document.createElement('span');el.textContent='• ';return el;}}
function liveDecorations(v) {
  const ranges=[], doc=v.state.doc, selected=v.state.selection.main;
  const activeFrom=doc.lineAt(selected.from).from, activeTo=doc.lineAt(selected.to).to;
  syntaxTree(v.state).iterate({
    enter(node){
      const name=node.name, a=node.from, b=node.to;
      if(b<=a) return;
      const line=doc.lineAt(a), isActive=line.from<=activeTo && line.to>=activeFrom;
      if(/^ATXHeading[1-6]$/.test(name)) ranges.push(Decoration.line({class:'md-heading md-h'+name.slice(-1)}).range(line.from));
      if(name==='Blockquote') ranges.push(Decoration.line({class:'md-quote'}).range(line.from));
      if(name==='StrongEmphasis') ranges.push(Decoration.mark({class:'md-strong'}).range(a,b));
      if(name==='Emphasis') ranges.push(Decoration.mark({class:'md-emphasis'}).range(a,b));
      if(name==='InlineCode'||name==='CodeText') ranges.push(Decoration.mark({class:'md-code'}).range(a,b));
      if(name==='Link') ranges.push(Decoration.mark({class:'md-link'}).range(a,b));
      if(isActive) return;
      if(['HeaderMark','EmphasisMark','CodeMark','QuoteMark','LinkMark'].includes(name) && doc.lineAt(b).number===line.number)
        ranges.push(Decoration.replace({}).range(a,b));
      if(name==='URL' && doc.lineAt(b).number===line.number) ranges.push(Decoration.replace({}).range(a,b));
      if(name==='ListMark') ranges.push(Decoration.replace({widget:new Bullet()}).range(a,b));
    }
  });
  return Decoration.set(ranges,true);
}
const liveMarkdown = ViewPlugin.fromClass(class {
  constructor(v){this.decorations=liveDecorations(v);}
  update(u){if(u.docChanged||u.selectionSet||u.viewportChanged)this.decorations=liveDecorations(u.view);}
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
function entry(){return active?tabs.get(active):null;}
function remember(){localStorage.setItem('looking-glass-tabs:'+root,JSON.stringify({active,tabs:[...tabs.values()].map(e=>({path:e.path,pinned:e.pinned,mode:e.mode}))}));}
function syncState(){const e=entry();if(e&&view){e.state=view.state;e.content=view.state.sliceDoc();}}
function spansFor(threads,text){return threads.filter(t=>t.anchor_status==='attached'&&!t.resolved).map(t=>({id:t.id,from:toUnits(text,t.start),to:toUnits(text,t.end)})).filter(s=>s.from<s.to&&s.to<=text.length);}

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
const $$=selector=>[...document.querySelectorAll(selector)];
function showTabMenu(e,x,y){
  $('.tab-menu')?.remove();const menu=document.createElement('div');menu.className='tab-menu';menu.style.left=x+'px';menu.style.top=y+'px';
  const others=document.createElement('button');others.textContent='Close other tabs';others.onclick=guard(async()=>{menu.remove();for(const name of [...tabs.keys()])if(name!==e.path&&!tabs.get(name).pinned)await closeTab(name);});menu.append(others);document.body.append(menu);setTimeout(()=>document.addEventListener('click',()=>menu.remove(),{once:true}),0);
}
async function closeTab(path){
  const e=tabs.get(path);if(e.dirty&&!confirm('Discard unsaved edits in '+path+'?'))return;
  if(path===active){syncState();view?.destroy();view=null;cleanup();cleanup=()=>{};active=null;}
  tabs.delete(path);remember();renderTabs();
  if(!active&&tabs.size)await openFile([...tabs.keys()].at(-1));
  else if(!active){$('#surface').innerHTML='<div class="welcome"><h1>Open a file to begin.</h1></div>';$('#threads').replaceChildren();currentThreads=[];$('#thread-count').textContent='0';updateToolbar();}
}

function language(path){switch(ext(path)){case'md':case'markdown':return markdown();case'py':return python();case'sh':case'bash':return StreamLanguage.define(shell);case'html':case'htm':return html();case'json':return json();default:return [];}}
function makeState(e){
  const prose=['md','markdown','txt'].includes(ext(e.path));
  return EditorState.create({doc:e.content,extensions:[EditorState.lineSeparator.of(e.diskContent.includes('\r\n')?'\r\n':'\n'),basicSetup,language(e.path),syntaxHighlighting(colors),spanField,
    themeSlot.of(theme()),liveSlot.of(['md','markdown'].includes(ext(e.path))&&e.mode==='live'?liveMarkdown:[]),
    ...(prose?[EditorView.lineWrapping,EditorView.theme({'.cm-scroller':{fontFamily:'"Times New Roman", Times, serif',fontSize:'18px'},'.cm-content':{maxWidth:'850px',margin:'0 auto',width:'100%'},'.cm-gutters':{display:'none'}})]:[]),
    keymap.of([{key:'Mod-s',run:()=>{guard(saveActive)();return true;}},{key:'Mod-Enter',run:()=>{guard(startComment)();return true;}},{key:'Mod-f',run:openSearchPanel},{key:'Mod-h',run:openSearchPanel},indentWithTab]),
    EditorView.updateListener.of(u=>{if(u.docChanged){e.content=u.state.sliceDoc();e.dirty=e.content!==e.diskContent;e.state=u.state;updateToolbar();renderTabs();}if(u.selectionSet)updateToolbar();}),
    EditorView.domEventHandlers({click:event=>{const mark=event.target.closest?.('[data-anchor]');if(mark){guard(()=>jump(Number(mark.dataset.anchor)))();return true;}return false;}})
  ]});
}

async function openFile(path){
  if(switching){queuedFile=path;return;}switching=true;
  try{
    if(active===path)return;
    syncState();
    let e=tabs.get(path);
    if(!e){
      const type=ext(path);
      const file=type==='stl'?{content:'',version:null}:await api('file?'+new URLSearchParams({path}));
      e={path,...file,diskContent:file.content,dirty:false,conflict:null,pinned:false,state:null,mode:type==='md'||type==='markdown'?'live':type==='html'||type==='htm'?'rendered':'source'};
      tabs.set(path,e);
    }
    view?.destroy();view=null;cleanup();cleanup=()=>{};active=path;activeThread=null;currentThreads=[];
    $('#surface').replaceChildren();renderTabs();updateToolbar();remember();
    if(ext(path)==='stl')await mountSTL(e);
    else if(ext(path)==='jsonl')mountJSONL(e);
    else mountDocument(e);
    await refreshThreads();notify('');
  }finally{switching=false;if(queuedFile){const next=queuedFile;queuedFile=null;queueMicrotask(()=>guard(()=>openFile(next))());}}
}
function mountDocument(e){
  $('#surface').replaceChildren();
  if(e.mode==='rendered'){
    const frame=document.createElement('iframe');frame.id='html-preview';frame.title='Isolated HTML report';frame.setAttribute('sandbox','allow-scripts allow-forms allow-modals');
    // A separate preview capability grants no application API access. The
    // iframe and response sandbox both enforce an opaque report origin.
    guard(async()=>{const preview=await api('preview','POST',{path:e.path,content:e.content});if(frame.isConnected)frame.src=preview.url;})();
    $('#surface').append(frame);
  }else if(e.mode==='preview'){
    const preview=document.createElement('div');preview.className='markdown-preview';preview.innerHTML=DOMPurify.sanitize(marked.parse(e.content));$('#surface').append(preview);
  }else{
    const parent=document.createElement('div');parent.id='editor';if(['md','markdown','txt'].includes(ext(e.path)))parent.className='prose-editor';$('#surface').append(parent);view=new EditorView({state:e.state||makeState(e),parent});
    view.dispatch({effects:[themeSlot.reconfigure(theme()),liveSlot.reconfigure(['md','markdown'].includes(ext(e.path))&&e.mode==='live'?liveMarkdown:[])]});
  }
  updateToolbar();
}
function updateToolbar(){
  const e=entry(), type=e?ext(e.path):'', viewer=['stl','jsonl'].includes(type);
  $('#document-name').textContent=e?.path||'Open a file';$('#dirty').textContent=e?.dirty?' · Unsaved':'';
  $('#save').disabled=!e||viewer||!e.dirty||saving;$('#annotate').disabled=!view||!e||viewer||view.state.selection.main.empty;
  const mode=$('#mode');const modes=type==='md'||type==='markdown'?[['live','Live Markdown'],['source','Raw source'],['preview','Reading preview']]:type==='html'||type==='htm'?[['rendered','Rendered HTML'],['source','HTML source']]:[['source',viewer?'Viewer':'Source']];
  if(mode.dataset.path!==active){mode.replaceChildren(...modes.map(([value,label])=>{const opt=document.createElement('option');opt.value=value;opt.textContent=label;return opt;}));mode.dataset.path=active||'';}
  mode.hidden=!e||modes.length===1;if(e)mode.value=e.mode;
  $('#file-info').textContent=e?(viewer?type.toUpperCase()+' viewer':Array.from(e.content).length.toLocaleString()+' characters · UTF-8'):'Choose a file from the sidebar';
  $('#conflict').hidden=!e?.conflict;
  if(e?.conflict)$('#conflict span').textContent=e.conflict.deleted?'This file was deleted or became unavailable on disk. Copy your draft before closing it.':'Changed on disk. Your unsaved edits are preserved. Compare and merge before saving.';
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

async function refreshThreads(){
  const e=entry();if(!e||['stl','jsonl'].includes(ext(e.path))){$('#threads').innerHTML='<div class="empty-discussions">This viewer has no annotations.</div>';$('#thread-count').textContent='0';return;}
  const path=active, generation=++refreshNumber;
  const threads=await api('threads?'+new URLSearchParams({path}));
  if(active!==path||generation!==refreshNumber)return;
  currentThreads=threads;$('#thread-count').textContent=threads.filter(t=>!t.resolved).length;
  if(view&&!e.dirty)view.dispatch({effects:spansEffect.of(spansFor(threads,e.content))});
  await window.htmx.ajax('GET','/fragments/threads?'+new URLSearchParams({path,active:activeThread||''}),{target:'#threads',swap:'innerHTML'});
  filterThreads();
}
function filterThreads(){$$('.thread').forEach(t=>{t.hidden=t.dataset.resolved==='true'&&!$('#show-resolved').checked;t.classList.toggle('active',Number(t.dataset.thread)===activeThread);});}
async function jump(id){
  const t=currentThreads.find(t=>t.id===id);if(!t)return;activeThread=id;filterThreads();
  if(t.anchor_status!=='attached'){notify('This passage needs reattachment. Select the new passage and click “Attach to selection”.');return;}
  if(!view){entry().mode='source';mountDocument(entry());view.dispatch({effects:spansEffect.of(spansFor(currentThreads,entry().content))});}
  const span=view.state.field(spanField).find(s=>s.id===id);
  if(entry().dirty&&!span){notify('Save your draft before navigating to this passage. Its local anchor is unavailable.');return;}
  const from=span?.from??toUnits(entry().content,t.start),to=span?.to??toUnits(entry().content,t.end);
  if(to<=view.state.doc.length){view.dispatch({selection:{anchor:from,head:to},effects:EditorView.scrollIntoView(from,{y:'center'})});view.focus();}
  $('.thread[data-thread="'+id+'"]')?.scrollIntoView({block:'nearest'});
}
async function navigate(direction){const threads=currentThreads.filter(t=>!t.resolved||$('#show-resolved').checked);if(!threads.length)return;let at=threads.findIndex(t=>t.id===activeThread);at=(at+direction+threads.length)%threads.length;await jump(threads[at].id);}
async function startComment(){
  const e=entry();if(!view||!e||view.state.selection.main.empty)return;
  const {from,to}=view.state.selection.main;
  pending={path:e.path,start:selectionPoints(view.state,from),end:selectionPoints(view.state,to),quote:view.state.sliceDoc(from,to)};
  $('#selected-quote').textContent=pending.quote;$('#comment-body').value='';$('#comment-dialog').showModal();$('#comment-body').focus();
}
async function submitComment(event){
  event.preventDefault();if(!pending)return;await saveActive();const e=entry();if(pending.path!==active)throw new Error('The selected file changed. Select the passage again.');
  const result=await api('threads','POST',{path:pending.path,start:pending.start,end:pending.end,version:e.version,body:$('#comment-body').value,author:$('#author').value});
  $('#comment-dialog').close();pending=null;activeThread=result.id;await refreshThreads();await jump(result.id);notify('Discussion created');
}

function mountJSONL(e){
  const container=document.createElement('div');container.className='jsonl-split';const left=document.createElement('div'),right=document.createElement('div');left.className='jsonl-raw';right.className='jsonl-detail';
  const rawTitle=document.createElement('div');rawTitle.className='viewer-heading';rawTitle.textContent='FULL JSONL · SELECT A ROW';left.append(rawTitle);
  const detailTitle=document.createElement('div');detailTitle.className='viewer-heading';right.append(detailTitle);
  const parent=document.createElement('div');parent.className='json-detail-editor';right.append(parent);
  const detail=new EditorView({state:EditorState.create({extensions:[basicSetup,json(),syntaxHighlighting(colors),theme(),EditorView.editable.of(false),EditorState.readOnly.of(true),EditorView.lineWrapping]}),parent});
  const lines=e.content.split(/\r?\n/);if(lines.at(-1)==='')lines.pop();
  function select(index){const raw=lines[index];let text;try{text=JSON.stringify(JSON.parse(raw),null,2);detailTitle.textContent='ROW '+(index+1)+' · FORMATTED JSON';}catch(error){text=raw;detailTitle.textContent='ROW '+(index+1)+' · MALFORMED: '+error.message;}detail.dispatch({changes:{from:0,to:detail.state.doc.length,insert:text}});left.querySelectorAll('.jsonl-row').forEach((b,i)=>b.classList.toggle('selected',i===index));}
  lines.forEach((line,index)=>{const button=document.createElement('button');button.className='jsonl-row';button.dataset.row=index;let malformed=false;try{JSON.parse(line);}catch{malformed=true;}if(malformed)button.classList.add('malformed');const number=document.createElement('span');number.className='row-number';number.textContent=(index+1)+(malformed?' !':'');const source=document.createElement('code');source.textContent=line||'[empty line]';button.append(number,source);button.onclick=()=>select(index);left.append(button);});
  container.append(left,right);$('#surface').append(container);if(lines.length)select(0);cleanup=()=>detail.destroy();
}
async function mountSTL(e){
  const host=document.createElement('div');host.className='stl-view';const tools=document.createElement('div');tools.className='stl-tools';const fit=document.createElement('button');fit.textContent='Fit to view';const info=document.createElement('span');info.textContent='Orbit: drag · Pan: right drag · Zoom: scroll';tools.append(fit,info);host.append(tools);$('#surface').append(host);
  const status=document.createElement('div');status.className='stl-status';status.setAttribute('role','status');status.textContent='Loading model…';host.append(status);fit.disabled=true;
  let geometry, material, renderer, controls, observer;
  cleanup=()=>{observer?.disconnect();renderer?.setAnimationLoop?.(null);controls?.dispose();geometry?.dispose();material?.dispose();renderer?.dispose?.();};
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
  }catch(error){cleanup();status.textContent='Unable to display this STL: '+error.message;fit.disabled=true;notify(error.message,true);}
}

async function poll(){
  if(polling||saving||switching||document.hidden)return;polling=true;
  try{
    for(const e of [...tabs.values()]){
      try{
        const requestedVersion=e.version;
        if(ext(e.path)==='stl'){
          const disk=await api('stat?'+new URLSearchParams({path:e.path}));
          if(e.version!==requestedVersion||switching||saving)continue;
          if(disk.version!==e.version){e.version=disk.version;if(e.path===active){cleanup();cleanup=()=>{};$('#surface').replaceChildren();await mountSTL(e);notify('Reloaded the external STL change');}}
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
document.addEventListener('htmx:beforeSwap',event=>{if(event.detail.target.id==='threads'&&new URL(event.detail.xhr.responseURL,location.href).searchParams.get('path')!==active)event.detail.shouldSwap=false;});
document.addEventListener('htmx:afterSwap',event=>{if(event.detail.target.id==='file-tree'){filterFiles();renderTabs();}if(event.detail.target.id==='threads')filterThreads();});
document.addEventListener('htmx:responseError',event=>notify('Sidebar request failed: '+event.detail.xhr.status,true));
document.addEventListener('click',guard(async event=>{
  const file=event.target.closest('.file-entry');if(file)await openFile(file.dataset.path);
  const close=event.target.closest('[data-close]');if(close)close.closest('dialog').close();
  const action=event.target.closest('[data-action]');if(!action)return;
  const id=Number(action.closest('.thread').dataset.thread),t=currentThreads.find(t=>t.id===id);
  if(action.dataset.action==='jump')await jump(id);
  if(action.dataset.action==='resolve'){await api('threads/'+id,'PATCH',{resolved:!t.resolved});await refreshThreads();}
  if(action.dataset.action==='reattach'){
    if(!view||view.state.selection.main.empty)throw new Error('Select the new passage in the editor first.');const {from,to}=view.state.selection.main;const start=selectionPoints(view.state,from),end=selectionPoints(view.state,to);await saveActive();await api('threads/'+id,'PATCH',{start,end,version:entry().version});await refreshThreads();await jump(id);
  }
}));
document.addEventListener('submit',event=>{
  if(event.target.matches('.reply-form')){event.preventDefault();guard(async()=>{const id=Number(event.target.closest('.thread').dataset.thread);await api('threads/'+id+'/replies','POST',{author:$('#author').value,body:event.target.querySelector('textarea').value});await refreshThreads();notify('Reply added');})();}
});
$('#comment-form').onsubmit=guard(submitComment);
$('#save').onclick=guard(saveActive);$('#annotate').onclick=guard(startComment);
$('#previous').onclick=guard(()=>navigate(-1));$('#next').onclick=guard(()=>navigate(1));$('#show-resolved').onchange=filterThreads;
$('#mode').onchange=guard(async()=>{const e=entry();syncState();e.mode=$('#mode').value;view?.destroy();view=null;mountDocument(e);await refreshThreads();remember();});
$('#theme').onclick=()=>{const value=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=value;localStorage.setItem('looking-glass-theme',value);$('#theme').textContent=value==='dark'?'Light mode':'Dark mode';if(view)view.dispatch({effects:themeSlot.reconfigure(theme())});};
function filterFiles(){const query=$('#file-filter').value.toLowerCase();$$('.file-entry').forEach(b=>b.hidden=!b.dataset.path.toLowerCase().includes(query));}
$('#file-filter').oninput=filterFiles;$('#refresh-files').onclick=()=>window.htmx.trigger('#file-tree','refresh');
$('#author').value=localStorage.getItem('looking-glass-author')||'Altay';$('#author').onchange=()=>localStorage.setItem('looking-glass-author',$('#author').value);
$('#reload-disk').onclick=guard(async()=>{
  const e=entry();if(!e)return;if(e.dirty&&!confirm('Discard your unsaved edits and reload the current disk file?'))return;const disk=await api('file?'+new URLSearchParams({path:e.path}));e.content=disk.content;e.diskContent=disk.content;e.version=disk.version;e.dirty=false;e.conflict=null;e.state=null;view?.destroy();view=null;mountDocument(e);await refreshThreads();renderTabs();notify('Reloaded from disk');
});
$('#copy-draft').onclick=guard(async()=>{await navigator.clipboard.writeText(entry().content);notify('Draft copied');});
$('#merge-disk').onclick=guard(async()=>{const e=entry();const disk=await api('file?'+new URLSearchParams({path:e.path}));pending={mergePath:e.path,disk};$('#disk-text').textContent=disk.content;$('#merge-text').value=e.content;$('#merge-dialog').showModal();});
$('#accept-merge').onclick=guard(async()=>{const e=entry();if(pending?.mergePath!==e.path)throw new Error('Open the original file to finish merging.');e.version=pending.disk.version;e.diskContent=pending.disk.content;e.content=$('#merge-text').value;e.dirty=e.content!==e.diskContent;e.conflict=null;e.state=null;view?.destroy();view=null;mountDocument(e);$('#merge-dialog').close();pending=null;renderTabs();updateToolbar();notify('Merged draft ready. Save to write it to disk.');});
$('#git-open').onclick=guard(showGit);$('#inspect-diff').onclick=guard(async()=>{const result=await api('git/diff','POST',{paths:selectedGit()});$('#git-diff').textContent=result.diff;});
$('#checkpoint').onclick=guard(async()=>{const paths=selectedGit();if(paths.some(p=>tabs.get(p)?.dirty))throw new Error('Save your edits in the selected files before checkpointing.');const result=await api('git/checkpoint','POST',{paths,message:$('#checkpoint-name').value});$('#git-dialog').close();notify('Checkpoint '+result.commit.slice(0,8)+' created');});
window.addEventListener('beforeunload',event=>{if([...tabs.values()].some(e=>e.dirty)){event.preventDefault();event.returnValue='';}});
document.documentElement.dataset.theme=localStorage.getItem('looking-glass-theme')||'light';$('#theme').textContent=document.documentElement.dataset.theme==='dark'?'Light mode':'Dark mode';
// Restore tab metadata only; unsaved text is never silently persisted over disk.
let restored={tabs:[]};try{restored=JSON.parse(localStorage.getItem('looking-glass-tabs:'+root)||'{"tabs":[]}');if(Array.isArray(restored))restored={tabs:restored};}catch{}
guard(async()=>{
  switching=true;
  try{
    const results=await Promise.allSettled((restored.tabs||[]).map(async item=>{
      const type=ext(item.path),file=type==='stl'?{content:'',version:null}:await api('file?'+new URLSearchParams({path:item.path}));
      return {path:item.path,...file,diskContent:file.content,dirty:false,conflict:null,pinned:!!item.pinned,state:null,mode:item.mode||'source'};
    }));
    for(const result of results)if(result.status==='fulfilled')tabs.set(result.value.path,result.value);
  }finally{switching=false;}
  const requested=queuedFile;queuedFile=null;
  if(requested)await openFile(requested);
  else if(tabs.size)await openFile(tabs.has(restored.active)?restored.active:[...tabs.keys()].at(-1));
  renderTabs();
})();
setInterval(poll,2200);setInterval(()=>{if(!document.hidden)window.htmx.trigger('#file-tree','refresh');},12000);
