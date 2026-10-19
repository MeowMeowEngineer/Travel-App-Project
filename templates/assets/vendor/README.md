# 자체 호스팅 라이브러리

| 폴더 | 버전 | 라이선스 | 받은 곳 |
|---|---|---|---|
| `gsap/` | GSAP 3.13.0 (`gsap.min.js`, `ScrollTrigger.min.js`, `SplitText.min.js`) — 스크롤·텍스트 연출 | GSAP Standard "no charge" license (`gsap/LICENSE.md`) | npm `gsap@3.13.0` |
| `lenis/` | Lenis 1.3.11 (`lenis.min.js`, `lenis.css`) — 부드러운 스크롤 | MIT (`lenis/LICENSE`) | npm `lenis@1.3.11` |
| `pretendard/` | Pretendard 1.3.9 — 400·700 unicode-range 분할(`Pretendard-Regular.N.woff2`, `Pretendard-Bold.N.woff2`), 200 숫자 전용 `LightNumerals-ExtraLight.woff2` | SIL OFL 1.1 (`pretendard/LICENSE.txt`) | npm `pretendard@1.3.9` |

## 불러오는 방식(첫 화면을 막지 않는다)
- **글꼴**: `pretendard.css`의 `@font-face`마다 `unicode-range`가 있어, 브라우저는 그 페이지에 실제로 나오는 글자가 든 조각만 받는다.
  - 0번 조각(약 54KB)은 라틴·문장부호와 사이트 글에 가장 흔한 한글 450자, 다음은 사이트에 나오는 나머지 한글(빈도순 90자씩), 그 뒤는 사이트에 없는 글자(한글 300자·기타 400자씩, 코드 순서)다. 굵기마다 50조각, 합계 약 1MB지만 한 페이지가 받는 양은 측정한 페이지 기준 약 110~190KB다(압축 없는 로컬 서버 기준).
  - 400·700은 원본의 **모든 글자**를 나눠 담았다(빠진 글자 없음, OpenType 기능·이름·저작권 정보 유지). 그래서 이름 Pretendard를 그대로 쓴다.
  - 200은 큰 숫자용으로 숫자·쉼표·마침표·%·km 등만 남긴 부분 글꼴이다. OFL의 예약 글꼴 이름 규정에 따라 `Light Numerals`로 이름을 바꿨다(저작권·라이선스 표기 유지). CSS는 `var(--font-num)`(= 'Light Numerals', Pretendard …)으로 쓰며, 같은 줄의 한글은 Pretendard 400으로 그려진다(시스템 글꼴로 빠지지 않음).
  - 600(SemiBold)은 쓰지 않는다. 예전 600 자리는 700으로 바꿨다. 800은 700 글꼴로 표시된다.
  - 대체 글꼴 보정: 첫 방문에는 글이 시스템 글꼴로 먼저 그려졌다가 Pretendard로 바뀐다(swap). 시스템 한글은 폭이 넓어(Pretendard 0.864em · Noto Sans CJK KR 0.92em · WenQuanYi Zen Hei 1em) 바뀔 때 줄 수가 줄며 아래 내용이 밀린다(CLS). 그래서 `pretendard.css` 끝의 'Pretendard Fallback Noto'·'Pretendard Fallback WQY'가 해당 시스템 글꼴을 local()로 불러 size-adjust·ascent/descent-override로 한글 폭과 줄 높이를 Pretendard에 맞춘다(한글 범위만). Apple SD Gothic Neo·Malgun Gothic은 폭을 재지 못해 아직 넣지 않았다 — macOS·Windows에서 한글 한 자 폭을 재서 `tools/font_subset.py`의 `FALLBACKS`에 더한다.
  - 라틴·숫자·문장부호도 같은 방식으로 맞춘다(3차 리디자인): 사이트 글에서 한글 밖 글자의 절반이 띄어쓰기라, 시스템 산세리프(이 환경의 Inter)와 Pretendard의 폭 차이만으로도 swap 때 줄이 바뀌어 각주 번호 같은 줄 끝 요소가 멀리 움직였다(홈 시안 CLS 0.15). 'Pretendard Fallback Inter'(라틴 범위만)가 그 폭을 맞춘 뒤 0이 됐다. Roboto(안드로이드)·Arial(윈도·맥)은 재서 `LATIN_FALLBACKS`에 더한다. 조각은 그대로 두고 대체 글꼴 규칙만 다시 쓰기: `python tools/font_subset.py --fallbacks-only --out templates/assets/vendor/pretendard`.
  - 다시 만들기: `tools/font_subset.py` 머리말 참고(`npm pack pretendard@1.3.9` → 공개 빌드·미리보기 빌드를 글자 빈도 자료로 넣어 실행). 글이 크게 바뀌면 다시 만든다 — 사이트에 없던 글자는 300자짜리 일반 조각(약 20KB)으로 받게 되어 첫 방문 글꼴이 커진다(2026-10-08 다시 만들기 전 /food/ 709KB → 뒤 190KB). 안 해도 글자가 빠지지는 않는다.
- **스크립트 순서**: HTML에 있는 스크립트는 `assets/site.js`(defer) 하나다. site.js가 페이지 로드(또는 4초) 뒤에 `assets/motion.js`(동작 줄이기면 붙이지 않음)를 붙이고, 지도 상자가 있는 페이지에는 `assets/map.js`, `[data-course]`가 있으면 `assets/course.js`, `[data-search]`가 있으면 `assets/search.js`를 붙인다.
- **GSAP·ScrollTrigger·SplitText·Lenis**: `<head>`에 넣지 않는다. motion.js가 필요한 것만 받는다. 걸 수 있는 속성 전체는 `motion.js` 머리말에 있다.
  - GSAP+ScrollTrigger는 첫 화면 아래에 연출 대상(`data-reveal`·`data-reveal-ph`·`data-split`·`data-parallax`·`data-route-draw`, 홈 이야기·섬 갤러리)이 있을 때만 받는다. 연출은 사진 열림·길 그리기·전환에 쓴다(소유자 결정 2026-10-08). 숫자 세기는 없다(데이터에 없는 숫자가 잠깐 보이므로 뺐다).
  - SplitText는 첫 화면 아래에 `[data-split]` 제목이 있을 때만 받는다(줄 올림, 쓰는 쪽이 고르는 선택 연출). 첫 화면 제목에 붙은 `data-split`은 무시한다.
  - Lenis는 데스크톱(1024px 이상) + 정밀 포인터(`hover: hover` + `pointer: fine`)에서만 받는다. 지도·`[data-lenis-prevent]` 안의 휠은 건드리지 않고, 앵커는 머리말 아래로 이동한 뒤 초점을 옮기며, 키보드 스크롤은 브라우저 기본 동작 그대로다.
  - 동작 줄이기(reduced motion)면 motion.js 자체를 받지 않는다. JS가 없으면 아무것도 받지 않는다. 둘 다 최종 상태 그대로 보인다(`templates/assets/css/65-states.css`).
- **지도(카카오맵, 운영자 결정 2026-10-14)**: 자체 호스팅하지 않는다. 카카오 지도 JavaScript SDK(`dapi.kakao.com/v2/maps/sdk.js?appkey=…&autoload=false`)를 map.js가 지도 상자(`.map[data-map]`, 옛 `.map[data-points]`)가 화면 가까이(400px) 오거나 접힌 지도가 열릴 때, 페이지 로드(`load`) 뒤에만 받는다. 주소는 빌드가 `site.json`의 `kakao_js_key`로 만들어 상자의 `data-kakao-sdk`에 적는다(`pipeline/build.kakao_sdk_url`). 지도 상자가 없는 페이지는 map.js도 SDK도 받지 않는다. 마커·이름표·확대 버튼은 사이트 CSS(`css/30-info.css`)로 꾸민 우리 요소이고, 지도 안 로고는 카카오가 그린다.
  - 이 키는 카카오 개발자 콘솔에 등록한 웹 도메인(지금 `https://gunsan.webforai.kr`)에서만 동작한다. 다른 주소에서는 SDK가 HTTP 401(domain mismatched)을 돌려주고, 상자에는 '지도를 불러오지 못했습니다'가 남는다(목록·글은 그대로).
