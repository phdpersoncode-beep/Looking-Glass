import test from 'node:test';
import assert from 'node:assert/strict';
import {imageRanges,imageID,imageLink} from '../frontend/markdown-images.mjs';
import {markdown} from '../frontend/markdown-math.mjs';

test('standard and wiki images preserve source coordinates and exclude code',()=>{
  const source='🪞 ![Caption](photo.png)\n\n![[my screenshot.jpg]]\n\n`![[code.png]]`\n\n```md\n![](code.png)\n```';
  const ranges=imageRanges(source);
  assert.deepEqual(ranges.map(r=>source.slice(r.from,r.to)),['![Caption](photo.png)','![[my screenshot.jpg]]']);
  assert.deepEqual(ranges.map(r=>r.href),['photo.png','my screenshot.jpg']);
});
test('managed references retain identity across rename and encode names',()=>{
  const id='a'.repeat(64),href=imageLink({id,name:'my screenshot (2).png'});
  assert.equal(imageID(href),id);assert.equal(imageID(imageLink({id,name:'renamed.jpg'})),id);
  assert.ok(href.includes('%20'));assert.equal(imageID('https://example.com/photo.png'),null);
});
test('wiki image attributes are escaped',()=>{
  assert.ok(markdown.parse('![[x" onerror="bad.png]]').includes('&quot;'));
  assert.ok(!markdown.parse('![[x" onerror="bad.png]]').includes('src="x"'));
});
