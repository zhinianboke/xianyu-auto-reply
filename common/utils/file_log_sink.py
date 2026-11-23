"""可观测文件日志输出：保留Loguru滚动与保留策略，记录输出故障供审计落库后报告。"""
from __future__ import annotations

import traceback
from collections import deque
from threading import Lock

from loguru._file_sink import FileSink

_MAX_PENDING_FAILURES = 64
_failures: deque[str] = deque(maxlen=_MAX_PENDING_FAILURES)
_failure_count = 0
_failure_lock = Lock()


class ObservableFileSink(FileSink):
    """复用Loguru文件滚动，输出异常不穿透到数据库业务或独立审计。"""

    def write(self, message) -> None:
        """记录原始文件输出错误；调用方在队列排空后向用户明确报告。"""
        try:
            super().write(message)
        except Exception as exc:
            self._record_failure('write', exc)

    def stop(self) -> None:
        """关闭故障仍尝试释放文件，不阻断处理器更换，并保留完整故障供审计后报告。"""
        try:
            super().stop()
        except Exception as exc:
            self._record_failure('stop', exc)
            if self._file is not None:
                try:
                    self._close_file()
                except Exception as close_error:
                    self._record_failure('close_after_stop_failure', close_error)

    def _close_file(self) -> None:
        """即使flush失败也执行close；确认关闭后才清理状态，异常由write或stop记录。"""
        log_file = self._file
        try:
            log_file.flush()
        finally:
            try:
                log_file.close()
            finally:
                if log_file.closed:
                    self._file = self._file_path = None
                    self._file_dev = self._file_ino = -1

    def _record_failure(self, operation: str, exc: Exception) -> None:
        """完整保存输出路径、操作与异常链，避免关闭故障只有内部stderr记录。"""
        record_file_log_failure(f'operation={operation} path={self._path} '
                                + ''.join(traceback.format_exception(exc)))


def record_file_log_failure(message: str) -> None:
    """保留最新故障与全部发生次数，避免持续磁盘故障让内存无限增长。"""
    global _failure_count
    with _failure_lock:
        _failure_count += 1
        _failures.append(message)


def consume_file_log_failures() -> str | None:
    """返回并清空本轮已记录的文件故障，不把日志输出故障伪装为成功。"""
    global _failure_count
    with _failure_lock:
        failures = list(_failures)
        count = _failure_count
        _failures.clear()
        _failure_count = 0
    if not failures:
        return None
    summary = f'共{count}次，保留最近{len(failures)}次故障；' if count > len(failures) else ''
    return '文件日志输出失败：' + summary + '; '.join(failures)
