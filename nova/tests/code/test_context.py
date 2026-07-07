"""Tests for nova.code.context (CodeContext query API)"""
import threading
import unittest

from nova.code.context import CodeContext
from nova.code.parser.base import CallEdge, Symbol, SymbolKind


def _sym(name, kind=SymbolKind.FUNCTION, file="a.py", line=1, parent=None,
          calls=None, metadata=None):
    return Symbol(name=name, kind=kind, file=file, line=line, end_line=line+5,
                  parent=parent, calls=calls or [], metadata=metadata or {})


class TestCodeContextFindSymbol(unittest.TestCase):
    def setUp(self):
        self.ctx = CodeContext()
        syms = [
            _sym("WorkingMemory", kind=SymbolKind.CLASS, file="core/memory.py"),
            _sym("SessionState", kind=SymbolKind.CLASS, file="core/memory.py"),
            _sym("run_voice_loop", kind=SymbolKind.FUNCTION, file="voice/pipeline.py"),
        ]
        for s in syms:
            self.ctx._add_symbols(s.file, [s])

    def test_find_by_name(self):
        hits = self.ctx.find_symbol("WorkingMemory")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].kind, SymbolKind.CLASS)

    def test_find_by_name_and_kind(self):
        hits = self.ctx.find_symbol("WorkingMemory", kind=SymbolKind.FUNCTION)
        self.assertEqual(hits, [])

    def test_missing_name_returns_empty(self):
        self.assertEqual(self.ctx.find_symbol("NonExistent"), [])

    def test_case_sensitive(self):
        self.assertEqual(self.ctx.find_symbol("workingmemory"), [])


class TestCodeContextSearch(unittest.TestCase):
    def setUp(self):
        self.ctx = CodeContext()
        self.ctx._add_symbols("a.py", [
            _sym("AuthService", kind=SymbolKind.CLASS),
            _sym("authMiddleware", kind=SymbolKind.FUNCTION),
            _sym("getUser", kind=SymbolKind.FUNCTION),
        ])

    def test_substring_match(self):
        results = self.ctx.search("auth")
        names = [s.name for s in results]
        self.assertIn("AuthService", names)
        self.assertIn("authMiddleware", names)

    def test_no_match(self):
        results = self.ctx.search("zzz")
        self.assertEqual(results, [])

    def test_limit_respected(self):
        ctx = CodeContext()
        ctx._add_symbols("a.py", [_sym(f"fooBar{i}") for i in range(50)])
        results = ctx.search("foo", limit=10)
        self.assertLessEqual(len(results), 10)

    def test_search_by_pattern(self):
        results = self.ctx.search_by_pattern("auth*")
        names = [s.name for s in results]
        self.assertIn("authMiddleware", names)


class TestCodeContextRoutes(unittest.TestCase):
    def setUp(self):
        self.ctx = CodeContext()
        self.ctx._add_symbols("views.py", [
            _sym("list_users", kind=SymbolKind.ROUTE,
                 metadata={"http_method": "GET", "path": "/users"}),
            _sym("create_user", kind=SymbolKind.ROUTE,
                 metadata={"http_method": "POST", "path": "/users"}),
        ])
        self.ctx._add_symbols("other.py", [_sym("helper")])

    def test_find_all_routes(self):
        routes = self.ctx.find_routes()
        self.assertEqual(len(routes), 2)

    def test_filter_by_method(self):
        gets = self.ctx.find_routes(method="GET")
        self.assertEqual(len(gets), 1)
        self.assertEqual(gets[0].name, "list_users")

    def test_filter_post(self):
        posts = self.ctx.find_routes(method="POST")
        self.assertEqual(len(posts), 1)


class TestCodeContextComponents(unittest.TestCase):
    def test_find_components(self):
        ctx = CodeContext()
        ctx._add_symbols("Login.tsx", [
            _sym("LoginPage", kind=SymbolKind.COMPONENT),
            _sym("Header", kind=SymbolKind.COMPONENT),
        ])
        comps = ctx.find_components()
        self.assertEqual(len(comps), 2)

    def test_find_hooks(self):
        ctx = CodeContext()
        ctx._add_symbols("hooks.ts", [
            _sym("useAuth", kind=SymbolKind.HOOK),
            _sym("useTheme", kind=SymbolKind.HOOK),
        ])
        hooks = ctx.find_hooks()
        self.assertEqual(len(hooks), 2)

    def test_find_models(self):
        ctx = CodeContext()
        ctx._add_symbols("models.py", [
            _sym("User", kind=SymbolKind.MODEL),
            _sym("Order", kind=SymbolKind.MODEL),
        ])
        models = ctx.find_models()
        names = [m.name for m in models]
        self.assertIn("User", names)
        self.assertIn("Order", names)


class TestCodeContextCallers(unittest.TestCase):
    def test_find_callers(self):
        ctx = CodeContext()
        sym = _sym("process", calls=["validate"])
        ctx._add_symbols("a.py", [sym])
        # Manually inject a call edge
        edge = CallEdge(caller_file="a.py", caller_name="process",
                        caller_line=1, callee_name="validate")
        ctx.call_graph["a.py:process"] = [edge]

        callers = ctx.find_callers("validate")
        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0].caller_name, "process")

    def test_find_references(self):
        ctx = CodeContext()
        caller = _sym("main", calls=["helper"])
        target = _sym("helper")
        ctx._add_symbols("a.py", [caller, target])

        refs = ctx.find_references("helper")
        self.assertTrue(any(r.name == "main" for r in refs))


class TestCodeContextFileMutations(unittest.TestCase):
    def test_remove_file(self):
        ctx = CodeContext()
        ctx._add_symbols("a.py", [_sym("foo"), _sym("bar")])
        ctx._remove_file("a.py")
        self.assertEqual(ctx.find_symbol("foo"), [])
        self.assertEqual(ctx.find_symbol("bar"), [])

    def test_replace_file(self):
        ctx = CodeContext()
        ctx._add_symbols("a.py", [_sym("old")])
        ctx._replace_file("a.py", [_sym("new", file="a.py")], [])
        self.assertEqual(ctx.find_symbol("old"), [])
        self.assertGreater(len(ctx.find_symbol("new")), 0)

    def test_symbols_in_file(self):
        ctx = CodeContext()
        ctx._add_symbols("core/memory.py", [_sym("WorkingMemory", file="core/memory.py")])
        syms = ctx.symbols_in_file("core/memory.py")
        self.assertEqual(len(syms), 1)

    def test_stats(self):
        ctx = CodeContext()
        ctx._add_symbols("a.py", [_sym("foo")])
        s = ctx.stats()
        self.assertEqual(s["total_symbols"], 1)
        self.assertEqual(s["total_files"], 1)


class TestCodeContextThreadSafety(unittest.TestCase):
    def test_concurrent_reads(self):
        ctx = CodeContext()
        ctx._add_symbols("a.py", [_sym("foo")])
        errors = []

        def read():
            try:
                for _ in range(100):
                    ctx.find_symbol("foo")
                    ctx.search("f")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
