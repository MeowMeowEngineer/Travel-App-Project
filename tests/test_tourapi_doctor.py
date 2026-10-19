"""tools/tourapi_doctor.py — key normalisation, redaction, response classification (network mocked)."""
import importlib.util
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("tourapi_doctor", ROOT / "tools" / "tourapi_doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

DECODED = "AbC+dEf/GhI=jKl123456789=="
ENCODED = "AbC%2BdEf%2FGhI%3DjKl123456789%3D%3D"


def test_key_forms_normalise_both_inputs():
    a, b = doctor.key_forms(DECODED), doctor.key_forms(ENCODED)
    assert a["decoded"] == b["decoded"] == DECODED
    assert a["encoded_once"] == b["encoded_once"] == ENCODED
    assert b["given_form"].startswith("Encoding") and a["given_form"].startswith("Decoding")


def test_redact_hides_every_form():
    text = f"url?serviceKey={ENCODED}&x=1 raw={DECODED}"
    out = doctor.redact(text, ENCODED, DECODED)
    assert ENCODED not in out and DECODED not in out and out.count("«KEY»") == 2


def test_classify_json_success_and_gateway_error():
    ok = json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                  "body": {"items": {"item": [{"title": "경암동 철길마을", "addr1": "군산", "contentid": "1"}]}}}})
    info = doctor.classify(ok)
    assert info["format"] == "json" and info["items"] == 1 and "경암동" in info["first"]
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
           "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode>"
           "</cmmMsgHeader></OpenAPI_ServiceResponse>")
    info = doctor.classify(xml)
    assert info["format"] == "xml" and info["code"] == "30"
    assert "등록되지 않은 키" in doctor.advice(info["message"])


class FakeResp(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_run_reports_success_without_leaking_key(monkeypatch):
    seen = []
    body = json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": {"title": "경암동 철길마을", "contentid": "9"}}}}}).encode()

    def fake_urlopen(req, timeout=15):
        seen.append(req.full_url)
        return FakeResp(body)

    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(doctor.urllib.request, "urlopen", fake_urlopen)
    rep = doctor.run("경암동 철길마을", ENCODED)
    assert rep["verdict"].startswith("정상")
    assert f"serviceKey={ENCODED}&" in seen[0]          # decoded key encoded exactly once
    dumped = json.dumps(rep, ensure_ascii=False)
    assert ENCODED not in dumped and DECODED not in dumped


def test_run_explains_unregistered_key(monkeypatch):
    xml = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
           b"</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda req, timeout=15: FakeResp(xml))
    rep = doctor.run("x", DECODED)
    assert rep["verdict"].startswith("실패") and "등록되지 않은 키" in rep["verdict"]


def test_missing_key_and_blocked_network(monkeypatch):
    assert "TOURAPI_KEY가 없습니다" in doctor.run("x", "")["verdict"]
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (False, "blocked"))
    assert "접속할 수 없습니다" in doctor.run("x", DECODED)["verdict"]
