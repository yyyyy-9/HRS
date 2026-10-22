"""PASTE-01: native clipboard binding, image fidelity and refusal boundaries."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from clipboard_document import html_fragment, prepare_document, rtf_pictures
from studio import check_image
from clipboard_graphics import _open_clipboard

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAI0lEQVR4nGPUjephoAZgooopDKMGEQNGA5swGA0jwmDwhREAMgYBM6jouUsAAAAASUVORK5CYII=')


def cf_html(fragment):
    fragment=fragment.encode('utf8')
    header='Version:1.0\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n'
    start=len(header.format(0,0).encode('ascii'))
    return header.format(start,start+len(fragment)).encode('ascii')+fragment+b'\0'


def snapshot(html,text='前文\r\n后文',rtf=None):
    result={13:(text+'\0').encode('utf-16le'),'HTML Format':cf_html(html)}
    if rtf is not None:result['Rich Text Format']=rtf
    return result


class WordClipboardContract(unittest.TestCase):
    def test_clipboard_acquisition_waits_for_copy_and_fails_bounded(self):
        user=Mock();user.OpenClipboard.side_effect=[False,False,True]
        with patch('clipboard_graphics.time.sleep'):_open_clipboard(user)
        user.OpenClipboard.side_effect=None;user.OpenClipboard.return_value=False
        with patch('clipboard_graphics.time.sleep'),self.assertRaisesRegex(RuntimeError,'占用'):_open_clipboard(user)

    def test_local_image_bytes_and_utf8_fragment(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'图 中文.png';path.write_bytes(PNG)
            url=path.as_uri();html=f'<p>前文😀</p><img src="{url}"><p>后文</p>'
            result=prepare_document(snapshot(html),'前文\n后文',check_image)
            self.assertEqual(result['html'],html)
            resource=result['images'][url]
            self.assertEqual(base64.b64decode(next(iter(resource['assets'].values()))['base64']),PNG)
            self.assertTrue(resource['path'].startswith('assets/'))

    def test_rtf_image_order_fallback_and_deduplication(self):
        url='file:///C:/missing/clip_image001.png'
        hex_data=PNG.hex().encode()
        rtf=b'{\\rtf1{\\*\\shppict{\\pict\\pngblip{\\*\\blipuid 1234} '+hex_data+b'}}{\\nonshppict{\\pict\\wmetafile8 aabb}}}'
        self.assertEqual(rtf_pictures(rtf),[('pngblip',PNG)])
        result=prepare_document(snapshot(f'<p>前文</p><img src="{url}">',rtf=rtf),'前文\n后文',check_image)
        self.assertEqual(base64.b64decode(next(iter(result['images'][url]['assets'].values()))['base64']),PNG)

    def test_rtf_binary_braces_are_not_structure(self):
        data=b'{}\\binary'
        rtf=b'{\\rtf1{\\pict\\pngblip\\bin'+str(len(data)).encode()+b' '+data+b'}}'
        self.assertEqual(rtf_pictures(rtf),[('pngblip',data)])

    def test_changed_clipboard_refuses_before_file_read(self):
        with self.assertRaisesRegex(ValueError,'已变化'):
            prepare_document(snapshot('<img src="file:///C:/not-read.png">'),'另一次复制',check_image)

    def test_missing_image_count_and_corrupt_data_refused(self):
        url='file:///C:/missing/picture.png'
        with self.assertRaisesRegex(ValueError,'一一对应'):
            prepare_document(snapshot(f'<img src="{url}"><img src="{url}">',rtf=b'{\\rtf1{\\pict\\pngblip '+PNG.hex().encode()+b'}}'),'前文\n后文',check_image)
        with self.assertRaises(ValueError):
            prepare_document(snapshot('<img src="data:image/png;base64,YmFk">'),'前文\n后文',check_image)

    def test_external_images_are_not_downloaded(self):
        with self.assertRaisesRegex(ValueError,'外部图片'):
            prepare_document(snapshot('<img src="https://example.invalid/a.png">'),'前文\n后文',check_image)

    def test_rtf_original_preferred_to_html_preview_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'preview.png';path.write_bytes(b'not-the-original-image')
            url=path.as_uri()
            rtf=b'{\\rtf1{\\pict\\pngblip '+PNG.hex().encode()+b'}}'
            result=prepare_document(snapshot(f'<img src="{url}">',rtf=rtf),'前文\n后文',check_image)
            asset=next(iter(result['images'][url]['assets'].values()))
            self.assertEqual(base64.b64decode(asset['base64']),PNG)

    def test_text_and_table_only_snapshot_needs_no_image(self):
        result=prepare_document(snapshot('<p>前文</p><table><tr><td>后文</td></tr></table>'),'前文\n后文',check_image)
        self.assertEqual(result['images'],{})

    def test_cf_html_offsets_must_be_byte_exact_and_bounded(self):
        html='<p>中文😀</p>'
        self.assertEqual(html_fragment(cf_html(html)),html)
        with self.assertRaisesRegex(ValueError,'范围无效'):
            html_fragment(b'StartFragment:0000000050\nEndFragment:9999999999\n')

    def test_malformed_rtf_is_not_silently_accepted(self):
        for raw in (b'{\\rtf1{\\pict\\pngblip zz}}',b'{\\rtf1{\\pict\\bin999 aa}}',b'{\\rtf1{\\pict\\pngblip aabb}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):rtf_pictures(raw)


if __name__=='__main__':unittest.main()
