// Index once per discussion update, then search locally without network requests.
// Fuzzy matches stay inside words: unrelated letters scattered across a long
// conversation should not make it a result.
function field(text,label) {
  text=String(text||'').replace(/\s+/gu,' ').trim();
  let normalized='',offsets=[];
  for(let at=0;at<text.length;){
    const char=String.fromCodePoint(text.codePointAt(at));
    const folded=char.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase();
    for(let i=0;i<folded.length;i++)offsets.push(at);
    normalized+=folded;at+=char.length;
  }
  offsets.push(text.length);
  const seen=new Set(),words=[];
  for(const m of normalized.matchAll(/[\p{L}\p{N}_]+/gu))if(!seen.has(m[0])){seen.add(m[0]);words.push({text:m[0],at:m.index});}
  return {text,label,normalized,offsets,words};
}

// Bounded Damerau–Levenshtein distance also accepts transposed letters.
function distance(a,b,limit) {
  if(Math.abs(a.length-b.length)>limit)return limit+1;
  let previous=Array.from({length:b.length+1},(_,i)=>i),older;
  for(let i=1;i<=a.length;i++){
    const row=[i];let minimum=i;
    for(let j=1;j<=b.length;j++){
      let value=Math.min(row[j-1]+1,previous[j]+1,previous[j-1]+(a[i-1]!==b[j-1]));
      if(i>1&&j>1&&a[i-1]===b[j-2]&&a[i-2]===b[j-1])value=Math.min(value,older[j-2]+1);
      row[j]=value;minimum=Math.min(minimum,value);
    }
    if(minimum>limit)return limit+1;
    older=previous;previous=row;
  }
  return previous[b.length];
}

function match(term,f,cache) {
  const at=f.normalized.indexOf(term);
  if(at>=0){
    const boundary=at===0||!/[\p{L}\p{N}_]/u.test(f.normalized[at-1]);
    return {score:boundary?100:85,from:at,to:at+term.length};
  }
  if(term.length<3||/^\d+$/u.test(term))return null;
  let best=null;
  for(const word of f.words){
    const key=term+'\0'+word.text;
    if(cache.has(key)){
      const found=cache.get(key);
      if(found&&(!best||found.score>best.score))best={...found,from:word.at+found.from,to:word.at+found.to};
      continue;
    }
    let found=null;
    const limit=term.length>=6?2:term.length>=4?1:0;
    if(limit&&Math.abs(term.length-word.text.length)<=limit){
      const edits=distance(term,word.text,limit);
      if(edits<=limit)found={score:65-edits*8,from:0,to:word.text.length};
    }
    // Compact abbreviations (e.g. "cfg" → "config") without broad subsequences.
    if(word.text.length<=term.length+3){
      let next=0,first=-1,last=0;
      for(let i=0;i<word.text.length&&next<term.length;i++)if(word.text[i]===term[next]){if(first<0)first=i;last=i;next++;}
      if(next===term.length){const hit={score:40-(last-first+1-term.length),from:first,to:last+1};if(!found||hit.score>found.score)found=hit;}
    }
    cache.set(key,found);
    if(found&&(!best||found.score>best.score))best={...found,from:word.at+found.from,to:word.at+found.to};
  }
  return best;
}

export function searchExcerpt(f,hits,width=150) {
  const ranges=hits.map(h=>[f.offsets[h.from],f.offsets[h.to]]).sort((a,b)=>a[0]-b[0]);
  const focus=ranges[0]||[0,0],start=Math.max(0,focus[0]-40),end=Math.min(f.text.length,Math.max(start+width,focus[1]));
  const merged=[];
  for(const [from,to] of ranges){
    if(from>=end||to<=start)continue;
    const range=[Math.max(start,from)-start,Math.min(end,to)-start],last=merged.at(-1);
    if(last&&range[0]<=last[1])last[1]=Math.max(last[1],range[1]);else merged.push(range);
  }
  return {text:f.text.slice(start,end),ranges:merged,leading:start>0,trailing:end<f.text.length};
}

export function createThreadSearch(threads) {
  const index=threads.map(thread=>({thread,fields:[field(thread.quote,'Passage'),...(thread.messages||[]).map((message,i)=>field(message.body,i?'Reply':'Comment'))]}));
  let lastQuery=null,lastResults=[];
  return query=>{
    query=String(query).trim();if(query===lastQuery)return lastResults;
    const normalized=field(query,'').normalized;
    const idQuery=normalized.match(/^#?\s*(\d+)$/u);
    const terms=[...new Set(normalized.match(/#\d+|[\p{L}\p{N}_]+/gu)||[])];
    const results=[],wordCache=new Map();
    if(terms.length)for(const {thread,fields} of index){
      const id=String(thread.id);
      if(idQuery&&id.startsWith(idQuery[1])){
        results.push({id:thread.id,score:id===idQuery[1]?2000:1000,label:'Thread number',excerpt:searchExcerpt(fields[0],[])});continue;
      }
      if(normalized.startsWith('#')&&idQuery)continue;
      let score=0,matched=true;const fieldHits=new Map();
      for(const term of terms){
        if(term.startsWith('#')){if(term.slice(1)!==id){matched=false;break;}score+=200;continue;}
        let best=null;
        for(const f of fields){const hit=match(term,f,wordCache);if(hit&&(!best||hit.score>best.hit.score))best={f,hit};}
        if(!best){matched=false;break;}
        score+=best.hit.score;
        if(!fieldHits.has(best.f))fieldHits.set(best.f,[]);fieldHits.get(best.f).push(best.hit);
      }
      if(!matched)continue;
      // Prefer an exact phrase; otherwise show the field explaining most terms.
      let chosen=null,hits=[];
      for(const [f,matches] of fieldHits){
        if(!chosen||matches.length>hits.length){chosen=f;hits=matches;}
        const phrase=f.normalized.indexOf(normalized);
        if(phrase>=0){score+=120;chosen=f;hits=[{from:phrase,to:phrase+normalized.length}];break;}
      }
      chosen??=fields[0];
      results.push({id:thread.id,score,label:chosen.label,excerpt:searchExcerpt(chosen,hits)});
    }
    results.sort((a,b)=>b.score-a.score||a.id-b.id);
    lastQuery=query;lastResults=results;return results;
  };
}
