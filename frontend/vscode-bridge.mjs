import {EditorState,StateEffect} from '@codemirror/state';
import {hoverTooltip} from '@codemirror/view';
import {renderMarkdown} from './markdown-render.mjs';

export const bridgeDiskReload=StateEffect.define();
const REASON='Read only — unsaved changes in VS Code';
export function createBridge(api, changed) {
  let state={enabled:false,live:false,dirty:[],epoch:null},ready;
  const locked=path=>state.enabled&&state.dirty.includes(path);
  const blocked=path=>!path?.startsWith('/')&&state.enabled&&(!state.live||locked(path));
  const bridge={locked,blocked,reason:path=>locked(path)?REASON:'VS Code status unknown. Reconnect or explicitly disconnect the bridge.',
    get state(){return state;},get ready(){return ready;},
    async read(wait=false){
      try {
        const next=await api('bridge/status'+(wait?'?wait='+encodeURIComponent(JSON.stringify([state.epoch,state.sequence,state.enabled,state.live])):''));
        const difference=JSON.stringify({...next,sequence:0})!==JSON.stringify({...state,sequence:0});state=next;if(difference)changed();
      } catch {if(state.enabled&&state.live){state={...state,live:false};changed();}}
    },
    async disconnect(){await api('bridge/disconnect','POST',{});await bridge.read();},
    eligible(e){return !!e&&!e.kind&&e.workMode!=='review'&&!e.dirty&&!e.conflict&&state.live&&!blocked(e.path);},
    async provider(e,editor,at,provider,current){
      if(!bridge.eligible(e))return null;
      const doc=editor.state.doc,epoch=state.epoch,line=doc.lineAt(at);
      const valid=()=>current()&&editor.state.doc===doc&&bridge.eligible(e)&&state.epoch===epoch;
      try {
        const result=await api('bridge/provider','POST',{path:e.path,mode:'edit',hash:e.version,content:editor.state.sliceDoc(),provider,line:line.number,column:Array.from(line.text.slice(0,at-line.from)).length});
        return valid()?{...result,valid}:null;
      } catch {return null;}
    },
    extensions(e,current){
      const complete=async context=>{
        if(!context.explicit||!bridge.eligible(e))return null;
        const result=await bridge.provider(e,context.view,context.pos,'completion',current);
        if(!result?.items?.length)return null;
        const offset=p=>p&&Number.isInteger(p.line)&&Number.isInteger(p.character)&&p.line>=0&&p.line<context.state.doc.lines&&p.character>=0&&p.character<=context.state.doc.line(p.line+1).length?context.state.doc.line(p.line+1).from+p.character+(p.line===0&&e.diskContent.startsWith('\uFEFF')?1:0):null;
        const options=result.items.flatMap(item=>{
          const from=offset(item.range?.start),to=offset(item.range?.end);
          if(from===null||to===null||from>to||typeof item.label!=='string'||typeof item.text!=='string')return [];
          return [{label:item.label,apply(view){if(result.valid()&&!view.state.readOnly)view.dispatch({changes:{from,to,insert:item.text},selection:{anchor:from+item.text.length},userEvent:'input.complete'});}}];
        });
        return options.length?{from:context.pos,options}:null;
      };
      return [EditorState.languageData.of(()=>[{autocomplete:complete}]),hoverTooltip(async(view,pos)=>{
        if(!bridge.eligible(e))return null;
        const result=await bridge.provider(e,view,pos,'hover',current);
        if(!result?.markdown)return null;
        return {pos,create(){const dom=document.createElement('div');dom.className='bridge-hover';renderMarkdown(dom,result.markdown);return {dom};}};
      })];
    }
  };
  ready=bridge.read();
  void (async()=>{await ready;while(true){await bridge.read(true);await new Promise(resolve=>setTimeout(resolve,100));}})();
  return bridge;
}
export function lockIcon() {
  const icon=document.createElement('span');icon.className='vscode-lock';icon.tabIndex=0;icon.title=REASON;icon.setAttribute('aria-label',REASON);
  icon.innerHTML='<svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="4" y="9" width="12" height="9" rx="2"/><path d="M6 9V6a4 4 0 0 1 8 0v3"/></svg>';
  return icon;
}
