import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorState,EditorSelection,Text,Transaction} from '@codemirror/state';
import {normalizeInputTransaction,normalizeClipboardInput} from '../frontend/editor-input.mjs';
import {operationsFor} from '../frontend/review-editor.mjs';

for(const separator of ['\n','\r\n'])test('DOM newlines become real lines with preserved raw operations: '+JSON.stringify(separator),()=>{
  const state=EditorState.create({doc:'old'+separator,extensions:[EditorState.lineSeparator.of(separator)]});
  // A native composition may deliver a single Text line containing LF/CRLF.
  const input='🦊 first\nnext\r\nlast\r';
  const tr=state.update({changes:{from:0,to:state.doc.length,insert:Text.of([input])},
    selection:EditorSelection.cursor(input.length),userEvent:'input.type.compose',scrollIntoView:true});
  const repaired=normalizeInputTransaction(tr);
  assert.equal(repaired.newDoc.lines,4);
  assert.deepEqual([...repaired.newDoc.iterLines()],['🦊 first','next','last','']);
  assert.equal(repaired.state.sliceDoc(),['🦊 first','next','last',''].join(separator));
  assert.equal(repaired.newSelection.main.head,repaired.newDoc.length);
  assert.equal(repaired.annotation(Transaction.userEvent),'input.type.compose');
  assert.ok(repaired.scrollIntoView);
  assert.deepEqual(operationsFor(repaired),[{start:0,end:4+(separator.length-1),insert:['🦊 first','next','last',''].join(separator)}]);
  const undo=repaired.changes.invert(state.doc);
  assert.equal(undo.apply(repaired.newDoc).toString(),state.doc.toString());
});

test('repair preserves multi-cursor selection positions across CRLF contraction',()=>{
  const state=EditorState.create({doc:'AB',extensions:[EditorState.allowMultipleSelections.of(true)]});
  const tr=state.update({changes:[{from:1,insert:Text.of(['x\r\ny'])},{from:2,insert:Text.of(['z\nq'])}],
    selection:EditorSelection.create([EditorSelection.cursor(5),EditorSelection.cursor(9)])});
  const repaired=normalizeInputTransaction(tr);
  assert.equal(repaired.newDoc.toString(),'Ax\nyBz\nq');
  assert.deepEqual(repaired.newSelection.ranges.map(range=>range.head),[4,8]);
});

test('ordinary input is unchanged and mixed clipboard line endings use the file convention',()=>{
  const state=EditorState.create({doc:'a\r\nb',extensions:[EditorState.lineSeparator.of('\r\n')]});
  for(const insert of ['x',Text.of(['two','lines'])])assert.equal(normalizeInputTransaction(state.update({changes:{from:0,insert}})),null);
  const pasted=normalizeClipboardInput('first\nsecond\rthird\r\n',state);
  assert.equal(pasted,'first\r\nsecond\r\nthird\r\n');
  assert.equal(state.toText(pasted).lines,4);
});
