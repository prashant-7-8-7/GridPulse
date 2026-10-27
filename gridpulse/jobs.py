"""Short HTTP requests around longer forecasts; results live only in this instance."""
from concurrent.futures import ThreadPoolExecutor
import secrets
import threading
import time


class ForecastJobs:
    def __init__(self, limit=16, ttl=600):
        self.limit, self.ttl = limit, ttl
        self.lock = threading.RLock()
        self.items = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gridpulse-forecast")

    def submit(self, function):
        with self.lock:
            now = time.monotonic()
            expired = [key for key, value in self.items.items()
                       if value["future"].done() and now-value["created"] > self.ttl]
            for key in expired:
                del self.items[key]
            if len(self.items) >= self.limit:
                completed = [key for key, value in self.items.items() if value["future"].done()]
                if completed:
                    del self.items[completed[0]]
                else:
                    raise RuntimeError("The forecast queue is busy. Please try again shortly.")
            identifier = secrets.token_hex(16)
            self.items[identifier] = {"created": now, "future": self.executor.submit(function)}
            return identifier

    def get(self, identifier):
        with self.lock:
            item = self.items.get(identifier)
            if item is None:
                return None
            future = item["future"]
        if not future.done():
            return {"status": "running" if future.running() else "queued"}
        try:
            return {"status": "complete", "result": future.result()}
        except (ValueError, RuntimeError) as error:
            return {"status": "failed", "error": str(error)}
        except Exception:
            return {"status": "failed", "error": "Forecast failed. Check the server configuration."}

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
