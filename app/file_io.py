"""Standard-library file primitives shared by services, CLI and project commits.

Callers own authorization, locks, revision checks and backups.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class IncompleteOutputError(OSError):
    """A failed new-output write could not remove its own incomplete files."""
    code = 'OUTPUT_INCOMPLETE'

    def __init__(self, paths, error):
        self.incomplete_outputs = [str(path) for path in paths]
        super().__init__('Incomplete output requires cleanup: ' + ', '.join(self.incomplete_outputs) + '; ' + str(error))

def write_new(path: Path, data: bytes) -> None:
    """Create exclusively; a failed write removes only the file we created."""
    created=False
    try:
        with path.open('xb') as file:
            created=True
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except BaseException as error:
        if created:
            try:path.unlink(missing_ok=True)
            except OSError:
                raise IncompleteOutputError([path],error) from error
        raise

def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix='.tmp_', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tempname, path)
    finally:
        if os.path.exists(tempname): os.unlink(tempname)

def write_json(path: Path, obj: dict) -> None:
    atomic_write(path, (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
