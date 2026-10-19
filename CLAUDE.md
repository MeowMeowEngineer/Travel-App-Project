# CLAUDE.md — 인천 여행 사이트 (가칭 '인천 여행의 모든 것')

> 이 파일이 최우선 지시다. 군산 여행 사이트(https://gunsan.webforai.kr)의 엔진을 복사해 2026-10-19에 시작했다.
> 데이터 표준: `docs/02_page_standard.md` · 사람이 정할 것: 6절 · 시작 방법: `README.md`

## 1. 무엇을 만드는가
- 여행자가 실제로 쓰는 인천 여행 사이트(관광지·맛집·숙소·코스·행사)이자, 공개 후 AI 답변엔진 인용·유입을 측정할 실험 사이트다.
- 정적 사이트: Python 엔진(`pipeline/`)이 `data/incheon/*.json`을 `public/`으로 빌드하고, Vercel이 그대로 배포한다.
- 사이트 도우미(챗봇): `api/chat.js`(Vercel 함수) + `chatbot/`.
- 목표: **키만 넣으면 사이트가 나온다.** `TOURAPI_KEY` → 수집 → 빌드 → 검증 → Vercel 배포(`ANTHROPIC_API_KEY`). 순서는 `README.md`.

**성공 기준**
1. 공개 페이지가 '방문 판단 정보'(이용시간·쉬는 날·요금·주차·전화·체크인)로 채워져 있다.
2. 얇은 페이지는 색인되지 않는다(3절 8항).
3. 사람이 검수와 공개 설정만 하면 바로 공개·측정을 시작할 수 있다.

안전장치·문서·테스트·모션의 양은 성공 기준이 아니다.

## 2. 지금 상태 (2026-10-19)
- 엔진·템플릿·테스트·범용 도구를 군산 저장소에서 복사했고(이력 없이), 도시와 무관하게 고쳤다. **도시마다 다른 값은 `data/<도시>/site.json`(지역 키와 `city` 블록) 한 곳에 있고 `pipeline/city.py`가 읽는다** — 주소 앞부분, 공식 관광 사이트, 여행 권역과 그 기준, 거리 기준 장소, 지정 목록, 홈 이야기·사진 고르기·답 문구, 검색 예시, 챗봇 이름·추천 질문, 다른 언어판 이름. 엔진 코드(`pipeline/`·`templates/`·`tools/`·`chatbot/`)에 도시 이름을 쓰지 않는다(`tests/test_city.py`가 인천 설정 빌드에 다른 도시 이름이 없는지 본다).
- `data/incheon/`: `site.json`·`icons.json`·`ask.json`. 장소 데이터는 아직 없다 — TourAPI 키가 오면 수집한다. 수집 전에는 미리보기 빌드가 빈 상태 사이트를 만들고(안내 출력), 공개 빌드는 '수집 전' 안내와 함께 멈춘다.
- 광역시 처리: `tools/tourapi_bulk.py`가 `site.json` `tourapi.scope` 'sido'면 TourAPI 법정동 코드 목록의 구·군을 모두 돈다(`--districts`로 일부만). 새 장소는 그 구·군을 `district`로 단다.
- 군산 실데이터(`data/gunsan`)·군산 그림·군산 문서에 기대던 테스트와 군산 측정 질문 도구는 옮기지 않았다: `tests/excluded_gunsan_tests.txt`. 인천 데이터가 생기면 같은 성질의 시험을 인천 데이터로 다시 쓴다. 엔진 시험의 고정 데이터는 `data/sample/`(군산 모양의 가짜 샘플)과 `tests/fixtures/incheon_tiny/`(인천 설정용 가짜 장소 5곳)다.
- 마스코트는 없다(군산 마스코트는 '군산 사이트 전용'). 엔진은 마스코트 없이 동작한다(`pipeline/icons.py` `mascot()`).

## 3. 지켜야 할 규칙
1. **사실은 출처 데이터에서만** 가져온다: TourAPI(한국관광공사), 인천광역시·인천관광공사 공식 관광 사이트, 해당 시설 공식 홈페이지.
   - 인천의 장소·시간·요금·개수·좌표를 지어내지 않는다. 추정이나 일반 지식으로 채우지 않는다.
   - 없는 값은 블록마다 "확인 필요: 요금·주차"처럼 한 번만 쓰거나 그 블록을 뺀다.
   - `data/sample/`은 테스트용 가짜 데이터(군산 샘플)다. 인천 콘텐츠로 내보내지 않는다.
2. **필드별 출처**: 한 장소의 사실이 여러 출처에서 오면 필드마다 출처와 확인일을 남기고 화면에도 출처를 표시한다.
   - 두 출처 값이 다르면 둘 다 보여 주고 "방문 전 전화 확인"을 한 줄 붙인다. 한쪽을 임의로 고르지 않는다.
   - 화면에는 확인일을 표시하지 않는다(군산 운영자 결정 2026-10-09을 옮김). 데이터와 구조화 데이터의 날짜는 남긴다.
3. **시 공식 관광 사이트의 원문·사진은 게재하지 않는다**(확인 전 기본값).
   - 인천투어(https://itour.incheon.go.kr/) 하단: "COPYRIGHT(c) 2018 Incheon Metropolitan City. ALL RIGHTS RESERVED.", 첫 화면에 공공누리 표시 없음(2026-10-19 확인).
   - `site.json` `city.official`(이름·짧은 이름·주소 도메인)이 출처 줄과 링크 판단에 쓰인다.
   - 원문은 링크로만 건다. 설명은 우리 문장으로 쓴다(원문과 15자 이상 연속 일치 금지).
   - 표의 값(시간·요금·메뉴)은 값 그대로 써도 된다.
   - 페이지에 공공누리 표시가 따로 있으면 그 유형을 확인한 뒤 따른다(6절).
4. **TourAPI 이미지**
   - `cpyrhtDivCd`가 Type1·Type3인 것만 쓰고 "출처: 한국관광공사"를 표기한다(`site.json` `publish_rules`).
   - Type3은 자르기·확대·보정을 하지 않는다. 자르는 자리(홈 첫 화면 등)에는 Type1만 쓴다.
   - overview 문장은 게재하지 않고 사실 확인용으로만 쓴다(사람 결정 전).
5. **요약 문장**: 답부터 쓰는 평서문으로 쓴다.
   - "○○은 인천광역시 ○○구에 있는 ○○입니다"로만 끝내지 않는다. 그 장소만의 사실(대표 메뉴·좌석·객실 수·운영 특징·볼거리)을 하나 이상 넣는다.
   - 쓸 사실이 없으면 짧게 두고 색인 대상에서 뺀다(8항). "원문은 ~" 같은 출처 해설체는 쓰지 않는다.
6. **FAQ**: 질문은 존댓말 "~나요?/~인가요?"로 통일한다. 같은 질문을 여러 장소 페이지에 반복하지 않는다(지역 단위 질문은 가이드로). 데이터로 답할 수 없는 질문은 만들지 않는다.
7. **공개는 사람이 정한다**
   - `status=published`, `reviewed_at`·`approved_at`, `site.json`의 `site_url`·`site_name`·`brand`·`ga4_id`·`gtm_id`·`search_verification`·`kakao_js_key`·`operator`·`publish_rules`·`crawler_policy`, noindex·robots 해제는 바꾸지 않는다.
   - 사람이 표시한 검수 시트를 그대로 반영하는 스크립트(`tools/apply_review.py`, 기본 dry-run)와 운영자 공개 승인(`tools/approve_publication.py --apply`)은 사람이 지시할 때만 실행한다.
8. **색인 기준(production)**: 장소 페이지는 세 조건을 모두 갖췄을 때만 색인한다.
   - (a) 유형별 필수 정보가 2개 이상이다(`pipeline/schema.py` `INDEX_KIND_GROUPS`).
   - (b) 요약이 5항을 지킨다.
   - (c) `reviewed_at` 또는 운영자 공개 승인(`approved_at`)이 있다.
   - 미달 페이지는 noindex로 내보내고 sitemap·llms.txt에서 뺀다. 목록·지도에는 남긴다.
9. **비밀값**
   - `TOURAPI_KEY`는 환경 변수나 `.env`에 둔다. `ANTHROPIC_API_KEY`는 Vercel 환경 변수에 둔다(로컬 시험은 환경 변수나 `.env`).
   - `.env`는 커밋하지 않는다(`.gitignore`). `.env`를 열어 보거나 출력하지 않는다.
   - 키 값을 코드·문서·로그·커밋 메시지 어디에도 쓰지 않는다. 로그에서는 키 문자열만 가리고, 공급자 오류 메시지는 그대로 보인다.
   - 카카오 지도 JavaScript 키는 공개 키라 `site.json` `kakao_js_key`에 둔다(등록한 도메인에서만 동작).
10. **제3자 콘텐츠 금지**: 네이버 플레이스·블로그·리뷰·평점은 복제하지 않는다. 회원가입·예약·결제는 넣지 않는다. 특정 업체를 근거 없이 추천하지 않는다.
11. **사이트 도우미(챗봇)**
    - 모델: Claude Haiku 5.5 `claude-haiku-5-5`(`chatbot/prompt.js` `MODEL`).
    - 키: `ANTHROPIC_API_KEY` 환경 변수에만 둔다(Vercel Settings → Environment Variables). 키가 없으면 `/api/chat/`은 503 `not_configured`로 답하고, 사이트의 질문 상자는 사이트 검색으로 동작한다.
    - 이 사이트 데이터로만 답한다(1·2항 그대로 — 없는 값은 '사이트에 없음'과 공식 확인처, 출처가 다르면 둘 다). 답마다 해당 페이지 링크를 단다.
    - 질문한 언어로 답한다. 대화는 저장하지 않는다. 회원가입·예약·결제는 넣지 않는다.
    - 지식은 빌드가 만든다(`pipeline/chat_index.py` → `public/chat/`). 함수는 그 파일만 읽는다.

## 4. 하지 말 것
- 방어 장치(누적 장부·잠금·메시지 은폐)를 새로 만들지 않는다. 실행당 상한과 캐시, 키 마스킹이면 충분하다.
- 검증 규칙을 완화해서 통과시키지 않는다. 테스트·문서 분량을 목표로 삼지 않는다.
- 빈 데이터를 장식으로 덮지 않는다(가짜 사진, AI 이미지, 가짜 지도, 큰 빈 표지).
- AI 일러스트는 배경·캠페인 그림·장식에만 쓰고 실제 사진처럼 내보이지 않는다.
  - alt는 '일러스트'로 시작한다. 소개 페이지(/about/)에 '이 사이트의 일러스트는 생성형 AI로 그렸다'고 한 번 적는다.
  - 장소 사진 자리·썸네일과 구조화 데이터(ImageObject·장소 og:image)에는 쓰지 않는다.
  - 'AI 생성 이미지' 표기는 하지 않는다(`pipeline/art.py`·validate가 검사).
- 군산 사이트의 일러스트·사진·마스코트는 군산을 그렸거나 군산 전용이라 쓰지 않는다. 옮긴 그림은 도시와 무관한 3D 아이콘 28장(`templates/assets/icons/`)·브랜드(운영사 로고)·글꼴뿐이다.
- 첫 화면 내용을 스크립트로 숨겼다가 보여 주지 않는다. 연출은 첫 화면 아래 요소에만 쓴다.
- '멈추고 보고'를 남발하지 않는다. 6절 항목만 사람에게 넘기고, 나머지는 판단해서 진행한다.
- `public/`을 직접 고치지 않는다. 빌드로만 갱신한다.

## 5. 화면·성능·접근성 기준
- **장소 첫 화면(390px)**: 이름 → 한 줄 답 → 핵심 정보 줄(운영시간·쉬는 날·요금·주차·전화 중 있는 값). 사진은 모바일에서 화면 높이의 45% 이하, 썸네일 줄은 핵심 정보 아래.
- **길찾기**: 앞줄에 3개(네이버 지도·카카오맵·길찾기)만 두고 나머지는 '다른 지도'로 접는다. 좌표·ID가 있는 정확 링크를 우선한다.
- **사진 없는 항목**: 큰 빈 표지 대신 작은 유형 아이콘 + 텍스트 행.
- **카드 칩**: 핵심 값을 말줄임으로 자르지 않는다.
- **목록 지도**: 좌표가 있는 항목이 30% 미만이면 지도를 기본으로 접고 "좌표가 있는 n곳만 표시"라고 적는다.
- **고정 영역**: 모바일 고정 영역 합 ≤ 화면의 15%.
- **검색**: 이름·대표 메뉴·지역. 빌드 때 만든 정적 색인 + 작은 JS, JS가 없으면 목록 링크.
- **지도 페이지**: 구·군·동 묶음에 여행 권역 보기를 더하고, 권역을 나눈 기준을 페이지에 적는다(설정 `city.travel_regions`에서 만든 문장 — 장소를 나눈 바로 그 규칙). 지도 제공자는 카카오맵(`site.json` `kakao_js_key`).
- **인천 권역**(제안, 운영자 확인): 주소의 구·군(없으면 TourAPI 구·군)으로, 옛 중구만 법정동으로 나눈다 — 개항장·원도심(제물포구·동구·영종 법정동 밖 중구), 영종·용유(영종구·중구 운서·운남·운북·중산·을왕·남북·덕교·무의동), 송도·연수(연수구), 도심 생활권(미추홀·남동·부평·계양·서해·서·검단구), 강화(강화군), 옹진 섬(옹진군). 법정동이 없는 중구 주소는 '권역 미정'.
- **모션**(GSAP·Lenis): 첫 화면 요소는 처음부터 보이게 한다. reduced-motion이거나 JS가 없으면 최종 상태로 보여 준다. Lenis는 데스크톱에만.
- **글꼴**: Pretendard를 unicode-range 분할로 자체 호스팅한다(`tools/font_subset.py`).
- **성능 목표**(`tools/perf_check.py`, 느린 4G·CPU 4배): LCP ≤ 2.5초, CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB.
- **접근성**: 대비 4.5:1, 터치 영역 44px, 보이는 포커스, 이미지 alt.

## 6. 사람이 정할 것 — 결정하지 말고 선택지와 권장안으로 보고
- **도메인**(`site_url`): 지금은 자리표시 `https://incheon.example.com`(production 검증이 막는다). 처음부터 최종 주소로 정한다(권장: 회사 하위 주소). 공개 뒤에는 바꾸지 않는다.
- **사이트 이름**: '인천 여행의 모든 것'은 가칭이다. 도메인과 같은 이름으로 읽히게 확정한다. 운영 표기(에이아이오투오)도 확인한다.
- **GA4·GTM**(도시별 별도 속성), **검색엔진 인증 토큰**(구글·빙·네이버), IndexNow 키(공개 직전).
- **공개**: 공개 범위·시점, 검수(검수 시트), 운영자 공개 승인.
- **정정 요청 연락처**(`operator.contact`), 편집 책임자 표기.
- **페이지 주소 형식**: 한글 슬러그 / 영문 슬러그 — 공개 전에 정한다.
- **범위**: 구·군 11곳 전체 / 권역부터(`tools/tourapi_bulk.py --districts`).
- **구·군 이름**: 2026-07-01 「인천광역시 제물포구ㆍ영종구 및 검단구 설치 등에 관한 법률」 시행(국가법령정보센터 확인)으로 중구·동구가 폐지되고 제물포구·영종구·검단구가 생겼다. 서구의 새 이름 '서해구'는 위키백과로만 확인했다 — 확인 필요. 영종구 법정동 8개(권역 규칙)도 위키백과에서 옮겼다 — 행정표준코드로 확인.
- **여행 권역 이름과 나눔**(`city.travel_regions`), **거리 기준 장소**(`city.distance_anchors`: 인천국제공항·차이나타운·송도센트럴파크·월미도 제안), **홈 이야기·첫 화면 사진**(`city.home`), **시 지정 음식점 목록**(`city.designations`, 조사 전).
- **출처 이용 조건**: 인천투어·인천관광공사 자료의 이용 조건, 추가 출처 수집 범위, TourAPI overview 게재 여부.
- **카카오 지도 JavaScript 키**: 새 도메인을 카카오 개발자 콘솔에 등록하고 키를 보낸다.
- `publish_rules`·`crawler_policy`: 군산 값을 기본으로 옮겼다. 인천용으로 확인한다.
- 마스코트·일러스트를 새로 만들지, 영어·다국어판을 할지(권장: 한국어만 먼저).
- 저장소 공개 여부와 원본 데이터(`data/raw`) 위치.

## 7. 명령어
```bash
python -m pip install -r requirements.txt
npm ci                                   # 챗봇 함수의 SDK(@anthropic-ai/sdk, 고정 버전)
python -m pytest                         # 파이썬 시험(Node가 있으면 챗봇 시험도 함께)
npm test                                 # 챗봇 서버 시험만(node --test)
python tools/tourapi_doctor.py --data data/incheon                   # TourAPI 연결 진단 — 가장 먼저
python tools/tourapi_bulk.py --data data/incheon --details --add-new --events --max-calls 900   # 수집(구·군 전부, 이어받기)
python -m pipeline.build --data data/incheon --out dist-preview --mode preview
python -m pipeline.validate --data data/incheon --out dist-preview --mode preview
python tools/build_public.py --data data/incheon --out public          # 공개 빌드 + 검증(production)
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/quality_report.py --data data/incheon --out public
python tools/perf_check.py --out public                               # Playwright 필요
```
- 도구의 `--data` 기본값은 `data/incheon`이다. 새 도시는 `data/<도시>/site.json`을 만들고 `--data`로 넘긴다(엔진은 바꾸지 않는다).
- `main`에 push하면 Vercel이 `public/`을 배포한다. 공개 전환은 사람이 정한다.

## 8. 코드·데이터 지도
| 경로 | 역할 |
|---|---|
| `data/incheon/site.json` | 사이트 설정(지역·구·군·출처·공개 규칙·사람이 정할 값)과 도시 설정 `city` 블록(권역·기준 장소·홈·챗봇·다국어 이름) |
| `pipeline/city.py` | 도시 설정을 읽는 한 곳(빌드·검증·도구가 site.json으로 활성화) |
| `data/incheon/ask.json` | 홈 가운데 사이트 도우미 카드를 켠다(추천 질문은 데이터가 생기면) |
| `data/incheon/icons.json` | 3D 그림 자리 등록부(id → glyph·label) |
| `data/incheon/*.json` | 장소·코스·가이드·행사(수집 뒤 생긴다) |
| `data/sample/` | 테스트용 가짜 데이터(군산 샘플). 공개하지 않는다 |
| `pipeline/` | 빌드·검증·구조화 데이터·화면 데이터·TourAPI 클라이언트·챗봇 지식 |
| `templates/` | 화면(Jinja2)·CSS·JS·글꼴·3D 아이콘 |
| `tools/` | TourAPI 진단·수집, 공개 빌드, 검수 시트·반영, 품질·성능·공개 전 점검 |
| `chatbot/`, `api/chat.js` | 사이트 도우미(Vercel 함수). 사이트 주소·이름·도시 이름은 빌드가 쓴 `public/chat/site.json`에서 읽는다(`chatbot/site.js`) |
| `tests/` | pytest + `tests/js/`(node --test). 고정 데이터 `data/sample/`·`tests/fixtures/incheon_tiny/`. 옮기지 않은 군산 전용 시험: `tests/excluded_gunsan_tests.txt` |
| `docs/02_page_standard.md` | 데이터 표준 |
