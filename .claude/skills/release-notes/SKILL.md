---
name: release-notes
description: Draft a user-facing changelog entry between two git tags. Manual invocation only.
disable-model-invocation: true
allowed-tools: Read, Bash(git log:*), Bash(git tag:*), Bash(git diff:*)
---

# Skill: release-notes

## Usage

`/release-notes v0.1.0..v0.2.0`

## What I produce

Markdown section to append to `docs/changelog.md`:

```markdown
## v0.2.0 — YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Deprecated
- ...

### Removed
- ...

### Security
- ...
```

## Rules

- Group by Keep-a-Changelog categories.
- Write for **users**, not developers. "Added webhook trigger for GitLab" — not "Implemented `GitLabTrigger.node.py`".
- Cite PR/issue numbers where known.
- Cite the commit shorthash for security fixes so auditors can trace.
