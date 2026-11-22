import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cardTitle,milestoneInsertion,outlineRows,shiftTarget} from '../frontend/task-outline.mjs';
const cards=[
 {id:1,title:'Later',milestone:1,milestone_number:9,parent_id:null,outline_position:0},
 {id:2,title:'First',milestone:1,milestone_number:2,parent_id:null,outline_position:1},
 {id:3,title:'Task',parent_id:2,outline_position:5},
 {id:4,title:'Subitem',parent_id:3,outline_position:2},
 {id:5,title:'Unassigned',parent_id:null,outline_position:0},
 {id:6,title:'Second task',parent_id:2,outline_position:6},
];
test('milestone title contains its number without rewriting stored text',()=>{
 assert.equal(cardTitle(cards[0]),'M9: Later');assert.equal(cardTitle(cards[2]),'Task');assert.equal(cards[0].title,'Later');
});
test('outline is milestone-number ordered with task subtrees and unassigned roots',()=>{
 assert.deepEqual(outlineRows(cards).map(r=>[r.card.id,r.depth]),[[2,0],[3,1],[4,2],[6,1],[1,0],[5,0]]);
 assert.deepEqual(outlineRows(cards,{rootId:2}).map(r=>r.card.id),[3,4,6]);
 assert.deepEqual(outlineRows(cards,{folded:new Set([3])}).map(r=>r.card.id),[2,3,6,1,5]);
});
test('archived ancestors retain active descendants as context in the hierarchy',()=>{
 const archived=cards.map(c=>c.id===2?{...c,archived:1}:c);
 const rows=outlineRows(archived);assert.equal(rows[0].context,true);assert.equal(rows[1].card.id,3);
 assert.deepEqual(outlineRows(archived,{archived:true}).map(r=>r.card.id),[2]);
});
test('Tab nests under the previous sibling and Shift+Tab lifts after the parent',()=>{
 assert.deepEqual(shiftTarget(cards,6),{parent_id:3,before:null});
 assert.deepEqual(shiftTarget(cards,4,true),{parent_id:2,before:6});
 assert.deepEqual(shiftTarget(cards,5),{parent_id:1,before:null});
 assert.equal(shiftTarget(cards,2),null);assert.equal(shiftTarget(cards,3),null);assert.equal(shiftTarget(cards,5,true),null);
});

test('collapse all shows only local top-level tasks without changing hierarchy or order',()=>{
 const before=structuredClone(cards);
 assert.deepEqual(outlineRows(cards,{collapsed:true}).map(r=>r.card.id),[2,1,5]);
 assert.deepEqual(outlineRows(cards,{rootId:2,collapsed:true}).map(r=>r.card.id),[3,6]);
 assert.deepEqual(outlineRows(cards,{rootId:3,collapsed:true}).map(r=>r.card.id),[4]);
 assert.deepEqual(outlineRows(cards,{rootId:2}).map(r=>r.card.id),[3,4,6]);
 assert.deepEqual(cards,before);
});

test('collapsed outlines keep newly polled descendants hidden and archived context visible',()=>{
 const updated=[...cards,{id:7,title:'New child',parent_id:5,outline_position:7}];
 assert.deepEqual(outlineRows(updated,{collapsed:true}).map(r=>r.card.id),[2,1,5]);
 assert.deepEqual(outlineRows(updated).map(r=>r.card.id),[2,3,4,6,1,5,7]);
 const archived=updated.map(c=>c.id===2?{...c,archived:1}:c);
 assert.equal(outlineRows(archived,{collapsed:true})[0].context,true);
});

test('sidebar keeps archived tasks in place and expands individual branches after collapse all', () => {
  const archived = cards.map(card => [2, 4].includes(card.id) ? {...card, archived: true} : card);
  const rows = outlineRows(archived, {includeArchived: true, collapsed: true, expanded: new Set([2, 3])});
  assert.deepEqual(rows.map(({card}) => card.id), [2, 3, 4, 6, 1, 5]);
  assert.equal(rows[2].card.archived, true);
  assert.ok(rows.every(row => !row.context));
  assert.equal(shiftTarget(archived, 4, true), null);
});

test('milestone placement follows the cursor branch and skips archived or moving milestones', () => {
  const ordered = cards.map(card => [3, 4, 6].includes(card.id) ? {...card, milestone_id: 2} : card);
  assert.equal(milestoneInsertion(ordered, 2, false), 2);
  assert.equal(milestoneInsertion(ordered, 2, true), 1);
  assert.equal(milestoneInsertion(ordered, 3, false), 1);
  assert.equal(milestoneInsertion(ordered, 5, false), null);
  assert.equal(milestoneInsertion(ordered, 2, true, 1), null);
  assert.equal(milestoneInsertion(ordered.map(card => card.id === 2 ? {...card, archived: true} : card),
    2, false), 1);
});
