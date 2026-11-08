// Runs ONLY in a disposable test workspace; never included in the private VSIX.
const vscode=require('vscode');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const hash=s=>crypto.createHash('sha256').update(s).digest('hex');
const pause=()=>new Promise(resolve=>setTimeout(resolve,50));
async function until(fn){const deadline=Date.now()+15000;while(Date.now()<deadline){if(await fn())return;await pause();}throw new Error('Observable state did not arrive within 15 seconds.');}
function activate(){void run();}
async function run(){
  const root=vscode.workspace.workspaceFolders[0].uri.fsPath,resultFile=path.join(root,'.looking-glass','host-result.json'),passed=[];
  const base=vscode.workspace.getConfiguration('lookingGlass').get('serverUrl');
  const token=(await fs.readFile(path.join(root,'.looking-glass','token'),'utf8')).trim();
  async function api(route,body,method){
    return new Promise((resolve,reject)=>{
      const payload=body===undefined?undefined:JSON.stringify(body);
      const req=http.request(new URL('/api/'+route,base),{method:method||(payload?'POST':'GET'),headers:{'X-Looking-Glass-Token':token,...(payload?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)}:{})}},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>{try{resolve({status:res.statusCode,body:JSON.parse(Buffer.concat(chunks).toString())});}catch(e){reject(e);}});});req.on('error',reject);req.end(payload);
    });
  }
  try {
    const file=path.join(root,'main.py'),uri=vscode.Uri.file(file);
    const doc=await vscode.workspace.openTextDocument(uri);await vscode.window.showTextDocument(doc);
    const original=doc.getText();
    async function replace(text){const edit=new vscode.WorkspaceEdit();edit.replace(uri,new vscode.Range(doc.positionAt(0),doc.positionAt(doc.getText().length)),text);assert.ok(await vscode.workspace.applyEdit(edit));}
    await replace(original+'# already dirty\n');assert.ok(doc.isDirty);
    const ext=vscode.extensions.getExtension('looking-glass-local.looking-glass-companion');assert.ok(ext,'Packaged companion is installed');
    const bridge=await ext.activate();await bridge.connect();
    await until(async()=> (await api('bridge/status')).body.dirty.includes('main.py'));
    passed.push('initial already-dirty snapshot');
    assert.equal((await api('bridge/pair',{root})).status,409);
    passed.push('second paired window rejected');
    let disk=await api('file?path=main.py');
    assert.equal((await api('file',{path:'main.py',content:'clobber',version:disk.body.version},'PUT')).status,423);
    passed.push('native dirty state blocks backend save');
    assert.ok(await doc.save());
    await until(async()=> !(await api('bridge/status')).body.dirty.includes('main.py'));
    assert.equal(await fs.readFile(file,'utf8'),doc.getText());
    passed.push('native save unlocks after final disk bytes');
    disk=await api('file?path=main.py');
    const external=original+'# saved by Looking Glass\n';
    assert.equal((await api('file',{path:'main.py',content:external,version:disk.body.version},'PUT')).status,200);
    await until(()=>doc.getText()===external&&!doc.isDirty);
    passed.push('Looking Glass atomic save reloads through native watcher');
    let providerCalls=0;
    const registrations=[
      vscode.languages.registerDefinitionProvider('python',{provideDefinition(){providerCalls++;return new vscode.Location(uri,new vscode.Position(0,4));}}),
      vscode.languages.registerCompletionItemProvider('python',{provideCompletionItems(){providerCalls++;const safe=new vscode.CompletionItem('safe');safe.insertText='safe_value';safe.range=new vscode.Range(1,0,1,5);const unsafe=new vscode.CompletionItem('unsafe');unsafe.command={command:'workbench.action.closeWindow',title:'never run'};return [safe,unsafe];}}),
      vscode.languages.registerHoverProvider('python',{provideHover(){providerCalls++;return new vscode.Hover(new vscode.MarkdownString('**Native provider**'));}})
    ];
    const language=async provider=>{const d=(await api('file?path=main.py')).body;return api('bridge/provider',{path:'main.py',content:d.content,hash:d.version,mode:'edit',line:2,column:2,provider});};
    let answer=await language('definition');assert.equal(answer.status,200);assert.equal(answer.body.definitions[0].column,4);
    answer=await language('completion');assert.equal(answer.status,200);assert.deepEqual(answer.body.items.map(i=>i.label),['safe']);
    answer=await language('hover');assert.equal(answer.status,200);assert.match(answer.body.markdown,/Native provider/);
    passed.push('public native definition, completion and hover commands; unsafe commands omitted');
    const calls=providerCalls,d=(await api('file?path=main.py')).body;
    assert.equal((await api('bridge/provider',{path:'main.py',content:d.content,hash:d.version,mode:'review',line:2,column:2,provider:'definition'})).status,400);
    assert.equal(providerCalls,calls);
    passed.push('Review dispatches zero native provider calls');
    await replace(external+'# unsaved\n');
    await until(async()=> (await api('bridge/status')).body.dirty.includes('main.py'));
    assert.equal((await language('hover')).status,423);
    passed.push('new dirty buffer rejects provider eligibility');
    await vscode.commands.executeCommand('workbench.action.files.revert');
    await until(()=>!doc.isDirty);await until(async()=>!(await api('bridge/status')).body.dirty.includes('main.py'));
    assert.equal(doc.getText(),external);
    passed.push('native discard reconciles and unlocks without saving');
    // Use VS Code's installed built-in TypeScript/JavaScript extension as well as controlled fixtures.
    const jsUri=vscode.Uri.file(path.join(root,'native.js'));
    const jsDoc=await vscode.workspace.openTextDocument(jsUri);
    await vscode.window.showTextDocument(jsDoc);
    await vscode.extensions.getExtension('vscode.typescript-language-features').activate();
    await until(async()=> (await vscode.commands.executeCommand('vscode.executeDefinitionProvider',jsUri,new vscode.Position(1,2)))?.length>0);
    const js=(await api('file?path=native.js')).body;
    answer=await api('bridge/provider',{path:'native.js',content:js.content,hash:js.version,mode:'edit',line:2,column:2,provider:'definition'});
    assert.equal(answer.status,200);assert.equal(answer.body.definitions[0].line,1);
    passed.push('installed built-in JavaScript language service forwarded end to end');
    registrations.forEach(r=>r.dispose());
    if(vscode.workspace.getConfiguration('lookingGlass').get('testPythonProvider')) {
      const python=vscode.extensions.getExtension('detachhead.basedpyright');assert.ok(python,'BasedPyright is installed');await python.activate();
      await vscode.window.showTextDocument(doc);
      await until(async()=> (await vscode.commands.executeCommand('vscode.executeDefinitionProvider',uri,new vscode.Position(3,2)))?.length>0);
      const real=await api('bridge/provider',{path:'main.py',content:external,hash:hash(external),mode:'edit',line:4,column:2,provider:'definition'});
      assert.equal(real.status,200);assert.equal(real.body.definitions[0].line,1);
      passed.push('installed open-source BasedPyright Python definition forwarded end to end');
    }
    await vscode.window.showTextDocument(doc);
    let nativeSaves=0;
    const saveEvent=vscode.workspace.onDidSaveTextDocument(d=>{if(d===doc)nativeSaves++;});
    const formatter=vscode.workspace.onWillSaveTextDocument(e=>{if(e.document===doc)e.waitUntil(Promise.resolve([vscode.TextEdit.insert(doc.positionAt(doc.getText().length),'# save participant\n')]));});
    await replace(external+'# format me\n');assert.ok(await doc.save());
    await until(async()=>!(await api('bridge/status')).body.dirty.includes('main.py'));
    assert.equal(await fs.readFile(file,'utf8'),doc.getText());assert.ok(doc.getText().endsWith('# save participant\n'));
    assert.equal(nativeSaves,1);formatter.dispose();
    passed.push('save participants publish final bytes exactly once without a save echo');
    const editAll=new vscode.WorkspaceEdit();editAll.insert(uri,doc.positionAt(doc.getText().length),'# save all\n');editAll.insert(jsUri,jsDoc.positionAt(jsDoc.getText().length),'// save all\n');
    assert.ok(await vscode.workspace.applyEdit(editAll));assert.ok(await vscode.workspace.saveAll(false));
    await until(async()=>!(await api('bridge/status')).body.dirty.length);
    assert.equal(await fs.readFile(file,'utf8'),doc.getText());assert.equal(await fs.readFile(jsUri.fsPath,'utf8'),jsDoc.getText());
    passed.push('native Save All reconciles multiple documents');
    const auto=vscode.workspace.getConfiguration('files',uri);await auto.update('autoSave','afterDelay',vscode.ConfigurationTarget.Workspace);await auto.update('autoSaveDelay',1000,vscode.ConfigurationTarget.Workspace);
    await replace(doc.getText()+'# autosave\n');await until(()=>!doc.isDirty);
    await until(async()=>!(await api('bridge/status')).body.dirty.includes('main.py'));
    assert.equal(await fs.readFile(file,'utf8'),doc.getText());await auto.update('autoSave','off',vscode.ConfigurationTarget.Workspace);saveEvent.dispose();
    passed.push('native Auto Save reconciles after the actual save');
    const slow=vscode.languages.registerHoverProvider('python',{async provideHover(){await replace(doc.getText()+'# dirty during provider\n');return new vscode.Hover('stale result');}});
    const latest=(await api('file?path=main.py')).body;
    const stale=await api('bridge/provider',{path:'main.py',content:latest.content,hash:latest.version,mode:'edit',line:2,column:2,provider:'hover'});
    assert.notEqual(stale.status,200);slow.dispose();assert.ok(doc.isDirty);
    passed.push('native edit during provider call rejects stale results and preserves draft');

    await api('bridge/disconnect',{});
    await fs.writeFile(resultFile,JSON.stringify({passed}));
  }catch(error){await fs.writeFile(resultFile,JSON.stringify({passed,error:error.stack}));}
}
module.exports={activate};
