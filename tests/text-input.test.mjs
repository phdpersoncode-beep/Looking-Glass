import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorState,EditorSelection,StateEffect,Text,Transaction} from '@codemirror/state';
import {normalizeInputLineBreaks} from '../frontend/text-input.mjs';
import {reviewTracking,operationsFor} from '../frontend/review-editor.mjs';
import {accepted} from '../frontend/review-model.mjs';

const source='def café():\r\n    return "🦊"\r\n';
const draft='# changed draft\ndef draft_only():\n    return 1\ndraft_only()\n';
function state(extra=[]){return EditorState.create({doc:source,extensions:[EditorState.lineSeparator.of('\r\n'),normalizeInputLineBreaks,...extra]});}

for(const [name,text] of [
  ['Firefox composition with normalized LF',Text.of([draft])],
  ['CRLF inside a single browser Text line',Text.of([draft.replaceAll('\n','\r\n')])],
  ['DOM line breaks with trailing carriage returns',Text.of(draft.replaceAll('\n','\r\n').split('\n'))]
])test(name+' becomes real lines and preserves CRLF serialization',()=>{
  const before=state(),tr=before.update({changes:{from:0,to:before.doc.length,insert:text},selection:{anchor:text.length},userEvent:'input.type.compose'});
  assert.equal(tr.state.doc.lines,5);
  assert.equal(tr.state.doc.toString(),draft);
  assert.equal(tr.state.sliceDoc(),draft.replaceAll('\n','\r\n'));
  assert.equal(tr.state.selection.main.head,tr.state.doc.length);
  assert.equal(tr.annotation(Transaction.userEvent),'input.type.compose');
  assert.deepEqual(operationsFor(tr),[{start:0,end:Array.from(source).length,insert:draft.replaceAll('\n','\r\n')}]);
});

test('normalization keeps multi-cursor selection, mapped effects and annotations',()=>{
  const effect=StateEffect.define({map:(position,changes)=>changes.mapPos(position)});
  const before=EditorState.create({doc:'abc',extensions:[EditorState.lineSeparator.of('\r\n'),EditorState.allowMultipleSelections.of(true),normalizeInputLineBreaks]});
  const tr=before.update({changes:[{from:0,insert:Text.of(['left\r\n'])},{from:3,insert:Text.of(['right\n'])}],selection:EditorSelection.create([EditorSelection.cursor(6),EditorSelection.cursor(15)]),effects:effect.of(6),annotations:Transaction.addToHistory.of(false),userEvent:'input.paste'});
  assert.equal(tr.state.doc.toString(),'left\nabcright\n');
  assert.deepEqual(tr.state.selection.ranges.map(r=>r.head),[5,14]);
  assert.equal(tr.effects[0].value,5);
  assert.equal(tr.annotation(Transaction.addToHistory),false);
});

test('review provenance receives only normalized CRLF edits',()=>{
  const field=reviewTracking({base:source,segments:[{text:source,kind:'base'}]},()=>({author:'User',role:'human',at:'2026-11-08'}));
  const before=state([field]),tr=before.update({changes:{from:0,to:before.doc.length,insert:Text.of([draft])},userEvent:'input.type.compose'});
  assert.equal(accepted(tr.state.field(field).segments),tr.state.sliceDoc());
  assert.equal(tr.state.field(field).segments.find(s=>s.kind==='delete').text,source);
});

for(const first of [true,false])test('line normalization respects an edit blocker '+(first?'before':'after')+' it',()=>{
  const blocked=EditorState.transactionFilter.of(tr=>tr.docChanged?[]:tr);
  const before=EditorState.create({doc:source,extensions:[EditorState.lineSeparator.of('\r\n'),...(first?[blocked,normalizeInputLineBreaks]:[normalizeInputLineBreaks,blocked])]}),tr=before.update({changes:{from:0,insert:Text.of(['new\nline'])},userEvent:'input'});
  assert.equal(tr.state.sliceDoc(),source);
});
