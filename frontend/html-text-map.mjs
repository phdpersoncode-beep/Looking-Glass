import {EntityDecoder,DecodingMode,htmlDecodeTree} from 'entities/decode';

// UTF-16 positions on both sides. Parent converts raw offsets to Python code
// points only at the API boundary. Each entity maps to its complete spelling.
export function htmlTextMap(raw,from,expected) {
  const starts=[],ends=[];let text='',part='',consumed=0;
  const decoder=new EntityDecoder(htmlDecodeTree,(cp,size)=>{part+=String.fromCodePoint(cp);consumed=size;});
  for(let i=0;i<raw.length;){
    const start=i;part='';consumed=0;
    if(raw[i]==='&'){
      decoder.startEntity(DecodingMode.Legacy);
      if(decoder.write(raw,i+1)<0)decoder.end();
    }
    if(consumed)i+=consumed;
    else {part=raw[i++];if(part==='\r'){if(raw[i]==='\n')i++;part='\n';}}
    text+=part;
    for(let j=0;j<part.length;j++){starts.push(from+start);ends.push(from+i);}
  }
  // HTML strips the first newline in pre/listing elements. Nulls or malformed
  // foster-parented text may be non-contiguous: refuse unprovable mappings.
  if(text!==expected){if(text==='\n'+expected){starts.shift();ends.shift();}else return null;}
  return {starts,ends};
}
