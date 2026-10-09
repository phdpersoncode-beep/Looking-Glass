// Filter the existing list in place. Cards never move or acquire copies, so
// drafts and attachments belong to the same discussion in either view.
export function createThreadSpotlight(sidebar,onChange) {
  const scroller=sidebar.querySelector('.discussion-content');
  const heading=sidebar.querySelector('#passage-spotlight');
  const label=heading.querySelector('[role=status]');
  let ids=null,listScroll=0;
  function update(next) {
    ids=next?.length?new Set(next):null;
    sidebar.classList.toggle('passage-focused',!!ids);heading.hidden=!ids;
    if(ids)label.textContent=`This passage · ${ids.size} ${ids.size===1?'thread':'threads'}`;
    onChange();
  }
  function restore() {
    if(!ids)return;
    const focus=heading.contains(document.activeElement);
    update(null);scroller.scrollTop=listScroll;
    // The return control disappears; leave keyboard focus on a stable control.
    if(focus)sidebar.querySelector('#collapse-threads').focus({preventScroll:true});
  }
  function show(next) {
    if(!next.length)return;
    if(!ids)listScroll=scroller.scrollTop;
    const changed=!ids||ids.size!==next.length||next.some(id=>!ids.has(id));
    update(next);if(changed)scroller.scrollTop=0;
  }
  function sync(next) {if(!ids)return;if(next.length)update(next);else restore();}
  function reveal(card) {
    if(!card||card.hidden)return;
    const bounds=scroller.getBoundingClientRect(),rect=card.getBoundingClientRect();
    // Navigation may reveal a card, but never scroll the document's ancestors.
    if(rect.top<bounds.top||rect.height>scroller.clientHeight)scroller.scrollTop+=rect.top-bounds.top;
    else if(rect.bottom>bounds.bottom)scroller.scrollTop+=rect.bottom-bounds.bottom;
  }
  return {show,sync,restore,reveal,get active(){return !!ids;},get ids(){return ids?[...ids]:[];},includes:id=>!!ids?.has(id)};
}
