import test from 'node:test';
import assert from 'node:assert/strict';
import {parser,TaskList} from '@lezer/markdown';
import {Text} from '@codemirror/state';
import {markdownListLines} from '../frontend/markdown-lists.mjs';

const layout=source=>{
  const doc=Text.of(source.split('\n'));
  return markdownListLines(parser.configure([TaskList]).parse(source),doc).map(line=>({
    text:doc.lineAt(line.from).text,depth:line.depth,
    content:doc.sliceString(line.indentTo,doc.lineAt(line.from).to),
    marker:line.markerFrom===null?null:doc.sliceString(line.markerFrom,line.markerTo)
  }));
};

test('mixed lists keep three levels and sibling numbering',()=>{
  const rows=layout('Before\n\n- Parent\n  1. Child\n     - Grandchild\n  2. Sibling\n- Next\n\nAfter');
  assert.deepEqual(rows.map(r=>[r.depth,r.marker]),[[1,'- '],[2,'1. '],[3,'- '],[2,'2. '],[1,'- ']]);
  assert.deepEqual(rows.map(r=>r.content),['- Parent','1. Child','- Grandchild','2. Sibling','- Next']);
});

test('ordered continuation paragraphs and lazy lines retain item ownership',()=>{
  const rows=layout('12. First\n    continuation\nlazy text\n\n    New paragraph\n13. Next');
  assert.deepEqual(rows.map(r=>r.depth),[1,1,1,1,1,1]);
  assert.deepEqual(rows.map(r=>r.content),['12. First','continuation','lazy text','','New paragraph','13. Next']);
  assert.equal(rows[1].marker,null);
});

test('task prefixes leave extra code indentation intact',()=>{
  const rows=layout('- [ ] Task\n\n      code\n\n  - [x] Child\n');
  assert.deepEqual(rows.filter(r=>r.marker).map(r=>[r.depth,r.marker]),[[1,'- [ ] '],[2,'- [x] ']]);
  assert.equal(rows.find(r=>r.text.includes('code')).content,'    code');
});

test('fenced and indented literal list markers stay code',()=>{
  assert.deepEqual(layout('```md\n- literal\n  1. literal\n```\n\n    - indented code\n'),[]);
  // An ordered list cannot interrupt a paragraph at an arbitrary starting value.
  const rows=layout('- Parent\n  12. continuation');
  assert.equal(rows[1].marker,null);
});
