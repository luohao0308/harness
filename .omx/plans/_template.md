# PRD Template

## DoD Commit Hygiene

- Plan for N atomic commits that match the PRD work items, with a tolerance of +/-2 when closely related cleanup is safer to merge together.
- Each commit must leave the touched backend/frontend surface buildable and its relevant targeted tests passing.
- Commit messages must follow the repository Lore protocol, including `Scope-risk:` and `Tested:` trailers when they add decision context.
