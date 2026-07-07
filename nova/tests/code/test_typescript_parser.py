"""Tests for nova.code.parser.typescript_parser"""
import unittest

from nova.code.parser.typescript_parser import parse_typescript
from nova.code.parser.base import SymbolKind


class TestTypeScriptParserClasses(unittest.TestCase):
    def test_class_declaration(self):
        src = "class AuthService {\n  login() {}\n}\n"
        syms = parse_typescript("auth.ts", src)
        cls = next((s for s in syms if s.name == "AuthService"), None)
        self.assertIsNotNone(cls)
        self.assertEqual(cls.kind, SymbolKind.CLASS)

    def test_export_class(self):
        src = "export class UserController {}\n"
        syms = parse_typescript("ctrl.ts", src)
        cls = next((s for s in syms if s.name == "UserController"), None)
        self.assertIsNotNone(cls)

    def test_abstract_class(self):
        src = "abstract class BaseRepo {}\n"
        syms = parse_typescript("repo.ts", src)
        cls = next((s for s in syms if s.name == "BaseRepo"), None)
        self.assertIsNotNone(cls)


class TestTypeScriptParserInterfaces(unittest.TestCase):
    def test_interface(self):
        src = "interface AuthResponse {\n  token: string;\n}\n"
        syms = parse_typescript("types.ts", src)
        iface = next((s for s in syms if s.name == "AuthResponse"), None)
        self.assertIsNotNone(iface)
        self.assertEqual(iface.kind, SymbolKind.INTERFACE)

    def test_type_alias(self):
        src = "type UserId = string;\n"
        syms = parse_typescript("types.ts", src)
        ta = next((s for s in syms if s.name == "UserId"), None)
        self.assertIsNotNone(ta)
        self.assertEqual(ta.kind, SymbolKind.TYPE_ALIAS)

    def test_enum(self):
        src = "enum Status { Active, Inactive }\n"
        syms = parse_typescript("enums.ts", src)
        e = next((s for s in syms if s.name == "Status"), None)
        self.assertIsNotNone(e)
        self.assertEqual(e.kind, SymbolKind.ENUM)


class TestTypeScriptParserFunctions(unittest.TestCase):
    def test_named_function(self):
        src = "function fetchUser(id: string) {}\n"
        syms = parse_typescript("api.ts", src)
        fn = next((s for s in syms if s.name == "fetchUser"), None)
        self.assertIsNotNone(fn)
        self.assertEqual(fn.kind, SymbolKind.FUNCTION)

    def test_async_arrow_function(self):
        src = "const getData = async (url) => { return fetch(url); };\n"
        syms = parse_typescript("utils.ts", src)
        fn = next((s for s in syms if s.name == "getData"), None)
        self.assertIsNotNone(fn)
        self.assertEqual(fn.kind, SymbolKind.ASYNC_FUNCTION)

    def test_export_default_handler(self):
        src = "export default function handler(req, res) {}\n"
        syms = parse_typescript("pages/api/users.ts", src)
        h = next((s for s in syms if s.name == "handler"), None)
        self.assertIsNotNone(h)
        # handler is detected as a route
        self.assertEqual(h.kind, SymbolKind.ROUTE)


class TestTypeScriptParserComponents(unittest.TestCase):
    def test_react_component_function(self):
        src = "function LoginPage() { return <div/>; }\n"
        syms = parse_typescript("Login.tsx", src)
        comp = next((s for s in syms if s.name == "LoginPage"), None)
        self.assertIsNotNone(comp)
        self.assertEqual(comp.kind, SymbolKind.COMPONENT)

    def test_react_component_arrow(self):
        src = "const Dashboard = () => <div>Hello</div>;\n"
        syms = parse_typescript("Dashboard.tsx", src)
        comp = next((s for s in syms if s.name == "Dashboard"), None)
        self.assertIsNotNone(comp)
        self.assertEqual(comp.kind, SymbolKind.COMPONENT)

    def test_react_hook(self):
        src = "const useAuth = () => { return {}; };\n"
        syms = parse_typescript("hooks.ts", src)
        hook = next((s for s in syms if s.name == "useAuth"), None)
        self.assertIsNotNone(hook)
        self.assertEqual(hook.kind, SymbolKind.HOOK)

    def test_named_hook_function(self):
        src = "function useTheme() { return {}; }\n"
        syms = parse_typescript("hooks.ts", src)
        hook = next((s for s in syms if s.name == "useTheme"), None)
        self.assertIsNotNone(hook)
        self.assertEqual(hook.kind, SymbolKind.HOOK)


class TestTypeScriptParserRoutes(unittest.TestCase):
    def test_express_get(self):
        src = "app.get('/users', (req, res) => {});\n"
        syms = parse_typescript("server.ts", src)
        route = next((s for s in syms if "GET" in s.name), None)
        self.assertIsNotNone(route)
        self.assertEqual(route.kind, SymbolKind.ROUTE)
        self.assertEqual(route.metadata.get("path"), "/users")

    def test_router_post(self):
        src = "router.post('/login', authController.login);\n"
        syms = parse_typescript("routes.ts", src)
        route = next((s for s in syms if "POST" in s.name), None)
        self.assertIsNotNone(route)
        self.assertEqual(route.metadata.get("http_method"), "POST")

    def test_multiple_routes(self):
        src = (
            "router.get('/a', h1);\n"
            "router.post('/b', h2);\n"
            "router.delete('/c', h3);\n"
        )
        syms = parse_typescript("routes.ts", src)
        routes = [s for s in syms if s.kind == SymbolKind.ROUTE]
        self.assertEqual(len(routes), 3)


class TestTypeScriptParserConstants(unittest.TestCase):
    def test_all_caps_constant(self):
        src = "const API_URL = 'https://api.example.com';\n"
        syms = parse_typescript("config.ts", src)
        c = next((s for s in syms if s.name == "API_URL"), None)
        self.assertIsNotNone(c)
        self.assertEqual(c.kind, SymbolKind.CONSTANT)

    def test_empty_file(self):
        syms = parse_typescript("empty.ts", "")
        self.assertEqual(syms, [])
