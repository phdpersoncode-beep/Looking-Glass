import {test} from 'node:test';
import assert from 'node:assert/strict';
import {bindTaskDismiss} from '../frontend/task-dialog.mjs';

function popup() {
  const handlers=new Map(), dialog={addEventListener:(name,callback)=>handlers.set(name,callback),getBoundingClientRect:()=>({left:200,right:968,top:32,bottom:768})};
  let dismissed=0;
  bindTaskDismiss(dialog,()=>dismissed++);
  const send=(name,x,y,extra={})=>handlers.get(name)({target:dialog,button:0,clientX:x,clientY:y,preventDefault(){this.prevented=true;},...extra});
  return {dialog,send,count:()=>dismissed};
}
test('only a complete primary-button backdrop click dismisses card focus',()=>{
 const {send,count,dialog}=popup();
 send('pointerdown',100,400);send('click',100,400);assert.equal(count(),1);
 send('pointerdown',400,400);send('click',100,400);assert.equal(count(),1);
 send('pointerdown',100,400);send('click',400,400);assert.equal(count(),1);
 send('pointerdown',400,400);send('click',400,400);assert.equal(count(),1);
 send('pointerdown',100,400,{button:2});send('click',100,400);assert.equal(count(),1);
 send('pointerdown',100,400);send('click',100,400,{target:{parent:dialog}});assert.equal(count(),1);
 send('pointerdown',100,400);send('pointercancel');send('click',100,400);assert.equal(count(),1);
});
test('all four backdrop edges dismiss, while the card edges remain inside',()=>{
 const {send,count}=popup();
 for(const [x,y] of [[199,400],[968,400],[400,31],[400,768]]){send('pointerdown',x,y);send('click',x,y);}
 assert.equal(count(),4);
 for(const [x,y] of [[200,32],[967,767]]){send('pointerdown',x,y);send('click',x,y);}
 assert.equal(count(),4);
});
test('Escape uses the same dismissal callback',()=>{
 const {send,count}=popup();send('cancel');assert.equal(count(),1);
});
