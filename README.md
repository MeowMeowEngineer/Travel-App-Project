# 인천 여행 사이트 (가칭 '인천 여행의 모든 것')

인천의 관광지·맛집(음식점)·숙소·여행 코스·행사를 모아, 장소마다 **방문 판단 정보**(이용시간·쉬는 날·요금·주차·전화·체크인)를 값별 출처와 함께 싣는 정적 여행 사이트입니다. 사이트에 실린 정보로만 답하는 **사이트 도우미(챗봇, Claude Haiku 5.5)** 가 함께 있습니다.

- 군산 여행 사이트(https://gunsan.webforai.kr)의 엔진을 옮겨 와(2026-10-19, 이력 없이 복사) 도시와 무관하게 고쳤습니다. 도시마다 다른 값은 모두 `data/<도시>/site.json`(지역 키와 `city` 블록)에 있고 `pipeline/city.py`가 읽습니다.
- 사실은 TourAPI(한국관광공사)·인천광역시/인천관광공사 공식 관광 사이트·시설 공식 홈페이지에서만 가져옵니다. 지어내지 않습니다.
- 작업 규칙은 `CLAUDE.md`, 데이터 표준은 `docs/02_page_standard.md`에 있습니다.
- 사이트 이름·도메인·GA4·검색엔진 인증·공개 여부는 운영자가 정합니다(`CLAUDE.md` 6절).

## 키만 넣으면 사이트가 나오기까지

| 단계 | 할 일 | 명령 |
|---|---|---|
| 0 | 준비(Python 3.11 이상, Node 22 이상 — Vercel은 24) | `python -m pip install -r requirements.txt` · `npm ci` |
| 1 | TourAPI 키 넣기 | `cp .env.example .env` 후 `TOURAPI_KEY=` 뒤에 키, 또는 `export TOURAPI_KEY=…` |
| 2 | 연결 진단 | `python tools/tourapi_doctor.py --data data/incheon` |
| 3 | 수집(한 번) | `python tools/tourapi_bulk.py --data data/incheon --details --add-new --events --max-calls 900` |
| 4 | 미리보기 빌드·검증 | `python -m pipeline.build --data data/incheon --out dist-preview --mode preview` → `python -m pipeline.validate --data data/incheon --out dist-preview --mode preview` |
| 5 | 공개 빌드·검증 | `python tools/build_public.py --data data/incheon --out public` |
| 6 | Vercel 배포 + 챗봇 키 | Vercel 환경 변수 `ANTHROPIC_API_KEY` → `public/`을 커밋해 `main`에 push |

1. **TourAPI 키**: 공공데이터포털의 '한국관광공사_국문 관광정보 서비스_GW' 일반 인증키(Encoding·Decoding 어느 쪽이든 된다). `.env`는 커밋되지 않습니다(`.gitignore`). 키 값을 문서·코드·커밋 메시지에 쓰지 않습니다.
2. **연결 진단**: 키·네트워크·서비스 버전 문제를 한 번에 가립니다. 공급자 오류 메시지는 그대로 보이고 키 문자열만 가려집니다.
3. **수집**: 인천광역시 아래 구·군을 TourAPI 법정동 코드 목록(ldongCode2)대로 모두 돌며(`site.json` `tourapi.scope` 'sido') 지역 목록 → 매칭·좌표·사진(공공누리 제1·3유형만) → 상세(detailCommon2·detailIntro2: 전화·이용시간·쉬는 날·요금·주차·체크인, 필드별 출처·확인일) → TourAPI에만 있는 장소(draft, 그 구·군을 `district`로) → 행사(시도 전체 한 번). `places.json`이 없어도 시작합니다. 실행당 호출 상한이 있고 응답은 `data/cache/`에 쌓이므로, 상한에 걸리면 같은 명령을 다시 실행하면 이어서 받습니다. 구·군 일부만: `--districts 연수구,강화군`. `site.json`에 없는 구·군 이름이 TourAPI에 있으면 `reports/tourapi_bulk.md`에 적힙니다.
4. **미리보기**: `python -m http.server -d dist-preview 8000` 으로 열어 봅니다. 미리보기는 draft까지 보이고 전부 noindex입니다. 수집 전(장소 0곳)에도 미리보기는 빈 상태 사이트로 만들어지고(안내 문구 출력), 공개 빌드는 '수집 전' 안내와 함께 멈춥니다.
5. **공개 빌드**: 공개(published) 레코드만, 색인 기준 미달 페이지는 noindex·sitemap 제외. 검증 오류가 있으면 종료 코드 1이고 배포하지 않습니다. 도메인(`site_url`)이 자리표시(`https://incheon.example.com`)인 동안은 production 검증이 막습니다 — 운영자가 도메인을 정해야 공개할 수 있습니다. 새 레코드는 draft로 들어오며, 공개는 운영자 승인(`python tools/approve_publication.py --data data/incheon --date <날짜> --apply`) 또는 검수 시트 반영(`tools/apply_review.py`)으로만 됩니다.
6. **Vercel**: 저장소를 Vercel 프로젝트에 연결합니다(Framework Preset: Other — 설정은 `vercel.json`: 빌드 명령 없음, 출력 `public/`, 설치 `npm ci --omit=dev`). Settings → Environment Variables에 `ANTHROPIC_API_KEY`(Production·Preview)를 넣습니다. 키가 없으면 챗봇은 "챗봇이 아직 연결되지 않았습니다"(503 `not_configured`)로 답하고, 질문 상자는 사이트 검색으로 동작하며 나머지 사이트는 그대로입니다.
7. **도메인을 정한 뒤**(사람): `data/incheon/site.json`의 `site_url`, 카카오 개발자 콘솔에 그 도메인을 등록한 지도 JavaScript 키(`kakao_js_key`, 공개 키), 서치콘솔(구글·빙·네이버) 인증 토큰, GA4·GTM, IndexNow 키.

### 도시 설정(`data/incheon/site.json`)
- **지역**: `region` '인천', `locality` '인천광역시', `districts` 지금 구·군 11곳(2026-07-01 행정체제 개편 뒤), `districts_former` 옛 이름(중구·동구·서구 — 주소·TourAPI가 옛 이름을 쓸 수 있어 둘 다 읽는다).
- **여행 권역**(`city.travel_regions`, method 'district'): 주소의 구·군(없으면 TourAPI가 준 구·군)과, 옛 중구만 법정동으로 나눈다. 개항장·원도심 · 영종·용유 · 송도·연수 · 도심 생활권 · 강화 · 옹진 섬. 지도 페이지가 이 설정에서 만든 기준 문장을 그대로 보인다.
- **거리 기준 장소**(`city.distance_anchors`): 수집한 데이터에서 이름으로 찾고, 없으면 빌드 경고와 함께 뺀다.
- **홈**(`city.home`): 홈 이야기 장·첫 화면 사진·갤러리·코스 지도·답 문구는 비어 있다 — 데이터와 운영자가 고른 사진이 생기면 넣는다. 그 전에는 그 블록 없이 데이터만으로 만든다. 가운데 사이트 도우미 카드는 `data/incheon/ask.json`이 켠다(장소가 생기면 보인다).
- **챗봇**(`city.chat`): 도시 이름(언어별)·추천 질문·추가 허용 출처. 빌드가 `public/chat/site.json`에 공개 주소·사이트 이름과 함께 쓰고, 함수(`chatbot/site.js`)와 화면(`templates/assets/chat.js`)이 그것을 읽는다. 코드에 도시 이름이 없다.
- **다른 언어판**: 한국어만(`city.intl` 비어 있음). `data/incheon/<code>`와 `city.intl.<code>` 이름이 둘 다 있어야 그 언어판이 만들어진다.

## 명령어
```bash
python -m pytest                                   # 파이썬 시험(Node가 있으면 챗봇 서버 시험도 함께)
npm test                                           # 챗봇 서버 시험만(node --test tests/js/)
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/quality_report.py --data data/incheon --out public       # 정보 채움률(전화·이용시간·주차·사진·좌표)
python tools/launch_check.py --data data/incheon --stdout             # 공개 전 점검표
python tools/make_review_sheet.py --data data/incheon --out reports/review.csv   # 검수 시트(사람이 OK 표시)
python tools/apply_review.py --sheet reports/review.csv --data data/incheon      # 반영 미리 보기(기본 dry-run)
python tools/perf_check.py --out public                              # 모바일 속도(Playwright 필요)
```
- 챗봇을 로컬에서 시험하려면 `ANTHROPIC_API_KEY`를 환경 변수로 두고 `vercel dev`를 씁니다. 대화는 저장하지 않습니다.
- 브라우저 시험(`tests/test_*_browser.py`)은 Playwright와 Chromium이 있을 때만 돕니다.

## 폴더
| 경로 | 내용 |
|---|---|
| `data/incheon/` | 인천 사이트 데이터(`site.json`, `icons.json`, 수집 뒤 `places.json` 등) |
| `data/sample/` | 테스트용 가짜 데이터(군산 샘플). 공개하지 않습니다 |
| `pipeline/` | 빌드·검증·구조화 데이터·TourAPI 클라이언트·챗봇 지식 만들기 |
| `templates/` | 화면(Jinja2)·CSS·JS·글꼴(Pretendard 서브셋)·3D 아이콘 |
| `tools/` | TourAPI 진단·수집, 공개 빌드, 검수·공개 승인, 품질·성능 점검 |
| `chatbot/`, `api/chat.js` | 사이트 도우미(Vercel 함수, 모델 `claude-haiku-5-5`) |
| `tests/` | pytest와 `tests/js/`(node --test) |
| `public/` | 공개 산출물(빌드로만 만든다, Vercel이 그대로 배포) |
