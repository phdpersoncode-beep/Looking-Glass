"""The same Unicode/newline operation fixtures run in Python and JavaScript."""
import json
from pathlib import Path
import pytest
from looking_glass.reviews import accepted, splice

CASES = json.loads((Path(__file__).parent / 'fixtures/review-operations.json').read_text())

@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_shared_review_operations(case):
    segments = [dict(kind='base', text=case['base'])]
    metadata = dict(author='Altay', role='human', at='2026-10-11', edit_id=1)
    for operation in case['operations']:
        segments = splice(segments, operation['start'], operation['end'], operation['insert'], metadata)
        if accepted(segments) == case['base']:
            segments = [dict(kind='base', text=case['base'])]
    assert accepted(segments) == case['content']
    assert [segment['text'] for segment in segments if segment['kind'] == 'delete'] == case['removed']
