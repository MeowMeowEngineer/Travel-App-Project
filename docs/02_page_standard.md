# 02. 페이지·데이터 표준 (AEO 메타데이터 표준 — 장소형 초안)

> 10/7 회의 확정 과제 "AEO 메타데이터 표준 정립"의 장소형 초안이다. 숙박형(스테이,머뭄 JSON-LD 5블록)과 함께 Web4AI 공통 표준으로 합친다.
> 이 문서와 `pipeline/schema.py`는 항상 같은 내용을 유지한다.

## 1. 원칙 6가지

| # | 원칙 | 구현 |
|---|---|---|
| 1 | **원문과 우리가 쓴 내용을 분리한다** | 원문 블록은 글자 그대로(해시 검증), 요약·FAQ·가이드는 별도 블록 |
| 2 | **사실은 출처 데이터에서만 가져온다** | 운영시간·요금·주차·주소는 TourAPI/원문 값만. 없으면 "확인 필요"로 표시, 추정 금지 |
| 3 | **모든 링크에는 역할이 있다** | 근거(공식 안내) · 행동(지도·길찾기) · 탐색(코스·주변) · 미디어(공식 영상·보도). 링크 수를 늘리는 것이 목적이 아님 |
| 4 | **구조화 데이터는 본문과 일치한다** | 같은 데이터로 본문과 JSON-LD를 동시에 생성. QA가 불일치 검사 |
| 5 | **공개 = 검수 완료** | `status=published`와 `reviewed_at`이 있어야 공개 빌드에 포함 |
| 6 | **메타데이터는 구현 항목이지 인용 보증이 아니다** | 구글은 AI 기능 노출에 별도 AI 파일·특별 스키마가 필요 없다고 안내한다. llms.txt·JSON-LD는 "넣었으니 인용된다"로 설명·판매하지 않는다 |

## 2. 화면 3종 (+확장 2종)

| 화면 | 역할 | 핵심 연결 |
|---|---|---|
| **지역 허브** `/` | 방문 목적으로 진입(목적별 가이드 → 테마 → 대표 여행지 → 코스) | 가이드·테마·숙소/음식점 목록 |
| **장소·업체 상세** `/places/{slug}/` | 한 장소의 방문 여부를 판단하게 함 | 지도·공식 안내·관련 코스·주변 장소 |
| **목적별 가이드** `/guides/{slug}/` | 여러 장소를 묶어 구체적 질문에 답함 | 근거가 된 상세 페이지·공식 자료 |
| 코스 `/courses/{slug}/` | 원문 코스의 경유지를 순서대로 연결 | 경유지 상세·지도 |
| 행사 `/events/` | 일정·장소·출처 | 주최 측 안내 |

## 3. 장소 상세 페이지 — 9블록

표시 순서는 "어떤 곳 → 방문 전 확인 → 행동 → 함께 갈 곳 → 근거" 흐름을 따른다.

| 블록 | data-block | 표시 순서 | 내용 | 데이터 | 없을 때 |
|---|---|---|---|---|---|
| 1 요약 | `summary` | 1 | 2~3문장. 첫 문장에 "무엇·어디", 다음에 원문·TourAPI 근거의 방문 이유 | `summary` | full·basic 필수 |
| 2 방문 전 확인 | `facts` | 2 | 주소·이용시간·쉬는 날·요금·주차·문의 + 유모차·반려동물·체험연령 + **확인 필요 항목** + 정보 확인일 | `facts`, `facts_source` | "확인 필요: …" 자동 표시 |
| 3 지도·길찾기 | `directions` | 3 | 네이버·카카오·구글 + 길찾기(카카오·구글·티맵). **정확 링크(좌표·Place ID)와 검색 링크를 라벨로 구분** | `geo`, `map_ids` | 검색 링크 + "(검색)" |
| 6 함께 가기 | `nearby` | 4 | 이곳을 지나는 코스, 포함된 가이드, 주변 볼거리, **주변 숙소·음식점**(직선거리·산출 기준 표기) | 코스/가이드 역참조, `nearby` | full 필수 |
| 7 영상·소식 | `media` | 5 | 공식 채널 영상 임베드, 보도자료·기사(제목·매체·날짜·링크만) | `media` | 권장 — 공식 영상·보도자료를 확인한 경우에만 표시 |
| 8 자주 묻는 질문 | `faq` | 6 | 여행자 질문 3~5개. 답은 근거 데이터 안에서만 | `faq` | full 필수 |
| 5 원문 | `original` | 7 | 허용 유형이면 전문(수정 없음), 아니면 원문 링크 | `original` | 링크 또는 "원문 없음" 안내 |
| 4 공식 정보·출처 | `sources` | 8 | 원문·구석구석·홈페이지 링크, **원문 수집일 / 정보 확인일 / 검수일** | `official`, 날짜 필드 | 필수 |
| 9 구조화 데이터 | (head) | — | 본문과 같은 값의 JSON-LD | 전체 | 필수 |

- **full 등급**: 9블록(영상·소식은 권장). 대표 장소와 질문셋 관련 장소.
- **basic 등급**: 1·2·3·5·4·9. 나머지 장소. 원문만 옮긴 얇은 페이지를 대량으로 공개하지 않는다(구글 스팸 정책의 scraped content·scaled content abuse 소지). basic도 2·3블록의 실용 정보가 있어야 공개한다.

## 4. 데이터 모델

### 4-1. 장소·업체 `places.json`

| 필드 | 설명 | 예 |
|---|---|---|
| `id` | 불변 고유 ID | `incheon-0001`, TourAPI에서 새로 들어온 곳은 `tourapi-<contentid>` |
| `slug` | URL. 임포트 때 한 번 정하고 공개 후 바꾸지 않음 | `경암동-철길마을` |
| `name`, `kind` | 명칭, 유형 `attraction`/`stay`/`food`/`cafe`(카페·디저트: TourAPI 신분류 FD05…·FD030100, 신분류가 없으면 cat3 A05020900)/`shopping`(TourAPI 유형 38) — `pipeline/tourapi.kind_of`, 수집이 분류를 따라 맞춘다(`locks`에 `kind`가 있으면 그대로) | |
| `tourapi` | `{contentid, contenttypeid, title, match_basis, modifiedtime, lclsSystm1, lclsSystm2, lclsSystm3, cat1, cat2, cat3, overview, details_pending?}` — 분류 코드는 TourAPI가 준 그대로(2026-10-19 전 수집분은 `lcls` = lclsSystm3). overview는 사실 확인용, 화면에 내지 않음. `details_pending: true`는 지역 목록 항목만으로 더한 곳(`tools/collect.py --lists-only`) — 다음 수집의 상세 단계가 채우고 지운다 | `{"lclsSystm3": "FD050100"}` |
| `category`, `themes` | 원본 분류, 테마 slug 목록 | `["alleys-culture"]` |
| `status` | `draft`(작성·검수 전) → `reviewed`(검수 완료·공개 대기) → `published` | |
| `tier` | `full`/`basic` | |
| `summary` | 블록1 (우리 작성) | |
| `facts` | 블록2 값(출처 값 그대로). 키: address, usetime, usetime_restdate(영업시간·정기휴일이 한 칸인 출처), restdate, usefee, parking, parking_seats(주차·좌석이 한 칸인 출처), parkingfee, spendtime, checkin, checkout, menu, infocenter, homepage, babycarriage, pet, expagerange, useseason, accessible_parking, wheelchair, accessible_toilet, accessible_route | |
| `facts_source` | `{provider, contentid, checked_at}` — **정보 확인일** | |
| `fact_sources` | 항목별 출처 `{키: {provider, checked_at, url?, contentid?, confirmed_by?, raw?, note?, via?}}` — `via`는 값을 가져온 TourAPI 기능이 상세가 아닐 때(목록 `areaBasedList2`). 표기를 고친 값(도 이름 보정, 붙어 있던 전화번호 분리)은 원래 값을 `raw`, 사유를 `note`에 남긴다 | `{"address": {"raw": "○○시 ○○로 111-5(○○동)", …}}` |
| `fact_alternatives` | 다른 출처의 값 `{키: [{value, provider, checked_at, relation?}]}`. `relation: "also"`는 보완 값(둘째 메뉴·안내소 전화), 없으면 충돌 값 | |
| `designations[]` | 공식 지정 목록(시가 운영하는 목록 — site.json `city.designations` — 과 모범음식점·백년가게·향토음식점·착한가격업소·안심식당) `{type, label, year, source_name, url, checked_at, match: {row_ref, confidence, basis}, confirmed_by?}`. 매칭 신뢰도 high·medium이고 `needs_check`가 없을 때만 화면에 나간다(`schema.designations`). 장소 첫 화면 칩(목록 링크)·방문 전 확인의 '지정' 줄(목록 링크·확인일)·목록 칩 하나·검색·llms.txt·JSON-LD `award`. 색인 기준에는 넣지 않는다 | `{"type": "mobeom", "label": "모범음식점(○○구 지정)", …}` |
| `geo` | `{lat, lng, source, checked_at?}` (TourAPI 목록에서 온 좌표는 목록을 받은 날을 `checked_at`에) | |
| `map_ids` | `{naver_place_id, google_place_id}` — 있으면 정확 링크 | |
| `official` | `{source_url, visitkorea_url, homepage}` | |
| `original` | `{text, source_name, source_url, license, collected_at, sha256, body?}` — **원문 수집일**. 상세 본문이 상호·메뉴명뿐이면 `text`는 비우고 `body: "metadata_only"`(수집 원본은 `data/raw`에 보존) | |
| `images[]` | `{url, alt, credit, license, source, checked_at?}` | |
| `nearby[]`, `nearby_source` | `{name, kind, type_label, distance_m, contentid, internal_slug}` / `{provider, radius_m, distance_basis, checked_at}` | |
| `media` | `{videos:[{youtube_id,title,channel,url}], news:[{title,publisher,date,url}]}` | |
| `faq[]` | `{q, a, source}` | |
| `question_ids` | 관련 측정 질문 | `["N01","N18"]` |
| `reviewed_at`, `reviewer` | **검수일**, 검수자 | |
| `locks` | 자동 보강이 덮어쓰지 않을 필드 | `["facts"]` |
| `fact_conflicts` | 같은 출처 안에서 값이 서로 다른 항목 `{키: 설명}`. 그 키는 facts에 넣지 않고 화면에 사유만 표시 | `{"usetime": "상세 정보표 …와 본문 …이 다름"}` |
| `duplicate_of` | 같은 장소를 다른 게시판에서 다시 수집한 기록이면 대표 기록의 `id`. 빌드에서 제외 | `incheon-0042` |
| `tourapi` | `{contentid, contenttypeid, match_score, overview, modifiedtime}` (overview는 작성 참고용, 화면 미표시) | |

### 4-2. 가이드 `guides.json`
`id, slug, label, title(질문형), status, summary(첫 문장 = 답), body[{heading,text}], items[{place_slug, reason}], sources[{name,url}], faq[], question_ids, checked_at, reviewed_at`

### 4-3. 코스·행사·테마
- `courses.json`: `id, slug, name, duration, status, summary, stops[{place_slug|name, note}], original{…}, question_ids, reviewed_at`
- `events.json`: `id, contentid, status, name, period_text(출처의 기간 문구 그대로), start_date, end_date(출처에 연·월·일이 모두 있을 때만), place_name, address, geo, summary, playtime, fee, sponsor(주최), tel, homepage, also_sources[{name,url,checked_at}], source_name, source_url, checked_at` + 선택: `series`(회차 묶음 키 — 없으면 이름 앞 연도를 떼고 `normalize_name`이 같은 것끼리), `place_slug`(열리는 장소), `question_ids`.
  - 날짜가 있는 기록이 하나라도 있는 묶음은 `/events/{묶음 slug}/` 페이지를 갖고, 가장 최근 회차만 `Event`로 마크업한다. `/events/`는 절대 월 제목(`2026년 10월`)으로 묶은 목록이며 `Event` 노드가 없다.
- `themes.json`: `slug, name, description`

### 4-4. 이용조건 코드
`KOGL-1`(출처표시) · `KOGL-2`(+상업적 이용금지) · `KOGL-3`(+변경금지) · `KOGL-4`(+상업적 이용금지·변경금지) · `NONE`(공공누리 미표시 — 사전 협의 필요) · `UNKNOWN`(확인 전).
기본 게재 허용: `KOGL-1`, `KOGL-3`(`site.json → publish_rules`). 3유형은 변경 금지이므로 원문·사진을 고치거나 자르지 않는다(이미지는 `object-fit: contain`).

## 5. 링크 규칙

1. **정확한 장소 링크 우선**: 구글은 `query_place_id`/`destination_place_id`, 네이버는 `map.naver.com/p/entry/place/{ID}`, 카카오는 좌표 링크. 없으면 검색 링크를 쓰고 라벨에 "(검색)"을 붙인다.
2. **역할 없는 링크 금지**: 무관한 기관·다른 지역 사이트 일괄 링크, 상호 링크 교환("링크해 주면 링크해 주겠다")은 하지 않는다.
3. **공식 사이트를 우리가 링크하는 것 ≠ 공식 기관이 우리를 인정하는 것**. 대외 표현에서 구분한다. 공신력 신호는 '받는 링크'(예: 시 관련 사이트 등재)에서 생긴다.
4. 제3자 콘텐츠(네이버 플레이스·블로그·인스타·리뷰)는 복제하지 않고 링크만.
5. 지도·공식 안내·숙소·음식점 링크에는 `data-track` 속성을 붙여 GA4 이벤트로 측정한다(6절).

## 6. 크롤러·색인

- 모든 본문은 정적 HTML에 있다(클라이언트 렌더링 금지).
- `robots.txt`: 검색·답변 엔진과 사용자 요청 크롤러는 허용(OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User, Googlebot, Bingbot, Yeti, Daumoa). **학습 전용 크롤러(GPTBot, ClaudeBot, CCBot)는 기본 차단** — 원문 권리가 원 출처에 있기 때문. OpenAI 안내상 GPTBot 차단은 ChatGPT 검색 노출에 영향을 주지 않는다. 정책 변경은 `site.json → crawler_policy`.
- `noindex`·전체 차단은 미리보기·샘플 빌드에만. 공개 빌드에 남아 있으면 QA 오류.
- `sitemap.xml`(lastmod = 그 페이지가 보여 주는 데이터 날짜: 장소 max(검수일, 정보 확인일) · 가이드 max(검수일, 정보 확인일) · 코스 max(검수일, 원문 수집일) · 행사 max(일정 확인일) · 목록·테마·지도·홈은 링크한 페이지 날짜의 최댓값을 화면에 함께 표시. 빌드 날짜는 쓰지 않고, 날짜를 모르면 `<lastmod>`를 생략), `canonical`, `llms.txt`·`llms-full.txt`(비공식 제안 규격 — 비용이 낮아 포함하되 효과를 주장하지 않음).

## 7. 구조화 데이터 매핑

| 화면 | 타입 |
|---|---|
| 관광지 / 숙소 / 음식점 | 출처 분류로 가장 구체적인 타입(`schema.schema_type`: `["Museum"|"Park"|"Mountain"|"LandmarksOrHistoricalBuildings"|"GolfCourse", "TouristAttraction"]`, 숙소 `Hotel`/`Motel`/`LodgingBusiness`, 음식점 `Restaurant`+`servesCuisine`은 한식·중식·일식·분식일 때만, 음식점·숙소의 `award`는 화면에 나간 공식 지정 이름만) + `WebPage`(`isBasedOn` = 원문 URL, `dateModified` = 검수일, `lastReviewed` = 정보 확인일) + `BreadcrumbList` + `FAQPage` |
| 가이드 | `Article`(`about` = 근거 장소 `@id`, `isBasedOn` = 출처, `dateModified`) + `ItemList` |
| 코스 | `TouristTrip`(`itinerary` = 경유지 `ItemList`, 연결된 경유지는 장소 `@id`, `isBasedOn` = 원문 코스 URL) |
| 행사 | 회차 묶음 페이지의 최신 회차 하나만 `Event`(시작·종료일, 장소·주소, 주최는 화면에 있을 때, `isAccessibleForFree`는 요금이 정확히 "무료"일 때, `eventStatus`·이미지 없음) |
| 목록·테마 | `WebPage` + 카드 순서대로 절대 URL `ItemList` |
| 홈 | `WebSite` + `Organization`(url·sameAs는 `site.operator`에 사람이 채운 값만) + 도시 노드 `["City","TouristDestination"]`(`@id` …/#city, `includesAttraction`). 장소의 `containedInPlace`가 이 노드를 가리킨다 |

**구조화 데이터 = 화면**: 모든 문자열 값은 화면 본문이나 `<title>`에 보여야 하고(앞 25자 비교, 날짜는 본문 또는 `<time datetime>`, 전화는 국내 표기로 비교), `validate.jsonld_visibility`가 모든 페이지에서 오류로 막는다. 참/거짓 값은 화면의 해당 칸(`<dt>`/`<dd>`)과 맞아야 한다: `isAccessibleForFree`는 요금 칸 값이 정확히 "무료"(주차요금 칸은 해당 없음), `amenityFeature`·`petsAllowed`는 주차·유모차 대여·반려동물 동반 칸 값이 같은 참/거짓, 영업시간의 opens·closes는 화면에 그 시각이 있어야 한다. 타입이 있는 값은 출처 문자열이 정확히 맞을 때만: `isAccessibleForFree`(요금이 "무료", 다른 출처 충돌 없음), `openingHoursSpecification`(`HH:MM~HH:MM` + `연중무휴`/`매주 X요일`, 충돌 없음, 시각은 00:00~23:59 — `00:00~24:00` 같은 값과 그 밖은 `additionalProperty`), `amenityFeature`·`petsAllowed`(가능/불가·없음 같은 예/아니요 값), `telephone`(`+82-…`, 번호가 여럿이면 배열). 주소는 도 이름만 `전북특별자치도`로 바꿔 보여 주고(`textutil.display_address`) `PostalAddress`를 도·시·나머지로 나눈다. 여러 장소가 함께 쓰는 홈페이지(시 관광 포털 등)는 `sameAs`에 넣지 않는다. 평점·리뷰 수는 넣지 않는다.

## 8. 메타 태그

- title: `{지역 이름이 들어간 이름} {있는 정보 라벨 최대 3개} | {site_name}` — 예 `인천 ○○박물관 이용시간·쉬는 날·요금 | 인천각`. 라벨은 화면에 있는 핵심 정보(이용시간·영업시간·쉬는 날·요금·주차·체크인·메뉴)에서만, 없으면 `방문 정보·지도`. 코스: `{지역} {이름}({N코스}) — 경유지 n곳 | {site_name}`
- description: 요약 첫 문장(40자 미만이면 다음 문장까지) + 다른 출처와 충돌 없는 짧은(30자 이하) 사실 최대 2개, 160자 이하. 상투 꼬리 문장 없음
- og:image: 장소는 공공누리 1유형 사진 우선(3유형만 있으면 첫 사진 — 미리보기 자르기 허용 여부는 사람 결정), 목록·테마·가이드는 사진 있는 첫 카드, 코스는 표지, 홈은 첫 대표 사진
- `canonical`, `og:*`(locale ko_KR), `geo.position`·`ICBM`(좌표 있을 때), `html lang="ko"`

## 9. 날짜 3종 (화면·데이터 모두)

| 날짜 | 의미 | 필드 |
|---|---|---|
| 원문 수집일 | 출처의 글을 가져온 날 | `original.collected_at` |
| 정보 확인일 | 운영시간·요금 등 실용 정보를 출처에서 다시 확인한 날 | `facts_source.checked_at` |
| 검수일 | 사람이 페이지를 검토한 날 | `reviewed_at` |

원문을 오늘 가져와도 그 안의 요금·운영 정보는 오래됐을 수 있으므로 셋을 섞지 않는다.
`fact_sources[키].checked_at`(정보 확인일)은 사람이나 도구가 출처와 **실제로 다시 대조했을 때만** 올린다. 재빌드·재배포만으로는 바꾸지 않는다(sitemap lastmod와 `dateModified`가 이 날짜를 따른다). TourAPI 값은 응답을 받은 날짜를 쓴다(캐시 응답이면 캐시 파일 날짜) — 주간 갱신(`tools/refresh.py`)을 캐시로 다시 돌려도 확인일이 오르지 않고, `--fresh`로 새로 받은 값만 그날로 바뀐다.

## 10. 고지 항목 (출처·이용 안내 페이지 + 모든 페이지 하단)
운영 주체 · 정보 출처 · **공식 제휴 여부(없음)** · 원문 이용조건 처리 원칙 · 정정 요청 연락처 · 방문 통계(GA4) 수집 사실 · AI/검색 크롤러 정책.

## 11. GA4 이벤트

| 이벤트 | 언제 |
|---|---|
| `map_click` / `route_click` | 지도 보기 / 길찾기 링크 |
| `official_click` | 원문·공식 안내·홈페이지 |
| `stay_click` / `food_click` | 숙소·음식점 링크 |
| `nearby_click`, `course_click`, `guide_click` | 내부 탐색 |
| `video_click`, `news_click` | 미디어 |
| `parking_click` | 근처 공영주차장 이름(카카오맵 위치) |
| `chat_open` / `chat_send` / `chat_link_click` | 사이트 안내 챗봇 열기 / 질문 보내기(내용은 보내지 않음) / 답 속 링크 |

매개변수: `place_id`, `link_provider`, `page_kind`, `link_url` → GA4 관리에서 맞춤 측정기준으로 등록해야 보고서에 보인다. 외부 링크 클릭은 예약 완료·매출이 아니다.
