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
from schematalog.common.logging import get_logger

log = get_logger(__name__)

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


class PydanticGenerationError(Exception):
    """Pydantic models could not be generated from a schema; the message is safe to show."""


# Keywords the generator resolves by opening whatever they name: a path or a URL.
_REFERENCE_KEYWORDS = frozenset({"$ref", "$dynamicRef", "$recursiveRef"})


def _has_outside_reference(node: Any) -> bool:
    """Tell whether a schema refers to anything outside its own document.

    Args:
        node: The schema, or a part of it.

    Returns:
        Whether a reference anywhere in it does not start with `#`.
    """
    if isinstance(node, list):
        return any(_has_outside_reference(item) for item in node)
    if not isinstance(node, dict):
        return False
    return any(
        (key in _REFERENCE_KEYWORDS and isinstance(value, str) and not value.startswith("#"))
        or _has_outside_reference(value)
        for key, value in node.items()
    )


def to_pydantic(schema: Any) -> str:
    """Generate Pydantic v2 model source from a JSON Schema, for Python 3.14.

    A schema that refers to itself or forms a cycle relies on 3.14's deferred annotations,
    so that output raises `NameError` on older versions.

    The generator is written for trusted local files and follows a reference by opening it.
    A schema comes from whoever published it, so one referring outside its own document is
    refused rather than letting them read the server's files or make it fetch a URL.

    Args:
        schema: The schema, as a mapping or a model of one.

    Returns:
        The source code of the models.

    Raises:
        PydanticGenerationError: If the schema refers outside its own document, or the
            generator cannot handle it.
    """
    if isinstance(schema, BaseModel):
        schema = schema.model_dump(mode="json", by_alias=True)
    if isinstance(schema, dict) and "$id" in schema:
        # Drop the canonical `$id`: it is an absolute URL, and datamodel-code-generator
        # resolves internal `$ref`s against it as a *remote* base and fetches it - for our
        # own `$id` that re-enters this server and deadlocks it. Codegen does not need it.
        schema = schema.copy()
        del schema["$id"]
    if _has_outside_reference(schema):
        raise PydanticGenerationError(  # noqa: TRY003
            "it refers to something outside its own document"
        )
    data_model_types = get_data_model_types(
        DataModelType.PydanticV2BaseModel, target_python_version=PythonVersion.PY_314
    )
    try:
        parser = JsonSchemaParser(
            to_json(schema),
            data_model_type=data_model_types.data_model,
            data_model_root_type=data_model_types.root_model,
            data_model_field_type=data_model_types.field_model,
            data_type_manager_type=data_model_types.data_type_manager,
            dump_resolve_reference_action=data_model_types.dump_resolve_reference_action,
            target_python_version=PythonVersion.PY_314,
            use_union_operator=True,
            use_standard_collections=True,
            formatters=[Formatter.BUILTIN],
        )
        generated = parser.parse(disable_future_imports=True)
    # The generator raises many unrelated types, and any of them only costs one tab.
    except Exception as exc:
        log.warning("could not generate pydantic models", error=type(exc).__name__)
        raise PydanticGenerationError("the code generator could not handle it") from exc  # noqa: TRY003
    # It answers with a mapping of modules when a schema's names imply a package.
    if not isinstance(generated, str):
        raise PydanticGenerationError("its names would need several Python modules")  # noqa: TRY003
    return generated


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
