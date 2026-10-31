// Flat preorder keeps stable IDs and explicit hierarchy in the database.
export function subtreeEnd(items,index){let end=index+1;while(end<items.length&&items[end].level>items[index].level)end++;return end;}
export function moveBookmark(items,index,direction){
  const result=items.map(item=>({...item})),end=subtreeEnd(result,index),level=result[index].level;
  if(direction<0){let before=index-1;while(before>=0&&result[before].level>level)before--;if(before<0||result[before].level!==level)return result;const group=result.splice(index,end-index);result.splice(before,0,...group);}
  else{if(end>=result.length||result[end].level!==level)return result;const after=subtreeEnd(result,end),group=result.splice(index,end-index);result.splice(after-group.length,0,...group);}
  return result;
}
export function indentBookmark(items,index,direction){
  const result=items.map(item=>({...item})),end=subtreeEnd(result,index),level=result[index].level;
  if(direction<0&&level===0||direction>0&&(index===0||result[index-1].level<level))return result;
  if(direction<0){
    let parent=index-1;while(parent>=0&&result[parent].level>=level)parent--;
    const parentEnd=subtreeEnd(result,parent),group=result.splice(index,end-index);
    for(const item of group)item.level--;
    result.splice(parentEnd-group.length,0,...group);
    return result;
  }
  if(result.slice(index,end).some(item=>item.level+direction>32))return result;
  for(let at=index;at<end;at++)result[at].level+=direction;
  return result;
}
export function removeBookmark(items,index){const result=items.map(item=>({...item})),end=subtreeEnd(result,index);for(let at=index+1;at<end;at++)result[at].level--;result.splice(index,1);return result;}

export function mountPDFContents(host,session,{api,jump,onError}){
  const nav=host.querySelector('nav'),summary=host.querySelector('summary');
  let draft=session.bookmarkDraft??null,draftVersion=session.bookmarkDraftVersion??session.version,draftRevision=session.bookmarkDraftRevision??session.bookmark_revision,busy=false,disposed=false;
  const button=(label,action)=>{const node=document.createElement('button');node.type='button';node.textContent=label;node.onclick=action;return node;};
  function render(){
    session.bookmarkDraft=draft;session.bookmarkDraftVersion=draftVersion;session.bookmarkDraftRevision=draftRevision;
    nav.replaceChildren();
    if(session.bookmarks_stale){const warning=document.createElement('p');warning.textContent='PDF changed. Check bookmark pages, then save to confirm them.';nav.append(warning);}
    if(draft){
      const form=document.createElement('form');form.className='pdf-bookmark-editor';
      draft.forEach((item,index)=>{
        const row=document.createElement('div');row.className='pdf-bookmark-row';row.style.setProperty('--heading-level',item.level);
        const title=document.createElement('input');title.value=item.title;title.required=true;title.maxLength=500;title.setAttribute('aria-label','Bookmark title');title.oninput=()=>item.title=title.value;
        const page=document.createElement('input');page.type='number';page.min=1;page.max=session.pages;page.value=item.page;page.required=true;page.setAttribute('aria-label','Bookmark page');page.oninput=()=>item.page=Number(page.value);
        const act=(label,operation)=>{const control=button(label,()=>{draft=operation();render();});control.setAttribute('aria-label',label+' '+item.title);return control;};
        row.append(title,page,act('Move up',()=>moveBookmark(draft,index,-1)),act('Move down',()=>moveBookmark(draft,index,1)),act('Indent',()=>indentBookmark(draft,index,1)),act('Outdent',()=>indentBookmark(draft,index,-1)),act('Remove',()=>removeBookmark(draft,index)));form.append(row);
      });
      const add=button('Add bookmark',()=>{draft.push({id:crypto.randomUUID(),title:'New bookmark',page:1,level:0});render();nav.querySelector('.pdf-bookmark-row:last-of-type input')?.focus();});
      const save=document.createElement('button');save.type='submit';save.textContent='Save bookmarks';save.disabled=busy;
      const cancel=button('Cancel',()=>{draft=null;render();});cancel.disabled=busy;
      form.append(add,save,cancel);form.onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;save.disabled=cancel.disabled=add.disabled=true;form.querySelectorAll('input,button').forEach(node=>node.disabled=true);
        try{const saved=await api('pdf/bookmarks','PUT',{path:session.path,version:draftVersion,bookmark_revision:draftRevision,bookmarks:draft});Object.assign(session,{bookmarks:saved.bookmarks,bookmark_revision:saved.bookmark_revision,bookmarks_stale:saved.bookmarks_stale});draft=null;session.bookmarkDraft=null;}
        catch(error){onError(error.message);}
        finally{busy=false;if(!disposed)render();}
      };nav.append(form);
    }else{
      for(const item of session.bookmarks){const link=button(item.title+' · '+item.page,()=>{host.open=false;jump(item.page);});link.style.setProperty('--heading-level',item.level);link.disabled=session.bookmarks_stale||item.page>session.pages;nav.append(link);}
      if(!session.bookmarks.length){const empty=document.createElement('p');empty.textContent='No bookmarks yet';nav.append(empty);}
      nav.append(button('Edit bookmarks',()=>{draftVersion=session.version;draftRevision=session.bookmark_revision;draft=session.bookmarks.map(item=>({...item}));render();}));
      nav.append(button('Reload contents',async()=>{try{const saved=await api('pdf?'+new URLSearchParams({path:session.path}));if(saved.version!==session.version)throw new Error('PDF changed. Reopen the file to reload it.');Object.assign(session,saved);render();}catch(error){onError(error.message);}}));
    }
  }
  const outside=event=>{if(host.open&&!host.contains(event.target)&&!draft)host.open=false;};
  const key=event=>{if(event.key==='Escape'){event.stopPropagation();host.open=false;summary.focus();}};
  host.addEventListener('keydown',key);document.addEventListener('pointerdown',outside);render();
  return ()=>{disposed=true;host.open=false;nav.replaceChildren();host.removeEventListener('keydown',key);document.removeEventListener('pointerdown',outside);};
}
