"""NOTEBOOK-01: staged delivery protects against incomplete, changed and failed writes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from module_exports import ModuleExports


class ModuleTransaction(unittest.TestCase):
    def test_missing_or_changed_stage_cannot_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=ModuleExports(root);token=store.begin({},['same','same'])
            store.stage(token,0,b'first',{})
            with self.assertRaisesRegex(ValueError,'尚未全部'):
                store.finish(token,root/'out','batch.zip',lambda r:None)
            self.assertFalse((root/'out').exists())
            store.stage(token,1,b'second',{})
            store.get(token)['parts'][1]['path'].write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError,'已变化'):
                store.finish(token,root/'out','batch.zip',lambda r:None)
            self.assertFalse((root/'out').exists());store.close()
            self.assertEqual(list(root.iterdir()),[])

    def test_write_failure_cleans_only_own_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);original=root/'report.md';original.write_bytes(b'original')
            store=ModuleExports(root);token=store.begin({},['../CON'])
            store.stage(token,0,b'html',{})
            self.assertNotIn('/',store.get(token)['names'][0])
            with patch('module_exports.shutil.copyfile',side_effect=PermissionError('occupied')):
                with self.assertRaises(PermissionError):store.finish(token,root/'out','one.html',lambda r:None)
            self.assertEqual(list((root/'out').iterdir()),[])
            self.assertEqual(original.read_bytes(),b'original');self.assertEqual(store.jobs,{})


if __name__=='__main__':unittest.main()
