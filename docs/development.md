# Development and releases

Normal release flow:

```text
dev -> tests/build -> explicit user approval -> main -> PyPI
```

`dev` can accumulate several commits and completed tasks. Finishing a task, or
committing and pushing to `dev`, does not create a release or update `main`.
Changes normally stay in `dev` until the user explicitly authorizes promoting
the accumulated state to `main`.

`dev` is the normal development branch. `main` is the stable release branch;
changes reach it only when an authorized release is ready. Every commit on
`main` publishes a new package version through GitHub Actions and PyPI Trusted
Publishing.

## Semantic versioning

- **Patch** — `1.0.0` → `1.0.1`: bug fixes and small compatible changes.
- **Minor** — `1.0.1` → `1.1.0`: new backwards-compatible functionality.
- **Major** — `1.x` → `2.0.0`: breaking API changes.
