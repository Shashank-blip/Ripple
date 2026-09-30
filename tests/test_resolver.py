from textwrap import dedent

import pytest

from ripple.graph.parser import parse_source
from ripple.graph.resolver import ModuleIndex, resolve_file

PATHS = [
    "pkg/__init__.py",
    "pkg/a.py",
    "pkg/sub/__init__.py",
    "pkg/sub/b.py",
    "pkg/sub/c.py",
    "app.py",
    "tests/test_a.py",
    "src/lib/__init__.py",
    "src/lib/core.py",
    "ns/inner/mod.py",  # namespace package: no __init__.py
    "scripts/my-tool.py",  # not importable as a module
]

PKG_INIT = "pkg/__init__.py"
SUB_INIT = "pkg/sub/__init__.py"


@pytest.fixture(scope="module")
def index():
    return ModuleIndex.from_paths(PATHS, source_roots=(".", "src"))


def resolve(index, path, source):
    return resolve_file(index, path, parse_source(dedent(source)))


def targets(index, path, source):
    return set(resolve(index, path, source).targets)


# --- module naming -------------------------------------------------------------


def test_module_names(index):
    assert index.file_modules["pkg/sub/b.py"] == "pkg.sub.b"
    assert index.file_modules[SUB_INIT] == "pkg.sub"
    assert index.file_modules["src/lib/core.py"] == "lib.core"  # deepest root wins
    assert "scripts/my-tool.py" not in index.file_modules


def test_package_beats_module_with_same_name():
    idx = ModuleIndex.from_paths(["a.py", "a/__init__.py"])
    assert idx.modules["a"] == "a/__init__.py"


# --- absolute imports ----------------------------------------------------------


def test_absolute_import_depends_on_every_prefix(index):
    assert targets(index, "app.py", "import pkg.sub.b") == {PKG_INIT, SUB_INIT, "pkg/sub/b.py"}


def test_from_import_of_submodule_adds_the_submodule(index):
    assert targets(index, "app.py", "from pkg import a") == {PKG_INIT, "pkg/a.py"}


def test_from_import_of_attribute_depends_on_package_only(index):
    assert targets(index, "app.py", "from pkg import something") == {PKG_INIT}


def test_import_from_src_layout(index):
    assert targets(index, "app.py", "import lib.core") == {"src/lib/__init__.py", "src/lib/core.py"}


def test_star_import_includes_direct_submodules(index):
    assert targets(index, "app.py", "from pkg.sub import *") == {
        PKG_INIT,
        SUB_INIT,
        "pkg/sub/b.py",
        "pkg/sub/c.py",
    }


def test_namespace_package_import(index):
    result = resolve(index, "app.py", "import ns.inner.mod")
    assert set(result.targets) == {"ns/inner/mod.py"}
    assert not result.uncertain
    assert not resolve(index, "app.py", "import ns.inner").uncertain


# --- relative imports ----------------------------------------------------------


def test_relative_from_dot_import_sibling(index):
    assert targets(index, "pkg/sub/b.py", "from . import c") == {PKG_INIT, SUB_INIT, "pkg/sub/c.py"}


def test_relative_from_dot_module(index):
    assert targets(index, "pkg/sub/b.py", "from .c import thing") == {
        PKG_INIT,
        SUB_INIT,
        "pkg/sub/c.py",
    }


def test_relative_parent_package(index):
    assert targets(index, "pkg/sub/b.py", "from .. import a") == {PKG_INIT, SUB_INIT, "pkg/a.py"}
    assert targets(index, "pkg/sub/b.py", "from ..a import x") == {PKG_INIT, SUB_INIT, "pkg/a.py"}


def test_relative_import_inside_init_ignores_self(index):
    # in pkg/sub/__init__.py, "." means pkg.sub itself; the self-edge must be dropped
    assert targets(index, SUB_INIT, "from . import b") == {PKG_INIT, "pkg/sub/b.py"}
    assert targets(index, SUB_INIT, "from .b import thing") == {PKG_INIT, "pkg/sub/b.py"}


def test_relative_import_past_top_level_is_unresolved(index):
    result = resolve(index, "pkg/a.py", "from ... import x")
    assert result.uncertain
    assert len(result.unresolved) == 1


def test_relative_import_in_top_level_module_is_unresolved(index):
    assert resolve(index, "app.py", "from . import x").uncertain


# --- implicit edges ------------------------------------------------------------


def test_module_implicitly_depends_on_parent_package_inits(index):
    result = resolve(index, "pkg/sub/b.py", "x = 1")
    assert set(result.targets) == {PKG_INIT, SUB_INIT}
    assert not result.uncertain


# --- external vs unresolved ----------------------------------------------------


def test_external_imports_are_ignored_and_certain(index):
    result = resolve(index, "app.py", "import os, requests\nfrom numpy import array")
    assert set(result.targets) == set()
    assert not result.uncertain


def test_missing_module_inside_our_package_is_unresolved(index):
    result = resolve(index, "app.py", "import pkg.missing")
    assert set(result.targets) == {PKG_INIT}
    assert result.uncertain
    assert [r.module for r in result.unresolved] == ["pkg.missing"]
    assert resolve(index, "app.py", "from pkg.missing import x").uncertain


# --- files that aren't importable modules --------------------------------------


def test_non_importable_file_can_still_have_absolute_edges(index):
    assert targets(index, "scripts/my-tool.py", "import pkg.a") == {PKG_INIT, "pkg/a.py"}
    assert resolve(index, "scripts/my-tool.py", "from . import x").uncertain


# --- uncertainty propagation ---------------------------------------------------


def test_parse_uncertainty_propagates(index):
    assert resolve(index, "app.py", "def broken(:").uncertain
    assert resolve(index, "app.py", "importlib.import_module(name)").uncertain


# --- sys.path aliases (formerly the known hole) --------------------------------


def test_sibling_import_in_init_less_test_dir():
    idx = ModuleIndex.from_paths(["tests/test_a.py", "tests/helpers.py"])
    assert "tests/helpers.py" in resolve(idx, "tests/test_a.py", "import helpers").targets


def test_nested_dirs_under_init_less_root_are_importable():
    idx = ModuleIndex.from_paths(["tests/unit/test_x.py", "tests/unit/sub/mod.py"])
    assert targets(idx, "tests/unit/test_x.py", "import sub.mod") == {"tests/unit/sub/mod.py"}


def test_src_layout_needs_no_configuration():
    idx = ModuleIndex.from_paths(["src/lib/__init__.py", "src/lib/core.py", "app.py"])
    assert targets(idx, "app.py", "import lib.core") == {
        "src/lib/__init__.py",
        "src/lib/core.py",
    }


def test_aliases_never_shadow_real_module_names():
    idx = ModuleIndex.from_paths(["helpers.py", "tests/helpers.py"])
    assert idx.modules["helpers"] == "helpers.py"