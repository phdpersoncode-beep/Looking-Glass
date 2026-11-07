import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorState,EditorSelection} from '@codemirror/state';
import {occurrenceBands,collectOccurrenceBands} from '../frontend/match-overview.mjs';
import {quickFileMatches} from '../frontend/file-search.mjs';

test('occurrence overview finds offscreen Unicode/CRLF matches and clears invalid selections',()=>{
  const doc='🪞 needle\r\n'+('ordinary line\r\n'.repeat(90))+'needle\r\n';
  const state=EditorState.create({doc,selection:{anchor:3,head:9}});
  const hits=occurrenceBands(state);assert.deepEqual(hits.map(h=>h.line),[1,92]);
  assert.equal(state.sliceDoc(hits[1].from,hits[1].to),'needle');
  assert.deepEqual(occurrenceBands(EditorState.create({doc,selection:{anchor:0}})),[]);
  const multi=EditorState.create({doc,selection:EditorSelection.create([EditorSelection.range(3,9),EditorSelection.cursor(20)]),extensions:EditorState.allowMultipleSelections.of(true)});
  assert.deepEqual(occurrenceBands(multi),[]);
});
test('dense occurrence bands stay bounded while covering the complete file',()=>{
  const state=EditorState.create({doc:'needle\n'.repeat(10000),selection:{anchor:0,head:6}});
  const hits=occurrenceBands(state);assert.ok(hits.length<=250);assert.ok(hits.at(-1).line>9900);
});
test('empty fuzzy query lists unique recent files first and filtering retains ranking',()=>{
  assert.deepEqual(quickFileMatches(['a.txt','b.txt','c.txt','z.txt'],'',['z.txt','b.txt','z.txt']).map(i=>i.path),['z.txt','b.txt','a.txt','c.txt']);
  assert.deepEqual(quickFileMatches(['src/part.py','note.txt'],'spp',['note.txt']).map(i=>i.path),['src/part.py']);
});

test('large scans preserve Unicode normalization and cancel stale selection work',async()=>{
  const source='ﬃ\n'+('ordinary line\n'.repeat(10000))+'ffi\n';
  const state=EditorState.create({doc:source,selection:{anchor:0,head:1}});
  const hits=await collectOccurrenceBands(state);assert.equal(hits.length,2);
  assert.equal(state.sliceDoc(hits.at(-1).from,hits.at(-1).to),'ffi');
  let current=true,pauses=0;
  const stale=await collectOccurrenceBands(state,{current:()=>current,budget:0,pause:async()=>{pauses++;current=false;}});
  assert.equal(stale,null);assert.equal(pauses,1);
});
