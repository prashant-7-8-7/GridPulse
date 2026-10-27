import json
import socket
import ssl
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app import BUILD_VERSION, make_server
from gridpulse.jobs import ForecastJobs
from gridpulse.quickml import QuickMLClient, QuickMLError, network_error
from test_core import window


class FinalNetworkTests(unittest.TestCase):
    def test_network_errors_have_specific_codes_without_private_values(self):
        cases = [(socket.gaierror(-2, "private-value"), "DNS_LOOKUP"),
                 (ssl.SSLCertVerificationError(1, "private-value"), "TLS_CERTIFICATE"),
                 (TimeoutError("private-value"), "NETWORK_TIMEOUT"),
                 (ConnectionRefusedError("private-value"), "NETWORK_CONNECTION")]
        for reason, code in cases:
            with self.subTest(code=code):
                message = str(network_error("QuickML prediction", URLError(reason)))
                self.assertIn(code, message)
                self.assertNotIn("private-value", message)

    def test_quoted_endpoint_values_are_cleaned(self):
        with patch.dict("os.environ", {"QUICKML_ENDPOINT_URL": ' "https://api.catalyst.zoho.in/example" ',
                                      "QUICKML_ORG_ID": ' "123" ', "QUICKML_ENDPOINT_KEY": ' "test-key" ',
                                      "QUICKML_REQUEST_MODE": "single", "QUICKML_ENVIRONMENT": "Development"}):
            client = QuickMLClient()
        self.assertEqual(client.endpoint, "https://api.catalyst.zoho.in/example")
        self.assertEqual(client.org, "123")
        self.assertEqual(client.key, "test-key")

    def test_https_certificate_verification_remains_enabled(self):
        opener = QuickMLClient._new_opener()
        handlers = [handler for handler in opener.handlers if hasattr(handler, "_context")]
        self.assertTrue(handlers)
        for handler in handlers:
            self.assertTrue(handler._context.check_hostname)
            self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)


class JobTests(unittest.TestCase):
    def test_failed_job_does_not_expose_unexpected_exception(self):
        jobs = ForecastJobs()
        self.addCleanup(jobs.close)
        def fail():
            raise Exception("private-value")
        identifier = jobs.submit(fail)
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            result = jobs.get(identifier)
            if result["status"] == "failed":
                break
            time.sleep(.01)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("private-value", result["error"])

    def test_queue_is_bounded_and_missing_jobs_are_safe(self):
        jobs, release = ForecastJobs(limit=2), threading.Event()
        self.addCleanup(jobs.close)
        self.addCleanup(release.set)
        jobs.submit(lambda: release.wait(1))
        jobs.submit(lambda: release.wait(1))
        with self.assertRaisesRegex(RuntimeError, "queue is busy"):
            jobs.submit(lambda: None)
        self.assertIsNone(jobs.get("missing"))
        release.set()


class AsyncHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def test_async_forecast_returns_before_provider_finishes(self):
        release = threading.Event()
        result = {"backend": "quickml", "rows": [{"target_demand_kw": 123.5}]}
        def forecast(*args):
            release.wait(2)
            return result
        request = Request(self.url+"/api/forecast", data=json.dumps({"rows": window().to_dict(orient="records")}).encode(),
                          headers={"Content-Type": "application/json", "Prefer": "respond-async"})
        with patch("gridpulse.service.run_forecast", side_effect=forecast):
            try:
                with urlopen(request, timeout=1) as response:
                    self.assertEqual(response.status, 202)
                    identifier = json.load(response)["job_id"]
                self.assertEqual(len(identifier), 32)
                release.set()
                deadline = time.monotonic()+2
                while time.monotonic() < deadline:
                    with urlopen(self.url+"/api/forecast-jobs/"+identifier) as response:
                        job = json.load(response)
                    if job["status"] == "complete":
                        break
                    time.sleep(.01)
                self.assertEqual(job["result"], result)
            finally:
                release.set()

    def test_invalid_async_input_is_rejected_before_scheduling(self):
        request = Request(self.url+"/api/forecast", data=b'{"rows":[]}',
                          headers={"Content-Type": "application/json", "Prefer": "respond-async"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_build_version_and_missing_job(self):
        with urlopen(self.url+"/health") as response:
            self.assertEqual(json.load(response)["build"], BUILD_VERSION)
            self.assertEqual(response.headers["X-GridPulse-Build"], BUILD_VERSION)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+"/api/forecast-jobs/"+"0"*32)
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
