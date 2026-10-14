// Spotlight IDs belong to application state. This adapter owns only geometry.
export function createThreadSpotlight(sidebar, getState) {
  const scroller = sidebar.querySelector('.discussion-content');
  const heading = sidebar.querySelector('#passage-spotlight');
  const label = heading.querySelector('[role=status]');
  heading.title = '← → Previous/next thread · ↑ Search · ↓ Reply';
  let showing = false, signature = '', listScroll = 0;
  function capture() {
    if (getState().spotlightIds.length && !showing) listScroll = scroller.scrollTop;
  }
  function render() {
    const ids = getState().spotlightIds, active = ids.length > 0;
    const next = ids.join(',');
    const focus = heading.contains(document.activeElement);
    sidebar.classList.toggle('passage-focused', active); heading.hidden = !active;
    if (active) label.textContent = `This passage · ${ids.length} ${ids.length === 1 ? 'thread' : 'threads'}`;
    if (active && next !== signature) scroller.scrollTop = 0;
    if (!active && showing) {
      scroller.scrollTop = listScroll;
      if (focus) sidebar.querySelector('#collapse-threads').focus({preventScroll: true});
    }
    showing = active; signature = next;
  }
  function reveal(card) {
    if (!card || card.hidden) return;
    const bounds = scroller.getBoundingClientRect(), rect = card.getBoundingClientRect();
    if (rect.top < bounds.top || rect.height > scroller.clientHeight) scroller.scrollTop += rect.top - bounds.top;
    else if (rect.bottom > bounds.bottom) scroller.scrollTop += rect.bottom - bounds.bottom;
  }
  return {capture, render, reveal, get active() { return getState().spotlightIds.length > 0; },
    get ids() { return getState().spotlightIds; }, includes: id => getState().spotlightIds.includes(id)};
}
