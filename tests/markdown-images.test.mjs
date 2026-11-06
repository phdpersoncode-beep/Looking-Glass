import test from 'node:test';
import assert from 'node:assert/strict';
import {imageRanges,imageID,imageLink,imagePath} from '../frontend/markdown-images.mjs';
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
test('encoded filename delimiters survive relative image resolution',()=>{
  assert.equal(imagePath('../assets/chart%231%3F%2520.png','docs/notes.md'),'assets/chart#1?%20.png');
  assert.equal(imagePath('my%20photo.png','notes.md'),'my photo.png');
});

test('image widths preserve destinations and captions in wiki, standard and reference embeds',async()=>{
  const {imageCaption,resizedImageSource}=await import('../frontend/image-size.mjs');
  assert.deepEqual(imageCaption('A caption|320'),{alt:'A caption',width:320});
  assert.deepEqual(imageCaption('Literal|word'),{alt:'Literal|word',width:null});
  for(const [before,after] of [
    ['![[my screenshot.png]]','![[my screenshot.png|240]]'],
    ['![[photo.png|400]]','![[photo.png|240]]'],
    ['![Caption][]','![Caption|240][Caption]'],
    ['![Caption]','![Caption|240][Caption]'],
    ['![Nested [caption]](chart%231.png "Title")','![Nested [caption]|240](chart%231.png "Title")'],
    ['![A\\] label|320][picture]','![A\\] label|240][picture]']
  ])assert.equal(resizedImageSource(before,240),after);
  assert.deepEqual(imageRanges('![[photo.png|240]]').map(r=>r.href),['photo.png']);
});
