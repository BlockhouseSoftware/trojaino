# PyPI trusted publishing

Trojaino's official Python distribution is `trojaino`. This document records
how maintainers publish it without storing a PyPI API token in GitHub.

## One-time PyPI setup

A maintainer who controls the `trojaino` PyPI project must configure a PyPI
**Trusted Publisher** before the first publication:

- **Owner:** `BlockhouseSoftware`
- **Repository:** `trojaino`
- **Workflow:** `publish-pypi.yml`
- **Environment:** `pypi`

Create the PyPI project through PyPI's trusted-publisher flow or reserve the
name through the approved Blockhouse Software PyPI account. Confirm that the
project URL is exactly <https://pypi.org/project/trojaino/> before changing the
public installation instructions. Do not create an `aishield` package: that
name belongs to an unrelated Bosch distribution.

On GitHub, create a protected `pypi` environment with required reviewer
approval. The workflow requests an OIDC identity token only in its final
publish job; it has no PyPI API-token secret.

## Release procedure

1. Start from a clean, reviewed `main` commit and choose the next normalized
   version in `pyproject.toml` and `CHANGELOG.md`.
2. Run the full test suite and release-profile scan locally.
3. Commit the release metadata and create an immutable `vX.Y.Z` tag at that
   exact commit. Do not move or reuse a published tag.
4. Push the tag. The `Publish to PyPI` workflow builds a wheel and sdist from
   that tag, runs `twine check`, verifies package metadata and required files,
   and smoke-tests the wheel in a fresh environment before requesting the
   protected `pypi` environment approval.
5. Approve the environment only after reviewing the build artifact, version,
   and workflow commit. PyPI then validates the GitHub OIDC identity and
   receives the already-verified artifacts.
6. Read the PyPI project and release back. Confirm the version, project URL,
   wheel and sdist files, `AGPL-3.0-only` license metadata, and fresh
   `pipx install trojaino` smoke test before updating README installation text.

## Safety boundaries

- The workflow triggers only from a `v*` tag push, never a pull request or
  branch push.
- Publishing is blocked by the protected GitHub `pypi` environment.
- Do not add a `PYPI_API_TOKEN` or equivalent registry token to GitHub.
- Do not publish a placeholder or test build to the production project.
- An unsigned Windows preview and a PyPI package are separate release claims;
  preserve the Windows signing status accurately in release notes.
