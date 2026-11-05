"""One report commit path for the editor and explicit block apply."""
from file_io import atomic_write, digest
from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
from project_workspace import is_link

@contextmanager
def report_lock(folder):
    folder=Path(folder);path=folder/'.hrs-write.lock'
    if is_link(folder) or is_link(path):raise ValueError('报告写入锁不能是链接')
    # A persistent lock inode avoids stale locks and unlink/recreate races.
    handle=path.open('a+b');locked=False
    try:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError as error:raise ValueError('WRITE_BUSY：另一程序正在提交该报告') from error
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()

def backup_report(folder,source=None):
    folder=Path(folder);data=(Path(source) if source is not None else folder/'report.md').read_bytes();history=folder/'.history'
    if is_link(history):raise ValueError('工程 .history 目录不能是链接')
    history.mkdir(exist_ok=True)
    name=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+digest(data)[:8]+'.md'
    target=history/name;atomic_write(target,data)
    for path in sorted(history.glob('*.md'))[:-30]:path.unlink()
    return target

def commit_report_locked(folder,data,expected,*,source=None,warnings=None,timestamp_snapshot=None):
    """Caller holds report_lock; revision is checked again after the backup."""
    explicit_source=source
    folder=Path(folder);source=Path(source) if source is not None else folder/'report.md'
    if is_link(source):raise ValueError('报告正文不能是链接文件')
    raw=source.read_bytes()
    if digest(raw)!=expected:raise ValueError('STALE_SNAPSHOT：正式文稿已变化')
    if raw==data:return None
    backup=backup_report(folder,source) if explicit_source is not None else backup_report(folder)
    if source.read_bytes()!=raw:raise ValueError('STALE_SNAPSHOT：备份期间正式文稿发生变化')
    atomic_write(source,data)
    # Presentation metadata is a follow-up: a failed sidecar write must never
    # report a committed source as a failed/stale write.
    try:
        import document_timestamps as times
        before,after=raw.decode('utf-8-sig'),data.decode('utf-8-sig')
        snapshot=times.validate(timestamp_snapshot)
        if snapshot and snapshot['source_sha256']==digest(after.encode('utf-8')):times.store(folder,snapshot)
        else:times.store(folder,times.advance(before,after,times.load(folder,before)))
    except (OSError,ValueError,TypeError) as error:
        message='正文已保存，时间信息更新未完成：'+str(error)
        if warnings is not None:warnings.append(message)
        else:
            import warnings as warning_output
            warning_output.warn(message,RuntimeWarning,stacklevel=2)
    return backup

def commit_report(folder,data,expected,*,warnings=None,timestamp_snapshot=None):
    with report_lock(folder):return commit_report_locked(folder,data,expected,warnings=warnings,timestamp_snapshot=timestamp_snapshot)
