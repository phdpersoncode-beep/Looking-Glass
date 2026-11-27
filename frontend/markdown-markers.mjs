const markerPattern = /(?<![\p{L}\p{M}\p{N}_])(?:TODO|P[0-3])(?![\p{L}\p{M}\p{N}_])/gu;

export function markerRanges(text) {
  return Array.from(text.matchAll(markerPattern), match => ({from: match.index, to: match.index + match[0].length, kind: match[0]}));
}

// Append successive slices of the same text while keeping marker styling inside
// existing passage and review marks, even when a slice ends mid-word.
export function markerTextAppender(text, ranges) {
  let next = 0;
  return (host, from = 0, to = text.length) => {
    for (; next < ranges.length && ranges[next].from < to; next++) {
      const range = ranges[next];
      const start = Math.max(from, range.from);
      const end = Math.min(to, range.to);
      if (from < start) host.append(text.slice(from, start));
      const marker = document.createElement('span');
      marker.className = 'md-marker';
      marker.dataset.kind = range.kind;
      marker.textContent = text.slice(start, end);
      host.append(marker);
      from = end;
      if (end < range.to) break;
    }
    if (from < to) host.append(text.slice(from, to));
  };
}

export function styleMarkdownMarkers(host) {
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  const pending = [];
  for (let text; (text = walker.nextNode());) {
    if (text.parentElement.closest('pre,.md-math,style,textarea')) continue;
    const ranges = markerRanges(text.data);
    if (ranges.length) pending.push({text, ranges});
  }
  for (const {text, ranges} of pending) {
    const fragment = document.createDocumentFragment();
    markerTextAppender(text.data, ranges)(fragment);
    text.replaceWith(fragment);
  }
}
