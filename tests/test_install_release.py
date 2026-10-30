import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'packaging' / 'install-release.sh'
PACKAGE = 'mediadesk_0.1.0_all.deb'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.release = self.root / 'release'
        self.bin.mkdir()
        self.release.mkdir()
        source = self.root / 'package'
        (source / 'DEBIAN').mkdir(parents=True)
        (source / 'DEBIAN' / 'control').write_text(
            'Package: mediadesk\nVersion: 0.1.0\nArchitecture: all\n'
            'Maintainer: test <test@example.invalid>\nDescription: test\n')
        subprocess.run(['dpkg-deb', '--build', str(source), str(self.release / PACKAGE)],
                       check=True, stdout=subprocess.DEVNULL)
        self.write_checksum()
        self.command('gh', '''#!/usr/bin/python3
import os, pathlib, shutil, sys
if sys.argv[1:3] == ['auth', 'status']:
    sys.exit(int(os.environ.get('FAKE_AUTH_ERROR', '0')))
dest = pathlib.Path(sys.argv[sys.argv.index('--dir')+1])
for name in ('mediadesk_0.1.0_all.deb', 'SHA256SUMS'):
    shutil.copy(pathlib.Path(os.environ['FAKE_RELEASE']) / name, dest / name)
''')
        self.command('sudo', '''#!/usr/bin/python3
import os, sys
with open(os.environ['FAKE_SUDO_LOG'], 'a') as f:
    f.write(' '.join(sys.argv[1:])+'\\n')
sys.exit(int(os.environ.get('FAKE_APT_ERROR', '0')) if len(sys.argv) > 1 and sys.argv[1] == 'apt-get' else 0)
''')
        self.env = {**os.environ, 'PATH': f'{self.bin}:/usr/bin:/bin',
                    'FAKE_RELEASE': str(self.release),
                    'FAKE_SUDO_LOG': str(self.root / 'sudo.log'),
                    'TMPDIR': str(self.root)}
        self.os_release = self.root / 'os-release'
        self.os_release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')

    def command(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def write_checksum(self):
        digest = hashlib.sha256((self.release / PACKAGE).read_bytes()).hexdigest()
        (self.release / 'SHA256SUMS').write_text(f'{digest}  {PACKAGE}\n')

    def run_script(self):
        script = SCRIPT.read_text().replace('/etc/os-release', str(self.os_release))
        return subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True, env=self.env)

    def log(self):
        path = self.root / 'sudo.log'
        return path.read_text() if path.exists() else ''

    def test_success_from_pipe_delegates_dependency_resolution_to_apt(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('apt-get update', self.log())
        self.assertIn('apt-get install -y ', self.log())
        self.assertIn('安装完成', result.stdout)
        self.assertEqual(list(self.root.glob('mediadesk-install.*')), [])

    def test_bad_checksum_stops_before_privileged_action(self):
        (self.release / PACKAGE).write_bytes(b'corrupted')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-256 不匹配', result.stderr)
        self.assertEqual(self.log(), '')

    def test_unsupported_system_and_missing_auth_stop_before_install(self):
        self.os_release.write_text('ID=ubuntu\nVERSION_ID="22.04"\n')
        self.assertNotEqual(self.run_script().returncode, 0)
        self.os_release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
        self.env['FAKE_AUTH_ERROR'] = '1'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gh auth login', result.stderr)
        self.assertEqual(self.log(), '')

    def test_duplicate_checksum_stops_before_privileged_action(self):
        manifest = self.release / 'SHA256SUMS'
        manifest.write_text(manifest.read_text() * 2)
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('唯一', result.stderr)
        self.assertEqual(self.log(), '')

    def test_apt_failure_does_not_claim_success(self):
        self.env['FAKE_APT_ERROR'] = '1'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('安装完成', result.stdout)

    def test_invalid_version_is_rejected_before_install(self):
        self.env['MEDIADESK_VERSION'] = '../bad'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('版本号', result.stderr)
        self.assertEqual(self.log(), '')


if __name__ == '__main__':
    unittest.main()
