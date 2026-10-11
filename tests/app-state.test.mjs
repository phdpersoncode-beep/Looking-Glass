import test from 'node:test';
import assert from 'node:assert/strict';
import {initialAppState, transition, selectVisibleThreads, createAppStore} from '../frontend/app-state.mjs';
const thread = (id, start = 0, end = 12, more = {}) => ({id, start, end, path: 'note.txt', quote: 'passage', anchor_kind: 'source', anchor_status: 'attached', messages: [], resolved: false, ...more});

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
