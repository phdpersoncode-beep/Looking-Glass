import test from 'node:test';
import assert from 'node:assert/strict';
import {createNavigationController,createRequestGate,threadDestination} from '../frontend/navigation.mjs';
import {createSurfaceSession} from '../frontend/document-session.mjs';
import {createThreadNavigator} from '../frontend/thread-navigation.mjs';
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('queued navigation resolves for its own target and supersedes old reads',async()=>{
  const first=deferred(),loads=[],displayed=[];
  const nav=createNavigationController({load:async(path,request)=>{loads.push(path);if(path==='a')await first.promise;if(request.current())displayed.push(path);}});
  const a=nav.open('a');await Promise.resolve();
  const b=nav.open('b'),c=nav.open('c');
  let done=false;c.then(()=>done=true);await Promise.resolve();assert.equal(done,false);
  first.resolve();
  assert.equal((await a).status,'superseded');assert.equal((await b).status,'superseded');assert.equal((await c).status,'ready');
  assert.deepEqual(displayed,['c']);assert.equal(nav.busy,false);
});

test('a pending write completes before the superseding document loads',async()=>{
  const write=deferred(),events=[];
  const nav=createNavigationController({load:async(path)=>{if(path==='a'){events.push('write');await write.promise;events.push('saved');}events.push(path);}});
  const a=nav.open('a');await new Promise(r=>setImmediate(r));const b=nav.open('b');
  assert.deepEqual(events,['write']);write.resolve();await Promise.all([a,b]);assert.deepEqual(events,['write','saved','a','b']);
});

test('failure does not poison the navigation queue and context gates reject stale completion',async()=>{
  const failures=[],nav=createNavigationController({load:async(path)=>{if(path==='bad')throw Error('missing');},onFailure:request=>failures.push(request.path)});
  await assert.rejects(nav.open('bad'),/missing/);assert.equal((await nav.open('good')).status,'ready');assert.deepEqual(failures,['bad']);
  const gate=createRequestGate(),old=gate.begin('draft:1'),next=gate.begin('draft:2');
  assert.equal(gate.accepts(old,'draft:1'),false);assert.equal(gate.accepts(next,'draft:1'),false);assert.equal(gate.accepts(next,'draft:2'),true);
});

test('surface lifetimes suspend/resume and dispose resources exactly once',async()=>{
 const events=[],surface=createSurfaceSession({suspend:()=>events.push('suspend'),resume:()=>events.push('resume'),dispose:()=>events.push('dispose')});
 await surface.suspend();surface.resume();surface.dispose();surface.dispose();assert.deepEqual(events,['suspend','resume','dispose']);
 await assert.rejects(surface.suspend(),/mounted/);
});

test('navigation policy retains distinct source, rendered, removed and Git destinations',()=>{
 const options={historyPath:'history',originalPath:id=>'original/'+id};
 assert.deepEqual(threadDestination({id:1,path:'a',anchor_kind:'source',anchor_status:'needs_reattachment'},null,options),{path:'original/1',surface:'original'});
 assert.deepEqual(threadDestination({id:2,path:'a',anchor_kind:'rendered',anchor_status:'needs_reattachment'},null,options),{path:'a',surface:'rendered'});
 assert.equal(threadDestination({id:3,anchor_kind:'commit'},null,options).path,'history');
});

test('a newer reading intention cancels a pending thread reveal',async()=>{
 const opening=deferred(),effects=[],thread={id:1,path:'a',anchor_kind:'source',anchor_status:'attached'};
 const navigator=createThreadNavigator({find:()=>thread,session:()=>null,displayed:()=>null,
  paths:{historyPath:'history',originalPath:id=>'original/'+id},open:()=>opening.promise,
  focus:()=>effects.push('focus'),revealSource:()=>effects.push('reveal')});
 const activation=navigator.activate(1);navigator.invalidate();opening.resolve({status:'ready'});await activation;
 assert.deepEqual(effects,[]);
});

test('a missing current file reveals immutable context after it becomes ready',async()=>{
 const original=deferred(),effects=[],thread={id:1,path:'missing',anchor_kind:'source',anchor_status:'attached'};
 const navigator=createThreadNavigator({find:()=>thread,session:()=>null,displayed:()=>null,
  paths:{historyPath:'history',originalPath:id=>'original/'+id},
  open:async path=>{effects.push('open:'+path);if(path==='missing')throw Object.assign(Error('missing'),{status:404});return original.promise;},
  focus:id=>effects.push('focus:'+id)});
 const activation=navigator.activate(1);await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(effects,['open:missing','open:original/1']);
 original.resolve({status:'ready'});await activation;assert.equal(effects.at(-1),'focus:1');
});
