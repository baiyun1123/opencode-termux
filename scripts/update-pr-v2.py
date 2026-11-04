#!/usr/bin/env python3
"""One persistent review PR; a failed PR permission is a failed check with a summary."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def main():
    summary = Path(os.environ['GITHUB_STEP_SUMMARY'])
    report = Path('build-v2/updates.md').read_text()
    with summary.open('a') as f: f.write(report)
    result = json.loads(Path('build-v2/updates.json').read_text())
    if result['errors']: raise RuntimeError('Update lookup incomplete; see report')
    if not result['has_updates']: return
    branch = 'automation/opencode2-update-candidates'
    repo = os.environ['GITHUB_REPOSITORY']
    existing = json.loads(gh('pr', 'list', '--repo', repo, '--head', branch, '--state', 'all', '--limit', '100', '--json', 'number,state,body'))
    fingerprint = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    marker = '<!-- v2-candidate:' + fingerprint + ' -->'
    if any(marker in pr.get('body', '') for pr in existing):
        return
    Path('build-v2/updates.md').write_text(report + '\n' + marker + '\n')
    opened = [pr for pr in existing if pr['state'] == 'OPEN']
    subprocess.check_call(['git', 'switch', '-c', branch])
    target = Path('config/update-candidates-v2.json')
    # Stable JSON: no timestamp churn, no changes to versions-v2.json.
    target.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    subprocess.check_call(['git', 'config', 'user.name', 'github-actions[bot]'])
    subprocess.check_call(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'])
    subprocess.check_call(['git', 'add', str(target)])
    # Compare to the last candidate branch, avoiding identical daily commits.
    remote = subprocess.run(['git', 'fetch', 'origin', branch], capture_output=True)
    lease = ''
    if remote.returncode == 0:
        lease = gh_git('rev-parse', 'FETCH_HEAD')
        old = subprocess.run(['git', 'show', 'FETCH_HEAD:config/update-candidates-v2.json'], capture_output=True, text=True)
        if old.returncode == 0 and old.stdout == target.read_text() and existing:
            return
    subprocess.check_call(['git', 'commit', '-m', 'chore(v2): record upstream update candidates for review'])
    subprocess.check_call(['git', 'push', f'--force-with-lease=refs/heads/{branch}:{lease}', 'origin', f'HEAD:refs/heads/{branch}'])
    if opened:
        gh('pr', 'edit', str(opened[0]['number']), '--repo', repo, '--body-file', 'build-v2/updates.md')
    else:
        gh('pr', 'create', '--repo', repo, '--head', branch, '--base', os.environ['DEFAULT_BRANCH'],
           '--title', 'chore(v2): review upstream Android update candidates', '--body-file', 'build-v2/updates.md', '--draft')


def gh_git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as f:
            f.write(f'\n## Update PR failed\n\n{exc}\n\nCheck contents:write, pull-requests:write and repository Actions PR policy.\n')
        raise
