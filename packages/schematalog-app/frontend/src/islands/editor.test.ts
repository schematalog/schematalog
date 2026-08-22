import type { EditorView } from "codemirror";
import { afterEach, describe, expect, test } from "vitest";
import { documentError, initEditor } from "./editor";

describe("documentError", () => {
  test.each([
    ['{"type": "object"}', null],
    ["{}", null],
    ["", "The document is empty."],
    ["   ", "The document is empty."],
    ["[1, 2]", "The document must be a JSON object."],
    ["null", "The document must be a JSON object."],
    ['"a string"', "The document must be a JSON object."],
  ])("rates %j as %j", (input, expected) => {
    expect(documentError(input)).toBe(expected);
  });

  test("reports the parser's own message for malformed JSON", () => {
    expect(documentError("{not json")).toBeTruthy();
  });
});

describe("editor island", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  interface Mounted {
    textarea: HTMLTextAreaElement;
    view: EditorView | null;
    form: HTMLFormElement;
    button: HTMLButtonElement;
    hint: HTMLElement;
    name: HTMLInputElement;
  }

  function mount({ doc = '{"type": "object"}', name = "customer" } = {}): Mounted {
    document.body.innerHTML = `
      <form>
        <input name="name" value="${name}" required pattern="[0-9a-zA-Z][0-9a-zA-Z\\-_.]*">
        <input name="version" value="1.0" required>
        <textarea data-editor name="json_schema" required>${doc}</textarea>
        <button type="submit" data-publish-submit>Publish</button>
        <p data-publish-hint class="hidden"></p>
      </form>`;
    const view = initEditor();
    return {
      textarea: document.querySelector("[data-editor]") as HTMLTextAreaElement,
      view,
      form: document.querySelector("form") as HTMLFormElement,
      button: document.querySelector("[data-publish-submit]") as HTMLButtonElement,
      hint: document.querySelector("[data-publish-hint]") as HTMLElement,
      name: document.querySelector("[name=name]") as HTMLInputElement,
    };
  }

  /** Edit the form's name field the way a user would. */
  function type(input: HTMLInputElement, value: string): void {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  /** Submit the form, reporting whether the island blocked it. */
  function submit(form: HTMLFormElement): boolean {
    const event = new Event("submit", { cancelable: true, bubbles: true });
    form.dispatchEvent(event);
    return event.defaultPrevented;
  }

  test("seeds the editor from the textarea's value", () => {
    const { view } = mount({ doc: '{"type": "object"}' });
    expect(view?.state.doc.toString()).toBe('{"type": "object"}');
  });

  test("keeps the textarea in the form so a plain POST still carries the value", () => {
    const { textarea } = mount();
    expect(textarea.isConnected).toBe(true);
    expect(textarea.form).not.toBeNull();
    expect(textarea.style.display).toBe("none");
  });

  test("syncs edits back into the textarea", () => {
    const { textarea, view } = mount({ doc: "{}" });
    view?.dispatch({ changes: { from: 0, to: 2, insert: '{"a": 1}' } });
    expect(textarea.value).toBe('{"a": 1}');
  });

  test("drops `required`, which a hidden control cannot report to the user", () => {
    const { textarea } = mount();
    expect(textarea.hasAttribute("required")).toBe(false);
  });

  test("enables publishing when the form is complete", () => {
    const { button, hint } = mount();
    expect(button.disabled).toBe(false);
    expect(hint.classList.contains("hidden")).toBe(true);
  });

  test("disables publishing while the document is malformed, and says so", () => {
    const { button, hint } = mount({ doc: "{not json" });
    expect(button.disabled).toBe(true);
    expect(hint.textContent).toContain("document is not ready");
    expect(hint.classList.contains("hidden")).toBe(false);
  });

  test("disables publishing while a required field is empty", () => {
    const { button, hint } = mount({ name: "" });
    expect(button.disabled).toBe(true);
    expect(hint.textContent).toBe("Fill in the name and version.");
  });

  test("reports a missing field ahead of the document", () => {
    const { hint } = mount({ name: "", doc: "{not json" });
    expect(hint.textContent).toBe("Fill in the name and version.");
  });

  test("disables publishing when the name breaks its pattern", () => {
    const { button } = mount({ name: "not a name!" });
    expect(button.disabled).toBe(true);
  });

  test("re-enables publishing once the document is fixed", () => {
    const { button, hint, view } = mount({ doc: "{not json" });
    expect(button.disabled).toBe(true);
    view?.dispatch({ changes: { from: 0, to: 9, insert: "{}" } });
    expect(button.disabled).toBe(false);
    expect(hint.classList.contains("hidden")).toBe(true);
  });

  test("re-enables publishing once a required field is filled in", () => {
    const { button, name } = mount({ name: "" });
    expect(button.disabled).toBe(true);
    type(name, "customer");
    expect(button.disabled).toBe(false);
  });

  test("blocks a submit that slips past the disabled button", () => {
    const { form } = mount({ doc: "[1, 2]" });
    expect(submit(form)).toBe(true);
  });

  test("lets a complete form submit", () => {
    const { form } = mount();
    expect(submit(form)).toBe(false);
  });

  test("does nothing when the page has no editor", () => {
    document.body.innerHTML = "<p>no editor here</p>";
    expect(initEditor()).toBeNull();
  });
});
