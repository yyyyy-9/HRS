"""Path memory and the real COM setup, without opening a user dialog."""
import ctypes,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import native_picker as picker

class PickerMemory(unittest.TestCase):
    def test_selected_directories_survive_restart_and_cancel_is_not_a_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();a=root/'导入 目录';b=root/'保存 目录';a.mkdir();b.mkdir();file=a/'稿件.md';file.write_text('# 稿件','utf8')
            history=picker.PickerHistory(root);history.remember('document-import',file);history.remember('project-parent',b,True)
            before=history.path.read_bytes();history.remember('document-import',None)
            self.assertEqual(history.path.read_bytes(),before)
            restored=picker.PickerHistory(root);self.assertEqual(restored.get('document-import'),a);self.assertEqual(restored.get('project-parent'),b)
            file.unlink();a.rmdir();self.assertIsNone(restored.get('document-import'))

    @unittest.skipUnless(os.name=='nt','Windows COM integration')
    def test_real_common_dialog_sets_folder_file_filters_and_releases_on_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folders in (True,False):
                seen=[]
                def cancel(dialog,call,owner):
                    options=ctypes.c_uint32();self.assertGreaterEqual(call(dialog,10,[ctypes.POINTER(ctypes.c_uint32)],[ctypes.byref(options)]),0)
                    self.assertEqual(bool(options.value&0x20),folders);self.assertTrue(options.value&0x40);seen.append(True)
                    return ctypes.c_long(0x800704c7).value
                with patch.object(picker,'_show',side_effect=cancel):
                    self.assertIsNone(picker._dialog(purpose='test-folder' if folders else 'test-file',title='HRS 自有选择器专项',folder=folders,filters=[('Markdown','*.md')],initial=Path(tmp)))
                self.assertEqual(seen,[True])

    def test_history_failure_does_not_replace_old_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);history=picker.PickerHistory(root);history.remember('project-open',root,True);before=history.path.read_bytes()
            with patch.object(picker.os,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):history.remember('project-parent',root,True)
            self.assertEqual(history.path.read_bytes(),before);self.assertFalse(list(root.glob('*.tmp')))

if __name__=='__main__':unittest.main()
