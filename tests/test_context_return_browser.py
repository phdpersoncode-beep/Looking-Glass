"""Temporary immutable context and resolved passages, in Edit and Review mode."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def thread_for(ws, path, text, quote, work):
    file = ws.read(path)
    start = text.index(quote)
    if work == 'review':
        draft = ws.reviews.start(path, file['version'])
        return ws.reviews.create_thread(draft['id'], draft['version'], start,
                                       start + len(quote), 'Check passage', 'Reviewer')
    return ws.create_thread(path, start, start + len(quote), 'Check passage',
                            'Reviewer', file['version'])


def start(page, url, path, work):
    from playwright.sync_api import expect
    page.goto(url)
    open_file(page, path)
    if work == 'review':
        page.locator('#work-mode').select_option('review')
        expect(page.locator('#review-status')).to_have_text('Review saved')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_numbered_markers_survive_live_rendering(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    text = '7. First item\n8. Second item\n   1. Nested item\n   2. Another nested item\n\n1) Parenthesized\n2) Next item\n\n1. [ ] Numbered task\n2. [x] Completed task\n\n- Bullet item\n'
    (root / 'lists.md').write_text(text)
    start(page, url, 'lists.md', 'edit')
    # Put the caret outside lists so live hiding applies to every marker.
    page.locator('.cm-content').click()
    page.keyboard.press('Control+End')
    expect(page.locator('.cm-content')).to_contain_text('7.')
    expect(page.locator('.cm-content')).to_contain_text('8.')
    expect(page.locator('.cm-content')).to_contain_text('1)')
    expect(page.locator('.cm-content')).to_contain_text('2)')
    expect(page.locator('.cm-content')).to_contain_text('1.')
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-preview ol').first).to_have_attribute('start', '7')
    assert (root / 'lists.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
@pytest.mark.parametrize('mode', ['live', 'source', 'preview'])
@pytest.mark.parametrize('exit', ['return', 'escape', 'resolve', 'delete',
                                  'external_resolve', 'external_delete', 'unfocus'])
def test_context_restores_reader_and_drafts(workspace_page, work, mode, exit):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '# Report\n\nPassage to discuss.\n\n7. First\n8. Second\n\n| Label | Value |\n| --- | --- |\n| width | 12 |\n\n```python\nif True:\n    print("context")\n```\n\n' + '\n\n'.join(f'Paragraph {i} remains readable.' for i in range(100))
    (root / 'report.md').write_text(text)
    thread = thread_for(ws, 'report.md', text, 'Passage to discuss.', work)
    start(page, url, 'report.md', work)
    if mode != 'preview':
        page.locator('#mode').select_option(mode)
        page.locator('.cm-content').click()
        page.keyboard.press('Control+End')
        page.keyboard.insert_text('\nLocal draft')
        if work == 'review':
            expect(page.locator('#review-status')).to_have_text('Review saved')
        else:
            expect(page.locator('#dirty')).to_contain_text('Unsaved')
    else:
        page.locator('#mode').select_option(mode)
    page.locator('.thread .jump').click()
    reply = page.locator(f'#reply-{thread["id"]}')
    reply.fill('Unsent reply')
    # Finish the preceding jump, then let virtual editor geometry settle before
    # recording the reading position this context visit must preserve.
    page.wait_for_function('''mode=>Math.abs((mode==='preview'?document.querySelector('#surface'):document.querySelector('.cm-scroller')).scrollTop)<2''', arg=mode)
    page.evaluate('''mode=>{
      window.heldReader=document.querySelector(mode==='preview'?'.markdown-preview':'.cm-editor');
      const scroller=mode==='preview'?document.querySelector('#surface'):document.querySelector('.cm-scroller');
      scroller.scrollTop=650;window.heldGeometry=null;
    }''', mode)
    page.wait_for_function('''mode=>{
      const scroller=mode==='preview'?document.querySelector('#surface'):document.querySelector('.cm-scroller');
      const state=[scroller.scrollTop,scroller.scrollHeight,scroller.clientHeight].join(':');
      const previous=window.heldGeometry;
      window.heldGeometry={state,frames:previous?.state===state?previous.frames+1:0};
      if(document.fonts.status!=='loaded'||window.heldGeometry.frames<3)return false;
      window.heldScroll=scroller.scrollTop;
      return true;
    }''', arg=mode)
    page.locator('.original-context').click()
    expect(page.locator('#document-name')).to_have_text('Original · report.md')
    expect(page.locator('.original-reading h1')).to_have_text('Report')
    expect(page.locator('.original-reading table')).to_be_visible()
    expect(page.locator('.original-reading ol')).to_have_attribute('start', '7')
    expect(page.locator('.original-reading pre code')).to_contain_text('print("context")')
    assert page.locator('.original-reading pre code span').count() > 0
    saved = page.evaluate('JSON.parse(localStorage.getItem("looking-glass-tabs:"+document.querySelector(".root-label").textContent))')
    assert saved['active'] == 'report.md'
    assert all(not item['path'].startswith('looking-glass://thread/') for item in saved['tabs'])
    if exit == 'return':
        page.locator('#context-return').click()
    elif exit == 'escape':
        reply.focus()
        page.keyboard.press('Escape')
    elif exit == 'resolve':
        page.get_by_role('button', name='Resolve thread', exact=True).click()
    elif exit == 'delete':
        page.once('dialog', lambda dialog: dialog.accept())
        page.get_by_role('button', name='Delete thread', exact=True).click()
    elif exit == 'external_resolve':
        ws.update_thread(thread['id'], resolved=True)
    elif exit == 'external_delete':
        ws.delete_thread(thread['id'])
    else:
        page.locator('#all-discussions').click()
    expect(page.locator('#document-name')).to_have_text('report.md', timeout=10000)
    expect(page.locator('#context-return')).to_have_count(0)
    assert page.evaluate('window.heldReader===document.querySelector(window.heldReader.classList.contains("cm-editor")?".cm-editor":".markdown-preview")')
    page.wait_for_function('''mode=>Math.abs((mode==='preview'?document.querySelector('#surface'):document.querySelector('.cm-scroller')).scrollTop-window.heldScroll)<2''', arg=mode)
    if mode != 'preview':
        page.locator('.cm-content').click()
        page.keyboard.press('Control+End')
        expect(page.locator('.cm-content')).to_contain_text('Local draft')
    if exit not in ('delete', 'external_delete'):
        expect(reply).to_have_value('Unsent reply')
    assert (root / 'report.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
@pytest.mark.parametrize('mode', ['live', 'source', 'preview', 'table'])
@pytest.mark.parametrize('dirty', [False, True])
def test_resolved_passages_are_faint_with_mapped_drafts(workspace_page, work, mode, dirty):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '# Report\n\nPassage to discuss.\n\n| Label | Value |\n| --- | --- |\n| width | 12 |\n'
    quote = 'width' if mode == 'table' else 'Passage to discuss.'
    (root / 'report.md').write_text(text)
    thread = thread_for(ws, 'report.md', text, quote, work)
    start(page, url, 'report.md', work)
    if dirty:
        page.locator('#mode').select_option('source')
        page.locator('.cm-content').click()
        page.keyboard.press('Control+Home')
        page.keyboard.insert_text('Draft prefix.\n\n')
        if work == 'review':
            expect(page.locator('#review-status')).to_have_text('Review saved')
    page.locator('#mode').select_option('live' if mode == 'table' else mode)
    host = '.md-table' if mode == 'table' else '.markdown-preview' if mode == 'preview' else '.cm-content'
    mark = page.locator(host + f' .passage-highlight[data-anchor="{thread["id"]}"]')
    expect(mark).to_have_text(quote)
    page.locator('.thread .jump').click()
    page.locator(f'#reply-{thread["id"]}').fill('Reply survives polling')
    ws.update_thread(thread['id'], resolved=True)
    expect(mark).to_have_class('passage-highlight resolved-passage', timeout=10000)
    assert mark.evaluate('el=>getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
    expect(page.locator(f'#reply-{thread["id"]}')).to_have_value('Reply survives polling')
    ws.update_thread(thread['id'], resolved=False)
    expect(mark).not_to_have_class('passage-highlight resolved-passage', timeout=10000)
    assert (root / 'report.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('external', [False, True])
def test_deleting_one_comment_closes_context_while_thread_survives(workspace_page, external):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = 'Original passage.\n'
    (root / 'note.txt').write_text(text)
    thread = thread_for(ws, 'note.txt', text, 'Original', 'edit')
    ws.reply(thread['id'], 'Keep this reply', 'Agent')
    start(page, url, 'note.txt', 'edit')
    page.locator('.original-context').click()
    expect(page.locator('#context-return')).to_be_visible()
    if external:
        ws.delete_message(thread['id'], thread['messages'][0]['id'])
    else:
        page.once('dialog', lambda dialog: dialog.accept())
        page.get_by_role('button', name='Delete comment', exact=True).first.click()
    expect(page.locator('#document-name')).to_have_text('note.txt', timeout=10000)
    assert len(ws.get_thread(thread['id'])['messages']) == 1


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
def test_already_resolved_context_closes_after_reopen_and_resolve(workspace_page, work):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = 'Original passage.\n'
    (root / 'note.txt').write_text(text)
    thread = thread_for(ws, 'note.txt', text, 'Original', work)
    ws.update_thread(thread['id'], resolved=True)
    start(page, url, 'note.txt', work)
    page.locator('#show-resolved').check()
    page.locator('.original-context').click()
    expect(page.locator('#context-return')).to_be_visible()
    page.get_by_role('button', name='Reopen thread', exact=True).click()
    expect(page.get_by_role('button', name='Resolve thread', exact=True)).to_be_visible()
    expect(page.locator('#context-return')).to_be_visible()
    page.get_by_role('button', name='Resolve thread', exact=True).click()
    expect(page.locator('#document-name')).to_have_text('note.txt')


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
@pytest.mark.parametrize('exit', ['return', 'resolve', 'external_delete'])
def test_html_context_preserves_iframe_state_and_scroll(workspace_page, work, exit):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '<p id="passage">Original passage.</p><div style="height:3000px"></div><script>window.reportCounter=1</script>'
    (root / 'report.html').write_text(text)
    thread = thread_for(ws, 'report.html', text, 'Original passage.', work)
    start(page, url, 'report.html', work)
    frame = page.frame_locator('#html-preview')
    expect(frame.locator('#passage')).to_have_text('Original passage.')
    frame.locator('body').evaluate('()=>{window.reportCounter=9;window.scrollTo(0,700)}')
    page.evaluate('window.heldFrame=document.querySelector("#html-preview")')
    page.locator('.original-context').click()
    expect(page.locator('.original-editor')).to_be_visible()
    if exit == 'return':
        page.locator('#context-return').click()
    elif exit == 'resolve':
        page.get_by_role('button', name='Resolve thread', exact=True).click()
    else:
        ws.delete_thread(thread['id'])
    expect(page.locator('#document-name')).to_have_text('report.html', timeout=10000)
    assert page.evaluate('window.heldFrame===document.querySelector("#html-preview")')
    assert frame.locator('body').evaluate('()=>window.reportCounter') == 9
    frame.locator('body').evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    assert abs(frame.locator('body').evaluate('()=>window.scrollY') - 700) < 2


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
@pytest.mark.parametrize('dirty', [False, True])
def test_resolved_html_clears_active_fill_and_selection(workspace_page, work, dirty):
    from playwright.sync_api import expect
    from test_html_annotations_browser import highlights
    root, page, url, ws = workspace_page
    text = '<p id="passage">Original passage.</p>'
    (root / 'report.html').write_text(text)
    thread = thread_for(ws, 'report.html', text, 'Original passage.', work)
    start(page, url, 'report.html', work)
    if dirty:
        page.locator('#html-toggle').click()
        page.locator('.cm-content').click()
        page.keyboard.press('Control+Home')
        page.keyboard.insert_text('<!-- Draft prefix -->\n')
        if work == 'review':
            expect(page.locator('#review-status')).to_have_text('Review saved')
        page.locator('#html-toggle').click()
    frame = page.frame_locator('#html-preview')
    expect(frame.locator('#passage')).to_have_text('Original passage.')
    frame.locator('#passage').click(position={'x': 20, 'y': 10})
    expect(page.locator('#passage-spotlight')).to_be_visible()
    frame.locator('#passage').evaluate('''el=>{const r=document.createRange();r.selectNodeContents(el);getSelection().removeAllRanges();getSelection().addRange(r)}''')
    ws.update_thread(thread['id'], resolved=True)
    expect(page.locator('.thread')).to_have_attribute('data-resolved', 'true', timeout=10000)
    frame.locator('body').evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    assert highlights(page, 'looking-glass-active') == []
    assert highlights(page, 'looking-glass-passages') == []
    assert highlights(page, 'looking-glass-resolved') == ['Original passage.']
    assert frame.locator('body').evaluate('()=>getSelection().toString()') == ''


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_overlapping_open_mark_retains_fill_until_both_resolve(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '| Label | Value |\n| --- | --- |\n| width | 12 |\n'
    (root / 'table.md').write_text(text)
    a = thread_for(ws, 'table.md', text, 'width', 'edit')
    b = thread_for(ws, 'table.md', text, 'width', 'edit')
    start(page, url, 'table.md', 'edit')
    mark = page.locator('.md-table .passage-highlight')
    expect(mark).to_have_text('width')
    ws.update_thread(a['id'], resolved=True)
    expect(page.locator(f'.thread[data-thread="{a["id"]}"]')).to_have_attribute('data-resolved', 'true', timeout=10000)
    assert not mark.evaluate('el=>el.classList.contains("resolved-passage")')
    ws.update_thread(b['id'], resolved=True)
    expect(mark).to_have_class('passage-highlight resolved-passage', timeout=10000)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
def test_code_context_and_reply_snapshots_keep_syntax_and_review_scope(workspace_page, work):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = 'if True:\n    print("original")\n'
    changed = text.replace('original', 'reply context')
    (root / 'sample.py').write_text(text)
    thread = thread_for(ws, 'sample.py', text, 'if True', 'edit')
    if work == 'review':
        draft = ws.reviews.start('sample.py', ws.read('sample.py')['version'])
        ws.reviews.update(draft['id'], draft['version'], [dict(
            start=text.index('original'), end=text.index('original') + len('original'),
            insert='reply context')], 'Agent', 'agent')
    else:
        ws.save('sample.py', changed, ws.read('sample.py')['version'])
    start(page, url, 'sample.py', work)
    page.locator('.original-context').click()
    expect(page.locator('.original-editor .cm-content')).to_contain_text('"original"')
    assert page.locator('.original-editor .cm-content span').count() > 0
    page.locator(f'#reply-{thread["id"]}').fill('Reply from context')
    page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.message')).to_have_count(2)
    # The reply records the active draft, not the displayed immutable snapshot.
    page.locator('.message-origin').last.click()
    expect(page.locator('.original-editor .cm-content')).to_contain_text('"reply context"')
    expect(page.locator('.original-editor .cm-content')).not_to_contain_text('"original"')
    assert page.locator('.original-editor .cm-content span').count() > 0
    page.locator('#context-return').click()
    expect(page.locator('#document-name')).to_have_text('sample.py')
    if work == 'review':
        expect(page.locator('.cm-content .review-agent')).to_have_text('reply context')
        assert ws.reviews.read(draft['id'])['content'] == changed
    else:
        expect(page.locator('.cm-content')).to_contain_text('"reply context"')
    assert (root / 'sample.py').read_text() == (text if work == 'review' else changed)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_comment_added_during_context_visit_also_closes_on_deletion(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = 'Original passage.\n'
    (root / 'note.txt').write_text(text)
    thread = thread_for(ws, 'note.txt', text, 'Original', 'edit')
    start(page, url, 'note.txt', 'edit')
    page.locator('.original-context').click()
    expect(page.locator('#context-return')).to_be_visible()
    ws.reply(thread['id'], 'Added during visit', 'Agent')
    expect(page.locator('.message')).to_have_count(2, timeout=10000)
    message = ws.get_thread(thread['id'])['messages'][-1]
    ws.delete_message(thread['id'], message['id'])
    expect(page.locator('#document-name')).to_have_text('note.txt', timeout=10000)


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
@pytest.mark.parametrize('mode', ['source', 'preview', 'table'])
def test_resolving_selected_markdown_clears_selection_fill(workspace_page, work, mode):
    from playwright.sync_api import expect
    from test_markdown_discussions import select_text
    root, page, url, ws = workspace_page
    text = 'Passage to discuss.\n\n| Label | Value |\n| --- | --- |\n| width | 12 |\n'
    quote = 'width' if mode == 'table' else 'Passage to discuss.'
    (root / 'report.md').write_text(text)
    thread = thread_for(ws, 'report.md', text, quote, work)
    start(page, url, 'report.md', work)
    page.locator('#mode').select_option('live' if mode == 'table' else mode)
    if mode == 'source':
        page.locator('.cm-content').click()
        page.keyboard.press('Control+Home')
        page.keyboard.press('Shift+End')
    else:
        select_text(page, '.md-table .passage-highlight' if mode == 'table' else '.markdown-preview>p')
    expect(page.locator('#selection-comment')).to_be_visible()
    ws.update_thread(thread['id'], resolved=True)
    expect(page.locator('.resolved-passage')).to_have_text(quote, timeout=10000)
    expect(page.locator('#selection-comment')).not_to_be_visible()
    assert page.evaluate('()=>getSelection().toString()') == ''


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('work', ['edit', 'review'])
def test_html_resolution_preserves_unrelated_selection_in_same_node(workspace_page, work):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '<p id="passage">Original passage. Unrelated selection.</p>'
    (root / 'report.html').write_text(text)
    thread = thread_for(ws, 'report.html', text, 'Original passage.', work)
    start(page, url, 'report.html', work)
    frame = page.frame_locator('#html-preview')
    expect(frame.locator('#passage')).to_contain_text('Unrelated selection.')
    frame.locator('#passage').evaluate('''el=>{
      const node=el.firstChild,range=document.createRange();range.setStart(node,node.data.indexOf('Unrelated'));range.setEnd(node,node.length);
      getSelection().removeAllRanges();getSelection().addRange(range);
    }''')
    ws.update_thread(thread['id'], resolved=True)
    expect(page.locator('.thread')).to_have_attribute('data-resolved', 'true', timeout=10000)
    frame.locator('body').evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    assert frame.locator('body').evaluate('()=>getSelection().toString()') == 'Unrelated selection.'
