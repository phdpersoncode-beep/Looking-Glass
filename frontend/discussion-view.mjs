// Keyed DOM projection. Reply forms and unchanged messages keep their nodes,
// native selections and listeners; no whole-list replacement or restoration.
export function createDiscussionView(host, {renderBody, composers}) {
  const cards = new Map(); let lastHTML = null;
  const key = node => node.nodeType !== 1 ? null : node.dataset.messageId ? 'message:' + node.dataset.messageId
    : node.dataset.attachment ? 'attachment:' + node.dataset.attachment
    : node.matches('.reply-form') ? 'composer'
    : node.dataset.action ? node.tagName + ':' + node.dataset.action + ':' + (node.dataset.message || '') : null;
  const compatible = (a, b) => a.nodeType === b.nodeType && (a.nodeType !== 1 || a.tagName === b.tagName);
  function decorate(node) {
    for (const body of node.querySelectorAll('.comment-markdown')) {
      body._discussionSource = body.textContent; renderBody(body, body._discussionSource);
    }
    for (const form of node.querySelectorAll('.reply-form')) composers.render(form);
  }
  function patch(current, next) {
    if (!compatible(current, next)) {const replacement = next.cloneNode(true); current.replaceWith(replacement); if (replacement.nodeType === 1) decorate(replacement); return replacement;}
    if (current.nodeType === 3) {if (current.data !== next.data) current.data = next.data; return current;}
    if (current.nodeType !== 1) return current;
    if (current.matches('.reply-form')) return current;
    if (current.matches('.comment-markdown')) {
      if (current._discussionSource !== next.textContent) {current._discussionSource = next.textContent; renderBody(current, next.textContent);}
      return current;
    }
    const keep = current.matches('.thread') ? ['active', 'collapsed'].filter(name => current.classList.contains(name)) : [];
    for (const attribute of [...current.attributes]) if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
    for (const attribute of next.attributes) if (current.getAttribute(attribute.name) !== attribute.value) current.setAttribute(attribute.name, attribute.value);
    for (const name of keep) current.classList.add(name);
    const old = [...current.childNodes], keyed = new Map(old.filter(node => key(node)).map(node => [key(node), node])), used = new Set();
    let cursor = current.firstChild;
    for (const incoming of next.childNodes) {
      const id = key(incoming);
      let node = id ? keyed.get(id) : cursor && !key(cursor) && compatible(cursor, incoming) ? cursor : null;
      if (!node || used.has(node)) {node = incoming.cloneNode(true); current.insertBefore(node, cursor); if (node.nodeType === 1) decorate(node);}
      else {if (node !== cursor) current.insertBefore(node, cursor); node = patch(node, incoming);}
      used.add(node); cursor = node.nextSibling;
    }
    for (const node of old) if (!used.has(node)) node.remove();
    return current;
  }
  function render(html) {
    if (html === lastHTML) return;
    lastHTML = html;
    const template = document.createElement('template'); template.innerHTML = html;
    const incoming = [...template.content.children].filter(node=>node.matches('.thread'));
    const visible = new Set(); let cursor = host.firstElementChild;
    for (const next of incoming) {
      const id = Number(next.dataset.thread), signature = next.outerHTML; visible.add(id);
      let record = cards.get(id);
      if (!record) {record = {node: next, signature}; cards.set(id, record); decorate(next);}
      else if (record.signature !== signature) {patch(record.node, next); record.signature = signature;}
      if (record.node !== cursor) host.insertBefore(record.node, cursor); else cursor = cursor.nextElementSibling;
    }
    for (const child of [...host.children]) if (!visible.has(Number(child.dataset.thread))) child.remove();
    if (!incoming.length) {const empty = template.content.querySelector('.empty-discussions'); if (empty) host.append(empty);}
  }
  function prune(ids) {for (const [id, record] of cards) if (!ids.has(id)) {record.node.remove(); cards.delete(id);}}
  return {render, prune, reset() {lastHTML = null;}};
}
