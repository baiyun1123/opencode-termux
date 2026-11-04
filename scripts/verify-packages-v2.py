#!/usr/bin/env python3
"""Inspect all three payloads without installing or executing target code."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

spec = importlib.util.spec_from_file_location('v2', Path(__file__).with_name('v2.py'))
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def verify(out):
    c = v2.config()
    version = c['release']['version']
    pv = version.replace('-', '_').replace('~', '_')
    rev = c['release']['revision']
    deb = f'opencode2_{version}_aarch64.deb'
    pac = f'opencode2-{pv}-{rev}-aarch64.pkg.tar.xz'
    zipname = f'opencode2-{version}-android-aarch64.zip'
    names = [deb, pac, zipname]
    lines = (out / 'SHA256SUMS').read_text().splitlines()
    assert len(lines) == 3 and {x.split('  ')[1] for x in lines} == set(names), 'Unexpected checksum entries'
    for line in lines:
        digest, name = line.split('  ')
        assert digest == v2.sha(out / name), 'Checksum mismatch: ' + name
    record = json.loads((out / 'build-record.json').read_text())
    assert record['cache_key'] == v2.key(c) and record['config'] == c, 'Provenance/config mismatch'
    prefix = 'data/data/com.termux/files/usr/'
    installed = {prefix+'bin/opencode2', prefix+'libexec/opencode2/opencode2.bin', prefix+'libexec/opencode2/libopentui.so'}
    payloads = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        control = subprocess.check_output(['dpkg-deb', '-f', str(out/deb), 'Package', 'Version', 'Architecture'], text=True)
        assert 'Package: opencode2' in control and f'Version: {version}' in control and 'Architecture: aarch64' in control
        subprocess.check_call(['dpkg-deb', '-x', str(out/deb), str(root/'deb')])
        payloads.append({str(p.relative_to(root/'deb')): (p.read_bytes(), p.stat().st_mode) for p in (root/'deb').rglob('*') if p.is_file()})
        assert set(payloads[-1]) == installed, 'DEB layout mismatch'
        with tarfile.open(out/pac) as t:
            members = t.getmembers()
            assert all(not m.issym() and not m.islnk() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in members), 'Unsafe tar member'
            payload = {m.name: (t.extractfile(m).read(), m.mode) for m in members if m.isfile()}
        info = payload.pop('.PKGINFO')[0].decode()
        assert f'pkgver = {pv}-{rev}\n' in info and 'arch = aarch64\n' in info
        assert set(payload) == installed, 'Pacman layout mismatch'
        payloads.append(payload)
        with zipfile.ZipFile(out/zipname) as z:
            assert z.testzip() is None
            assert set(z.namelist()) == {'opencode2', 'opencode2.bin', 'libopentui.so'}
            flat = {i.filename: (z.read(i), i.external_attr >> 16) for i in z.infolist()}
        mapping = {prefix+'bin/opencode2': 'opencode2', prefix+'libexec/opencode2/opencode2.bin': 'opencode2.bin', prefix+'libexec/opencode2/libopentui.so': 'libopentui.so'}
        payloads.append({p: flat[n] for p, n in mapping.items()})
        for payload in payloads:
            for p, n in mapping.items():
                data, mode = payload[p]
                assert data == payloads[0][p][0], 'Payload differs between package formats'
                assert mode & 0o777 == (0o644 if n.endswith('.so') else 0o755), f'Incorrect permissions: {p}'
                for forbidden in (str(v2.ROOT).encode(), b'/home/guy/', b'/workspace/'):
                    assert forbidden not in data, f'Build path leaked into {n}'
                if n != 'opencode2':
                    f = root / n
                    f.write_bytes(data)
                    v2.elf(f, n.endswith('.so'))
                    assert hashlib.sha256(data).hexdigest() == record['outputs'][n], 'Output provenance mismatch'
        wrapper = payloads[0][prefix+'bin/opencode2'][0]
        assert b'OPENTUI_LIB_PATH' in wrapper and b'libexec/opencode2' in wrapper
    print('PASS: DEB/Pacman/ZIP payload, metadata, permissions, ARM64 ELF, dependencies, checksums and provenance')
    print('Android runtime: NOT TESTED')


if __name__ == '__main__':
    verify(Path(sys.argv[1]).resolve())
