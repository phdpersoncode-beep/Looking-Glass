"""Browser regressions for the viewer and review improvements."""
import os
import threading
import pytest
from werkzeug.serving import make_server
from looking_glass.app import create_app
pytestmark=pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER for browser checks')

@pytest.fixture
def workspace_page(tmp_path, request):
    from playwright.sync_api import sync_playwright
    app=create_app(tmp_path)
    server=make_server('127.0.0.1',0,app,threaded=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as pw:
            executable=os.environ['LOOKING_GLASS_BROWSER']
            engine=getattr(request,'param','chromium')
            browser=getattr(pw,engine).launch(executable_path=None if engine!='chromium' or executable=='installed' else executable,headless=not bool(os.environ.get('LOOKING_GLASS_HEADED')),args=['--no-sandbox'] if engine=='chromium' else [])
            context=browser.new_context(viewport={'width':1440,'height':960})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            yield tmp_path,page,f'http://127.0.0.1:{server.server_port}',app.extensions['workspace']
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();worker.join(timeout=5);server.server_close()

def open_file(page,name):
    from playwright.sync_api import expect
    page.locator(f'.file-entry[data-path="{name}"]').click()
    expect(page.locator('#document-name')).to_have_text(name)

def test_markdown_tables(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    original='# Report\n\n| Name | Value |\n| :--- | ---: |\n| **width** | `12` |\n\nEnding.\n'
    (root/'table.md').write_text(original)
    page.goto(url);open_file(page,'table.md')
    expect(page.locator('.md-table th')).to_have_text(['Name','Value'])
    expect(page.locator('.md-table strong')).to_have_text('width')
    expect(page.locator('.md-table code')).to_have_text('12')
    assert page.locator('.md-table td').last.evaluate('el=>getComputedStyle(el).textAlign').endswith('right')
    page.locator('.md-table td').first.click()
    expect(page.locator('.md-table')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('| Name | Value |')
    page.keyboard.press('Control+End');expect(page.locator('.md-table table')).to_be_visible()
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-preview table')).to_be_visible()
    page.locator('#mode').select_option('source');expect(page.locator('.md-table')).to_have_count(0)
    assert (root/'table.md').read_text()==original

def test_json_folding(workspace_page):
    import json
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    data={'first':{'nested':[1,2]},'second':{'value':3}}
    original=json.dumps(data,indent=2)
    (root/'data.json').write_text(original)
    (root/'rows.jsonl').write_text(json.dumps(data)+'\n{"other":[4,5]}\ninvalid\n')
    page.goto(url)
    for name in ('data.json','rows.jsonl'):
        open_file(page,name)
        page.get_by_role('button',name='Collapse all',exact=True).click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(1)
        page.locator('.cm-foldPlaceholder').first.click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(2)
        expect(page.locator('.cm-content')).not_to_contain_text('nested')
        page.locator('.cm-foldPlaceholder').first.click()
        expect(page.locator('.cm-content')).to_contain_text('nested')
        expect(page.locator('.cm-content')).not_to_contain_text('value')
        page.get_by_role('button',name='Expand all',exact=True).click()
        expect(page.locator('.cm-foldPlaceholder')).to_have_count(0)
        expect(page.locator('.cm-content')).to_contain_text('value')
    page.locator('.jsonl-row[data-row="1"]').click();expect(page.locator('.cm-content')).to_contain_text('other')
    page.locator('.jsonl-row[data-row="2"]').click();expect(page.locator('.jsonl-detail .viewer-heading')).to_contain_text('MALFORMED')
    assert (root/'data.json').read_text()==original

def test_images_and_zoom(workspace_page):
    import base64
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    for name,mime in [('image.png','image/png'),('image.jpeg','image/jpeg')]:
        encoded=page.evaluate('''mime=>{const c=document.createElement('canvas');c.width=800;c.height=600;const x=c.getContext('2d');x.fillStyle='#9935ee';x.fillRect(0,0,800,600);return c.toDataURL(mime).split(',')[1];}''',mime)
        (root/name).write_bytes(base64.b64decode(encoded))
    (root/'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><script>parent.svgExecuted=true</script><rect width="800" height="600" fill="purple"/></svg>')
    (root/'broken.png').write_text('not an image')
    page.goto(url)
    for name in ('image.png','image.jpeg','image.svg'):
        open_file(page,name);expect(page.locator('.image-tools span')).to_contain_text('800 × 600')
        image=page.locator('.image-stage img')
        assert image.evaluate('el=>el.complete && el.naturalWidth')==800
        before=image.bounding_box()['width']
        page.get_by_role('button',name='Zoom in',exact=True).click();assert image.bounding_box()['width']>before
        page.get_by_role('button',name='Zoom out',exact=True).click()
        page.get_by_role('button',name='Actual size',exact=True).click();assert image.bounding_box()['width']==800
        image.hover();page.mouse.wheel(0,-300)
        page.wait_for_function('document.querySelector(".image-stage img").getBoundingClientRect().width>800')
        page.get_by_role('button',name='Fit to view',exact=True).click()
        assert image.bounding_box()['width']<=page.locator('.image-viewport').bounding_box()['width']
        expect(page.locator('#save')).to_be_disabled()
    page.reload();expect(page.locator('.image-tools span')).to_contain_text('800 × 600')
    assert page.evaluate('window.svgExecuted') is None
    open_file(page,'broken.png');expect(page.locator('.image-status')).to_contain_text('Unable to display this image')

def test_cross_file_comments(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'a.md').write_text('Alpha passage.\n');(root/'b.py').write_text('beta = 2\n');(root/'report.html').write_text('<p>Rendered passage.</p>')
    first=ws.create_thread('a.md',0,5,'First discussion.','Altay',ws.read('a.md')['version'])
    second=ws.create_thread('b.py',0,4,'Second discussion.','Agent',ws.read('b.py')['version'])
    ws.create_rendered_thread('report.html',{'quote':'Rendered passage.','prefix':'','suffix':''},'HTML discussion.','Agent',ws.read('report.html')['version'])
    page.goto(url);open_file(page,'a.md');expect(page.locator('.thread')).to_have_count(1)
    page.locator('#thread-scope').check();expect(page.locator('.thread')).to_have_count(3)
    expect(page.locator('.thread-file')).to_have_text(['a.md','b.py','report.html'])
    page.locator('#next').click();expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(first['id']))
    page.locator('#next').click();expect(page.locator('#document-name')).to_have_text('b.py')
    expect(page.locator('.focused-highlight')).to_have_text('beta')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(second['id']))
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('# draft')
    page.locator('#next').click();expect(page.locator('#document-name')).to_have_text('report.html')
    expect(page.frame_locator('#html-preview').locator('p')).to_have_text('Rendered passage.')
    page.locator('#previous').click();expect(page.locator('#document-name')).to_have_text('b.py')
    expect(page.locator('.cm-content')).to_contain_text('# draft')
    page.locator('.thread.active [data-action="resolve"]').click();expect(page.locator('#thread-count')).to_have_text('2')
    page.locator('#show-resolved').check();expect(page.locator('.thread.resolved')).to_be_visible()
    page.locator('#thread-scope').uncheck();expect(page.locator('.thread')).to_have_count(1)
    expect(page.locator('.thread-file')).to_have_count(0)

def test_resizable_file_explorer(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'note.txt').write_text('Example.');page.goto(url)
    separator=page.get_by_role('separator',name='Resize file explorer');box=separator.bounding_box()
    page.mouse.move(box['x']+box['width']/2,box['y']+100);page.mouse.down();page.mouse.move(360,box['y']+100);page.mouse.up()
    assert abs(page.locator('.file-sidebar').bounding_box()['width']-360)<2
    assert page.locator('.document-panel').bounding_box()['width']>=350
    page.reload();expect(separator).to_have_attribute('aria-valuenow','360')
    separator.focus();page.keyboard.press('ArrowRight');expect(separator).to_have_attribute('aria-valuenow','370')
    page.keyboard.press('Home');expect(separator).to_have_attribute('aria-valuenow','120')
    page.keyboard.press('End');expect(separator).to_have_attribute('aria-valuenow','600')
    assert page.locator('.document-panel').bounding_box()['width']>=350

def test_newsreader_is_local(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'note.md').write_text('A clean writing font.\n\n*İstanbul and München.*\n')
    page.goto(url);open_file(page,'note.md')
    fonts=page.evaluate('''async()=>{const normal=await document.fonts.load('18px Newsreader','İstanbul München');const italic=await document.fonts.load('italic 18px Newsreader','İstanbul München');return [...normal,...italic].map(f=>f.status);}''')
    assert fonts and all(status=='loaded' for status in fonts)
    assert 'Newsreader' in page.locator('.cm-scroller').evaluate('el=>getComputedStyle(el).fontFamily')
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-preview em')).to_have_text('İstanbul and München.')
    assert 'Newsreader' in page.locator('.markdown-preview').evaluate('el=>getComputedStyle(el).fontFamily')
    urls=page.evaluate('performance.getEntriesByType("resource").filter(r=>r.name.endsWith(".woff2")).map(r=>r.name)')
    assert urls and all(resource.startswith(url+'/static/newsreader-') for resource in urls)

def test_html_and_jsonl_downloads(workspace_page):
    from pathlib import Path
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    html='<html><body><button onclick="this.textContent=\'It works\'">Run</button></body></html>'
    jsonl='{"text":"München", "literal":"`width`"}\ninvalid\n'
    (root/'report.html').write_text(html);(root/'rows.jsonl').write_text(jsonl);(root/'note.txt').write_text('Plain text.')
    page.goto(url)
    for name,content in [('report.html',html),('rows.jsonl',jsonl)]:
        open_file(page,name)
        with page.expect_download() as downloaded:page.locator('#download-file').click()
        download=downloaded.value
        assert download.suggested_filename==name
        assert Path(download.path()).read_bytes()==content.encode('utf-8')
        if name.endswith('.html'):
            local=root/'downloaded.html';download.save_as(local)
            viewer=page.context.new_page();viewer.goto(local.as_uri());viewer.get_by_role('button',name='Run').click()
            expect(viewer.get_by_role('button')).to_have_text('It works');viewer.close()
    open_file(page,'report.html');page.locator('#html-toggle').click()
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('<!-- unsaved draft -->')
    with page.expect_download() as downloaded:page.locator('#download-file').click()
    assert Path(downloaded.value.path()).read_text()==html+'<!-- unsaved draft -->'
    assert (root/'report.html').read_text()==html
    open_file(page,'note.txt');expect(page.locator('#download-file')).not_to_be_visible()

def test_gitignored_files_have_no_gutter(workspace_page):
    import subprocess
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'tracked.txt').write_text('Tracked.\n')
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(root),'add','tracked.txt'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','Initial'],check=True,capture_output=True)
    (root/'.gitignore').write_text('*.txt\n');(root/'ignored.txt').write_text('Ignored.\n')
    (root/'new.py').write_text('value = 1\n');(root/'tracked.txt').write_text('Modified.\n')
    page.goto(url);open_file(page,'ignored.txt');expect(page.locator('.git-gutter')).to_have_count(0)
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('New draft.')
    expect(page.locator('.git-marker.added')).to_have_count(0)
    open_file(page,'new.py');expect(page.locator('.git-marker.added').first).to_be_visible()
    open_file(page,'tracked.txt');expect(page.locator('.git-marker.changed').first).to_be_visible()
    (root/'.gitignore').write_text('*.txt\nnew.py\n')
    open_file(page,'new.py');expect(page.locator('.git-gutter')).to_have_count(0)


def test_ctrl_p_in_rendered_html(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'report.html').write_text("""<p>Focus here</p><input aria-label="Report input"><script>
window.printed=false;window.prevented=false;
window.addEventListener('beforeprint',()=>window.printed=true);
document.addEventListener('keydown',event=>{if(event.key.toLowerCase()==='p')setTimeout(()=>window.prevented=event.defaultPrevented,0);},true);
</script>""")
    (root/'note.md').write_text('A note.\n')
    page.goto(url)
    for key in ('Control+p','Meta+p'):
        open_file(page,'report.html')
        frame=page.frame_locator('#html-preview')
        frame.get_by_role('textbox',name='Report input').click()
        page.keyboard.press(key)
        expect(page.locator('#quick-dialog')).to_be_visible()
        assert frame.locator('body').evaluate('()=>window.prevented')
        assert not frame.locator('body').evaluate('()=>window.printed')
        page.locator('#quick-query').fill('note');page.keyboard.press('Enter')
        expect(page.locator('#document-name')).to_have_text('note.md')
        expect(page.locator('#quick-dialog')).not_to_be_visible()


def test_fenced_markdown_highlighting(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    original='# Code\n\n```python\ndef volume(width):\n    return width * 12\n```\n\n```bash\nif true; then\n  echo "hello"\nfi\n```\n\n```unknown\n<script>window.codeExecuted=true</script>\n```\n\nEnding.\n'
    (root/'code.md').write_text(original)
    page.goto(url);open_file(page,'code.md')
    expect(page.locator('.cm-content')).not_to_contain_text('python')
    expect(page.locator('.cm-content')).not_to_contain_text('bash')
    expect(page.locator('.md-code-block').first).to_be_visible()
    for word in ('def','return','if'):
        page.wait_for_function("""word=>[...document.querySelectorAll('.cm-line span')].some(s=>s.textContent===word&&getComputedStyle(s).color==='rgb(173, 93, 237)')""",arg=word)
    page.locator('#mode').select_option('source')
    expect(page.locator('.cm-content')).to_contain_text('```python')
    page.locator('#mode').select_option('preview')
    expect(page.locator('.language-python .tok-keyword')).to_have_text(['def','return'])
    expect(page.locator('.language-bash .tok-keyword').first).to_have_text('if')
    expect(page.locator('.language-unknown')).to_have_text('<script>window.codeExecuted=true</script>\n')
    assert page.evaluate('window.codeExecuted') is None
    assert (root/'code.md').read_text()==original


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('event_delivery',['normal','mouse-only','missed-release'])
def test_linux_text_selection(workspace_page,event_delivery):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'note.md').write_text('# Heading\n\nAlpha **bold words** and ordinary words.\n\nSecond paragraph with München and 🪞.\n')
    (root/'note.txt').write_text('Alpha bold words and ordinary words.\nSecond paragraph with München and 🪞.\n')
    # Exercise mouse-only delivery and a release lost outside the window. These
    # must not leave live formatting frozen or the annotation controls hidden.
    blocked=['pointerdown','pointerup'] if event_delivery=='mouse-only' else ['pointerup','mouseup'] if event_delivery=='missed-release' else []
    import json
    page.add_init_script('for(const type of '+json.dumps(blocked)+'){window.addEventListener(type,event=>event.stopImmediatePropagation(),true);}')
    page.goto(url)
    for path in ('note.md','note.txt'):
        open_file(page,path)
        for end,reverse in [('ordinary words.',False),('ordinary words.',True),('München and 🪞.',False)]:
            page.keyboard.press('ArrowRight')
            page.wait_for_timeout(550)  # A new drag, not a double-click.
            points=page.locator('.cm-content').evaluate("""(el,end)=>{
                function caret(quote,end){
                    const line=[...el.querySelectorAll('.cm-line')].find(line=>line.textContent.includes(quote));
                    let offset=line.textContent.indexOf(quote)+(end?quote.length:0);
                    const walker=document.createTreeWalker(line,NodeFilter.SHOW_TEXT);
                    while(walker.nextNode()){
                        const node=walker.currentNode;
                        if(offset<node.length||(end&&offset===node.length)){
                            const range=document.createRange();range.setStart(node,offset);range.collapse(true);
                            const rect=range.getBoundingClientRect();return {x:rect.x+(end?-1:1),y:rect.y+rect.height/2};
                        }
                        offset-=node.length;
                    }
                    throw new Error('Caret not found');
                }
                return [caret('Alpha',false),caret(end,true)];
            }""",end)
            if reverse:points.reverse()
            page.mouse.move(**points[0]);page.mouse.down();page.mouse.move(**points[1],steps=20);page.mouse.up()
            page.mouse.move(points[1]['x']+1,points[1]['y'])
            expect(page.locator('#selection-tools')).to_be_visible()
            page.locator('#selection-comment').click()
            expected='Alpha **bold words** and ordinary words.' if path.endswith('.md') else 'Alpha bold words and ordinary words.'
            if end.startswith('München'):
                expected+=('\n\n' if path.endswith('.md') else '\n')+'Second paragraph with München and 🪞.'
            expect(page.locator('#selected-quote')).to_have_text(expected)
            expect(page.locator('#comment-body')).to_be_focused()
            page.locator('#comment-body').fill('Selected on Linux.')
            page.keyboard.press('Control+Enter')
            expect(page.locator('#comment-dialog')).not_to_be_visible()
            expect(page.locator('.thread').last.locator('blockquote')).to_have_text(expected)

def test_thread_attachments(workspace_page):
    from playwright.sync_api import expect
    from pathlib import Path
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Discuss this.')
    f=ws.read('note.txt');t=ws.create_thread('note.txt',0,7,'Review','Tester',f['version'])
    page.goto(url);open_file(page,'note.txt')
    page.locator('.attach-files').set_input_files([{'name':'shape.svg','mimeType':'image/svg+xml','buffer':b'<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30"><rect width="30" height="30"/></svg>'},{'name':'model.stl','mimeType':'application/octet-stream','buffer':b'\x00mesh'}])
    expect(page.locator('.attachment')).to_have_count(2)
    page.get_by_role('button',name='Preview shape.svg').click()
    expect(page.locator('#attachment-image')).to_be_visible()
    assert page.locator('#attachment-image').evaluate('el=>el.naturalWidth')==30
    page.locator('#attachment-dialog [data-close]').click()
    page.once('dialog',lambda dialog:dialog.accept('renamed.stl'))
    page.get_by_role('button',name='Rename model.stl').click()
    expect(page.locator('.attachment').last).to_contain_text('renamed.stl')
    with page.expect_download() as download:page.get_by_role('button',name='renamed.stl',exact=True).click()
    assert download.value.suggested_filename=='renamed.stl'
    assert Path(download.value.path()).read_bytes()==b'\x00mesh'
    page.reload();open_file(page,'note.txt');expect(page.locator('.attachment')).to_have_count(2)


def test_json_formatter(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    source='{"x":9007199254740993,"items":[1,{"s":"hello"}]}'
    (root/'one.json').write_text(source);(root/'bad.json').write_text('{"bad":}')
    page.goto(url);open_file(page,'one.json');page.locator('#json-format').click()
    expect(page.locator('.cm-line')).to_have_count(10)
    expect(page.locator('.cm-content')).to_contain_text('9007199254740993')
    assert (root/'one.json').read_text()==source
    page.keyboard.press('Control+z');expect(page.locator('.cm-content')).to_have_text(source)
    open_file(page,'bad.json');page.locator('#json-format').click()
    expect(page.locator('#notice.error')).to_be_visible()
    expect(page.locator('.cm-content')).to_have_text('{"bad":}')


def test_global_thread_arrows_and_fixed_header(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    for name in ('a.txt','b.txt'):
        (root/name).write_text('Passage.');f=ws.read(name)
        for i in range(4):ws.create_thread(name,0,7,'Long review. '*50,'Tester',f['version'])
    page.goto(url);open_file(page,'a.txt')
    expect(page.get_by_role('switch',name='Across files')).not_to_be_checked()
    initial=page.locator('#next').bounding_box()
    for _ in range(5):page.locator('#next').click()
    expect(page.locator('#document-name')).to_have_text('b.txt')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread','5')
    assert page.locator('#next').bounding_box()['y']==initial['y']
    expect(page.locator('.thread')).to_have_count(4)
    page.locator('#previous').click();expect(page.locator('#document-name')).to_have_text('a.txt')
    page.get_by_role('switch',name='Across files').check();expect(page.locator('.thread')).to_have_count(8)


def test_discussion_resizer(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    page.goto(url)
    separator=page.get_by_role('separator',name='Resize discussions');box=separator.bounding_box()
    page.mouse.move(box['x']+3,box['y']+100);page.mouse.down();page.mouse.move(1000,box['y']+100);page.mouse.up()
    assert abs(page.locator('.discussion-sidebar').bounding_box()['width']-440)<2
    assert page.locator('.document-panel').bounding_box()['width']>=350
    page.reload();expect(separator).to_have_attribute('aria-valuenow','440')
    separator.focus();page.keyboard.press('ArrowLeft');expect(separator).to_have_attribute('aria-valuenow','450')
    page.keyboard.press('Home');expect(separator).to_have_attribute('aria-valuenow','220')
    page.set_viewport_size({'width':1000,'height':800});page.keyboard.press('End')
    assert page.locator('.document-panel').bounding_box()['width']>=300


def test_thread_collapse_controls(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Passage.')
    f=ws.read('note.txt')
    for i in range(3):ws.create_thread('note.txt',0,7,'Comment '+str(i),'Tester',f['version'])
    page.goto(url);open_file(page,'note.txt')
    page.get_by_role('button',name='Collapse thread 1',exact=True).click()
    expect(page.locator('.thread[data-thread="1"] .thread-body')).not_to_be_visible()
    page.get_by_role('button',name='Expand thread 1',exact=True).click()
    expect(page.locator('.thread[data-thread="1"] .thread-body')).to_be_visible()
    page.get_by_role('button',name='Collapse all threads',exact=True).click()
    expect(page.locator('.thread.collapsed')).to_have_count(3)
    page.reload();expect(page.locator('.thread.collapsed')).to_have_count(3)
    page.get_by_role('button',name='Expand all threads',exact=True).click()
    expect(page.locator('.thread.collapsed')).to_have_count(0)
    page.get_by_role('button',name='Collapse all threads',exact=True).click()
    page.locator('#next').click();expect(page.locator('.thread.active .thread-body')).to_be_visible()
