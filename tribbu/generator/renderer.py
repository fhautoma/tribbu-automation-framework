"""Jinja2 renderer — turns PageSpec / TestFileSpec into Python source code."""
from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

from tribbu.generator.page_builder import PageSpec
from tribbu.generator.test_builder import TestFileSpec

_env = Environment(
    loader=PackageLoader("tribbu.generator", "templates"),
    autoescape=select_autoescape([]),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_page(spec: PageSpec) -> str:
    """Render a Page Object source file from *spec*."""
    return _env.get_template("page_object.py.j2").render(
        screen_name=spec.screen_name,
        class_name=spec.class_name,
        platforms=spec.platforms,
        methods=spec.methods,
    )


def render_test(spec: TestFileSpec) -> str:
    """Render a test file source from *spec*."""
    return _env.get_template("test_case.py.j2").render(
        suite_name=spec.suite_name,
        class_name=spec.class_name,
        page_imports=spec.page_imports,
        needs_requests=spec.needs_requests,
        needs_faker=spec.needs_faker,
        tests=spec.tests,
    )
