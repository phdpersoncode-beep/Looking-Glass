import test from 'node:test';
import assert from 'node:assert/strict';
import {graphRows} from '../frontend/history.mjs';
test('merge lanes preserve both parents and reconnect shared ancestors',()=>{
  const rows=graphRows([{hash:'merge',parents:['main','topic']},{hash:'topic',parents:['base']},{hash:'main',parents:['base']},{hash:'base',parents:[]}],[{commit:'merge',ref:'main'},{commit:'topic',ref:'agent/review'}]);
  assert.equal(rows[0].color,rows[2].color);
  assert.notEqual(rows[0].color,rows[1].color);
  assert.equal(rows[0].edges.filter(e=>e.half==='bottom').length,2);
  assert.ok(rows.some(r=>r.width===2));
  assert.equal(rows.at(-1).edges.filter(e=>e.half==='top').length,1);
  for(const row of rows)for(const edge of row.edges)assert.ok(edge.from>=0&&edge.to>=0);
});
test('layout stays identical when older commits are appended',()=>{
  const commits=[{hash:'a',parents:['b','c']},{hash:'b',parents:['d']},{hash:'c',parents:['d']},{hash:'d',parents:[]}];
  assert.deepEqual(graphRows(commits).slice(0,2),graphRows(commits.slice(0,2)));
});
