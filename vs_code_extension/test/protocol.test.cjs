const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const {origin,relative,documentState,hash,request}=require('../src/protocol.cjs');

for(const bad of ['https://localhost:8765','http://example.com:8765','http://127.0.0.1:8765/a','http://user:password@localhost:8765','http://localhost:8765/?a=1','http://localhost','http://localhost:8765/#secret']) {
  test('reject nonlocal or ambiguous URL '+bad,()=>assert.throws(()=>origin(bad)));
}
test('accept supported loopback URLs',()=>{for(const host of ['127.0.0.1','localhost','[::1]'])assert.equal(origin(`http://${host}:8765/`),`http://${host}:8765`);});
test('canonical paths reject traversal, schemes, symlinks and metadata',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'lg-path-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
  await fs.writeFile(path.join(root,'a.py'),'a');await fs.symlink(path.join(root,'a.py'),path.join(root,'link'));
  const uri=name=>({scheme:'file',fsPath:path.join(root,name)});
  assert.equal(await relative(root,uri('a.py')),'a.py');
  for(const value of [uri('../outside'),uri('.looking-glass/token'),uri('link'),uri('missing'),{...uri('a.py'),scheme:'untitled'}])assert.equal(await relative(root,value),null);
});
test('UTF-8 LF/CRLF BOM and dirty/lagging snapshots are version-bound',async t=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'lg-state-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const file=path.join(root,'a.py');
  for(const source of ['😀 = 1\n','😀 = 1\r\n','\uFEFF😀 = 1\r\n']) {
    await fs.writeFile(file,source);
    const doc={uri:{scheme:'file',fsPath:file},isDirty:false,version:1,getText:()=>source.replace(/^\uFEFF/,'')};
    assert.equal((await documentState(root,doc)).hash,hash(Buffer.from(source)));
    doc.isDirty=true;doc.version++;
    assert.equal((await documentState(root,doc)).hash,null);
    doc.isDirty=false;doc.version++;doc.getText=()=>source+'lagging';
    assert.equal((await documentState(root,doc)).hash,null);
  }
  await fs.writeFile(file,Buffer.from([0xff,0x80]));
  assert.equal((await documentState(root,{uri:{scheme:'file',fsPath:file},isDirty:false,version:1,getText:()=>''})).hash,null);
});
test('transport preserves scoped headers, bounds responses and rejects redirects',async t=>{
  const server=http.createServer((req,res)=>{
    assert.equal(req.headers['x-looking-glass-bridge'],'scoped');
    if(req.url.endsWith('/redirect')){res.writeHead(302,{'Location':'http://example.com'});res.end('{}');}
    else res.end(JSON.stringify({ok:true}));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>server.close());
  const base=`http://127.0.0.1:${server.address().port}`,headers={'X-Looking-Glass-Bridge':'scoped'};
  assert.deepEqual(await request(base,'session/snapshot',{},headers),{ok:true});
  await assert.rejects(request(base,'redirect',undefined,headers));
});
