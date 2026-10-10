export function pointLength(text){return text.length-(text.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g)||[]).length;}
export function unitAt(text,point){let unit=point;for(const match of text.matchAll(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g)){if(match.index>=unit)break;unit++;}return unit;}
// The same operation model as reviews.py. Offsets count accepted Unicode points.
export function accepted(segments){return segments.filter(s=>s.kind!=='delete').map(s=>s.text).join('');}
export function compact(segments){
  const result=[];
  for(const segment of segments){
    if(!segment.text)continue;
    const metadata=s=>JSON.stringify(Object.fromEntries(Object.entries(s).filter(([key])=>key!=='text').sort(([a],[b])=>a.localeCompare(b))));
    if(result.length&&metadata(result.at(-1))===metadata(segment))result.at(-1).text+=segment.text;
    else result.push({...segment});
  }
  return result;
}
export function splice(segments,start,end,insert,metadata){
  const before=[],middle=[],after=[];let position=0,removedBase=false;
  for(const segment of segments){
    const text=segment.text,size=pointLength(text),kind=segment.kind;
    if(kind==='delete'){(position<=start?before:position>=end?after:middle).push({...segment});continue;}
    const stop=position+size;
    if(stop<=start)before.push({...segment});
    else if(position>=end)after.push({...segment});
    else{
      const left=Math.max(0,start-position),right=Math.min(size,end-position);
      if(left)before.push({...segment,text:text.slice(0,unitAt(text,left))});
      if(right>left&&kind==='base'){removedBase=true;middle.push({text:text.slice(unitAt(text,left),unitAt(text,right)),kind:'delete',...metadata});}
      if(right<size)after.push({...segment,text:text.slice(unitAt(text,right))});
    }
    position=stop;
  }
  if(!removedBase&&insert&&before.at(-1)?.kind==='delete'&&before.at(-1).text===insert){before[before.length-1]={text:insert,kind:'base'};insert='';}
  return compact([...before,...middle,...(insert?[{text:insert,kind:'insert',...metadata}]:[]),...after]);
}
export function apply(segments,operations,metadata,base){
  for(const op of operations)segments=splice(segments,op.start,op.end,op.insert,metadata);
  if(base!==undefined&&accepted(segments)===base)return base?[{text:base,kind:'base'}]:[];
  return segments;
}
export function ranges(segments,normalized=false){
  let position=0;
  return segments.flatMap(segment=>{
    const size=(normalized?segment.text.replace(/\r\n/g,'\n'):segment.text).length;
    const range={...segment,from:position,to:position+(segment.kind==='delete'?0:size)};
    if(segment.kind!=='delete')position+=size;
    return segment.kind==='base'?[]:[range];
  });
}
export function label(segment){return `${segment.kind==='delete'?'Removed':'Added'} by ${segment.author||'Unknown'} (${segment.role||'human'}) · ${segment.at||''}`;}
