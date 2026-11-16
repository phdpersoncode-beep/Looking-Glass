import {Decoration,ViewPlugin,keymap} from '@codemirror/view';
import {syntaxTree} from '@codemirror/language';

export function pythonPosition(doc, at){
  const line=doc.lineAt(at);
  return {line:line.number,column:Array.from(line.text.slice(0,at-line.from)).length};
}
export function definitionOffset(doc,{line,column}){
  if(!Number.isInteger(line)||line<1||line>doc.lines)return null;
  const row=doc.line(line),characters=Array.from(row.text);
  if(!Number.isInteger(column)||column<0||column>characters.length)return null;
  return row.from+characters.slice(0,column).join('').length;
}
export function chooseDefinition(targets){
  return new Promise(resolve=>{
    const previous=document.activeElement,dialog=document.createElement('dialog'),heading=document.createElement('h2'),list=document.createElement('nav'),cancel=document.createElement('button');
    dialog.className='lg-dialog definition-choices';dialog.setAttribute('aria-label','Choose a definition');heading.textContent='Choose a definition';list.setAttribute('aria-label','Definitions');
    let selected=null;
    for(const target of targets){const button=document.createElement('button');button.type='button';button.textContent=`${target.name} · ${target.path}:${target.line}`;button.onclick=()=>{selected=target;dialog.close();};list.append(button);}
    cancel.type='button';cancel.textContent='Cancel';cancel.onclick=()=>dialog.close();dialog.append(heading,list,cancel);
    dialog.onclose=()=>{dialog.remove();if(previous?.isConnected)previous.focus({preventScroll:true});resolve(selected);};
    document.body.append(dialog);dialog.showModal();list.querySelector('button')?.focus();
  });
}
function identifier(editor,pos){
  if(pos==null)return null;
  const word=editor.state.wordAt(pos);if(!word)return null;
  const node=syntaxTree(editor.state).resolveInner(word.from+1,-1);
  return ['VariableName','PropertyName'].includes(node.name)?word:null;
}
export function pythonNavigation(lookup){
  return [keymap.of([{key:'F12',run:editor=>{lookup(editor,editor.state.selection.main.head);return true;}}]),
    ViewPlugin.fromClass(class{
      decorations=Decoration.none;
      update(update){if(update.docChanged)this.decorations=Decoration.none;}
      mark(editor,event){
        const word=(event.ctrlKey||event.metaKey)&&identifier(editor,editor.posAtCoords({x:event.clientX,y:event.clientY}));
        this.decorations=word?Decoration.set([Decoration.mark({class:'python-definition-link'}).range(word.from,word.to)]):Decoration.none;
        editor.dispatch({});
      }
    },{decorations:plugin=>plugin.decorations,eventHandlers:{
      mousemove(event,editor){this.mark(editor,event);},
      mouseleave(_event,editor){this.decorations=Decoration.none;editor.dispatch({});},
      keyup(event,editor){if(!event.ctrlKey&&!event.metaKey){this.decorations=Decoration.none;editor.dispatch({});}},
      mousedown(event,editor){
        if(event.button!==0||!(event.ctrlKey||event.metaKey))return false;
        const word=identifier(editor,editor.posAtCoords({x:event.clientX,y:event.clientY}));
        if(!word)return false;event.preventDefault();lookup(editor,word.from);return true;
      }
    }})];
}
