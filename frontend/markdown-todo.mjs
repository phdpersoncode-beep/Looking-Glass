const todoPattern = /(?<![\p{L}\p{M}\p{N}_])TODO(?![\p{L}\p{M}\p{N}_])/gu;

export function todoRanges(text) {
  return Array.from(text.matchAll(todoPattern), match => ({from: match.index, to: match.index + match[0].length}));
}

// Append successive slices of the same text while keeping TODO styling inside
// existing passage and review marks, even when a slice ends mid-word.
export function todoTextAppender(text, ranges) {
  let next = 0;
  return (host, from = 0, to = text.length) => {
    for (; next < ranges.length && ranges[next].from < to; next++) {
      const range = ranges[next];
      const start = Math.max(from, range.from);
      const end = Math.min(to, range.to);
      if (from < start) host.append(text.slice(from, start));
      const todo = document.createElement('span');
      todo.className = 'md-todo';
      todo.textContent = text.slice(start, end);
      host.append(todo);
      from = end;
      if (end < range.to) break;
    }
    if (from < to) host.append(text.slice(from, to));
  };
}

export function styleMarkdownTodos(host) {
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
  const pending = [];
  for (let text; (text = walker.nextNode());) {
    if (!text.data.includes('TODO') || text.parentElement.closest('pre,.md-math,style,textarea')) continue;
    const ranges = todoRanges(text.data);
    if (ranges.length) pending.push({text, ranges});
  }
  for (const {text, ranges} of pending) {
    const fragment = document.createDocumentFragment();
    todoTextAppender(text.data, ranges)(fragment);
    text.replaceWith(fragment);
  }
}
