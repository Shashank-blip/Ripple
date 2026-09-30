from ripple.graph.builder import build_graph, discover_python_files


def test_discovery_skips_environments_and_caches(make_tree):
    root = make_tree(
        {
            "app.py": "",
            "pkg/a.py": "",
            "pkg/notes.txt": "",
            "venv/lib/site.py": "",
            ".venv/lib/site.py": "",
            ".git/hooks/hook.py": "",
            "node_modules/x/y.py": "",
            "pkg/__pycache__/junk.py": "",
            "weird_env/pyvenv.cfg": "",  # a virtualenv with an unusual name
            "weird_env/lib/mod.py": "",
            "thing.egg-info/setup.py": "",
        }
    )
    assert discover_python_files(root) == ["app.py", "pkg/a.py"]


def test_end_to_end_edges_and_reverse_index(make_tree):
    root = make_tree(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from . import b\n",
            "pkg/b.py": "import os\n",
            "tests/test_a.py": "from pkg import a\n",
        }
    )
    g = build_graph(root)
    assert g.edges["pkg/a.py"] == {"pkg/__init__.py", "pkg/b.py"}
    assert g.edges["pkg/b.py"] == {"pkg/__init__.py"}
    assert g.edges["tests/test_a.py"] == {"pkg/__init__.py", "pkg/a.py"}
    assert g.edges["pkg/__init__.py"] == frozenset()
    assert g.reverse["pkg/__init__.py"] == {"pkg/a.py", "pkg/b.py", "tests/test_a.py"}
    assert not g.uncertain


def test_uncertain_files_carry_reasons(make_tree):
    root = make_tree(
        {
            "pkg/__init__.py": "",
            "dyn.py": "import importlib\nimportlib.import_module(name)\n",
            "bad.py": "def broken(:\n",
            "missing.py": "import pkg.nope\n",
            "fine.py": "import pkg\n",
        }
    )
    g = build_graph(root)
    assert set(g.uncertain) == {"dyn.py", "bad.py", "missing.py"}
    assert any("dynamic" in r for r in g.uncertain["dyn.py"])
    assert any("could not parse" in r for r in g.uncertain["bad.py"])
    assert any("pkg.nope" in r for r in g.uncertain["missing.py"])


def test_src_layout_is_detected_without_config(make_tree):
    root = make_tree(
        {
            "src/lib/__init__.py": "",
            "src/lib/core.py": "def f(): ...\n",
            "tests/test_core.py": "from lib.core import f\n",
        }
    )
    g = build_graph(root)
    assert "src/lib/core.py" in g.edges["tests/test_core.py"]
    assert g.reverse["src/lib/core.py"] == frozenset({"tests/test_core.py"})


def test_empty_repo(make_tree):
    g = build_graph(make_tree({}))
    assert g.files == frozenset()