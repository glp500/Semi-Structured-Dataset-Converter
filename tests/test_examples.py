import os
import fitz
import json
import importlib
import examples.init as init

def create_pdf_with_text(path: str, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()

def test_load_examples(monkeypatch, tmp_path):
    json_path1 = tmp_path / "ex1.json"
    pdf_path1 = tmp_path / "ex1.pdf"
    json_path2 = tmp_path / "ex2.json"
    pdf_path2 = tmp_path / "ex2.pdf"
    data1 = {"foo": "bar"}
    data2 = {"id": "001", "name": "Test"}
    json_path1.write_text(json.dumps(data1))
    json_path2.write_text(json.dumps(data2))
    create_pdf_with_text(pdf_path1, "Hello PDF1")
    create_pdf_with_text(pdf_path2, "Hello PDF2")
    monkeypatch.setattr(init, "__file__", str(tmp_path / "__init__.py"))
    importlib.reload(init)
    example_list = init.load_examples()
    assert len(example_list) == 2
    pdf_texts = [ex[0] for ex in example_list]
    json_texts = [ex[1] for ex in example_list]
    assert any("Hello PDF1" in txt for txt in pdf_texts)
    assert any("Hello PDF2" in txt for txt in pdf_texts)
    assert any('"foo": "bar"' in txt for txt in json_texts)
    assert any('"name": "Test"' in txt for txt in json_texts)
    limited_list = init.load_examples(max_examples=1)
    assert len(limited_list) == 1