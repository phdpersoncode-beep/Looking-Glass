import {marked} from 'marked';
import DOMPurify from 'dompurify';
import {tokenPositions} from './markdown-render.mjs';

export function mountMarkdownContents(host,readDocument,navigate) {
  const list=host.querySelector('nav'),summary=host.querySelector('summary');
  let timer=null;
  function render() {
    const source=readDocument(),tokens=marked.lexer(source),positions=tokenPositions(tokens,source);
    const fragment=document.createDocumentFragment();
    marked.walkTokens(tokens,token=>{
      if(token.type!=='heading')return;
      const position=positions.get(token);if(!position)return;
      const label=document.createElement('span');
      label.innerHTML=DOMPurify.sanitize(marked.parseInline(token.text),{ALLOWED_TAGS:[]});
      const button=document.createElement('button');button.type='button';button.textContent=label.textContent||'Untitled heading';
      button.title=button.textContent;button.style.setProperty('--heading-level',token.depth-1);
      button.onclick=()=>{host.open=false;navigate(position.from);};fragment.append(button);
    });
    if(!fragment.childNodes.length){const empty=document.createElement('p');empty.textContent='No headings yet';fragment.append(empty);}
    list.replaceChildren(fragment);
  }
  host.addEventListener('toggle',()=>{if(host.open)render();else clearTimeout(timer);});
  document.addEventListener('pointerdown',event=>{if(host.open&&!host.contains(event.target))host.open=false;});
  host.addEventListener('keydown',event=>{if(event.key==='Escape'&&host.open){event.preventDefault();host.open=false;summary.focus();}});
  return {
    reset(){clearTimeout(timer);host.open=false;list.replaceChildren();},
    update(){if(host.open){clearTimeout(timer);timer=setTimeout(render,150);}}
  };
}
