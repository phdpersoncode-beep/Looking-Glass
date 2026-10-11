import {marked,Renderer} from 'marked';
import {decodeHTML} from 'entities';

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

export function visibleMap(raw,from,text,code=false) {
  // A visible '&' or '*' can occur inside '&amp;' or '\\*'. Decode ordinary
  // text before matching so each character covers its complete source spelling.
  // Code is literal and can keep the direct path (including block newlines).
  const direct=code?raw.indexOf(text):-1;
  if(direct>=0)return Array.from({length:text.length},(_,i)=>({from:from+direct+i,to:from+direct+i+1}));
  let value='',map=[];
  for(let i=0;i<raw.length;) {
    const start=i;
    if(!code&&raw[i]==='\\'&&/[!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~]/.test(raw[i+1]||''))i++;
    let part=raw[i++];
    const entity=!code&&raw.slice(start).match(/^&(?:#\d+|#x[\da-f]+|[a-z][\da-z]+);/i);
    if(entity){part=decodeHTML(entity[0]);i=start+entity[0].length;}
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

