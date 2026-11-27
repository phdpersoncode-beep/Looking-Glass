import {markdown as marked} from './markdown-math.mjs';
import DOMPurify from 'dompurify';
import {tokenPositions} from './markdown-render.mjs';
import {scrollWithin} from './scroll-within.mjs';

export function mountMarkdownContents(host,{navigate,saveOpen}) {
  const list=host.querySelector('nav'),summary=host.querySelector('summary');
  let path=null,doc=null,rendered=null,cursor=null,timer;
  let headings=[],current=null;
  function highlightCurrent(){
    if(!host.open||doc!==rendered)return;
    const heading=headings.findLast(item=>item.from<=cursor);
    const button=heading?.button;
    if(button===current)return;
    current?.removeAttribute('aria-current');
    current=button;
    if(current){
      current.setAttribute('aria-current','location');
      scrollWithin(list,current);
    }
  }
  function render() {
    if(!doc||doc===rendered)return;
    const renderedDoc=doc,source=doc.toString(),tokens=marked.lexer(source),positions=tokenPositions(tokens,source);
    const fragment=document.createDocumentFragment();
    headings=[];
    marked.walkTokens(tokens,token=>{
      if(token.type!=='heading')return;
      const position=positions.get(token);if(!position)return;
      const label=document.createElement('span');
      label.innerHTML=DOMPurify.sanitize(marked.parseInline(token.text),{ALLOWED_TAGS:[]});
      const button=document.createElement('button');button.type='button';button.textContent=label.textContent||'Untitled heading';
      button.title=button.textContent;button.style.setProperty('--outline-depth',token.depth-1);
      const from=renderedDoc.lineAt(position.from).from;
      headings.push({from,button});
      button.onclick=()=>{if(doc===renderedDoc)navigate(position.from);};fragment.append(button);
    });
    if(!fragment.childNodes.length){const empty=document.createElement('p');empty.textContent='No headings yet';fragment.append(empty);}
    list.replaceChildren(fragment);rendered=doc;highlightCurrent();
  }
  host.addEventListener('toggle',()=>{saveOpen(host.open);if(host.open){render();highlightCurrent();}else clearTimeout(timer);});
  host.addEventListener('keydown',event=>{if(event.key==='Escape'&&host.open&&!event.defaultPrevented){event.preventDefault();host.open=false;summary.focus();}});
  return {
    setDocument(nextPath,nextDoc,nextCursor){
      cursor=nextCursor;
      if(nextPath===path&&nextDoc===doc){highlightCurrent();return;}
      clearTimeout(timer);
      const changedPath=nextPath!==path;
      path=nextPath;doc=nextDoc;host.hidden=!doc;
      if(changedPath){rendered=null;current=null;headings=[];list.replaceChildren();list.scrollTop=0;}
      if(!host.open||!doc)return;
      if(changedPath)render();else timer=setTimeout(render,150);
    }
  };
}
