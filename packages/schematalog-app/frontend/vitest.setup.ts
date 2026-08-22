// jsdom implements no layout, so the geometry APIs CodeMirror calls during its measure
// phase are missing entirely (`Range.getClientRects`) or always return zeroes. Left
// unstubbed they throw asynchronously and bury the test output in stack traces. Zero-size
// rects are the honest answer for an unlaid-out document, and the island tests assert on
// document/DOM state rather than geometry.

if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => Object.assign([], { item: () => null });
  Range.prototype.getBoundingClientRect = () => new DOMRect();
}
