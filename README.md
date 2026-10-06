# 공공데이터 Open API 예제 · 이번 달 공휴일

**5주차 구글 시트 예제에 공공데이터포털 Open API를 더한 예제**입니다. GitHub Actions가 저장소 Secrets에 둔 인증키로 한국천문연구원_특일 정보 API를 불러 이번 달 공휴일을 정리하고, 시트의 수업 팁과 함께 웹페이지로 만들어 GitHub Pages에 배포합니다. Python 표준 라이브러리만 사용합니다.

```text
공공데이터포털 인증키(Decoding) → 저장소 Secrets의 DATA_GO_KR_KEY
  → main에 저장 / 버튼으로 실행 / 예약 시각 도달
  → Actions: 저장한 응답으로 시험 → API 호출 → 결과 코드 확인 → item 정규화 → HTML·JSON 생성
  → GitHub Pages에 배포 (중간에 멈추면 이전 배포가 그대로 유지)
```

## 파일 역할

| 파일 | 역할 |
|---|---|
| `main.py` | 시트 읽기(5주차와 같음), 특일 정보 읽기, HTML과 `special-days.json` 생성 |
| `data_go_kr.py` | 공공데이터포털 API 공통 처리: 요청 주소 만들기, 인증키 가리기, 오류 판정, item 정규화 |
| `special_days.py` | 특일 정보 API의 요청 주소·인증키 변수·성공 코드·요청 변수·응답 항목. 다른 API는 이 파일을 본떠 만듭니다 |
| `fixtures/special_days_sample.json` | 키 없이 로컬에서 확인하는 모의 응답(2026년 10월) |
| `tests/` | 모의 응답으로 여러 개·하나·없음·인증 오류·결과 코드 오류·HTTP 오류·시간 초과를 확인하는 시험 |
| `sample.csv`, `site.json` | 5주차와 같은 시트 샘플, 서비스 제목·설명·출처 문구 |
| `.github/workflows/open_api_site.yml` | 시험 → Variables·Secrets 전달 → 생성 → Pages 배포 |

## 1. 키 없이 로컬에서 먼저 실행

예제 폴더에서 실행합니다.

```bash
python3 main.py --api-fixture fixtures/special_days_sample.json --output _site/index.html
python3 -m unittest discover -s tests -v
```

첫 명령은 모의 응답 파일을 API 응답처럼 읽어 `_site/index.html`과 `_site/special-days.json`을 만듭니다. 출력 마지막 부분은 이렇습니다.

```text
특일 정보: 모의 응답 파일 special_days_sample.json · 2026년 10월 3개 (쉬는 날 3개)
HTML 생성 완료: _site/index.html
JSON 저장 완료: _site/special-days.json
```

둘째 명령은 시험 24개를 실행하고 `OK`로 끝납니다. 공휴일이 없는 달의 화면은 `--api-fixture tests/fixtures/none.json --month 2026-11`로 봅니다.

## 2. 인증키 받기

1. [공공데이터포털](https://www.data.go.kr/)에 로그인하고 `한국천문연구원_특일 정보`를 검색해 **활용신청**합니다. 개발단계 자동승인이고 개발계정 트래픽은 하루 10,000건입니다.
2. 마이페이지 → 데이터 활용 → Open API → 활용신청 현황에서 신청한 API를 열고 일반 인증키 **Decoding**을 복사합니다.
3. 활용신청 직후에는 인증키 오류가 날 수 있습니다. 잠시 뒤 다시 실행합니다.

인증키는 비밀번호처럼 다룹니다. 저장소 Secrets에만 넣습니다.

## 3. 저장소 Secrets에 등록

1. 저장소 Settings → Secrets and variables → Actions → **Secrets** 탭 → New repository secret
2. Name: `DATA_GO_KR_KEY`, Secret: 복사한 Decoding 키 → Add secret
3. 시트를 연결했다면 Variables 탭의 `SHEET_CSV_URL`은 5주차 그대로 둡니다.
4. Settings → Pages → Source가 **GitHub Actions**인지 확인합니다.

워크플로는 `DATA_GO_KR_KEY: ${{ secrets.DATA_GO_KR_KEY }}`로 키를 환경 변수에 넣고, `main.py`는 그 값을 읽습니다. 코드와 로그에는 키가 나오지 않습니다.

## 4. Actions로 실행하고 확인

1. Actions → Open API Site → Run workflow
2. build 로그에서 `Test with saved responses`의 `OK`를 확인합니다.
3. `Build page from Google Sheet and Open API` 단계에서 두 줄을 읽습니다. `n`은 그달의 공휴일 수입니다.

```text
특일 정보 요청: https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo?ServiceKey=***&solYear=2026&solMonth=10&numOfRows=50&pageNo=1&_type=json
특일 정보: 공공데이터 Open API(한국천문연구원_특일 정보) · 2026년 10월 n개 (쉬는 날 n개)
```

4. deploy가 끝나면 공개 주소에서 이번 달 공휴일 구역과 출처, 바닥글을 확인합니다. `공개주소/special-days.json`을 열면 Actions가 저장한 정리 데이터가 보입니다.

매일 자동으로 다시 부르려면 워크플로의 `schedule` 두 줄 앞 `#`을 지웁니다. 하루 한 번 호출은 개발계정 트래픽 안에서 충분합니다.

## 5. (선택) 내 컴퓨터에서 실제 키로 실행

macOS·Linux 터미널에서 키를 화면과 명령 기록에 남기지 않고 넣는 방법입니다.

```bash
read -s DATA_GO_KR_KEY    # 붙여 넣어도 글자가 보이지 않습니다. Enter로 마칩니다
export DATA_GO_KR_KEY
python3 main.py --output _site/index.html
```

## 6. 검증할 것

| 상황 | 해 보는 방법 | 기대 결과 |
|---|---|---|
| 정상 | Run workflow | 이번 달 공휴일 목록, 바닥글 `공휴일: 공공데이터 Open API(…)` |
| item 여러 개·하나·없음 | 시험 실행, `--api-fixture tests/fixtures/none.json --month 2026-11` | 모두 목록으로 정리되고, 없으면 `이번 달에는 공휴일이 없습니다.` |
| 키 없음 | Secrets 등록 전 Run workflow | build 실패, 로그와 실행 요약에 등록 방법 안내, 이전 배포 유지 |
| 인증 오류 | `--api-fixture tests/fixtures/auth_error.xml` | `SERVICE_KEY_IS_NOT_REGISTERED_ERROR (코드 30)`과 확인할 것 |
| 결과 코드 오류 | `--api-fixture tests/fixtures/result_error.json` | `결과 코드가 10입니다`와 요청 변수 확인 안내 |
| 로그의 키 | build 로그에서 요청 주소 확인 | `ServiceKey=***`만 보임 |
| 휴대전화 폭 | 휴대전화로 공개 주소 열기 | 가로 넘침 없이 한 줄씩 쌓임 |

시험(`tests/`)은 HTTP 403·429·500 응답, 시간 초과, 연결 실패도 흉내 내어 확인합니다.

## 7. 다른 API로 바꾸기

`special_days.py`를 복사해 새 파일(예: `my_api.py`)로 만들고 ①–⑤를 쓸 API 상세 화면의 값으로 바꿉니다. `data_go_kr.py`는 그대로 씁니다. 예시 API는 강의 핵심정리 7절, AI 요청문은 실습안내 6절에 있습니다. 새 API도 Secrets에 넣은 키의 계정으로 활용신청합니다.

| 번호 | 바꿀 것 | 특일 정보의 값 |
|---|---|---|
| ① | 요청 주소 | `https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo` |
| ② | 인증키 변수 이름 | `ServiceKey` |
| ③ | 성공 코드 | `00` |
| ④ | 요청 변수 | `solYear`, `solMonth`, `numOfRows`, `pageNo`, `_type=json` |
| ⑤ | 화면에 쓸 응답 항목 | `locdate` → 날짜, `dateName` → 이름, `isHoliday` → 쉬는 날 |

## 출처 표기

- 공휴일: 한국천문연구원_특일 정보, 공공데이터포털(https://www.data.go.kr/data/15012690/openapi.do), 이용허락범위 제한 없음
- 수업 팁: 수업용으로 새로 작성
- `fixtures/`와 `tests/fixtures/`는 공식 활용가이드의 응답 구조를 본떠 만든 모의 응답입니다.

## 공식 문서

- 한국천문연구원_특일 정보(참고문서: OpenAPI 활용가이드 v1.4): https://www.data.go.kr/data/15012690/openapi.do
- GitHub Actions에서 Secrets 사용: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- Pages 사용자 지정 워크플로: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- 공공누리 유형: https://www.kogl.or.kr/info/license.do
