import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { initClipboard } from "./clipboard";

describe("clipboard island", () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    document.body.innerHTML = `
      <pre id="code">{"a": 1}</pre>
      <button data-copy="code">Copy</button>
    `;
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  function button(): HTMLButtonElement {
    return document.querySelector("button") as HTMLButtonElement;
  }

  test("copies the source element's text and flashes feedback", async () => {
    initClipboard();
    button().click();
    await vi.waitFor(() => expect(button().textContent).toBe("Copied!"));
    expect(writeText).toHaveBeenCalledWith('{"a": 1}');
  });

  test("restores the resting label after the feedback delay", async () => {
    initClipboard();
    button().click();
    await vi.waitFor(() => expect(button().textContent).toBe("Copied!"));
    vi.advanceTimersByTime(1500);
    expect(button().textContent).toBe("Copy");
  });

  test("does nothing when the copy target is missing", () => {
    document.body.innerHTML = `<button data-copy="absent">Copy</button>`;
    initClipboard();
    button().click();
    expect(writeText).not.toHaveBeenCalled();
  });
});
