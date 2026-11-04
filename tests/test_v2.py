import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(file):
    spec = importlib.util.spec_from_file_location(file.replace('-', '_'), ROOT/'scripts'/file)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


v2 = load('v2.py')
updates = load('check-updates-v2.py')
release = load('release-v2.py')
update_pr = load('update-pr-v2.py')


def synthetic_elf(path, shared=False, machine=183):
    """Minimal ELF fixture for archive validation; never execute as Android code."""
    interp = b'/system/bin/linker64\x00'
    header = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01'+b'\0'*9,
                         3, machine, 1, 0, 64 if not shared else 0, 0, 0, 64, 56, 0 if shared else 1, 0, 0, 0)
    segment = b'' if shared else struct.pack('<IIQQQQQQ', 3, 4, 120, 0, 0, len(interp), len(interp), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header+segment+(b'' if shared else interp)); path.chmod(0o755 if not shared else 0o644)


class ConfigTests(unittest.TestCase):
    def test_locked_config(self):
        c = v2.config()
        self.assertEqual(c['bun']['version'], '1.4.2')
        self.assertNotEqual(c['release']['version'], c['opencode']['version'])

    def test_bad_commit(self):
        c = v2.config(); c['bun']['commit'] = 'HEAD'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'config';p.write_text(json.dumps(c))
            with patch.object(v2, 'CONFIG', p), self.assertRaises(AssertionError): v2.config()

    def test_bad_versions(self):
        for value in ['../../oops', '1\nX: y', 'v1.0.0', '1.0.0;touch x']:
            c = v2.config();c['release']['version'] = value
            with tempfile.TemporaryDirectory() as d:
                p = Path(d)/'config';p.write_text(json.dumps(c))
                with patch.object(v2, 'CONFIG', p), self.assertRaises(AssertionError):v2.config()

    def test_cache_changes_with_lock(self):
        c = v2.config(); altered = copy.deepcopy(c);altered['bun']['commit'] = 'a'*40
        self.assertNotEqual(v2.key(c), v2.key(altered))

    def test_reject_host_elf(self):
        with self.assertRaises(AssertionError): v2.elf(Path('/bin/ls'))

    def test_reject_build_paths_even_without_debug_sections(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'libtest.so';synthetic_elf(p,True)
            p.write_bytes(p.read_bytes()+b'\0'+str(ROOT).encode()+b'/native/header.h\0')
            with self.assertRaisesRegex(AssertionError,'Build path leaked'):v2.elf(p,True)

    def test_reject_glibc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bun';synthetic_elf(p)
            with patch.object(v2, 'run', side_effect=['ELF64 AArch64 DYN (Shared object file)', 'NEEDED libc.so.6']), self.assertRaises(AssertionError):v2.elf(p)


class PatchTests(unittest.TestCase):
    def test_apply_already_applied_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d); subprocess.run(['git', 'init', '-q', str(src)], check=True)
            (src/'file').write_text('before\n')
            subprocess.run(['git', 'add', '.'], cwd=src, check=True)
            subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], cwd=src, check=True)
            patchfile = src/'change.patch'; patchfile.write_text('--- a/file\n+++ b/file\n@@ -1 +1 @@\n-before\n+after\n')
            v2.apply_patch(src, patchfile);v2.apply_patch(src, patchfile)
            self.assertEqual((src/'file').read_text(), 'after\n')
            (src/'file').write_text('unexpected\n')
            with self.assertRaises(RuntimeError): v2.apply_patch(src, patchfile)

    def test_patch_new_file_checked_with_temporary_index(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d); subprocess.run(['git', 'init', '-q', str(src)], check=True)
            (src/'original').write_text('original\n')
            subprocess.run(['git', 'add', '.'], cwd=src, check=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'], cwd=src, check=True)
            head = v2.run('git','rev-parse','HEAD',cwd=src)
            patchfile = src/'.git/add.patch'
            patchfile.write_text('diff --git a/newfile b/newfile\nnew file mode 100644\n--- /dev/null\n+++ b/newfile\n@@ -0,0 +1 @@\n+hello\n')
            v2.apply_patch(src, patchfile)
            with patch.object(v2, 'ROOT', src):
                v2.verify_tree(src, {'commit':head,'patches':[{'path':'.git/add.patch'}]})
                (src/'newfile').write_text('wrong\n')
                with self.assertRaises(subprocess.CalledProcessError):
                    v2.verify_tree(src, {'commit':head,'patches':[{'path':'.git/add.patch'}]})

    def test_dirty_tree_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d);subprocess.run(['git', 'init', '-q', str(src)],check=True)
            (src/'file').write_text('original\n')
            subprocess.run(['git', 'add', '.'],cwd=src,check=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],cwd=src,check=True)
            sha = v2.run('git','rev-parse','HEAD',cwd=src)
            (src/'file').write_text('dirty\n')
            with self.assertRaises(subprocess.CalledProcessError):v2.verify_tree(src, {'commit': sha, 'patches': []})


class UpdateTests(unittest.TestCase):
    def fixtures(self, changed=False):
        c = v2.config()
        repos = {'oven-sh/bun':'bun','anomalyco/opentui':'opentui'}
        def fetch(path):
            if path.startswith(c['opencode']['upstream']+'/'):
                return {'tag_name': 'v'+c['opencode']['source_version'], 'html_url':'https://example.invalid'}
            repo = path.split('/releases/')[0];name = repos[repo]
            return {'tag_name': c[name]['ref']}
        def resolve(repo, ref):
            return 'a'*40 if changed else c[repos.get(repo, 'opencode')]['commit']
        def read(repo, ref, path):
            return {'packageManager':'bun@1.4.2','workspaces':{'catalog':{'@opentui/core':'0.5.10','@opentui/solid':'0.5.10'}}} if path == 'package.json' else {'dependencies':{'@opentui/core':'catalog:','@opentui/solid':'catalog:'}}
        return c, fetch, resolve, read

    def test_no_updates_success(self):
        r = updates.inspect(*self.fixtures())
        self.assertFalse(r['has_updates']);self.assertFalse(r['errors'])
        self.assertTrue(r['compatibility']['dependency_versions_match'])

    def test_candidate_does_not_change_lock(self):
        c,f,r,d = self.fixtures(True); original = copy.deepcopy(c)
        result = updates.inspect(c,f,r,d)
        self.assertTrue(result['has_updates']);self.assertEqual(c, original)
        self.assertEqual(result['compatibility']['android_runtime'], 'NOT TESTED')

    def test_lookup_errors_are_reported(self):
        c,f,r,d = self.fixtures()
        def fail(path): raise RuntimeError('HTTP 403')
        result = updates.inspect(c,fail,r,d)
        self.assertTrue(result['errors']);self.assertIn('HTTP 403', updates.report(result))

    def test_dependency_mismatch(self):
        c,f,r,d = self.fixtures();c['bun']['version']='9.0.0'
        self.assertFalse(updates.inspect(c,f,r,d)['compatibility']['dependency_versions_match'])


class UpdatePRTests(unittest.TestCase):
    def test_permission_denial_is_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); (base/'build-v2').mkdir()
            (base/'build-v2/updates.json').write_text(json.dumps({'errors': [], 'has_updates': True}))
            (base/'build-v2/updates.md').write_text('Report\n')
            previous = Path.cwd()
            try:
                os.chdir(base)
                with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY':str(base/'summary'),'GITHUB_REPOSITORY':'owner/repo'}), patch.object(update_pr, 'gh', side_effect=RuntimeError('403 PR permission denied')):
                    with self.assertRaisesRegex(RuntimeError, '403'):update_pr.main()
            finally: os.chdir(previous)

    def test_same_candidate_closed_pr_is_not_recreated(self):
        result = {'errors': [], 'has_updates': True}
        fingerprint = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        existing = [{'number':1,'state':'CLOSED','body':'<!-- v2-candidate:'+fingerprint+' -->'}]
        with tempfile.TemporaryDirectory() as d:
            base = Path(d);(base/'build-v2').mkdir()
            (base/'build-v2/updates.json').write_text(json.dumps(result))
            (base/'build-v2/updates.md').write_text('Report\n')
            previous = Path.cwd()
            try:
                os.chdir(base)
                with patch.dict(os.environ, {'GITHUB_STEP_SUMMARY':str(base/'summary'),'GITHUB_REPOSITORY':'owner/repo'}), patch.object(update_pr,'gh',return_value=json.dumps(existing)) as gh, patch.object(update_pr.subprocess,'check_call') as mutate:
                    update_pr.main()
                    self.assertEqual(gh.call_count,1);mutate.assert_not_called()
            finally: os.chdir(previous)


class ReleaseTests(unittest.TestCase):
    def fixture(self):
        c = v2.config(); record = {'config': c, 'repository_commit':'abc','outputs':{'opencode2.bin':'hash'}}
        report = {'build_run_id':'123','outputs':record['outputs'],'approval':'approved','tested_by':'tester','tested_at':'2026-11-04',
                  'devices':[{'model':'fixture','android':'11','api':30,'log_reference':'reviewed/log', 'checks':dict.fromkeys(release.CHECKS,'PASS')}]}
        return c,record,report

    def test_complete_evidence(self):
        c,r,e=self.fixture();self.assertTrue(release.evidence(c,r,e,'123','abc'))

    def test_no_device_or_failed_interaction(self):
        c,r,e=self.fixture();e['devices'][0]['checks']['plan_tab']='NOT TESTED'
        with self.assertRaises(AssertionError):release.evidence(c,r,e,'123','abc')
        e['devices']=[]
        with self.assertRaises(AssertionError):release.evidence(c,r,e,'123','abc')

    def test_wrong_run_binary_and_source(self):
        for mutate in [lambda e:e.update(build_run_id='456'),lambda e:e.update(outputs={}),lambda e:e['devices'][0].update(api=28)]:
            c,r,e=self.fixture();mutate(e)
            with self.assertRaises(AssertionError):release.evidence(c,r,e,'123','abc')


@unittest.skipUnless(all(shutil.which(t) for t in ('readelf','zip','xz','dpkg-deb')), 'Packaging tools unavailable')
class PackagingTests(unittest.TestCase):
    def test_packages_reproducible_and_corruption_rejected(self):
        self.packages('1.0.3')

    def test_prerelease_pacman_version(self):
        self.packages('1.0.4-rc.1')

    def packages(self, release_version):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            synthetic_elf(work/'dist/opencode2.bin');synthetic_elf(work/'dist/bun-android/bun');synthetic_elf(work/'libopentui.so', True)
            logs=work/'logs';logs.mkdir()
            c=v2.config();c['release']['version']=release_version
            config_path=work/'versions.json';config_path.write_text(json.dumps(c))
            for n in ('bun','opentui','opencode'):
                s=c[n];(logs/f'source-{n}.json').write_text(json.dumps({'component':n,'commit':s['commit'],'version':s['version'],'patches':{p['path']:v2.sha(ROOT/p['path']) for p in s['patches']}}))
            env=dict(os.environ,WORK_DIR=d,SOURCE_DATE_EPOCH='1700000000',V2_CONFIG=str(config_path))
            def command(name, ok=True):
                r=subprocess.run(['bash',str(ROOT/'scripts'/name)],env=env,capture_output=True,text=True)
                self.assertEqual(r.returncode==0, ok, r.stdout+r.stderr)
            command('make-packages-v2.sh');command('verify-packages-v2.sh')
            flat=work/'dist/flat'
            wrapper=flat/'opencode2'
            (flat/'opencode2.bin').write_text('#!/bin/sh\nprintf "%s|%s" "$OPENTUI_LIB_PATH" "$*"\n')
            foreign=work/'foreign/libexec/opencode2';foreign.mkdir(parents=True)
            (foreign/'libopentui.so').write_text('foreign')
            (foreign/'opencode2.bin').write_text('#!/bin/sh\necho foreign\n');(foreign/'opencode2.bin').chmod(0o755)
            result=subprocess.check_output(['sh',str(wrapper),'arg with space'],env=dict(env,PREFIX=str(work/'foreign')),text=True)
            self.assertEqual(result, str(flat/'libopentui.so')+'|arg with space')
            before=(work/'packages/SHA256SUMS').read_bytes()
            command('make-packages-v2.sh');command('verify-packages-v2.sh')
            self.assertEqual(before,(work/'packages/SHA256SUMS').read_bytes())
            deb=next((work/'packages').glob('*.deb'));deb.write_bytes(deb.read_bytes()+b'corruption')
            command('verify-packages-v2.sh',False)


if __name__ == '__main__': unittest.main()
