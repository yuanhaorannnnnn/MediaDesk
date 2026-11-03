"""Extract only hash-pinned pure-Python wheels offline; never run pip or package code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--wheel-dir', type=Path, required=True)
parser.add_argument('--target', type=Path, required=True)
args = parser.parse_args()
lock = json.loads(Path(__file__).with_name('qr-packages.json').read_text())
# Validate all inputs and destinations before writing the overlay.
files = {}
for package in lock:
    wheel = args.wheel_dir / package['filename']
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != package['sha256']:
        raise SystemExit('QR dependency checksum mismatch: ' + wheel.name)
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            allowed = {package['package'], package['package'] + '-' + package['version'] + '.dist-info'}
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename
                    or not path.parts or path.parts[0] not in allowed
                    or (entry.external_attr >> 16) & 0o170000 not in (0, 0o100000, 0o040000)):
                raise SystemExit('Unsafe QR wheel entry: ' + entry.filename)
            if entry.is_dir():
                continue
            if path.suffix not in ('.py', '.txt') and '.dist-info' not in path.parts[0]:
                raise SystemExit('Unexpected QR wheel payload: ' + entry.filename)
            target = args.target / 'lib/python3.14/site-packages' / path
            if target in files or target.exists():
                raise SystemExit('QR overlay would overwrite a file: ' + str(target))
            files[target] = archive.read(entry)
        license_target = args.target / 'share/licenses' / package['package'] / 'LICENSE'
        if license_target.exists():
            raise SystemExit('QR license target already exists')
        files[license_target] = archive.read(package['license_path'])
for target, content in files.items():
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
print(json.dumps({'files': len(files), 'bytes': sum(map(len, files.values())), 'target': str(args.target)}))
