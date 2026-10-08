// Move the actual card, not a copy: reply drafts, attachments, and focus stay
// with it. A placeholder preserves list order and the sidebar scroll position.
export function createThreadFloat(sidebar) {
  const overlay=document.createElement('div');overlay.className='floating-discussion';overlay.hidden=true;
  sidebar.append(overlay);
  const scroller=sidebar.querySelector('.discussion-content');
  let card=null,placeholder=null,anchorY=null;
  function layout() {
    if(!card)return;
    const bounds=sidebar.getBoundingClientRect(),heading=sidebar.querySelector('.panel-heading').getBoundingClientRect();
    const min=heading.bottom-bounds.top+8,available=bounds.height-min-12;
    // Keep at least a useful portion of a long discussion visible below it.
    const top=Math.max(min,Math.min((anchorY??heading.bottom+8)-bounds.top,bounds.height-Math.min(240,available)-12));
    overlay.style.top=top+'px';overlay.style.maxHeight=Math.max(0,bounds.height-top-12)+'px';
  }
  function restore() {
    if(!card)return;
    const top=scroller.scrollTop;
    if(placeholder?.isConnected)placeholder.replaceWith(card);else card.remove();
    card.classList.remove('floating-thread');overlay.hidden=true;
    card=null;placeholder=null;anchorY=null;scroller.scrollTop=top;
  }
  function show(next,y) {
    if(!next||next.hidden||next.classList.contains('collapsed'))return;
    if(card===next){if(Number.isFinite(y))anchorY=y;layout();return;}
    restore();const top=scroller.scrollTop;
    placeholder=document.createElement('div');placeholder.className='thread-placeholder';placeholder.setAttribute('aria-hidden','true');
    placeholder.style.height=next.getBoundingClientRect().height+'px';placeholder.style.marginBottom=getComputedStyle(next).marginBottom;
    next.replaceWith(placeholder);card=next;anchorY=Number.isFinite(y)?y:null;
    card.classList.add('floating-thread');overlay.replaceChildren(card);overlay.hidden=false;overlay.scrollTop=0;layout();scroller.scrollTop=top;
  }
  function reveal(next) {
    restore();if(!next||next.hidden)return;
    const bounds=scroller.getBoundingClientRect(),rect=next.getBoundingClientRect();
    // Scroll only the discussion list, never its ancestors or the document.
    if(rect.top<bounds.top||rect.height>scroller.clientHeight)scroller.scrollTop+=rect.top-bounds.top;
    else if(rect.bottom>bounds.bottom)scroller.scrollTop+=rect.bottom-bounds.bottom;
  }
  new ResizeObserver(layout).observe(sidebar);
  return {show,reveal,restore,layout,get id(){return card?Number(card.dataset.thread):null;},get y(){return anchorY;},contains:node=>overlay.contains(node)};
}
