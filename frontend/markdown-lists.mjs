// Use parser ownership rather than whitespace guesses: ordered, unordered and
// mixed lists share the same depth, including lazy and multi-paragraph items.
export function markdownListLines(tree, doc) {
  const lines=new Map();
  tree.iterate({enter(ref){
    if(ref.name!=='ListItem')return;
    const item=ref.node,marker=item.getChild('ListMark');if(!marker)return;
    let depth=1;for(let parent=item.parent;parent;parent=parent.parent)if(parent.name==='ListItem')depth++;
    const first=doc.lineAt(marker.from),last=doc.lineAt(Math.max(marker.from,item.to-1));
    const task=item.getChild('Task')?.getChild('TaskMarker');
    let prefixTo=task?.to??marker.to;
    while(prefixTo<first.to&&/[ \t]/.test(doc.sliceString(prefixTo,prefixTo+1)))prefixTo++;
    const width=Math.max(1.8,(marker.to-marker.from)*.6+.5);
    let contentFrom=marker.to;
    while(contentFrom<first.to&&/[ \t]/.test(doc.sliceString(contentFrom,contentFrom+1)))contentFrom++;
    const indentation=doc.sliceString(first.from,contentFrom);
    const columns=[...indentation].reduce((n,ch)=>ch==='\t'?n+4-n%4:n+1,0);
    for(let number=first.number;number<=last.number;number++){
      const line=doc.line(number);let indentTo=line.from;
      if(number===first.number){
        if(/^[ \t]*$/.test(doc.sliceString(line.from,marker.from)))indentTo=marker.from;
      }else{
        let column=0;
        while(indentTo<line.to&&column<columns){
          const ch=doc.sliceString(indentTo,indentTo+1);if(!/[ \t]/.test(ch))break;
          const next=ch==='\t'?column+4-column%4:column+1;if(next>columns)break;
          column=next;indentTo++;
        }
      }
      lines.set(line.from,{from:line.from,depth,width,indentTo,
        markerFrom:number===first.number?marker.from:null,markerTo:prefixTo,bullet:!task&&/^[*+-]$/.test(doc.sliceString(marker.from,marker.to))});
    }
  }});
  return [...lines.values()].sort((a,b)=>a.from-b.from);
}
