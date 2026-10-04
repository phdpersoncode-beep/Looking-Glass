// Validate syntax, but format original tokens so numbers/duplicate keys survive.
export function formatJSON(source, newline='\n') {
  JSON.parse(source);
  const tokens=source.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]|[^\s{}\[\],:]+/g);
  let depth=0,output='';
  const line=()=>newline+'  '.repeat(depth);
  tokens.forEach((token,i)=>{
    if(token==='{'||token==='['){output+=token;depth++;if(tokens[i+1]!=='}'&&tokens[i+1]!==']')output+=line();}
    else if(token==='}'||token===']'){depth--;if(tokens[i-1]!=='{'&&tokens[i-1]!=='[')output+=line();output+=token;}
    else if(token===',')output+=token+line();
    else if(token===':')output+=': ';
    else output+=token;
  });
  return output+newline;
}
