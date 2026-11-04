import json
from typing import Any

from datamodel_code_generator import DataModelType, PythonVersion
from datamodel_code_generator.format import Formatter
from datamodel_code_generator.model import get_data_model_types
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser
from pydantic import BaseModel
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer
from pygments.lexers import JsonLexer, PythonLexer, YamlLexer
import yaml

from schematalog.common import avroform

LEXERS: dict[str, type[Lexer]] = {
    "json": JsonLexer,
    "yaml": YamlLexer,
    "python": PythonLexer,
}
"""Lexers for the formats the detail page renders. Avro is JSON, so it reuses that one."""


def to_json(schema: Any) -> str:
    if isinstance(schema, BaseModel):
        schema = schema.model_dump(mode="json", by_alias=True)
    return json.dumps(schema, indent=2)


def to_yaml(schema: Any) -> str:
    if isinstance(schema, BaseModel):
        schema = schema.model_dump(mode="json", by_alias=True)
    return yaml.safe_dump(schema, indent=2)


def to_avro(schema: Any, namespace: str = "") -> str:
    if isinstance(schema, BaseModel):
        schema = schema.model_dump(mode="json", by_alias=True)
    name = schema.get("title") or "document"
    return to_json(avroform.to_avro(schema, name=name, namespace=namespace))


def to_pydantic(schema: Any) -> str:
    if isinstance(schema, BaseModel):
        schema = schema.model_dump(mode="json", by_alias=True)
    if isinstance(schema, dict) and "$id" in schema:
        # Drop the canonical `$id`: it is an absolute URL, and datamodel-code-generator
        # resolves internal `$ref`s against it as a *remote* base and fetches it - for our
        # own `$id` that re-enters this server and deadlocks it. Codegen does not need it.
        schema = schema.copy()
        del schema["$id"]
    data_model_types = get_data_model_types(
        DataModelType.PydanticV2BaseModel, target_python_version=PythonVersion.PY_311
    )
    parser = JsonSchemaParser(
        to_json(schema),
        data_model_type=data_model_types.data_model,
        data_model_root_type=data_model_types.root_model,
        data_model_field_type=data_model_types.field_model,
        data_type_manager_type=data_model_types.data_type_manager,
        dump_resolve_reference_action=data_model_types.dump_resolve_reference_action,
        # Pin the formatters: datamodel-code-generator warns when they're left to default.
        formatters=[Formatter.BLACK, Formatter.ISORT],
    )
    return str(parser.parse())


def highlight(code: str, language: str, anchor: str) -> str:
    """Render `code` as syntax-highlighted HTML, one `<span>` per line.

    The per-line spans exist so the stylesheet can number the lines with a CSS counter;
    numbering in markup would put the numbers into the DOM text, where the copy button
    would pick them up. `anchor` prefixes those span ids to keep them unique across the
    several code blocks a page renders.

    Args:
        code: The already-formatted source text.
        language: Which lexer to use; one of `LEXERS`.
        anchor: Per-block prefix for the generated line-span ids.

    Returns:
        HTML for the highlighted block. Pygments escapes the code it is given, so the
        result is safe to render unescaped.

    Raises:
        KeyError: If `language` is not a known lexer.
    """
    formatter = HtmlFormatter(nowrap=False, cssclass="hl", linespans=f"{anchor}-line")
    return pygments.highlight(code, LEXERS[language](), formatter)
