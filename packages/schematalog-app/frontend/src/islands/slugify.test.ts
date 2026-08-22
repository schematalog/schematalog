import { afterEach, describe, expect, test } from "vitest";
import { initSlugify, slugify } from "./slugify";

describe("slugify", () => {
  test.each([
    ["Acme Corp", "acme-corp"],
    ["  Weird -- Name!  ", "weird-name"],
    ["ALL CAPS", "all-caps"],
    ["", ""],
    ["!!!", ""],
  ])("turns %j into %j", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });

  test("caps the slug at 63 characters", () => {
    expect(slugify("x".repeat(80))).toHaveLength(63);
  });
});

describe("slugify island", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function mount(slugValue = ""): { name: HTMLInputElement; slug: HTMLInputElement } {
    document.body.innerHTML = `
      <input data-slugify-source value="">
      <input data-slugify-target value="${slugValue}">
    `;
    initSlugify();
    return {
      name: document.querySelector("[data-slugify-source]") as HTMLInputElement,
      slug: document.querySelector("[data-slugify-target]") as HTMLInputElement,
    };
  }

  function type(input: HTMLInputElement, value: string): void {
    input.value = value;
    input.dispatchEvent(new Event("input"));
  }

  test("suggests a slug as the name is typed", () => {
    const { name, slug } = mount();
    type(name, "Acme Corp");
    expect(slug.value).toBe("acme-corp");
  });

  test("stops suggesting once the slug is edited by hand", () => {
    const { name, slug } = mount();
    type(slug, "my-own-slug");
    type(name, "Acme Corp");
    expect(slug.value).toBe("my-own-slug");
  });

  test("resumes suggesting when the hand-edited slug is cleared", () => {
    const { name, slug } = mount();
    type(slug, "my-own-slug");
    type(slug, "");
    type(name, "Acme Corp");
    expect(slug.value).toBe("acme-corp");
  });

  test("treats a server-prefilled slug as already edited", () => {
    const { name, slug } = mount("kept-slug");
    type(name, "Acme Corp");
    expect(slug.value).toBe("kept-slug");
  });

  test("does nothing when the form is not on the page", () => {
    document.body.innerHTML = "<p>no form here</p>";
    expect(() => initSlugify()).not.toThrow();
  });
});
