import test from 'node:test';
import assert from 'node:assert/strict';
import {createThreadSearch} from '../frontend/thread-search.mjs';

const threads=[
  {id:12,quote:'CadQuery configuration',messages:[{body:'Review the geometry verifier.'},{body:'Topology needs another pass.'}]},
  {id:123,quote:'Mesh configuration',messages:[{body:'Check the geometry.'}]},
  {id:7,quote:'Café and 🪞 mirror',messages:[{body:'The configuration is here.'}]},
];

test('passages, all replies, case and accents are searchable',()=>{
  const search=createThreadSearch(threads);
  assert.equal(search('cadquery')[0].label,'Passage');
  assert.equal(search('TOPOLOGY')[0].label,'Reply');
  assert.equal(search('verifier')[0].label,'Comment');
  const cafe=search('cafe')[0];assert.equal(cafe.id,7);
  assert.equal(cafe.excerpt.text.slice(...cafe.excerpt.ranges[0]),'Café');
});
test('exact thread numbers rank first, # numbers never match body text',()=>{
  const search=createThreadSearch([...threads,{id:2,quote:'Issue #12 or 123',messages:[]}]);
  assert.deepEqual(search('#12').map(r=>r.id),[12,123]);
  assert.deepEqual(search('# 12').map(r=>r.id),[12,123]);
  assert.equal(search('12')[0].id,12);
  assert.deepEqual(search('#13'),[]);
  assert.deepEqual(search('#12 topology').map(r=>r.id),[12]);
});
test('typos, transpositions and compact abbreviations work without scattered-letter noise',()=>{
  const search=createThreadSearch(threads);
  assert.equal(search('geomtery')[0].id,12); // equal quality ties use stable IDs
  assert.equal(search('verifer')[0].id,12);
  assert.equal(search('tpology')[0].id,12);
  assert.equal(search('cadqury')[0].id,12);
  assert.deepEqual(search('cfg'),[]); // "configuration" is too long for this abbreviation
  assert.equal(createThreadSearch([{id:1,quote:'config',messages:[]}])('cfg')[0].id,1);
  assert.deepEqual(search('xyz'),[]);
  assert.deepEqual(search('cgv'),[]);
});
test('all query words are required, including across passage and reply',()=>{
  const search=createThreadSearch(threads);
  assert.deepEqual(search('cadquery topology').map(r=>r.id),[12]);
  assert.deepEqual(search('geometry absent'),[]);
  assert.equal(search('geometry verifier')[0].id,12);
});
test('snippets center on distant matches, merge ranges, and stay plain text',()=>{
  const body='Start. '.repeat(100)+'<img onerror="bad()"> Needle needle. '+'End. '.repeat(100);
  const search=createThreadSearch([{id:1,quote:'Other',messages:[{body}]}]);
  const result=search('needle')[0];assert.equal(result.label,'Comment');
  assert.ok(result.excerpt.leading&&result.excerpt.trailing);
  assert.equal(result.excerpt.text.slice(...result.excerpt.ranges[0]),'Needle');
  assert.ok(result.excerpt.text.length<=150);
  assert.deepEqual(search(''),[]);assert.deepEqual(search('  '),[]);assert.deepEqual(search('!!!'),[]);
});
test('index updates and repeat queries return cached results',()=>{
  const search=createThreadSearch(threads);assert.equal(search('topology'),search('topology'));
  const updated=createThreadSearch([{...threads[0],messages:[{body:'New reply'}]}]);
  assert.deepEqual(updated('topology'),[]);assert.equal(updated('new')[0].id,12);
});
