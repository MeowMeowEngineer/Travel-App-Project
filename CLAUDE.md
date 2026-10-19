# CLAUDE.md — 인천각(Incheongak), 인천 여행 사이트

> 이 파일이 최우선 지시다. 군산 여행 사이트(https://gunsan.webforai.kr)의 엔진을 복사해 2026-10-19에 시작했다.
> 데이터 표준: `docs/02_page_standard.md` · 사람이 정할 것: 6절 · 시작 방법: `README.md`

## 1. 무엇을 만드는가
- 여행자가 실제로 쓰는 인천 여행 사이트(관광지·맛집·카페·숙소·쇼핑·코스·행사)이자, 공개 후 AI 답변엔진 인용·유입을 측정할 실험 사이트다.
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
- `data/incheon/`: 설정 `site.json`·`icons.json`·`ask.json`·`art.json`과 수집 결과 `places.json`·`events.json`·`image_sizes.json`. **첫 TourAPI 수집(2026-10-19)**: 관광지 260곳(모두 draft, 요약 없음 — 좌표 260·사진 245, 필드별 출처)과 행사 6건을 받고 하루 한도로 멈췄다. 남은 호출(약 3,736회 — 목록 1,946곳 가운데 아직 상세를 받지 않은 나머지 관광지·문화시설·레포츠와 쇼핑 585·음식점(카페 포함) 577·숙소 78)은 `python tools/collect.py --data data/incheon`로 날마다 이어 받는다(실행당 900회, 4~5일). 이 명령이 끝에 사진 크기(`image_sizes.json`, `tools/image_sizes.py`)도 갱신한다. `places.json`·`events.json`은 수집 도구로만 바꾼다.
  - **목록만으로 먼저 실음(2026-10-19, `python tools/collect.py --data data/incheon --lists-only` — 호출 없음, 캐시의 목록 응답만)**: TourAPI 목록의 나머지 1,686곳을 draft로 더해 장소가 1,946곳(목록 전체)이다 — 관광지 706·카페·디저트 113·음식점 464·쇼핑 585·숙소 78, 구·군 강화군 350·연수구 372·서해구 227·영종구 193·제물포구 176·남동구 136·옹진군 122·부평구 125·미추홀구 114·계양구 77·검단구 54. 그 1,686곳은 목록 값만(이름·주소·구·군·좌표·제1·3유형 사진 1,478곳(제1유형 265·제3유형 1,213), 값마다 출처·확인일 — 목록에는 전화가 없다)이고 `tourapi.details_pending`이 붙어 있다. 날마다 하는 수집의 상세 단계가 그 장소들을 다른 장소처럼 받아 채우고 표시를 지운다(새 장소로 다시 더하지 않고 slug도 그대로, `tools/tourapi_details.complete_listed`). 그때까지 그 페이지의 방문 판단 정보는 '확인 필요'뿐이다. 사진 크기는 같은 날 `tools/image_sizes.py`(사진 주소, TourAPI 호출 아님)로 기록했다 — 원본 1,723장 전부, 작은 크기 파일 1,607장(116장은 제공처 404라 목록에서도 원본). 장소가 0곳인 빌드(새 도시의 첫 설정)는 미리보기가 빈 상태 사이트를 만들고(안내 출력), 공개 빌드는 '수집 전' 안내와 함께 멈춘다.
- 광역시 처리: `tools/tourapi_bulk.py`가 `site.json` `tourapi.scope` 'sido'면 TourAPI 법정동 코드 목록의 구·군을 모두 돈다(`--districts`로 일부만). 새 장소는 그 구·군을 `district`로 단다. 시도·구·군 코드는 저장하지 않고 실행 때 TourAPI(ldongCode2)에서 받는다(`tools/tourapi_doctor.py`가 보여 준다).
- 키를 받으면: `python tools/collect.py --data data/incheon` 한 명령(키 확인 → 진단 → 목록·좌표·사진 → 행사(오늘부터) → 상세 → TourAPI에만 있는 장소 → 요약·남은 호출·다음 명령). 호출 예산 식은 `README.md` 'TourAPI 호출 예산'.
- 군산 실데이터(`data/gunsan`)·군산 그림·군산 문서에 기대던 테스트와 군산 측정 질문 도구는 옮기지 않았다: `tests/excluded_gunsan_tests.txt`. 인천 데이터가 생기면 같은 성질의 시험을 인천 데이터로 다시 쓴다. 엔진 시험의 고정 데이터는 `data/sample/`(군산 모양의 가짜 샘플)과 `tests/fixtures/incheon_tiny/`(인천 설정용 가짜 장소 5곳)다.
- **그림(운영자 납품 2026-10-19, `docs/image_prompts_incheongak.md`, 137장)** — 원본 `incoming/{brand,mascot,icons,ai-images}/<ID>.png`는 커밋하지 않고 파생본(AVIF·WebP)만 커밋한다.
  - 마스코트 점박이물범(B): `tools/mascot_media.py` → `templates/assets/mascot/`. 자리: AI 챗봇 버튼(icon-3d), 홈 질문 상자·코스 만들기 안내(hello), 챗봇 답 기다림(think)·오류(sorry), 검색 머리(search), 목록 필터 0건(empty), 404(404), `/plan/`(plan·plan-done, 수정 상자 자리는 point). mascot-base는 기준 그림이라 싣지 않는다. 엔진은 마스코트 없이도 동작한다(`pipeline/icons.py` `mascot()`).
  - 소품 든 물범(mascot-eat·-cafe·-camera·-airport·-ferry)과 3D 아이콘(C·D·I): `tools/icon_media.py`(원본 `incoming/icons/`와 `incoming/mascot/`의 등록부 ID) → `templates/assets/icons/`, 등록부 `data/incheon/icons.json`. 홈 메뉴(icon-*), 사진 없는 장소·행사(kind-*, 행사 페이지는 kind-festival), 코스 만들기(theme-*·sit-*·transit-bus), 음식점·카페 목록 머리(mascot-eat·-cafe), 영상 목록 머리(mascot-camera). 가이드 머리 그림은 `site.json` `city.guide_pics`({가이드 id: [그림, glyph, px]} — 가는 법 가이드가 생기면 mascot-airport), 섬 테마는 mascot-ferry. transit-subway·-ferry·-plane, theme-sky-airport·-tidal-flat은 등록만(쓰는 페이지가 아직 없다).
  - 일러스트 80장(E–M): `data/incheon/art.json` → `tools/art_media.py` → `templates/assets/art/`. 권역(area-* — 지도 권역 띠와 홈 권역 줄, `site.json` `city.travel_regions[].art`), 목록 머리(head-* — 카페·쇼핑 포함), 홈 소식 카드(card-event·-guide·-video), 월(month-*), 행사 종류(evkind-* — `city.event_kind_words`가 인천 종류 heritage·film·design·airport를 만들고 sports는 race 자리), 영상 주제(vtopic-*), 소개 머리·404·빈 검색·챗봇 첫 화면·코스 만들기 머리. card-course·-cafe·-island·-airport·-season과 가이드 머리 camp-*-notext 18장은 자리가 아직 없어 '개편 뒤 연결'로 등록만 했다(가이드가 생기면 slot을 `guide.banner.<가이드 id>`로). 장소가 하나도 없는 동안(수집 전)에는 일러스트를 싣지 않는다(빈 데이터를 장식으로 덮지 않음). 그림을 싣는 빌드에서 /about/에 '생성형 AI' 안내가 없으면 검증 오류다.
  - 로고 시안(A)은 `tools/brand_kit.py`가 도형으로 다시 그린 SVG만 쓴다(원본 래스터는 싣지 않는다).
- **운영자 결정(2026-10-19)**
  - **이름**: 인천각(MZ 표현 '~하는 각?' — '오늘 인천 가는 각'), 영어 **Incheongak**. `site.json` `site_name`·`brand` '인천각', 영어 이름은 `city.intl.en.site_name`(영어판을 만들 때의 이름, 로고 아래 줄). 가칭 '인천 여행의 모든 것'은 쓰지 않는다. 머리말·바닥글은 심볼(`brand_symbol`) + '인천' 잉크 + '각' 로고 파랑(`pipeline/present.wordmark`, css `--brand`). 페이지 제목·og:site_name·구조화 데이터 WebSite 이름은 site_name에서 나온다. 홈 첫 화면 h1은 `city.home.h1` '오늘, 인천 가는 각'(없으면 '<지역> 여행의 모든 것').
  - **로고**: 시안 A(인천대교 주탑 + 책갈피, `incoming/brand/logo-a-bridge.png`와 단색·반전 래스터 — 커밋 안 함)를 래스터에서 재서 도형으로 다시 그렸다: `tools/brand_kit.py`(shapely·fonttools, 이 도구만) → `templates/assets/brand/incheongak-symbol.svg`(머리말·바닥글)·`-symbol-reverse`·`-symbol-mono`·`-logo`(가로형, 글자는 Pretendard Bold 윤곽)·`-app-icon`, `icon-48/96/180/192/512.png`·`favicon.ico`. 색은 `site.json` `brand_colors`(바다 파랑 #1764C0, 노을 코랄 #FF7A5C, 잉크 #172033).
  - **도메인**: `site_url` https://incheon.webforai.kr — canonical·sitemap·robots·llms.txt·챗봇 허용 출처(`public/chat/site.json`)·IndexNow host가 모두 이 값에서 나온다. 카카오 지도 키는 이 도메인을 등록한 키여야 한다.
  - **구·군**: TourAPI ldongCode2(lDongRegnCd 28)가 돌려주는 11곳 — 제물포구·영종구·미추홀구·연수구·남동구·부평구·계양구·서해구·검단구·강화군·옹진군(`districts`). 옛 이름 중구·동구·서구는 `districts_former`로 둔다(옛 주소를 읽는다).
  - **여행 권역**: 장소마다 주소의 구·군 하나로 권역 하나 — 개항장·월미 = 제물포구, 영종·용유 = 영종구, 송도·연수 = 연수구, 강화 = 강화군, 옹진 섬 = 옹진군, 도심·소래 = 미추홀·남동·부평·계양·서해·검단구. 옛 이름 주소는 그 자리를 이은 구를 따른다(동구 → 개항장·월미, 서구 → 도심·소래, 중구는 영종도 법정동 8개면 영종·용유, 그 밖이면 개항장·월미, 법정동 없으면 '권역 미정'). 지도 페이지가 이 규칙을 설정에서 만든 문장으로 보인다.
  - **카페·디저트**(음식점과 별도): TourAPI 신분류 `lclsSystm3`가 FD05로 시작(카페/찻집: 카페·찻집·기타음료점)하거나 FD030100(제과)이면 `kind: cafe`. 신분류가 없을 때만 옛 cat3 A05020900(카페/전통찻집)도 센다(`pipeline/tourapi.kind_of`). 목록 `/cafes/`, 메뉴, 홈 타일(그림 `icon-cafe`), 검색 묶음, 챗봇 카탈로그 절, 사진 없는 행의 그림 `kind-cafe`. **쇼핑**: TourAPI 유형 38은 `kind: shopping`(목록 `/shopping/`, 홈 타일, 그림 `kind-shopping`). `icon-cafe`·`kind-shopping` 파생본은 운영자가 받은 3D 그림(`incoming/icons/`)에서 `tools/icon_media.py`로 만들었다. 수집은 장소마다 `tourapi.lclsSystm1·2·3`(과 cat1·2·3)을 남기고, 다시 돌 때마다 종류가 그 분류를 따른다(`tools/tourapi_bulk.py` `reclassify`, `locks`에 kind가 있으면 그대로). 화면의 사실은 데이터에서, 개수는 계산한다.
- **엔진 재동기화(2026-10-19)**: 이식 기준(군산 `85d7151`, 10-14) 뒤 군산각 엔진 변경을 도시 중립 형태로 들여왔다 — AI 코스 만들기(`/plan/`, `api/plan.js`, `chatbot/planner.js`·`plan_*.js`), 검색 개선(질문 낱말·관련 가이드·코스 만들기 연결), 목록 필터 칩 개수와 0건에서 돌아가는 길, 장소 관계(`pipeline/relations.py`)·통합권(`tickets.py`·`fee_table.py`)·예약하기(`booking.py`)·시설 공지(`notices.py`), 챗봇 개선(답 언어, 코스 만들기로 넘기기 planQuery, fee_total·check_plan, 긴급 연락처), 홈·핵심 정보, 운영사 정보 바닥글, 9개 언어 엔진, 검증기. 들여온 기능에 딸려 온 도시 값은 `site.json` `city` 블록으로 옮겼다(아래 키, `pipeline/city.py` 설명): `plan`(코스 만들기 출발·도착 hubs, 섬 권역), `course_move`('차 없이 다니기' 가이드·섬 노선·시간표 가이드), `geo_bounds`·`geo_default_points`(좌표 검증), `official_web`(본문에 적힌 공식 사이트), `resident_label`(요금표의 '○○시민', 기본 지역 이름+시민), `brand_em`, `intl.<code>.course_sources`. 예약 서비스 이름 가운데 도시 것은 `booking.json` `services.<key>.names`. 인천 값은 아직 비어 있고 그 블록은 빠진다(코스 만들기는 출발·도착 선택 없이, 섬 취향은 이름에 '섬'이 든 권역으로). 옮기지 않은 것: 군산 그림·마스코트·브랜드 파일, 군산 전용 도구(군산의 `brand_kit.py` — 인천각은 새로 쓴 `tools/brand_kit.py`(로고 항목) — `museum_notices.py`·`official_coords.py`), 군산 실데이터 시험(`tests/excluded_gunsan_tests.txt`).

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
   - `site.json` `source`(인천투어)는 빌드한 레코드가 실제로 그 이름이나 주소를 출처로 달 때만 바닥글·/about/·llms.txt·사이트 도우미에 '원문 출처'로 나온다(`pipeline/build.py` `source_cited`). TourAPI로만 모은 동안은 '한국관광공사 TourAPI'만 출처로 적고, 인천투어는 `official_links`의 공식 안내 링크로만 둔다.
   - 원문은 링크로만 건다. 설명은 우리 문장으로 쓴다(원문과 15자 이상 연속 일치 금지 — TourAPI overview도 같다. `tools/content_check.py`와 빌드 검증이 잡는다).
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
    - 키: `ANTHROPIC_API_KEY` 환경 변수에만 둔다(Vercel Settings → Environment Variables, 넣은 뒤 재배포). 함수는 그 변수만 읽는다(`chatbot/server.js` `apiKey`·`makeClient`).
    - 키가 없으면 `GET /api/chat/`과 질문(POST) 모두 503 `not_configured`로 답하고, 화면(`templates/assets/chat.js`)은 질문 칸 대신 'AI 도우미 준비 중'과 사이트 검색을 보인다. 키를 넣으면 다른 변경 없이 답한다(`GET`이 200 `{"ready":true}`). 로컬 시험: `npm run chat:dev`(README '사이트 도우미').
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
- 군산 사이트의 일러스트·사진·마스코트는 군산을 그렸거나 군산 전용이라 쓰지 않는다. 옮긴 그림은 도시와 무관한 3D 아이콘(`templates/assets/icons/`)·브랜드(운영사 로고)·글꼴뿐이고, 같은 ID의 아이콘은 인천 납품(2026-10-19)으로 바뀌었다 — 군산에서 온 것은 납품에 없는 fact-*·guide·info-center·icon-abroad·plan-*·pref-photo·cond-*만 남았다.
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
- **인천 권역**(운영자 결정 2026-10-19, 2절): 개항장·월미 · 영종·용유 · 송도·연수 · 강화 · 옹진 섬 · 도심·소래 — 구·군 하나에 권역 하나.
- **모션**(GSAP·Lenis): 첫 화면 요소는 처음부터 보이게 한다. reduced-motion이거나 JS가 없으면 최종 상태로 보여 준다. Lenis는 데스크톱에만.
- **글꼴**: Pretendard를 unicode-range 분할로 자체 호스팅한다(`tools/font_subset.py`).
- **성능 목표**(`tools/perf_check.py`, 느린 4G·CPU 4배): LCP ≤ 2.5초, CLS ≤ 0.1, 첫 방문 글꼴 ≤ 300KB.
- **접근성**: 대비 4.5:1, 터치 영역 44px, 보이는 포커스, 이미지 alt.

## 6. 사람이 정할 것 — 결정하지 말고 선택지와 권장안으로 보고
- **도메인**(`site_url`): 운영자 결정(2026-10-19) https://incheon.webforai.kr. 공개 뒤에는 바꾸지 않는다. production 검증은 `ga4_id`(또는 운영자 사유를 적은 `launch_exceptions.ga4_id`)와 `operator.contact`가 비어 있어도 막는다 — 공개 빌드에는 세 값이 모두 필요하다.
- **사이트 이름**: 운영자 결정(2026-10-19) 인천각 / Incheongak(2절). 운영 표기(에이아이오투오)는 확인한다.
- **GA4·GTM**(도시별 별도 속성; `ga4_id`가 비어 있으면 production 검증이 막는다 — GA4를 공개 뒤에 달기로 정하면 `site.json` `launch_exceptions.ga4_id`에 사유), **검색엔진 인증 토큰**(구글·빙·네이버), IndexNow 키(공개 직전).
- **공개**: 공개 범위·시점, 검수(검수 시트), 운영자 공개 승인.
- **정정 요청 연락처**(`operator.contact`, 비어 있으면 production 검증이 막는다), 편집 책임자 표기.
- **페이지 주소 형식**: 한글 슬러그 / 영문 슬러그 — 공개 전에 정한다.
- **범위**: 구·군 11곳 전체 / 권역부터(`tools/tourapi_bulk.py --districts`).
- **구·군 이름**: 2026-07-01 「인천광역시 제물포구ㆍ영종구 및 검단구 설치 등에 관한 법률」 시행(국가법령정보센터 확인)으로 중구·동구가 폐지되고 제물포구·영종구·검단구가 생겼다. TourAPI ldongCode2가 서해구를 포함한 11곳을 돌려준다(2026-10-19). 옛 중구 주소를 나누는 영종구 법정동 8개(권역 규칙)는 위키백과에서 옮겼다 — 행정표준코드로 확인.
- **거리 기준 장소**(`city.distance_anchors`: 인천국제공항·차이나타운·송도센트럴파크·월미도 제안), **홈 이야기·첫 화면 사진**(`city.home`), **시 지정 음식점 목록**(`city.designations`, 조사 전).
- **출처 이용 조건**: 인천투어·인천관광공사 자료의 이용 조건, 추가 출처 수집 범위, TourAPI overview 게재 여부.
- **카카오 지도 JavaScript 키**: 키는 받았다(2026-10-19, 새 카카오 앱 '인천각' → `site.json` `kakao_js_key`). 남은 일: 카카오 개발자 콘솔(앱 → 플랫폼 → Web 사이트 도메인)에 https://incheon.webforai.kr 등록 — 2026-10-19 현재 미등록이라 SDK가 401 'domain mismatched'로 답하고 지도 상자는 글과 '지도를 불러오지 못했습니다' 줄만 남는다. 로컬·Vercel 미리보기 주소에서 지도를 보려면 그 주소도 시험할 때만 더한다.
- `publish_rules`·`crawler_policy`: 군산 값을 기본으로 옮겼다. 인천용으로 확인한다.
- 영어·다국어판을 할지(권장: 한국어만 먼저). 마스코트·일러스트는 운영자가 납품했다(2026-10-19, 2절). 글자처럼 보이는 무늬가 있는 그림(evkind-heritage 깃발의 금색 문양, mascot-404의 물음표)을 다시 그릴지.
- **코스 만들기 출발·도착 장소**(`city.plan.hubs`: 역·터미널·공항 이름 — 비어 있으면 선택이 없다), **섬 권역**(`city.plan.island_regions`), **좌표 범위**(`city.geo_bounds`, 비어 있으면 범위 검사 없음), **긴급 연락처 절**(`site.json` `emergency`: 군산은 한국관광공사 VisitKorea 119·112·1330 — 인천판은 운영자 확인 뒤), **운영사 공식 정보**(`operator.business_no` 등이 있으면 바닥글·/about/#company에 나온다).
- 저장소 공개 여부와 원본 데이터(`data/raw`) 위치.

## 7. 명령어
```bash
python -m pip install -r requirements.txt
npm ci                                   # 챗봇 함수의 SDK(@anthropic-ai/sdk, 고정 버전)
python -m pytest                         # 파이썬 시험(Node가 있으면 챗봇 시험도 함께)
npm test                                 # 챗봇 서버 시험만(node --test)
npm run chat:dev -- --dir dist-preview   # 챗봇 로컬 시험(빌드 폴더 + /api/chat/, 키는 환경 변수 ANTHROPIC_API_KEY)
npm run preview                          # 시나리오 QA: 미리보기 빌드 + /api/chat/·/api/plan/(api/*.js 그대로, 키는 환경 변수 또는 .env의 그 한 줄) — http://127.0.0.1:8788 (tools/serve_preview.mjs, README)
python tools/collect.py --data data/incheon                           # 키 확인 → 진단(지역 코드) → 수집 → 다음 명령. 멈추면(종료 3) 같은 명령 다시
python tools/collect.py --data data/incheon --lists-only              # 호출 없이 캐시의 목록으로 아직 없는 장소를 draft로(상세 대기 — 위 명령이 날마다 채움)
python tools/tourapi_doctor.py --data data/incheon                   # 연결·지역 코드 진단만
python tools/tourapi_bulk.py --data data/incheon --details --add-new --events --max-calls 900   # 수집만(collect.py가 부르는 것)
python tools/image_sizes.py --data data/incheon                      # 사진 크기·작은 크기 파일(collect.py가 끝에 부르는 것) → image_sizes.json
python -m pipeline.build --data data/incheon --out dist-preview --mode preview
python -m pipeline.validate --data data/incheon --out dist-preview --mode preview
python tools/content_check.py --data data/incheon                     # 우리가 쓴 요약·FAQ 검사(원문 베끼기·숫자·출처·표현)
python tools/build_review.py --data data/incheon --out dist-review --report-dir reports   # 공개 선별 미리보기(승인 전)
python tools/build_public.py --data data/incheon --out public          # 공개 빌드 + 검증(production)
python -m pipeline.build --data data/sample --out dist-sample --mode sample && python -m pipeline.validate --data data/sample --out dist-sample --mode sample
python tools/quality_report.py --data data/incheon --out public
python tools/perf_check.py --out public                               # Playwright 필요
python tools/brand_kit.py --data data/incheon --out templates/assets/brand --png   # 로고·심볼·아이콘 다시 그리기(shapely·fonttools·Playwright, 이 도구만)
```
- 도구의 `--data` 기본값은 `data/incheon`이다. 새 도시는 `data/<도시>/site.json`을 만들고 `--data`로 넘긴다(엔진은 바꾸지 않는다).
- `main`에 push하면 Vercel이 `public/`을 배포한다. 공개 전환은 사람이 정한다.
- **미리보기 배포(운영자 요청 2026-10-19)**: 공개 전까지 `public/`은 미리보기 빌드다 — draft 전부, 모든 페이지 noindex, robots.txt 전체 차단, `vercel.json`의 X-Robots-Tag `noindex, nofollow`(모든 경로). 갱신은 빌드로만: `python -m pipeline.build --data data/incheon --out public --mode preview && python -m pipeline.validate --data data/incheon --out public --mode preview`. 정식 공개 때 `tools/build_public.py`로 바꾸고 X-Robots-Tag를 공개 호스트에서 푸는 것은 사람이 정한다(`tools/launch_check.py`가 남은 헤더를 알린다).

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
| `tools/` | TourAPI 진단·수집, 공개 빌드, 검수 시트·반영, 품질·성능·공개 전 점검, 브랜드 키트(`brand_kit.py`) |
| `templates/assets/brand/` | 인천각 심볼·로고·앱 아이콘 SVG와 icon-*.png·favicon.ico(`tools/brand_kit.py`가 만든다), 운영사 로고 |
| `tools/serve_preview.mjs` | 시나리오 QA용 로컬 미리보기: 미리보기 빌드를 127.0.0.1:8788에 띄우고 `/api/chat/`·`/api/plan/`을 `api/*.js`로 답한다(`npm run preview`) |
| `chatbot/`, `api/chat.js` | 사이트 도우미(Vercel 함수). 사이트 주소·이름·도시 이름은 빌드가 쓴 `public/chat/site.json`에서 읽는다(`chatbot/site.js`) |
| `api/plan.js`, `chatbot/planner.js`·`plan_*.js`, `templates/plan.html.j2`·`assets/plan.js` | AI 코스 만들기(`/plan/`, 같은 키 `ANTHROPIC_API_KEY`, vercel.json `api/plan.js`). 출발·도착 이름은 `public/chat/site.json` `hubs`(= `city.plan.hubs`) |
| `pipeline/relations.py`·`tickets.py`·`fee_table.py`·`booking.py`·`notices.py` | 장소 관계(part_of)·통합권·요금표 읽기·예약하기·시설 공지(각각 `data/<도시>/` 파일이 있을 때만) |
| `tests/` | pytest + `tests/js/`(node --test). 고정 데이터 `data/sample/`·`tests/fixtures/incheon_tiny/`. 옮기지 않은 군산 전용 시험: `tests/excluded_gunsan_tests.txt` |
| `docs/02_page_standard.md` | 데이터 표준 |
