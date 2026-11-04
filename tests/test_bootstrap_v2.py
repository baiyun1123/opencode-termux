import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'scripts/bootstrap-v2.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_lock_versions_and_hashes(self):
        data=bootstrap.lock()
        self.assertEqual(data['archives']['llvm']['version'],'21.1.8')
        self.assertIn('sha256',data['archives']['bun'])

    def test_checksum_mismatch_never_becomes_installable(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'tool.zip'
            entry={'url':'https://example.invalid/tool.zip','sha256':'0'*64}
            def corrupt(args):Path(args[args.index('--output')+1]).write_bytes(b'corrupt')
            with patch.object(bootstrap.subprocess,'check_call',side_effect=corrupt):
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):bootstrap.download(entry,target)
            self.assertFalse(target.exists())
            self.assertFalse(Path(str(target)+'.partial').exists())

    def test_verified_cache_does_not_download(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'tool.zip';target.write_bytes(b'valid')
            entry={'sha256':hashlib.sha256(b'valid').hexdigest()}
            with patch.object(bootstrap.subprocess,'check_call') as download:
                bootstrap.download(entry,target);download.assert_not_called()

    def test_zip_traversal_rejected_before_unzip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('../escaped','bad')
            with patch.object(bootstrap.subprocess,'check_call') as unzip:
                with self.assertRaises(AssertionError):bootstrap.safe_zip(p,Path(d)/'out')
                unzip.assert_not_called()

    def test_application_and_toolchain_mismatch(self):
        c=bootstrap.v2.config();c=copy.deepcopy(c);c['bun']['version']='1.4.4'
        with patch.object(bootstrap.v2,'config',return_value=c):
            with self.assertRaisesRegex(AssertionError,'mismatch'):bootstrap.lock()

    def test_preflight_collects_multiple_missing_tools(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,WORK_DIR=d,HOST_BUN='/missing-bun',ZIG_BIN='/missing-zig',
                     ANDROID_NDK_HOME='/missing-ndk',BUN_TOOLCHAIN_LLVM='/missing-llvm')
            r=subprocess.run(['bash',str(ROOT/'scripts/preflight-v2.sh')],env=env,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('Host Bun missing',r.stderr)
            self.assertIn('Zig missing',r.stderr)
            self.assertIn('LLVM 21 missing',r.stderr)
            self.assertIn('preflight check(s) failed',r.stderr)


if __name__=='__main__':unittest.main()
