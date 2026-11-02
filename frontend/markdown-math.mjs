import {Marked} from 'marked';
import katex from 'katex';

const escapeHTML=value=>value.replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const escaped=(source,at)=>{let count=0;while(at>0&&source[--at]==='\\')count++;return count%2===1;};

// Parse before Markdown consumes backslashes, underscores, braces or line breaks.
// Single dollars use Pandoc-style whitespace/digit rules to avoid ordinary prices.
export function readMath(source) {
  const open=source.startsWith('$$')?'$$':source.startsWith('\\[')?'\\[':source.startsWith('\\(')?'\\(':source[0]==='$'?'$':null;
  if(!open)return null;
  const close=open==='\\['?'\\]':open==='\\('?'\\)':open,display=open==='$$'||open==='\\[';
  if(open==='$'&&(/\s/.test(source[1]||'')||source[1]==='$'))return null;
  for(let at=open.length;(at=source.indexOf(close,at))>=0;at+=close.length){
    if(escaped(source,at))continue;
    if(open==='$'&&(/\s/.test(source[at-1])||/\d/.test(source[at+1]||'')))return null;
    const text=source.slice(open.length,at);
    if(!text.trim()||!display&&/[\r\n]/.test(text))return null;
    return {raw:source.slice(0,at+close.length),text,display};
  }
  return null;
}

export const isMathFence=token=>token.type==='code'&&/^(math|latex|tex)$/i.test(token.lang?.trim()||'');

function mathRenderer(token) {
  return this.parser.options.mathRenderer?.(token)??escapeHTML(token.raw);
}

export const markdown=new Marked({extensions:[
  {
    name:'mathBlock',level:'block',
    start:source=>{const match=/\n {0,3}(?:\$\$|\\\[)/.exec(source);return match?match.index+1:undefined;},
    tokenizer(source){
      const indent=/^ {0,3}/.exec(source)[0],math=readMath(source.slice(indent.length));
      if(!math?.display||!/^[ \t]*(?:\n|$)/.test(source.slice(indent.length+math.raw.length)))return;
      return {type:'mathBlock',...math,raw:indent+math.raw};
    },renderer:mathRenderer
  },
  {
    name:'mathInline',level:'inline',start:source=>source.search(/\$|\\[([]/),
    tokenizer(source){const math=readMath(source);if(math)return {type:'mathInline',...math};},renderer:mathRenderer
  }
]});

// Only placeholders created by this parse are hydrated, after authored HTML has
// been sanitized. A fresh key prevents authored markup from posing as a formula.
export function mathPlaceholder(token,slots,position) {
  const key=crypto.randomUUID();
  slots.push({key,text:token.text,raw:token.raw,display:token.display??true,position});
  return `<span data-lg-math="${key}">${escapeHTML(token.raw)}</span>`;
}

export const mathOptions=Object.freeze({output:'htmlAndMathml',trust:false,throwOnError:true,strict:'ignore',maxExpand:1000,maxSize:20});

function selectMathOnDrag(element) {
  element.addEventListener('pointerdown',event=>{
    if(event.button!==0||event.pointerType!=='mouse')return;
    const {clientX:x,clientY:y}=event,scrollLeft=element.scrollLeft,controller=new AbortController();
    const finish=end=>{
      controller.abort();
      if(end.type!=='pointerup'||!element.isConnected||!element.contains(end.target)||element.scrollLeft!==scrollLeft||Math.hypot(end.clientX-x,end.clientY-y)<4)return;
      // Positioned fractions, roots and matrices do not expose reliable native
      // caret hits in every browser. Math is one source passage, so normalize a
      // drag within it to the visible formula, retaining its exact source map.
      const selection=window.getSelection(),existing=selection.rangeCount&&selection.getRangeAt(0);
      if(!selection.isCollapsed&&existing&&element.contains(existing.startContainer)&&element.contains(existing.endContainer))return;
      const content=element.querySelector('.katex-html')||element.querySelector('.md-math-content');
      const range=document.createRange();range.selectNodeContents(content);
      selection.removeAllRanges();selection.addRange(range);
    };
    document.addEventListener('pointerup',finish,{capture:true,signal:controller.signal});
    document.addEventListener('pointercancel',finish,{capture:true,signal:controller.signal});
    window.addEventListener('blur',finish,{signal:controller.signal});
  });
}

export function hydrateMath(host,slots) {
  for(const {key,text,raw,display,position} of slots){
    const element=host.querySelector(`[data-lg-math="${key}"]`);if(!element)continue;
    element.removeAttribute('data-lg-math');element.className='md-math'+(display?' md-math-display':'');
    if(display){element.tabIndex=0;element.setAttribute('role','region');element.setAttribute('aria-label','Math equation');}
    if(position){element.dataset.mdFrom=position.from;element.dataset.mdTo=position.to;selectMathOnDrag(element);}
    const body=document.createElement('span');body.className='md-math-content';element.replaceChildren(body);
    try{katex.render(text,body,{...mathOptions,displayMode:display});}
    catch(error){body.textContent=raw;element.classList.add('math-error');element.title=error.message;}
  }
  host.querySelectorAll('[data-lg-math]').forEach(element=>element.removeAttribute('data-lg-math'));
}
