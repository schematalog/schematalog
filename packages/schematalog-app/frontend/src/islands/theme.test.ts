import { beforeEach, describe, expect, it, vi } from "vitest";
import { initTheme, readPreference, resolve, STORAGE_KEY } from "./theme";

function setSystemDark(dark: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: dark, addEventListener: vi.fn() }),
  );
}

function render(): void {
  document.body.innerHTML = `
    <div data-theme-control hidden>
      <button type="button" data-theme-choice="auto">Auto</button>
      <button type="button" data-theme-choice="light">Light</button>
      <button type="button" data-theme-choice="dark">Dark</button>
    </div>`;
}

function choose(preference: string): void {
  document.querySelector<HTMLElement>(`[data-theme-choice="${preference}"]`)?.click();
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  setSystemDark(false);
  render();
});

describe("the stored preference", () => {
  it("defaults to auto when nothing has been chosen", () => {
    expect(readPreference()).toBe("auto");
  });

  it("falls back to auto rather than trusting an unrecognised stored value", () => {
    localStorage.setItem(STORAGE_KEY, "solarized");
    expect(readPreference()).toBe("auto");
  });

  it("resolves auto against the system setting", () => {
    setSystemDark(true);
    expect(resolve("auto")).toBe("dark");
    setSystemDark(false);
    expect(resolve("auto")).toBe("light");
  });

  it("resolves an explicit choice without consulting the system", () => {
    setSystemDark(true);
    expect(resolve("light")).toBe("light");
  });
});

describe("the theme control", () => {
  it("stays hidden when there is nothing to control", () => {
    document.body.innerHTML = "";
    expect(() => initTheme()).not.toThrow();
  });

  it("reveals itself, because it only works once the island has run", () => {
    const control = document.querySelector<HTMLElement>("[data-theme-control]");
    expect(control?.hidden).toBe(true);
    initTheme();
    expect(control?.hidden).toBe(false);
  });

  it("puts a concrete theme on the page, never the auto preference", () => {
    setSystemDark(true);
    initTheme();
    expect(document.documentElement.dataset.theme).toBe("dark");
    choose("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("remembers an explicit choice", () => {
    initTheme();
    choose("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    expect(readPreference()).toBe("dark");
  });

  it("stores auto as no entry at all", () => {
    initTheme();
    choose("dark");
    choose("auto");
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(readPreference()).toBe("auto");
  });

  it("marks which choice is in effect", () => {
    initTheme();
    choose("dark");
    const dark = document.querySelector('[data-theme-choice="dark"]');
    const light = document.querySelector('[data-theme-choice="light"]');
    expect(dark?.getAttribute("aria-checked")).toBe("true");
    expect(light?.getAttribute("aria-checked")).toBe("false");
  });
});
