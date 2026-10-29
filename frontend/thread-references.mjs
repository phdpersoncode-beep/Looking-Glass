// Decorate only sanitized discussion text. Authored links and code remain
// untouched, and generated controls never come from authored HTML attributes.
export function linkThreadReferences(host) {
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, {
    acceptNode: node => node.parentElement.closest('a,code,pre,button') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
  });
  const nodes = []; let node;
  while ((node = walker.nextNode())) nodes.push(node);
  for (const node of nodes) {
    const matches = [...node.data.matchAll(/(?<![\p{L}\p{N}_/#])#([1-9]\d*)(?![\p{L}\p{N}_])/gu)]
      .filter(match => Number.isSafeInteger(Number(match[1])));
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment(); let at = 0;
    for (const match of matches) {
      fragment.append(node.data.slice(at, match.index));
      const link = document.createElement('a');
      link.href = '#thread-' + match[1]; link.dataset.threadReference = match[1];
      link.textContent = match[0]; link.title = 'Open thread ' + match[0] + ' and its file';
      fragment.append(link); at = match.index + match[0].length;
    }
    fragment.append(node.data.slice(at)); node.replaceWith(fragment);
  }
}
