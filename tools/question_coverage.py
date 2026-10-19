"""Report fixed-question evidence coverage using stored originals only.

This is a review aid, not generated travel advice or a publication approval.
It never fetches pages, changes questions/data, or treats a place-name match as
proof of hours, transport, indoor access, price or accommodation suitability.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


NAMED = {
    "N01": ("경암동 철길마을",), "N02": ("초원사진관",),
    "N03": ("군산근대역사박물관", "근대역사박물관"),
    "N04": ("신흥동 일본식 가옥", "군산신흥동일본식가옥", "군산신흥동일본식가옥(히로쓰가옥)"),
    "N05": ("동국사",), "N06": ("은파호수공원",), "N07": ("월명공원",),
    "N08": ("말랭이마을",), "N15": ("선유도",),
    "N17": ("군산근대역사박물관", "근대역사박물관"),
    "N18": ("경암동 철길마을",), "P03": ("경암동 철길마을",),
}
UNVERIFIED = {
    "N03": "박물관 관람 시간·휴관일(TourAPI 확인값 필요)",
    "N04": "가옥 내부 관람 가능 여부·출입 조건",
    "N05": "동국사 자체 소개·볼거리 원문",
    "N06": "한 바퀴 보행 소요시간의 직접 근거",
    "N08": "말랭이마을 자체 소개 원문",
    "N14": "철도·버스·도보 환승과 각 경유지 접근 방법",
    "N15": "선유도 차량 진입·주차장 위치의 직접 근거",
    "N16": "서울 출발 기차·버스 노선과 군산 도착 정보",
    "N17": "군산역→근대역사박물관 교통 경로",
    "N18": "경암동 철길마을 일반 방문객 주차 정보",
    "N19": "시티투어 여행 안내·현재 운행 여부·정기 운영조건",
    "N21": "실내 이용을 명시한 장소 원문·우천 이용 조건",
    "N25": "무료임이 확인된 이용요금 필드·출처",
    "N27": "시간여행축제 개최일·연도·공식 행사 데이터",
    "N28": "측정 월에 해당하는 행사 기간·갱신일",
    "N29": "독채 여부와 숙소 자체 정보·업주 확인",
    "N30": "음식점·메뉴 자체 정보(코스 내 상호 언급으로 대체 불가)",
    "P01": "독채 여부·숙소 자체 안내·예약 플랫폼 이외의 확인 경로",
    "P03": "경암동 철길마을 주차 정보의 직접 출처",
}


def _normalized(name):
    # Only identity lookup uses normalization; quoted source text remains unchanged.
    return re.sub(r"\s", "", name)


def _excerpt(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    if end < 0:
        end = len(text)
    # Keep a continuation line when the original is wrapped mid-sentence.
    while end < len(text) and end - start < 1200 and not text[start:end].rstrip().endswith((".", "다", "요")):
        following = text.find("\n", end + 1)
        if following < 0:
            following = len(text)
        if not text[end + 1:following].strip():
            break
        end = following
    return text[start:end]


def source_documents(records: list[dict], source_type: str) -> list[dict]:
    """Represent saved source material without inventing public page slugs."""
    return [{"name": r.get("name", ""), "slug": "", "source_type": source_type,
             "kind": r["candidate_kinds"][0] if len(r.get("candidate_kinds", [])) == 1 else "",
             "source_fields": r.get("source_fields", []),
             "original": {"text": r.get("original_text", ""), "source_url": r.get("source_url", ""),
                          "license": r.get("original_license", "UNKNOWN")}}
            for r in records if r.get("original_text", "").strip()]


def course_candidates(raw_courses: list[dict], imported: list[dict] | None = None) -> list[dict]:
    counters: dict[str, int] = {}
    results = []
    for raw in raw_courses:
        source = raw.get("source_url") or raw.get("original", {}).get("source_url", "")
        page = urlsplit(source).path.rsplit("/", 1)[-1]
        counters[page] = counters.get(page, 0) + 1
        matched = [c for c in imported or [] if c.get("name") == raw.get("name")
                   and (c.get("original", {}).get("source_url") or c.get("source_url")) == source]
        slug = matched[0]["slug"] if len(matched) == 1 else f"gunsan-course-{page}-{counters[page]}"
        results.append({**raw, "slug": slug, "slug_registered": len(matched) == 1, "source_page": page})
    return results


def assess_question(question: dict, places: list[dict], courses: list[dict],
                    samples: list[dict] | None = None, documents: list[dict] | None = None) -> dict:
    ident = question["id"]
    result = {"id": ident, "group": question["group"], "question": question["question"],
              "candidate_slugs": [], "evidence": [], "missing": [], "answer_status": "미확인"}
    sources = places + (documents or [])
    selected = [p for p in sources if any(_normalized(p.get("name", "")) == _normalized(name)
                                        for name in NAMED.get(ident, ()))]

    def candidate(item):
        slug = item.get("slug", "")
        if slug and slug not in result["candidate_slugs"]:
            result["candidate_slugs"].append(slug)

    for item in selected:
        candidate(item)

    def add_text(items, pattern, facet):
        count = 0
        for item in items:
            original = item.get("original", {})
            quote = _excerpt(original.get("text", ""), pattern)
            if quote is None:
                continue
            candidate(item)
            evidence = {"slug": item.get("slug", ""), "name": item.get("name", ""),
                                       "source_url": original.get("source_url", ""),
                                       "quote": quote, "facet": facet, "license": original.get("license", "UNKNOWN"),
                                       "source_type": item.get("source_type", "registered_original"),
                                       "slug_registered": bool(item.get("slug"))}
            if not any(e["source_url"] == evidence["source_url"] and e["quote"] == quote
                       for e in result["evidence"]):
                result["evidence"].append(evidence)
            count += 1
        return count

    def add_fact(items, field, facet):
        count = 0
        for item in items:
            value = item.get("facts", {}).get(field)
            provider = item.get("facts_source", {}).get("provider", "")
            if not value or provider not in {"군산시 문화관광", "한국관광공사 TourAPI"}:
                continue
            candidate(item)
            fact_source_url = item.get("facts_source", {}).get("source_url", "")
            if not fact_source_url and provider == "군산시 문화관광":
                fact_source_url = item.get("original", {}).get("source_url", "")
            result["evidence"].append({"slug": item.get("slug", ""), "name": item.get("name", ""),
                                       "source_url": fact_source_url,
                                       "quote": str(value), "facet": facet, "license": "UNKNOWN",
                                       "source_type": "sourced_facts", "source_field": "facts." + field,
                                       "provider": provider, "slug_registered": bool(item.get("slug"))})
            count += 1
        return count

    def add_courses(pages, facet="코스 순서"):
        found = []
        for course in courses:
            if course.get("source_page") not in pages or not course.get("stops"):
                continue
            text = course.get("original", {}).get("text", "")
            if not text.strip():
                continue
            candidate(course)
            result["evidence"].append({"slug": course["slug"], "name": course.get("name", ""),
                                       "source_url": course.get("source_url") or course.get("original", {}).get("source_url", ""),
                                       "quote": text[:600], "facet": facet,
                                       "license": course.get("original", {}).get("license", "UNKNOWN")})
            found.append(course)
        return found

    if ident in ("N01", "N02"):
        count = add_text(selected, "마을은|촬영 장소", "장소 설명")
        if ident == "N01":
            add_text(selected, "(?:입장|관람|이용)[^\n]{0,20}(?:료|무료)", "원문 이용요금 언급")
            result["missing"].append("입장료의 현재 적용 여부 확인값")
        elif not (add_fact(selected, "address", "출처가 기록된 주소 필드")
                  or add_text(selected, "주소\\s*[:：]", "원문 주소")):
            result["missing"].append("주소·위치 직접 근거")
        if not count:
            result["missing"].append("장소 소개 원문")
    elif ident in ("N05", "N08"):
        pattern = "대웅전|사찰|절이다|금강선사" if ident == "N05" else "말랭이.{0,5}마을|산비탈|레지던스"
        if not add_text(selected, pattern, "해당 장소 자체 소개 원문"):
            result["missing"].append(UNVERIFIED[ident])
    elif ident == "N03":
        add_text(selected, "\\d{1,2}:\\d{2}|휴관", "원문 관람시간·휴관일 언급")
        add_text(selected, "휴관", "원문 휴관일")
        result["missing"].append("박물관 운영시간의 출처 간 상충 여부 및 현재 적용값 확인 필요; 원문 언급만으로 확정하지 않음")
        for item in selected:
            body_times = set(re.findall(r"\d{1,2}:\d{2}", item.get("original", {}).get("text", "")))
            for field in item.get("source_fields", []):
                field_times = set(re.findall(r"\d{1,2}:\d{2}", field.get("value", "")))
                if field.get("label") == "이용시간" and body_times and field_times - body_times:
                    result["missing"].append("수집 본문과 상세 정보표의 이용시간 상충을 확인함; 검증 전 확정 불가")
                    result["evidence"].append({"slug": item.get("slug", ""), "name": item.get("name", ""),
                                               "source_url": item.get("original", {}).get("source_url", ""),
                                               "quote": field["value"], "facet": "본문과 상충하는 원문 정보표 이용시간",
                                               "license": item.get("original", {}).get("license", "UNKNOWN"),
                                               "source_type": "raw_source_field", "source_field": "source_fields.이용시간"})
    elif ident == "N04":
        add_text(selected, "실내.{0,40}(?:개방|관람)|내부.{0,40}(?:개방|관람)", "실내 관람 허용·제한을 명시한 원문")
        result["missing"].append("기재된 실내 개방·제한 조건의 현재 적용 여부 확인")
    elif ident == "N06":
        add_text(selected, "(?:한 바퀴|산책|보행)[^\n]{0,80}(?:시간|분)", "보행 소요시간 언급")
        result["missing"].append("한 바퀴의 경로·출발점·보행 조건과 소요시간 직접 근거 대조")
    elif ident == "N07":
        add_text(selected, "월명공원은|정상|공원", "산책 후보의 공원 소개")
        result["missing"].append("공원 내부 산책 동선·경유지 순서의 직접 근거")
    elif ident in ("N09", "P02"):
        if not add_courses({"m2135"}):
            result["missing"].append("당일 코스 분류에 속한 공식 원문과 경유지 순서")
    elif ident == "N10":
        available = add_courses({"m2136"})
        if not available:
            result["missing"].append("1박 2일 코스 원문")
        elif not any("1일차" in c["original"]["text"] and "2일차" in c["original"]["text"] for c in available):
            result["missing"].append("1·2일차로 나뉜 경유지의 직접 근거")
    elif ident == "N11":
        add_courses({"m2107"}, "근대문화유산 코스 순서")
        result["missing"].append("경유지 사이 도보 이동·보행 가능 여부(코스가 존재해도 도보임을 의미하지 않음)")
    elif ident == "N12":
        selected_courses = [c for c in courses if c.get("source_page") in {"m2135", "m2136"}
                            and all(any(token in s.get("name", "") for s in c.get("stops", []))
                                    for token in ("선유", "장자도", "대장도"))]
        for c in selected_courses:
            candidate(c)
            original = c.get("original", {})
            result["evidence"].append({"slug": c["slug"], "name": c.get("name", ""),
                                       "source_url": c.get("source_url", ""), "quote": original.get("text", "")[:600],
                                       "facet": "관련 명칭을 포함한 코스 순서", "license": original.get("license", "UNKNOWN")})
        island_sources = [p for p in sources if _normalized(p.get("name", "")) in {"선유도", "장자도", "대장도"}]
        add_text(island_sources, "다리|연결|섬", "섬 자체 소개·연결 근거")
        result["missing"].append("코스 내 명칭 대응과 현재 이동·접근 조건 확인")
    elif ident == "N13":
        available = add_courses({"m2137"})
        if not available:
            result["missing"].append("2박 3일 코스 원문")
        elif not any("3일차" in c["original"]["text"] for c in available):
            result["missing"].append("제목은 2박 3일이나 저장 원문에서 3일차 경유지를 확인하지 못함")
    elif ident == "N19":
        city_sources = [p for p in sources if "시티투어" in p.get("name", "")]
        regular = add_text(city_sources, "시티투어|사전예약|운행", "수집된 시티투어 안내(현재 운행 확정 아님)")
        for sample in samples or []:
            text = sample.get("original_text", "")
            quote = _excerpt(text, "시티투어")
            if quote is not None:
                result["evidence"].append({"slug": "", "name": sample.get("name", ""),
                                           "source_url": sample.get("source_url", ""),
                                           "quote": quote, "facet": "기간 한정 공지에 시티투어 존재 언급",
                                           "license": sample.get("original_license", "UNKNOWN")})
        result["missing"].append("현재 운행 여부·해당 날짜 예약 가능 여부·운영조건 재확인 필요" if regular else
                                  "특정 추석 연휴 증차 공지의 근거와 현재 운행 여부는 구분해야 함; 정기 운영 안내 원문 미확인")
    elif ident in ("N14", "N15", "N16", "N17", "N18", "P03"):
        travel = [p for p in (documents or []) if any(w in p.get("name", "") for w in
                  ("교통", "버스", "철도", "군산역", "시티투어"))]
        if ident in ("N18", "P03"):
            add_text(selected, "주차", "해당 장소의 원문 주차 언급")
        elif ident == "N15":
            add_text(selected, "차량|자동차|주차", "선유도 자체 교통·주차 언급")
            add_text([p for p in travel if "선유" in p["original"]["text"]], "자동차로 진입|선유.{0,20}주차장|주차장", "선유도 관련 교통 안내")
            add_text([p for p in travel if "선유" in p["original"]["text"]], "선유.{0,20}주차장", "선유도 관련 주차장 명칭 근거")
        elif ident == "N17":
            add_text([p for p in travel if "군산역" in p["original"]["text"] and "박물관" in p["original"]["text"]],
                     "군산역", "군산역과 박물관을 함께 언급한 교통 안내(노선 답변 검토 필요)")
        else:
            add_text(travel, "서울|기차|철도|시내버스|시외버스|고속버스|대중교통", "교통 안내 보조 근거")
        result["missing"].append(UNVERIFIED[ident] + "의 현재 적용 여부·정확한 경로/위치 확인")
    elif ident == "N20":
        add_text(sources, "어린이.{0,20}체험|아동.{0,20}체험|어린이박물관", "어린이 시설·체험의 직접 근거")
        result["missing"].append("체험연령·유모차·보호자 동반 등 방문 적합성 확인값")
    elif ident == "N22":
        add_text(sources, "근대 추억|사진도 찍을", "레트로 또는 사진 촬영의 일부 근거")
        result["missing"].append("각 후보마다 레트로와 사진 촬영 가능 범위를 함께 확인할 근거")
    elif ident == "N23":
        if not add_text(sources, "영화[^\n]{0,200}촬영|촬영 영화", "영화 촬영 사실"):
            result["missing"].append("영화·드라마 촬영을 명시한 장소 자체 원문")
    elif ident == "N24":
        if not add_text(sources, "야경|야간경관", "야경 직접 근거"):
            result["missing"].append("야경을 명시한 장소 자체 원문")
    elif ident == "N26":
        if not add_text(sources, "가을.{0,40}단풍|가을.{0,40}풍경", "가을 직접 근거"):
            result["missing"].append("가을을 명시한 장소 자체 원문")
    elif ident == "N21":
        add_text(sources, "실내|우천", "실내·우천 언급(이용 제한 문구 포함 가능)")
        result["missing"].append("실내 언급의 허용/제한 맥락·현재 개방·우천 접근 조건 확인; 명칭만으로 적합성 확정 금지")
    elif ident == "N25":
        add_text(sources, "(?:입장|관람|이용)[^\n]{0,20}무료|무료[^\n]{0,20}(?:입장|관람)", "무료 입장·관람의 원문 언급")
        result["missing"].append("무료 적용 대상·기간·현재 이용요금 확인")
    elif ident in ("N27", "N28"):
        events = [p for p in sources if any(w in p.get("name", "") for w in ("축제", "행사"))
                  and (ident == "N28" or "시간여행" in p.get("name", ""))]
        add_text(events, "20\\d{2}|기간|일시|개최", "수집된 행사 일정 언급")
        result["missing"].append("측정 날짜의 연도·월과 행사 적용 기간 및 취소/변경 공지 확인")
    elif ident in ("N29", "P01"):
        stays = [p for p in sources if p.get("kind") == "stay"]
        add_text(stays, "독채", "숙소 자체 원문의 독채 언급")
        result["missing"].append("독채 적용 객실·현재 영업·예약 경로·업주 확인")
    elif ident == "N30":
        food = [p for p in sources if p.get("kind") == "food"]
        add_text(food, "메뉴|음식|요리|식당|전문", "음식점 자체 원문")
        result["missing"].append("현재 메뉴·영업 여부 확인; 원문 존재가 맛 평가·순위의 근거는 아님")
    else:
        result["missing"].append(UNVERIFIED.get(ident, "이 질문의 직접 답변 근거"))
    if result["evidence"]:
        result["answer_status"] = "일부" if result["missing"] else "답충분"
    # Suggestions without direct answer evidence must never become '답충분'.
    return result


def guide_candidates(places: list[dict], courses: list[dict], documents: list[dict] | None = None) -> list[dict]:
    sources = places + (documents or [])

    def candidates(pattern, *, kind=None, reject=None):
        found, seen = [], set()
        for place in sources:
            original = place.get("original", {})
            text = original.get("text", "")
            if kind and place.get("kind") != kind:
                continue
            quote = _excerpt(text, pattern)
            if quote is None or (reject and re.search(reject, quote)):
                continue
            key = original.get("source_url", ""), quote
            if key in seen:
                continue
            seen.add(key)
            found.append({"slug": place.get("slug", ""), "name": place.get("name", ""),
                          "source_url": key[0], "quote": quote})
        return found

    children = candidates("어린이.{0,20}체험|아동.{0,20}체험|어린이박물관")
    indoor = candidates("실내.{0,15}(?:전시|체험|관광)", reject="(?:않|불가|금지|중단)")
    stays = candidates("독채", kind="stay")
    transit = candidates("(?:시내버스|대중교통|도보).{0,50}(?:이용|접근|진입|탑승)")
    return [
        {"name": "차 없는 당일여행", "candidates": transit, "missing": "현재 대중교통·도보 접근 및 출발지·환승 확인 필요. 당일 코스만으로 무차량 여행을 단정하지 않음."},
        {"name": "아이와 함께", "candidates": children, "missing": "체험연령·유모차·보호자 동반 조건. 후보 등록과 가이드 본문 작성은 별도 검수."},
        {"name": "비 오는 날", "candidates": indoor, "missing": "현재 개방·우천 접근 조건 확인 필요. 실내 이용 언급은 우천 적합성 확정이 아님."},
        {"name": "독채 숙소 고르기", "candidates": stays, "missing": "독채 적용 객실·현재 영업·업주 확인 필요. 코스의 '숙소'·관광호텔 언급으로 대체하지 않음."},
    ]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", "").replace("\n", " ")


def coverage_markdown(results: list[dict], place_count: int, course_count: int) -> str:
    lines = ["# 고정 질문군 원문 근거 점검", "",
             f"입력: 저장된 장소 원문 {place_count}건, 코스 원문 {course_count}건. 질문 CSV와 데이터는 변경하지 않았습니다.", "",
             "`답충분`은 질문에 필요한 최소 원문 근거가 있다는 뜻입니다. 검수·이용조건·공개·색인·실제 AI 인용을 통과했다는 뜻이 아닙니다. `일부`는 관련 원문은 있지만 질문 전체를 답할 근거가 부족한 상태, `미확인`은 직접 답변 근거를 찾지 못한 상태입니다.", "",
             "장소·코스 이름의 단순 일치, 코스에서 언급한 시설명, 요약·FAQ 문장은 답변 근거로 사용하지 않습니다. N/P를 분리하고 U군은 이 점검에서 제외했습니다.", ""]
    lines.extend(["별도 정적 안내·수집 문서는 보조 근거입니다. slug가 없는 문서는 공개 페이지가 등록되지 않은 상태이며, 시티투어 안내나 기간 한정 공지의 존재를 현재 운행 확인으로 취급하지 않습니다.", ""])
    for group, title in (("N", "N 핵심 30문항"), ("P", "P 플랫폼 제외 3문항")):
        rows = [r for r in results if r["group"] == group]
        counts = {status: sum(r["answer_status"] == status for r in rows) for status in ("답충분", "일부", "미확인")}
        lines.extend([f"## {title}", "", " / ".join(f"{status} {number}건" for status, number in counts.items()), "",
                      "| ID | 질문 | 후보 slug | 원문 근거 | 부족한 데이터 |", "| --- | --- | --- | --- | --- |"])
        for r in rows:
            lines.append("| " + " | ".join(_cell(str(v)) for v in (r["id"], r["question"], ", ".join(r["candidate_slugs"]) or "없음", r["answer_status"], "; ".join(r["missing"]) or "질문 수준의 최소 원문 근거 있음")) + " |")
        lines.append("")
    lines.extend(["## 원문 근거 발췌(검수용)", "", "아래 문구는 저장된 `original.text`·보조 자료의 `original_text`에서 가져온 연속 부분 문자열입니다. 출처가 기록된 주소 등은 `sourced_facts`와 필드 경로로 별도 표시합니다. 원문은 수정하지 않았으며 긴 코스는 앞부분만 발췌했습니다. 원문 전체의 공개 가능 여부는 권리 리포트로 별도 판단해야 합니다.", ""])
    for r in results:
        for e in r["evidence"]:
            lines.extend([f"### {r['id']} / {e['slug'] or '공개 페이지 slug 미등록 원문'} / {e['facet']}", "", f"자료명: {e['name']}", "", f"출처: {e['source_url']} · 원문 이용조건: {e['license']}",
                          f"근거 유형: {e.get('source_type', 'original')} {e.get('source_field', '')}", "", "```text", e["quote"], "```", ""])
    return "\n".join(lines)


def guide_markdown(guides: list[dict]) -> str:
    lines = ["# 가이드 4종 후보 검토", "", "가이드 본문은 작성하지 않았습니다. 저장된 장소·코스 원문에서 직접 확인할 수 있는 후보와 정확한 원문 발췌만 기록합니다. 후보는 게재 승인이나 완성된 여행 추천이 아닙니다.", ""]
    for guide in guides:
        lines.extend([f"## {guide['name']}", "", f"후보: {', '.join(c['slug'] or c['name'] + ' (공개 페이지 slug 없음)' for c in guide['candidates']) or '없음(근거 미확인)'}", "", f"부족한 데이터: {guide['missing']}", ""])
        for c in guide["candidates"]:
            lines.extend([f"{c['name']} · {c['source_url']}", "", "```text", c["quote"], "```", ""])
    return "\n".join(lines)


def run(questions_path: Path, data: Path, raw_courses_path: Path, reports: Path,
        *, out: Path | None = None, guides_out: Path | None = None,
        sample_review_path: Path | None = None, raw_dir: Path | None = None) -> list[dict]:
    with questions_path.open(encoding="utf-8-sig", newline="") as f:
        questions = [q for q in csv.DictReader(f) if q.get("group") in {"N", "P"}]
    expected = {f"N{i:02d}" for i in range(1, 31)} | {f"P{i:02d}" for i in range(1, 4)}
    if len(questions) != 33 or {q["id"] for q in questions} != expected:
        raise ValueError("Expected the fixed N30/P3 question IDs without duplicates")
    places = json.loads((data / "places.json").read_text("utf-8"))
    raw = json.loads(raw_courses_path.read_text("utf-8"))
    imported_path = data / "courses.json"
    imported = json.loads(imported_path.read_text("utf-8")) if imported_path.exists() else []
    raw_keys = {(c.get("name"), c.get("original", {}).get("source_url") or c.get("source_url")) for c in raw}
    raw = raw + [c for c in imported if (c.get("name"), c.get("original", {}).get("source_url")) not in raw_keys]
    courses = course_candidates(raw, imported)
    sample_path = sample_review_path or raw_courses_path.parent / "gunsan" / "sample_review.json"
    samples = json.loads(sample_path.read_text("utf-8")).get("samples", []) if sample_path.exists() else []
    source_dir = raw_dir or raw_courses_path.parent / "gunsan"
    documents = []
    for filename, key, label in (("static_documents.json", "documents", "static_source"),
                                 ("details_crawl.json", "records", "raw_detail_source")):
        path = source_dir / filename
        if path.exists():
            documents.extend(source_documents(json.loads(path.read_text("utf-8")).get(key, []), label))
    results = [assess_question(q, places, courses, samples, documents) for q in questions]
    coverage_path = out or reports / "question_coverage.md"
    guides_path = guides_out or reports / "guide_candidates.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    guides_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(coverage_markdown(results, len(places), len(courses)), "utf-8")
    guides_path.write_text(guide_markdown(guide_candidates(places, courses, documents)), "utf-8")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("measurement/questions.csv"))
    parser.add_argument("--data", type=Path, default=Path("data/gunsan"))
    parser.add_argument("--raw-courses", type=Path, default=Path("data/raw/gunsan_courses.json"))
    parser.add_argument("--raw", type=Path, help="Collector raw HTML directory; courses JSON is its sibling")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--guides-out", type=Path)
    parser.add_argument("--sample-review", type=Path, help="Optional saved detail samples; only N19 uses them")
    args = parser.parse_args(argv)
    raw_courses_path = args.raw.parent / "gunsan_courses.json" if args.raw is not None else args.raw_courses
    results = run(args.questions, args.data, raw_courses_path, args.reports,
                  out=args.out, guides_out=args.guides_out,
                  sample_review_path=args.sample_review or (args.raw / "sample_review.json" if args.raw else None),
                  raw_dir=args.raw)
    print(json.dumps({group: {status: sum(r["group"] == group and r["answer_status"] == status for r in results)
                             for status in ("답충분", "일부", "미확인")} for group in ("N", "P")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
