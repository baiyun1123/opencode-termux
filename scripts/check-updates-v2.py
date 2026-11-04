#!/usr/bin/env python3
"""Report candidate updates. Never modify the production lock or apply patches."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('v2', Path(__file__).with_name('v2.py'))
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def api(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'opencode-termux-v2-update-check'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urlopen(Request('https://api.github.com/repos/' + path, headers=headers), timeout=30) as response:
        return json.load(response)


def commit(repo, ref):
    return api(f'{repo}/commits/{quote(ref, safe="")}')['sha']


def contents(repo, ref, path):
    item = api(f'{repo}/contents/{path}?ref={quote(ref, safe="")}')
    return json.loads(base64.b64decode(item['content']))


def inspect(c, fetch=api, resolve=commit, read=contents):
    result = {'schema_version': 1, 'updates': [], 'errors': [], 'compatibility': {}, 'production_config_modified': False}
    def check(label, fn):
        try:
            return fn()
        except Exception as exc:
            result['errors'].append({'check': label, 'error': str(exc)})
            return None
    upstream = check('opencode-release', lambda: fetch(c['opencode']['upstream']+'/releases/latest'))
    if upstream and not upstream.get('prerelease') and not upstream.get('draft'):
        current = c['opencode']['source_version']
        if upstream['tag_name'].removeprefix('v') != current:
            result['updates'].append({'component': 'opencode-release', 'current': current,
                                      'candidate': upstream['tag_name'], 'url': upstream['html_url'],
                                      'action': 'Review and port Android commits; never substitute upstream directly'})
    for name in ('opencode', 'bun', 'opentui'):
        s = c[name]
        repo = urlparse(s['repository']).path.strip('/').removesuffix('.git')
        if name == 'opencode':
            candidate_ref = s['ref']
            candidate = check(name+'-branch', lambda: resolve(repo, candidate_ref))
        else:
            latest = check(name+'-release', lambda: fetch(repo+'/releases/latest'))
            candidate_ref = latest['tag_name'] if latest else None
            candidate = check(name+'-commit', lambda: resolve(repo, candidate_ref)) if candidate_ref else None
        if candidate and candidate != s['commit']:
            result['updates'].append({'component': name, 'current': s['version'], 'current_commit': s['commit'],
                                      'candidate': candidate_ref, 'candidate_commit': candidate,
                                      'action': 'Requires dependency, patch, build and Android device validation'})
        if name == 'opencode' and candidate:
            def dependencies():
                root = read(repo, candidate, 'package.json')
                cli = read(repo, candidate, 'packages/cli/package.json')
                expected = {'bun': 'bun@'+c['bun']['version'], '@opentui/core': c['opentui']['version'], '@opentui/solid': c['opentui']['version']}
                actual = {'bun': root['packageManager']}
                for dep in ('@opentui/core', '@opentui/solid'):
                    value = cli['dependencies'][dep]
                    actual[dep] = root['workspaces']['catalog'][dep] if value == 'catalog:' else value
                return {'commit': candidate, 'actual': actual, 'expected': expected,
                        'dependency_versions_match': actual == expected,
                        'patch_compatibility': 'NOT TESTED', 'android_runtime': 'NOT TESTED'}
            result['compatibility'] = check('android-dependencies', dependencies) or {}
    result['has_updates'] = bool(result['updates'])
    return result


def report(result):
    lines = ['# OpenCode 2 Android update candidates', '',
             'Review only. Production versions and patches have not been changed.', '',
             'Full build and Android runtime: NOT TESTED.', '']
    for update in result['updates']:
        lines.append('- ' + json.dumps(update, sort_keys=True))
    if not result['updates']: lines.append('No updates found.')
    lines += ['', '## Dependency compatibility', '', '```json', json.dumps(result['compatibility'], indent=2), '```']
    for error in result['errors']: lines.append(f"\nCHECK FAILED: {error['check']}: {error['error']}")
    return '\n'.join(lines)+'\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='build-v2/updates.json')
    p.add_argument('--report', default='build-v2/updates.md')
    a = p.parse_args()
    result = inspect(v2.config())
    for path, data in ((a.output, json.dumps(result, indent=2)+'\n'), (a.report, report(result))):
        file = Path(path); file.parent.mkdir(parents=True, exist_ok=True); file.write_text(data)
    print(json.dumps(result))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
