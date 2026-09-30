from pathlib import Path

import pytest

import compiler.backends as backends_pkg
from compiler.backends import registry
from compiler.backends.base import CodeGenError
from compiler.backends.plsql.backend import PlsqlBackend

FAKE_BACKEND = """
from pathlib import Path

from compiler.backends.base import Backend


class FakeBackend(Backend):
    target = "fake"
    required_keys = ("out",)
    defaults = {"flavour": "plain"}

    def compile_module(self, tree, mapping_id, scope_resolution=None):
        raise NotImplementedError

    def unit_from_json(self, data):
        raise NotImplementedError

    def assemble(self, units):
        return {"out.txt": ""}
"""


@pytest.fixture
def fresh_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(registry, "_cache", {})


def test_plsql_backend_is_discovered_by_its_target_name(fresh_registry):
    assert registry.backend_class("plsql") is PlsqlBackend
    assert "plsql" in registry.backends()


def test_unknown_target_is_an_error_listing_the_available_ones(fresh_registry):
    with pytest.raises(CodeGenError, match=r"unknown target 'nope'.*plsql"):
        registry.backend_class("nope")


def test_create_backend_merges_defaults_under_the_given_config(fresh_registry):
    backend = registry.create_backend(
        "plsql", {"mapping_package_prefix": "M_", "export_rule_functions": True}
    )
    assert backend.config["mapping_package_prefix"] == "M_"
    assert backend.config["export_rule_functions"] is True
    assert backend.config["fn_prefix"] == ""


def test_a_new_backend_module_is_picked_up_without_registration(
    fresh_registry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "fakeback").mkdir()
    (tmp_path / "fakeback" / "__init__.py").write_text("")
    (tmp_path / "fakeback" / "backend.py").write_text(FAKE_BACKEND)
    monkeypatch.setattr(backends_pkg, "__path__", [*backends_pkg.__path__, str(tmp_path)])
    cls = registry.backend_class("fake")
    assert cls.required_keys == ("out",)
    assert registry.create_backend("fake", {"out": "x"}).config == {"flavour": "plain", "out": "x"}


PROJECT_PLSQL = FAKE_BACKEND.replace('target = "fake"', 'target = "plsql"').replace(
    "FakeBackend", "MyPlsql"
)


def test_project_backends_folder_adds_and_overrides(
    fresh_registry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    mine = tmp_path / "compiler" / "backends"
    (mine / "fake").mkdir(parents=True)
    (mine / "fake" / "__init__.py").write_text("")
    (mine / "fake" / "backend.py").write_text(FAKE_BACKEND)
    (mine / "plsql_mine.py").write_text(PROJECT_PLSQL)
    monkeypatch.chdir(tmp_path)
    assert registry.backend_class("fake").required_keys == ("out",)
    assert registry.backend_class("plsql").__name__ == "MyPlsql"  # overrides the built-in


def test_engine_checkout_does_not_load_its_own_backends_twice(fresh_registry):
    assert (
        registry._project_dir() is None
    )  # cwd is the repo: its compiler/backends is the built-in one


def test_plsql_requires_schema_and_error_code():
    from compiler.backends.plsql.backend import PlsqlBackend

    assert PlsqlBackend.required_keys == ("schema", "error_code")
