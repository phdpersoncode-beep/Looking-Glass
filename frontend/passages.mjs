import {sourceCoordinates} from './coordinates.mjs';

export function passageGroup(threads, passage) {
  if (!passage) return [];
  const seeds = passage.seeds.map(seed => threads.find(t => t.id === seed.id) || seed);
  const source = seeds.filter(t => t.anchor_kind === 'source' && t.anchor_status === 'attached');
  const from = Math.max(...source.map(t => t.start)), to = Math.min(...source.map(t => t.end));
  return threads.filter(t => t.path === passage.path && (
    seeds.some(seed => seed.id === t.id) ||
    t.anchor_kind === 'source' && t.anchor_status === 'attached' && source.length > 0 && from < to && t.start < to && t.end > from ||
    t.anchor_kind === 'rendered' && seeds.some(seed => seed.anchor_kind === 'rendered' && JSON.stringify(seed.render_anchor) === JSON.stringify(t.render_anchor))
  )).map(t => t.id);
}

export function resolveSourcePassage(thread, {path, content, version = null, dirty = false, localRanges = [], coordinates = null}) {
  const documentRef = {path, version};
  const result = (status, range, reason) => ({status, documentRef, range, reason});
  if (thread.path !== path || thread.anchor_kind !== 'source') return result('unavailable', null, 'different_document_or_surface');
  if (thread.anchor_status !== 'attached') return result('needs_reattachment', null, 'detached_anchor');
  if (dirty) {
    const range = localRanges.find(range => range.id === thread.id);
    return range && range.from < range.to && range.to <= content.replace(/\r\n/g, '\n').length
      ? result('attached', {from: range.from, to: range.to, coordinates: 'editor-utf16'}, 'mapped_local_edits')
      : result('unavailable', null, 'local_anchor_unavailable');
  }
  coordinates ??= sourceCoordinates(content, [thread.start, thread.end]);
  if (!Number.isInteger(thread.start) || !Number.isInteger(thread.end) || thread.start < 0 || thread.start >= thread.end || thread.end > coordinates.length)
    return result('needs_reattachment', null, 'invalid_source_range');
  if (typeof thread.quote === 'string' && content.slice(coordinates.raw.get(thread.start),coordinates.raw.get(thread.end)) !== thread.quote)
    return result('unavailable', null, 'source_revision_changed');
  return result('attached', {from: coordinates.editor.get(thread.start), to: coordinates.editor.get(thread.end), coordinates: 'editor-utf16'}, 'saved_source_anchor');
}

export function sourceSpans(threads, content, path, version) {
  const local=threads.filter(thread=>thread.path===path&&thread.anchor_kind==='source'&&thread.anchor_status==='attached');
  const coordinates=sourceCoordinates(content,local.flatMap(thread=>[thread.start,thread.end]));
  return local.flatMap(thread => {
    const result = resolveSourcePassage(thread, {path, content, version,coordinates});
    return result.status === 'attached' && result.range.from < result.range.to ? [{id: thread.id, resolved: thread.resolved, from: result.range.from, to: result.range.to}] : [];
  });
}

export function resolveRenderedPassage(text, anchor, documentRef = null) {
  const result = (status, range, reason) => ({status, documentRef, range, reason});
  if (!anchor?.quote) return result('unavailable', null, 'missing_quote');
  const candidates = []; let at = 0;
  while ((at = text.indexOf(anchor.quote, at)) >= 0) {candidates.push(at); at++;}
  const supported = candidates.filter(at =>
    (!anchor.prefix || text.slice(Math.max(0, at - anchor.prefix.length), at) === anchor.prefix) &&
    (!anchor.suffix || text.slice(at + anchor.quote.length, at + anchor.quote.length + anchor.suffix.length) === anchor.suffix));
  const from = supported.length === 1 ? supported[0] : candidates.length === 1 ? candidates[0] : null;
  return from === null ? result('needs_reattachment', null, candidates.length ? 'ambiguous_quote' : 'missing_passage')
    : result('attached', {from, to: from + anchor.quote.length, coordinates: 'rendered-utf16'}, 'unique_quote_or_context');
}
