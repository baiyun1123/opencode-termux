#!/usr/bin/env python3
"""Download fixed official host tools; verify archives before executing/extracting."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v2', ROOT/'scripts/v2.py')
v2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v2)


def lock():
    data = json.loads((ROOT/'config/toolchains-v2.json').read_text())
    c = v2.config()
    assert data['schema_version'] == 1 and data['host'] == 'linux-x86_64'
    for name, entry in data['archives'].items():
        assert entry['url'].startswith(('https://github.com/', 'https://ziglang.org/', 'https://dl.google.com/'))
        assert entry['format'] in ('zip', 'tar.xz')
        assert re.fullmatch(r'[A-Za-z0-9.+_-]+', entry['directory'])
        algorithm = 'sha256' if 'sha256' in entry else 'sha1'
        assert algorithm == 'sha256' or name == 'ndk', 'Only the vendor-published NDK SHA1 is allowed'
        assert re.fullmatch('[0-9a-f]{64}' if algorithm == 'sha256' else '[0-9a-f]{40}', entry[algorithm])
    for name, version in [('bun', c['bun']['version']), ('zig', c['toolchain']['zig']), ('ndk', c['toolchain']['ndk'])]:
        assert data['archives'][name]['version'] == version, name+' toolchain/application lock mismatch'
    assert data['archives']['llvm']['version'] == c['toolchain']['llvm']
    return data


def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def download(entry, path):
    algorithm = 'sha256' if 'sha256' in entry else 'sha1'
    if path.exists() and digest(path, algorithm) == entry[algorithm]: return
    path.unlink(missing_ok=True)
    partial = path.with_suffix(path.suffix+'.partial')
    partial.unlink(missing_ok=True)
    print('Downloading '+entry['url'], flush=True)
    try:
        subprocess.check_call(['curl','--silent','--show-error','--http1.1','--fail','--location',
                               '--retry','3','--retry-all-errors','--retry-max-time','600',
                               '--connect-timeout','30','--max-time','1800','--proto','=https',
                               '--proto-redir','=https','--output',str(partial),entry['url']])
    except subprocess.CalledProcessError:
        partial.unlink(missing_ok=True)
        raise
    if digest(partial, algorithm) != entry[algorithm]:
        partial.unlink(missing_ok=True)
        raise RuntimeError('Archive checksum mismatch: '+entry['url'])
    partial.replace(path)


def safe_zip(archive, destination):
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            assert not item.filename.startswith('/') and '..' not in Path(item.filename).parts, 'Unsafe ZIP entry'
    # unzip preserves Unix mode bits and symlinks required by NDK; Python's ZIP extraction doesn't.
    subprocess.check_call(['unzip','-q',str(archive),'-d',str(destination)])


def install(name, entry, downloads, tools):
    archive = downloads/(name+'-'+entry['version']+'.'+entry['format'])
    download(entry, archive)
    destination = tools/(name+'-'+entry['version'])
    stamp = destination/'.v2-toolchain.json'
    if stamp.is_file() and json.loads(stamp.read_text()) == entry: return destination
    if destination.exists():
        raise RuntimeError('Unrecognized tool directory; use a fresh V2_TOOLS_DIR: '+str(destination))
    with tempfile.TemporaryDirectory(prefix='.extract-', dir=tools) as tmp:
        tmp = Path(tmp)
        if entry['format'] == 'zip': safe_zip(archive, tmp)
        else:
            with tarfile.open(archive, 'r:xz') as t: t.extractall(tmp, filter='data')
        extracted = tmp/entry['directory']
        assert extracted.is_dir(), 'Archive root mismatch: '+str(extracted)
        extracted.rename(destination)
    stamp.write_text(json.dumps(entry, sort_keys=True)+'\n')
    return destination


def provision(selected):
    assert platform.system() == 'Linux' and platform.machine() in ('x86_64', 'AMD64'), 'Linux x86_64 host required'
    data = lock()
    work = Path(os.environ.get('WORK_DIR', ROOT/'build-v2')).resolve()
    tools = Path(os.environ.get('V2_TOOLS_DIR', work/'tools')).resolve()
    downloads = work/'downloads'
    for p in (tools,downloads,work/'logs'):p.mkdir(parents=True,exist_ok=True)
    installed = {}
    for name in selected:
        installed[name] = install(name,data['archives'][name],downloads,tools)
    # Official ZIPs contain bun only; package scripts also expect the bunx alias.
    if 'bun' in installed:
        alias = installed['bun']/'bunx'
        if not alias.exists(): alias.symlink_to('bun')
        assert alias.resolve() == (installed['bun']/'bun').resolve(), 'Unexpected bunx executable'
    env = {}
    if 'bun' in installed: env['HOST_BUN'] = str(installed['bun']/'bun')
    if 'zig' in installed: env['ZIG_BIN'] = str(installed['zig']/'zig')
    if 'ndk' in installed: env['ANDROID_NDK_HOME'] = str(installed['ndk'])
    if 'llvm' in installed: env['BUN_TOOLCHAIN_LLVM'] = str(installed['llvm'])
    paths = [str(installed[n]) for n in ('bun','zig') if n in installed]
    if 'llvm' in installed:paths.append(str(installed['llvm']/'bin'))
    envfile=work/'toolchain-env.sh'
    envfile.write_text(''.join('export '+n+'='+shlex.quote(v)+'\n' for n,v in env.items())+
                       'export PATH='+shlex.quote(':'.join(paths))+':"$PATH"\n')
    for key, value in env.items():
        if key in ('HOST_BUN','ZIG_BIN'):
            subprocess.check_call([value,'--version' if key=='HOST_BUN' else 'version'])
    if 'llvm' in installed:subprocess.check_call([str(installed['llvm']/'bin/clang'),'--version'])
    record={'archives': {n:dict(data['archives'][n], downloaded_sha256=digest(downloads/(n+'-'+data['archives'][n]['version']+'.'+data['archives'][n]['format']),'sha256')) for n in selected}}
    (work/'logs/toolchains.json').write_text(json.dumps(record,indent=2)+'\n')
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a') as f:
            for name,value in env.items():f.write(name+'='+value+'\n')
        with open(os.environ['GITHUB_PATH'],'a') as f:f.write('\n'.join(paths)+'\n')
    print('Toolchain environment: '+str(envfile))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--only',nargs='+',choices=['bun','zig','ndk','llvm'],default=['bun','zig','ndk','llvm'])
    p.add_argument('--validate',action='store_true')
    a=p.parse_args()
    if a.validate:lock();print('Toolchain download lock valid');return
    provision(a.only)


if __name__=='__main__':main()
