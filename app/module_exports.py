"""Staged module HTML delivery. No partial output on validation failure."""
from pathlib import Path
import hashlib
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from project_workspace import is_link

MAX_MODULES = 500
MAX_BATCH_BYTES = 512 * 1024 * 1024
BATCH_LIFETIME_SECONDS = 30 * 60


class ModuleExports:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.jobs = {}

    def close(self):
        for token in list(self.jobs):
            self.cancel(token)

    def cancel(self, token):
        job = self.jobs.pop(token, None)
        if job:
            job['temporary'].cleanup()

    def begin(self, context, titles):
        now = time.monotonic()
        for token, job in list(self.jobs.items()):
            if now - job['created'] > BATCH_LIFETIME_SECONDS:
                self.cancel(token)
        if len(self.jobs) >= 4:
            raise ValueError('仍有分册导出在进行，请先完成或取消')
        if not isinstance(titles, list) or not 1 <= len(titles) <= MAX_MODULES or any(not isinstance(t, str) or len(t) > 500 for t in titles):
            raise ValueError(f'分册列表无效或超过 {MAX_MODULES} 项')
        names = []
        for i, title in enumerate(titles, 1):
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:80] or '专题'
            names.append(f'{i:03d}_{safe}.html')
        temporary = tempfile.TemporaryDirectory(prefix='.hrs-modules-', dir=self.workspace)
        token = uuid.uuid4().hex
        self.jobs[token] = dict(context=context, names=names, temporary=temporary, created=now, parts={}, bytes=0)
        return token

    def get(self, token):
        job = self.jobs.get(token)
        if job is None or time.monotonic() - job['created'] > BATCH_LIFETIME_SECONDS:
            self.cancel(token)
            raise ValueError('分册导出会话已失效，请重新导出')
        return job

    def stage(self, token, index, raw, request):
        job = self.get(token)
        if type(index) is not int or not 0 <= index < len(job['names']) or index in job['parts']:
            raise ValueError('分册序号无效或重复提交')
        if job['bytes'] + len(raw) > MAX_BATCH_BYTES:
            raise ValueError(f'本批分册超过 {MAX_BATCH_BYTES // (1024 * 1024)} MiB，请减少本次勾选数量')
        path = Path(job['temporary'].name) / job['names'][index]
        path.write_bytes(raw)
        job['parts'][index] = dict(path=path, request=request, sha256=hashlib.sha256(raw).hexdigest())
        job['bytes'] += len(raw)

    def finish(self, token, output, filename, verify):
        job = self.get(token)
        if len(job['parts']) != len(job['names']):
            raise ValueError('分册尚未全部生成，未写入任何交付文件')
        def check():
            for part in job['parts'].values():
                verify(part['request'])
                if hashlib.sha256(part['path'].read_bytes()).hexdigest() != part['sha256']:
                    raise RuntimeError('分册暂存内容已变化，导出已取消')
        check()
        output = Path(output)
        if is_link(output):
            raise ValueError('output 不能为符号链接')
        output.mkdir(exist_ok=True)
        target = output / filename
        if target.exists():
            raise RuntimeError('导出目标已存在，请重新生成文件名')
        pending = output / ('.' + uuid.uuid4().hex + '.tmp')
        try:
            if len(job['names']) == 1:
                shutil.copyfile(job['parts'][0]['path'], pending)
            else:
                with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for i, name in enumerate(job['names']):
                        archive.write(job['parts'][i]['path'], name)
            check()
            pending.replace(target)
            try:
                check()
            except Exception:
                target.unlink()
                raise
            return target, list(job['names'])
        finally:
            pending.unlink(missing_ok=True)
            self.cancel(token)
