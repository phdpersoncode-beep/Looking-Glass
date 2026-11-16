import {SearchCursor} from '@codemirror/search';
import {EditorView,ViewPlugin} from '@codemirror/view';

// One representative per line band bounds DOM/work even for dense matches.
// Chunking lets large Unicode searches yield to input and cancel stale work.
function* scanBands(state,bands){
  const range=state.selection.main;
  if(state.selection.ranges.length!==1||range.empty||range.to-range.from>200)return;
  const query=state.sliceDoc(range.from,range.to);if(!query)return;
  const normalized=query.normalize('NFKD'),asciiQuery=!/[^\x00-\x7f]/.test(normalized);
  const count=Math.min(bands,state.doc.lines),chunk=32768;let start=0;
  while(start<state.doc.length){
    const boundary=Math.min(state.doc.length,start+chunk),end=Math.min(state.doc.length,boundary+normalized.length+2);
    const text=state.doc.sliceString(start,end);let hit;
    if(asciiQuery&&!/[^\x00-\x7f]/.test(text)){
      const at=text.indexOf(normalized);if(at>=0)hit={from:start+at,to:start+at+normalized.length};
    }else{const cursor=new SearchCursor(state.doc,query,start,end);if(!cursor.next().done)hit=cursor.value;}
    if(!hit){start=boundary;yield null;continue;}
    const {from,to}=hit,line=state.doc.lineAt(from),band=Math.floor((line.number-1)*count/state.doc.lines);
    yield {from,to,line:line.number};
    const nextLine=Math.max(line.number+1,Math.ceil((band+1)*state.doc.lines/count)+1);
    if(nextLine>state.doc.lines)break;start=state.doc.line(nextLine).from;
  }
}
export function occurrenceBands(state,bands=250){return [...scanBands(state,bands)].filter(Boolean);}
export async function collectOccurrenceBands(state,{current=()=>true,pause=()=>new Promise(resolve=>setTimeout(resolve,0)),budget=8}={}){
  const positions=[];let started=performance.now();
  for(const hit of scanBands(state,250)){
    if(!current())return null;if(hit)positions.push(hit);
    if(performance.now()-started>=budget){await pause();if(!current())return null;started=performance.now();}
  }
  return current()?positions:null;
}
export const matchOverview=ViewPlugin.fromClass(class{
  constructor(view){
    this.view=view;this.positions=[];this.serial=0;
    this.dom=document.createElement('div');this.dom.className='cm-match-map';this.dom.setAttribute('role','navigation');this.dom.setAttribute('aria-label','Selected text matches');view.dom.append(this.dom);this.schedule();
  }
  update(update){if(update.docChanged||update.selectionSet)this.schedule();else if(update.geometryChanged||update.viewportChanged)this.measure();}
  schedule(){clearTimeout(this.timer);const serial=++this.serial;const range=this.view.state.selection.main;
    if(range.empty){this.positions=[];this.dom.replaceChildren();this.dom.hidden=true;return;}
    this.timer=setTimeout(async()=>{if(serial!==this.serial)return;const positions=await collectOccurrenceBands(this.view.state,{current:()=>serial===this.serial});if(!positions)return;this.positions=positions;this.render();},80);
  }
  render(){const serial=this.serial;this.dom.replaceChildren();this.dom.hidden=!this.positions.length;
    for(const match of this.positions){const b=document.createElement('button');b.type='button';b.className='cm-match-marker';b.title='Match at line '+match.line;b.setAttribute('aria-label','Matching text, line '+match.line);b.onpointerdown=e=>e.preventDefault();b.onclick=()=>{if(serial!==this.serial)return;this.view.dispatch({selection:{anchor:match.from,head:match.to},effects:EditorView.scrollIntoView(match.from,{y:'center'})});this.view.focus();};this.dom.append(b);}this.measure();
  }
  measure(){const positions=this.positions,serial=this.serial;if(!positions.length)return;
    this.view.requestMeasure({key:this,read:view=>{if(serial!==this.serial||positions!==this.positions)return null;const scroll=view.scrollDOM.getBoundingClientRect(),editor=view.dom.getBoundingClientRect();return {top:scroll.top-editor.top,height:scroll.height,points:positions.map(p=>view.lineBlockAt(p.from).top/Math.max(1,view.contentHeight,scroll.height))};},write:layout=>{if(!layout||serial!==this.serial||positions!==this.positions)return;this.dom.style.top=layout.top+'px';this.dom.style.height=layout.height+'px';[...this.dom.children].forEach((el,i)=>el.style.top=Math.max(0,Math.min(layout.height-6,layout.points[i]*(layout.height-6)))+'px');}});
  }
  destroy(){clearTimeout(this.timer);this.serial++;this.dom.remove();}
});
