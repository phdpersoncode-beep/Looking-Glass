import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
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
        from looking_glass.projects import known_projects
        assert known_projects()==[dict(root=str(tmp_path),url=url)]
        thread=agent('create','notes.md','--quote','A passage','--body','A terminal-created thread.')
        agent('reply',str(thread['id']),'--body','A terminal reply.','--author','Altay')
        process.terminate();process.wait(timeout=5)
        process=start()
        persisted=agent('read',str(thread['id']))
        assert [m['body'] for m in persisted['messages']]==['A terminal-created thread.','A terminal reply.']
        assert agent('resolve',str(thread['id']))['resolved']
        assert not agent('reopen',str(thread['id']))['resolved']
        assert agent('list')['total']==1
        assert agent('delete',str(thread['id']),'--message',str(persisted['messages'][1]['id']))=={'deleted':True}
        assert len(agent('read',str(thread['id']))['messages'])==1
        assert agent('delete',str(thread['id']))=={'deleted':True}
        assert agent('list')['threads']==[]
    finally:
        process.terminate();process.wait(timeout=5)


def test_discovery_inference_search_and_instructions(tmp_path, monkeypatch):
    import threading
    from urllib.request import Request
    from werkzeug.serving import make_server
    from looking_glass.app import create_app
    from looking_glass.projects import register_project

    root=tmp_path/'project';root.mkdir()
    (root/'notes.md').write_text('Before\nA passage to discuss.\nAfter\n')
    child=root/'nested';child.mkdir()
    other=tmp_path/'other';other.mkdir()
    app=create_app(root)
    server=make_server('127.0.0.1',0,app,threaded=True)
    url=f'http://127.0.0.1:{server.server_port}'
    app.config['LOCAL_SERVER_URL']=url
    register_project(root,url)
    worker=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.02},daemon=True);worker.start()
    monkeypatch.chdir(child)

    def run(*args, ok=True):
        # Use an absolute executable script import path while testing another cwd.
        env=dict(os.environ)
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        result=subprocess.run([sys.executable,'-m','looking_glass.cli',*args],capture_output=True,text=True,env=env)
        assert (result.returncode==0)==ok,result.stderr
        return result

    def agent(*args):
        return json.loads(run('agent',*args).stdout)

    try:
        listing=json.loads(run('projects','list').stdout)
        assert listing==[dict(root=str(root),url=url,reachable=True)]
        first=agent('create','notes.md','--quote','A passage','--body','Explain SHEBANG','--author','Altay')
        second=agent('create','notes.md','--quote','After','--body','Other comment')
        agent('reply',str(first['id']),'--body','A reply with Unicode 🪞','--author','OpenCode')
        agent('resolve',str(second['id']))
        found=agent('search','shebang','--status','open','--author','altay','--path','notes.md')
        assert found['total']==1 and found['threads'][0]['id']==first['id']
        assert 'messages' not in found['threads'][0]
        assert agent('search','🪞','--full')['threads'][0]['messages'][-1]['author']=='OpenCode'
        assert agent('list','--status','resolved')['threads'][0]['id']==second['id']
        page=agent('list','--limit','1')
        assert page['total']==2 and page['next_offset']==1
        assert agent('list','--limit','1','--offset','1')['threads'][0]['id']==second['id']
        context=agent('read',str(first['id']),'--context-lines','0')['context']
        assert context['content']=='A passage to discuss.\n' and context['first_line']==2
        show=json.loads(run('projects','show').stdout)
        assert show['files']==['notes.md'] and show['thread_counts']==dict(all=2,open=1,resolved=1)
        instructions=run('agent','instructions').stdout
        assert 'looking-glass agent --root' in instructions and 'uv run' not in instructions
        assert 'search' in instructions and '--help' in instructions
        for args in [('list','--limit','0'),('read',str(first['id']),'--context-lines','-1')]:
            assert 'error' in run('agent',*args,ok=False).stderr
        assert 'HTTP loopback' in run('agent','--url','http://localhost:8765@evil.example:80','list',ok=False).stderr

        # Browser switching registers the new project. The old root cannot reach it.
        token=(root/'.looking-glass'/'token').read_text().strip()
        request=Request(url+'/api/workspace',data=json.dumps({'path':str(other)}).encode(),
                        headers={'X-Looking-Glass-Token':token,'Content-Type':'application/json'},method='POST')
        with urlopen(request) as response:
            assert json.load(response)['root']==str(other)
        listing=json.loads(run('projects','list').stdout)
        assert {p['root']:p['reachable'] for p in listing}=={str(root):False,str(other):True}
        # Even matching tokens must not allow routing to the wrong workspace.
        (root/'.looking-glass'/'token').write_text((other/'.looking-glass'/'token').read_text())
        assert 'different project' in run('agent','list',ok=False).stderr
        assert json.loads(run('projects','show',str(other)).stdout)['root']==str(other)
    finally:
        server.shutdown();worker.join(timeout=5);server.server_close()
    assert all(not p['reachable'] for p in json.loads(run('projects','list').stdout))


def test_every_command_has_help_and_examples(capsys):
    import pytest
    from looking_glass.cli import main
    commands=[[],['serve'],['projects'],['projects','list'],['projects','show'],['agent']]
    commands += [['agent',name] for name in ('list','search','read','create','reattach','reply','resolve','reopen','delete','instructions')]
    for command in commands:
        with pytest.raises(SystemExit) as error:
            main([*command,'--help'])
        assert error.value.code==0
        help=capsys.readouterr().out
        assert 'usage:' in help and ('Example:' in help or 'Start here:' in help)


def test_markdown_body_file_and_stdin(tmp_path):
    import threading
    from werkzeug.serving import make_server
    from looking_glass.app import create_app
    (tmp_path/'notes.md').write_text('A passage.\n')
    app=create_app(tmp_path);server=make_server('127.0.0.1',0,app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.02},daemon=True);worker.start()
    command=[sys.executable,'-m','looking_glass.cli','agent','--root',str(tmp_path),'--url',f'http://127.0.0.1:{server.server_port}']
    markdown='Use `width`, "quotes", $(do_not_execute), and 🪞.\n\n```python\nwidth = 12\n```'
    body=tmp_path/'reply.md';body.write_text(markdown,encoding='utf-8')
    def run(*args,input=None,ok=True):
        result=subprocess.run([*command,*args],input=input,capture_output=True,text=True)
        assert (result.returncode==0)==ok,result.stderr
        return json.loads(result.stdout) if ok else result.stderr
    try:
        first=run('create','notes.md','--quote','A passage','--body-file',str(body))
        assert first['messages'][0]['body']==markdown
        for args in [('--body-stdin',),('--body-file','-'),('--body',markdown)]:
            result=run('reply',str(first['id']),*args,input=markdown if args[0]!='--body' else None)
            assert result['messages'][-1]['body']==markdown
        assert run('create','notes.md','--quote','A passage','--body-stdin',input=markdown)['messages'][0]['body']==markdown
        assert 'not allowed' in run('reply',str(first['id']),'--body','x','--body-stdin',ok=False)
        assert 'No such file' in run('reply',str(first['id']),'--body-file',str(tmp_path/'missing'),ok=False)
        assert 'required' in run('reply',str(first['id']),ok=False)
        help=subprocess.run([*command,'reply','--help'],capture_output=True,text=True).stdout
        assert 'backticks' in help and '--body-file' in help and '--body-stdin' in help
    finally:
        server.shutdown();worker.join(timeout=5);server.server_close()


def test_agent_reattach_repairs_failed_and_wrong_anchors(tmp_path):
    import threading
    from werkzeug.serving import make_server
    from looking_glass.app import create_app
    from looking_glass.workspace import Workspace

    old = 'Before\nThe original reviewed passage.\nAfter\n'
    path = tmp_path / 'notes.md'; path.write_text(old, encoding='utf-8')
    app = create_app(tmp_path); ws = app.extensions['workspace']
    server = make_server('127.0.0.1', 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.02}, daemon=True); worker.start()
    command = [sys.executable, '-m', 'looking_glass.cli', 'agent', '--root', str(tmp_path),
               '--url', f'http://127.0.0.1:{server.server_port}']
    def run(*args, ok=True):
        result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=5)
        assert (result.returncode == 0) == ok, result.stderr
        return json.loads(result.stdout) if ok else result.stderr

    try:
        thread = run('create', 'notes.md', '--quote', 'The original reviewed passage.', '--body', 'Review')
        identifier = str(thread['id'])
        run('reply', identifier, '--body', 'Keep this conversation.')
        run('resolve', identifier)
        messages = run('read', identifier)['messages']
        replacement = '🪞 Intended replacement.\nSecond line.'
        new = 'Rewritten introduction\n' + replacement + '\nOther passage\n' + replacement + '\n'
        path.write_text(new, encoding='utf-8')
        assert run('read', identifier)['anchor_status'] == 'needs_reattachment'
        for quote in ('', 'Missing passage', replacement):
            assert 'Quote is empty, missing, or ambiguous' in run('reattach', identifier, '--quote', quote, ok=False)
            assert ws.get_thread(thread['id'])['anchor_status'] == 'needs_reattachment'
        for occurrence in ('0', '-1', '3'):
            assert 'Occurrence is out of range' in run('reattach', identifier, '--quote', replacement,
                                                      '--occurrence', occurrence, ok=False)
        repaired = run('reattach', identifier, '--quote', replacement, '--occurrence', '2')
        assert repaired['start'] == new.rindex(replacement) and repaired['quote'] == replacement
        assert repaired['anchor_status'] == 'attached' and repaired['resolved']
        assert repaired['messages'] == messages and repaired['origin'] == thread['origin']
        assert ws.origins.read(thread['id'])['content'] == old
        assert path.read_text(encoding='utf-8') == new
        # Correct an attached but unintended passage through the same command.
        corrected = run('reattach', identifier, '--quote', 'Other passage')
        assert corrected['start'] == new.index('Other passage') and corrected['resolved']
        assert corrected['messages'] == messages
        assert Workspace(tmp_path).get_thread(thread['id']) == corrected
        missing = run('reattach', '999', '--quote', 'Other passage', ok=False)
        assert 'Thread not found' in missing
        path.unlink()
        assert 'File no longer exists' in run('reattach', identifier, '--quote', 'Other passage', ok=False)

        (tmp_path / 'report.html').write_text('<p>Visible passage</p>')
        report = ws.read('report.html')
        rendered = ws.create_rendered_thread('report.html', dict(quote='Visible passage', prefix='', suffix=''),
                                            'Review', 'Agent', report['version'])
        assert 'Rendered HTML anchors require' in run('reattach', str(rendered['id']),
                                                     '--quote', 'Visible passage', ok=False)
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close()


def test_agent_reattach_rejects_a_file_change_between_read_and_patch(tmp_path, monkeypatch, capsys):
    import threading
    import pytest
    from werkzeug.serving import make_server
    from looking_glass.app import create_app
    from looking_glass import cli

    path = tmp_path / 'notes.md'; path.write_text('The original passage.\nA replacement passage.')
    app = create_app(tmp_path); ws = app.extensions['workspace']
    source = ws.read('notes.md')
    thread = ws.create_thread('notes.md', 0, 21, 'Review', 'Agent', source['version'])
    server = make_server('127.0.0.1', 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.02}, daemon=True); worker.start()
    original = cli.api
    def racing_api(root, url, route, *args, **kwargs):
        result = original(root, url, route, *args, **kwargs)
        if route.startswith('file?'):
            path.write_text('A newer, unrelated document.')
        return result
    monkeypatch.setattr(cli, 'api', racing_api)
    try:
        with pytest.raises(SystemExit) as error:
            cli.main(['agent', '--root', str(tmp_path), '--url', f'http://127.0.0.1:{server.server_port}',
                      'reattach', str(thread['id']), '--quote', 'A replacement passage.'])
        assert error.value.code == 1 and 'Selection is stale' in capsys.readouterr().err
        final = ws.get_thread(thread['id'])
        assert final['quote'] == thread['quote'] and final['anchor_status'] == 'needs_reattachment'
    finally:
        server.shutdown(); worker.join(timeout=5); server.server_close()
