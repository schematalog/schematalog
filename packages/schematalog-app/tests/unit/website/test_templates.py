from datetime import UTC, datetime
import json

import pytest
import yaml

from schematalog.app.presentation.webapp.templates import (
    datetime_filter,
    json_filter,
    yaml_filter,
)


@pytest.mark.parametrize(
    "data", ({"foo": {"bar": [1, 2, 3], "baz": "bam"}}, [1, 2, "3", 4]), ids=("dict", "list")
)
def test_json_filter_converts_string(data):
    json_data = json.dumps(data)

    assert json_filter(json_data) == json.dumps(data, indent=2)


@pytest.mark.parametrize(
    "data",
    ({"foo": {"bar": [1, 2, 3], "baz": "bam"}}, [1, 2, "3", 4], 1, "foo", 12.34),
    ids=("dict", "list", "int", "str", "float"),
)
def test_json_filter_converts_data(data):
    assert json_filter(data) == json.dumps(data, indent=2)


@pytest.mark.parametrize(
    "data", ({"foo": {"bar": [1, 2, 3], "baz": "bam"}}, [1, 2, "3", 4]), ids=("dict", "list")
)
def test_yaml_filter_converts_string(data):
    json_data = json.dumps(data)

    assert yaml_filter(json_data) == yaml.safe_dump(data)


@pytest.mark.parametrize(
    "data",
    ({"foo": {"bar": [1, 2, 3], "baz": "bam"}}, [1, 2, "3", 4], 1, "foo", 12.34),
    ids=("dict", "list", "int", "str", "float"),
)
def test_yaml_filter_converts_data(data):
    assert yaml_filter(data) == yaml.safe_dump(data)


def test_datetime_filter_converts_iso_string():
    data = "2008-05-05T11:45:00"
    expected = "05 May 2008 11:45"

    assert datetime_filter(data) == expected


def test_datetime_filter_converts_datetime_object():
    data = datetime(2002, 5, 22, 16, tzinfo=UTC)
    expected = "22 May 2002 16:00"

    assert datetime_filter(data) == expected


def test_templates_autoescape_html():
    """Regression: the `.jinja` extension defeats Starlette's `select_autoescape`.

    Starlette builds the env with `select_autoescape(["html", "xml"])`, which decides
    by file extension - so every `*.html.jinja` template here rendered unescaped until
    autoescaping was forced on. These templates interpolate user-controlled strings,
    so this must stay true.
    """
    from schematalog.app.presentation.webapp.templates import templates

    assert templates.env.autoescape is True
    rendered = templates.env.from_string("{{ value }}").render(value="<script>x</script>")
    assert rendered == "&lt;script&gt;x&lt;/script&gt;"
