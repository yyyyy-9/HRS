"""READ-01: updating the reader keeps exact earlier exports trusted, not arbitrary scripts."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(ROOT))
from studio import audit_export,LEGACY_READER_SHA256


class ReaderTrust(unittest.TestCase):
    def test_previous_pf137_reader_remains_explicitly_trusted(self):
        """HTML exported before the H5/H6 change remains eligible for existing safe import."""
        self.assertIn('bb6ecd6c41f23bd618bbf109377f2895ec3fe35fa22c4d96b65da4ea818cb577',LEGACY_READER_SHA256)

    def test_current_reader_is_allowed_but_modified_script_is_rejected(self):
        """The presentation fix must not weaken the byte-exact script integrity check."""
        script=(ROOT/'web/report_reader.js').read_text('utf8')
        template='<!doctype html><html><body><script type="application/json" id="report-source">{"schema":"html-report-studio-v1","markdown":"# Test","assets":{}}</script><script id="hrs-reader-runtime">__READER__</script></body></html>'
        audit_export(template.replace('__READER__',script))
        with self.assertRaises(ValueError):audit_export(template.replace('__READER__',script+'\n/* altered */'))


if __name__=='__main__':unittest.main()
