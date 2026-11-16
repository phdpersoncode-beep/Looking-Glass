import test from 'node:test';
import assert from 'node:assert/strict';
import {Text} from '@codemirror/state';
import {pythonPosition,definitionOffset} from '../frontend/python-navigation.mjs';
import {initialAppState,transition,selectVisibleThreads,selectThreadSequence} from '../frontend/app-state.mjs';

test('Python columns count Unicode points while editor offsets count UTF-16',()=>{
  const doc=Text.of(['# heading','value = "🦊"; café()']);
  const at=doc.line(2).from+doc.line(2).text.indexOf('café');
  assert.deepEqual(pythonPosition(doc,at),{line:2,column:13});
  assert.equal(definitionOffset(doc,{line:2,column:13}),at);
  assert.equal(definitionOffset(doc,{line:3,column:0}),null);
  assert.equal(definitionOffset(doc,{line:2,column:999}),null);
});

test('marker filter composes with search, resolution, unattached and navigation',()=>{
  const base={path:'a.py',anchor_status:'attached',messages:[],resolved:false};
  const threads=[{...base,id:1,start:0,quote:'TODO manual'},
    {...base,id:2,start:10,quote:'TODO flagged',source_marker:'TODO'},
    {...base,id:3,start:20,quote:'NOTE flagged',source_marker:'NOTE',resolved:true,anchor_status:'needs_reattachment'}];
  let state={...initialAppState(),threads};
  state=transition(state,{type:'THREAD_ACTIVATED',threadId:1,spotlight:true}).state;
  state=transition(state,{type:'FILTERS_CHANGED',filters:{onlySourceMarkers:true}}).state;
  assert.equal(state.spotlight,null);
  assert.deepEqual(selectVisibleThreads(state).map(t=>t.id),[2]);
  assert.deepEqual(selectThreadSequence(state).map(t=>t.id),[2]);
  state=transition(state,{type:'FILTERS_CHANGED',filters:{showResolved:true,searchQuery:'NOTE',onlyUnattached:true}}).state;
  assert.deepEqual(selectThreadSequence(state).map(t=>t.id),[3]);
});
