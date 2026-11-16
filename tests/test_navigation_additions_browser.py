import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page,open_file
from test_explorer_status import git
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_git_status_colors_refresh_without_losing_folder_expansion(workspace_page):
    root,page,url,ws=workspace_page
    git(root,'init');git(root,'config','user.name','Test');git(root,'config','user.email','test@example.invalid')
    (root/'src').mkdir();(root/'src/clean.py').write_text('A=1');(root/'.gitignore').write_text('*.log\n');git(root,'add','.');git(root,'commit','-m','Initial')
    (root/'src/new.py').write_text('NEW=1');(root/'trace.log').write_text('Ignored')
    page.goto(url);page.locator('.file-folder>summary').click()
    clean=page.locator('.file-entry[data-path="src/clean.py"]');new=page.locator('.file-entry[data-path="src/new.py"]');ignored=page.locator('.file-entry[data-path="trace.log"]')
    expect(new).to_have_attribute('data-git-status','new');expect(ignored).to_have_attribute('data-git-status','ignored');expect(clean).to_have_attribute('data-git-status','')
    for theme in ['light','dark']:
        if page.locator('html').get_attribute('data-theme')!=theme:page.locator('#theme').click()
        colors=[el.locator('.file-name').evaluate('el=>getComputedStyle(el).color') for el in [clean,new,ignored]]
        assert len(set(colors))==3
    (root/'src/clean.py').write_text('A=2');page.locator('#refresh-files').click()
    expect(clean).to_have_attribute('data-git-status','modified');expect(page.locator('.file-folder')).to_have_attribute('open','')
    expect(page.locator('.file-folder')).to_have_attribute('data-git-status','modified')
    git(root,'add','src/clean.py');git(root,'commit','-m','Update');page.locator('#refresh-files').click();expect(clean).to_have_attribute('data-git-status','')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_ctrl_p_recent_order_filter_keys_reload_and_uppercase_typing(workspace_page):
    root,page,url,ws=workspace_page
    for name in ['a.txt','b.txt','z.txt']:(root/name).write_text(name)
    page.goto(url)
    for name in ['a.txt','z.txt','b.txt']:open_file(page,name)
    page.keyboard.press('Control+p');options=page.locator('#quick-results [role=option]')
    expect(options).to_have_text(['b.txt','z.txt','a.txt'])
    page.locator('#quick-query').press('ArrowDown');page.locator('#quick-query').press('Enter');expect(page.locator('#document-name')).to_have_text('z.txt')
    page.keyboard.press('Control+p');page.locator('#quick-query').fill('at');expect(options).to_have_text(['a.txt'])
    page.locator('#quick-query').press('Enter');expect(page.locator('#document-name')).to_have_text('a.txt')
    page.reload();open_file(page,'a.txt');page.keyboard.press('Control+p');expect(options.first).to_have_text('a.txt');page.keyboard.press('Escape')
    page.locator('.cm-content').click();page.keyboard.press('Shift+P');expect(page.locator('.cm-content')).to_contain_text('P');expect(page.locator('#quick-dialog')).not_to_be_visible()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_drag_keyboard_resize_persists_and_keeps_draft(workspace_page):
    root,page,url,ws=workspace_page
    (root/'part.py').write_text('class Part:\n    def build(self): pass\n');(root/'note.txt').write_text('Other')
    page.goto(url);open_file(page,'part.py');page.locator('#code-outline>summary').click()
    outline=page.locator('#code-outline');handle=page.get_by_role('separator',name='Resize Python outline')
    before=outline.bounding_box()['width'];box=handle.bounding_box()
    page.mouse.move(box['x']+2,box['y']+50);page.mouse.down();page.mouse.move(box['x']-98,box['y']+50,steps=6);page.mouse.up()
    expect(handle).to_have_attribute('aria-valuenow',str(round(before+100)));assert abs(outline.bounding_box()['width']-before-100)<2
    handle.focus();handle.press('ArrowLeft');assert abs(outline.bounding_box()['width']-before-120)<2
    box=handle.bounding_box();page.mouse.move(box['x']+2,box['y']+50);page.mouse.down();page.mouse.move(box['x']-58,box['y']+50,steps=3);page.keyboard.press('Escape');page.mouse.up()
    expect(outline).to_have_attribute('open','');assert abs(outline.bounding_box()['width']-before-120)<2
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('# draft')
    open_file(page,'note.txt');open_file(page,'part.py');expect(page.locator('.cm-content')).to_contain_text('# draft');assert abs(outline.bounding_box()['width']-before-120)<2
    page.locator('.cm-content').click();page.keyboard.press('Control+z');expect(page.locator('.cm-content')).not_to_contain_text('# draft')
    page.reload();open_file(page,'part.py');assert abs(outline.bounding_box()['width']-before-120)<2
    page.set_viewport_size({'width':900,'height':740});assert outline.bounding_box()['width']<=page.locator('.reading-pane').bounding_box()['width']*.8+1
    handle.dblclick();expect(handle).to_have_attribute('aria-valuenow','190')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_occurrence_scrollbar_map_jumps_keeps_selection_and_clears(workspace_page):
    root,page,url,ws=workspace_page
    lines=['needle at top']+['ordinary prose line '*3 for _ in range(300)]+['last needle match']
    (root/'long.txt').write_text('\n'.join(lines))
    page.goto(url);open_file(page,'long.txt');page.locator('.cm-content').click();page.keyboard.press('Control+Home');page.keyboard.press('Control+Shift+ArrowRight')
    overview=page.get_by_role('navigation',name='Selected text matches');expect(overview).to_be_visible()
    target=overview.get_by_role('button',name='Matching text, line 302');expect(target).to_be_visible()
    first=overview.get_by_role('button').first.bounding_box();last=target.bounding_box();assert last['y']>first['y']+100
    target.click()
    page.wait_for_function('()=>document.querySelector(".cm-scroller").scrollTop>1000')
    expect(page.locator('.cm-content')).to_contain_text('last needle match');expect(overview).to_be_visible()
    page.keyboard.press('ArrowRight');expect(overview).not_to_be_visible()
    page.keyboard.press('Control+Home');page.keyboard.press('Control+Shift+ArrowRight');expect(overview).to_be_visible()
    page.keyboard.press('Control+a');page.keyboard.insert_text('short replacement');expect(overview).not_to_be_visible()
    expect(page.locator('.cm-content')).to_have_text('short replacement')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_recent_picker_keeps_closed_outside_visits_and_selection_during_refresh(workspace_page):
    root,page,url,ws=workspace_page
    outside=root.parent/('outside-'+root.name+'.txt');outside.write_text('Outside')
    (root/'note.txt').write_text('Inside');page.goto(url);open_file(page,'note.txt')
    page.locator('#file-open').click();page.locator('#file-path').fill(str(outside));page.locator('#file-form button[type=submit]').click()
    expect(page.locator('#document-name')).to_have_text(str(outside))
    page.get_by_role('button',name='Close '+str(outside),exact=True).click();expect(page.locator('#document-name')).to_have_text('note.txt')
    held=[];page.route('**/api/workspace',lambda route:held.append(route))
    page.keyboard.press('Control+p');options=page.locator('#quick-results [role=option]')
    expect(options).to_have_text(['note.txt',str(outside)])
    page.locator('#quick-query').press('ArrowDown');expect(options.last).to_have_attribute('aria-selected','true')
    (root/'late.txt').write_text('Discovered during refresh')
    assert held
    with page.expect_response('**/api/workspace'):held[0].continue_()
    expect(options).to_have_count(3);expect(options.filter(has_text=str(outside))).to_have_attribute('aria-selected','true')
    page.locator('#quick-query').press('Enter');expect(page.locator('#document-name')).to_have_text(str(outside))
