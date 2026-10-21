"""HRS installed resources; starting the server always requires an explicit CLI call."""
from pathlib import Path
import sys

# Portable modules share one resource directory. Installed/module entry points
# use that same import boundary; importing the package never starts a service.
_app = str(Path(__file__).resolve().parent)
if _app not in sys.path:
    sys.path.insert(0, _app)

