// Slug-suggestion island. Progressive enhancement for the create-workspace form: as
// the user types the workspace name (`[data-slugify-source]`), a subdomain slug is
// suggested into the slug input (`[data-slugify-target]`) - until the user edits the
// slug themselves, at which point their value wins. The page works without this
// script (the slug can always be typed by hand).

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

export function initSlugify(root: ParentNode = document): void {
  const source = root.querySelector<HTMLInputElement>("[data-slugify-source]");
  const target = root.querySelector<HTMLInputElement>("[data-slugify-target]");
  if (!source || !target) {
    return;
  }
  // A slug prefilled by the server (a form re-rendered after a validation error)
  // counts as user-edited; suggestions must not clobber it.
  let edited = target.value !== "";
  source.addEventListener("input", () => {
    if (!edited) {
      target.value = slugify(source.value);
    }
  });
  target.addEventListener("input", () => {
    edited = target.value !== "";
  });
}

initSlugify();
