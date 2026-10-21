from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
from . import __version__

ROOT = Path(__file__).resolve().parents[1]

def default_roots():
    bundle_hrs=ROOT.parent/'HTML_Report_Studio';bundle_wps=ROOT.parent/'WPS_Document_Tool'
    if bundle_hrs.is_dir() and bundle_wps.is_dir():return bundle_hrs,bundle_wps
    workspace=next((p for p in ROOT.parents if (p/'PROJECT_STATE.md').is_file()),None)
    declaration=workspace/'integration/release.json' if workspace else None
    if declaration and declaration.is_file():
        try:
            projects=json.loads(declaration.read_text('utf8'))['projects']
            roots=tuple((workspace/projects[name]).resolve() for name in ('HTML_Report_Studio','WPS_Document_Tool'))
            if any(not path.is_relative_to(workspace) or not path.is_dir() for path in roots):raise ValueError('Project path is missing or outside workspace')
            return roots
        except (KeyError,TypeError,ValueError) as exc:
            raise BridgeError('Invalid integration/release.json project roots; use explicit --hrs-root and --wps-root') from exc
    # An independent checkout has no workspace declaration. Expect adjacent
    # projects or explicit CLI/environment roots, never a dated local version.
    return bundle_hrs,bundle_wps


class BridgeError(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Runtime:
    hrs: Path
    wps: Path
    browser: str | None = None
    node: str | None = None
    pandoc: str | None = None

    def __post_init__(self):
        self.hrs, self.wps = Path(self.hrs).resolve(), Path(self.wps).resolve()
        if (self.hrs / 'app').is_dir():
            self.hrs /= 'app'
        if not (self.hrs / 'report_contract.py').is_file():
            raise BridgeError('HRS root must contain report_contract.py or app/')
        if not (self.hrs/'render_profile.py').is_file() or not (self.hrs/'web/render_profile.js').is_file() or not (self.hrs/'object_clipboard.py').is_file():
            raise BridgeError(f'Bridge {__version__} requires compatible HRS source and output policy')
        if not (self.wps / 'config.json').is_file():
            raise BridgeError('WPS root must contain config.json')
        if not (self.wps/'src/wps_pipeline/figure_layout.py').is_file():
            raise BridgeError(f'Bridge {__version__} requires WPS with shared figure-layout recognition')
        sys.path.insert(0, str(self.hrs))
        sys.path.insert(0, str(self.wps / 'src'))
        self.contract = importlib.import_module('report_contract')
        if Path(self.contract.__file__).resolve().parent != self.hrs:
            raise BridgeError('Do not mix two HRS versions in the same process')
        wps_module=importlib.import_module('wps_pipeline')
        if Path(wps_module.__file__).resolve().parent!=self.wps/'src/wps_pipeline':
            raise BridgeError('Do not mix two WPS versions in the same process')
        self.node = self.node or os.environ.get('HRS_BRIDGE_NODE') or shutil.which('node')
        self.browser = self.browser or os.environ.get('CHROMIUM_PATH')
        self.pandoc = self.pandoc or os.environ.get('PANDOC_PATH') or shutil.which('pandoc')

    def analyze(self, raw, assets=None):
        return self.contract.analyze(raw.decode('utf8'), assets=assets)


def source_contract_valid(ir):
    """Only the structural entry gate; the browser model validates output semantics."""
    from agent_readonly import project
    result=project(ir)
    return result.get('sourceContractValid',result.get('safeToCompile',False))


def new_path(path):
    path = Path(path).resolve()
    if path.exists():
        raise BridgeError('Output already exists; choose a new path: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
