"""An OCR worker pool that is fair across tenants.

At most one job per tenant is in flight, and when a worker frees up the next
job comes from the next tenant in round-robin order, so one tenant's large
upload queues behind itself rather than ahead of anyone else. A job's
exception is its own: it is logged and the worker moves on, so a tenant's bad
key or rate limit never touches another tenant's jobs.
"""

import threading
import traceback
from collections import OrderedDict, deque


class FairPool:
    def __init__(self, max_workers: int):
        self._max = max_workers
        self._lock = threading.Lock()
        self._queues: "OrderedDict[object, deque]" = OrderedDict()
        self._running: set = set()
        self._active = 0
        self._closed = False
        self._idle = threading.Condition(self._lock)

    def submit(self, tenant, fn, *args):
        with self._lock:
            if self._closed:
                raise RuntimeError("pool is shut down")
            self._queues.setdefault(tenant, deque()).append((fn, args))
            self._dispatch()

    def _next_tenant(self):
        for tenant in self._queues:
            if tenant not in self._running:
                return tenant
        return None

    def _dispatch(self):
        while self._active < self._max:
            tenant = self._next_tenant()
            if tenant is None:
                return
            fn, args = self._queues[tenant].popleft()
            # Rotate: a tenant that still has work goes to the back of the line.
            queue = self._queues.pop(tenant)
            if queue:
                self._queues[tenant] = queue
            self._running.add(tenant)
            self._active += 1
            threading.Thread(target=self._run, args=(tenant, fn, args), daemon=True).start()

    def _run(self, tenant, fn, args):
        try:
            fn(*args)
        except Exception:
            traceback.print_exc()
        finally:
            with self._lock:
                self._running.discard(tenant)
                if tenant in self._queues:
                    self._queues.move_to_end(tenant)
                self._active -= 1
                self._dispatch()
                self._idle.notify_all()

    def wait_idle(self, timeout=None) -> bool:
        with self._lock:
            return self._idle.wait_for(
                lambda: self._active == 0 and not any(self._queues.values()), timeout
            )

    def shutdown(self, wait=False):
        with self._lock:
            self._closed = True
            self._queues.clear()
        if wait:
            self.wait_idle()
