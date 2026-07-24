import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.coke_monitor import create_github_issue


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GitHubFallbackTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "eeminionn/coca-cola-stock-monitor",
        },
        clear=False,
    )
    @patch("scripts.coke_monitor.urlopen")
    def test_retries_without_label_after_validation_error(self, mocked_urlopen):
        validation_error = HTTPError(
            url="https://api.github.com/repos/example/issues",
            code=422,
            msg="Validation Failed",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Validation Failed"}'),
        )
        mocked_urlopen.side_effect = [
            validation_error,
            FakeResponse({"html_url": "https://github.com/example/issues/1"}),
        ]

        issue_url = create_github_issue("Alerta", "Cambio detectado")

        self.assertEqual(issue_url, "https://github.com/example/issues/1")
        self.assertEqual(mocked_urlopen.call_count, 2)
        first_payload = json.loads(mocked_urlopen.call_args_list[0].args[0].data)
        second_payload = json.loads(mocked_urlopen.call_args_list[1].args[0].data)
        self.assertEqual(first_payload["labels"], ["stock-alert"])
        self.assertNotIn("labels", second_payload)

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "eeminionn/coca-cola-stock-monitor",
        },
        clear=False,
    )
    @patch("scripts.coke_monitor.urlopen")
    def test_does_not_retry_other_http_errors(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            url="https://api.github.com/repos/example/issues",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Bad credentials"}'),
        )

        with self.assertRaises(HTTPError):
            create_github_issue("Alerta", "Cambio detectado")

        self.assertEqual(mocked_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
