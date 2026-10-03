import json
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def test_agent_threads_survive_a_real_process_restart(tmp_path):
    (tmp_path/'notes.md').write_text('A passage to discuss.\n')
    with socket.socket() as socket_handle:
        socket_handle.bind(('127.0.0.1',0))
        port=socket_handle.getsockname()[1]
    url=f'http://127.0.0.1:{port}'

    def start():
        process=subprocess.Popen([sys.executable,'-m','looking_glass.cli','serve',str(tmp_path),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            try:
                with urlopen(url,timeout=1) as response:
                    assert response.status==200
                return process
            except (URLError,TimeoutError):
                if process.poll() is not None:
                    raise AssertionError('Server exited before becoming ready')
                time.sleep(.05)
        process.terminate()
        raise AssertionError('Server did not become ready')

    def agent(*args):
        p=subprocess.run([sys.executable,'-m','looking_glass.cli','agent','--root',str(tmp_path),'--url',url,*args],capture_output=True,text=True)
        assert p.returncode==0,p.stderr
        return json.loads(p.stdout)

    process=start()
    try:
        thread=agent('create','notes.md','--quote','A passage','--body','A terminal-created thread.')
        agent('reply',str(thread['id']),'--body','A terminal reply.','--author','Altay')
        process.terminate();process.wait(timeout=5)
        process=start()
        persisted=agent('read',str(thread['id']))
        assert [m['body'] for m in persisted['messages']]==['A terminal-created thread.','A terminal reply.']
        assert agent('resolve',str(thread['id']))['resolved']
        assert not agent('reopen',str(thread['id']))['resolved']
        assert len(agent('list'))==1
    finally:
        process.terminate();process.wait(timeout=5)
