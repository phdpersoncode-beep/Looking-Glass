import test from 'node:test';
import assert from 'node:assert/strict';
import {codePointsToEditorUnits,editorUnitsToRawUnits,rawUnitsToCodePoints,editorUnitsToCodePoints} from '../frontend/coordinates.mjs';
import {resolveSourcePassage,resolveRenderedPassage,passageGroup} from '../frontend/passages.mjs';
import {visibleMap,mappedMarkdownHTML} from '../frontend/markdown-source.mjs';

test('coordinate boundaries distinguish code points, raw UTF-16 and editor CRLF',()=>{
 const text='A🧠\r\nB';
 assert.equal(codePointsToEditorUnits(text,4),4);
 assert.equal(editorUnitsToRawUnits(text,4),5);
 assert.equal(rawUnitsToCodePoints(text,5),4);
 assert.equal(editorUnitsToCodePoints(text,4),4);
 assert.equal(codePointsToEditorUnits(text,5),5);
});

test('source resolution refuses stale quotes, detached anchors and missing local ranges',()=>{
 const thread={id:1,path:'a',anchor_kind:'source',anchor_status:'attached',start:1,end:2,quote:'🧠'};
 const context={path:'a',content:'A🧠\r\nB',version:'v1'};
 assert.deepEqual(resolveSourcePassage(thread,context).range,{from:1,to:3,coordinates:'editor-utf16'});
 assert.equal(resolveSourcePassage(thread,{...context,content:'AB'}).status,'unavailable');
 assert.equal(resolveSourcePassage({...thread,anchor_status:'needs_reattachment'},context).status,'needs_reattachment');
 assert.equal(resolveSourcePassage(thread,{...context,dirty:true}).reason,'local_anchor_unavailable');
 assert.equal(resolveSourcePassage(thread,{...context,dirty:true,localRanges:[{id:1,from:2,to:3}]}).reason,'mapped_local_edits');
});

test('rendered resolution distinguishes unique contextual matches from ambiguous passages',()=>{
 const text='left same right; other same end';
 assert.equal(resolveRenderedPassage(text,{quote:'same'}).reason,'ambiguous_quote');
 assert.deepEqual(resolveRenderedPassage(text,{quote:'same',prefix:'left ',suffix:' right'}).range,{from:5,to:9,coordinates:'rendered-utf16'});
 assert.equal(resolveRenderedPassage(text,{quote:'absent'}).reason,'missing_passage');
 assert.equal(resolveRenderedPassage('only one',{quote:'one',prefix:'stale'}).status,'attached');
});

test('Markdown visible mapping is pure and preserves entity, escape and continuation spelling',()=>{
 assert.deepEqual(visibleMap('&amp; \\* 🧠',10,'& * 🧠'),[{from:10,to:15},{from:15,to:16},{from:16,to:18},{from:18,to:19},{from:19,to:20},{from:20,to:21}]);
 assert.deepEqual(visibleMap('first\n> next',0,'first\nnext').map(p=>p.from),[0,1,2,3,4,5,8,9,10,11]);
 assert.equal(visibleMap('wrong',0,'missing'),null);
 assert.match(mappedMarkdownHTML('**bold**\r\n\r\n| a |\r\n| --- |\r\n| x |'),/data-md-from="2" data-md-to="6"/);
});

test('batch coordinates agree at every Unicode and newline boundary',async()=>{
 const {sourceCoordinates,replacementFor}=await import('../frontend/coordinates.mjs');
 const text='A🧠\r\nB\rC\nD',points=Array.from({length:Array.from(text).length+1},(_,i)=>i),coordinates=sourceCoordinates(text,points);
 for(const point of points)assert.equal(coordinates.editor.get(point),codePointsToEditorUnits(text,point));
 assert.deepEqual(replacementFor('A🧠\r\nB','A🪞\r\nB'),{from:1,to:3,insert:'🪞'});
 assert.deepEqual(replacementFor('A\r\nB','A\nB'),{from:1,to:2,insert:'\n'});
});
