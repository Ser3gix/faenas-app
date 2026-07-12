import sys
import os

diag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_env.txt')

with open(diag_path, 'w', encoding='utf-8') as fh:
    fh.write(sys.executable + '\n')
    try:
        import flask
        fh.write('FLASK_OK ' + flask.__version__ + '\n')
    except Exception as exc:
        fh.write('FLASK_FAIL ' + repr(exc) + '\n')

print(sys.executable)
try:
    import flask
    print("FLASK_OK", flask.__version__)
except Exception as exc:
    print("FLASK_FAIL", repr(exc))

from PyInstaller.__main__ import run

run([
    '--noconfirm',
    '--clean',
    '--onedir',
    '--name', 'Faenas',
    '--add-data', 'templates;templates',
    '--add-data', 'static;static',
    '--add-data', 'datos;datos',
    'server2.py',
])
