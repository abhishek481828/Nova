"""Tests for nova.code.call_graph"""
import unittest

from nova.code.call_graph import build_call_graph, build_edges_for_file
from nova.code.parser.base import Symbol, SymbolKind


def _make_sym(name, calls=None, file="a.py", parent=None):
    return Symbol(
        name=name, kind=SymbolKind.FUNCTION, file=file, line=1, end_line=5,
        parent=parent, calls=calls or [],
    )


class TestBuildEdgesForFile(unittest.TestCase):
    def test_basic_call_edge(self):
        syms = [_make_sym("foo", calls=["bar"]), _make_sym("bar")]
        edges = build_edges_for_file("a.py", syms, {"foo", "bar"})
        callee_names = [e.callee_name for e in edges]
        self.assertIn("bar", callee_names)

    def test_self_call_excluded(self):
        syms = [_make_sym("foo", calls=["foo"])]
        edges = build_edges_for_file("a.py", syms, {"foo"})
        self.assertEqual(edges, [])

    def test_caller_key(self):
        syms = [_make_sym("foo", calls=["bar"])]
        edges = build_edges_for_file("a.py", syms, {"foo", "bar"})
        self.assertEqual(edges[0].caller_key, "a.py:foo")

    def test_empty_calls(self):
        syms = [_make_sym("foo", calls=[])]
        edges = build_edges_for_file("a.py", syms, {"foo"})
        self.assertEqual(edges, [])

    def test_qualified_caller_name(self):
        syms = [_make_sym("bar", calls=["baz"], parent="MyClass")]
        edges = build_edges_for_file("a.py", syms, {"baz"})
        self.assertEqual(edges[0].caller_name, "MyClass.bar")

    def test_caller_line_recorded(self):
        sym = Symbol(name="foo", kind=SymbolKind.FUNCTION, file="a.py",
                     line=42, end_line=50, calls=["bar"])
        edges = build_edges_for_file("a.py", [sym], {"bar"})
        self.assertEqual(edges[0].caller_line, 42)


class TestBuildCallGraph(unittest.TestCase):
    def test_cross_file_edges(self):
        file_symbols = {
            "a.py": [_make_sym("process", calls=["validate"], file="a.py")],
            "b.py": [_make_sym("validate", calls=[], file="b.py")],
        }
        graph = build_call_graph(file_symbols)
        all_callee_names = [
            e.callee_name
            for edges in graph.values()
            for e in edges
        ]
        self.assertIn("validate", all_callee_names)

    def test_empty_project(self):
        graph = build_call_graph({})
        self.assertEqual(graph, {})

    def test_no_calls(self):
        file_symbols = {
            "a.py": [_make_sym("foo", calls=[]), _make_sym("bar", calls=[])],
        }
        graph = build_call_graph(file_symbols)
        self.assertEqual(graph, {})

    def test_multiple_callees(self):
        syms = [_make_sym("main", calls=["helper", "cleanup", "init"])]
        graph = build_call_graph({"a.py": syms})
        all_callees = [e.callee_name for edges in graph.values() for e in edges]
        for name in ["helper", "cleanup", "init"]:
            self.assertIn(name, all_callees)
