"""Rendering, retained report contexts, and the visible agent/Git controls."""
import os
import subprocess

import pytest
from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_horizontal_rules_preserve_markdown_syntax_and_editing(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    text = '# Title\n\n---\n\nMiddle.\n\n***\n\n___\n\nSetext heading\n---\n\n```text\n---\n```\n\nEnd.\n'
    (root/'rules.md').write_text(text)
    ws.create_thread('rules.md', 0, 7, 'Before\n\n---\n\nAfter', 'Reviewer', ws.read('rules.md')['version'])
    page.goto(url); open_file(page, 'rules.md')
    expect(page.locator('.cm-content hr')).to_have_count(3)
    expect(page.locator('.comment-markdown hr')).to_have_count(1)
    page.locator('.cm-content').click(); page.keyboard.press('Control+Home')
    page.keyboard.press('ArrowDown'); page.keyboard.press('ArrowDown')
    expect(page.locator('.cm-content hr')).to_have_count(2)
    expect(page.locator('.cm-content')).to_contain_text('---')
    page.keyboard.press('Control+End')
    expect(page.locator('.cm-content hr')).to_have_count(3)
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        assert page.locator('.cm-content hr').first.evaluate('el=>getComputedStyle(el).borderTopWidth') == '1px'
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-preview hr')).to_have_count(3)
    expect(page.locator('.markdown-preview h2')).to_have_text('Setext heading')
    expect(page.locator('.markdown-preview pre')).to_have_text('---\n')
    page.locator('#mode').select_option('source')
    expect(page.locator('#surface hr')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('---')
    page.locator('.cm-content').click(); page.keyboard.press('Control+End')
    page.keyboard.insert_text('Added'); page.keyboard.press('Control+z')
    page.locator('#mode').select_option('live')
    expect(page.locator('.cm-content hr')).to_have_count(3)
    assert (root/'rules.md').read_text() == text


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
@pytest.mark.parametrize('mode', ['live', 'preview'])
def test_equations_use_available_width_before_scrolling(workspace_page, mode):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    # Wider than the prose measure, but fits in the expanded document pane.
    equation = r'\underbrace{' + '+'.join(['abcdefgh']*10) + r'}_{result}'
    (root/'math.md').write_text('Before.\n\n$$\n'+equation+'\n$$\n\nAfter.\n')
    page.goto(url); open_file(page, 'math.md'); page.locator('#mode').select_option(mode)
    page.set_viewport_size({'width': 1900, 'height': 1000})
    formula = page.locator('#surface .md-math-display')
    expect(formula.locator('.katex')).to_have_count(1)
    for theme in ['light', 'dark']:
        if page.locator('html').get_attribute('data-theme') != theme:
            page.locator('#theme').click()
        page.evaluate('document.fonts.ready')
        wide = formula.evaluate('''el=>({width:el.clientWidth,scroll:el.scrollWidth,
          size:parseFloat(getComputedStyle(el).fontSize),
          prose:parseFloat(getComputedStyle(el.closest('.md-formula')||el.parentElement).fontSize)})''')
        assert wide['width'] > 850
        assert wide['scroll'] <= wide['width']+1
        assert wide['size'] < wide['prose']
        page.set_viewport_size({'width': 960, 'height': 900})
        assert formula.evaluate('el=>el.scrollWidth>el.clientWidth')
        formula.evaluate('el=>el.scrollLeft=100')
        assert formula.evaluate('el=>el.scrollLeft') > 0
        assert page.locator('#surface').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        page.set_viewport_size({'width': 1900, 'height': 1000})


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_report_state_survives_tabs_modes_context_and_closes_cleanly(workspace_page):
    from playwright.sync_api import expect
    root, page, url, ws = workspace_page
    report = '<p>Passage.</p><input id="value"><button onclick="this.textContent=++window.count">Count</button><div style="height:3000px"></div><script>window.count=0</script>'
    (root/'one.html').write_text(report); (root/'two.html').write_text(report)
    (root/'notes.md').write_text('# Notes\n')
    ws.create_thread('one.html', 3, 11, 'Check report', 'Reviewer', ws.read('one.html')['version'])
    page.goto(url); open_file(page, 'one.html')
    frame = page.frame_locator('#html-preview')
    frame.locator('#value').fill('Keep this'); frame.locator('button').click()
    page.evaluate('window.reportFrame=document.querySelector("#html-preview")')
    frame.locator('body').evaluate('()=>window.scrollTo(0,650)')
    for other in ['notes.md', 'two.html', 'notes.md']:
        open_file(page, other)
        if other == 'two.html':
            frame.locator('#value').fill('Second report'); frame.locator('button').click(); frame.locator('button').click()
        page.locator('.tab[data-path="one.html"] .tab-name').click()
        expect(frame.locator('#value')).to_have_value('Keep this')
        expect(frame.locator('button')).to_have_text('1')
        assert page.evaluate('window.reportFrame===document.querySelector("#html-preview")')
        page.wait_for_function('''()=>document.querySelector('#html-preview')?.contentWindow!==null''')
        assert frame.locator('body').evaluate('()=>window.scrollY') == 650
    # Temporary immutable context and source-mode inspection reuse the same report.
    page.locator('.original-context').click(); page.locator('#context-return').click()
    expect(frame.locator('#value')).to_have_value('Keep this')
    page.locator('.original-context').click(); open_file(page, 'notes.md')
    page.locator('.tab[data-path="one.html"] .tab-name').click()
    expect(frame.locator('#value')).to_have_value('Keep this')
    page.locator('#html-toggle').click(); expect(page.locator('.cm-content')).to_be_visible()
    page.locator('#html-toggle').click(); expect(frame.locator('#value')).to_have_value('Keep this')
    page.locator('.tab[data-path="two.html"] .tab-name').click()
    expect(frame.locator('#value')).to_have_value('Second report'); expect(frame.locator('button')).to_have_text('2')
    page.get_by_role('button', name='Close one.html', exact=True).click()
    assert page.locator('iframe[data-report-surface]').count() == 1
    open_file(page, 'one.html'); expect(frame.locator('#value')).to_have_value('')
    # Clean external changes invalidate a hidden report; it must not reopen stale.
    open_file(page, 'notes.md'); (root/'one.html').write_text('<p>Updated report.</p>')
    page.wait_for_function('()=>!document.querySelectorAll("iframe[data-report-surface]")[1]')
    page.locator('.tab[data-path="one.html"] .tab-name').click()
    expect(frame.locator('p')).to_have_text('Updated report.')
    assert frame.locator('body').evaluate('()=>{try{return !!parent.document}catch{return false}}') is False


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_changes_checkpoints_and_agent_instructions_controls(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    git(root, 'init'); git(root, 'config', 'user.name', 'Test'); git(root, 'config', 'user.email', 'test@example.invalid')
    for name in ['selected.md', 'other.txt']:
        (root/name).write_text('Original\n')
    git(root, 'add', 'selected.md', 'other.txt'); git(root, 'commit', '-m', 'Initial')
    (root/'selected.md').write_text('Saved change\n')
    (root/'other.txt').write_text('Staged change\n'); git(root, 'add', 'other.txt')
    (root/'other.txt').write_text('Unstaged change\n'); (root/'new.txt').write_text('Untracked\n')
    page.goto(url); page.locator('#agent-open').click()
    expect(page.locator('#agent-dialog')).to_be_visible()
    instructions = page.locator('#agent-instructions').input_value()
    assert str(root) in instructions and url in instructions
    assert 'do not commit' in instructions and 'does not push' in instructions
    assert 'Only unattached' in instructions and 'Unicode code points' in instructions
    page.locator('#agent-dialog [data-close]').click()
    page.locator('#git-open').click()
    page.locator('#git-files input[value="selected.md"]').check()
    page.locator('#inspect-diff').click()
    expect(page.locator('#git-diff')).to_contain_text('+Saved change')
    page.locator('#checkpoint-name').fill('Selected checkpoint'); page.locator('#checkpoint').click()
    expect(page.locator('#git-dialog')).not_to_be_visible()
    expect(page.locator('#notice')).to_contain_text('Checkpoint')
    assert git(root, 'show', 'HEAD:selected.md') == 'Saved change'
    assert git(root, 'show', 'HEAD:other.txt') == 'Original'
    assert git(root, 'show', ':other.txt') == 'Staged change'
    assert (root/'other.txt').read_text() == 'Unstaged change\n'
    assert git(root, 'diff', '--cached', '--name-only') == 'other.txt'
    assert (root/'new.txt').read_text() == 'Untracked\n'
