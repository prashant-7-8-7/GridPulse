"""Check bounded cloud concurrency without calling any external endpoint."""
import io
import json
import os
import threading
import unittest
from unittest.mock import patch

from gridpulse.quickml import QuickMLClient, QuickMLError


class QuickMLConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "QUICKML_ENDPOINT_URL": "https://api.catalyst.zoho.in/example",
            "QUICKML_ENDPOINT_KEY": "test-key", "QUICKML_ORG_ID": "123",
            "QUICKML_ACCESS_TOKEN": "test-access", "QUICKML_REFRESH_TOKEN": "",
            "QUICKML_REQUEST_MODE": "single", "QUICKML_REQUEST_KEY": "data",
            "QUICKML_RESPONSE_PATH": "result", "QUICKML_MAX_WORKERS": "4",
            "QUICKML_ENVIRONMENT": "Development",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_out_of_order_responses_preserve_input_order(self):
        client = QuickMLClient()
        release = threading.Event()
        finished = []

        def send(request, operation):
            hour = json.loads(request.data)["data"]["hour"]
            if hour == 1:
                self.assertTrue(release.wait(2))
            finished.append(hour)
            if hour == 2:
                release.set()
            return {"result": [100 + hour]}

        with patch.object(client, "_send", side_effect=send):
            result = client.predict([{"hour": n} for n in range(24)])
        self.assertEqual(result, [100 + n for n in range(24)])
        self.assertLess(finished.index(2), finished.index(1))
        self.assertEqual(sorted(finished), list(range(24)))

    def test_worker_limit_and_exact_prediction_call_count(self):
        client = QuickMLClient()
        lock, release = threading.Lock(), threading.Event()
        state = {"active": 0, "peak": 0, "calls": 0}

        def send(request, operation):
            hour = json.loads(request.data)["data"]["hour"]
            with lock:
                state["active"] += 1
                state["calls"] += 1
                state["peak"] = max(state["peak"], state["active"])
                if state["active"] == 4:
                    release.set()
            if hour:
                self.assertTrue(release.wait(2))
            with lock:
                state["active"] -= 1
            return {"result": [100 + hour]}

        with patch.object(client, "_send", side_effect=send):
            self.assertEqual(len(client.predict([{"hour": n} for n in range(24)])), 24)
        self.assertEqual(state["calls"], 24)
        self.assertEqual(state["peak"], 4)

    def test_failed_first_call_does_not_schedule_other_rows(self):
        client = QuickMLClient()
        with patch.object(client, "_send", side_effect=QuickMLError("Provider unavailable")) as send:
            with self.assertRaises(QuickMLError):
                client.predict([{"hour": n} for n in range(24)])
        self.assertEqual(send.call_count, 1)

    def test_worker_failure_stops_scheduling_and_has_no_fallback(self):
        client = QuickMLClient()
        pause = threading.Event()

        def send(request, operation):
            hour = json.loads(request.data)["data"]["hour"]
            if hour == 1:
                raise QuickMLError("Provider unavailable")
            if hour:
                pause.wait(.1)
            return {"result": [100 + hour]}

        with patch.object(client, "_send", side_effect=send) as mocked:
            with self.assertRaisesRegex(QuickMLError, "Provider unavailable"):
                client.predict([{"hour": n} for n in range(1000)])
        self.assertLessEqual(mocked.call_count, 5)

    def test_one_worker_and_empty_input(self):
        with patch.dict(os.environ, {"QUICKML_MAX_WORKERS": "1"}):
            client = QuickMLClient()
        observed = []

        def send(request, operation):
            hour = json.loads(request.data)["data"]["hour"]
            observed.append((hour, threading.get_ident()))
            return {"result": [100 + hour]}

        with patch.object(client, "_send", side_effect=send):
            self.assertEqual(client.predict([]), [])
            self.assertEqual(client.predict([{"hour": n} for n in range(5)]), [100., 101., 102., 103., 104.])
        self.assertEqual(observed, [(n, threading.get_ident()) for n in range(5)])

    def test_normalizes_environment_without_guessing_unknown_values(self):
        for value, expected in [(' "development" ', "Development"), ("'PRODUCTION'", "Production")]:
            with self.subTest(value=value), patch.dict(os.environ, {"QUICKML_ENVIRONMENT": value}):
                self.assertEqual(QuickMLClient().environment, expected)
        with patch.dict(os.environ, {"QUICKML_ENVIRONMENT": "staging"}):
            with self.assertRaises(QuickMLError):
                QuickMLClient()

    def test_invalid_worker_counts(self):
        for value in ("0", "9", "oops"):
            with self.subTest(value=value), patch.dict(os.environ, {"QUICKML_MAX_WORKERS": value}):
                with self.assertRaisesRegex(QuickMLError, "QUICKML_MAX_WORKERS"):
                    QuickMLClient()

    def test_parallel_predictions_share_one_token_refresh(self):
        with patch.dict(os.environ, {"QUICKML_REFRESH_TOKEN": "test-refresh",
                                    "ZOHO_CLIENT_ID": "test-client",
                                    "ZOHO_CLIENT_SECRET": "test-secret"}):
            client = QuickMLClient()
            refreshes, authorizations = [], []

            def send(request, operation):
                if operation == "OAuth refresh":
                    refreshes.append(operation)
                    return {"access_token": "refreshed-access", "expires_in": 3600}
                authorizations.append(request.get_header("Authorization"))
                hour = json.loads(request.data)["data"]["hour"]
                return {"result": [100 + hour]}

            with patch.object(client, "_send", side_effect=send):
                result = client.predict([{"hour": n} for n in range(24)])
        self.assertEqual(len(result), 24)
        self.assertEqual(len(refreshes), 1)
        self.assertEqual(authorizations, ["Zoho-oauthtoken refreshed-access"] * 24)

    def test_transport_is_not_shared_between_threads(self):
        used = []

        class Opener:
            def __init__(self):
                self.owner = threading.get_ident()

            def open(self, request, timeout):
                if self.owner != threading.get_ident():
                    raise AssertionError("HTTP opener crossed threads")
                used.append(self.owner)
                hour = json.loads(request.data)["data"]["hour"]
                return io.BytesIO(json.dumps({"result": [100 + hour]}).encode())

        with patch("gridpulse.quickml.build_opener", side_effect=lambda *args: Opener()):
            client = QuickMLClient()
            result = client.predict([{"hour": n} for n in range(24)])
        self.assertEqual(result, [100 + n for n in range(24)])
        self.assertEqual(len(used), 24)
        self.assertGreater(len(set(used)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
