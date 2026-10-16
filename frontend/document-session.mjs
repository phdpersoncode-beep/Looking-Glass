export function createDocumentSession(path, file, mode) {
  return {path, ...file, diskContent: file.content, dirty: false, conflict: null,
    pinned: false, state: null, mode, modes: new Map(), generation: 0};
}

export function retainModeState(session) {
  if (!session.workMode) return;
  session.modes ??= new Map();
  session.modes.set(session.workMode, {state: session.state, content: session.content,
    version: session.version, reviewId: session.review?.id, reviewField: session.reviewField});
}

export function matchingModeState(session, mode, content, reviewId) {
  const held = session.modes?.get(mode);
  return held?.content === content && (mode !== 'review' || held.reviewId === reviewId) ? held : null;
}

// Explicit resource lifetime for temporary original-context visits. The adapter
// supplies browser-specific operations; the lifecycle itself contains no DOM.
export function createSurfaceSession(adapter) {
  let status = 'mounted';
  return {
    get status() {return status;},
    async suspend() {
      if (status !== 'mounted') throw new Error('Only a mounted surface can suspend.');
      await adapter.suspend?.(); status = 'suspended';
    },
    resume() {
      if (status !== 'suspended') throw new Error('Only a suspended surface can resume.');
      adapter.resume?.(); status = 'mounted';
    },
    dispose() {
      if (status === 'disposed') return;
      adapter.dispose?.(); status = 'disposed';
    }
  };
}
