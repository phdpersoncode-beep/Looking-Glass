import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formatJSON} from '../frontend/json-format.mjs';
test('formats JSON without changing numeric/string tokens or duplicate keys',()=>{
  const source='{"n":9007199254740993,"n":1e1000,"s":"a \\" b \\n München","empty":[],"object":{},"a":[true,null,{"x":-0}]}';
  const result=formatJSON(source);
  assert.ok(result.includes('9007199254740993'));assert.ok(result.includes('1e1000'));
  assert.equal((result.match(/"n":/g)||[]).length,2);assert.ok(result.includes('"x": -0'));
  assert.equal(formatJSON(result),result);assert.equal(JSON.parse(result).s,JSON.parse(source).s);
  assert.ok(formatJSON('[1,2]','\r\n').includes('\r\n  2\r\n'));
});
test('rejects invalid JSON and handles scalar values',()=>{
  for(const value of ['', '{"x":}', '[1,]'])assert.throws(()=>formatJSON(value));
  assert.equal(formatJSON(' "hello" '),'"hello"\n');assert.equal(formatJSON('null'),'null\n');
});
