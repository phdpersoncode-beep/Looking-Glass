#!/usr/bin/env python3
"""Apply exact-text replacements to an existing Looking Glass review draft.

The human sees agent insertions in blue and removals struck through, and
approves the draft in the browser. The file on disk is never written. This
helper never starts a draft; it refuses unless the review is already pending.

Edits file: JSON array, applied in order against the running draft text:
  [{"old": "exact unique passage", "new": "replacement", "occurrence": 1}]
"occurrence" (one-based) is required only when "old" repeats.

Example:
  lg_draft_edit.py 3 --root ~/proj --edits-file /tmp/edits.json --author Claude
Prints JSON with the review ID, new version, and per-edit offsets.
A 409 means the draft changed meanwhile: reread it and rebuild the edits.
"""
import argparse
import json
import subprocess
import sys


def cli(base, *args, stdin=None):
    proc = subprocess.run([*base, *args], capture_output=True, text=True, input=stdin)
    if proc.returncode:
        sys.exit(f'looking-glass {" ".join(args)} failed: {proc.stderr.strip()}')
    return json.loads(proc.stdout)


def locate(text, old, occurrence):
    hits, i = [], text.find(old)
    while i != -1:
        hits.append(i)
        i = text.find(old, i + 1)
    if not old or not hits:
        sys.exit(f'Passage empty or not found in draft: {old[:120]!r}')
    if occurrence is None and len(hits) > 1:
        sys.exit(f'Passage repeats {len(hits)} times; set "occurrence": {old[:120]!r}')
    n = occurrence or 1
    if n > len(hits):
        sys.exit(f'Occurrence {n} requested but passage appears {len(hits)} times: {old[:120]!r}')
    return hits[n - 1]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('review', type=int, help='Pending review ID (from lg_watch.py output or `agent review list`).')
    p.add_argument('--edits-file', required=True, help='JSON array of {old,new[,occurrence]}; - for stdin.')
    p.add_argument('--root', required=True)
    p.add_argument('--url')
    p.add_argument('--author', default='Claude')
    args = p.parse_args()

    base = ['looking-glass', 'agent', '--root', args.root, *(['--url', args.url] if args.url else [])]
    edits = json.load(sys.stdin if args.edits_file == '-' else open(args.edits_file, encoding='utf-8'))
    draft = cli(base, 'review', 'read', str(args.review))
    if draft['status'] != 'pending':
        sys.exit(f'Review {args.review} is {draft["status"]}; edit the file on disk instead.')
    # Offsets are Python str indices, which count Unicode code points as the API requires.
    text, operations, applied = draft['content'], [], []
    for edit in edits:
        old, new = edit['old'], edit['new']
        start = locate(text, old, edit.get('occurrence'))
        end = start + len(old)
        operations.append({'start': start, 'end': end, 'insert': new})
        applied.append({'start': start, 'end': end, 'old': old[:80], 'new': new[:80]})
        text = text[:start] + new + text[end:]

    result = cli(base, 'review', 'edit', str(args.review), '--version', draft['version'],
                 '--author', args.author, '--operations-file', '-', stdin=json.dumps(operations))
    print(json.dumps({'review_id': args.review, 'path': draft['path'], 'version': result.get('version'),
                      'edits': applied}, ensure_ascii=False))


if __name__ == '__main__':
    main()
