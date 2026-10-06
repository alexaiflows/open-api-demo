"""한국천문연구원_특일 정보 · 공휴일 정보 조회(getRestDeInfo)를 불러와 화면에 쓸 모양으로 정리합니다.

다른 API로 바꿀 때는 이 파일을 복사해 ①–⑤를 그 API 상세 화면의 값으로 바꿉니다.
공통 처리(요청 주소 만들기, 오류 판정, item 정규화)는 data_go_kr.py가 맡습니다.
"""

from datetime import date
from pathlib import Path
import re

import data_go_kr
from data_go_kr import ApiError


LABEL = "특일 정보 API"

# ① 요청 주소 = 서비스 URL + 오퍼레이션 (API 상세 화면의 '요청주소')
#    같은 서비스의 다른 오퍼레이션: getHoliDeInfo(국경일) getAnniversaryInfo(기념일)
#    get24DivisionsInfo(24절기) getSundryDayInfo(잡절). 요청 변수와 응답 항목은 같습니다.
ENDPOINT = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

# ② 인증키 변수 이름 (활용가이드 표기 그대로. 이 API는 ServiceKey)
KEY_PARAM = "ServiceKey"

# ③ 성공 코드 (API마다 다릅니다. 이 API는 00, 한국관광공사 API는 0000)
OK_CODES = ("00",)

# 화면·README·JSON에 함께 적는 출처
SOURCE = {
    "name": "한국천문연구원_특일 정보",
    "operation": "공휴일 정보 조회(getRestDeInfo)",
    "portal": "공공데이터포털",
    "url": "https://www.data.go.kr/data/15012690/openapi.do",
    "license": "이용허락범위 제한 없음",
}
SECTION_TITLE = "이번 달 공휴일"
EMPTY_TEXT = "이번 달에는 공휴일이 없습니다."
WEEKDAYS = "월화수목금토일"


def request_params(year, month):
    """④ 요청 변수: 연(solYear)·월(solMonth, 두 자리), 한 번에 받을 개수, JSON 지정(_type=json)."""
    return {"solYear": f"{year:04d}", "solMonth": f"{month:02d}", "numOfRows": 50, "pageNo": 1, "_type": "json"}


def request_preview(year, month):
    """로그에 찍을 요청 주소. 인증키 자리는 ***입니다."""
    return data_go_kr.masked(data_go_kr.build_url(ENDPOINT, request_params(year, month), "***", KEY_PARAM))


def normalize(raw_items):
    """⑤ 응답 항목 → 화면 항목. locdate(20261003)·dateName·isHoliday를 날짜·이름·공휴일 여부로 바꿉니다."""
    days = []
    for number, item in enumerate(raw_items, start=1):
        locdate = str(item.get("locdate", "")).strip()
        if not re.fullmatch(r"\d{8}", locdate):
            raise ApiError(f"{LABEL} {number}번째 항목의 locdate가 날짜(YYYYMMDD)가 아닙니다: {locdate or '(빈 값)'}")
        try:
            day = date(int(locdate[:4]), int(locdate[4:6]), int(locdate[6:]))
        except ValueError:
            raise ApiError(f"{LABEL} {number}번째 항목의 locdate가 없는 날짜입니다: {locdate}") from None
        name = str(item.get("dateName", "")).strip()
        if not name:
            raise ApiError(f"{LABEL} {number}번째 항목({day.isoformat()})의 dateName이 비어 있습니다.")
        days.append({
            "date": day.isoformat(),
            "weekday": WEEKDAYS[day.weekday()],
            "name": name,
            "holiday": str(item.get("isHoliday", "")).strip().upper() == "Y",
            "kind": str(item.get("dateKind", "")).strip(),
        })
    days.sort(key=lambda entry: (entry["date"], entry["name"]))
    return days


def _finish(body):
    raw_items = data_go_kr.read_items(body)
    days = normalize(raw_items)
    total = data_go_kr.to_int(body.get("totalCount"), len(raw_items))
    return {"items": days, "total_count": total, "received": len(raw_items)}


def fetch(key, year, month, timeout=20):
    """인증키로 API를 불러 정리한 결과를 돌려줍니다."""
    _, body = data_go_kr.call_api(ENDPOINT, request_params(year, month), key, key_param=KEY_PARAM,
                                  ok_codes=OK_CODES, label=LABEL, timeout=timeout)
    return _finish(body)


def from_fixture(path):
    """저장해 둔 응답 파일(모의 응답)을 API 응답처럼 읽습니다. 키 없이 로컬에서 확인할 때 씁니다."""
    _, body = data_go_kr.parse_body(Path(path).read_bytes(), OK_CODES, LABEL)
    return _finish(body)
