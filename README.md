# 인천각 (Incheongak) — 인천 여행 사이트

인천의 관광지·맛집(음식점)·카페·디저트·숙소·쇼핑·여행 코스·행사를 모아, 장소마다 **방문 판단 정보**(이용시간·쉬는 날·요금·주차·전화·체크인)를 값별 출처와 함께 싣는 정적 여행 사이트입니다. 사이트에 실린 정보로만 답하는 **사이트 도우미(챗봇, Claude Haiku 5.5)** 가 함께 있습니다.

- 군산 여행 사이트(https://gunsan.webforai.kr)의 엔진을 옮겨 와(2026-10-19, 이력 없이 복사) 도시와 무관하게 고쳤습니다. 도시마다 다른 값은 모두 `data/<도시>/site.json`(지역 키와 `city` 블록)에 있고 `pipeline/city.py`가 읽습니다.
- 사실은 TourAPI(한국관광공사)·인천광역시/인천관광공사 공식 관광 사이트·시설 공식 홈페이지에서만 가져옵니다. 지어내지 않습니다.
- 작업 규칙은 `CLAUDE.md`, 데이터 표준은 `docs/02_page_standard.md`에 있습니다.
- 사이트 이름 **인천각**(Incheongak)과 도메인 **https://incheon.webforai.kr**은 운영자가 정했습니다(2026-10-19, `CLAUDE.md` 2절). GA4·검색엔진 인증·공개 여부는 운영자가 정합니다(6절).

## 키만 넣으면 사이트가 나오기까지

| 단계 | 할 일 | 명령 |
|---|---|---|
| 0 | 준비(Python 3.11 이상, Node 22 이상 — Vercel은 24) | `python -m pip install -r requirements.txt` · `npm ci` |
| 1 | TourAPI 키 넣기 | `cp .env.example .env` 후 `TOURAPI_KEY=` 뒤에 키, 또는 `export TOURAPI_KEY=…` |
| 2–3 | 진단 + 수집(한 명령) | `python tools/collect.py --data data/incheon` — 상한에 걸려 멈추면(종료 코드 3) 같은 명령을 다시 |
| 4 | 미리보기 빌드·검증 | `python -m pipeline.build --data data/incheon --out dist-preview --mode preview` → `python -m pipeline.validate --data data/incheon --out dist-preview --mode preview` |
| 5 | 요약 쓰기 + 문장 검사 | 장소마다 `summary`(필요하면 `faq`)를 `data/incheon/places.json`에 쓴다 → `python tools/content_check.py --data data/incheon`(걸리면 고쳐 쓴다) |
| 6 | 공개 선별 미리보기 | `python tools/build_review.py --data data/incheon --out dist-review --report-dir reports` |
| 7 | 운영자 공개 승인(사람) | `python tools/approve_publication.py --data data/incheon --date <날짜>`(미리 보기) → 운영자가 정하면 같은 명령에 `--apply` |
| 8 | 공개 설정(사람) + 공개 빌드·검증 | `site.json`의 `site_url`·`ga4_id`(또는 `launch_exceptions.ga4_id`)·`operator.contact`를 채운 뒤 `python tools/build_public.py --data data/incheon --out public` |
| 9 | Vercel 배포 + 챗봇 키 | Vercel 환경 변수 `ANTHROPIC_API_KEY` → 재배포(`public/`을 커밋해 `main`에 push) → `curl https://<도메인>/api/chat/`이 `{"ready":true}` |

1. **TourAPI 키**: 공공데이터포털의 '한국관광공사_국문 관광정보 서비스_GW' 일반 인증키(Encoding·Decoding 어느 쪽이든 된다). `.env`는 커밋되지 않습니다(`.gitignore`). 키 값을 문서·코드·커밋 메시지에 쓰지 않습니다.
2. **진단**(`tools/collect.py`의 1단계, 따로: `python tools/tourapi_doctor.py --data data/incheon`): 키·네트워크·서비스 버전 문제를 한 번에 가리고, `site.json` `region_full`('인천광역시')의 법정동 시도 코드와 그 아래 구·군 코드를 TourAPI(ldongCode2)에서 받아 보여 줍니다(옛 지역코드 areaCode2는 참고). 코드는 저장하지 않고 수집할 때마다 같은 목록을 받아 씁니다(응답은 캐시). `site.json` `districts`와 이름이 다르면 '확인' 줄이 나옵니다. 키가 없으면 곧바로 멈추고 어디에 넣는지 알려 주며, 공급자 오류 메시지는 그대로 보이고 키 문자열만 가려집니다.
3. **수집**(`tools/collect.py`의 2단계 = `tools/tourapi_bulk.py --details --add-new --events`): 인천광역시 아래 구·군을 TourAPI 법정동 코드 목록대로 모두 돌며(`site.json` `tourapi.scope` 'sido') 지역 목록(관광지·문화시설·레포츠·쇼핑·숙박·음식점, 모든 쪽) → 매칭·좌표·사진(공공누리 제1·3유형만, '출처: 한국관광공사') → 행사(searchFestival2, **오늘부터**, 시도 전체) → 상세(detailCommon2·detailIntro2, 관광지·레포츠는 detailInfo2도: 전화·이용시간·쉬는 날·요금·주차·체크인, 필드별 출처·확인일) → TourAPI에만 있는 장소(draft, 그 구·군을 `district`로). overview는 사실 확인용으로만 남기고 화면에 내지 않습니다. `places.json`이 없어도 시작합니다. 쓰는 파일: `data/incheon/places.json`·`events.json`, `data/cache/tourapi/`(커밋 안 함), `reports/collect.md`·`tourapi_bulk.md`. 끝에 장소·구·군·좌표·사진·방문 판단 정보 채움·행사·**남은 호출 수**와 다음 명령을 출력합니다. 구·군 일부만: `--districts 연수구,강화군`. 진행 중인 행사(오늘 전에 시작)도 받으려면 `--events-from YYYYMMDD`. 키 없이 캐시로만 다시 만들기: `--offline`.

### TourAPI 호출 예산
실행당 상한 `--max-calls`(기본 900, 진단 포함)은 공공데이터포털 개발계정 일일 한도 안의 값입니다. 상한에 걸리면 받은 데까지 쓰고 종료 코드 3으로 멈추며, 같은 명령을 다시 실행하면 캐시에 있는 응답은 호출 없이 쓰고 나머지를 이어 받습니다. 첫 실행 뒤 출력되는 '목록 크기'와 '남은 호출'이 실제 수치입니다. 그 전에는 아래 식으로 어림합니다(D = TourAPI가 주는 구·군 수, N = 6개 유형 목록 항목 수, N₁ = 그중 관광지·레포츠, F = 오늘 이후 행사 수, n_dt = 구·군 d·유형 t의 항목 수).

- 진단: 검색 1(실패하면 최대 4) + 지역 코드 4
- 목록: 2 + Σ_d Σ_t max(1, ⌈n_dt / 200⌉) — 최소 6·D
- 행사: ⌈F / 100⌉ + 2F
- 장소 상세: 2N + N₁ (detailCommon2·detailIntro2, 관광지·레포츠는 detailInfo2 하나 더) — `--gallery`면 장소당 +1
- 합계 T ≈ 5 + 2 + 6D + ⌈F/100⌉ + 2F + 2N + N₁, 실행 횟수 ≈ ⌈T / 900⌉(하루 한 번)
4. **미리보기**: `python -m http.server -d dist-preview 8000` 으로 열어 봅니다. 미리보기는 draft까지 보이고 전부 noindex입니다. 수집 전(장소 0곳)에도 미리보기는 빈 상태 사이트로 만들어지고(안내 문구 출력), 공개 빌드는 '수집 전' 안내와 함께 멈춥니다.
5. **요약 쓰기와 문장 검사**: 수집한 장소는 `summary`가 비어 있고(draft) 요약이 생겨야 공개 선별·색인 대상이 됩니다. 요약은 그 장소의 사실(`facts`·값별 출처)만으로 답부터 쓰고(CLAUDE.md 3절 5항), FAQ는 데이터로 답할 수 있는 것만 존댓말 질문으로 씁니다(6항). TourAPI overview(`tourapi.overview`)는 사실 확인용이며 문장을 옮기지 않습니다. 쓴 뒤 `python tools/content_check.py --data data/incheon`이 원문 베끼기(overview·원문과 15자 이상 연속 일치, 이름·사실 값 제외), 숫자 대조(사실·출처 글에 없는 숫자), FAQ 출처 대조, 출처 해설체·'확인 필요'·근거 없는 수식어, FAQ 존댓말·장소 간 같은 질문을 봅니다. 하나라도 걸리면 종료 코드 1 — 문장을 고쳐 씁니다. 원문 베끼기는 빌드 검증(`pipeline.validate`)도 모든 페이지에서 오류로 잡습니다.
6. **공개 선별 미리보기**(`tools/build_review.py`): 요약과 주소 외 실용 정보가 함께 있는 장소(코스·가이드가 가리키는 곳 포함)만 골라 noindex 미리보기를 만들고, 고른 목록을 `reports/review_build_selection.json`에 씁니다. 선별은 검수·공개 승인이 아닙니다(status를 바꾸지 않음). 요약이 하나도 없으면 '선별 0곳'이라고 알립니다.
7. **운영자 공개 승인**(사람, `tools/approve_publication.py`): 6단계의 선별 목록에 든 장소와 가이드·코스·행사를 `status: published`로 바꾸고 `approved_at`(승인한 날)을 남깁니다. `--apply` 없이는 미리 보기만 합니다. 선별 목록이 없으면 6단계를 먼저 하라고 알리고 멈춥니다. 검수 시트(`tools/make_review_sheet.py` → `tools/apply_review.py`)는 공개 경로가 아닙니다: 시트에는 `tier: full` 장소와 가이드·코스·행사만 오르고(수집한 장소는 모두 `tier: basic`), OK로 표시한 행을 `status: reviewed`·`reviewed_at`(검수일)으로만 바꿉니다 — published 전환은 하지 않습니다.
8. **공개 설정과 공개 빌드**: 공개 빌드는 공개(published) 레코드만, 색인 기준 미달 페이지는 noindex·sitemap 제외로 만듭니다. production 검증은 아래 세 값이 비어 있거나 자리표시인 동안 오류(종료 코드 1)를 내며, 그동안 `public/`은 배포할 수 없습니다. 세 값 모두 운영자가 정합니다(CLAUDE.md 3절 7항·6절).
   - `site_url`: 최종 https 주소 — 운영자 결정 `https://incheon.webforai.kr`(2026-10-19).
   - `ga4_id`: GA4 측정 ID. 운영자가 GA4를 공개 뒤에 달기로 정했다면 `site.json`에 `"launch_exceptions": {"ga4_id": "<운영자 사유>"}`를 두면 경고로 바뀝니다.
   - `operator.contact`: 정정 요청을 받을 연락처.
   
   그 밖에 카카오 지도 JavaScript 키(`kakao_js_key`, 공개 키 — 그 도메인을 카카오 개발자 콘솔에 등록), 서치콘솔(구글·빙·네이버) 인증 토큰, GTM, IndexNow 키는 검증을 막지 않지만 공개 전에 넣습니다. 비어 있는 값과 할 일은 `python tools/launch_check.py --data data/incheon --stdout`이 보여 줍니다.
9. **Vercel**: 저장소를 Vercel 프로젝트에 연결합니다(Framework Preset: Other — 설정은 `vercel.json`: 빌드 명령 없음, 출력 `public/`, 설치 `npm ci --omit=dev`). Settings → Environment Variables에 `ANTHROPIC_API_KEY`(Production·Preview)를 넣고 재배포합니다(아래 '사이트 도우미'). 키가 없으면 `/api/chat/`은 503 `not_configured`로 답하고, 화면의 도우미는 'AI 도우미 준비 중'과 사이트 검색을 보이며 나머지 사이트는 그대로입니다.

### 도시 설정(`data/incheon/site.json`)
- **지역**: `region` '인천', `locality` '인천광역시', `districts` 지금 구·군 11곳(2026-07-01 행정체제 개편 뒤), `districts_former` 옛 이름(중구·동구·서구 — 주소·TourAPI가 옛 이름을 쓸 수 있어 둘 다 읽는다).
- **여행 권역**(`city.travel_regions`, method 'district', 운영자 결정 2026-10-19): 주소의 구·군(없으면 TourAPI가 준 구·군) 하나에 권역 하나 — 개항장·월미(제물포구) · 영종·용유(영종구) · 송도·연수(연수구) · 강화(강화군) · 옹진 섬(옹진군) · 도심·소래(미추홀·남동·부평·계양·서해·검단구). 옛 이름 주소는 그 자리를 이은 구를 따르고, 옛 중구만 법정동으로 나눈다. 지도 페이지가 이 설정에서 만든 기준 문장을 그대로 보인다.
- **카페·디저트·쇼핑**: TourAPI 신분류 `lclsSystm3` FD05…(카페/찻집)·FD030100(제과) — 신분류가 없으면 옛 cat3 A05020900 — 은 `kind: cafe`(목록 `/cafes/`, 음식점과 별도), 유형 38은 `kind: shopping`(목록 `/shopping/`). 수집이 장소마다 분류 코드(`tourapi.lclsSystm1·2·3`, cat1·2·3)를 남기고 종류를 그에 맞춘다(`pipeline/tourapi.kind_of`, `tools/tourapi_bulk.py` reclassify).
- **브랜드**: `site_name`·`brand` '인천각', `brand_symbol`(머리말·바닥글 심볼), `brand_colors`, 영어 이름 `city.intl.en.site_name` 'Incheongak', 홈 h1 `city.home.h1` '오늘, 인천 가는 각'. 심볼·로고·아이콘은 `python tools/brand_kit.py --data data/incheon --out templates/assets/brand --png`(shapely·fonttools·Playwright)로 다시 만든다.
- **거리 기준 장소**(`city.distance_anchors`): 수집한 데이터에서 이름으로 찾고, 없으면 빌드 경고와 함께 뺀다.
- **홈**(`city.home`): 홈 이야기 장·첫 화면 사진·갤러리·코스 지도·답 문구는 비어 있다 — 데이터와 운영자가 고른 사진이 생기면 넣는다. 그 전에는 그 블록 없이 데이터만으로 만든다. 가운데 사이트 도우미 카드는 `data/incheon/ask.json`이 켠다(장소가 생기면 보인다).
- **챗봇**(`city.chat`): 도시 이름(언어별)·추천 질문·추가 허용 출처. 빌드가 `public/chat/site.json`에 공개 주소·사이트 이름과 함께 쓰고, 함수(`chatbot/site.js`)와 화면(`templates/assets/chat.js`)이 그것을 읽는다. 코드에 도시 이름이 없다.
- **다른 언어판**: 한국어만(`city.intl` 비어 있음). `data/incheon/<code>`와 `city.intl.<code>` 이름이 둘 다 있어야 그 언어판이 만들어진다.

## 사이트 도우미(챗봇) — 키만 넣으면 켜진다
- 모델 Claude Haiku 5.5(`claude-haiku-5-5`, `chatbot/prompt.js`). 키는 환경 변수 `ANTHROPIC_API_KEY` 하나만 읽습니다(`ANTHROPIC_AUTH_TOKEN`이나 디스크의 프로필은 쓰지 않음). 키 값은 로그·응답·코드 어디에도 나오지 않습니다.
- 지식은 빌드가 만듭니다: `pipeline/chat_index.py` → `public/chat/`(`catalog.txt`·`docs.json`·`index.json`·`site.json`). 함수(`api/chat.js` → `chatbot/`)는 그 파일만 읽고, 사이트 주소·이름·도시 이름도 `site.json`에서 읽습니다. 수집·빌드를 다시 하면 도우미가 아는 내용도 함께 바뀝니다. 답은 이 사이트 데이터로만, 답마다 해당 페이지 링크, 질문한 언어로 하고, 대화는 저장하지 않습니다.
- **키가 없을 때**: `GET /api/chat/` → 503 `{"ready":false,"code":"not_configured"}`, 질문(POST)도 503 `not_configured`(모델을 부르지 않고 SDK도 불러오지 않음). 화면은 '물어보기'를 누르면 질문 칸 대신 **'AI 도우미 준비 중'** 과 사이트 검색 칸을 보이고, 홈 가운데 카드는 독자가 상자를 누르면 안내 줄이 'AI 도우미 준비 중 — …'으로, 버튼이 '검색하기'로 바뀌어 질문을 `/search/?q=`로 보냅니다(검색 페이지가 없는 수집 전에는 안내 문장만). 페이지는 처음 도우미를 쓸 때 `GET /api/chat/`을 한 번 묻고 그 답을 그 탭에 5분 기억합니다.
- **키를 넣은 뒤**: `GET /api/chat/` → 200 `{"ready":true}`, 다른 변경 없이 질문에 답합니다.

### 로컬에서 실제 키로 시험
```bash
python -m pipeline.build --data data/incheon --out dist-preview --mode preview
export ANTHROPIC_API_KEY=…                      # 또는 키를 .env에 두고: node --env-file=.env tools/chat_dev.mjs
npm run chat:dev                                # http://127.0.0.1:8787 — dist-preview를 보여 주고 /api/chat/을 Vercel 함수와 같은 처리기로 답한다
curl -s http://127.0.0.1:8787/api/chat/         # {"ready":true}
```
- `--dir public`(공개 빌드), `--port 8787`, `--host 0.0.0.0`(같은 와이파이의 휴대폰에서 열기 — 시험할 때만). 키 없이 띄우면 'AI 도우미 준비 중' 화면을 그대로 볼 수 있습니다.
- 질문마다 실제 API를 부르므로 비용이 듭니다(질문 하나의 출력 상한 11,500토큰, `chatbot/server.js` `LIMITS`). `vercel dev`(Vercel CLI 로그인 필요, 같은 환경 변수)로도 됩니다.
- 시험(`npm test`, `python -m pytest`)은 키 없이 가짜 모델 스트림으로 돌고 네트워크에 나가지 않습니다: 키 없음 503, 키를 넣으면 답과 링크(`tests/js/keyready.test.js`), 빌드한 지식으로 끝까지(`tests/test_chat_key_ready.py`), 화면의 준비 중 상태(`tests/test_chat_key_ready_browser.py`, Playwright).

### Vercel에 키 넣기
1. Vercel 프로젝트 → Settings → Environment Variables → Add: Key `ANTHROPIC_API_KEY`, Value에 키, Environments는 Production(미리보기 배포에서도 쓰려면 Preview도) → Save.
2. 환경 변수는 새 배포부터 적용됩니다: Deployments → 최신 배포 → ⋯ → Redeploy(또는 `main`에 push).
3. 확인: `curl -s https://<도메인>/api/chat/` → `{"ready":true}`. 사이트에서 '물어보기'로 한 번 물어 답과 페이지 링크가 오는지 봅니다. 키를 넣기 전에 열어 둔 탭은 '준비 중'을 최대 5분 기억하므로 새 탭에서 확인합니다.
4. 허용 출처: `site.json` `site_url`, 이 배포의 Vercel 주소(시스템 변수 `VERCEL_URL`·`VERCEL_BRANCH_URL`·`VERCEL_PROJECT_PRODUCTION_URL` — 따로 켤 것 없음), `city.chat.origins`(예: 사용자 도메인을 붙인 뒤에도 쓰는 `<프로젝트>-<팀>.vercel.app` 별칭). 도메인을 정하기 전에도 `*.vercel.app` 배포 주소에서 바로 시험할 수 있습니다. 단 배포할 `public/`은 공개 빌드가 만들며, 공개 빌드는 위 8단계의 세 값(`site_url`·`ga4_id` 또는 `launch_exceptions.ga4_id`·`operator.contact`)이 채워져야 검증을 통과합니다.
5. 운영자 안전 설정: Anthropic Console의 사용 한도(spend limit), Vercel Firewall의 `/api/chat/` 요청 수 제한 규칙. 함수도 인스턴스마다 IP당 분·일 한도와 전체 분·일 한도를 둡니다(`LIMITS`).
6. 문제 확인: Vercel → Logs에 요청마다 JSON 한 줄(`evt: chat`, 상태·도구 이름·토큰 수 — 질문·답·주소·키는 남기지 않음). 키가 틀리거나 폐기되면 `status: unavailable`, `api_status: 401`, `hint: check ANTHROPIC_API_KEY`가 남고, 화면에는 "지금은 답을 만들 수 없습니다"가 나옵니다.

## AI 코스 만들기(/plan/)
- 조건(날짜·시간·이동 수단·동행·취향·필요한 것·입장료 예산)을 고르면 모델이 이 사이트 장소로 일정을 짜고, 코드가 휴무·운영시간·입장 마감·구간 여유·입장료를 데이터로 다시 검사해 보여 줍니다(`chatbot/planner.js`, `api/plan.js`). 키는 사이트 도우미와 같은 `ANTHROPIC_API_KEY`이고, 키가 없으면 `/api/plan/`이 503 `not_configured`로 답합니다. Vercel 설정은 `vercel.json` `functions."api/plan.js"`(최대 60초, `public/chat/**` 포함).
- 장소가 있으면 빌드가 `/plan/`과 `/plan/places.json`을 만들고 머리말·홈에 입구를 답니다. 코스·가이드가 없어도 동작하고(대신 '가볼만한 곳'으로 안내), 출발·도착 장소는 `site.json` `city.plan.hubs`(이름만)가 있을 때만 고를 수 있습니다. 인천은 아직 비어 있습니다(운영자 결정).

## 명령어
```bash
python -m pytest                                   # 파이썬 시험(Node가 있으면 챗봇 서버 시험도 함께)
npm test                                           # 챗봇 서버 시험만(node --test tests/js/)
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/quality_report.py --data data/incheon --out public       # 정보 채움률(전화·이용시간·주차·사진·좌표)
python tools/content_check.py --data data/incheon                   # 우리가 쓴 요약·FAQ 검사(원문 베끼기·숫자·출처·표현)
python tools/build_review.py --data data/incheon --out dist-review --report-dir reports   # 공개 선별 미리보기(noindex)
python tools/approve_publication.py --data data/incheon --date <날짜>   # 운영자 공개 승인 미리 보기(사람이 정하면 --apply)
python tools/launch_check.py --data data/incheon --stdout             # 공개 전 점검표
python tools/make_review_sheet.py --data data/incheon --out reports/review.csv   # 검수 시트(tier=full 장소·가이드·코스·행사, 사람이 OK 표시)
python tools/apply_review.py --sheet reports/review.csv --data data/incheon      # OK 행을 reviewed·검수일로(기본 dry-run, 공개 전환은 안 함)
python tools/perf_check.py --out public                              # 모바일 속도(Playwright 필요)
python tools/link_check.py --data data/incheon                       # 홈페이지·예약 주소 점검(한국 네트워크에서 한 달에 한 번, --apply면 dead_links.json에 후보)
python tools/tourapi_bulk.py --data data/incheon --nearby-only       # 저장된 좌표로 주변 장소만 다시 계산(호출 없음)
python tools/tourapi_bulk.py --data data/incheon --barrier-free --max-calls 600   # 무장애 여행 정보(KorWithService2, 별도 활용신청)를 공개 장소에 병합
```
- 챗봇을 로컬에서 실제 키로 시험: `npm run chat:dev`(위 '사이트 도우미'). 대화는 저장하지 않습니다.
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
