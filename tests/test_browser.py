"""Opt-in browser integration, entirely on a disposable demo_dir copy.

LOOKING_GLASS_BROWSER=/path/to/chromium pytest tests/test_browser.py -v
Or LOOKING_GLASS_BROWSER=installed after `playwright install chromium`.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server
from looking_glass.app import create_app

pytestmark = pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER to run the browser workflow')


def test_end_to_end(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    project = Path(__file__).resolve().parents[1]
    root = tmp_path/'demo_dir'
    shutil.copytree(project/'demo_dir',root,ignore=shutil.ignore_patterns('.looking-glass'))
    (root/'_crlf.txt').write_bytes('First line\r\n🪞 München\r\n'.encode())
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    for key,value in [('user.name','Looking Glass Test'),('user.email','test@example.invalid')]:
        subprocess.run(['git','-C',str(root),'config',key,value],check=True)
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    subprocess.run(['git','-C',str(root),'commit','-m','demo baseline'],check=True,capture_output=True)

    def start(port=0):
        server=make_server('127.0.0.1',port,create_app(root),threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        return server,thread

    server,thread=start()
    url=f'http://127.0.0.1:{server.server_port}'

    def agent(*args):
        p=subprocess.run([sys.executable,'-m','looking_glass.cli','agent','--root',str(root),'--url',url,*args],capture_output=True,text=True)
        assert p.returncode==0,p.stderr
        return json.loads(p.stdout)

    with sync_playwright() as pw:
        executable=os.environ['LOOKING_GLASS_BROWSER']
        browser=pw.chromium.launch(executable_path=None if executable=='installed' else executable,
                                   headless=True,args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':960})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url)

        def open_file(path):
            page.locator(f'.file-entry[data-path="{path}"]').click()
            expect(page.locator('#document-name')).to_have_text(path)

        def select_passage(quote):
            page.locator('.cm-content').click()
            page.keyboard.press('Control+f')
            page.get_by_role('textbox',name='Find',exact=True).fill(quote)
            page.get_by_role('button',name='next',exact=True).click()
            page.keyboard.press('Escape')

        open_file('welcome.md')
        assert page.locator('.md-heading').count()>0
        page.locator('#mode').select_option('source')
        original=(root/'welcome.md').read_text()
        page.locator('.cm-content').click()
        page.keyboard.press('Control+a')
        page.keyboard.insert_text(original+'\nAn edited ending.\n')
        assert 'Unsaved' in page.locator('#dirty').inner_text()
        page.keyboard.press('Control+z')
        page.keyboard.press('Control+Shift+z')
        page.keyboard.press('Control+s')
        expect(page.locator('#dirty')).to_have_text('')
        assert 'An edited ending.' in (root/'welcome.md').read_text()

        select_passage('Select this passage')
        page.locator('#annotate').click()
        page.locator('#comment-body').fill('Does this passage explain the review workflow clearly?')
        page.get_by_role('button',name='Start thread',exact=True).click()
        page.locator('.thread').wait_for()
        assert page.locator('.passage-highlight').count()>0
        id=int(page.locator('.thread').get_attribute('data-thread'))
        reply=agent('reply',str(id),'--body','Yes. I would add a concrete example.','--author','Codex')
        assert len(reply['messages'])==2
        page.get_by_text('Yes. I would add a concrete example.',exact=True).wait_for()
        page.locator('.reply-form textarea').fill('Add the example in the next editing pass.')
        page.locator('.reply-form button').click()
        page.get_by_text('Add the example in the next editing pass.',exact=True).wait_for()
        assert len(agent('read',str(id))['messages'])==3
        page.locator('#next').click()
        page.locator('#previous').click()
        page.locator('.thread [data-action=resolve]').click()
        expect(page.locator('#thread-count')).to_have_text('0')
        agent('reopen',str(id))
        expect(page.locator('#thread-count')).to_have_text('1')

        # Verify ordinary code editing, keyboard search/replace and agent creation.
        open_file('example.py')
        page.locator('.cm-content').click()
        page.keyboard.press('Control+h')
        page.get_by_role('textbox',name='Find',exact=True).fill('box_volume')
        page.get_by_role('textbox',name='Replace',exact=True).fill('solid_volume')
        page.get_by_role('button',name='replace all',exact=True).click()
        page.keyboard.press('Escape')
        page.keyboard.press('Control+s')
        expect(page.locator('#dirty')).to_have_text('')
        assert 'solid_volume' in (root/'example.py').read_text()
        t=agent('create','example.py','--quote','return width * height * depth','--body','Validate positive dimensions first.')
        page.get_by_text('Validate positive dimensions first.',exact=True).wait_for()
        assert t['messages'][0]['author']=='Codex'

        open_file('_crlf.txt')
        page.locator('.cm-content').click()
        page.keyboard.press('Control+End')
        page.keyboard.insert_text('Last line.')
        page.keyboard.press('Control+s')
        expect(page.locator('#dirty')).to_have_text('')
        raw=(root/'_crlf.txt').read_bytes()
        assert b'\r\n' in raw and b'\n' not in raw.replace(b'\r\n',b'')
        unicode_thread=agent('create','_crlf.txt','--quote','🪞 München','--body','Check the Unicode anchor.')
        page.get_by_text('Check the Unicode anchor.',exact=True).wait_for()
        assert unicode_thread['quote']=='🪞 München'
        assert page.locator('.passage-highlight').inner_text()=='🪞 München'

        # A clean external edit reloads; a dirty external edit enters a conflict.
        open_file('notes.txt')
        (root/'notes.txt').write_text('External clean update.\n')
        page.get_by_text('External clean update.',exact=False).wait_for()
        page.locator('.cm-content').click()
        page.keyboard.press('Control+End')
        page.keyboard.insert_text('My unsaved draft.\n')
        (root/'notes.txt').write_text('Second external update.\n')
        page.locator('#conflict').wait_for(state='visible')
        assert 'My unsaved draft.' in page.locator('.cm-content').inner_text()
        page.locator('#merge-disk').click()
        page.locator('#merge-text').fill('Second external update.\nMy merged draft.\n')
        page.locator('#accept-merge').click()
        page.locator('#save').click()
        expect(page.locator('#dirty')).to_have_text('')
        assert (root/'notes.txt').read_text()=='Second external update.\nMy merged draft.\n'

        open_file('records.jsonl')
        page.locator('.jsonl-row[data-row="2"]').click()
        assert 'MALFORMED' in page.locator('.jsonl-detail .viewer-heading').inner_text()
        page.locator('.jsonl-row[data-row="1"]').click()
        assert 'check boundary' in page.locator('.json-detail-editor').inner_text()
        for name in ('tetrahedron-ascii.stl','tetrahedron-binary.stl'):
            open_file(name)
            page.get_by_text('4 triangles',exact=True).wait_for()
            page.locator('.stl-tools button').click()
            box=page.locator('.stl-view canvas').bounding_box()
            page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
            page.mouse.down();page.mouse.move(box['x']+box['width']/2+60,box['y']+box['height']/2+20);page.mouse.up();page.mouse.wheel(0,100)

        open_file('report.html')
        frame=page.frame_locator('#html-preview')
        frame.get_by_role('button',name='Run check').click()
        assert frame.locator('#result').inner_text()=='Checks run: 1'
        assert frame.locator('#isolation').inner_text()=='Parent application state is isolated.'
        page.locator('#mode').select_option('source')
        select_passage('A report with a working interaction.')
        page.locator('#annotate').click()
        page.locator('#comment-body').fill('HTML source is commentable.')
        page.get_by_role('button',name='Start thread',exact=True).click()
        page.get_by_text('HTML source is commentable.',exact=True).wait_for()

        # UI checkpoint includes selected saved files only.
        page.locator('#git-open').click()
        page.locator('#git-files input[value="notes.txt"]').check()
        page.locator('#inspect-diff').click()
        page.get_by_text('+My merged draft.',exact=False).wait_for()
        page.locator('#checkpoint-name').fill('Merge reviewed notes')
        page.locator('#checkpoint').click()
        page.locator('#git-dialog').wait_for(state='hidden')
        committed=subprocess.check_output(['git','-C',str(root),'show','--pretty=','--name-only','HEAD'],text=True).strip()
        assert committed=='notes.txt'

        # Restart the process state and reload persisted discussions.
        port=server.server_port
        server.shutdown();thread.join();server.server_close()
        server,thread=start(port)
        page.reload()
        open_file('welcome.md')
        page.get_by_text('Does this passage explain the review workflow clearly?',exact=True).wait_for()
        assert len(agent('read',str(id))['messages'])==3
        page.locator('#mode').select_option('live')
        page.locator('#next').click()
        page.locator('#editor').click(position={'x':300,'y':450})
        family=page.locator('#editor .cm-scroller').evaluate('(el)=>getComputedStyle(el).fontFamily')
        assert 'Times New Roman' in family
        page.locator('.tab[data-path="example.py"] button[title="Pin tab"]').click()
        page.locator('.tab[data-path="welcome.md"]').click(button='right')
        page.get_by_role('button',name='Close other tabs',exact=True).click()
        expect(page.locator('.tab')).to_have_count(2)
        page.locator('.tab[data-path="example.py"] button[title="Close tab"]').click()
        expect(page.locator('.tab')).to_have_count(1)
        screenshots=project/'test-results'
        screenshots.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshots/'looking-glass-light.png'))
        page.locator('#theme').click()
        page.screenshot(path=str(screenshots/'looking-glass-dark.png'))
        assert not errors, errors
        browser.close()
    server.shutdown();thread.join();server.server_close()
