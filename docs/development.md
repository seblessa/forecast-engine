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
changes reach it only when an authorized release is ready. One authorized
promotion of the accumulated `dev` state to `main` represents one package
release and may contain multiple commits. The promoted tip of `main` must
contain a PyPI version that has never been published; additional pushes to
`main` outside an authorized release are not allowed. GitHub Actions publishes
that release through PyPI Trusted Publishing.

## Semantic versioning

- **Patch** — `1.0.0` → `1.0.1`: bug fixes and small compatible changes.
- **Minor** — `1.0.1` → `1.1.0`: new backwards-compatible functionality.
- **Major** — `1.x` → `2.0.0`: breaking API changes.
