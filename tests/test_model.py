from ripple.graph.model import Graph


def test_reverse_index_is_built_from_edges():
    g = Graph.from_edges({"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": set()})
    assert g.reverse["b.py"] == frozenset({"a.py"})
    assert g.reverse["c.py"] == frozenset({"b.py"})
    assert g.reverse["a.py"] == frozenset()


def test_cycles_are_fine():
    g = Graph.from_edges({"a.py": {"b.py"}, "b.py": {"a.py"}})
    assert g.reverse["a.py"] == frozenset({"b.py"})
    assert g.reverse["b.py"] == frozenset({"a.py"})


def test_files_are_the_edge_keys():
    g = Graph.from_edges({"a.py": {"b.py"}, "b.py": set()})
    assert g.files == frozenset({"a.py", "b.py"})


def test_uncertainty_reasons_are_kept():
    g = Graph.from_edges({"a.py": set()}, {"a.py": ["boom"]})
    assert g.uncertain == {"a.py": ("boom",)}


def test_json_dict_is_sorted_and_skips_empty_edge_lists():
    data = Graph.from_edges({"b.py": {"a.py"}, "a.py": set()}).to_json_dict()
    assert data["files"] == ["a.py", "b.py"]
    assert data["edges"] == {"b.py": ["a.py"]}
    assert data["uncertain"] == {}