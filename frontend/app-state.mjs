import {passageGroup} from './passages.mjs';
export {passageGroup} from './passages.mjs';
import {createThreadSearch} from './thread-search.mjs';

const searchIndexes = new WeakMap();
export function threadEligible(thread, state) {
  return (state.showResolved || !thread.resolved) &&
    (state.showUnattached !== false || thread.anchor_status === 'attached');
}
export function selectVisibleThreads(state) {
  if (state.spotlight) return state.threads.filter(t => state.spotlightIds.includes(t.id));
  const eligible = state.threads.filter(t => threadEligible(t, state));
  if (!state.searchQuery.trim()) return eligible;
  let search = searchIndexes.get(state.threads);
  if (!search) { search = createThreadSearch(state.threads); searchIndexes.set(state.threads, search); }
  const byId = new Map(eligible.map(t => [t.id, t]));
  return search(state.searchQuery).map(result => byId.get(result.id)).filter(Boolean);
}

export function initialAppState(preferences = {}) {
  return {displayedDocument: null, requestedDocument: null, focusedThread: null, requestedThread: null,
    spotlight: null, spotlightIds: [], threads: [], searchQuery: '', scope: 'file',
    showResolved: false, showUnattached: true, zen: false, reviewPreference: false, ...preferences};
}

export function selectThreadSequence(state) {
  const threads = selectVisibleThreads({...state, spotlight: null, spotlightIds: []});
  return state.searchQuery.trim() ? threads : threads.sort((a, b) =>
    (a.path > b.path) - (a.path < b.path) || a.start - b.start || a.id - b.id);
}

export function nextOpenThread(state, id, order = selectThreadSequence(state).map(t => t.id)) {
  const at = order.indexOf(id), byId = new Map(state.threads.map(t => [t.id, t]));
  for (let step = 1; step <= order.length; step++) {
    const candidate = byId.get(order[(at + step + order.length) % order.length]);
    if (candidate && candidate.id !== id && !candidate.resolved) return candidate;
  }
  return null;
}

function reconcileFocus(state) {
  const spotlightIds = passageGroup(state.threads, state.spotlight);
  let next = {...state, spotlightIds, spotlight: spotlightIds.length ? state.spotlight : null};
  if (next.zen && !next.spotlight) {
    const visible = selectVisibleThreads(next).filter(t => !t.resolved);
    if (!visible.some(t => t.id === next.focusedThread)) next.focusedThread = visible[0]?.id ?? null;
  }
  return next;
}

export function transition(state, event) {
  let next = state;
  const effects = [];
  switch (event.type) {
    case 'THREAD_ACTIVATED': {
      const seeds = event.ids?.map(id => state.threads.find(t => t.id === id)).filter(Boolean);
      const thread = event.thread || state.threads.find(t => t.id === event.threadId);
      const spotlight = event.spotlight ? {path: thread?.path || state.displayedDocument, seeds: seeds?.length ? seeds : thread ? [thread] : []} : null;
      next = {...state, focusedThread: event.threadId, requestedThread: null, spotlight};
      next.spotlightIds = event.spotlight ? passageGroup(state.threads, spotlight) : [];
      if (event.origin && event.origin !== 'document-highlight') effects.push({type: 'REVEAL_THREAD', threadId: event.threadId, origin: event.origin});
      break;
    }
    case 'THREAD_COMPLETED': {
      if (!state.zen || state.focusedThread !== event.threadId) break;
      const thread = nextOpenThread(state, event.threadId, event.order);
      const spotlight = thread && state.spotlight ? {path: thread.path, seeds: [thread]} : null;
      next = {...state, focusedThread: thread?.id ?? null, spotlight,
        spotlightIds: passageGroup(state.threads, spotlight)};
      if (thread) effects.push({type: 'REVEAL_THREAD', threadId: thread.id, origin: 'zen-completion'});
      break;
    }
    case 'THREAD_NAVIGATION_REQUESTED': next = {...state, requestedThread: event.threadId}; break;
    case 'THREAD_NAVIGATION_CANCELLED': next = {...state, requestedThread: null}; break;
    case 'FOCUS_CLEARED': next = {...state, focusedThread: null, requestedThread: null}; break;
    case 'SPOTLIGHT_CLEARED': next = reconcileFocus({...state, spotlight: null, spotlightIds: [], requestedThread: null}); break;
    case 'THREADS_RECEIVED': {
      next = {...state, threads: event.threads};
      if (event.activation && event.threads.some(t => t.id === event.activation.threadId)) {
        next = transition(next, {type: 'THREAD_ACTIVATED', ...event.activation}).state;
      } else next = reconcileFocus(next);
      if(event.availableIds&&!event.availableIds.includes(next.focusedThread))next.focusedThread=null;
      break;
    }
    case 'FILTERS_CHANGED': next = reconcileFocus({...state, ...event.filters}); break;
    case 'ZEN_CHANGED': next = reconcileFocus({...state, zen: event.value}); break;
    case 'REVIEW_PREFERENCE_CHANGED': next = {...state, reviewPreference: event.value}; break;
    case 'DOCUMENT_REQUESTED': next = {...state, requestedDocument: event.path}; break;
    case 'DOCUMENT_DISPLAYED': next = event.discussions
      ? transition({...state, displayedDocument:event.path, requestedDocument:event.path}, {type:'THREADS_RECEIVED', ...event.discussions, activation:event.activation}).state
      : {...state, displayedDocument: event.path, requestedDocument: event.path, threads: [], focusedThread: event.focusedThread ?? null, requestedThread: null, spotlight: null, spotlightIds: []}; break;
    case 'DOCUMENT_CANCELLED':
    case 'DOCUMENT_FAILED': next = {...state, requestedDocument: state.displayedDocument}; break;
    default: throw new Error('Unknown application transition: ' + event.type);
  }
  return {state: next, effects};
}

export function createAppStore(preferences) {
  let state = initialAppState(preferences);
  const listeners = new Set();
  return {
    get state() { return state; },
    dispatch(event) {
      const previous = state, result = transition(state, event);
      state = result.state;
      for (const listener of listeners) listener(state, previous, event);
      return result.effects;
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }
  };
}
