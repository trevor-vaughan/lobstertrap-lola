# ADR: Use Architecture Decision Records

**Status**: Accepted
**Date**: 2026-04-28
**Last Updated**: 2026-05-25
**Authors**: Igor Brandao
**Reviewers**:

## Context

We need to record the architectural decisions made on this project in a way that is
accessible, versioned, and avoids merge conflicts when multiple ADRs are submitted
concurrently.

## Decision

We will use Architecture Decision Records (ADRs) as
[described by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Each ADR documents one architectural decision and lives as a single markdown file in
`docs/adr/`.

## How We Use ADRs

**Creating an ADR:**
Copy `docs/adr/template.md` to `docs/adr/topic-name.md`, fill in all sections, and
open a pull request. Use `make adr-new topic-name` for convenience.

**Updating an ADR:**
If a decision changes, update the existing ADR in place and bump `Last Updated` to
today's date. The git history provides a full audit trail of what changed and when.

**Deprecating an ADR:**
If a decision is no longer relevant, set `Status` to `Deprecated` and update
`Last Updated`. Add a brief note explaining why.

## ADR Statuses

| Status | Meaning |
|--------|---------|
| **Proposed** | Under discussion, not yet accepted |
| **Accepted** | Approved and in effect |
| **Deprecated** | No longer relevant |

## Naming Convention

ADR files use descriptive kebab-case names — no sequential numbers, no date prefix.
The date lives inside the document. Topic names must be unique.

```text
docs/adr/use-adrs.md
docs/adr/go-migration.md
```

## Template Changes

If the template needs to change, describe what changed and why in `docs/adr/README.md`,
apply the change to `docs/adr/template.md`, and open a pull request for Core Maintainer
approval. Existing ADRs are not retroactively reformatted.

## Rationale

Topic-based names avoid merge conflicts from sequential numbering and make the ADR
subject immediately clear from the filename. Updating ADRs in place keeps one file per
topic with git as the audit trail.

## Consequences

### Positive Consequences

- No merge conflicts from sequential numbering
- ADR filenames are self-describing
- No external tooling dependency
- One file per topic

### Negative Consequences

- ADRs are not ordered by creation date from the filename; use `git log docs/adr/` for
  chronological ordering

## References

- [Michael Nygard on ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR README](README.md)
- [ADR Template](template.md)
