"""Launch the packaged extension in a real code-server extension host and Chromium.

LG_CODE_SERVER=/path/to/bin/code-server .venv/bin/python vs_code_extension/test/run_host.py
No production workspace is changed. Uses only disposable directories and loopback.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from looking_glass.app import create_app
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright


def main():
    binary=os.environ['LG_CODE_SERVER']
    with tempfile.TemporaryDirectory(prefix='lg-host-') as temporary:
        base=Path(temporary);root=base/'project';root.mkdir()
        (root/'main.py').write_text('def value():\n    return 1\n\nvalue()\n')
        (root/'native.js').write_text('function hello() { return 1; }\nhello();\n')
        app=create_app(root);server=make_server('127.0.0.1',0,app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        config=root/'.vscode';config.mkdir();(config/'settings.json').write_text(json.dumps({'lookingGlass.serverUrl':f'http://127.0.0.1:{server.server_port}','files.autoSave':'off','workbench.startupEditor':'none','extensions.autoUpdate':False,'lookingGlass.testPythonProvider':bool(os.environ.get('LG_PYTHON_VSIX'))}))
        extensions=base/'extensions';extensions.mkdir()
        if os.environ.get('LG_PYTHON_VSIX'):
            subprocess.run([binary,'--user-data-dir',str(base/'data'),'--extensions-dir',str(extensions),'--install-extension',os.environ['LG_PYTHON_VSIX']],check=True)
        subprocess.run([binary,'--user-data-dir',str(base/'data'),'--extensions-dir',str(extensions),'--install-extension',str(ROOT/'looking-glass-companion-0.1.0.vsix')],check=True)
        driver=base/'host-tests.vsix'
        with zipfile.ZipFile(ROOT/'looking-glass-companion-0.1.0.vsix') as source, zipfile.ZipFile(driver,'w') as target:
            target.writestr('[Content_Types].xml',source.read('[Content_Types].xml'))
            target.writestr('extension.vsixmanifest',source.read('extension.vsixmanifest').decode().replace('looking-glass-companion','looking-glass-host-tests').replace('0.1.0','0.0.1'))
            for name in ['package.json','runner.cjs']:target.writestr('extension/'+name,(ROOT/'test/host'/name).read_bytes())
        subprocess.run([binary,'--user-data-dir',str(base/'data'),'--extensions-dir',str(extensions),'--install-extension',str(driver)],check=True)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        log=(base/'server.log').open('w+')
        process=subprocess.Popen([binary,'--bind-addr',f'127.0.0.1:{port}','--auth','none','--user-data-dir',str(base/'data'),'--extensions-dir',str(extensions),'--disable-workspace-trust','--disable-telemetry','--disable-update-check',str(root)],stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+30
            while True:
                try:urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1);break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('code-server startup failed')
                    time.sleep(.1)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('LOOKING_GLASS_BROWSER','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                page=browser.new_page();page.goto(f'http://127.0.0.1:{port}/?folder={root}')
                result=root/'.looking-glass/host-result.json'
                deadline=time.monotonic()+90
                while not result.exists() and time.monotonic()<deadline:page.wait_for_timeout(100)
                if not result.exists():
                    page.screenshot(path='/tmp/looking-glass-host-failure.png')
                    for file in (base/'data/logs').rglob('*.log'):
                        print(file, file.read_text(errors='replace')[-8000:])
                    raise RuntimeError('Extension-host suite timed out; screenshot /tmp/looking-glass-host-failure.png')
                report=json.loads(result.read_text());print(json.dumps(report,indent=2))
                assert not report.get('error'),report.get('error')
                browser.close()
        finally:
            process.terminate();process.wait(timeout=10);server.shutdown();log.seek(0)
            if process.returncode not in (0,-15):print(log.read()[-8000:])

if __name__=='__main__':main()
