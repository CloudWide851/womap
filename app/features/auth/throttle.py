from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock


class LoginThrottle:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def is_locked(self, key: str, *, limit: int, window_minutes: int) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            return len(attempts) >= limit

    def record_failure(self, key: str, *, window_minutes: int) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            attempts.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


login_throttle = LoginThrottle()
