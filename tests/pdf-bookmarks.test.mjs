import test from 'node:test';
import assert from 'node:assert/strict';
import {moveBookmark,indentBookmark,removeBookmark} from '../frontend/pdf-bookmarks.mjs';
const items=[{id:'a',level:0},{id:'b',level:1},{id:'c',level:0},{id:'d',level:1},{id:'e',level:0}];
test('moving a bookmark carries its subtree and preserves sibling order',()=>{
  assert.deepEqual(moveBookmark(items,0,1).map(x=>x.id),['c','d','a','b','e']);
  assert.deepEqual(moveBookmark(items,2,-1).map(x=>x.id),['c','d','a','b','e']);
  assert.deepEqual(moveBookmark(items,0,-1),items);
  assert.equal(items[0].id,'a');
});
test('indent and remove preserve a valid hierarchy and stable IDs',()=>{
  assert.deepEqual(indentBookmark(items,2,1).map(x=>x.level),[0,1,1,2,0]);
  assert.deepEqual(indentBookmark(items,0,1),items);
  assert.deepEqual(removeBookmark(items,0),[{id:'b',level:0},...items.slice(2)]);
});

test('outdenting moves only the chosen subtree past its parent siblings',()=>{
  const nested=[{id:'a',level:0},{id:'b',level:1},{id:'c',level:2},{id:'d',level:1},{id:'e',level:0}];
  assert.deepEqual(indentBookmark(nested,1,-1),[{id:'a',level:0},{id:'d',level:1},{id:'b',level:0},{id:'c',level:1},{id:'e',level:0}]);
});
