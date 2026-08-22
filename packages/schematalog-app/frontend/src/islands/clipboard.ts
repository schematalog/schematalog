// Copy-to-clipboard island. Progressive enhancement: any element with a `data-copy`
// attribute whose value is the id of a source element becomes a copy button. The page
// works without this script (the code is visible and selectable); the island just adds
// one-click copy with brief inline feedback instead of a blocking alert.

const FEEDBACK_MS = 1500;

async function writeClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

function flash(button: HTMLElement, message: string): void {
  // Stash the resting label once, so repeated clicks always restore the same text.
  const label = button.dataset.label ?? button.textContent ?? "";
  button.dataset.label = label;
  button.textContent = message;
  window.setTimeout(() => {
    button.textContent = button.dataset.label ?? label;
  }, FEEDBACK_MS);
}

async function handleCopy(button: HTMLElement): Promise<void> {
  const sourceId = button.dataset.copy;
  const source = sourceId ? document.getElementById(sourceId) : null;
  if (!source) {
    return;
  }
  try {
    await writeClipboard(source.textContent ?? "");
    flash(button, "Copied!");
  } catch {
    flash(button, "Copy failed");
  }
}

export function initClipboard(root: ParentNode = document): void {
  for (const button of root.querySelectorAll<HTMLElement>("[data-copy]")) {
    button.addEventListener("click", () => {
      void handleCopy(button);
    });
  }
}

initClipboard();
