// The committed cursor changes only when a file is displayed. A requested
// cursor lets rapid Back/Forward clicks supersede an unfinished file read.
export function createFileHistory(saved={},limit=100){
  const original=Array.isArray(saved.entries)?saved.entries.filter(path=>typeof path==='string'&&path):[];
  let entries=original.slice(-limit),index=entries.length?Math.max(0,Math.min(entries.length-1,(Number.isInteger(saved.index)?saved.index:original.length-1)-(original.length-entries.length))):-1,requested=null;
  return {
    get snapshot(){return {entries:[...entries],index};},
    target(delta){const at=(requested??index)+delta;return at>=0&&at<entries.length?{path:entries[at],index:at}:null;},
    request(at=null){requested=Number.isInteger(at)&&at>=0&&at<entries.length?at:null;},
    cancel(){requested=null;},
    visit(path,at=null){
      requested=null;
      if(Number.isInteger(at)&&entries[at]===path){index=at;return;}
      if(entries[index]===path)return;
      entries=entries.slice(0,index+1).concat(path).slice(-limit);index=entries.length-1;
    },
    clear(){entries=[];index=-1;requested=null;}
  };
}

export function mountFileHistory(host,history,{navigate,save}){
  const back=host.querySelector('[data-history=back]'),forward=host.querySelector('[data-history=forward]');
  const menu=host.querySelector('details'),list=host.querySelector('nav'),clear=host.querySelector('[data-history=clear]');
  function open(target){if(target){history.request(target.index);menu.open=false;render();navigate(target);}}
  function render(){
    back.disabled=!history.target(-1);forward.disabled=!history.target(1);
    if(!menu.open)return;
    const {entries,index}=history.snapshot,fragment=document.createDocumentFragment();
    clear.disabled=!entries.length;
    for(let at=entries.length-1;at>=0;at--){
      const button=document.createElement('button');button.type='button';button.textContent=entries[at];button.title=entries[at];
      if(at===index)button.setAttribute('aria-current','page');
      button.onclick=()=>open({path:entries[at],index:at});fragment.append(button);
    }
    if(!entries.length){const empty=document.createElement('p');empty.textContent='No recent files';fragment.append(empty);}
    list.replaceChildren(fragment);
  }
  back.onclick=()=>open(history.target(-1));forward.onclick=()=>open(history.target(1));
  clear.onclick=()=>{history.clear();save(history.snapshot);render();};
  menu.addEventListener('toggle',render);
  menu.addEventListener('keydown',event=>{if(event.key==='Escape'&&menu.open){event.preventDefault();event.stopPropagation();menu.open=false;menu.querySelector('summary').focus();}});
  document.addEventListener('pointerdown',event=>{if(menu.open&&!host.contains(event.target))menu.open=false;});
  render();return {render,remember(){save(history.snapshot);render();}};
}
