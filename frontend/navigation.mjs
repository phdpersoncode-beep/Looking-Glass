// Serial transitions finish writes; newer reads supersede older presentation.
// Every caller receives completion for its own request, including queued calls.
export function createNavigationController({load, onRequest = () => {}, onFailure = () => {}, onInvalidate = () => {}}) {
  let serial = 0, tail = Promise.resolve(), busy = 0;
  function open(path, context = null) {
    const id = ++serial, current = () => id === serial;
    onRequest({path, id, context}); busy++;
    const result = tail.catch(() => {}).then(async () => {
      if (!current()) return {status: 'superseded', path, id};
      try {
        await load(path, {id, current, context});
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

// Repeated keys choose a destination immediately, but paint at most once per
// frame. A newer intention supersedes an in-flight reveal rather than queuing it.
export function createFrameNavigator({activate, onRequest = () => {}, schedule, cancel}) {
  let serial = 0, frame = null, pending = null;
  function invalidate() {
    serial++;
    if (frame !== null) cancel(frame);
    frame = null;
    pending?.resolve({status: 'superseded'}); pending = null;
  }
  function request(target) {
    const id = ++serial;
    pending?.resolve({status: 'superseded'});
    onRequest(target);
    const result = new Promise((resolve, reject) => {pending = {id, target, resolve, reject};});
    if (frame === null) frame = schedule(() => {
      frame = null;
      const task = pending; pending = null;
      const current = () => task.id === serial;
      Promise.resolve().then(() => current() && activate(task.target, {current})).then(
        () => task.resolve({status: current() ? 'ready' : 'superseded'}), task.reject);
    });
    return result;
  }
  return {request, invalidate};
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

export function threadDestination(thread, session, {historyPath}) {
  if (['commit', 'branch'].includes(thread.anchor_kind)) return {path: historyPath, surface: 'history'};
  if (thread.anchor_kind === 'review_removed') return session?.path === thread.path && session.workMode === 'review'
    ? {path: thread.path, surface: 'removed'} : {path: thread.path, surface: 'unavailable'};
  if (thread.anchor_status === 'needs_reattachment' || session?.conflict?.deleted)
    return {path: thread.path, surface: 'unavailable'};
  return {path: thread.path, surface: thread.anchor_kind === 'rendered' ? 'rendered' : 'source'};
}
