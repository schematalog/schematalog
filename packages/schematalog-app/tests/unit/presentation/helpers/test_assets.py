"""The Vite manifest glue: `vite_asset()` dev/prod tag rendering and degradation."""

import json

import pytest

from schematalog.app.presentation.helpers import assets


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    """Each test controls the manifest, so start from an empty cache and prod mode."""
    monkeypatch.setattr(assets, "_manifest_cache", {})
    monkeypatch.setattr(assets.settings, "VITE_DEV_SERVER", "")


def _write_manifest(monkeypatch, tmp_path, mapping):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(mapping))
    monkeypatch.setattr(assets, "_MANIFEST_PATH", manifest)


def test_dev_server_mode_emits_hmr_tags(monkeypatch):
    monkeypatch.setattr(assets.settings, "VITE_DEV_SERVER", "http://localhost:5173")
    out = str(assets.vite_asset("src/styles/app.css"))
    assert "http://localhost:5173/@vite/client" in out
    assert "http://localhost:5173/src/styles/app.css" in out


def test_css_entry_emits_hashed_link(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        {"src/styles/app.css": {"file": "assets/app-abc123.css", "isEntry": True}},
    )
    out = str(assets.vite_asset("src/styles/app.css"))
    assert out == '<link rel="stylesheet" href="/static/dist/assets/app-abc123.css">'


def test_js_entry_emits_script_and_its_imported_css(monkeypatch, tmp_path):
    _write_manifest(
        monkeypatch,
        tmp_path,
        {
            "src/islands/editor.ts": {
                "file": "assets/editor-xyz.js",
                "css": ["assets/editor-xyz.css"],
                "isEntry": True,
            }
        },
    )
    out = str(assets.vite_asset("src/islands/editor.ts"))
    assert '<link rel="stylesheet" href="/static/dist/assets/editor-xyz.css">' in out
    assert '<script type="module" src="/static/dist/assets/editor-xyz.js"></script>' in out


def test_missing_manifest_degrades_to_comment(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "_MANIFEST_PATH", tmp_path / "absent.json")
    out = str(assets.vite_asset("src/styles/app.css"))
    assert out.startswith("<!-- vite asset not built")


def test_unknown_entry_degrades_to_comment(monkeypatch, tmp_path):
    _write_manifest(monkeypatch, tmp_path, {"src/styles/app.css": {"file": "x.css"}})
    out = str(assets.vite_asset("src/islands/missing.ts"))
    assert out.startswith("<!-- vite asset not built")
