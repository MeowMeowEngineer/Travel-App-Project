"""TourAPI client (한국관광공사 국문 관광정보 서비스, KorService2) with an on-disk response cache.

Notes
- The key may be the portal's "Encoding" or "Decoding" form. A key containing '%' is unquoted once,
  then urlencode() encodes it exactly once, so neither form is double-encoded.
- Every successful response is cached under data/cache/tourapi/, so re-runs cost nothing.
- `fetched_dates` records, per answered call, the date its data was fetched: today for a live call, the cache
  file's date for a cached one. Merges use it as checked_at, so a cache-first re-run never bumps a 확인일.
- `last_total` is the provider's totalCount of the last answered call (list sizes for the call budget);
  `cached(op, **params)` says whether a call would be answered from the cache (no live call needed).
- Each client stops itself after `max_calls` live requests (default 900, inside the development
  account's daily limit). The next run continues from the cache.
- Provider error messages (resultMsg, returnAuthMsg, errMsg) are shown as-is with only the key masked.
- base_url / op_suffix / detail_common_params come from site.json -> "tourapi".
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_MAX_CALLS = 900

CONTENT_TYPES = {
    "12": "관광지", "14": "문화시설", "15": "축제·공연·행사", "25": "여행코스",
    "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점",
}
# contentTypeId -> our entity kind
KIND_BY_TYPE = {"12": "attraction", "14": "attraction", "28": "attraction", "38": "attraction",
                "32": "stay", "39": "food"}

# detailIntro field names per contentTypeId -> our fact keys (TourAPI 4.x manual)
INTRO_FIELDS = {
    "usetime": {"12": "usetime", "14": "usetimeculture", "28": "usetimeleports",
                "38": "opentime", "39": "opentimefood", "15": "playtime"},
    "restdate": {"12": "restdate", "14": "restdateculture", "28": "restdateleports",
                 "38": "restdateshopping", "39": "restdatefood"},
    "usefee": {"14": "usefee", "28": "usefeeleports", "15": "usetimefestival"},
    "parking": {"12": "parking", "14": "parkingculture", "28": "parkingleports",
                "38": "parkingshopping", "39": "parkingfood", "32": "parkinglodging"},
    "parkingfee": {"14": "parkingfee", "28": "parkingfeeleports"},
    "spendtime": {"14": "spendtime", "15": "spendtimefestival", "25": "taketime"},
    "infocenter": {"12": "infocenter", "14": "infocenterculture", "28": "infocenterleports",
                   "38": "infocentershopping", "39": "infocenterfood", "32": "infocenterlodging",
                   "25": "infocentertourcourse", "15": "sponsor1tel"},
    "checkin": {"32": "checkintime"},
    "checkout": {"32": "checkouttime"},
    "menu": {"39": "firstmenu"},
    "babycarriage": {"12": "chkbabycarriage", "14": "chkbabycarriageculture",
                     "28": "chkbabycarriageleports", "38": "chkbabycarriageshopping"},
    "pet": {"12": "chkpet", "14": "chkpetculture", "28": "chkpetleports", "38": "chkpetshopping"},
    "expagerange": {"12": "expagerange", "28": "expagerangeleports"},
    "useseason": {"12": "useseason"},
}

QUOTA_MARKERS = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS", "TOO_MANY_REQUESTS", "QUOTA_EXCEEDED")


class TourAPIError(RuntimeError):
    pass


class TourAPIStopError(TourAPIError):
    """Stop the current run (per-run call cap or provider quota); the next run resumes from cache."""


class TourAPIQuotaError(TourAPIStopError):
    pass


def normalize_key(raw: str) -> str:
    """Return the decoded key. A key containing '%' (the portal's Encoding form) is unquoted once."""
    key = (raw or "").strip().strip('"').strip("'")
    return urllib.parse.unquote(key) if "%" in key else key


def redact(text: str, key: str) -> str:
    """Mask every form of the key (decoded, encoded once, form-encoded) in a message."""
    out = str(text or "")
    if not key or len(key) < 6:
        return out
    forms = {key, urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)}
    for form in sorted(forms, key=len, reverse=True):
        out = out.replace(form, "«KEY»")
    return out


def _provider_error(label: str, code: str, message: str) -> TourAPIError:
    text = f"{label}: resultCode={code or '?'} {message}".strip()
    if code == "22" or any(marker in str(message).upper() for marker in QUOTA_MARKERS):
        return TourAPIQuotaError(text)
    return TourAPIError(text)


def _xml_error(body: str) -> tuple[str, str] | None:
    def tag(*names: str) -> str:
        for name in names:
            m = re.search(rf"<{name}>\s*([^<]*)<", body or "")
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""
    code = tag("returnReasonCode", "resultCode")
    message = tag("returnAuthMsg", "resultMsg", "errMsg")
    return (code, message) if code or message else None


def total_count(payload: dict) -> int | None:
    """The provider's body.totalCount (all pages of a list), None when the payload does not carry it."""
    body = ((payload or {}).get("response") or {}).get("body") if isinstance(payload, dict) else None
    try:
        return int(body.get("totalCount")) if isinstance(body, dict) else None
    except (TypeError, ValueError):
        return None


def parse_items(payload: dict, op: str = "") -> list[dict]:
    """Return the item list from a TourAPI JSON payload (handles dict/list/empty)."""
    label = op or "TourAPI"
    gateway = payload.get("OpenAPI_ServiceResponse") if isinstance(payload, dict) else None
    if isinstance(gateway, dict):
        header = gateway.get("cmmMsgHeader") or {}
        raise _provider_error(label, str(header.get("returnReasonCode", "")),
                              header.get("returnAuthMsg") or header.get("errMsg") or "")
    resp = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(resp, dict):
        raise TourAPIError(f"{label}: 예상과 다른 응답 구조: {json.dumps(payload, ensure_ascii=False)[:300]}")
    header = resp.get("header") or {}
    code = str(header.get("resultCode", ""))
    if code not in ("0000", "00", "0"):
        raise _provider_error(label, code, str(header.get("resultMsg", "")))
    body = resp.get("body") or {}
    items = body.get("items") if isinstance(body, dict) else None
    if not items or not isinstance(items, dict):
        return []
    item = items.get("item")
    if item is None:
        return []
    values = item if isinstance(item, list) else [item]
    if not all(isinstance(value, dict) for value in values):
        raise TourAPIError(f"{label}: 예상과 다른 항목 구조")
    return values


class TourAPI:
    def __init__(self, service_key: str, base_url: str = "https://apis.data.go.kr/B551011/KorService2",
                 op_suffix: str = "2", mobile_app: str = "WebforAI",
                 cache_dir: str | Path = "data/cache/tourapi", min_interval: float = 0.3,
                 detail_common_params: dict | None = None, timeout: int = 20, offline: bool = False,
                 refresh: bool = False, max_calls: int = DEFAULT_MAX_CALLS):
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.service_key = normalize_key(service_key)
        self.base_url = base_url.rstrip("/")
        self.op_suffix = op_suffix
        self.mobile_app = mobile_app
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self.detail_common_params = detail_common_params or {}
        self.timeout = timeout
        self.offline = offline  # True: cache only, never call the network
        self.refresh = refresh  # True: ignore cached responses (weekly re-check), still write cache
        self.max_calls = max_calls
        self._last = 0.0
        self.live_calls = 0
        self.cache_hits = 0
        self.fetched_dates: list[str] = []  # ISO date each answered call's data was fetched (see module notes)
        self.last_total: int | None = None  # totalCount of the last answered call

    def _cache_path(self, op: str, params: dict) -> Path:
        key = json.dumps([self.base_url, op, sorted(params.items())], ensure_ascii=False)
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{op}-{h}.json"

    def _fail(self, label: str, status, body: str) -> TourAPIError:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            payload = None
        prefix = f"HTTP {status}; " if status not in (None, 200) else ""
        if isinstance(payload, dict):
            try:
                parse_items(payload, label)
            except TourAPIError as err:
                return type(err)(redact(prefix + str(err), self.service_key))
        found = _xml_error(body)
        if found:
            err = _provider_error(label, *found)
            return type(err)(redact(prefix + str(err), self.service_key))
        return TourAPIError(redact(f"{label}: {prefix}JSON이 아닌 응답: {(body or '')[:300]}", self.service_key))

    def cached(self, op: str, **params) -> bool:
        """True when the response of call(op, **params) is in the cache (a cache-first run answers it without a
        live call)."""
        params = {k: v for k, v in params.items() if v not in (None, "")}
        return self._cache_path(op, params).exists()

    def call(self, op: str, **params) -> list[dict]:
        label = f"{op}{self.op_suffix}"
        params = {k: v for k, v in params.items() if v not in (None, "")}
        path = self._cache_path(op, params)
        if path.exists() and not self.refresh:
            self.cache_hits += 1
            payload = json.loads(path.read_text("utf-8"))
            items = parse_items(payload, label)
            self.last_total = total_count(payload)
            self.fetched_dates.append(dt.date.fromtimestamp(path.stat().st_mtime).isoformat())
            return items
        if self.offline:
            raise TourAPIError(f"{label}: 오프라인 모드인데 캐시가 없습니다")
        if not self.service_key:
            raise TourAPIError("TOURAPI_KEY가 없습니다 (.env 또는 환경 변수)")
        if self.live_calls >= self.max_calls:
            raise TourAPIStopError(f"이번 실행의 호출 상한 {self.max_calls}회에 도달 — 다음 실행에서 캐시로 이어 갑니다")
        query = {"serviceKey": self.service_key, "MobileOS": "ETC", "MobileApp": self.mobile_app,
                 "_type": "json", **params}
        url = f"{self.base_url}/{op}{self.op_suffix}?{urllib.parse.urlencode(query)}"
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.live_calls += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"{self.mobile_app} enrichment"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", "replace")
            except (OSError, AttributeError):
                body = ""
            if error.code == 429 and not body:
                raise TourAPIQuotaError(f"{label}: HTTP 429 호출 한도") from None
            raise self._fail(label, error.code, body) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise TourAPIError(redact(f"{label}: 네트워크 오류 {type(error).__name__}: {error}",
                                      self.service_key)) from None
        finally:
            self._last = time.monotonic()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise self._fail(label, 200, raw) from None
        try:
            items = parse_items(payload, label)
        except TourAPIError as err:
            raise type(err)(redact(str(err), self.service_key)) from None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        self.last_total = total_count(payload)
        self.fetched_dates.append(dt.date.today().isoformat())
        return items

    # ---- operations -------------------------------------------------------
    def search_keyword(self, keyword: str, content_type_id: str | None = None, rows: int = 20) -> list[dict]:
        return self.call("searchKeyword", keyword=keyword, contentTypeId=content_type_id,
                         numOfRows=rows, pageNo=1, arrange="A")

    def detail_common(self, content_id: str) -> dict:
        items = self.call("detailCommon", contentId=content_id, **self.detail_common_params)
        return items[0] if items else {}

    def detail_intro(self, content_id: str, content_type_id: str) -> dict:
        items = self.call("detailIntro", contentId=content_id, contentTypeId=content_type_id)
        return items[0] if items else {}

    def detail_info(self, content_id: str, content_type_id: str) -> list[dict]:
        return self.call("detailInfo", contentId=content_id, contentTypeId=content_type_id)

    def detail_image(self, content_id: str) -> list[dict]:
        return self.call("detailImage", contentId=content_id, imageYN="Y", numOfRows=20, pageNo=1)

    def location_based(self, lat: float, lng: float, radius: int = 2000,
                       content_type_id: str | None = None, rows: int = 40) -> list[dict]:
        # arrange=E : distance order. Items carry 'dist' (metres).
        return self.call("locationBasedList", mapX=lng, mapY=lat, radius=radius,
                         contentTypeId=content_type_id, numOfRows=rows, pageNo=1, arrange="E")

    def ldong_code(self, l_dong_regn_cd: str | None = None, rows: int = 100) -> list[dict]:
        """Statutory region codes (lDongRegnCd, then lDongSignguCd under it) from the provider."""
        return self.call("ldongCode", lDongRegnCd=l_dong_regn_cd, numOfRows=rows, pageNo=1)

    def search_festival(self, event_start_date: str, l_dong_regn_cd: str | None = None,
                        l_dong_signgu_cd: str | None = None, rows: int = 100, page: int = 1) -> list[dict]:
        if not re.fullmatch(r"\d{8}", event_start_date or ""):
            raise ValueError("eventStartDate must be YYYYMMDD")
        return self.call("searchFestival", eventStartDate=event_start_date, lDongRegnCd=l_dong_regn_cd,
                         lDongSignguCd=l_dong_signgu_cd, numOfRows=rows, pageNo=page, arrange="A")

    def area_based(self, l_dong_regn_cd: str | None = None, l_dong_signgu_cd: str | None = None,
                   content_type_id: str | None = None, rows: int = 40, page: int = 1,
                   arrange: str = "A") -> list[dict]:
        """areaBasedList2 with statutory region codes (lDongRegnCd/lDongSignguCd from ldongCode2)."""
        for label, value in (("rows", rows), ("page", page)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if arrange not in {"A", "C", "D", "O", "Q", "R"}:
            raise ValueError("areaBasedList arrange must be A, C, D, O, Q or R")
        region = str(l_dong_regn_cd) if l_dong_regn_cd is not None else None
        district = str(l_dong_signgu_cd) if l_dong_signgu_cd is not None else None
        for label, value in (("lDongRegnCd", region), ("lDongSignguCd", district)):
            if value is not None and not re.fullmatch(r"[0-9]+", value):
                raise ValueError(f"{label} must be a numeric code from the provider")
        if district is not None and region is None:
            raise ValueError("lDongSignguCd requires lDongRegnCd")
        ctype = str(content_type_id) if content_type_id is not None else None
        if ctype is not None and ctype not in CONTENT_TYPES:
            raise ValueError("contentTypeId must be a documented tourism content type")
        return self.call("areaBasedList", lDongRegnCd=region, lDongSignguCd=district,
                         contentTypeId=ctype, numOfRows=rows, pageNo=page, arrange=arrange)


def from_site_config(site: dict, service_key: str, cache_dir: str | Path, offline: bool = False,
                     refresh: bool = False, max_calls: int = DEFAULT_MAX_CALLS) -> TourAPI:
    t = site.get("tourapi") or {}
    return TourAPI(
        service_key=service_key,
        base_url=t.get("base_url", "https://apis.data.go.kr/B551011/KorService2"),
        op_suffix=t.get("op_suffix", "2"),
        mobile_app=t.get("mobile_app", "WebforAI"),
        cache_dir=cache_dir,
        min_interval=float(t.get("min_interval", 0.3)),
        detail_common_params=t.get("detail_common_params") or {},
        offline=offline,
        refresh=refresh,
        max_calls=max_calls,
    )
