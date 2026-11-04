#!/usr/bin/env python3
"""Fail-closed device evidence gate; called after verifying downloaded packages."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

spec = importlib.util.spec_from_file_location('v2', Path(__file__).with_name('v2.py'))
v2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v2)
CHECKS = ['version', 'help', 'tui_start', 'input', 'project', 'subprocess', 'background', 'ctrl_b', 'plan_tab', 'terminal_restore']


def evidence(c, record, report, run_id, revision):
    assert record['config'] == c, 'Release config differs from build'
    assert record['repository_commit'] == revision, 'Build repository commit mismatch'
    assert report['build_run_id'] == str(run_id), 'Device evidence refers to another run'
    assert report['outputs'] == record['outputs'], 'Device evidence refers to another binary'
    assert report['approval'] == 'approved' and report['tested_by'].strip() and report['tested_at'].strip()
    devices = report['devices']
    assert devices, 'No tested devices'
    for d in devices:
        assert d['model'].strip() and d['android'].strip()
        assert d['api'] >= c['toolchain']['android_api'], 'Unsupported device API'
        assert all(d['checks'].get(k) == 'PASS' for k in CHECKS), 'Incomplete Android device regression results'
        assert d['log_reference'].strip(), 'Device logs required'
    return devices


def main():
    c = v2.config()
    out = Path('build-v2/packages')
    record = json.loads((out/'build-record.json').read_text())
    report = json.loads(Path('device-results.json').read_text())
    devices = evidence(c, record, report, os.environ['BUILD_RUN_ID'], os.environ['BUILD_COMMIT'])
    version = c['release']['version']
    tag = f'opencode2-v{version}'
    assert re.fullmatch(r'opencode2-v[0-9A-Za-z.+~_-]+', tag)
    lines = [f'# OpenCode 2 Android {version} (pre-release)', '',
             f"Application: {c['opencode']['version']}; package release: {version}", '',
             '## Sources and toolchain', '', '```json', json.dumps(c, indent=2), '```',
             '', '## Verified devices', '', json.dumps(devices, indent=2), '',
             '## Known limitations', '',
             'File watching is disabled on Android. fff uses its JavaScript fallback. Linux CI cannot verify TUI/PTY behavior.',
             '', '## Installation', '', '```sh', 'sha256sum -c SHA256SUMS',
             f'apt install ./opencode2_{version}_aarch64.deb', 'opencode2 --version', 'opencode2', '```',
             '', '## Checksums', '', '```', (out/'SHA256SUMS').read_text().strip(), '```',
             '', '## Changed files in build commit', '', '```',
             subprocess.check_output(['git', 'show', '--stat', '--oneline', os.environ['BUILD_COMMIT']], text=True).strip(), '```']
    Path('release-notes-v2.md').write_text('\n'.join(lines)+'\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f: f.write('tag='+tag+'\n')


if __name__ == '__main__': main()
