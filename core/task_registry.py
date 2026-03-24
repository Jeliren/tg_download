import threading


class UserTaskRegistry:
    """Потокобезопасный реестр активных задач пользователя."""

    def __init__(self):
        self._active_users = set()
        self._lock = threading.Lock()

    def try_start(self, user_id):
        with self._lock:
            if user_id in self._active_users:
                return False

            self._active_users.add(user_id)
            return True

    def finish(self, user_id):
        with self._lock:
            self._active_users.discard(user_id)

    def is_active(self, user_id):
        with self._lock:
            return user_id in self._active_users

