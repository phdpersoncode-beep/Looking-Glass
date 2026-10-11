import {apply,accepted,pointLength} from './review-model.mjs';
import {retainModeState,matchingModeState} from './document-session.mjs';

export function appendOperations(pending, operations, protectedCount = 0) {
  for (const operation of operations) {
    const op = {...operation}, last = pending.length > protectedCount ? pending.at(-1) : null;
    if (last && last.start === last.end && op.start === op.end && op.start === last.start + pointLength(last.insert)) last.insert += op.insert;
    else if (last && !last.insert && !op.insert && op.end === last.start) last.start = op.start;
    else if (last && !last.insert && !op.insert && op.start === last.start) last.end += op.end - op.start;
    else pending.push(op);
  }
}

// The controller owns all draft revision/operation/error transitions. The
// document session remains the owner of editor content/state; ports project
// accepted controller snapshots into the currently mounted surface.
export function createReviewSync(session, ports) {
  let status = 'clean', timer = null, flight = null, protectedCount = 0, epoch = 0;
  session.pendingOps ??= [];
  const changed = () => ports.changed?.();
  function adopt(draft) {
    epoch++; status = 'clean'; session.review = draft; session.reviewSegments = draft?.segments;
    session.pendingOps = []; session.reviewError = null;
    if (draft) {session.version = draft.version; session.diskContent = draft.content; session.content = draft.content; session.dirty = false;}
    changed();
  }
  function enqueue(operations, segments) {
    epoch++; appendOperations(session.pendingOps, operations, protectedCount);
    session.reviewSegments = segments || apply(session.reviewSegments, operations, ports.metadata(), session.review.base);
    if (status !== 'saving' && status !== 'conflicted') status = 'pending';
  }
  function schedule() {
    clearTimeout(timer); timer = setTimeout(() => flush().catch(error => ports.error?.(error)), ports.delay ?? 450);
  }
  async function flush() {
    clearTimeout(timer);
    if (!session.review || session.workMode !== 'review') return;
    if (flight) {await flight; return flush();}
    if (status === 'conflicted') throw session.reviewError;
    if (!session.pendingOps.length) return;
    // Freeze the sent prefix: typing during a save must never mutate its batch.
    const operations = session.pendingOps.slice(0, 1000).map(op => ({...op}));
    protectedCount = operations.length; const draft = session.review, metadata = ports.metadata();
    status = 'saving'; changed();
    flight = (async () => {
      try {
        const saved = await ports.api('reviews/' + draft.id, 'PATCH', {version: draft.version, operations, author: metadata.author, role: 'human', minimal: true});
        const segments = saved.segments || apply(draft.segments, operations, saved.edit || metadata, draft.base);
        const content = saved.content ?? accepted(segments);
        session.pendingOps.splice(0, operations.length);
        session.review = {...draft, ...saved, segments, content}; session.version = saved.version; session.diskContent = content;
        session.reviewSegments = apply(segments, session.pendingOps, ports.metadata(), draft.base);
        session.dirty = session.pendingOps.length > 0;
        status = session.dirty ? 'pending' : 'clean';
        await ports.saved?.(session.reviewSegments);
      } catch (error) {status = 'conflicted'; session.reviewError = error; throw error;}
      finally {protectedCount = 0; flight = null; changed();}
    })();
    await flight;
    if (session.pendingOps.length) return flush();
  }
  async function poll() {
    if (status !== 'clean' || !session.review || session.workMode !== 'review') return;
    const draft = session.review, requestedEpoch = epoch;
    const incoming = await ports.api('reviews/' + draft.id + '?' + new URLSearchParams({version: draft.version}));
    if (!incoming || epoch !== requestedEpoch || session.review !== draft || status !== 'clean' || session.workMode !== 'review') return;
    if (incoming.status !== 'pending') {await ports.concluded?.(); return;}
    const before = session.content;
    adopt(incoming);
    await ports.remote?.(incoming, before);
  }
  function approvalTarget() {return Object.freeze({entry: session, id: session.review.id, version: session.review.version, epoch});}
  function assertApproval(target) {
    if (!target || target.entry !== session || session.workMode !== 'review' || session.review?.id !== target.id || session.review.version !== target.version || target.epoch !== epoch || session.pendingOps.length || status !== 'clean')
      throw new Error('The review changed while confirmation was open. Inspect the latest draft and approve again.');
  }
  async function approve(target) {
    assertApproval(target); status = 'approving'; changed();
    try {return await ports.api('reviews/' + target.id + '/approve', 'POST', {version: target.version});}
    finally {status = 'clean'; changed();}
  }
  return {get status() {return status;}, get saving() {return flight;}, adopt, enqueue, schedule, flush, poll,
    approvalTarget, assertApproval, approve,
    retry() {session.reviewError = null; status = session.pendingOps.length ? 'pending' : 'clean'; return flush();},
    dispose() {clearTimeout(timer); epoch++;}};
}

// Preparation has no visible mutation. A group of modes commits only after all
// reads/saves succeed and every captured session still matches its revision.
export async function prepareWorkMode(session, desired, ports) {
  if (!ports.supports(session) || session.workMode === desired) return {validate() {}, commit() {}};
  if (!session.workMode && desired === 'edit') return {validate() {}, commit() {session.workMode = 'edit';}};
  if (desired === 'review' && session.dirty) throw new Error('Save or undo edit-mode changes before starting review.');
  if (session.workMode === 'review') await ports.sync(session).flush();
  const before = {content: session.content, version: session.version, mode: session.workMode};
  const file = desired === 'review'
    ? await ports.api('reviews', 'POST', {path: session.path, version: session.version})
    : await ports.api('file?' + new URLSearchParams({path: session.path}));
  function validate() {
    if (session.content !== before.content || session.version !== before.version || session.workMode !== before.mode || session.pendingOps?.length)
      throw new Error('The document changed while switching modes. Try switching again.');
  }
  return {validate, commit() {
    validate(); retainModeState(session);
    const held = matchingModeState(session, desired, file.content, desired === 'review' ? file.id : undefined);
    session.generation = (session.generation || 0) + 1;
    session.workMode = desired;
    if (desired === 'review') ports.sync(session).adopt(file);
    else {ports.sync(session).adopt(null); session.content = file.content; session.diskContent = file.content; session.version = file.version; session.dirty = false;}
    session.state = held?.state || null; session.reviewField = held?.reviewField || null; session.conflict = null; ports.resumed?.(session);
  }};
}
