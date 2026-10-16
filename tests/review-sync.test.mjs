import test from 'node:test';
import assert from 'node:assert/strict';
import {createReviewSync,prepareWorkMode} from '../frontend/review-sync.mjs';
import {apply,accepted} from '../frontend/review-model.mjs';
const metadata={author:'Altay',role:'human',at:'2026-10-11'};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function setup(api){
 const session={path:'a.txt',content:'A',diskContent:'A',version:'1',workMode:'review',state:null};
 const controller=createReviewSync(session,{api,metadata:()=>metadata});
 controller.adopt({id:1,version:'1',base:'A',content:'A',segments:[{text:'A',kind:'base'}],status:'pending'});
 return {session,controller};
}

test('edits arriving during a save cannot mutate the sent batch or disappear',async()=>{
 const first=deferred(),calls=[];
 const {session,controller}=setup(async(_route,_method,body)=>{calls.push(structuredClone(body));if(calls.length===1)return first.promise;return {version:'3',edit:metadata};});
 controller.enqueue([{start:1,end:1,insert:'B'}]);session.content='AB';
 const saving=controller.flush();assert.equal(controller.status,'saving');
 controller.enqueue([{start:2,end:2,insert:'C'}]);session.content='ABC';
 first.resolve({version:'2',edit:metadata});await saving;
 assert.deepEqual(calls.map(c=>c.operations),[[{start:1,end:1,insert:'B'}],[{start:2,end:2,insert:'C'}]]);
 assert.equal(session.diskContent,'ABC');assert.equal(accepted(session.reviewSegments),'ABC');assert.equal(controller.status,'clean');
});

test('stale remote completion and revision-changed approval are rejected',async()=>{
 const remote=deferred();const {session,controller}=setup(()=>remote.promise);
 const target=controller.approvalTarget(),poll=controller.poll();
 controller.enqueue([{start:1,end:1,insert:'B'}]);session.content='AB';
 remote.resolve({id:1,version:'2',status:'pending',content:'X',segments:[{text:'X',kind:'base'}]});await poll;
 assert.equal(session.content,'AB');assert.equal(session.review.version,'1');assert.throws(()=>controller.assertApproval(target),/changed/);
});

test('failed saves retain all operations and retry uses the unchanged saved revision',async()=>{
 let failed=true;const calls=[];
 const {session,controller}=setup(async(_route,_method,body)=>{calls.push(body);if(failed)throw Error('conflict');return {version:'2',edit:metadata};});
 controller.enqueue([{start:1,end:1,insert:'B'}]);await assert.rejects(controller.flush(),/conflict/);
 assert.equal(controller.status,'conflicted');assert.equal(session.pendingOps.length,1);assert.equal(session.review.version,'1');
 failed=false;await controller.retry();assert.equal(controller.status,'clean');assert.equal(calls[1].version,'1');assert.equal(session.diskContent,'AB');
});

test('failed or stale mode preparation never discards the current session',async()=>{
 const session={path:'a',content:'original',diskContent:'original',version:'v1',workMode:'edit',state:{undo:'retained'},dirty:false};
 const ports={supports:()=>true,sync:()=>({adopt(){}}),api:async()=>{throw Error('offline');}};
 await assert.rejects(prepareWorkMode(session,'review',ports),/offline/);assert.equal(session.workMode,'edit');assert.equal(session.state.undo,'retained');
 ports.api=async()=>({id:1,content:'proposal',version:'d1'});const prepared=await prepareWorkMode(session,'review',ports);
 session.content='typed';assert.throws(()=>prepared.commit(),/changed/);assert.equal(session.workMode,'edit');assert.equal(session.state.undo,'retained');
});

test('mode sessions restore history only for a compatible document and draft',async()=>{
 const editState={undo:'edit'},reviewState={undo:'review'};
 const session={path:'a',content:'A',diskContent:'A',version:'v1',workMode:'edit',state:editState,dirty:false};
 let draft={id:1,content:'AB',version:'d1',base:'A',segments:[{text:'AB',kind:'base'}]};
 const controller=createReviewSync(session,{metadata:()=>metadata,api:async()=>null});
 const ports={supports:()=>true,sync:()=>controller,api:async(route)=>route==='reviews'?draft:{content:'A',version:'v1'}};
 (await prepareWorkMode(session,'review',ports)).commit();session.state=reviewState;
 (await prepareWorkMode(session,'edit',ports)).commit();assert.equal(session.state,editState);
 (await prepareWorkMode(session,'review',ports)).commit();assert.equal(session.state,reviewState);
 (await prepareWorkMode(session,'edit',ports)).commit();draft={...draft,id:2};
 (await prepareWorkMode(session,'review',ports)).commit();assert.equal(session.state,null);
});
