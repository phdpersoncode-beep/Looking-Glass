const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const {createHash} = require('node:crypto');
const MAX_BYTES = 8*1024*1024;
const hash = value => createHash('sha256').update(value).digest('hex');
function origin(value) {
  const url = new URL(value);
  if(url.protocol!=='http:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname) || !url.port || url.username || url.password || url.pathname!=='/' || url.search || url.hash) throw new Error('Use an HTTP loopback origin with an explicit port.');
  return url.origin;
}
async function relative(root, uri) {
  if(uri.scheme!=='file') return null;
  const name=path.relative(root,uri.fsPath);
  if(!name || path.isAbsolute(name) || name.split(path.sep).some(p=>['..','.looking-glass','.git','node_modules','.venv'].includes(p))) return null;
  let full=root;
  for(const part of name.split(path.sep)) {
    full=path.join(full,part);
    try {if((await fs.lstat(full)).isSymbolicLink()) return null;} catch {return null;}
  }
  if(await fs.realpath(full)!==full) return null;
  return name.split(path.sep).join('/');
}
function request(base, route, data, headers={}, signal) {
  return new Promise((resolve,reject)=>{
    let body;
    try {body=data===undefined?undefined:Buffer.from(JSON.stringify(data));} catch(error){reject(error);return;}
    if(body?.length>MAX_BYTES){reject(new Error('Bridge payload too large.'));return;}
    const req=http.request(new URL('/api/bridge/'+route,origin(base)),{method:body?'POST':'GET',headers:{...headers,...(body?{'Content-Type':'application/json','Content-Length':body.length}:{})},signal},response=>{
      let size=0; const chunks=[];
      response.on('data',chunk=>{size+=chunk.length;if(size>MAX_BYTES)req.destroy(new Error('Bridge response too large.'));else chunks.push(chunk);});
      response.on('error',reject);
      response.on('end',()=>{try {const value=JSON.parse(Buffer.concat(chunks).toString());if(response.statusCode!==200){const error=new Error(value.error||'Bridge request failed.');error.status=response.statusCode;reject(error);}else resolve(value);}catch(error){reject(error);}});
    });
    req.setTimeout(10000,()=>req.destroy(new Error('Bridge request timed out.')));
    req.on('error',reject);req.end(body);
  });
}
const cache=new WeakMap();
async function documentState(root, doc) {
  const name=await relative(root,doc.uri);if(!name)return null;
  let diskHash=null,textHash=null;
  if(!doc.isDirty) {
    const stat=await fs.stat(doc.uri.fsPath);
    const key=[doc.version,stat.size,stat.mtimeMs,stat.ctimeMs].join(':');
    const previous=cache.get(doc);
    if(previous?.key===key)return {...previous.state};
    if(stat.size<=MAX_BYTES) {
      const bytes=await fs.readFile(doc.uri.fsPath);
      try {
        const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
        if(!text.includes('\0') && text===doc.getText()) {diskHash=hash(bytes);textHash=hash(text);}
        if(!doc.isDirty)cache.set(doc,{key,state:{path:name,dirty:false,version:doc.version,hash:diskHash,text_hash:textHash}});
      } catch { /* Unsupported encodings are ineligible for provider requests. */ }
    }
  }
  return {path:name,dirty:doc.isDirty,version:doc.version,hash:diskHash,text_hash:textHash};
}
module.exports={origin,relative,request,documentState,hash,MAX_BYTES};
