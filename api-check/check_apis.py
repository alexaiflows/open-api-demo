"""수업 전 교수자 확인용: 수업 예제(한국천문연구원_특일 정보)와 예시 API 두 개(관광정보·상가정보)가
GitHub Actions(해외 러너)에서 호출되는지 확인한다.

- 인증키: 환경 변수 DATA_GO_KR_KEY (교수자 계정의 Decoding 키를 데모 저장소 Secrets에 등록)
- 출력: API별 HTTP 상태, 결과 코드, totalCount, 응답 모양(item이 목록/객체/빈 값인지), 걸린 시간
- 응답 내용과 인증키는 출력하지 않는다. Actions에서는 실행 요약(GITHUB_STEP_SUMMARY)에 표를 남긴다.
- 하나라도 실패하면 종료 코드 1 (실행이 빨간색으로 보인다)

로컬 실행(선택):  read -s DATA_GO_KR_KEY; export DATA_GO_KR_KEY; python3 check_apis.py
"""

from datetime import datetime
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

KST = ZoneInfo("Asia/Seoul")
BASE = "https://apis.data.go.kr"
KASI = BASE + "/B090041/openapi/service/SpcdeInfoService"


def checks(now):
    """확인할 호출 목록. 요청 변수는 각 API의 공공데이터포털 상세 화면·활용가이드(2026-09-26 확인) 기준."""
    ym = [(now.year, now.month)]
    for step in (1, 2):  # 다음 두 달도 본다: 공휴일이 하나인 달·없는 달이 섞이면 응답 모양을 함께 확인할 수 있다
        month = now.month + step
        ym.append((now.year + (month - 1) // 12, (month - 1) % 12 + 1))
    items = []
    for year, month in ym:
        items.append({"group": "수업 예제", "api": f"한국천문연구원_특일 정보 · 공휴일 {year}-{month:02d}",
                      "url": KASI + "/getRestDeInfo", "key": "ServiceKey", "ok": ("00",),
                      "params": {"solYear": f"{year}", "solMonth": f"{month:02d}", "numOfRows": 50, "pageNo": 1,
                                 "_type": "json"}})
    # 같은 서비스의 다른 오퍼레이션(시연 7의 AI 요청문 예시)
    items.append({"group": "다른 오퍼레이션", "api": f"한국천문연구원_특일 정보 · 기념일 {now.year}-{now.month:02d}",
                  "url": KASI + "/getAnniversaryInfo", "key": "ServiceKey", "ok": ("00",),
                  "params": {"solYear": f"{now.year}", "solMonth": f"{now.month:02d}", "numOfRows": 50,
                             "pageNo": 1, "_type": "json"}})
    items.append({"group": "예시 API", "api": "한국관광공사_국문 관광정보 서비스_GW · 행사정보조회",
                  "url": BASE + "/B551011/KorService2/searchFestival2", "key": "serviceKey", "ok": ("0000",),
                  "params": {"numOfRows": 5, "pageNo": 1, "MobileOS": "ETC", "MobileApp": "tdrpClass",
                             "_type": "json", "arrange": "C", "eventStartDate": now.strftime("%Y%m%d")}})
    items.append({"group": "예시 API", "api": "소상공인시장진흥공단_상가(상권)정보_API · 반경내 상가업소",
                  "url": BASE + "/B553077/api/open/sdsc2/storeListInRadius", "key": "serviceKey", "ok": ("00",),
                  # 좌표는 서울캠퍼스 근처 예시(경도 cx, 위도 cy). 확인하고 싶은 위치로 바꿔도 된다.
                  "params": {"radius": 300, "cx": "127.0590", "cy": "37.5970", "numOfRows": 5, "pageNo": 1,
                             "type": "json"}})
    return items


def masked(url):
    parts = urlsplit(url)
    pairs = [(k, "***" if k.lower() == "servicekey" else v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(pairs, safe="*")))


def scrub(text, key):
    text = str(text)
    for form in sorted({key, quote(key, safe="")}, key=len, reverse=True):
        if form:
            text = text.replace(form, "***")
    return text


def xml_to_dict(element):
    children = list(element)
    if not children:
        return (element.text or "").strip()
    out = {}
    for child in children:
        value = xml_to_dict(child)
        if child.tag in out:
            out[child.tag] = out[child.tag] if isinstance(out[child.tag], list) else [out[child.tag]]
            out[child.tag].append(value)
        else:
            out[child.tag] = value
    return out


def parse(text):
    text = text.strip()
    if text.startswith("<"):
        root = ET.fromstring(text)
        return {root.tag: xml_to_dict(root)}, "XML"
    return json.loads(text), "JSON"


def shape(body):
    """items 자리의 모양을 글로 적는다: item=list(3) / item=dict / items=''(빈 값) / items=list(5)."""
    items = body.get("items", "(없음)")
    if isinstance(items, dict):
        item = items.get("item", "(없음)")
        if isinstance(item, list):
            return f"items.item=목록({len(item)})"
        if isinstance(item, dict):
            return "items.item=객체(1)"
        return f"items.item={item!r}"
    if isinstance(items, list):
        return f"items=목록({len(items)})"
    return f"items={items!r}"


def run_one(check, key):
    query = {check["key"]: key}
    query.update(check["params"])
    url = check["url"] + "?" + urlencode(query)
    row = {"group": check["group"], "api": check["api"], "request": masked(url), "http": "-", "code": "-",
           "total": "-", "shape": "-", "format": "-", "ok": False, "note": ""}
    started = time.monotonic()
    try:
        with urlopen(Request(url, headers={"User-Agent": "tdrp-api-check/1.0"}), timeout=20) as response:
            row["http"] = response.status
            text = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        row["http"] = error.code
        text = error.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as error:
        row["note"] = scrub(f"연결 실패: {getattr(error, 'reason', error)}", key)
        row["seconds"] = round(time.monotonic() - started, 2)
        return row
    row["seconds"] = round(time.monotonic() - started, 2)
    try:
        data, row["format"] = parse(text)
    except (ET.ParseError, json.JSONDecodeError):
        row["note"] = scrub("해석 불가: " + " ".join(text.split())[:100], key)
        return row
    if "OpenAPI_ServiceResponse" in data:
        header = data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        names = [v for v in (header.get("errMsg"), header.get("returnAuthMsg")) if v and v != "SERVICE ERROR"]
        row["code"] = f"{' · '.join(names)} ({header.get('returnReasonCode', '')})"
        return row
    root = data.get("response", data)
    header = root.get("header") or {}
    body = root.get("body") or {}
    row["code"] = str(header.get("resultCode", "(없음)"))
    row["total"] = str(body.get("totalCount", "-"))
    row["shape"] = shape(body) if isinstance(body, dict) else "-"
    row["ok"] = row["code"] in check["ok"]
    if not row["ok"]:
        row["note"] = scrub(str(header.get("resultMsg", "")), key)
    return row


def main():
    key = (os.environ.get("DATA_GO_KR_KEY") or "").strip()
    if "%" in key:
        key = unquote(key)  # Encoding 키가 들어왔으면 한 번 풀어 이중 인코딩을 막는다
    if not key:
        print("DATA_GO_KR_KEY가 없습니다. 저장소 Settings → Secrets and variables → Actions → Secrets에 등록한다.")
        return 1
    now = datetime.now(KST)
    where = "GitHub Actions 러너" if os.environ.get("GITHUB_ACTIONS") == "true" else "로컬 컴퓨터"
    print(f"확인 시각 {now:%Y-%m-%d %H:%M} KST · 실행 위치 {where}")
    rows = []
    for check in checks(now):
        row = run_one(check, key)
        rows.append(row)
        mark = "OK  " if row["ok"] else "FAIL"
        print(f"[{mark}] {row['group']} · {row['api']} | HTTP {row['http']} | 결과 {row['code']} | "
              f"totalCount {row['total']} | {row['format']} {row['shape']} | {row.get('seconds', '-')}초 {row['note']}")
        print(f"       요청: {row['request']}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [f"### 공공데이터 API 호출 확인 ({now:%Y-%m-%d %H:%M} KST, {where})", "",
                 "| 결과 | 구분 | API | HTTP | 결과 코드 | totalCount | 응답 모양 | 초 |", "|---|---|---|---|---|---|---|---|"]
        for row in rows:
            lines.append(f"| {'OK' if row['ok'] else 'FAIL'} | {row['group']} | {row['api']} | {row['http']} | "
                         f"{row['code']} | {row['total']} | {row['format']} {row['shape']} | {row.get('seconds', '-')} |")
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    failed = [row for row in rows if not row["ok"]]
    print(f"성공 {len(rows) - len(failed)} / 전체 {len(rows)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
