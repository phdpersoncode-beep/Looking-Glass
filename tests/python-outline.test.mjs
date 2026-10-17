import test from 'node:test';
import assert from 'node:assert/strict';
import {pythonDefinitions} from '../frontend/python-outline.mjs';

test('outline distinguishes decorated async functions, classes, methods and nested definitions',()=>{
  const source='LIMIT = 5\n@decorator\nasync def run():\n    local = 1\n    def inner(): pass\nclass Part:\n    attribute = 2\n    @staticmethod\n    def build():\n        hidden = 3\n';
  assert.deepEqual(pythonDefinitions(source).map(({name,kind,depth})=>({name,kind,depth})),[
    {name:'LIMIT',kind:'variable',depth:0},{name:'run',kind:'function',depth:0},{name:'inner',kind:'function',depth:1},
    {name:'Part',kind:'class',depth:0},{name:'build',kind:'method',depth:1}
  ]);
});
test('module bindings include annotations, unpacking, chained assignments and conditional definitions',()=>{
  const source='name: str\nx = y = 2\na, (b, c) = (1, (2, 3))\nif ready:\n    cache = {}\nelse:\n    cache = None\nif (found := lookup()): pass\nobj.field = 2\narr[0] = 3\nimport os\n';
  assert.deepEqual(pythonDefinitions(source).map(d=>d.name),['name','x','y','a','b','c','cache','found']);
});
test('comments and strings cannot invent definitions; Unicode offsets and lines match source',()=>{
  const source='# def fake():\ntext = "class Nope: def missing():"\n\ncafé = 1\nclass Shape:\n    def valid(self): pass\n';
  for(const item of pythonDefinitions(source)){
    assert.equal(source.slice(item.from,item.from+item.name.length),item.name);
    assert.equal(item.line,source.slice(0,item.from).split('\n').length);
  }
  assert.deepEqual(pythonDefinitions(source).map(d=>d.name),['text','café','Shape','valid']);
});
test('incomplete edits keep readable definitions and an empty module has an empty outline',()=>{
  assert.deepEqual(pythonDefinitions(''),[]);
  assert.deepEqual(pythonDefinitions('class Part:\n    def build(self):\n        value =\n\ndef later():\n    pass\n').map(d=>d.name),['Part','build','later']);
});
test('starred module bindings are included while lambda-local assignments are omitted',()=>{
  assert.deepEqual(pythonDefinitions('first, *rest = items\nf = lambda: (hidden := 1)\n').map(d=>d.name),['first','rest','f']);
});
