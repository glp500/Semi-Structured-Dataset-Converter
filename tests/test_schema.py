import pytest
from prompts.schema import OutputModel

def test_output_model_validation_success():
    data = {
        "entities": [
            {"id": "abc123", "type": "Person", "name": "Alice"}
        ]
    }
    model = OutputModel.model_validate(data)
    assert model.entities[0].id == "abc123"
    assert model.entities[0].attributes is None
    assert model.entities[0].relations is None

def test_output_model_validation_missing_required():
    bad_data = {
        "entities": [
            {"type": "X", "name": "Y"}
        ]
    }
    with pytest.raises(Exception) as excinfo:
        OutputModel.model_validate(bad_data)
    assert "id" in str(excinfo.value) and "field required" in str(excinfo.value)

def test_output_model_validation_extra_field():
    bad_data = {
        "entities": [
            {"id": "1", "type": "X", "name": "Y", "extra": 5}
        ]
    }
    with pytest.raises(Exception) as excinfo:
        OutputModel.model_validate(bad_data)
    assert "extra" in str(excinfo.value)

def test_optional_missing_flag():
    data = {
        "entities": [
            {
                "id": "id1",
                "type": "TypeA",
                "name": "NameA",
                "attributes": {"missing": True},
                "relations": {"missing": True}
            }
        ]
    }
    model = OutputModel.model_validate(data)
    ent = model.entities[0]
    assert isinstance(ent.attributes, dict) and ent.attributes.get("missing") is True
    assert ent.relations and getattr(ent.relations, "missing") is True