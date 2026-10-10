import test from 'node:test';
import assert from 'node:assert/strict';
import {accepted,apply,ranges} from '../frontend/review-model.mjs';
const meta={author:'Altay',role:'human',at:'2026-10-09T00:00:00Z',edit_id:1};
test('incremental replacement and mixed provenance preserve source and Unicode',()=>{
  const base='a🧠b\r\nc';let segments=[{text:base,kind:'base'}];
  segments=apply(segments,[{start:1,end:2,insert:'X'}],meta,base);
  assert.equal(accepted(segments),'aXb\r\nc');
  assert.equal(segments.find(s=>s.kind==='delete').text,'🧠');
  segments=apply(segments,[{start:6,end:6,insert:'!'}],{...meta,role:'agent'},base);
  assert.equal(accepted(segments),'aXb\r\nc!');
  assert.deepEqual(ranges(segments,true).map(s=>[s.kind,s.from,s.to]),[['delete',1,1],['insert',1,2],['insert',5,6]]);
});
test('undo and removal of additions have no net marks but keep operation semantics',()=>{
  const base='abc';let segments=[{text:base,kind:'base'}];
  segments=apply(segments,[{start:1,end:2,insert:''}],meta,base);
  segments=apply(segments,[{start:1,end:1,insert:'b'}],meta,base);
  assert.deepEqual(segments,[{text:base,kind:'base'}]);
  segments=apply(segments,[{start:0,end:0,insert:'x'},{start:0,end:1,insert:''}],meta,base);
  assert.deepEqual(segments,[{text:base,kind:'base'}]);
});
test('undo of one replacement keeps other changes and cancels restored deletion',()=>{
  const base='abcxyz';let segments=[{text:base,kind:'base'}];
  segments=apply(segments,[{start:1,end:3,insert:'Q'},{start:5,end:5,insert:'!'}],meta,base);
  segments=apply(segments,[{start:1,end:2,insert:'bc'}],meta,base);
  assert.equal(accepted(segments),'abcxyz!');
  assert.deepEqual(segments.filter(s=>s.kind!=='base').map(s=>s.text),['!']);
});
