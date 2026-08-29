// Colour-theme island. The stored *preference* is one of "auto" | "light" | "dark";
// the `data-theme` attribute the page carries is only ever "light" or "dark", because
// DaisyUI and the generated code palette both need a concrete answer. "auto" means
// "resolve it from the system", not "a third theme".
//
// Resolution happens twice: once in a tiny blocking script in the document head, before
// first paint, so the page never flashes the wrong palette; and again here, whenever the
// reader chooses or - while on "auto" - the system setting changes underneath them.

export const STORAGE_KEY = "schematalog-theme";

export type Preference = "auto" | "light" | "dark";
export type Theme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemPrefersDark(): boolean {
  return window.matchMedia?.(DARK_QUERY).matches ?? false;
}

/** The stored preference, defaulting to "auto" when absent or unreadable. */
export function readPreference(): Preference {
  let stored: string | null = null;
  try {
    // Private-browsing modes and blocked site data throw on access, not on read.
    stored = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return "auto";
  }
  return stored === "light" || stored === "dark" || stored === "auto" ? stored : "auto";
}

/** The concrete theme a preference resolves to right now. */
export function resolve(preference: Preference): Theme {
  if (preference === "auto") {
    return systemPrefersDark() ? "dark" : "light";
  }
  return preference;
}

function apply(preference: Preference): void {
  document.documentElement.dataset.theme = resolve(preference);
  for (const button of document.querySelectorAll<HTMLElement>("[data-theme-choice]")) {
    const chosen = button.dataset.themeChoice === preference;
    button.classList.toggle("menu-active", chosen);
    // The menu is a list of choices, exactly one of which is in effect.
    button.setAttribute("aria-checked", String(chosen));
  }
}

function store(preference: Preference): void {
  try {
    if (preference === "auto") {
      // Absent rather than "auto", so a reader who never touches this is indistinguishable
      // from one who chose to follow the system - which is what they both want.
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, preference);
    }
  } catch {
    // A theme that lasts only for this page is still better than no theme control.
  }
}

export function initTheme(root: ParentNode = document): void {
  const control = root.querySelector<HTMLElement>("[data-theme-control]");
  if (!control) {
    return;
  }
  // Rendered hidden: without this script the buttons would be an affordance that does
  // nothing, which is worse than not offering one.
  control.hidden = false;

  apply(readPreference());

  for (const button of root.querySelectorAll<HTMLElement>("[data-theme-choice]")) {
    button.addEventListener("click", () => {
      const preference = (button.dataset.themeChoice ?? "auto") as Preference;
      store(preference);
      apply(preference);
      // Close the dropdown: DaisyUI opens it on focus, so surrendering focus closes it.
      button.blur();
    });
  }

  // Only meaningful while the preference is "auto"; re-reading it on each event means
  // a reader who switches to "auto" starts tracking the system without a reload.
  window.matchMedia?.(DARK_QUERY).addEventListener("change", () => {
    const preference = readPreference();
    if (preference === "auto") {
      apply(preference);
    }
  });
}

initTheme();
