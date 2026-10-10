"""Discussion search composes with navigation, spotlight, drafts and polling."""
import os
import pytest
from test_requested_features import workspace_page,open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def seed(root,ws):
    text='CadQuery configuration.\n\n'+'Reading context.\n\n'*100+'Topology passage.\n'
    (root/'note.md').write_text(text)
    version=ws.read('note.md')['version']
    first=ws.create_thread('note.md',0,22,'Geometry verifier requires review.','Reviewer',version)
    start=text.index('Topology passage')
    second=ws.create_thread('note.md',start,start+16,'Another observation.','Reviewer',version)
    ws.reply(second['id'],'Prefix. '*80+'A café and geometry concern. <img src=x onerror="window.searchInjected=true">','Agent')
    return first,second,text


def visible_ids(page):
    return page.locator('#threads>.thread:visible').evaluate_all('els=>els.map(el=>Number(el.dataset.thread))')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_fuzzy_search_explains_matches_and_thread_numbers(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first,second,text=seed(root,ws)
    page.goto(url);open_file(page,'note.md');search=page.get_by_role('searchbox',name='Search threads')
    search.fill('verifer')
    expect(page.locator('#thread-search-status')).to_have_text('1 match · Best matches first')
    assert visible_ids(page)==[first['id']]
    expect(page.locator('.thread-search-match:visible .search-match-label')).to_have_text('Comment')
    expect(page.locator('.thread-search-match:visible mark')).to_have_text('verifier')
    search.fill('cadqury');expect(page.locator('.thread-search-match:visible .search-match-label')).to_have_text('Passage')
    search.fill('cafe');expect(page.locator('.thread-search-match:visible .search-match-label')).to_have_text('Reply')
    expect(page.locator('.thread-search-match:visible mark')).to_have_text('café')
    assert visible_ids(page)==[second['id']]
    search.fill('searchInjected');expect(page.locator('.thread-search-match:visible')).to_contain_text('<img')
    assert not page.evaluate('!!window.searchInjected')
    assert page.locator('.thread-search-match img').count()==0
    search.fill('#'+str(first['id']));expect(page.locator('.thread-search-match:visible .search-match-label')).to_have_text('Thread number')
    assert visible_ids(page)==[first['id']]
    search.fill('zzzzzz');expect(page.locator('#thread-search-empty')).to_be_visible();assert visible_ids(page)==[]
    search.press('Escape');expect(search).to_have_value('');expect(page.locator('#thread-search-status')).not_to_be_visible()
    assert visible_ids(page)==[first['id'],second['id']]
    assert (root/'note.md').read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_search_scope_resolved_threads_and_cross_file_jump(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first,second,_=seed(root,ws)
    (root/'other.py').write_text('geometry = 42\n')
    other=ws.create_thread('other.py',0,8,'Geometry verifier','Agent',ws.read('other.py')['version'])
    ws.update_thread(first['id'],resolved=True)
    page.goto(url);open_file(page,'note.md');search=page.locator('#thread-search');search.fill('verifier')
    expect(page.locator('#thread-search-empty')).to_be_visible()
    page.locator('#show-resolved').check();expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('#thread-scope').check();expect(page.locator('#thread-search-status')).to_contain_text('2 matches')
    expect(page.locator(f'.thread[data-thread="{other["id"]}"] .search-match-label')).to_contain_text('other.py')
    page.locator('#show-resolved').uncheck();expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('.thread-search-match:visible').click();expect(page.locator('#document-name')).to_have_text('other.py')
    expect(page.locator('#passage-spotlight')).to_be_visible();expect(page.locator('.focused-highlight')).to_have_text('geometry')
    page.keyboard.press('Escape');expect(page.locator('#passage-spotlight')).not_to_be_visible();expect(search).to_have_value('verifier')
    assert visible_ids(page)==[other['id']]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_keyboard_search_navigation_and_spotlight_return_preserve_reading(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first,second,_=seed(root,ws)
    page.goto(url);open_file(page,'note.md');page.locator('#collapse-threads').click()
    search=page.locator('#thread-search');pane=page.locator('.cm-scroller');pane.evaluate('el=>el.scrollTop=150')
    before=pane.evaluate('el=>el.scrollTop');search.fill('geometry')
    expect(page.locator('#thread-search-status')).to_contain_text('2 matches')
    assert pane.evaluate('el=>el.scrollTop')==before
    assert visible_ids(page)==[first['id'],second['id']]
    search.press('ArrowDown');expect(page.locator('.thread-search-match:focus')).to_have_attribute('aria-label',f'Open thread #{first["id"]}, matched comment')
    page.keyboard.press('ArrowDown');page.keyboard.press('Enter')
    expect(page.locator('#passage-spotlight')).to_be_visible();expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(second['id']))
    expect(page.locator('.focused-highlight')).to_have_text('Topology passage')
    page.keyboard.press('Escape');expect(page.locator('#passage-spotlight')).not_to_be_visible()
    expect(search).to_have_value('geometry');assert visible_ids(page)==[first['id'],second['id']]
    page.locator('#previous').click();expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(first['id']))
    page.locator('#next').click();expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(second['id']))
    search.focus();search.press('Enter');expect(page.locator('#passage-spotlight')).to_be_visible()
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(first['id']))


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_search_keeps_drafts_and_updates_from_external_replies(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first,second,_=seed(root,ws)
    page.goto(url);open_file(page,'note.md')
    page.locator(f'.thread[data-thread="{first["id"]}"] .jump').click()
    draft=page.locator(f'#reply-{first["id"]}');draft.fill('Unsent reply draft')
    identity=draft.evaluate('el=>{window.savedReply=el;return true}')
    assert identity
    search=page.locator('#thread-search');search.fill('cafe');expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('#thread-search-clear').click();expect(draft).to_have_value('Unsent reply draft')
    assert draft.evaluate('el=>el===window.savedReply')
    search.fill('newlyadded');expect(page.locator('#thread-search-empty')).to_be_visible()
    ws.reply(first['id'],'Newlyadded observation','Agent')
    expect(page.locator('#thread-search-status')).to_contain_text('1 match',timeout=10000)
    assert visible_ids(page)==[first['id']];expect(draft).to_have_value('Unsent reply draft')
    search.focus();search.press('Escape');expect(draft).to_have_value('Unsent reply draft')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_collapsed_search_results_remain_readable_in_both_themes_and_zen(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    seed(root,ws);page.set_viewport_size({'width':1100,'height':680});page.goto(url);open_file(page,'note.md')
    page.locator('#collapse-threads').click();search=page.locator('#thread-search');search.fill('geometry')
    for theme in ['light','dark']:
        if page.locator('html').get_attribute('data-theme')!=theme:page.locator('#theme').click()
        expect(page.locator('.thread-search-match:visible')).to_have_count(2)
        assert page.locator('.thread-search-match:visible').first.bounding_box()['width']>180
        assert page.locator('.thread-search-bar').evaluate('el=>el.scrollWidth<=el.clientWidth')
    page.keyboard.press('Control+Alt+z');expect(page.locator('.thread-search-match:visible')).to_have_count(2)
    page.locator('.thread-search-match:visible').last.click();expect(page.locator('#passage-spotlight')).to_be_visible()
    page.keyboard.press('Escape');expect(page.locator('.thread-search-match:visible')).to_have_count(2)
    page.locator('#discussions-toggle').click();expect(search).not_to_be_visible()
    page.locator('#discussions-toggle').click();expect(search).to_be_visible();expect(search).to_have_value('geometry')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_empty_search_hints_reveal_only_the_required_scopes(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    first,second,_=seed(root,ws)
    ws.update_thread(first['id'],resolved=True)
    (root/'other.txt').write_text('Outside passage.')
    outside=ws.create_thread('other.txt',0,7,'Outsideonly observation','Agent',ws.read('other.txt')['version'])
    closed=ws.create_thread('other.txt',0,7,'Closedoutside observation','Agent',ws.read('other.txt')['version'])
    ws.update_thread(closed['id'],resolved=True)
    requests=[];page.on('request',lambda request:requests.append(request.url))
    page.goto(url);open_file(page,'note.md')
    assert not any('/api/thread-search-index' in url for url in requests)
    search=page.locator('#thread-search');hints=page.locator('#thread-search-hints')
    search.fill('verifier');expect(hints).to_contain_text('1 match in resolved threads')
    hints.get_by_role('button',name='1 match in resolved threads',exact=True).click()
    expect(page.locator('#show-resolved')).to_be_checked();expect(page.locator('#thread-search-empty')).not_to_be_visible()
    page.locator('#show-resolved').uncheck();search.fill('outsideonly')
    expect(hints).to_contain_text('1 match in other files');assert visible_ids(page)==[]
    hints.get_by_role('button',name='1 match in other files',exact=True).click()
    expect(page.locator('#thread-scope')).to_be_checked();expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    assert visible_ids(page)==[outside['id']]
    expect(page.locator('#show-resolved')).not_to_be_checked()
    page.locator('#thread-scope').uncheck();search.fill('closedoutside')
    expect(hints).to_contain_text('1 match in resolved threads in other files');assert visible_ids(page)==[]
    hints.get_by_role('button',name='1 match in resolved threads in other files',exact=True).click()
    expect(page.locator('#thread-scope')).to_be_checked();expect(page.locator('#show-resolved')).to_be_checked()
    expect(page.locator('#thread-search-status')).to_contain_text('1 match');assert visible_ids(page)==[closed['id']]
    search.fill('trulyabsent');expect(page.locator('#thread-search-empty')).to_be_visible();expect(hints.locator('button')).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_search_review_drafts_filters_navigation_and_approval(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='Original passage.\n';(root/'note.txt').write_text(original)
    file=ws.read('note.txt');draft=ws.reviews.start('note.txt',file['version'])
    draft=ws.reviews.update(draft['id'],draft['version'],[dict(start=0,end=0,insert='Draftvalue\n')],'Agent','agent')
    local=ws.reviews.create_thread(draft['id'],draft['version'],0,10,'Verifier feedback','Agent')
    (root/'other.txt').write_text('Outside passage.')
    otherfile=ws.read('other.txt');otherdraft=ws.reviews.start('other.txt',otherfile['version'])
    outside=ws.reviews.create_thread(otherdraft['id'],otherdraft['version'],0,7,'Verifier feedback','Agent')
    ws.update_thread(outside['id'],resolved=True)
    page.goto(url);open_file(page,'note.txt');page.locator('#work-mode').click()
    expect(page.locator('.review-agent')).to_have_text('Draftvalue')
    search=page.locator('#thread-search');search.fill('verifer')
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    assert visible_ids(page)==[local['id']]
    search.fill('draftvalue');expect(page.locator('.thread-search-match:visible .search-match-label')).to_have_text('Passage')
    search.press('Enter');expect(page.locator('#passage-spotlight')).to_be_visible()
    expect(page.locator('.focused-highlight')).to_have_text('Draftvalue')
    page.keyboard.press('Escape');expect(search).to_have_value('draftvalue')
    search.fill('verifier');page.locator('#thread-scope').check()
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    page.locator('#show-resolved').check();expect(page.locator('#thread-search-status')).to_contain_text('2 matches')
    page.locator(f'.thread[data-thread="{outside["id"]}"] .thread-search-match').click()
    expect(page.locator('#document-name')).to_have_text('other.txt')
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked','true')
    expect(page.locator('.thread.active')).to_have_attribute('data-thread',str(outside['id']))
    page.wait_for_function("getSelection().toString()==='Outside'")
    page.keyboard.press('Escape');open_file(page,'note.txt')
    assert (root/'note.txt').read_text()==original
    page.locator('#approve-review').click();page.locator('#confirm-review-approve').click();expect(page.locator('#work-mode')).to_have_attribute('aria-checked','false')
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    assert visible_ids(page)==[local['id']]
    assert (root/'note.txt').read_text()==draft['content']
    assert (root/'other.txt').read_text()=='Outside passage.'
    assert [item['id'] for item in ws.reviews.list()]==[otherdraft['id']]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_review_search_hints_use_draft_passages_and_clear_on_mode_switch(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Local passage.')
    (root/'other.txt').write_text('Outside passage.')
    file=ws.read('other.txt');thread=ws.create_thread('other.txt',0,len(file['content']),'Ordinary comment','Agent',file['version'])
    draft=ws.reviews.start('other.txt',file['version'])
    draft=ws.reviews.update(draft['id'],draft['version'],[dict(start=8,end=8,insert='uniquereview ')],'Agent','agent')
    closed=ws.reviews.create_thread(draft['id'],draft['version'],0,7,'Closedreview observation','Agent')
    ws.update_thread(closed['id'],resolved=True)
    page.goto(url);open_file(page,'note.txt');search=page.locator('#thread-search');hints=page.locator('#thread-search-hints')
    search.fill('uniquereview');expect(page.locator('#thread-search-empty')).to_be_visible()
    # Wait for the index response rather than relying on a fixed delay.
    with page.expect_response('**/api/thread-search-index?review=*'):
        page.locator('#work-mode').click()
    expect(hints).to_contain_text('1 match in other files')
    hints.get_by_role('button',name='1 match in other files',exact=True).click()
    expect(page.locator('#thread-search-status')).to_contain_text('1 match')
    assert visible_ids(page)==[thread['id']]
    expect(page.locator('.thread-search-match:visible mark')).to_have_text('uniquereview')
    page.locator('#thread-scope').uncheck();search.fill('closedreview')
    expect(hints).to_contain_text('1 match in resolved threads in other files')
    with page.expect_response('**/api/thread-search-index'):
        page.locator('#work-mode').click()
    expect(page.locator('#work-mode')).to_have_attribute('aria-checked','false')
    expect(page.locator('#thread-search-empty')).to_be_visible();expect(hints.locator('button')).to_have_count(0)
    page.locator('#thread-scope').check();page.locator('#show-resolved').check()
    expect(page.locator('#thread-search-empty')).to_be_visible();assert visible_ids(page)==[]
