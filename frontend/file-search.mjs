export function fuzzyScore(path,query){const text=path.toLowerCase();let cursor=0,score=0,previous=-2;for(const character of query.toLowerCase().replace(/\s/g,'')){const index=text.indexOf(character,cursor);if(index<0)return null;score+=index===previous+1?8:0;score+=index===0||'/._-'.includes(text[index-1])?12:0;score-=index-cursor;previous=index;cursor=index+1;}return score-text.length/100;}

export function quickFileMatches(paths,query,recent=[]){
  const recency=new Map([...new Set(recent)].map((path,index)=>[path,index]));
  return [...new Set(paths)].map(path=>({path,score:fuzzyScore(path,query)})).filter(item=>item.score!==null)
    .sort((a,b)=>(query.trim()?b.score-a.score:0)||(recency.get(a.path)??Infinity)-(recency.get(b.path)??Infinity)||a.path.localeCompare(b.path)).slice(0,50);
}
