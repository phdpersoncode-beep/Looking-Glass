import test from 'node:test';
import assert from 'node:assert/strict';
import {Text} from '@codemirror/state';
import {pythonPosition,definitionOffset} from '../frontend/python-navigation.mjs';

test('Python columns count Unicode points while editor offsets count UTF-16',()=>{
  const doc=Text.of(['# heading','value = "🦊"; café()']);
  const at=doc.line(2).from+doc.line(2).text.indexOf('café');
  assert.deepEqual(pythonPosition(doc,at),{line:2,column:13});
  assert.equal(definitionOffset(doc,{line:2,column:13}),at);
  assert.equal(definitionOffset(doc,{line:3,column:0}),null);
  assert.equal(definitionOffset(doc,{line:2,column:999}),null);
});
