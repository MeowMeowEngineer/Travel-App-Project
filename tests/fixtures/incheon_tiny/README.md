# tests/fixtures/incheon_tiny

테스트 전용 가짜 데이터(tests/test_city.py): 인천 site.json으로 엔진이 도는지 본다. 이름·주소·좌표·값은 모두 지어낸 것이며 공개하지 않는다. 실제 인천 데이터는 data/incheon/에 TourAPI 수집으로만 생긴다.

- places.json: 장소 7곳(관광지 3·음식점 1·숙소 1·카페·디저트 1·쇼핑 1) — 권역 규칙의 일곱 경우(중구+영종 법정동, 연수구, 강화군, 법정동 없는 중구, 주소에 구·군 없이 TourAPI 구·군만 있는 곳, 미추홀구, 옹진군)와 카페·디저트(TourAPI 분류 FD05…)·쇼핑(유형 38) 목록
- guides·courses·themes·events: 비어 있음
