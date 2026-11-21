const todoPattern = /(?<![\p{L}\p{M}\p{N}_])TODO(?![\p{L}\p{M}\p{N}_])/gu;

export function todoRanges(text) {
  return Array.from(text.matchAll(todoPattern), match => ({from: match.index, to: match.index + match[0].length}));
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
    let at = 0;
    for (const {from, to} of ranges) {
      fragment.append(text.data.slice(at, from));
      const todo = document.createElement('span');
      todo.className = 'md-todo';
      todo.textContent = text.data.slice(from, to);
      fragment.append(todo);
      at = to;
    }
    fragment.append(text.data.slice(at));
    text.replaceWith(fragment);
  }
}
