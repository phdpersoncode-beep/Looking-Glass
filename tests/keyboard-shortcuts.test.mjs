import test from 'node:test';
import assert from 'node:assert/strict';
import {isZenShortcut} from '../frontend/keyboard-shortcuts.mjs';

const key = changes => ({key:'z',code:'KeyZ',altKey:true,ctrlKey:false,metaKey:false,shiftKey:false,isComposing:false,...changes});

test('zen accepts Alt+Z, legacy aliases, and the macOS Option character',()=>{
  for(const changes of [{},{ctrlKey:true},{metaKey:true},{key:'Ω'},{key:'Z'}])
    assert.equal(isZenShortcut(key(changes)),true);
});

test('zen preserves undo/redo, composing input and AltGr characters',()=>{
  for(const changes of [{altKey:false,ctrlKey:true},{shiftKey:true},{isComposing:true},
    {key:'ż',ctrlKey:true},{key:'ż',ctrlKey:true,getModifierState:name=>name==='AltGraph'},
    {ctrlKey:true,getModifierState:name=>name==='AltGraph'},{key:'x',code:'KeyX'}])
    assert.equal(isZenShortcut(key(changes)),false);
});
