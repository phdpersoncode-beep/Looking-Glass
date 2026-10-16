// A visibility change is not deletion. Only a newer authoritative index for
// the same visibility universe may retire IDs and their cached forms/drafts.
export function createDiscussionRetention() {
  const snapshots = new Map();
  return {accept(scope, ids) {
    const incoming = new Set(ids), previous = snapshots.get(scope) || new Set();
    const deleted = [...previous].filter(id => !incoming.has(id));
    for (const snapshot of snapshots.values()) for (const id of deleted) snapshot.delete(id);
    snapshots.set(scope, incoming);
    return new Set([...snapshots.values()].flatMap(snapshot => [...snapshot]));
  }};
}
