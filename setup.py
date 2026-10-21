"""Package the existing application without a second copy of its source."""
from pathlib import Path
import sys
from setuptools import setup

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app'
sys.path.insert(0, str(APP))
from release_info import load_release
version = load_release()['python_version']
data = [p.relative_to(APP).as_posix() for p in APP.rglob('*')
        if p.is_file() and not {'__pycache__', 'projects', 'data', 'output'} & set(p.relative_to(APP).parts)
        and p.suffix not in ('.pyc', '.pyo')]
setup(version=version, packages=['html_report_studio'],
      package_dir={'html_report_studio': 'app'},
      package_data={'html_report_studio': data})

