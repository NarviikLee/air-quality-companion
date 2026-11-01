"""Qt 5.11 / PySide2 on Pi, with a PySide6 fallback for development.

QT_API=pyside2 or QT_API=pyside6 forces a binding. No mixing in one process.
"""
import importlib
import importlib.util
import os

requested = os.environ.get('QT_API', 'auto').lower()
if requested not in ('auto', 'pyside2', 'pyside6'):
    raise RuntimeError('QT_API must be auto, pyside2 or pyside6')
if requested == 'auto':
    BINDING = 'PySide2' if importlib.util.find_spec('PySide2') is not None else 'PySide6'
else:
    BINDING = {'pyside2': 'PySide2', 'pyside6': 'PySide6'}[requested]

QtCore = importlib.import_module(BINDING + '.QtCore')
QtGui = importlib.import_module(BINDING + '.QtGui')
QtWidgets = importlib.import_module(BINDING + '.QtWidgets')


def __getattr__(name):
    # QtTest is optional: the display itself does not require its apt package.
    if name == 'QTest':
        return importlib.import_module(BINDING + '.QtTest').QTest
    for module in (QtCore, QtGui, QtWidgets):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)


def run_app(app):
    return app.exec_() if BINDING == 'PySide2' else app.exec()
