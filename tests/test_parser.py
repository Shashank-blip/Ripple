from textwrap import dedent

import pytest

from ripple.graph.parser import ImportRef, parse_file, parse_source


def imports_of(source: str):
    return parse_source(dedent(source).lstrip("\n")).imports


def test_plain_import():
    assert imports_of("import os") == (ImportRef(module="os", lineno=1),)


def test_multiple_modules_in_one_statement():
    refs = imports_of("import os, sys")
    assert [r.module for r in refs] == ["os", "sys"]


def test_alias_keeps_real_module_name():
    refs = imports_of("import numpy as np\nimport a.b.c as abc")
    assert [r.module for r in refs] == ["numpy", "a.b.c"]


def test_from_import_collects_names():
    (ref,) = imports_of("from pkg.mod import a, b as c")
    assert ref.module == "pkg.mod"
    assert ref.names == ("a", "b")
    assert ref.level == 0
    assert not ref.is_relative


@pytest.mark.parametrize(
    ("source", "module", "names", "level"),
    [
        ("from . import x", None, ("x",), 1),
        ("from .a import b", "a", ("b",), 1),
        ("from ..pkg.mod import c", "pkg.mod", ("c",), 2),
    ],
)
def test_relative_imports(source, module, names, level):
    (ref,) = imports_of(source)
    assert (ref.module, ref.names, ref.level) == (module, names, level)
    assert ref.is_relative


def test_star_import_is_flagged():
    (ref,) = imports_of("from pkg import *")
    assert ref.is_star


def test_imports_in_nested_scopes_are_included():
    refs = imports_of(
        """
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            import heavy
        try:
            import fast
        except ImportError:
            import slow
        def f():
            from lazy import thing
        """
    )
    assert {r.module for r in refs} == {"typing", "heavy", "fast", "slow", "lazy"}


def test_line_numbers_are_recorded():
    refs = imports_of("import os\n\nimport sys")
    assert [r.lineno for r in refs] == [1, 3]


@pytest.mark.parametrize(
    "source",
    [
        "importlib.import_module(name)",
        "__import__(name)",
        'importlib.import_module(".sibling", package)',
        'importlib.import_module("a." + suffix)',
        '__import__("x", globals(), locals(), [], 1)',
    ],
)
def test_unresolvable_dynamic_imports_mark_file_uncertain(source):
    result = parse_source(source)
    assert result.uncertain
    assert result.dynamic_import_lines


@pytest.mark.parametrize(
    "source",
    [
        'importlib.import_module("plugins.csv")',
        '__import__("plugins.csv")',
    ],
)
def test_literal_dynamic_import_becomes_normal_edge(source):
    result = parse_source(source)
    assert not result.uncertain
    assert [r.module for r in result.imports] == ["plugins.csv"]


@pytest.mark.parametrize("source", ["def broken(:\n", "import os\x00"])
def test_unparseable_source_is_uncertain_not_a_crash(source):
    result = parse_source(source)
    assert result.uncertain
    assert result.error
    assert result.imports == ()


def test_empty_source():
    result = parse_source("")
    assert result.imports == ()
    assert not result.uncertain


def test_parse_file_reads_source(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("import os\n", encoding="utf-8")
    assert [r.module for r in parse_file(f).imports] == ["os"]


def test_parse_file_honours_encoding_cookie(tmp_path):
    f = tmp_path / "m.py"
    f.write_bytes("# -*- coding: latin-1 -*-\nimport os\nx = 'é'\n".encode("latin-1"))
    assert [r.module for r in parse_file(f).imports] == ["os"]


def test_parse_file_missing_file_is_uncertain(tmp_path):
    result = parse_file(tmp_path / "nope.py")
    assert result.uncertain
    assert result.error