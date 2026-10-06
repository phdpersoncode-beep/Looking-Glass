import {marked, Renderer} from 'marked';
import DOMPurify from 'dompurify';

// Locate tokens inside their parent's source range. A link's destination, for
// example, must never be mistaken for the next visible word with the same text.
export function tokenPositions(tokens, source) {
  const positions=new WeakMap();
  function locate(items,from,to) {
    let cursor=from;
    for(const token of items||[]) {
      const raw=token.raw||'';let at=raw?source.indexOf(raw,cursor):-1,size=raw.length;
      if(raw&&(at<cursor||at+size>to)&&/[\n|]/.test(raw)){
        // Block quotes/list continuations insert prefixes between token lines;
        // GFM table lexing removes the backslash from escaped cell pipes.
        const pattern=[...raw].map(ch=>ch==='\n'?'\\n(?:[ \t]*>[ \t]?)*[ \t]*':ch==='|'?'\\\\?\\|':ch.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('');
        const match=new RegExp(pattern).exec(source.slice(cursor,to));
        if(match){at=cursor+match.index;size=match[0].length;}
      }
      const found=at>=cursor&&at+size<=to;
      const start=found?at:cursor,end=found?at+size:to;
      if(found)positions.set(token,{from:start,to:end});
      if(token.tokens)locate(token.tokens,start,end);
      if(token.items)locate(token.items,start,end);
      if(token.type==='table') {
        let cellCursor=start;
        for(const cell of [...token.header,...token.rows.flat()]) {
          locate(cell.tokens,cellCursor,end);
          const last=cell.tokens?.at(-1),position=last&&positions.get(last);
          if(position)cellCursor=position.to;
        }
      }
      if(found)cursor=end;
    }
  }
  locate(tokens,0,source.length);return positions;
}

export function mappedMarkdownHTML(source,offset=0) {
  const normalized=source.replace(/\r\n?/g,'\n'),boundaries=[0];
  for(let i=0;i<source.length;i++){if(source[i]==='\r'&&source[i+1]==='\n')i++;boundaries.push(i+1);}
  const tokens=marked.lexer(normalized),positions=tokenPositions(tokens,normalized),renderer=new Renderer();
  const baseText=renderer.text,baseCode=renderer.codespan,baseBlock=renderer.code;
  const wrap=(token,html)=>{
    const position=positions.get(token);if(!position)return html;
    return `<span class="md-mapped-text" data-md-from="${offset+boundaries[position.from]}" data-md-to="${offset+boundaries[position.to]}">${html}</span>`;
  };
  renderer.text=function(token){return token.tokens?baseText.call(this,token):wrap(token,baseText.call(this,token));};
  renderer.codespan=function(token){return wrap(token,baseCode.call(this,token));};
  renderer.code=function(token){return baseBlock.call(this,token).replace(/(<code[^>]*>)([\s\S]*)(<\/code>)/,(_all,open,body,close)=>open+wrap(token,body)+close);};
  // Marked sends escaped punctuation through the text renderer as well.
  return marked.parser(tokens,{renderer});
}

function visibleMap(raw,from,text,code=false) {
  const direct=raw.indexOf(text);
  if(direct>=0)return Array.from({length:text.length},(_,i)=>({from:from+direct+i,to:from+direct+i+1}));
  let value='',map=[];
  const decode=document.createElement('textarea');
  for(let i=0;i<raw.length;) {
    const start=i;
    if(!code&&raw[i]==='\\'&&/[!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~]/.test(raw[i+1]||''))i++;
    let part=raw[i++];
    const entity=!code&&raw.slice(start).match(/^&(?:#\d+|#x[\da-f]+|[a-z][\da-z]+);/i);
    if(entity){decode.innerHTML=entity[0];part=decode.value;i=start+entity[0].length;}
    if(part==='\r'&&raw[i]==='\n'){part='\n';i++;}
    if(code&&part==='\n')part=' ';
    value+=part;for(let j=0;j<part.length;j++)map.push({from:from+start,to:from+i});
  }
  let at=value.indexOf(text);if(at>=0)return map.slice(at,at+text.length);
  // Preserve source coordinates while removing structural continuation prefixes.
  for(const pattern of [/\n(?:[ \t]*>[ \t]?)+[ \t]*/g,/\n[ \t]+/g]){
    let projected='',projectedMap=[],cursor=0;
    for(const match of value.matchAll(pattern)){
      const end=match.index+1;projected+=value.slice(cursor,end);projectedMap=projectedMap.concat(map.slice(cursor,end));cursor=match.index+match[0].length;
    }
    projected+=value.slice(cursor);projectedMap=projectedMap.concat(map.slice(cursor));
    at=projected.indexOf(text);if(at>=0)return projectedMap.slice(at,at+text.length);
  }
  return null;
}

export function mountMappedMarkdown(host,source,offset=0,decorate=()=>{}) {
  host.innerHTML=DOMPurify.sanitize(mappedMarkdownHTML(source,offset));
  decorate(host);
  let lastHighlights=null;
  const leaves=[...host.querySelectorAll('.md-mapped-text')],nodes=new WeakMap();
  for(const leaf of leaves) {
    const from=Number(leaf.dataset.mdFrom),to=Number(leaf.dataset.mdTo),text=leaf.textContent;
    leaf._mapping=visibleMap(source.slice(from-offset,to-offset),from,text,!!leaf.querySelector('code'));
    leaf._text=text;
  }
  function register(leaf) {
    if(!leaf._mapping)return;
    const walker=document.createTreeWalker(leaf,NodeFilter.SHOW_TEXT);let node,at=0;
    while((node=walker.nextNode())){nodes.set(node,leaf._mapping.slice(at,at+node.length));at+=node.length;}
  }
  leaves.forEach(register);
  function boundary(node,at,end) {
    if(node.nodeType!==Node.TEXT_NODE){
      const children=[...node.childNodes],candidates=end?children.slice(0,at).reverse():children.slice(at);
      for(const child of candidates){
        if(child.nodeType===Node.TEXT_NODE){const value=boundary(child,end?child.length:0,end);if(value!==null)return value;}
        else{const walker=document.createTreeWalker(child,NodeFilter.SHOW_TEXT),texts=[];let text;while((text=walker.nextNode()))if(nodes.has(text))texts.push(text);const target=end?texts.at(-1):texts[0];if(target)return boundary(target,end?target.length:0,end);}
      }
      return null;
    }
    const map=nodes.get(node);if(!map?.length)return null;
    if(end)return at===0?map[0].from:map[Math.min(at,map.length)-1].to;
    return at===map.length?map.at(-1).to:map[at]?.from;
  }
  return {
    host,
    selection(selection=window.getSelection()) {
      if(!selection?.rangeCount||selection.isCollapsed)return null;
      const range=selection.getRangeAt(0);
      if(!host.contains(range.startContainer)||!host.contains(range.endContainer))return null;
      const from=boundary(range.startContainer,range.startOffset,false),to=boundary(range.endContainer,range.endOffset,true);
      if(from===null||to===null||from>=to)return null;
      return {from,to,rect:range.getBoundingClientRect()};
    },
    highlight(spans,active) {
      const signature=JSON.stringify([spans,active]);if(signature===lastHighlights)return;
      const selection=window.getSelection();
      if(selection&&!selection.isCollapsed&&host.contains(selection.anchorNode))return;
      lastHighlights=signature;
      for(const leaf of leaves) {
        const map=leaf._mapping;if(!map)continue;
        const target=leaf.querySelector('code')||leaf,fragment=document.createDocumentFragment();
        for(let at=0;at<map.length;) {
          const ids=spans.filter(s=>s.from<map[at].to&&s.to>map[at].from).map(s=>s.id);
          let end=at+1;
          while(end<map.length&&spans.filter(s=>s.from<map[end].to&&s.to>map[end].from).map(s=>s.id).join(',')===ids.join(','))end++;
          const text=leaf._text.slice(at,end);
          if(ids.length){const mark=document.createElement('span');mark.className='passage-highlight'+(ids.includes(active)?' focused-highlight':'');mark.dataset.anchor=String(ids.includes(active)?active:ids[0]);mark.textContent=text;fragment.append(mark);}
          else fragment.append(document.createTextNode(text));at=end;
        }
        target.replaceChildren(fragment);
      }
      decorate(host);leaves.forEach(register);
    },
    jump(from,to) {
      const walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode())){const map=nodes.get(node);if(map?.some(p=>p.from<to&&p.to>from)){node.parentElement.scrollIntoView({block:'center'});return true;}}
      return false;
    }
  };
}
