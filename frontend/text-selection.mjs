import {layer,RectangleMarker} from '@codemirror/view';

// Work with text-node ranges so block boxes, line endings, and prose margins
// never become part of the painted selection. The actual selection is intact.
export function selectedTextRanges(range,host) {
  const result=[],walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT);
  let node;
  while((node=walker.nextNode())) {
    if(!node.textContent.trim()||node.parentElement.closest('button,input,textarea,select,.markdown-source-controls')||!range.intersectsNode(node))continue;
    const part=document.createRange();part.selectNodeContents(node);
    if(range.startContainer===node)part.setStart(node,range.startOffset);
    if(range.endContainer===node)part.setEnd(node,range.endOffset);
    if(!part.collapsed)result.push(part);
  }
  return result;
}

export const textSelection=layer({
  above:false,class:'cm-text-selectionLayer',
  update:u=>u.selectionSet||u.docChanged||u.geometryChanged||u.viewportChanged,
  markers(view) {
    const markers=[],rect=view.scrollDOM.getBoundingClientRect();
    const left=rect.left-view.scrollDOM.scrollLeft,top=rect.top-view.scrollDOM.scrollTop;
    for(const selection of view.state.selection.ranges) {
      if(selection.empty)continue;
      for(const visible of view.visibleRanges) {
        const from=Math.max(selection.from,visible.from),to=Math.min(selection.to,visible.to);
        if(from>=to)continue;
        const start=view.domAtPos(from),end=view.domAtPos(to),range=document.createRange();
        range.setStart(start.node,start.offset);range.setEnd(end.node,end.offset);
        for(const part of selectedTextRanges(range,view.contentDOM))for(const piece of part.getClientRects()) {
          if(piece.width>0&&piece.height>0)markers.push(new RectangleMarker('cm-text-selection',
            (piece.left-left)/view.scaleX,(piece.top-top)/view.scaleY,piece.width/view.scaleX,piece.height/view.scaleY));
        }
      }
    }
    return markers;
  }
});

export function updateNativeTextSelection() {
  if(!globalThis.CSS?.highlights||!globalThis.Highlight)return;
  CSS.highlights.delete('looking-glass-text-selection');
  const selection=window.getSelection();if(!selection?.rangeCount||selection.isCollapsed)return;
  const range=selection.getRangeAt(0);
  const host=document.querySelector('#surface .markdown-preview')||selection.anchorNode?.parentElement?.closest('#surface .md-table');
  if(!host||!host.contains(range.startContainer)||!host.contains(range.endContainer))return;
  CSS.highlights.set('looking-glass-text-selection',new Highlight(...selectedTextRanges(range,host)));
}
