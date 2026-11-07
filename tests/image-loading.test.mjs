import test from 'node:test';
import assert from 'node:assert/strict';
import {loadImage} from '../frontend/image-loading.mjs';

test('replacement images await their load event rather than decoding the old request',async()=>{
  const img=new EventTarget();let assigned;
  Object.defineProperty(img,'src',{set(value){assigned=value;}});
  img.decode=()=>{throw Error('Invalid image request.');};
  let ready=false;const loading=loadImage(img,'blob:replacement').then(()=>{ready=true;});
  await Promise.resolve();assert.equal(assigned,'blob:replacement');assert.equal(ready,false);
  img.dispatchEvent(new Event('load'));await loading;assert.equal(ready,true);
});

test('load errors reject and a later valid image can load on the same element',async()=>{
  const img=new EventTarget();const failed=loadImage(img,'broken');img.dispatchEvent(new Event('error'));
  await assert.rejects(failed,/Unable to load/);
  const loading=loadImage(img,'valid');img.dispatchEvent(new Event('load'));assert.equal(await loading,img);
});
