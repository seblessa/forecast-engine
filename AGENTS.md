# Repository agent instructions

## Initial Mac Mini sync

Before starting every task, update the checkout on the Mac Mini:

```bash
ssh sebs-macmini 'cd /Users/seb/Projects/forecast-engine && git pull'
```

If the pull reports conflicts, inspect the remote working tree, understand both
sides, and resolve the conflicts without discarding either intentional change.
Complete the merge or rebase and run the relevant checks before proceeding. If
the intent cannot be determined safely, stop and ask the user instead of deleting
changes. Never use `reset --hard` or force-push to resolve a sync problem.

The `cd` must remain inside the quoted SSH command; running `ssh sebs-macmini &&
cd ...` changes directory locally after the SSH session exits.

## Project conventions

- Use the `git` command for repository operations, including sync, branches,
  commits, and pushes. Do not use the GitHub CLI (`gh`).
- Keep the REST layer small; forecasting behavior belongs to the public
  `chronos_forecaster` package.
- Preserve the request and response contract documented in `README.md` and the
  generated `/openapi.json` schema.
- Add dependencies only when the standard library or an existing dependency does
  not cover the requirement.
- Run `uv run pytest` after code changes.
- Never commit model weights, caches, virtual environments, or secrets.
