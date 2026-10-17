import {python} from '@codemirror/lang-python';

const parser=python().language.parser;
// Parse source without evaluating it. Offsets use the editor's UTF-16 units.
export function pythonDefinitions(source){
  const result=[],globals=new Set(),lines=[0];
  for(let at=source.indexOf('\n');at>=0;at=source.indexOf('\n',at+1))lines.push(at+1);
  function add(node,kind,depth){
    const name=source.slice(node.from,node.to);if(!name)return;
    if(kind==='variable'){if(globals.has(name))return;globals.add(name);}
    let lo=0,hi=lines.length;while(lo+1<hi){const mid=(lo+hi)>>1;if(lines[mid]<=node.from)lo=mid;else hi=mid;}
    result.push({name,kind,depth,from:node.from,line:lo+1});
  }
  function bindings(node){
    if(node.name==='VariableName')add(node,'variable',0);
    else if(['TupleExpression','ArrayExpression','ParenthesizedExpression','StarredExpression'].includes(node.name))for(let child=node.firstChild;child;child=child.nextSibling)bindings(child);
  }
  function walk(node,scopes=[]){
    if(node.name==='LambdaExpression')return;
    if(['ClassDefinition','FunctionDefinition'].includes(node.name)){
      const name=node.getChild('VariableName'),kind=node.name==='ClassDefinition'?'class':scopes.at(-1)==='class'?'method':'function';
      if(name)add(name,kind,scopes.length);
      const body=node.getChild('Body');if(body)walk(body,scopes.concat(kind==='class'?'class':'function'));
      return;
    }
    if(!scopes.length&&node.name==='AssignStatement'){
      let segment=[],assigned=false;
      for(let child=node.firstChild;child;child=child.nextSibling){
        if(child.name==='AssignOp'){segment.forEach(bindings);segment=[];assigned=true;}
        else if(child.name!=='TypeDef')segment.push(child);
      }
      if(!assigned&&node.getChild('TypeDef'))bindings(node.firstChild);
    }
    if(!scopes.length&&node.name==='NamedExpression')bindings(node.firstChild);
    for(let child=node.firstChild;child;child=child.nextSibling)walk(child,scopes);
  }
  walk(parser.parse(source).topNode);return result;
}

export function mountPythonOutline(host,{navigate,saveOpen}){
  const list=host.querySelector('nav'),summary=host.querySelector('summary');
  let path=null,doc=null,timer=null;
  function render(){
    clearTimeout(timer);if(!doc||!host.open)return;
    const fragment=document.createDocumentFragment();
    for(const item of pythonDefinitions(doc.toString())){
      const button=document.createElement('button');button.type='button';button.dataset.kind=item.kind;
      button.style.setProperty('--outline-depth',Math.min(item.depth,8));button.title=`${item.kind} ${item.name} · line ${item.line}`;
      const symbol=document.createElement('span');symbol.className='outline-symbol';symbol.setAttribute('aria-hidden','true');symbol.textContent=item.kind==='class'?'C':item.kind==='variable'?'·':'ƒ';
      const name=document.createElement('span');name.textContent=item.name;name.className='outline-name';
      button.setAttribute('aria-label',`${item.kind} ${item.name}, line ${item.line}`);
      button.onclick=()=>navigate(item.from);button.append(symbol,name);fragment.append(button);
    }
    if(!fragment.childNodes.length){const empty=document.createElement('p');empty.textContent='No definitions yet';fragment.append(empty);}
    list.replaceChildren(fragment);
  }
  host.addEventListener('toggle',()=>{saveOpen(host.open);if(host.open)render();else clearTimeout(timer);});
  host.addEventListener('keydown',event=>{if(event.key==='Escape'&&host.open){event.preventDefault();event.stopPropagation();host.open=false;summary.focus();}});
  return {setDocument(nextPath,nextDoc){
    if(path===nextPath&&doc===nextDoc)return;
    const changed=path!==nextPath;path=nextPath;doc=nextDoc;host.hidden=!doc;clearTimeout(timer);
    if(!doc){list.replaceChildren();return;}
    if(changed){list.scrollTop=0;render();}else if(host.open)timer=setTimeout(render,150);
  }};
}
