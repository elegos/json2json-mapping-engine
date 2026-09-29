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
        return ""

    def artifact_path(self, compiled_dir: Path) -> Path:
        return compiled_dir / "out.txt"
"""


@pytest.fixture
def fresh_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(registry, "_registry", None)


def test_plsql_backend_is_discovered_by_its_target_name(fresh_registry):
    assert registry.backend_class("plsql") is PlsqlBackend
    assert "plsql" in registry.backends()


def test_unknown_target_is_an_error_listing_the_available_ones(fresh_registry):
    with pytest.raises(CodeGenError, match=r"unknown target 'nope'.*plsql"):
        registry.backend_class("nope")


def test_create_backend_merges_defaults_under_the_given_config(fresh_registry):
    backend = registry.create_backend("plsql", {"package": "PKG", "export_rule_functions": True})
    assert backend.config["package"] == "PKG"
    assert backend.config["export_rule_functions"] is True
    assert backend.config["fn_prefix"] == ""
    assert backend.artifact_path(Path("build/compiled")) == Path("build/compiled/pkg.sql")


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
