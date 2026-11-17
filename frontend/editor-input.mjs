import {Text} from '@codemirror/state';

// Gecko composition input can normalize CRLF to literal LF inside a DOM text
// node. With an explicit CRLF lineSeparator, CodeMirror reads that LF as a
// control character within one line. Repair only the newly inserted text and
// merge the repair into the same transaction (selection, history, and review).
export function normalizeInputTransaction(transaction) {
  const changes=[];
  transaction.changes.iterChanges((_from,_to,fromB,_toB,inserted)=>{
    let offset=fromB;
    for(const lines=inserted.iterLines();!lines.next().done;){
      for(const match of lines.value.matchAll(/\r\n?|\n/g))
        changes.push({from:offset+match.index,to:offset+match.index+match[0].length,insert:Text.of(['',''])});
      offset+=lines.value.length+1;
    }
  });
  return changes.length ? transaction.startState.update(transaction,{changes,sequential:true}) : null;
}

export const normalizeClipboardInput=(text,state)=>text.replace(/\r\n?|\n/g,state.lineBreak);
