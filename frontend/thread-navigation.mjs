import {threadDestination,createRequestGate} from './navigation.mjs';

// This controller chooses destinations. Surfaces only reveal resolved targets.
export function createThreadNavigator(ports) {
  const requests = createRequestGate();
  async function activate(id, target = null, spotlight = false, focusEditor = true, {openUnavailable = false} = {}) {
    let thread = target || ports.find(id);
    if (!thread) return;
    const key = String(id), request = requests.begin(key), current = () => requests.accepts(request, key);
    const show = (reveal = true) => ports.focus(id, spotlight, thread, reveal);
    const open = path => ports.open(path, {threadId: id, spotlight, current});
    const destination = threadDestination(thread, ports.session(thread.path), ports.paths);
    if (destination.surface === 'history') {
      if (!thread.git_target) thread = await ports.read(id);
      if (!current()) return;
      const opened = await open(destination.path);
      if (opened.status !== 'ready' || !current()) return;
      await ports.selectGit(thread.git_target);
      if (current()) show();
      return;
    }
    if (destination.surface === 'removed' && ports.revealRemoved(thread)) {show(); return;}
    if (['unavailable', 'removed'].includes(destination.surface)) {
      if (openUnavailable && thread.path !== ports.displayed()) {
        const opened = await open(thread.path);
        if (opened.status !== 'ready' || !current()) return;
      }
      show(false); return;
    }
    if (thread.path !== ports.displayed()) {
      try {
        const opened = await open(thread.path);
        if (opened.status !== 'ready' || !current() || thread.path !== ports.displayed()) return;
      } catch (error) {
        if (!current()) return;
        if (error.status !== 404) throw error;
        show(false);
        return;
      }
    }
    thread = ports.find(id) || thread;
    if (!current()) return;
    show();
    if (thread.anchor_kind === 'pdf') {await ports.revealPDF(thread); return;}
    if (thread.anchor_kind === 'rendered' || ports.session(thread.path)?.mode === 'rendered' && thread.anchor_kind === 'source') {
      await ports.revealRendered(thread, current, focusEditor); return;
    }
    ports.revealSource(thread, focusEditor);
  }
  return {activate, invalidate: () => requests.invalidate()};
}
