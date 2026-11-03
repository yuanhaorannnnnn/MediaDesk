"""Check only an isolated overlay; matrix generation must not import image libraries."""
import hashlib
import importlib.abc
import importlib.metadata
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
site = root / 'lib/python3.14/site-packages'
sys.path.insert(0, str(site))
sys.dont_write_bytecode = True
class NoImageLibraries(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PIL', 'png'}:
            raise ModuleNotFoundError('Image library deliberately unavailable: ' + fullname)
sys.meta_path.insert(0, NoImageLibraries())
import qrcode
import colorama
for module in (qrcode, colorama):
    assert Path(module.__file__).resolve().is_relative_to(site), module.__file__
qr = qrcode.QRCode(box_size=1, border=4)
qr.add_data('https://example.invalid/mediadesk-synthetic-login')
qr.make(fit=True)
matrix = qr.get_matrix()
assert len(matrix) == 41 and all(len(row) == 41 for row in matrix)
assert not any(any(row) for row in matrix[:4] + matrix[-4:])
assert all(not any(row[:4] + row[-4:]) for row in matrix)
print(json.dumps(dict(qrcode_version=importlib.metadata.version('qrcode'),
                      colorama_version=importlib.metadata.version('colorama'),
                      module=qrcode.__file__, matrix_size=len(matrix),
                      matrix_sha256=hashlib.sha256(bytes(value for row in matrix for value in row)).hexdigest(),
                      pillow_or_png_loaded=any(name.split('.')[0] in {'PIL', 'png'} for name in sys.modules))))
