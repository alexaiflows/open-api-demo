"""특일 정보 예제 시험. 모의 응답(tests/fixtures)만 쓰고 실제 API는 부르지 않습니다.

예제 폴더에서 실행:  python3 -m unittest discover -s tests -v
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data_go_kr  # noqa: E402
from data_go_kr import ApiError  # noqa: E402
import main  # noqa: E402
import special_days  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
FAKE_KEY = "TEST+KEY/only=="  # 실제 인증키가 아닌 시험용 글자. +, /, = 가 들어 있어 인코딩 차이를 볼 수 있습니다


class FakeResponse:
    """urlopen이 돌려주는 응답 흉내."""

    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body):
    return HTTPError("https://apis.data.go.kr/example", code, "error", {}, io.BytesIO(body))


def fixture_bytes(name):
    return (FIX / name).read_bytes()


class NormalizeTest(unittest.TestCase):
    """item이 여러 개·하나·없음일 때 모두 같은 목록 모양이 되는지 봅니다."""

    def test_many_items_array(self):
        result = special_days.from_fixture(FIX / "many.json")
        self.assertEqual([d["date"] for d in result["items"]], ["2026-09-24", "2026-09-25", "2026-09-26"])
        self.assertEqual([d["weekday"] for d in result["items"]], ["목", "금", "토"])
        self.assertTrue(all(d["holiday"] for d in result["items"]))
        self.assertEqual(result["total_count"], 3)

    def test_one_item_object(self):
        result = special_days.from_fixture(FIX / "one.json")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "기독탄신일")
        self.assertEqual(result["items"][0]["date"], "2026-12-25")

    def test_no_items_empty_string(self):
        result = special_days.from_fixture(FIX / "none.json")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_count"], 0)

    def test_other_empty_shapes(self):
        for body in ({}, {"items": None}, {"items": {}}, {"items": {"item": []}}, {"items": {"item": ""}}):
            self.assertEqual(data_go_kr.read_items(body), [], body)

    def test_xml_normal_response(self):
        result = special_days.from_fixture(FIX / "xml_normal.xml")
        self.assertEqual(result["items"][0]["name"], "삼일절")
        self.assertEqual(result["items"][0]["date"], "2019-03-01")

    def test_bad_item_reports_number(self):
        with self.assertRaises(ApiError) as caught:
            special_days.from_fixture(FIX / "bad_item.json")
        self.assertIn("2번째 항목", str(caught.exception))
        self.assertIn("2026-10-05", str(caught.exception))

    def test_success_code_differs_by_api(self):
        raw = fixture_bytes("tour_style_0000.json")
        _, body = data_go_kr.parse_body(raw, ok_codes=("0000",), label="관광 API")
        self.assertEqual(data_go_kr.read_items(body)[0]["title"], "예시 가을 축제")
        with self.assertRaises(ApiError) as caught:
            data_go_kr.parse_body(raw, ok_codes=("00",), label="관광 API")
        self.assertIn("결과 코드가 0000", str(caught.exception))


class ErrorResponseTest(unittest.TestCase):
    """오류 응답마다 이유가 드러나고 멈추는지 봅니다."""

    def setUp(self):
        sleep = mock.patch("data_go_kr.time.sleep")  # 다시 시도할 때 기다리지 않게 합니다
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_xml_auth_error(self):
        with self.assertRaises(ApiError) as caught:
            special_days.from_fixture(FIX / "auth_error.xml")
        message = str(caught.exception)
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", message)
        self.assertIn("코드 30", message)
        self.assertIn("Decoding", message)

    def test_result_code_error(self):
        with self.assertRaises(ApiError) as caught:
            special_days.from_fixture(FIX / "result_error.json")
        self.assertIn("결과 코드가 10", str(caught.exception))
        self.assertIn("요청 변수", str(caught.exception))

    def test_http_403_with_gateway_body(self):
        with mock.patch("data_go_kr.urlopen", side_effect=http_error(403, fixture_bytes("auth_error_403.json"))):
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        message = str(caught.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", message)
        self.assertIn("코드 30", message)

    def test_http_500_retries_then_fails(self):
        with mock.patch("data_go_kr.urlopen", side_effect=[http_error(500, b"oops"), http_error(500, b"oops")]) as opener:
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        self.assertEqual(opener.call_count, 2)
        self.assertIn("HTTP 500", str(caught.exception))

    def test_quota_text(self):
        with mock.patch("data_go_kr.urlopen", side_effect=http_error(429, fixture_bytes("quota.txt"))):
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        self.assertIn("HTTP 429", str(caught.exception))
        self.assertIn("하루 호출 허용량", str(caught.exception))

    def test_timeout(self):
        with mock.patch("data_go_kr.urlopen", side_effect=TimeoutError("timed out")) as opener:
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        self.assertEqual(opener.call_count, 2)
        self.assertIn("응답하지 않았습니다", str(caught.exception))

    def test_connection_error(self):
        with mock.patch("data_go_kr.urlopen", side_effect=URLError("nodename nor servname provided")):
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        self.assertIn("연결하지 못했습니다", str(caught.exception))


class KeySafetyTest(unittest.TestCase):
    """인증키가 로그·메시지에 나오지 않고, 한 번만 인코딩되는지 봅니다."""

    def test_masked_url_hides_key(self):
        url = data_go_kr.build_url(special_days.ENDPOINT, special_days.request_params(2026, 10), FAKE_KEY, "ServiceKey")
        shown = data_go_kr.masked(url)
        self.assertIn("ServiceKey=***", shown)
        self.assertNotIn("TEST", shown)
        self.assertIn("solMonth=10", shown)
        self.assertIn("_type=json", shown)

    def test_encoding_key_is_decoded_once(self):
        encoding_key = "TEST%2BKEY%2Fonly%3D%3D"  # 포털의 Encoding 키 모양
        self.assertEqual(data_go_kr.clean_key(encoding_key), FAKE_KEY)
        self.assertEqual(data_go_kr.clean_key("  " + FAKE_KEY + "\n"), FAKE_KEY)
        url = data_go_kr.build_url("https://example.invalid/op", {}, data_go_kr.clean_key(encoding_key), "ServiceKey")
        self.assertIn("ServiceKey=TEST%2BKEY%2Fonly%3D%3D", url)
        self.assertNotIn("%25", url)  # %가 다시 인코딩되면(이중 인코딩) %25가 생깁니다

    def test_request_contains_params(self):
        with mock.patch("data_go_kr.urlopen", return_value=FakeResponse(fixture_bytes("many.json"))) as opener:
            special_days.fetch(FAKE_KEY, 2026, 9)
        sent = opener.call_args[0][0].full_url
        self.assertTrue(sent.startswith(special_days.ENDPOINT + "?"))
        for part in ("ServiceKey=TEST%2BKEY%2Fonly%3D%3D", "solYear=2026", "solMonth=09", "_type=json", "numOfRows=50"):
            self.assertIn(part, sent)

    def test_error_message_never_contains_key(self):
        echoed = f"Unauthorized request: ServiceKey={FAKE_KEY} / {data_go_kr.quote(FAKE_KEY, safe='')}".encode()
        with mock.patch("data_go_kr.urlopen", side_effect=http_error(401, echoed)):
            with self.assertRaises(ApiError) as caught:
                special_days.fetch(FAKE_KEY, 2026, 10)
        message = str(caught.exception)
        self.assertNotIn(FAKE_KEY, message)
        self.assertNotIn("TEST%2BKEY", message)
        self.assertIn("***", message)


class MainTest(unittest.TestCase):
    """main.py 전체 흐름: 모의 응답 실행, 키 없음, 실패 시 기존 파일 유지."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.output = self.tmp / "_site" / "index.html"
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ("DATA_GO_KR_KEY", "SHEET_CSV_URL", "GITHUB_ACTIONS", "GITHUB_RUN_NUMBER", "GITHUB_SHA"):
            os.environ.pop(name, None)
        sleep = mock.patch("data_go_kr.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main.main(["--output", str(self.output), "--date", "2026-10-07", *args])
        return code, out.getvalue(), err.getvalue()

    def test_fixture_run_writes_html_and_json(self):
        code, out, err = self.run_main("--api-fixture", str(ROOT / "fixtures" / "special_days_sample.json"))
        self.assertEqual(code, 0, err)
        html = self.output.read_text(encoding="utf-8")
        self.assertIn("개천절", html)
        self.assertIn("2026년 10월 · 3일", html)
        self.assertIn("한국천문연구원_특일 정보", html)
        data = json.loads((self.output.parent / "special-days.json").read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["items"][1], {"date": "2026-10-05", "weekday": "월", "name": "대체공휴일",
                                            "holiday": True, "kind": "01"})
        self.assertIn("모의 응답 파일", out)

    def test_empty_month_shows_message(self):
        code, _, err = self.run_main("--api-fixture", str(FIX / "none.json"), "--month", "2026-11")
        self.assertEqual(code, 0, err)
        html = self.output.read_text(encoding="utf-8")
        self.assertIn(special_days.EMPTY_TEXT, html)
        self.assertIn("2026년 11월 · 0일", html)

    def test_missing_key_local_mentions_fixture(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("--api-fixture", err)
        self.assertFalse(self.output.exists())

    def test_missing_key_in_actions(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        os.environ["DATA_GO_KR_KEY"] = ""  # 등록하지 않은 Secret은 빈 글자로 들어옵니다
        code, out, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Secrets", err)
        self.assertIn("이전 배포", err)
        self.assertIn("::error title=생성 실패::", out)

    def test_api_call_logs_masked_url_only(self):
        os.environ["DATA_GO_KR_KEY"] = FAKE_KEY
        with mock.patch("data_go_kr.urlopen", return_value=FakeResponse(fixture_bytes("many.json"))):
            code, out, err = self.run_main("--month", "2026-09")
        self.assertEqual(code, 0, err)
        self.assertIn("ServiceKey=***", out)
        for text in (out, err, self.output.read_text(encoding="utf-8"),
                     (self.output.parent / "special-days.json").read_text(encoding="utf-8")):
            self.assertNotIn("TEST+KEY", text)
            self.assertNotIn("TEST%2BKEY", text)

    def test_failure_keeps_previous_html(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("이전 배포본", encoding="utf-8")
        os.environ["DATA_GO_KR_KEY"] = FAKE_KEY
        with mock.patch("data_go_kr.urlopen", side_effect=http_error(403, fixture_bytes("auth_error_403.json"))):
            code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("SERVICE_KEY_IS_NOT_REGISTERED_ERROR", err)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "이전 배포본")


if __name__ == "__main__":
    unittest.main()
