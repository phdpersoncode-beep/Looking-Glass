"""Ignore rules update the explorer without disrupting an open document."""
import os

import pytest

from test_requested_features import workspace_page, open_file

pytestmark = [pytest.mark.browser, pytest.mark.skipif(
    not os.environ.get('LOOKING_GLASS_BROWSER'), reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page', ['chromium', 'firefox'], indirect=True)
def test_ignore_refresh_keeps_open_document(workspace_page):
    from playwright.sync_api import expect
    root, page, url, _ = workspace_page
    (root / 'main.py').write_text('answer = 42\n')
    (root / 'outputs').mkdir()
    (root / 'outputs/result.txt').write_text('generated output\n')
    rules = root / '.looking.ignore'
    rules.write_text('outputs/\n')
    page.goto(url)
    open_file(page, 'main.py')
    expect(page.locator('.file-entry[data-path="outputs/result.txt"]')).to_have_count(0)
    expect(page.locator('.file-entry[data-path=".looking.ignore"]')).to_be_visible()
    page.locator('.cm-content').click()
    page.keyboard.press('Control+End')
    page.keyboard.insert_text('# unsaved work\n')
    rules.write_text('*.py\n')
    page.locator('#refresh-files').click()
    expect(page.locator('.file-entry[data-path="main.py"]')).to_have_count(0)
    expect(page.locator('.file-entry[data-path="outputs/result.txt"]')).to_have_count(1)
    expect(page.locator('#document-name')).to_have_text('main.py')
    expect(page.locator('.cm-content')).to_contain_text('# unsaved work')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    page.locator('.cm-content').click()
    page.keyboard.press('Control+s')
    expect(page.locator('#dirty')).to_have_text('')
    assert '# unsaved work' in (root / 'main.py').read_text()
    rules.unlink()
    page.locator('#refresh-files').click()
    expect(page.locator('.file-entry[data-path="main.py"]')).to_be_visible()
    expect(page.locator('.file-entry[data-path=".looking.ignore"]')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('# unsaved work')
