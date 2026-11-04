#!/usr/bin/env python3
"""Locked source and artifact provenance; Python stdlib only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get('V2_CONFIG', ROOT / 'config/versions-v2.json')).resolve()


def run(*args, **kw):
    return subprocess.check_output(args, text=True, **kw).strip()


def config():
    c = json.loads(CONFIG.read_text())
    assert c['schema_version'] == 1, 'Unsupported config schema'
    for name in ('opencode', 'bun', 'opentui'):
        s = c[name]
        assert re.fullmatch(r'[0-9a-f]{40}', s['commit']), f'{name}: full commit SHA required'
        assert s['repository'].startswith('https://github.com/'), 'GitHub HTTPS repository required'
        for p in s['patches']:
            assert p['version'] == s['version'], f'{name}: patch version mismatch'
            assert (ROOT / p['path']).resolve().is_relative_to(ROOT / 'patches'), 'Invalid patch path'
            assert (ROOT / p['path']).is_file(), 'Missing patch'
    for v in (c['release']['version'], c['opencode']['version']):
        assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[.+~-][0-9A-Za-z.+~-]+)?', v), 'Invalid version'
    assert isinstance(c['release']['revision'], int) and c['release']['revision'] > 0
    assert c['toolchain']['arch'] == 'aarch64' and c['toolchain']['android_api'] >= 29
    return c


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(c):
    h = hashlib.sha256(json.dumps(c, sort_keys=True).encode())
    paths = {ROOT / p['path'] for n in ('opencode', 'bun', 'opentui') for p in c[n]['patches']}
    paths.update((ROOT / 'scripts').glob('*v2*'))
    paths.add(ROOT / 'config/toolchains-v2.json')
    paths.update([Path(__file__), ROOT / 'scripts/build-bun-android.sh', ROOT / 'scripts/build-opencode2-android.sh'])
    for p in sorted(paths):
        if p.is_file():
            h.update(str(p.relative_to(ROOT)).encode() + p.read_bytes())
    return h.hexdigest()


def environment(c):
    values = {'OPENCODE_VERSION': c['opencode']['version'], 'OPENCODE_CHANNEL': c['opencode']['channel'],
              'RELEASE_VERSION': c['release']['version'], 'PACKAGE_REVISION': str(c['release']['revision']),
              'PACMAN_VERSION': c['release']['version'].replace('-', '_').replace('~', '_'),
              'BUN_VERSION': c['bun']['version'], 'OPENTUI_VERSION': c['opentui']['version'],
              'ZIG_VERSION': c['toolchain']['zig'], 'LLVM_VERSION': c['toolchain']['llvm'], 'NDK_VERSION': c['toolchain']['ndk'],
              'ANDROID_API': str(c['toolchain']['android_api']), 'V2_CACHE_KEY': key(c)}
    for name, value in values.items():
        print(f'export {name}={shlex.quote(value)}')


def apply_patch(src, patch):
    opts = {'cwd': src, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if subprocess.call(['git', 'apply', '--check', str(patch)], **opts) == 0:
        subprocess.check_call(['git', 'apply', str(patch)], cwd=src)
        print(f'Applied {patch.name}')
    elif subprocess.call(['git', 'apply', '--reverse', '--check', str(patch)], **opts) == 0:
        print(f'Already applied: {patch.name}')
    else:
        raise RuntimeError(f'Incompatible or partially applied patch: {patch.name}')


def verify_tree(src, spec):
    """Require exactly HEAD + configured patches, including staged changes."""
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(d) / 'index'))
        subprocess.check_call(['git', 'read-tree', spec['commit']], cwd=src, env=env)
        for p in spec['patches']:
            subprocess.check_call(['git', 'apply', '--cached', str(ROOT / p['path'])], cwd=src, env=env)
        unexpected = run('git', 'ls-files', '--others', '--exclude-standard', cwd=src, env=env)
        assert not unexpected, f'Untracked build inputs in source: {unexpected}'
        tree = run('git', 'write-tree', cwd=src, env=env)
        subprocess.check_call(['git', 'diff', '--exit-code', tree, '--'], cwd=src, env=env)


def verify_source(src, name, c):
    s = c[name]
    assert run('git', 'rev-parse', 'HEAD', cwd=src) == s['commit'], f'{name}: wrong HEAD'
    verify_tree(src, s)
    if name == 'opencode':
        pkg = json.loads((src / 'package.json').read_text())
        cli = json.loads((src / 'packages/cli/package.json').read_text())
        assert pkg['packageManager'] == 'bun@' + c['bun']['version'], 'Host/target Bun mismatch'
        for dep in ('@opentui/core', '@opentui/solid'):
            v = cli['dependencies'][dep]
            if v == 'catalog:':
                v = pkg['workspaces']['catalog'][dep]
            assert v == c['opentui']['version'], f'{dep}: incompatible dependency {v}'
        assert cli['version'] == s['source_version'], 'Source/application version mismatch'
        build = (src / 'packages/cli/script/build.ts').read_text()
        for marker in ('abi: "android"', 'OPENCODE_BUN_RUNTIME', 'OPENTUI_LIB_PATH', 'opentui-android-assets'):
            assert marker in build, f'Android build capability missing: {marker}'
        assert (src / 'bun.lock').is_file(), 'Frozen dependency lock missing'
    elif name == 'opentui':
        assert json.loads((src / 'packages/core/package.json').read_text())['version'] == s['version']


def prepare(name, c):
    s = c[name]
    envname = {'bun': 'BUN_SRC', 'opentui': 'OPENTUI_SRC', 'opencode': 'OPENCODE_WORKTREE'}[name]
    default = Path(os.environ.get('WORK_DIR', ROOT / 'build-v2')) / 'sources' / name
    src = Path(os.environ.get(envname, default)).resolve()
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        subprocess.check_call(['git', 'init', str(src)])
        subprocess.check_call(['git', 'remote', 'add', 'origin', s['repository']], cwd=src)
    assert run('git', 'remote', 'get-url', 'origin', cwd=src) == s['repository'], 'Source origin mismatch'
    if subprocess.call(['git', 'cat-file', '-e', s['commit'] + '^{commit}'], cwd=src,
                       stderr=subprocess.DEVNULL) != 0:
        subprocess.check_call(['git', '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=30', 'fetch', '--depth=1', 'origin', s['commit']], cwd=src, timeout=120)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=src, capture_output=True, text=True)
    if head.returncode == 0 and head.stdout.strip() != s['commit']:
        raise RuntimeError(f'{name}: existing source has another HEAD; use a new WORK_DIR')
    if head.returncode != 0:
        subprocess.check_call(['git', 'checkout', '--detach', s['commit']], cwd=src)
    for p in s['patches']:
        apply_patch(src, ROOT / p['path'])
    verify_source(src, name, c)
    if name == 'opentui':
        # Versioned archive ships in the locked tree; no floating Git dependency.
        subprocess.check_call(['sh', 'packages/native/scripts/prepare-zig-deps.sh'], cwd=src)
        assert (src / 'packages/native/zig-deps/yoga/yoga/Yoga.h').is_file(), 'Missing vendored Yoga'
    record = {'component': name, 'commit': s['commit'], 'version': s['version'],
              'patches': {p['path']: sha(ROOT / p['path']) for p in s['patches']}}
    logs = Path(os.environ.get('WORK_DIR', ROOT / 'build-v2')) / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f'source-{name}.json').write_text(json.dumps(record, indent=2) + '\n')


def elf(path, shared=False):
    header = run('readelf', '-h', str(path))
    assert 'ELF64' in header and 'AArch64' in header, f'Not ARM64 ELF: {path}'
    dynamic = run('readelf', '-d', str(path))
    assert '(RPATH)' not in dynamic and '(RUNPATH)' not in dynamic, 'Embedded library search path'
    forbidden = ('libc.so.6', 'ld-linux', 'libpthread.so.0', 'libm.so.6', 'libstdc++.so.6')
    assert not any(x in dynamic for x in forbidden), 'glibc dependency in Android output'
    assert 'DYN (Shared object file)' in header or 'DYN (Position-Independent Executable file)' in header, 'Expected PIE/shared ELF'
    if not shared:
        assert '/system/bin/linker64' in run('readelf', '-l', str(path)), 'Missing Android interpreter'
    return dynamic


def record(c):
    work = Path(os.environ.get('WORK_DIR', ROOT / 'build-v2'))
    dist = Path(os.environ.get('DIST_DIR', work / 'dist'))
    lib = Path(os.environ.get('OPENTUI_LIB', work / 'libopentui.so'))
    files = {'opencode2.bin': dist / 'opencode2.bin', 'libopentui.so': lib,
             'bun': dist / 'bun-android/bun'}
    for n, p in files.items():
        elf(p, n == 'libopentui.so')
    sources = {n: json.loads((work / 'logs' / f'source-{n}.json').read_text()) for n in ('opencode', 'bun', 'opentui')}
    out = {'repository_commit': run('git', 'rev-parse', 'HEAD', cwd=ROOT),
           'cache_key': key(c), 'config': c, 'sources': sources,
           'outputs': {n: sha(p) for n, p in files.items()}, 'android_runtime': 'NOT TESTED'}
    (dist / 'build-record.json').write_text(json.dumps(out, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['env', 'validate', 'key', 'prepare', 'verify-source', 'elf', 'record', 'cache-check', 'cache-stamp'])
    p.add_argument('argument', nargs='?')
    a = p.parse_args()
    c = config()
    if a.command == 'env': environment(c)
    elif a.command == 'key': print(key(c))
    elif a.command == 'prepare':
        for name in ([a.argument] if a.argument else ['bun', 'opentui', 'opencode']): prepare(name, c)
    elif a.command == 'verify-source':
        n = a.argument
        envname = {'bun': 'BUN_SRC', 'opentui': 'OPENTUI_SRC', 'opencode': 'OPENCODE_WORKTREE'}[n]
        verify_source(Path(os.environ[envname]), n, c)
    elif a.command == 'elf': elf(Path(a.argument), a.argument.endswith('.so'))
    elif a.command in ('cache-check', 'cache-stamp'):
        p = Path(a.argument)
        stamp = p.with_name(p.name + '.provenance.json')
        expected = {'cache_key': key(c), 'sha256': sha(p)}
        if a.command == 'cache-stamp':
            stamp.write_text(json.dumps(expected) + '\n')
        else:
            assert json.loads(stamp.read_text()) == expected, 'Stale cached artifact; remove artifact and rebuild'
    elif a.command == 'record': record(c)
    else: print('Configuration valid; Android runtime: NOT TESTED')


if __name__ == '__main__':
    main()
