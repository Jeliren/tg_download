import threading
import traceback
from concurrent.futures import ThreadPoolExecutor


class BackgroundTaskRunner:
    """Ограниченный пул фоновых задач с защитой от бесконтрольного роста очереди."""

    def __init__(self, max_workers, max_queue_size=0, logger=None):
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_queue_size < 0:
            raise ValueError("max_queue_size must be non-negative")

        capacity = max_workers + max_queue_size
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tg-bot")
        self._capacity = threading.Semaphore(capacity)
        self._logger = logger
        self._is_shutdown = False
        self._submit_lock = threading.Lock()

    def submit(self, task_name, func, *args, **kwargs):
        if not self._capacity.acquire(blocking=False):
            if self._logger:
                self._logger(
                    f"Очередь фоновых задач переполнена, задача {task_name} отклонена",
                    level="WARNING",
                )
            return None

        try:
            with self._submit_lock:
                if self._is_shutdown:
                    if self._logger:
                        self._logger(
                            f"Task runner уже остановлен, задача {task_name} отклонена",
                            level="WARNING",
                        )
                    self._capacity.release()
                    return None

                future = self._executor.submit(self._run_task, task_name, func, *args, **kwargs)
        except RuntimeError as exc:
            self._capacity.release()
            if self._logger:
                self._logger(
                    f"Не удалось запустить фоновую задачу {task_name}: {exc}",
                    level="WARNING",
                )
            return None

        future.add_done_callback(self._release_capacity)
        return future

    def shutdown(self, wait=True):
        with self._submit_lock:
            self._is_shutdown = True
        self._executor.shutdown(wait=wait)

    def _release_capacity(self, _future):
        self._capacity.release()

    def _run_task(self, task_name, func, *args, **kwargs):
        try:
            if self._logger:
                self._logger(f"Запуск фоновой задачи: {task_name}", level="DEBUG")
            return func(*args, **kwargs)
        except Exception as e:
            if self._logger:
                self._logger(
                    f"Фоновая задача {task_name} завершилась с ошибкой: {e}\n{traceback.format_exc()}",
                    level="ERROR",
                )
            return None
