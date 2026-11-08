// Obsidian-compatible display widths; pixels and annotation coordinates stay unchanged.
export function imageCaption(text=''){
  const match=/\|(\d{1,4})$/.exec(text);
  const width=match&&Number(match[1]);
  return width>=40&&width<=4000?{alt:text.slice(0,match.index).replace(/\\$/,''),width}:{alt:text,width:null};
}
export function resizedImageSource(source,width,table=false){
  width=Math.max(40,Math.min(4000,Math.round(width)));const separator=table?'\\|':'|';
  if(source.startsWith('![['))return '![['+imageCaption(source.slice(3,-2)).alt+separator+width+']]';
  let depth=1,at=2;
  for(;at<source.length;at++){
    if(source[at]==='\\'){at++;continue;}
    if(source[at]==='[')depth++;
    if(source[at]===']'&&!--depth)break;
  }
  if(at===source.length)throw new Error('Unable to resize this image embed.');
  const caption=source.slice(2,at),tail=source.slice(at);
  // Keep collapsed and shortcut reference destinations explicit when the alt changes.
  const suffix=tail===']'||tail==='][]'?']['+caption+']':tail;
  return '!['+imageCaption(caption).alt+separator+width+suffix;
}
