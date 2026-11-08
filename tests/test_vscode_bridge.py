"""Live state authorization, epochs, restart safety and bounded provider forwarding."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace, Problem
from looking_glass.file_operations import FileOperations


@pytest.fixture
def pair(tmp_path):
    (tmp_path/'a.py').write_text('value = 1\n')
    ws=Workspace(tmp_path);b=ws.bridge
    credential=b.pair({'root':str(tmp_path)})
    b.snapshot({'sequence':1,'documents':[]})
    return ws,b,credential


def snapshot(b,dirty=False,request_id=None):
    b.snapshot({'sequence':b.sequence+1,'documents':[{'path':'a.py','dirty':dirty,'version':1,'hash':'a'*64,'text_hash':'a'*64}], 'request_id':request_id})


def respond(b,job,dirty=False,result=None):
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(job)
        messages=b.poll()['messages']
        assert len(messages)==1
        message=messages[0]
        if message['kind']=='state-request': snapshot(b,dirty,message['request_id'])
        else: b.result({'request_id':message['request_id'],'result':result})
        return future.result()


def test_pairing_root_scope_auth_and_second_window(pair):
    ws,b,c=pair
    b.authenticate(c['credential'],c['epoch'])
    for token,epoch in [(ws.token,c['epoch']),(c['credential'],'old')]:
        with pytest.raises(Problem): b.authenticate(token,epoch)
    with pytest.raises(Problem,match='already'): b.pair({'root':str(ws.root)})
    with pytest.raises(Problem,match='canonical'): b.pair({'root':'/wrong'})


def test_initial_snapshot_required_restart_and_expiry(pair):
    ws,b,c=pair
    snapshot(b,True)
    restarted=Workspace(ws.root).bridge
    assert restarted.status()['dirty']==['a.py']
    assert restarted.enabled and not restarted.status()['live']
    with pytest.raises(Problem): restarted.guard('a.py')
    b.seen-=16
    assert not b.status()['live']
    with pytest.raises(Problem): b.guard('a.py')
    b.disconnect()
    assert not Workspace(ws.root).bridge.enabled
    ws.save('a.py','changed\n',ws.read('a.py')['version'])


def test_dirty_blocks_save_approval_and_folder_operations(pair):
    ws,b,c=pair
    original=ws.read('a.py'); draft=ws.reviews.start('a.py',original['version'])
    for job in [lambda:ws.save('a.py','overwrite',original['version']),lambda:ws.reviews.approve(draft['id'],draft['version']),
                lambda:FileOperations(ws).change('a.py',FileOperations(ws).info('a.py')['version'],delete=True)]:
        with pytest.raises(Problem,match='unsaved'): respond(b,job,True)
    assert ws.text('a.py')[0]==original['content']
    assert ws.reviews.read(draft['id'])['status']=='pending'


def test_fresh_guard_clean_save_writes_once_and_notifies(pair):
    ws,b,c=pair
    before=ws.read('a.py')
    saved=respond(b,lambda:ws.save('a.py','new\n',before['version']))
    assert ws.text('a.py')==('new\n',saved['version'])
    messages=b.poll()['messages'];assert messages[0]['kind']=='saved'
    assert messages[0]['hash']==saved['version']


def test_duplicates_reordering_gap_and_close_reconciliation(pair):
    ws,b,c=pair
    snapshot(b,True);sequence=b.sequence
    b.snapshot({'sequence':sequence-1,'documents':[]})
    assert b.status()['dirty']==['a.py']
    b.snapshot({'sequence':sequence+4,'documents':[{'path':'a.py','dirty':False,'version':2}]})
    assert b.status()['dirty']==['a.py']  # clean but watcher not synchronized
    b.snapshot({'sequence':sequence+5,'documents':[]})
    assert not b.status()['dirty']


def test_disconnect_cancels_pending_and_stale_epoch_cannot_unlock(pair):
    ws,b,c=pair
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(b.guard,'a.py');b.poll();b.disconnect()
        with pytest.raises(Problem):job.result()
    new=b.pair({'root':str(ws.root)})
    with pytest.raises(Problem): b.authenticate(c['credential'],c['epoch'])
    assert new['epoch']!=c['epoch'] and not b.status()['live']


def test_snapshot_payload_paths_and_limits(pair):
    ws,b,c=pair
    for documents in [[{}]*513,[{'path':'../a.py','dirty':True,'version':1}],[{'path':'/tmp/a.py','dirty':True,'version':1}], [{'path':'a.py','dirty':'false','version':1}]]:
        with pytest.raises(Problem):b.snapshot({'sequence':2,'documents':documents})
    assert b.sequence==1


def test_http_auth_origin_and_scoped_credentials(tmp_path):
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client()
    assert client.post('/api/bridge/pair',json={'root':str(tmp_path)}).status_code==401
    h={'X-Looking-Glass-Token':ws.token}
    c=client.post('/api/bridge/pair',headers=h,json={'root':str(tmp_path)}).json
    scoped={'X-Looking-Glass-Bridge':c['credential'],'X-Looking-Glass-Epoch':c['epoch']}
    assert client.post('/api/bridge/session/snapshot',headers={**scoped,'Origin':'https://evil.invalid'},json={'sequence':1,'documents':[]}).status_code==403
    assert client.post('/api/bridge/session/snapshot',headers=scoped,json={'sequence':1,'documents':[]}).status_code==200
    assert client.get('/api/project',headers=scoped).status_code==401
    assert client.get('/api/bridge/session/poll',headers=h).status_code==401


def test_review_and_unsaved_buffers_never_dispatch_provider(pair):
    ws,b,c=pair
    data={'path':'a.py','mode':'review','provider':'definition','hash':ws.text('a.py')[1],'content':ws.text('a.py')[0],'line':1,'column':0}
    with pytest.raises(Problem):b.provider(data)
    data.update(mode='edit',content='unsaved')
    with pytest.raises(Problem):b.provider(data)
    assert b.queue==[]


def test_provider_unicode_position_result_and_stale_rejection(pair):
    ws,b,c=pair
    (ws.root/'a.py').write_text('"😀"; value\n')
    content,version=ws.text('a.py')
    data=dict(path='a.py',mode='edit',provider='definition',hash=version,content=content,line=1,column=5)
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(b.provider,data)
        probe=b.poll()['messages'][0]
        b.snapshot({'sequence':b.sequence+1,'request_id':probe['request_id'],'documents':[]})
        msg=b.poll()['messages'][0]
        assert msg['position']=={'line':0,'character':6}
        b.result({'request_id':msg['request_id'],'result':{'definitions':[{'path':'a.py','line':1,'column':5,'name':'value','version':version}]}})
        assert job.result()['definitions'][0]['version']==version


def test_containing_folder_guard_and_discussion_updates(pair):
    ws,b,c=pair
    (ws.root/'nested').mkdir();(ws.root/'nested/a.py').write_text('value\n')
    info=FileOperations(ws).info('nested')
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(FileOperations(ws).change,'nested',info['version'],'renamed')
        probe=b.poll()['messages'][0]
        b.snapshot({'sequence':2,'request_id':probe['request_id'],'documents':[{'path':'nested/a.py','dirty':True,'version':2}]})
        with pytest.raises(Problem,match='unsaved'):job.result()
    file=ws.read('a.py')
    thread=ws.create_thread('a.py',0,5,'Discussion remains available','User',file['version'])
    assert thread['messages'][0]['body']=='Discussion remains available'


def test_live_provider_results_rejected_after_dirty_edit_or_epoch_change(pair):
    ws,b,c=pair
    content,version=ws.text('a.py')
    data=dict(path='a.py',mode='edit',provider='hover',hash=version,content=content,line=1,column=2)
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(b.provider,data)
        probe=b.poll()['messages'][0];snapshot(b,False,probe['request_id'])
        # Replace the fixture's intentionally unrelated hash with the actual saved hash.
        b.states['a.py']['hash']=version
        message=b.poll()['messages'][0]
        snapshot(b,True)
        b.result({'request_id':message['request_id'],'result':{'version':1,'markdown':'stale'}})
        with pytest.raises(Problem,match='stale'):job.result()


def test_bom_crlf_position_adapter_preserves_disk_hash(pair):
    ws,b,c=pair
    content='\ufeff"😀"; value\r\n';(ws.root/'a.py').write_bytes(content.encode())
    version=ws.text('a.py')[1]
    data=dict(path='a.py',mode='edit',provider='hover',hash=version,content=content,line=1,column=6)
    with ThreadPoolExecutor(1) as pool:
        job=pool.submit(b.provider,data);probe=b.poll()['messages'][0]
        b.snapshot({'sequence':2,'documents':[],'request_id':probe['request_id']})
        message=b.poll()['messages'][0];assert message['position']=={'line':0,'character':6}
        b.result({'request_id':message['request_id'],'result':{'version':1,'markdown':'saved'}})
        assert job.result()['markdown']=='saved'


def test_pending_request_budget_and_timeout_leave_file_untouched(pair):
    ws,b,c=pair
    b.pending={str(i):{} for i in range(16)}
    with pytest.raises(Problem,match='busy'):b.guard('a.py')
    b.pending.clear()
    original=ws.text('a.py')
    with pytest.raises(Problem,match='confirm'):b.guard('a.py')
    assert ws.text('a.py')==original and not b.pending and not b.queue
