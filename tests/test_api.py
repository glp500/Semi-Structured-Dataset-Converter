import types
import pytest
import services.api as api

class DummyModel:
    def __init__(self, model_name=None):
        self.prompts = []
    def generate_content(self, prompt, generation_config=None):
        self.prompts.append(prompt)
        if "chunk 2" in prompt or "chunk2" in prompt:
            text = '{"b": 2}'
        elif "chunk 1" in prompt or "chunk1" in prompt:
            text = '{"a": 1}'
        else:
            text = '{"dummy": true}'
        return types.SimpleNamespace(text=text)

def test_handle_api_error(monkeypatch):
    errors = []
    warnings = []
    stopped = {"called": False}
    monkeypatch.setattr(api.st, "error", lambda msg: errors.append(msg))
    monkeypatch.setattr(api.st, "warning", lambda msg: warnings.append(msg))
    monkeypatch.setattr(api.st, "stop", lambda: stopped.update({"called": True}))
    e = Exception("Illegal header value in request")
    api.handle_api_error(e, step_name="testing")
    assert any("testing" in err for err in errors[:1])
    assert any("Illegal header value" in err for err in errors)
    assert any("pip install --upgrade --force-reinstall" in w for w in warnings)
    assert stopped["called"]

def test_configure_api(monkeypatch):
    config_args = {}
    monkeypatch.setattr(api.genai, "configure", lambda api_key=None: config_args.update({"key": api_key}))
    result = api.configure_api("MYKEY")
    assert result is True and config_args.get("key") == "MYKEY"
    def fail_config(api_key=None):
        raise Exception("fail")
    monkeypatch.setattr(api.genai, "configure", fail_config)
    errors = []
    monkeypatch.setattr(api.st.sidebar, "error", lambda msg: errors.append(msg))
    result2 = api.configure_api("OTHER")
    assert result2 is False
    assert any("Failed to configure" in msg for msg in errors)

def test_generate_structured_json_single(monkeypatch):
    monkeypatch.setattr(api, "chunk_text", lambda text: [text])
    monkeypatch.setattr(api.genai, "GenerativeModel", DummyModel)
    pages_text = ["sample text"]
    out_json = api.generate_structured_json(
        pages_text=pages_text,
        context_text="CTX",
        relationships_text="REL",
        additional_context_text="ADD",
        manual_context_text="MANUAL",
        examples=None
    )
    assert '{"dummy": true}' in out_json

def test_generate_structured_json_multiple(monkeypatch):
    monkeypatch.setattr(api, "chunk_text", lambda text: ["chunk1", "chunk2"])
    monkeypatch.setattr(api.genai, "GenerativeModel", DummyModel)
    pages_text = ["page1", "page2"]
    result_json = api.generate_structured_json(
        pages_text=pages_text,
        context_text="CTX",
        relationships_text="REL",
        additional_context_text="ADD",
        manual_context_text="MANUAL",
        examples=None
    )
    data = {}
    try:
        data = __import__("json").loads(result_json)
    except Exception:
        pytest.fail("Output is not valid JSON")
    assert data.get("a") == 1 and data.get("b") == 2

def test_generate_csv_from_json(monkeypatch):
    monkeypatch.setattr(api.genai, "GenerativeModel", DummyModel)
    dummy_json = '{"some": "data"}'
    out_text = api.generate_csv_from_json(
        json_text=dummy_json,
        table_names=["TableX"],
        context_text="CTX",
        relationships_text="REL",
        additional_context_text="ADD",
        manual_context_text="MANUAL",
        example_snippets=[]
    )
    assert '{"dummy": true}' in out_text