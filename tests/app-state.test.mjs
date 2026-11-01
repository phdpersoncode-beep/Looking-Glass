import test from 'node:test';
import assert from 'node:assert/strict';
import {initialAppState, transition, selectVisibleThreads, selectThreadSequence, nextOpenThread, createAppStore} from '../frontend/app-state.mjs';
const thread = (id, start = 0, end = 12, more = {}) => ({id, start, end, path: 'note.txt', quote: 'passage', anchor_kind: 'source', anchor_status: 'attached', messages: [], resolved: false, ...more});

test('only unattached defaults off and composes with resolved, search, navigation, and spotlight', () => {
  const threads = [thread(1), thread(2, 20, 30, {quote: 'lost passage', anchor_status: 'needs_reattachment'}),
    thread(3, 40, 50, {resolved: true, anchor_status: 'needs_reattachment'}), thread(4, 60, 70, {resolved: true})];
  let state = {...initialAppState(), threads};
  assert.equal(state.onlyUnattached, false);
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1, 2]);
  state = transition(state, {type: 'THREAD_ACTIVATED', threadId: 1, spotlight: true}).state;
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {onlyUnattached: true}}).state;
  assert.equal(state.spotlight, null);
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [2]);
  assert.deepEqual(selectThreadSequence(state).map(t => t.id), [2]);
  assert.equal(nextOpenThread(state, 1).id, 2);
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {showResolved: true}}).state;
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [2, 3]);
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {searchQuery: '#1'}}).state;
  assert.deepEqual(selectVisibleThreads(state), []);
  // Explicit references can still inspect a thread without changing filters.
  state = transition(state, {type: 'THREAD_ACTIVATED', threadId: 1, spotlight: true}).state;
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1]);
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {onlyUnattached: false}}).state;
  assert.equal(state.spotlight, null);
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1]);
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {searchQuery: ''}}).state;
  assert.deepEqual(selectThreadSequence(state).map(t => t.id), [1, 2, 3, 4]);
});

test('only unattached reconciles zen focus and reattached threads leave the filtered list', () => {
  let state = {...initialAppState({zen: true}), threads: [thread(1), thread(2, 20, 30, {anchor_status: 'needs_reattachment'})], focusedThread: 1};
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {onlyUnattached: true}}).state;
  assert.equal(state.focusedThread, 2);
  state = transition(state, {type: 'THREADS_RECEIVED', threads: [thread(1), thread(2, 20, 30)]}).state;
  assert.deepEqual(selectVisibleThreads(state), []);
  assert.equal(state.focusedThread, null);
  state = transition(state, {type: 'FILTERS_CHANGED', filters: {onlyUnattached: false}}).state;
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1, 2]);
  assert.equal(state.focusedThread, 1);
});

test('highlight inspection has no reveal effect; repeated card activation does', () => {
  const state = {...initialAppState(), threads: [thread(1)]};
  const inspected = transition(state, {type: 'THREAD_ACTIVATED', threadId: 1, origin: 'document-highlight', spotlight: true});
  assert.equal(inspected.state.focusedThread, 1);
  assert.deepEqual(inspected.state.spotlightIds, [1]);
  assert.deepEqual(inspected.effects, []);
  for (let i = 0; i < 2; i++) {
    const activated = transition(inspected.state, {type: 'THREAD_ACTIVATED', threadId: 1, origin: 'sidebar-card'});
    assert.deepEqual(activated.effects, [{type: 'REVEAL_THREAD', threadId: 1, origin: 'sidebar-card'}]);
  }
});

test('selectors never change focus and zen fallback is an explicit transition', () => {
  const state = {...initialAppState({zen: true}), threads: [thread(1), thread(2, 2, 5, {resolved: true})], focusedThread: 2};
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1]);
  assert.equal(state.focusedThread, 2);
  const next = transition(state, {type: 'FILTERS_CHANGED', filters: {showResolved: false}}).state;
  assert.equal(next.focusedThread, 1);
  const empty = transition(next, {type: 'FILTERS_CHANGED', filters: {searchQuery: 'unknown'}}).state;
  assert.equal(empty.focusedThread, null);
});

test('spotlight group tracks overlap without choosing a different focused thread', () => {
  const store = createAppStore();
  store.dispatch({type: 'THREADS_RECEIVED', threads: [thread(1), thread(2, 3, 8), thread(3, 12, 20)]});
  store.dispatch({type: 'THREAD_ACTIVATED', threadId: 2, spotlight: true});
  assert.deepEqual(store.state.spotlightIds, [1, 2]);
  store.dispatch({type: 'THREADS_RECEIVED', threads: [thread(1), thread(2, 3, 8), thread(4, 4, 6)]});
  assert.deepEqual(store.state.spotlightIds, [1, 2, 4]);
  assert.equal(store.state.focusedThread, 2);
  store.dispatch({type: 'SPOTLIGHT_CLEARED'});
  assert.equal(store.state.spotlight, null);
});

test('document and review preferences have separate authoritative facts', () => {
  const store = createAppStore({reviewPreference: true});
  store.dispatch({type: 'DOCUMENT_REQUESTED', path: 'report.html'});
  assert.equal(store.state.displayedDocument, null);
  store.dispatch({type: 'DOCUMENT_DISPLAYED', path: 'report.html'});
  assert.equal(store.state.reviewPreference, true);
  store.dispatch({type: 'DOCUMENT_REQUESTED', path: 'other.txt'});
  store.dispatch({type: 'DOCUMENT_CANCELLED'});
  assert.equal(store.state.requestedDocument, 'report.html');
  store.dispatch({type: 'DOCUMENT_REQUESTED', path: 'other.txt'});
  store.dispatch({type: 'DOCUMENT_FAILED'});
  assert.equal(store.state.requestedDocument, 'report.html');
});

test('spotlight navigation uses the scoped full list and preserves search ordering', () => {
  let state = {...initialAppState(), threads: [thread(3, 30, 40), thread(1), thread(2, 20, 25, {resolved: true})]};
  state = transition(state, {type: 'THREAD_ACTIVATED', threadId: 1, spotlight: true}).state;
  assert.deepEqual(selectVisibleThreads(state).map(t => t.id), [1]);
  assert.deepEqual(selectThreadSequence(state).map(t => t.id), [1, 3]);
  assert.equal(nextOpenThread(state, 3).id, 1);
  state = {...state, showResolved: true};
  assert.deepEqual(selectThreadSequence(state).map(t => t.id), [1, 2, 3]);
  assert.equal(nextOpenThread(state, 1).id, 3);
  state = {...state, searchQuery: '#3'};
  assert.deepEqual(selectThreadSequence(state).map(t => t.id), [3]);
  assert.equal(nextOpenThread(state, 3), null);
});

test('zen completion advances the full queue in spotlight and wraps past resolved threads', () => {
  const threads = [thread(1), thread(2, 20, 25, {resolved: true}), thread(3, 30, 40)];
  let state = {...initialAppState({zen: true, showResolved: true}), threads};
  state = transition(state, {type: 'THREAD_ACTIVATED', threadId: 3, spotlight: true}).state;
  const result = transition(state, {type: 'THREAD_COMPLETED', threadId: 3});
  assert.equal(result.state.focusedThread, 1);
  assert.deepEqual(result.state.spotlightIds, [1]);
  assert.deepEqual(result.effects, [{type: 'REVEAL_THREAD', threadId: 1, origin: 'zen-completion'}]);
  const last = transition({...result.state, threads: [thread(1), thread(2, 20, 25, {resolved: true})]}, {type: 'THREAD_COMPLETED', threadId: 1});
  assert.equal(last.state.focusedThread, null);
  assert.equal(last.state.spotlight, null);
  assert.deepEqual(last.effects, []);
  const refreshed = transition(last.state, {type: 'THREADS_RECEIVED', threads: [thread(1, 0, 12, {resolved: true}), threads[1]]});
  assert.equal(refreshed.state.focusedThread, null);
});

test('completion cannot steal focus outside zen or after the user chooses another thread', () => {
  const state = {...initialAppState(), threads: [thread(1), thread(2, 20, 30)], focusedThread: 1};
  assert.equal(transition(state, {type: 'THREAD_COMPLETED', threadId: 1}).state, state);
  const zen = {...state, zen: true, focusedThread: 2};
  assert.equal(transition(zen, {type: 'THREAD_COMPLETED', threadId: 1}).state, zen);
});

test('a poll completing the mutation first does not change the queued successor', () => {
  const state = {...initialAppState({zen: true}), focusedThread: 2,
    threads: [thread(1), thread(2, 20, 25, {resolved: true}), thread(3, 30, 40)]};
  const result = transition(state, {type: 'THREAD_COMPLETED', threadId: 2, order: [1, 2, 3]});
  assert.equal(result.state.focusedThread, 3);
});

test('pending thread navigation keeps displayed spotlight until the destination snapshot is ready',()=>{
 const first=thread(1),second=thread(2,0,6,{path:'other.txt'}),store=createAppStore();
 store.dispatch({type:'DOCUMENT_DISPLAYED',path:'note.txt'});
 store.dispatch({type:'THREADS_RECEIVED',threads:[first]});
 store.dispatch({type:'THREAD_ACTIVATED',threadId:1,spotlight:true});
 store.dispatch({type:'THREAD_NAVIGATION_REQUESTED',threadId:2});
 assert.equal(store.state.requestedThread,2);assert.equal(store.state.focusedThread,1);
 store.dispatch({type:'DOCUMENT_REQUESTED',path:'other.txt'});
 assert.equal(store.state.displayedDocument,'note.txt');
 assert.deepEqual(store.state.spotlightIds,[1]);assert.deepEqual(selectVisibleThreads(store.state).map(t=>t.id),[1]);
 const snapshots=[];store.subscribe(state=>snapshots.push({path:state.displayedDocument,thread:state.focusedThread,ids:state.spotlightIds}));
 store.dispatch({type:'DOCUMENT_DISPLAYED',path:'other.txt',discussions:{threads:[second]},activation:{threadId:2,spotlight:true}});
 assert.deepEqual(snapshots,[{path:'other.txt',thread:2,ids:[2]}]);
 assert.equal(store.state.requestedThread,null);assert.equal(store.state.focusedThread,2);
 assert.deepEqual(store.state.spotlightIds,[2]);assert.deepEqual(selectVisibleThreads(store.state).map(t=>t.id),[2]);
});

test('explicit document navigation and cancellation retire the requested thread cursor',()=>{
 let state={...initialAppState(),focusedThread:1};
 state=transition(state,{type:'THREAD_NAVIGATION_REQUESTED',threadId:2}).state;
 assert.equal(transition(state,{type:'THREAD_NAVIGATION_CANCELLED'}).state.requestedThread,null);
 assert.equal(transition(state,{type:'DOCUMENT_DISPLAYED',path:'manual.txt'}).state.requestedThread,null);
});
