"""飞书工具共享 client 上下文。"""

import threading
from typing import Any, Dict, Optional, Tuple

_local = threading.local()
_task_clients: Dict[str, Tuple[Any, int]] = {}
_task_clients_lock = threading.RLock()


def set_thread_client(client: Any) -> None:
    _local.client = client


def get_client(task_id: Optional[str] = None) -> Optional[Any]:
    client = getattr(_local, "client", None)
    if client is not None:
        return client
    if not task_id:
        return None
    with _task_clients_lock:
        entry = _task_clients.get(task_id)
        return entry[0] if entry else None


def bind_task_client(task_id: Optional[str], client: Any) -> None:
    if not task_id or client is None:
        return
    with _task_clients_lock:
        existing = _task_clients.get(task_id)
        if existing is None:
            _task_clients[task_id] = (client, 1)
            return
        _, count = existing
        _task_clients[task_id] = (client, count + 1)


def unbind_task_client(task_id: Optional[str]) -> None:
    if not task_id:
        return
    with _task_clients_lock:
        existing = _task_clients.get(task_id)
        if existing is None:
            return
        client, count = existing
        if count <= 1:
            _task_clients.pop(task_id, None)
            return
        _task_clients[task_id] = (client, count - 1)
