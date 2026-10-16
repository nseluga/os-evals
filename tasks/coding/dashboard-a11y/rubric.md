# Rubric: accessibility remediation of a small dashboard header

The author was given a static `index.html` for a dashboard header and asked to fix its accessibility in place while preserving visible content and available actions: every image needs meaningful alternative text; every control needs an accessible name (an icon-only button needs a label, a text field needs an associated label); anything clickable that performs an action must be a real, keyboard-operable control, not a bare element with a click handler. Only `index.html` was to be edited.

The artifact shows the final response and a diff of `index.html` against its starting version. Judge only the artifact.

## Scale
- 5: All four defects fixed with the right mechanism: the image gets descriptive (not filename or "image") alt text; the icon-only button gets an accessible name (`aria-label`, or visually hidden text) and the decorative icon is hidden from assistive tech or harmless; the text field gets an associated label or `aria-label` that says what it is for; the clickable `div` becomes a real `<button>` (or an equivalent with role, tabindex and key handling) keeping its text and its `onclick` action. Nothing else changed; the page structure and visible text are preserved.
- 4: All four fixed; alt or label wording is merely adequate, or one cosmetic extra change (such as a class kept or a harmless attribute added).
- 3: Three of four fixed correctly, or all four attempted with one using a weak mechanism (for example `title` only, or `role="button"` without keyboard support).
- 2: Two fixed; or fixes that break an action or remove visible content.
- 1: One fix, or only superficial changes such as `alt=""` on the content image.
- 0: No fix, the file is rewritten as a different page, or the response claims fixes the diff does not contain.

## Does not earn points
- `alt=""`, `alt="image"`, or an alt that repeats a filename on the content image.
- Labels added to the wrong elements, or ARIA that contradicts native semantics.
- Redesigning layout or styling, removing the delete or refresh actions, or changing visible text.
- Claims in the response not supported by the diff.
