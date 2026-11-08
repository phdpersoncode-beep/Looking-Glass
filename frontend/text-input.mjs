import {EditorState,Text} from '@codemirror/state';

// Browsers can normalize committed CRLF to LF, or leave a CR next to a DOM
// line break. With an explicit disk separator, CodeMirror may then represent
// those characters inside a Text line instead of as line boundaries.
export const normalizeInputLineBreaks=EditorState.transactionFilter.of(tr=>{
  if(!tr.docChanged||!tr.isUserEvent('input'))return tr;
  const changes=[];
  tr.changes.iterChanges((_from,_to,fromB,_toB,inserted)=>{
    let at=fromB;
    const lines=inserted.iterLines();
    while(!lines.next().done){
      const line=lines.value;
      for(let i=0;i<line.length;i++){
        if(line[i]!=='\r'&&line[i]!=='\n')continue;
        const pair=line[i]==='\r'&&line[i+1]==='\n';
        const beforeBreak=line[i]==='\r'&&i===line.length-1&&at+line.length<fromB+inserted.length;
        changes.push({from:at+i,to:at+i+(pair?2:1),insert:beforeBreak?Text.empty:Text.of(['',''])});
        if(pair)i++;
      }
      at+=line.length+1;
    }
  });
  // Sequential composition preserves the original input annotations, effects,
  // multi-cursor selection and undo grouping, mapping them through CR removal.
  return changes.length?[tr,{changes,sequential:true}]:tr;
});
