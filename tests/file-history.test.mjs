import test from 'node:test';
import assert from 'node:assert/strict';
import {createFileHistory} from '../frontend/file-history.mjs';

test('history follows successful visits, avoids adjacent duplicates and truncates forward visits',()=>{
  const h=createFileHistory();assert.equal(h.target(-1),null);
  for(const path of ['a','b','b','c'])h.visit(path);
  assert.deepEqual(h.snapshot,{entries:['a','b','c'],index:2});
  h.visit('b',1);assert.deepEqual(h.target(1),{path:'c',index:2});
  h.visit('d');assert.deepEqual(h.snapshot,{entries:['a','b','d'],index:2});assert.equal(h.target(1),null);
});
test('rapid history requests use their latest intention and cancellation changes no committed visit',()=>{
  const h=createFileHistory();for(const p of ['a','b','c'])h.visit(p);
  h.request(h.target(-1).index);assert.deepEqual(h.target(-1),{path:'a',index:0});
  h.request(0);assert.equal(h.target(-1),null);assert.equal(h.snapshot.index,2);
  h.cancel();assert.equal(h.snapshot.index,2);assert.equal(h.target(-1).path,'b');
  h.request(1);h.visit('b',1);assert.equal(h.snapshot.index,1);
});
test('repeated visits have distinct history positions; clearing keeps no stale cursor',()=>{
  const h=createFileHistory();for(const p of ['a','b','a'])h.visit(p);
  h.visit('a',0);assert.equal(h.snapshot.index,0);assert.equal(h.target(1).path,'b');
  h.request(1);h.clear();assert.deepEqual(h.snapshot,{entries:[],index:-1});assert.equal(h.target(1),null);
  h.visit('b',1);assert.deepEqual(h.snapshot,{entries:['b'],index:0});
});
test('history is bounded, restores a valid cursor and exposes an immutable snapshot',()=>{
  const h=createFileHistory({entries:['a','b','c','d'],index:2},3);
  assert.deepEqual(h.snapshot,{entries:['b','c','d'],index:1});
  h.snapshot.entries.push('external');assert.equal(h.snapshot.entries.length,3);
  h.visit('e');h.visit('f');assert.deepEqual(h.snapshot,{entries:['c','e','f'],index:2});
  assert.deepEqual(createFileHistory({entries:'broken',index:100}).snapshot,{entries:[],index:-1});
});
