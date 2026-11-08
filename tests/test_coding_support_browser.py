"""Source comment review and real Python navigation preserve ordinary editor state."""
import json
import os
import re

import pytest

from test_requested_features import workspace_page, open_file
from test_spotlight_navigation_browser import settle

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def replace_source(page, source):
    page.locator('.cm-content').click()
    page.keyboard.press('Control+Home'); page.keyboard.press('Control+Shift+End')
    page.keyboard.insert_text(source)


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_markdown_marker_tracking_filter_navigation_reply_and_restart(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws = workspace_page
    content = '# TODO first\n\n#TODO second\n\n# NOTE third\n\n#NOTE fourth\n'
    (root/'notes.md').write_text(content)
    manual = ws.create_thread('notes.md', 2, 12, 'Ordinary feedback', 'User', ws.read('notes.md')['version'])
    page.goto(url); open_file(page, 'notes.md')
    expect(page.locator('.thread')).to_have_count(1)
    track = page.get_by_role('button', name='Track TODO / NOTE', exact=True)
    track.click(); expect(track).to_have_attribute('aria-pressed','true')
    expect(page.locator('.source-marker-flag')).to_have_text(['⚑ TODO','⚑ TODO','⚑ NOTE','⚑ NOTE'])
    page.get_by_role('button', name='Markers only', exact=True).click()
    expect(page.locator('.thread:not([hidden])')).to_have_count(4)
    assert page.locator(f'.thread[data-thread="{manual["id"]}"]').is_hidden()
    page.locator('#next').click()
    expect(page.locator('.thread.active .source-marker-flag')).to_have_text('⚑ TODO')
    page.locator('.thread.active .reply-form textarea').fill('Keep this reply draft')
    page.locator('#next').click(); expect(page.locator('.thread.active blockquote')).to_have_text('TODO second')
    page.locator('#previous').click()
    expect(page.locator('.thread.active .reply-form textarea')).to_have_value('Keep this reply draft')
    page.locator('#mode').select_option('preview')
    page.locator('#next').click(); expect(page.locator('.thread.active blockquote')).to_have_text('TODO second')
    expect(page.locator('.markdown-preview .focused-highlight')).to_be_visible()
    page.reload(); expect(page.locator('#document-name')).to_have_text('notes.md')
    expect(track).to_have_attribute('aria-pressed','true')
    expect(page.locator('.source-marker-flag')).to_have_count(4)
    assert (root/'notes.md').read_text() == content


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
@pytest.mark.parametrize('theme,width', [('light',1440),('dark',900)])
def test_source_marker_save_external_edits_pause_and_narrow_layout(workspace_page, theme, width):
    from playwright.sync_api import expect
    root,page,url,ws = workspace_page
    (root/'main.py').write_text('value = "#TODO literal"\n# TODO first\n#NOTE second\n')
    page.goto(url); open_file(page, 'main.py')
    if page.locator('html').get_attribute('data-theme') != theme: page.locator('#theme').click()
    page.set_viewport_size({'width':width,'height':800})
    page.get_by_role('button', name='Track TODO / NOTE', exact=True).click()
    expect(page.locator('.source-marker-flag')).to_have_count(2)
    controls = page.locator('.source-marker-controls'); settle(page)
    bounds=controls.bounding_box(); sidebar=page.locator('#discussion-sidebar').bounding_box()
    assert bounds['x']>=sidebar['x'] and bounds['x']+bounds['width']<=sidebar['x']+sidebar['width']+1
    replace_source(page, '#NOTE second\n#TODO added\n'); page.keyboard.press('Control+s')
    expect(page.locator('#dirty')).to_have_text('')
    page.get_by_role('button', name='Markers only', exact=True).click()
    expect(page.locator('.thread:not([hidden])')).to_have_count(2)
    page.locator('#show-resolved').check()
    expect(page.locator('.thread:not([hidden])')).to_have_count(3)
    expect(page.locator('.thread.resolved .anchor-warning')).to_contain_text('reattachment')
    (root/'main.py').write_text('#NOTE second\n#TODO added\n# NOTE external\n')
    expect(page.locator('.source-marker-flag')).to_have_count(4, timeout=10000)
    page.get_by_role('button', name='Track TODO / NOTE', exact=True).click()
    expect(page.locator('#track-source-markers')).to_have_attribute('aria-pressed','false')
    replace_source(page, '#NOTE second\n#TODO added\n# NOTE external\n#TODO paused\n')
    page.keyboard.press('Control+s'); expect(page.locator('#dirty')).to_have_text('')
    expect(page.locator('.source-marker-flag')).to_have_count(4)
    assert len(ws.threads('main.py')) == 4


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
@pytest.mark.parametrize('modifier', ['Control','Meta'])
def test_python_ctrl_click_import_alias_and_back_preserve_draft_undo(workspace_page, modifier):
    from playwright.sync_api import expect
    root,page,url,_ = workspace_page
    (root/'helper.py').write_text('# helper\ndef build(value):\n    return value\n')
    source='from helper import build as make\nanswer = make(2)\n'
    (root/'main.py').write_text(source)
    page.goto(url); open_file(page,'main.py')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('# unsaved draft')
    reference=page.locator('.cm-line').filter(has_text='answer = make').get_by_text('make',exact=True)
    page.keyboard.down(modifier); reference.hover()
    expect(page.locator('.python-definition-link')).to_have_text('make')
    reference.click(); page.keyboard.up(modifier)
    expect(page.locator('#document-name')).to_have_text('helper.py')
    expect(page.locator('.cm-activeLine')).to_contain_text('def build')
    page.get_by_role('button',name='Back to previous file').click()
    expect(page.locator('#document-name')).to_have_text('main.py')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    page.locator('.cm-content').click(); page.keyboard.press('Control+z')
    expect(page.locator('#dirty')).to_have_text('')
    assert (root/'main.py').read_text() == source


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_python_f12_current_buffer_review_unicode_and_tab_indentation(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws = workspace_page
    source='def café():\r\n    return 2\r\nvalue = "🦊"; café()\r\n'
    (root/'main.py').write_bytes(source.encode())
    page.goto(url); open_file(page,'main.py')
    reference=page.locator('.cm-line').filter(has_text='value =').get_by_text('café',exact=True)
    reference.click(); page.keyboard.press('F12')
    expect(page.locator('.cm-activeLine')).to_contain_text('def café')
    expect(page.locator('#notice')).to_contain_text('Definition · main.py:1')
    page.locator('#work-mode').click(); expect(page.locator('#work-mode')).to_have_attribute('aria-checked','true')
    expect(page.locator('#work-mode')).to_be_enabled()
    draft='# changed draft\r\ndef draft_only():\r\n    return 1\r\ndraft_only()\r\n'
    replace_source(page, draft)
    expect(page.locator('.cm-content')).to_contain_text('draft_only()')
    expect(page.locator('.cm-line')).to_have_count(5)
    expect(page.locator('.cm-specialChar')).to_have_count(0)
    expect(page.locator('#review-status')).to_have_text('Review saved')
    assert ws.reviews.start('main.py',ws.text('main.py')[1])['content']==draft
    page.locator('.cm-line').filter(has_text=re.compile('^draft_only')).click()
    page.keyboard.press('Home'); page.keyboard.press('ArrowRight')
    page.keyboard.press('F12'); expect(page.locator('.cm-activeLine')).to_contain_text('def draft_only')
    page.keyboard.press('Control+End'); page.keyboard.press('Tab'); page.keyboard.insert_text('x = 1')
    # Compare exact DOM text: to_have_text normalizes away leading whitespace.
    expect(page.locator('.cm-activeLine')).to_have_js_property('textContent','  x = 1')
    assert (root/'main.py').read_bytes() == source.encode()


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_definition_results_never_override_new_navigation_or_edits(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_ = workspace_page
    (root/'main.py').write_text('def build(): pass\nbuild()\n')
    (root/'other.py').write_text('other = 1\n')
    page.goto(url); open_file(page,'main.py')
    held=[]
    page.route('**/api/python/definition',lambda route:held.append(route))
    reference=page.locator('.cm-line').filter(has_text=re.compile('^build')).get_by_text('build',exact=True)
    reference.click(modifiers=['Control']); expect(page.locator('#notice')).to_have_text('Finding definition…')
    open_file(page,'other.py')
    held.pop().fulfill(status=200,content_type='application/json',body=json.dumps({'definitions':[dict(path='main.py',line=1,column=4)]}))
    settle(page); expect(page.locator('#document-name')).to_have_text('other.py')
    open_file(page,'main.py'); reference.click(modifiers=['Control'])
    expect(page.locator('#notice')).to_have_text('Finding definition…')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.insert_text('# newer edit')
    held.pop().fulfill(status=200,content_type='application/json',body=json.dumps({'definitions':[dict(path='main.py',line=1,column=4)]}))
    settle(page); expect(page.locator('.cm-activeLine')).to_have_text('# newer edit')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_python_dirty_destination_and_missing_definition_keep_reading_stable(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_ = workspace_page
    (root/'helper.py').write_text('def build(): pass\n')
    (root/'main.py').write_text('from helper import build\nbuild()\nmissing()\n')
    page.goto(url); open_file(page,'helper.py')
    page.locator('.cm-content').click(); page.keyboard.press('Control+Home'); page.keyboard.insert_text('# held draft\n')
    open_file(page,'main.py')
    reference=page.locator('.cm-line').filter(has_text=re.compile('^build')).get_by_text('build',exact=True)
    reference.click(); reference.click(modifiers=['Control'])
    expect(page.locator('#notice')).to_contain_text('destination draft')
    expect(page.locator('#document-name')).to_have_text('main.py')
    page.locator('.cm-line').filter(has_text=re.compile('^missing')).get_by_text('missing',exact=True).click()
    page.keyboard.press('F12'); expect(page.locator('#notice')).to_have_text('No definition found in this workspace.')
    expect(page.locator('.cm-activeLine')).to_contain_text('missing()')
    open_file(page,'helper.py'); expect(page.locator('#dirty')).to_contain_text('Unsaved')
    expect(page.locator('.cm-content')).to_contain_text('# held draft')


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_definition_picker_and_cross_file_review_navigation(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_ = workspace_page
    for name in ['a.py','b.py']:
        (root/name).write_text('def build(): pass\n')
    source='if unknown:\n    from a import build\nelse:\n    from b import build\nbuild()\n'
    (root/'main.py').write_text(source)
    page.goto(url); open_file(page,'main.py')
    page.locator('#work-mode').click(); expect(page.locator('#work-mode')).to_be_enabled()
    reference=page.locator('.cm-line').filter(has_text=re.compile('^build')).get_by_text('build',exact=True)
    reference.click(); reference.click(modifiers=['Control'])
    dialog=page.get_by_role('dialog',name='Choose a definition')
    expect(dialog).to_be_visible(); expect(dialog.locator('nav button')).to_have_count(2)
    page.keyboard.press('Escape'); expect(dialog).not_to_be_visible()
    expect(page.locator('#document-name')).to_have_text('main.py')
    page.keyboard.press('F12'); expect(dialog).to_be_visible()
    dialog.get_by_role('button',name='build · b.py:1',exact=True).click()
    expect(page.locator('#document-name')).to_have_text('b.py')
    expect(page.locator('.cm-activeLine')).to_contain_text('def build')
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked','true')


@pytest.mark.parametrize('workspace_page', ['chromium','firefox'], indirect=True)
def test_existing_local_completions_need_no_analysis_requests(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_ = workspace_page
    (root/'main.py').write_text('def current_document_symbol(): pass\ncur')
    requests=[]
    page.on('request',lambda request:requests.append(request.url) if '/api/python/' in request.url else None)
    page.goto(url); open_file(page,'main.py')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End'); page.keyboard.press('Control+Space')
    expect(page.locator('.cm-tooltip-autocomplete')).to_be_visible()
    expect(page.locator('.cm-completionLabel').filter(has_text='current_document_symbol')).to_have_count(1)
    settle(page)  # Let the popup settle past CodeMirror's 75 ms interaction guard.
    page.keyboard.press('Enter')
    expect(page.locator('.cm-activeLine')).to_have_text('current_document_symbol')
    assert requests == []


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['edit','review'])
@pytest.mark.parametrize('inserted_break',['\n','\r\n'],ids=['lf-input','crlf-input'])
def test_crlf_multiline_input_undo_and_save_preserve_line_structure(workspace_page,mode,inserted_break):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='value = "🦊"\r\nsecond = 2\r\n'
    expected='first = "🧠"\r\nsecond = 3\r\n'
    (root/'main.py').write_bytes(original.encode())
    page.goto(url);open_file(page,'main.py')
    if mode=='review':
        page.locator('#work-mode').click()
        expect(page.locator('#work-mode')).to_have_attribute('aria-checked','true')
        expect(page.locator('#work-mode')).to_be_enabled()
    replace_source(page,expected.replace('\r\n',inserted_break))
    expect(page.locator('.cm-line')).to_have_count(3)
    expect(page.locator('.cm-specialChar')).to_have_count(0)
    assert (root/'main.py').read_bytes()==original.encode()
    page.keyboard.press('Control+z')
    if mode=='review':
        expect(page.locator('#review-status')).to_have_text('Review saved')
        assert ws.reviews.start('main.py',ws.text('main.py')[1])['content']==original
    else:
        expect(page.locator('#dirty')).to_have_text('')
    page.keyboard.press('Control+Shift+z')
    expect(page.locator('.cm-line')).to_have_count(3)
    page.keyboard.press('Control+s')
    if mode=='edit':
        expect(page.locator('#dirty')).to_have_text('')
        assert (root/'main.py').read_bytes()==expected.encode()
    else:
        expect(page.locator('#review-status')).to_have_text('Review saved')
        assert ws.reviews.start('main.py',ws.text('main.py')[1])['content']==expected
        assert (root/'main.py').read_bytes()==original.encode()
