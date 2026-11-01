// Lezer recognises shortcut references before it knows whether a definition
// exists. Keep undefined [labels] (including intervals) literal in live mode.
export function markdownLinks(tree, doc) {
  const normalize = text => text.slice(1, -1).trim().replace(/\s+/g, ' ').toLowerCase();
  const definitions = new Set(), links = [];
  tree.iterate({enter(node) {
    if (node.name === 'LinkReference') {
      const label = node.node.getChild('LinkLabel');
      if (label) definitions.add(normalize(doc.sliceString(label.from, label.to)));
    }
    if (node.name === 'Link') links.push(node.node);
  }});
  return new Set(links.filter(node => {
    if (node.getChild('URL')) return true;
    const label = node.getChild('LinkLabel');
    const text = label && doc.sliceString(label.from, label.to);
    const marks = node.getChildren('LinkMark');
    const fallback = marks.length >= 2 ? doc.sliceString(marks[0].from, marks[1].to) : '';
    return definitions.has(normalize(text && text !== '[]' ? text : fallback));
  }).map(node => node.from));
}
