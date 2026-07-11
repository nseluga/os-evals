import { describe, it, expect } from 'vitest';
import { computeDigestBuckets } from '../src/lib/digest.js';
import type { MergedProject } from '../src/types/project.js';

// Minimal valid MergedProject fixture
function makeProject(overrides: Partial<MergedProject> = {}): MergedProject {
  return {
    id: 'test-project',
    name: 'Test Project',
    summary: null,
    repo: null,
    github: null,
    tags: [],
    status: 'active',
    priority: 'medium',
    next_step: null,
    last_active: '2026-07-01T00:00:00.000Z',
    days_since_active: 10,
    due_date: null,
    overdue: false,
    ...overrides,
  };
}

const TODAY = '2026-07-08';
const SEVEN_DAYS = '2026-07-15';

describe('computeDigestBuckets()', () => {
  describe('moved bucket', () => {
    it('includes a project with days_since_active = 2', () => {
      const projects = [makeProject({ id: 'recent', name: 'Recent', days_since_active: 2 })];
      const { moved } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(1);
      expect(moved[0].id).toBe('recent');
    });

    it('includes a project with days_since_active = 7 (boundary)', () => {
      const projects = [makeProject({ id: 'boundary', days_since_active: 7 })];
      const { moved } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(1);
    });

    it('excludes a project with days_since_active = 8', () => {
      const projects = [makeProject({ id: 'old', days_since_active: 8 })];
      const { moved } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(0);
    });

    it('returns empty array when no projects match', () => {
      const projects = [makeProject({ days_since_active: 30 })];
      const { moved } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(0);
    });
  });

  describe('overdue bucket', () => {
    it('includes a project with overdue = true and a due_date of yesterday', () => {
      const yesterday = '2026-07-07';
      const projects = [
        makeProject({ id: 'past', name: 'Past Project', due_date: yesterday, overdue: true }),
      ];
      const { overdue } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(overdue).toHaveLength(1);
      expect(overdue[0].id).toBe('past');
    });

    it('excludes a project with overdue = false even if due_date is in the past', () => {
      const projects = [
        makeProject({ id: 'notoverdue', due_date: '2026-07-07', overdue: false }),
      ];
      const { overdue } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(overdue).toHaveLength(0);
    });

    it('excludes a project with no due_date', () => {
      const projects = [makeProject({ id: 'nodate', due_date: null, overdue: false })];
      const { overdue } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(overdue).toHaveLength(0);
    });

    it('returns empty array when no projects are overdue', () => {
      const projects = [makeProject({ days_since_active: 0, overdue: false })];
      const { overdue } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(overdue).toHaveLength(0);
    });
  });

  describe('comingUp bucket', () => {
    it('includes a project due 3 days from now', () => {
      const threeDays = '2026-07-11';
      const projects = [
        makeProject({ id: 'soon', name: 'Soon Project', due_date: threeDays, overdue: false }),
      ];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(1);
      expect(comingUp[0].id).toBe('soon');
    });

    it('includes a project due exactly on the 7-day boundary', () => {
      const projects = [
        makeProject({ id: 'boundary7', due_date: SEVEN_DAYS, overdue: false }),
      ];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(1);
    });

    it('excludes a project due 8 days from now', () => {
      const eightDays = '2026-07-16';
      const projects = [
        makeProject({ id: 'later', due_date: eightDays, overdue: false }),
      ];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(0);
    });

    it('excludes a project that is already overdue', () => {
      const yesterday = '2026-07-07';
      const projects = [
        makeProject({ id: 'past2', due_date: yesterday, overdue: true }),
      ];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(0);
    });

    it('excludes a project with a past due_date and overdue = false', () => {
      // Important fix (review): lower-bound guard ensures past-due projects not flagged
      // overdue do not silently appear in "Coming up".
      const yesterday = '2026-07-07';
      const projects = [
        makeProject({ id: 'past-not-flagged', due_date: yesterday, overdue: false }),
      ];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(0);
    });

    it('excludes a project with a malformed due_date (MM/DD/YYYY format) from all buckets', () => {
      // Important fix (review): non-YYYY-MM-DD due_date values are normalised to null
      // before any comparison, preventing wrong bucket placement.
      const projects = [
        makeProject({ id: 'malformed', due_date: '07/08/2026', overdue: false }),
      ];
      const { moved, overdue, comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(0);   // days_since_active defaults to 10 (> 7)
      expect(overdue).toHaveLength(0);
      expect(comingUp).toHaveLength(0);
    });

    it('excludes a project with no due_date', () => {
      const projects = [makeProject({ id: 'nodate2', due_date: null, overdue: false })];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(0);
    });

    it('returns empty array when no projects are coming up', () => {
      const projects = [makeProject({ due_date: null, overdue: false })];
      const { comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(comingUp).toHaveLength(0);
    });
  });

  describe('all three buckets together', () => {
    it('correctly places a project with days_since_active=2 in moved, one with overdue in overdue, and one due in 3 days in comingUp', () => {
      const yesterday = '2026-07-07';
      const threeDays = '2026-07-11';
      const projects = [
        makeProject({ id: 'recent', name: 'Recent', days_since_active: 2 }),
        makeProject({ id: 'past-due', name: 'Past Due', due_date: yesterday, overdue: true, days_since_active: 15 }),
        makeProject({ id: 'coming', name: 'Coming', due_date: threeDays, overdue: false, days_since_active: 20 }),
        makeProject({ id: 'nothing', name: 'Nothing', days_since_active: 30 }),
      ];

      const { moved, overdue, comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);

      expect(moved.map((p) => p.id)).toContain('recent');
      expect(moved.map((p) => p.id)).not.toContain('nothing');

      expect(overdue).toHaveLength(1);
      expect(overdue[0].id).toBe('past-due');

      expect(comingUp).toHaveLength(1);
      expect(comingUp[0].id).toBe('coming');
    });

    it('a project with days_since_active=2 AND overdue=true appears in both moved and overdue', () => {
      // The task does not exclude moved items from overdue — a recently-active overdue project appears in both
      const yesterday = '2026-07-07';
      const projects = [
        makeProject({ id: 'both', days_since_active: 2, due_date: yesterday, overdue: true }),
      ];
      const { moved, overdue, comingUp } = computeDigestBuckets(projects, TODAY, SEVEN_DAYS);
      expect(moved.map((p) => p.id)).toContain('both');
      expect(overdue.map((p) => p.id)).toContain('both');
      expect(comingUp).toHaveLength(0);
    });

    it('returns all empty arrays for an empty project list', () => {
      const { moved, overdue, comingUp } = computeDigestBuckets([], TODAY, SEVEN_DAYS);
      expect(moved).toHaveLength(0);
      expect(overdue).toHaveLength(0);
      expect(comingUp).toHaveLength(0);
    });
  });
});
