"""Tests for nova.code.parser.python_parser"""
import unittest

from nova.code.parser.python_parser import parse_python
from nova.code.parser.base import SymbolKind


class TestPythonParserClasses(unittest.TestCase):
    def test_simple_class(self):
        src = "class Foo:\n    pass\n"
        syms = parse_python("test.py", src)
        names = [s.name for s in syms]
        self.assertIn("Foo", names)
        cls = next(s for s in syms if s.name == "Foo")
        self.assertEqual(cls.kind, SymbolKind.CLASS)
        self.assertEqual(cls.line, 1)

    def test_model_class_detected(self):
        src = "class User(Base):\n    pass\n"
        syms = parse_python("models.py", src)
        user = next(s for s in syms if s.name == "User")
        self.assertEqual(user.kind, SymbolKind.MODEL)

    def test_pydantic_model(self):
        src = "class Item(BaseModel):\n    name: str\n"
        syms = parse_python("schema.py", src)
        item = next(s for s in syms if s.name == "Item")
        self.assertEqual(item.kind, SymbolKind.MODEL)

    def test_nested_class(self):
        src = "class Outer:\n    class Inner:\n        pass\n"
        syms = parse_python("t.py", src)
        names = {s.name for s in syms}
        self.assertIn("Inner", names)

    def test_class_docstring(self):
        src = 'class Foo:\n    """My docstring."""\n    pass\n'
        syms = parse_python("t.py", src)
        foo = next(s for s in syms if s.name == "Foo")
        self.assertIn("My docstring", foo.docstring)


class TestPythonParserFunctions(unittest.TestCase):
    def test_simple_function(self):
        src = "def greet(name):\n    return name\n"
        syms = parse_python("t.py", src)
        greet = next(s for s in syms if s.name == "greet")
        self.assertEqual(greet.kind, SymbolKind.FUNCTION)

    def test_async_function(self):
        src = "async def fetch(url):\n    pass\n"
        syms = parse_python("t.py", src)
        fetch = next(s for s in syms if s.name == "fetch")
        self.assertEqual(fetch.kind, SymbolKind.ASYNC_FUNCTION)

    def test_method_inside_class(self):
        src = "class Foo:\n    def bar(self):\n        pass\n"
        syms = parse_python("t.py", src)
        bar = next(s for s in syms if s.name == "bar")
        self.assertEqual(bar.kind, SymbolKind.METHOD)
        self.assertEqual(bar.parent, "Foo")

    def test_async_method(self):
        src = "class Foo:\n    async def bar(self):\n        pass\n"
        syms = parse_python("t.py", src)
        bar = next(s for s in syms if s.name == "bar")
        self.assertEqual(bar.kind, SymbolKind.ASYNC_METHOD)

    def test_function_signature(self):
        src = "def add(a, b):\n    return a + b\n"
        syms = parse_python("t.py", src)
        add = next(s for s in syms if s.name == "add")
        self.assertIn("add", add.signature)

    def test_call_extraction(self):
        src = "def foo():\n    bar()\n    baz()\n"
        syms = parse_python("t.py", src)
        foo = next(s for s in syms if s.name == "foo")
        self.assertIn("bar", foo.calls)
        self.assertIn("baz", foo.calls)


class TestPythonParserRoutes(unittest.TestCase):
    def test_flask_route(self):
        src = (
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/users')\ndef list_users():\n    pass\n"
        )
        syms = parse_python("views.py", src)
        route = next((s for s in syms if s.name == "list_users"), None)
        self.assertIsNotNone(route)
        self.assertEqual(route.kind, SymbolKind.ROUTE)
        self.assertEqual(route.metadata.get("path"), "/users")

    def test_fastapi_route(self):
        src = (
            "@router.get('/items')\nasync def get_items():\n    pass\n"
        )
        syms = parse_python("routes.py", src)
        route = next((s for s in syms if s.name == "get_items"), None)
        self.assertIsNotNone(route)
        self.assertEqual(route.kind, SymbolKind.ROUTE)
        self.assertEqual(route.metadata.get("http_method"), "GET")

    def test_flask_methods(self):
        src = (
            "@app.route('/login', methods=['GET', 'POST'])\n"
            "def login():\n    pass\n"
        )
        syms = parse_python("views.py", src)
        route = next((s for s in syms if s.name == "login"), None)
        self.assertIsNotNone(route)
        self.assertIn("GET", route.metadata.get("http_methods", []))


class TestPythonParserConstants(unittest.TestCase):
    def test_constant_uppercase(self):
        src = "MAX_RETRIES = 3\n"
        syms = parse_python("config.py", src)
        c = next((s for s in syms if s.name == "MAX_RETRIES"), None)
        self.assertIsNotNone(c)
        self.assertEqual(c.kind, SymbolKind.CONSTANT)

    def test_variable_lowercase(self):
        src = "my_var = 42\n"
        syms = parse_python("t.py", src)
        v = next((s for s in syms if s.name == "my_var"), None)
        # lowercase short names are variables
        if v:
            self.assertEqual(v.kind, SymbolKind.VARIABLE)

    def test_syntax_error_returns_empty(self):
        src = "def broken(\n"
        syms = parse_python("bad.py", src)
        self.assertEqual(syms, [])
