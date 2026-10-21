"""Explicit offline core update/rollback. Install files and user data stay separate.

No network, model calls, process killing or silent source/project writes.
"""
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
import zipfile
HOST=json.loads(Path(__file__).with_name('config.json').read_text('utf8'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_file(path):
    if path.is_symlink():
        raise ValueError('链接不能作为更新元数据')
    return json.loads(path.read_text('utf-8-sig'))


def checked_files(folder):
    manifest = json_file(folder / 'MANIFEST.json')
    expected = {item['path']: item for item in manifest['files']}
    if len(expected) != len(manifest['files']):
        raise ValueError('核心清单重复')
    actual = set()
    for file in folder.rglob('*'):
        if file.is_symlink() or getattr(file,'is_junction',lambda:False)():
            raise ValueError('核心中含链接')
        if file.is_file() and file != folder/'MANIFEST.json':
            actual.add(file.relative_to(folder).as_posix())
    if actual != set(expected):
        raise ValueError('核心文件清单不一致')
    for name, item in expected.items():
        raw = (folder / name).read_bytes()
        if digest(raw) != item['sha256'] or len(raw) != item['bytes']:
            raise ValueError('核心文件校验失败：' + name)
    identity = json_file(folder / 'release.json')
    capabilities=json_file(folder/'host_capabilities.json')
    if capabilities!={'schema':'hrs-host-capabilities-v1','desktop_protocol':HOST['protocol']}:
        raise ValueError('目标核心不支持当前宿主协议')
    if any(identity[k] != manifest[k] for k in ('version', 'package_revision')):
        raise ValueError('核心版本不一致')
    return identity


def layout(root):
    value = json_file(root / 'DESKTOP_MANIFEST.json')
    if value.get('schema') != 'hrs-desktop-layout-v1' or value.get('protocol') != HOST['protocol']:
        raise ValueError('不支持的桌面布局')
    return value


def selected(root, sha=None):
    base = root / 'resources/hrs'
    info = layout(root)
    if sha is None:
        pointer = base / 'active.json'
        sha = json_file(pointer)['sha256'] if pointer.exists() else info['core_manifest_sha256']
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('核心指针无效')
    folder = base / 'app' if sha == info['core_manifest_sha256'] else base / 'updates' / sha / 'app'
    if digest((folder / 'MANIFEST.json').read_bytes()) != sha:
        raise ValueError('核心指针摘要不匹配')
    identity = checked_files(folder)
    support = json_file(base / 'word_support/MANIFEST.json')
    if digest((folder / 'web/bridge_model.js').read_bytes()) != support['browser_model_sha256']:
        raise ValueError('目标核心需要其他Word组件，请使用完整发行包')
    return sha, folder, identity


def package_plan(root, package):
    base_sha, _, identity = selected(root)
    with zipfile.ZipFile(package) as archive:
        items = [i for i in archive.infolist() if not i.is_dir()]
        names = [i.filename for i in items]
        if len(items) > 1500 or sum(i.file_size for i in items) > 256 * 1024 * 1024:
            raise ValueError('更新包过大')
        if len({n.casefold() for n in names}) != len(names):
            raise ValueError('更新包含重复路径')
        for item in items:
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or any(p in ('.', '..') for p in name.parts) or
                    ':' in item.filename or '\\' in item.filename or
                    item.filename not in ('UPDATE.json',) and not item.filename.startswith('app/') or
                    (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('更新包路径无效')
        contract = json.loads(archive.read('UPDATE.json'))
        if (contract.get('schema') != 'hrs-core-update-v1' or contract.get('host_protocol') != HOST['protocol'] or
                contract.get('base_core_sha256') != base_sha):
            raise ValueError('更新包不适用于当前核心或宿主')
        manifest_raw = archive.read('app/MANIFEST.json')
        if digest(manifest_raw) != contract['target_core_sha256']:
            raise ValueError('更新包核心摘要不匹配')
        manifest = json.loads(manifest_raw)
        records = manifest['files']
        expected = {'app/' + r['path'] for r in records} | {'app/MANIFEST.json', 'UPDATE.json'}
        if set(names) != expected or len(expected) != len(records) + 2:
            raise ValueError('更新包文件清单不一致')
        for record in records:
            raw = archive.read('app/' + record['path'])
            if digest(raw) != record['sha256'] or len(raw) != record['bytes']:
                raise ValueError('更新包文件损坏：' + record['path'])
        target_identity = json.loads(archive.read('app/release.json'))
        capabilities=json.loads(archive.read('app/host_capabilities.json'))
        if capabilities!={'schema':'hrs-host-capabilities-v1','desktop_protocol':HOST['protocol']}:
            raise ValueError('目标核心不支持当前宿主协议')
        if target_identity != contract['target_identity'] or any(target_identity[k] != manifest[k] for k in ('version', 'package_revision')):
            raise ValueError('目标身份不一致')
        support = json_file(root / 'resources/hrs/word_support/MANIFEST.json')
        if digest(archive.read('app/web/bridge_model.js')) != support['browser_model_sha256']:
            raise ValueError('目标核心与Word组件不匹配')
    return {'ok': True, 'summary': identity['version'] + ' → ' + target_identity['version'],
            'package_sha256': digest(package.read_bytes()), 'contract': contract}


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'\0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('应用或更新正在运行，请先安全退出') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8'))
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute(root, data_dir, *, package=None, expected_sha=None, rollback=False, plan_only=False):
    root = root.resolve(strict=True); data_dir = data_dir.resolve()
    if data_dir == root or data_dir.is_relative_to(root):
        raise ValueError('用户数据必须位于安装资源之外')
    base = root / 'resources/hrs'
    # Reject redirected install-managed directories before creating any stage.
    for target in (base, base / 'updates', base / 'active.json', base / 'previous.json'):
        if target.is_symlink() or getattr(target, 'is_junction', lambda: False)():
            raise ValueError('更新目录不能是链接')
    if rollback:
        old_sha, _, _ = selected(root)
        previous = json_file(base / 'previous.json')
        target_sha, _, identity = selected(root, previous['sha256'])
        plan = {'ok': True, 'summary': '回退到 ' + identity['version'], 'target_core_sha256': target_sha}
    else:
        plan = package_plan(root, package)
        old_sha = plan['contract']['base_core_sha256']; target_sha = plan['contract']['target_core_sha256']
    if plan_only:
        return plan
    if not rollback and (not expected_sha or expected_sha != plan['package_sha256']):
        raise ValueError('必须提供已审查更新包SHA256')
    with ExitStack() as locks:
        locks.enter_context(lock(base / '.desktop-update.lock'))
        locks.enter_context(lock(data_dir / 'data/.portable-instance.lock'))
        if selected(root)[0] != old_sha:
            raise RuntimeError('核心已经变化，请重新审查更新')
        if not rollback:
            if digest(package.read_bytes()) != expected_sha:
                raise RuntimeError('更新包在确认后发生变化')
            updates = base / 'updates'; updates.mkdir(exist_ok=True)
            destination = updates / target_sha
            if destination.exists():
                selected(root, target_sha)
            else:
                stage = updates / ('.stage-' + uuid.uuid4().hex); stage.mkdir()
                try:
                    with zipfile.ZipFile(package) as archive:
                        for item in archive.infolist():
                            if item.is_dir() or not item.filename.startswith('app/'):
                                continue
                            output = stage.joinpath(*PurePosixPath(item.filename).parts)
                            output.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(item) as src, output.open('xb') as dest:
                                shutil.copyfileobj(src, dest, 1024 * 1024)
                    checked_files(stage / 'app')
                    os.replace(stage, destination)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
        atomic_json(base / 'previous.json', {'sha256': old_sha})
        atomic_json(base / 'active.json', {'sha256': target_sha})
    return {**plan, 'applied': True, 'active_core_sha256': target_sha, 'user_projects_unchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path,default=Path(os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or Path.home())/HOST['data_directory'])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--package', type=Path)
    group.add_argument('--rollback', action='store_true')
    parser.add_argument('--sha256'); parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.root, args.data_dir, package=args.package, expected_sha=args.sha256,
                                 rollback=args.rollback, plan_only=args.plan), ensure_ascii=False))
    except Exception as error:
        print(str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
