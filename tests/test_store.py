"""Store module tests."""

# pylint: disable=W0621,W0212,W0613
# flake8: noqa: PLR2004

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from openbb_store.store import Store


@pytest.fixture()
def store() -> Store:
    inst = Store()
    inst.verbose = False
    return inst


def test_add_store_duplicate_raises(store: Store):
    store.add_store("dup", [1])
    with pytest.raises(KeyError):
        store.add_store("dup", [2])


def test_get_store_default_name(store: Store):
    store.add_store("solo", [42])
    assert store.get_store() == [42]


def test_update_store_overwrites(store: Store):
    store.add_store("item", [1, 2])
    store.update_store("item", [3])
    assert store.get_store("item") == [3]


def test_remove_store_deletes_entry(store: Store):
    store.add_store("remove_me", [1])
    store.remove_store("remove_me")
    assert "remove_me" not in store.list_stores


def test_clear_stores_resets_directory(store: Store):
    store.add_store("one", [1])
    store.add_store("two", [2])
    store.clear_stores()
    assert store.list_stores == []


def test_get_schema_for_dataframe(store: Store):
    df = pd.DataFrame({"id": [1, 2], "value": [10, 20]}).set_index("id", drop=False)
    store.add_store("frame", df)
    schema = store.get_schema("frame")
    assert schema["length"] == 2
    assert list(schema["columns"]) == ["id", "value"]


def test_save_and_load_store_roundtrip(tmp_path):
    store = Store()
    store.verbose = False
    store.user_data_directory = f"{tmp_path}/"
    store.add_store("numbers", [1, 2, 3])
    store.save_store_to_file("snapshot")

    restored = Store()
    restored.verbose = False
    restored.user_data_directory = f"{tmp_path}/"
    restored.load_store_from_file("snapshot")

    assert restored.get_store("numbers") == [1, 2, 3]


def test_load_store_from_file_missing(tmp_path):
    store = Store()
    store.verbose = False
    store.user_data_directory = f"{tmp_path}/"
    with pytest.raises(FileNotFoundError):
        store.load_store_from_file("missing")


def test_load_store_from_file_with_names_filter(tmp_path):
    store = Store()
    store.verbose = False
    store.user_data_directory = f"{tmp_path}/"
    store.add_store("keep", [1])
    store.add_store("drop", [2])
    store.save_store_to_file("bundle")

    restored = Store()
    restored.verbose = False
    restored.user_data_directory = f"{tmp_path}/"
    restored.load_store_from_file("bundle", names=["keep"])

    assert restored.list_stores == ["keep"]


def test_load_from_excel_uses_loader(monkeypatch: pytest.MonkeyPatch):
    store = Store()
    store.verbose = False

    excel_stub = type("ExcelStub", (), {"sheet_names": ["Sheet1"]})()
    fake_bytes = BytesIO(b"excel-bytes")

    def fake_loader(file, **kwargs):
        return excel_stub, fake_bytes

    monkeypatch.setattr(Store, "_load_from_excel", staticmethod(fake_loader))

    result = store.load_from_excel(b"ignored", name="excel_store", description="stub")

    assert result is excel_stub
    assert "excel_store" in store.list_stores


def test_append_list_extends(store: Store):
    store.add_store("numbers", [1, 2])
    store.append_store("numbers", [2, 3, 4])
    assert store.get_store("numbers") == [1, 2, 3, 4]


def test_append_list_of_dicts_updates_matching_entry(store: Store):
    initial = [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
    store.add_store("records", initial)
    store.append_store("records", {"id": 2, "value": 99}, target_key="id")
    updated = store.get_store("records")
    assert updated[1]["value"] == 99
    assert len(updated) == 2


def test_append_list_of_dicts_scalar_broadcast(store: Store):
    initial = [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
    store.add_store("records", initial)
    store.append_store("records", "new", target_key="value")
    updated = store.get_store("records")
    assert [item["value"] for item in updated] == ["new", "new"]


def test_append_nested_dict(store: Store):
    initial = {"level1": {"level2": {"target": 1}}}
    store.add_store("nested", initial)
    store.append_store("nested", 42, target_key="target")
    updated = store.get_store("nested")
    assert updated["level1"]["level2"]["target"] == 42


def test_append_dataframe_replaces_and_appends(store: Store):
    existing = pd.DataFrame(
        {"id": [1, 2], "value": [10, 20]},
    ).set_index("id", drop=False)
    incoming = pd.DataFrame(
        {"id": [2, 3], "value": [99, 30]},
    ).set_index("id", drop=False)

    store.add_store("frame", existing)
    store.append_store("frame", incoming)

    result = store.get_store("frame").set_index("id")
    assert result.loc[2, "value"] == 99
    assert result.loc[3, "value"] == 30
    assert len(result) == 3


def test_append_dataframe_column_mismatch_raises(store: Store):
    existing = pd.DataFrame({"id": [1], "value": [10]}).set_index("id", drop=False)
    incoming = pd.DataFrame({"id": [2], "other": [30]}).set_index("id", drop=False)
    store.add_store("frame", existing)
    with pytest.raises(KeyError):
        store.append_store("frame", incoming)


def test_append_excelfile_updates_sheet(monkeypatch: pytest.MonkeyPatch):
    existing = pd.DataFrame(
        {"id": [1, 2], "value": [10, 20]},
    ).set_index("id", drop=False)
    incoming = pd.DataFrame(
        {"id": [2, 3], "value": [99, 30]},
    ).set_index("id", drop=False)

    def excel_init(self, sheets):
        self.sheet_names = list(sheets)
        self._sheets = {name: df.copy() for name, df in sheets.items()}

    def excel_parse(self, sheet):
        return self._sheets[sheet].copy()

    ExcelFileStub = type(
        "ExcelFile", (), {"__init__": excel_init, "parse": excel_parse}
    )
    excel_stub = ExcelFileStub({"Sheet1": existing})

    store = Store()
    store.verbose = False
    store.directory["excel"] = {"description": None}
    captured: dict[str, object] = {}

    monkeypatch.setattr(store, "get_store", lambda name, **kwargs: excel_stub)
    monkeypatch.setattr(store, "remove_store", lambda name: None)

    def fake_add_store(name, data, description=None):
        captured["name"] = name
        captured["data"] = data
        captured["description"] = description

    monkeypatch.setattr(store, "add_store", fake_add_store)
    store.append_store("excel", incoming, target_key="Sheet1")

    payload = captured["data"]
    assert isinstance(payload, dict)
    assert payload["sheet_names"] == ["Sheet1"]

    buffer = BytesIO(payload["bytes"])
    result = pd.read_excel(buffer, sheet_name="Sheet1")
    assert list(result["value"]) == [10, 99, 30]
    assert list(result["id"]) == [1, 2, 3]


def test_append_string_appends_text(store: Store):
    store.add_store("note", "First line")
    store.append_store("note", "Second line")
    assert store.get_store("note") == "First line\nSecond line"


def test_append_string_json_raises(store: Store):
    store.add_store("json", '{"a": 1}')
    with pytest.raises(TypeError):
        store.append_store("json", "extra")
    assert store.get_store("json") == '{"a": 1}'
