Implement the weekly-digest bucket logic for this Astro project dashboard (PLAN.md Item 3.1).

Context: this is an Astro + TypeScript SSR dashboard. `getMergedProjects()` returns
`MergedProject[]` (type in `src/types/project.ts`), where each project has at least:
`id`, `name`, `days_since_active: number`, `overdue: boolean`, and
`due_date: string | null` (ISO `YYYY-MM-DD`).

Implement and export a pure function `computeDigestBuckets(projects: MergedProject[])`
in `src/lib/digest.ts` that sorts projects into exactly three buckets and returns
`{ moved, overdue, comingUp }` (each a `MergedProject[]`):

- **moved** — projects with `days_since_active <= 7`.
- **overdue** — projects with `overdue === true`.
- **comingUp** — projects that have a `due_date`, are NOT overdue
  (`overdue === false`), and whose `due_date` is on or before 7 days from today.

Boundary rules matter: `days_since_active === 7` is IN "moved"; `days_since_active === 8`
is out. A project due exactly 7 days from now IS in "comingUp"; 8 days out is not. A
project with a malformed or missing `due_date` is never in "comingUp". Compute "today"
from the system clock. Keep the function pure and side-effect free.

Also wire a `src/components/WeeklyDigest.astro` that renders the three buckets above the
project board, showing "Nothing here." for any empty bucket — but the core deliverable
graded here is `computeDigestBuckets`.

Match the surrounding TypeScript style (types, no `any`).
