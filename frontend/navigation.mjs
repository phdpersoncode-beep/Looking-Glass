// Serial transitions finish writes; newer reads supersede older presentation.
// Every caller receives completion for its own request, including queued calls.
export function createNavigationController({load, onRequest = () => {}, onFailure = () => {}, onInvalidate = () => {}}) {
  let serial = 0, tail = Promise.resolve(), busy = 0;
  function open(path) {
    const id = ++serial, current = () => id === serial;
    onRequest({path, id}); busy++;
    const result = tail.catch(() => {}).then(async () => {
      if (!current()) return {status: 'superseded', path, id};
      try {
        await load(path, {id, current});
        return {status: current() ? 'ready' : 'superseded', path, id};
      } catch (error) {
        if (current()) onFailure({path, id, error});
        throw error;
      } finally { /* Pending writes are never aborted by this controller. */ }
    }).finally(() => {busy--;});
    tail = result;
    return result;
  }
  return {open, get busy() {return busy > 0;}, get requestId() {return serial;},
    isCurrent: request => request.id === serial, invalidate() {serial++; onInvalidate();}};
}

// A consistent request identity for discussion/baseline/index completions.
export function createRequestGate() {
  let serial = 0;
  return {
    begin(context) {return {id: ++serial, context};},
    accepts(request, context) {return request.id === serial && request.context === context;},
    invalidate() {serial++;}
  };
}

export function threadDestination(thread, session, {historyPath, originalPath}) {
  if (['commit', 'branch'].includes(thread.anchor_kind)) return {path: historyPath, surface: 'history'};
  if (thread.anchor_kind === 'review_removed') return session?.path === thread.path && session.workMode === 'review'
    ? {path: thread.path, surface: 'removed'} : {path: originalPath(thread.id), surface: 'original'};
  if (thread.anchor_kind !== 'rendered' && thread.anchor_status === 'needs_reattachment' || session?.conflict?.deleted)
    return {path: originalPath(thread.id), surface: 'original'};
  return {path: thread.path, surface: thread.anchor_kind === 'rendered' ? 'rendered' : 'source'};
}
