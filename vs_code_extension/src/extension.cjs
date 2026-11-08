const vscode=require('vscode');
const fs=require('node:fs/promises');
const path=require('node:path');
const {origin,request,documentState}=require('./protocol.cjs');
const {provide}=require('./providers.cjs');
let active,connecting=false;
function activate(context) {
  const status=vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left,10);
  status.text='$(plug) Looking Glass';status.command='lookingGlass.connect';status.tooltip='Connect to Looking Glass explicitly';status.show();
  context.subscriptions.push(status);
  const stop=()=>{if(active){active.abort.abort();active=undefined;}status.text='$(plug) Looking Glass';status.command='lookingGlass.connect';};
  async function connect() {
    if(connecting||active)throw new Error('Already connected or connecting. Disconnect first.');
    connecting=true;
    try {
      if(!vscode.workspace.isTrusted)throw new Error('Trust this workspace before connecting.');
      const folders=vscode.workspace.workspaceFolders;
      if(folders?.length!==1||folders[0].uri.scheme!=='file')throw new Error('Open one local workspace folder.');
      const root=await fs.realpath(folders[0].uri.fsPath);
      const base=origin(vscode.workspace.getConfiguration('lookingGlass',folders[0].uri).get('serverUrl'));
      const token=(await fs.readFile(path.join(root,'.looking-glass','token'),'utf8')).trim();
      const paired=await request(base,'pair',{root},{'X-Looking-Glass-Token':token});
      const session={root,base,epoch:paired.epoch,abort:new AbortController(),sequence:0,serial:Promise.resolve(),providers:0};
      session.headers={'X-Looking-Glass-Bridge':paired.credential,'X-Looking-Glass-Epoch':paired.epoch};
      active=session;
      const send=(route,data)=>request(base,'session/'+route,data,session.headers,session.abort.signal);
      session.send=send;
      session.snapshot=requestId=>{
        const job=session.serial.then(async()=>{
          if(active!==session)return;
          session.changeQueued=false;
          const documents=[];
          for(const doc of vscode.workspace.textDocuments){const state=await documentState(root,doc);if(state)documents.push(state);}
          if(documents.length>512)throw new Error('Close some files: the bridge supports 512 open documents.');
          await send('snapshot',{sequence:++session.sequence,documents,request_id:requestId});
        });
        session.serial=job.catch(()=>{});
        return job;
      };
      await session.snapshot();
      status.text='$(link) Looking Glass';status.tooltip='Paired with local Looking Glass';status.command='lookingGlass.disconnect';
      void (async()=>{
        try {
          while(active===session){
            const response=await send('poll');if(response.epoch!==session.epoch)throw new Error('Connection epoch changed.');
            for(const message of response.messages){
              if(active!==session||message.epoch!==session.epoch)continue;
              if(message.kind==='state-request'||message.kind==='saved')await session.snapshot(message.request_id);
              else if(message.kind==='provider-request') {
                if(session.providers>=4){void send('result',{request_id:message.request_id,result:{error:'Providers busy.'}}).catch(()=>{});continue;}
                session.providers++;let timer;
                const operation=provide(vscode,root,message,()=>active===session).finally(()=>{session.providers--;});
                void Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Provider deadline exceeded.')),2500);timer.unref?.();})])
                  .then(result=>send('result',{request_id:message.request_id,result}),()=>send('result',{request_id:message.request_id,result:{error:'Provider unavailable or stale.'}})).catch(()=>{}).finally(()=>clearTimeout(timer));
              }
            }
          }
        }catch(error){if(active===session){stop();status.text='$(warning) Looking Glass';status.tooltip='Connection lost. Looking Glass disk writes stay blocked until reconnect or explicit disconnect.';}}
      })();
    }catch(error){if(active)stop();throw error;}finally{connecting=false;}
  }
  async function disconnect() {
    const choice=await vscode.window.showWarningMessage('End Looking Glass dirty-file protection? Neither application’s drafts will be saved or discarded.',{modal:true},'Disconnect');
    if(choice!=='Disconnect')return;
    const session=active;
    if(session){
      const token=(await fs.readFile(path.join(session.root,'.looking-glass','token'),'utf8')).trim();
      await request(session.base,'disconnect',{}, {'X-Looking-Glass-Token':token});stop();
    } else vscode.window.showInformationMessage('Use “Disconnect VS Code” in Looking Glass to clear a lost pairing.');
  }
  const command=fn=>async()=>{try{return await fn();}catch(error){vscode.window.showErrorMessage('Looking Glass: '+error.message);}};
  const changed=()=>{const session=active;if(session&&!session.changeQueued){session.changeQueued=true;void session.snapshot().catch(()=>{if(active===session)stop();});}};
  context.subscriptions.push(vscode.commands.registerCommand('lookingGlass.connect',command(connect)),vscode.commands.registerCommand('lookingGlass.disconnect',command(disconnect)),
    vscode.workspace.onDidOpenTextDocument(changed),vscode.workspace.onDidChangeTextDocument(changed),vscode.workspace.onDidSaveTextDocument(changed),vscode.workspace.onDidCloseTextDocument(changed),
    vscode.workspace.onDidChangeWorkspaceFolders(stop),vscode.workspace.onDidChangeConfiguration(e=>{if(e.affectsConfiguration('lookingGlass.serverUrl'))stop();}),{dispose:stop});
  return {connect,disconnect,session:()=>active};
}
function deactivate(){active?.abort.abort();active=undefined;}
module.exports={activate,deactivate};
