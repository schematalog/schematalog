// Schema-editor island. Progressive enhancement for the publish form: the plain
// `[data-editor]` textarea is replaced by a CodeMirror JSON editor (syntax highlighting,
// bracket matching, inline parse errors in the lint gutter). The textarea itself stays
// in the DOM as the form's field - the editor writes every change straight back into
// it, so a normal form POST carries the edited document.
//
// The island also gates the submit button on the form being publishable: the native
// constraints (name and version) plus a document that parses to a JSON object. A
// disabled button with no explanation is a dead end, so the reason is always rendered
// beside it. None of this is authoritative - the server validates every submission,
// and without this script the form falls back to native validation and a server
// round-trip.

import { json, jsonParseLinter } from "@codemirror/lang-json";
import { linter, lintGutter } from "@codemirror/lint";
import { basicSetup, EditorView } from "codemirror";

/** Report a JSON parse failure for `text`, or null if it parses to an object. */
export function documentError(text: string): string | null {
  if (text.trim() === "") {
    return "The document is empty.";
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    return error instanceof Error ? error.message : "The document is not valid JSON.";
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return "The document must be a JSON object.";
  }
  return null;
}

/** Why the form cannot be submitted yet, or null when it is ready. */
export function publishBlocker(form: HTMLFormElement, document_: string): string | null {
  // Report the missing fields before the document: they sit above it in the form, and
  // an empty name is a more likely reason to be stuck than a malformed schema.
  if (!form.checkValidity()) {
    return "Fill in the name and version.";
  }
  const error = documentError(document_);
  return error === null ? null : `The document is not ready: ${error}`;
}

/** Mount a CodeMirror editor onto `textarea`, syncing edits back into it. */
export function mountEditor(textarea: HTMLTextAreaElement): EditorView {
  const host = document.createElement("div");
  host.className = "schema-editor rounded-box border border-base-300 overflow-hidden";
  textarea.after(host);
  // The textarea keeps carrying the value on submit, so it must stay in the form -
  // hidden rather than removed. `hidden` alone loses to the stylesheet's display rules.
  textarea.style.display = "none";
  // `required` on a hidden control makes the browser block submit with no visible
  // message (it cannot focus what it cannot show), so the island takes the document's
  // validation over. Without the island the attribute still does its job.
  textarea.removeAttribute("required");

  const view = new EditorView({
    parent: host,
    doc: textarea.value,
    extensions: [
      basicSetup,
      json(),
      linter(jsonParseLinter()),
      lintGutter(),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          textarea.value = update.state.doc.toString();
          refresh();
        }
      }),
    ],
  });

  const form = textarea.form;
  const button = form?.querySelector<HTMLButtonElement>("[data-publish-submit]");
  const hint = form?.querySelector<HTMLElement>("[data-publish-hint]");

  function refresh(): void {
    if (!form) {
      return;
    }
    const blocker = publishBlocker(form, textarea.value);
    if (button) {
      button.disabled = blocker !== null;
    }
    if (hint) {
      hint.textContent = blocker ?? "";
      hint.classList.toggle("hidden", blocker === null);
    }
  }

  // `input` covers every text field, and bubbles to the form.
  form?.addEventListener("input", refresh);
  // Belt and braces: a disabled button suppresses implicit submission too, but the
  // gate must not depend on the button's state alone.
  form?.addEventListener("submit", (event) => {
    if (publishBlocker(form, textarea.value) !== null) {
      event.preventDefault();
      refresh();
    }
  });
  refresh();
  return view;
}

export function initEditor(root: ParentNode = document): EditorView | null {
  const textarea = root.querySelector<HTMLTextAreaElement>("[data-editor]");
  return textarea ? mountEditor(textarea) : null;
}

initEditor();
