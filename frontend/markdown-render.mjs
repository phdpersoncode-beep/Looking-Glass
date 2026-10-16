import {label as reviewLabel} from './review-model.mjs';
import {marked} from 'marked';
import {mappedMarkdownHTML,visibleMap} from './markdown-source.mjs';
export {tokenPositions,mappedMarkdownHTML} from './markdown-source.mjs';
import DOMPurify from 'dompurify';

function wrapMarkdownTables(host) {
  for(const table of host.querySelectorAll('table')){
    const scroller=document.createElement('div');scroller.className='markdown-table-scroll';
    // Native table drags must focus this region rather than the surrounding
    // CodeMirror editor, whose source caret cannot represent a cell selection.
    scroller.setAttribute('role','region');scroller.setAttribute('aria-label','Markdown table');scroller.tabIndex=0;
    table.replaceWith(scroller);scroller.append(table);
  }
}

export function renderMarkdown(host,source,decorate=()=>{}) {
  // Discussion HTML is content, never application controls. Keep saved Markdown
  // unchanged and prevent authored attributes from impersonating sidebar actions.
  host.innerHTML=DOMPurify.sanitize(marked.parse(source),{
    ALLOW_DATA_ATTR:false,FORBID_ATTR:['id','name','style'],
    FORBID_TAGS:['button','form','select','textarea','iframe','object','embed','style']
  });
  for(const element of host.querySelectorAll('[class]')) {
    const language=element.tagName==='CODE'&&[...element.classList].find(name=>/^language-[\w-]+$/.test(name));
    element.removeAttribute('class');if(language)element.className=language;
  }
  for(const link of host.querySelectorAll('a')){link.target='_blank';link.rel='noopener noreferrer';}
  decorate(host);wrapMarkdownTables(host);
}

export function mountMappedMarkdown(host,source,offset=0,decorate=()=>{}) {
  host.innerHTML=DOMPurify.sanitize(mappedMarkdownHTML(source,offset));
  decorate(host);wrapMarkdownTables(host);
  let lastHighlights=null,lastActive=null,reviewChanges=[];
  const leaves=[...host.querySelectorAll('.md-mapped-text')],nodes=new WeakMap();
  for(const leaf of leaves) {
    const from=Number(leaf.dataset.mdFrom),to=Number(leaf.dataset.mdTo),text=leaf.textContent;
    leaf._mapping=visibleMap(source.slice(from-offset,to-offset),from,text,!!leaf.querySelector('code'));
    leaf._text=text;
  }
  function register(leaf) {
    if(!leaf._mapping)return;
    const walker=document.createTreeWalker(leaf,NodeFilter.SHOW_TEXT);let node,at=0;
    while((node=walker.nextNode())){if(node.parentElement.closest('.review-deletion'))continue;nodes.set(node,leaf._mapping.slice(at,at+node.length));at+=node.length;}
  }
  leaves.forEach(register);
  function boundary(node,at,end) {
    if(node.nodeType!==Node.TEXT_NODE){
      const children=[...node.childNodes],candidates=end?children.slice(0,at).reverse():children.slice(at);
      for(const child of candidates){
        if(child.nodeType===Node.TEXT_NODE){const value=boundary(child,end?child.length:0,end);if(value!==null)return value;}
        else{const walker=document.createTreeWalker(child,NodeFilter.SHOW_TEXT),texts=[];let text;while((text=walker.nextNode()))if(nodes.has(text))texts.push(text);const target=end?texts.at(-1):texts[0];if(target)return boundary(target,end?target.length:0,end);}
      }
      return null;
    }
    const map=nodes.get(node);if(!map?.length)return null;
    if(end)return at===0?map[0].from:map[Math.min(at,map.length)-1].to;
    return at===map.length?map.at(-1).to:map[at]?.from;
  }
  return {
    host,
    setReview(changes){reviewChanges=changes;},
    readingAnchor({x,y}) {
      const caret=document.caretPositionFromPoint?.(x,y),range=!caret&&document.caretRangeFromPoint?.(x,y);
      const node=caret?.offsetNode||range?.startContainer,offset=caret?.offset??range?.startOffset;
      if(!node||!host.contains(node))return null;
      const from=boundary(node,offset,false);if(from===null)return null;
      // Annotation refreshes replace marks/text nodes. Keep the source offset,
      // rather than a DOM Range that could be detached by that refresh.
      return ()=>{
        const walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT);let node;
        while((node=walker.nextNode())){
          const map=nodes.get(node),at=map?.findIndex(p=>p.from<=from&&p.to>from);
          if(at>=0){const range=document.createRange();range.setStart(node,at);range.setEnd(node,at+1);return range.getBoundingClientRect();}
        }
        return null;
      };
    },
    selection(selection=window.getSelection()) {
      if(!selection?.rangeCount||selection.isCollapsed)return null;
      const range=selection.getRangeAt(0);
      if(!host.contains(range.startContainer)||!host.contains(range.endContainer))return null;
      const from=boundary(range.startContainer,range.startOffset,false),to=boundary(range.endContainer,range.endOffset,true);
      if(from===null||to===null||from>=to)return null;
      return {from,to,rect:range.getBoundingClientRect()};
    },
    highlight(spans,active) {
      const signature=JSON.stringify([spans,reviewChanges]);
      if(signature===lastHighlights){
        if(active===lastActive)return;
        const resolved=spans.some(s=>s.id===active&&s.resolved);
        // Focus changes only colors, never text nodes, source maps or selection.
        for(const mark of host.querySelectorAll('[data-anchors]')){
          const ids=mark.dataset.anchors.split(',').map(Number),focused=ids.includes(active);
          mark.classList.toggle('focused-highlight',focused&&!resolved);
          mark.dataset.anchor=String(focused?active:ids[0]);
        }
        lastActive=active;return;
      }
      const selection=window.getSelection();
      if(selection&&!selection.isCollapsed&&host.contains(selection.anchorNode))return;
      lastHighlights=signature;lastActive=active;
      host.querySelectorAll('.review-empty-deletions').forEach(el=>el.remove());
      const deletions=reviewChanges.filter(s=>s.kind==='delete'),assigned=new Map();
      for(const deletion of deletions){
        let leaf=leaves.find(l=>l._mapping?.some(p=>p.to>=deletion.from));leaf??=leaves.filter(l=>l._mapping?.length).at(-1);
        if(leaf){const items=assigned.get(leaf)||[];items.push(deletion);assigned.set(leaf,items);}
        else{const ghost=document.createElement('span');ghost.className='review-deletion review-empty-deletions';ghost.textContent=deletion.text;ghost.title=reviewLabel(deletion);ghost.dataset.reviewDeletion=String(deletion.edit_id||'local');ghost.dataset.reviewFrom=String(deletion.from);host.append(ghost);}
      }
      for(const leaf of leaves) {
        const map=leaf._mapping;if(!map)continue;
        const target=leaf.querySelector('code')||leaf,fragment=document.createDocumentFragment(),ghosts=assigned.get(leaf)||[];let ghostAt=0;
        const addGhost=deletion=>{const ghost=document.createElement('span');ghost.className='review-deletion';ghost.textContent=deletion.text;ghost.title=reviewLabel(deletion);ghost.dataset.reviewDeletion=String(deletion.edit_id||'local');ghost.dataset.reviewFrom=String(deletion.from);fragment.append(ghost);};
        const idsAt=at=>spans.filter(s=>s.from<map[at].to&&s.to>map[at].from).map(s=>s.id);
        const changeAt=at=>reviewChanges.find(s=>s.kind==='insert'&&s.from<map[at].to&&s.to>map[at].from);
        for(let at=0;at<map.length;) {
          while(ghostAt<ghosts.length&&ghosts[ghostAt].from<=map[at].from)addGhost(ghosts[ghostAt++]);
          const ids=idsAt(at),change=changeAt(at);let end=at+1;
          while(end<map.length&&idsAt(end).join(',')===ids.join(',')&&changeAt(end)===change&&!(ghostAt<ghosts.length&&ghosts[ghostAt].from<=map[end].from))end++;
          const text=leaf._text.slice(at,end);
          if(ids.length||change){const resolved=ids.length&&ids.every(id=>spans.find(s=>s.id===id)?.resolved);const mark=document.createElement('span');mark.className=(ids.length?'passage-highlight'+(resolved?' resolved-passage':ids.includes(active)&&!spans.find(s=>s.id===active)?.resolved?' focused-highlight':''):'')+(change?' '+(change.role==='agent'?'review-agent':'review-human'):'');if(ids.length){mark.dataset.anchor=String(ids.includes(active)?active:ids[0]);mark.dataset.anchors=ids.join(',');}if(change)mark.title=reviewLabel(change);mark.textContent=text;fragment.append(mark);}
          else fragment.append(document.createTextNode(text));at=end;
        }
        while(ghostAt<ghosts.length)addGhost(ghosts[ghostAt++]);
        target.replaceChildren(fragment);
      }
      decorate(host);leaves.forEach(register);
    },
    jump(from,to,behavior='auto') {
      const walker=document.createTreeWalker(host,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode())){const map=nodes.get(node);if(map?.some(p=>p.from<to&&p.to>from)){node.parentElement.scrollIntoView({block:'center',behavior});return true;}}
      return false;
    }
  };
}
