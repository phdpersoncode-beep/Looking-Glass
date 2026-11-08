const fs = require('node:fs/promises');
const path = require('node:path');
const {relative,documentState,MAX_BYTES,hash} = require('./protocol.cjs');
function validRange(doc,range) {
  const valid=p=>Number.isInteger(p?.line)&&Number.isInteger(p.character)&&p.line>=0&&p.line<doc.lineCount&&p.character>=0&&p.character<=doc.lineAt(p.line).text.length;
  return valid(range?.start)&&valid(range?.end)&&!range.end.isBefore(range.start);
}
async function provide(vscode, root, message, current) {
  const uri=vscode.Uri.file(path.resolve(root,message.path));
  if(await relative(root,uri)!==message.path) throw new Error('Invalid workspace provider path.');
  const doc=await vscode.workspace.openTextDocument(uri),version=doc.version;
  const eligible=async()=>current()&&doc.version===version&&!doc.isDirty&&(await documentState(root,doc))?.hash===message.hash;
  if(!await eligible()) throw new Error('Document is dirty or awaiting disk refresh.');
  const pos=new vscode.Position(message.position.line,message.position.character);
  if(!validRange(doc,new vscode.Range(pos,pos)))throw new Error('Invalid UTF-16 position.');
  let result;
  if(message.provider==='definition') {
    const targets=await vscode.commands.executeCommand('vscode.executeDefinitionProvider',uri,pos)||[];
    const definitions=[];
    for(const target of targets.slice(0,64)) {
      const dest=target.targetUri||target.uri,range=target.targetSelectionRange||target.range;
      const name=dest&&await relative(root,dest);if(!name)continue;
      if((await fs.stat(dest.fsPath)).size>MAX_BYTES)continue;
      const destination=vscode.workspace.textDocuments.find(d=>d.uri.toString()===dest.toString());
      if(destination&&(destination.isDirty||!(await documentState(root,destination))?.hash))continue;
      const destVersion=destination?.version,bytes=await fs.readFile(dest.fsPath);
      if(destination&&(destination.isDirty||destination.version!==destVersion))continue;
      const disk=new TextDecoder('utf-8',{fatal:true}).decode(bytes);const lines=disk.replace(/^\uFEFF/,'').split('\n');
      if(range.start.line>=lines.length)continue;
      definitions.push({path:name,line:range.start.line+1,column:Array.from(lines[range.start.line].slice(0,range.start.character)).length,name:path.basename(name),version:hash(bytes)});
    }
    result={definitions};
  } else if(message.provider==='completion') {
    const list=await vscode.commands.executeCommand('vscode.executeCompletionItemProvider',uri,pos);
    const items=[];
    for(const item of (list?.items||[]).slice(0,200)) {
      // Never execute provider commands or apply workspace edits/snippets.
      if(item.command||item.additionalTextEdits?.length||item.insertText instanceof vscode.SnippetString)continue;
      const edit=item.textEdit,range=edit?.range||item.range;
      if(!validRange(doc,range))continue;
      const text=edit?.newText??item.insertText??(typeof item.label==='string'?item.label:item.label?.label);
      if(typeof text!=='string'||text.length>16384)continue;
      items.push({label:typeof item.label==='string'?item.label:item.label?.label,text,range:{start:range.start,end:range.end}});
    }
    result={items};
  } else if(message.provider==='hover') {
    const hovers=await vscode.commands.executeCommand('vscode.executeHoverProvider',uri,pos)||[];
    result={markdown:hovers.flatMap(h=>h.contents.map(c=>typeof c==='string'?c:c.value||'')).join('\n\n').slice(0,32768)};
  } else throw new Error('Unknown provider.');
  if(!await eligible()) throw new Error('Provider result became stale.');
  return {...result,version,hash:message.hash};
}
module.exports={provide,validRange};
