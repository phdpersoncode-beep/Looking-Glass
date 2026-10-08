import test from 'node:test';
import assert from 'node:assert/strict';
import {parse} from 'parse5';
import {prepareHTMLPreview,sourceOffsets} from '../frontend/html-source.mjs';
import {htmlTextMap} from '../frontend/html-text-map.mjs';

const marker='data-lg-test';
function records(source){return prepareHTMLPreview(source,marker).mapping.records;}
function textMap(raw,text=raw){return htmlTextMap(raw,10,text);}

test('entities cover their complete original spelling, including legacy and multi-codepoint entities',()=>{
  for(const [raw,text] of [['&amp;','&'],['&copy','©'],['&#65;','A'],['&#x1f600;','😀'],['&NotEqualTilde;','≂̸'],['&notit;','¬it;'],['&#0;','�']]){
    const map=textMap(raw,text);assert.ok(map,raw);
    assert.equal(map.starts[0],10);assert.equal(map.ends.at(-1),10+raw.length);
    if(!raw.includes('it;'))assert.ok(map.starts.every(v=>v===10));
  }
});

test('CRLF, bare CR, astral characters, and pre leading newline preserve offsets',()=>{
  assert.deepEqual(textMap('A\r\nB\rC','A\nB\nC'),{starts:[10,11,13,14,15],ends:[11,13,14,15,16]});
  assert.deepEqual(textMap('\r\nhello','hello'),{starts:[12,13,14,15,16],ends:[13,14,15,16,17]});
  assert.deepEqual(textMap('😀'),{starts:[10,11],ends:[11,12]});
  assert.equal(textMap('other','same'),null);
  assert.equal(textMap('a<b>b','ab'),null);
});

test('preview instrumentation preserves every original byte outside temporary tag attributes',()=>{
  const source='<!DOCTYPE html>\r\n<p id=x>Hello <b>world</b> &amp; 🪞</p><img src=x/><svg><path d="M0 0"/></svg><!-- note -->';
  const prepared=prepareHTMLPreview(source,marker);
  assert.equal(prepared.content.replace(/ data-lg-test="\d+"/g,''),source);
  assert.deepEqual(prepared.mapping.records.map(r=>source.slice(r.from,r.to)),['Hello ','world',' &amp; 🪞']);
  assert.deepEqual(prepared.mapping.records.map(r=>r.text),['Hello ','world',' & 🪞']);
  // Never turn an unquoted trailing slash into a self-closing delimiter.
  function image(node){return node.tagName==='img'?node:node.childNodes?.map(image).find(Boolean);}
  assert.deepEqual(image(parse(prepared.content)).attrs.filter(a=>a.name!==marker),image(parse(source)).attrs);
});

test('implicit table sections, optional end tags, repeated text, and body fragments have distinct source identities',()=>{
  const source='Intro<table><tr><td>same<td>same</table>Ending';
  const mapped=records(source);
  assert.deepEqual(mapped.map(r=>r.text),['Intro','same','same','Ending']);
  const duplicates=mapped.filter(r=>r.text==='same');assert.notEqual(duplicates[0].id,duplicates[1].id);
  for(const r of mapped)assert.equal(source.slice(r.from,r.to),r.text);
  assert.equal(mapped[0].id,null);
});

test('script, styles, templates, noscript, and form values are excluded',()=>{
  const source='<style>same</style><script>same</script><template><p>same</p></template><noscript>same</noscript><textarea>same</textarea><p>same</p>';
  assert.deepEqual(records(source).map(r=>r.text),['same']);
});

test('marker collisions and invalid attribute names are rejected',()=>{
  assert.throws(()=>prepareHTMLPreview('<p DATA-LG-TEST>text</p>',marker));
  assert.throws(()=>prepareHTMLPreview('<p>text</p>','onclick'));
});

test('batch Unicode offsets preserve raw CRLF and scan large sibling lists safely',()=>{
  assert.deepEqual([...sourceOffsets('A😀\r\nB',[5,2,1,2,0])],[[0,0],[1,1],[2,3],[5,6]]);
  const source='<main>'+('<p>same &amp; text</p>\n'.repeat(10000))+'</main>';
  const prepared=prepareHTMLPreview(source,marker);
  assert.equal(prepared.mapping.records.length,20000);
  assert.equal(prepared.content.replace(/ data-lg-test="\d+"/g,''),source);
});
