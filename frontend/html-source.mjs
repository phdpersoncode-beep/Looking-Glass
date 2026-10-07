import {parse} from 'parse5';

// Add identities to existing tags, never wrappers: table parsing and report CSS
// keep their original structure. Only the disposable preview receives markers.
export function prepareHTMLPreview(source, attribute) {
  if(!/^data-lg-[a-z0-9-]+$/.test(attribute)||source.toLowerCase().includes(attribute))throw new Error('Invalid preview marker.');
  const tree=parse(source,{sourceCodeLocationInfo:true}),records=[],insertions=[],ids=new Map();
  const stack=[tree];let serial=0;
  while(stack.length){
    const node=stack.pop(),tag=node.sourceCodeLocation?.startTag;
    if(tag){
      // Parser-reconstructed formatting elements can share a source tag.
      let id=ids.get(tag.startOffset);
      if(id===undefined){id=String(serial++);ids.set(tag.startOffset,id);const at=tag.startOffset+source.slice(tag.startOffset,tag.endOffset).match(/^<[^\s/>]+/)[0].length;insertions.push({at,text:` ${attribute}="${id}"`});}
      node.marker=id;
    }
    if(node.nodeName==='#text'&&node.sourceCodeLocation){
      let ancestor=node.parentNode,path=[ancestor.childNodes.indexOf(node)];
      while(ancestor&&!ancestor.marker&&ancestor.marker!=='0'&&ancestor.tagName!=='body'){
        const parent=ancestor.parentNode;if(!parent)break;
        path.unshift(parent.childNodes.indexOf(ancestor));ancestor=parent;
      }
      if(ancestor?.marker!==undefined||ancestor?.tagName==='body')records.push({id:ancestor.marker??null,path,siblings:node.parentNode.childNodes.length,text:node.value,from:node.sourceCodeLocation.startOffset,to:node.sourceCodeLocation.endOffset});
    }
    // Template contents and script/style text are never annotation surfaces.
    if(!['script','style','noscript','template','textarea','title','xmp','iframe','noembed','noframes','plaintext'].includes(node.tagName)){
      for(let i=(node.childNodes?.length||0)-1;i>=0;i--)stack.push(node.childNodes[i]);
    }
  }
  const parts=[];let cursor=0;
  for(const item of insertions.sort((a,b)=>a.at-b.at)){parts.push(source.slice(cursor,item.at),item.text);cursor=item.at;}
  parts.push(source.slice(cursor));
  return {content:parts.join(''),mapping:{attribute,records,source}};
}
