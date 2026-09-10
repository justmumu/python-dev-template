# Release process

This project releases from `main`. Create a version bump on a feature branch,
merge its PR, then push the local annotated tag to create the GitHub Release.
The sequence is identical for patch, minor and major bumps.

## Versioning policy

We follow [Semantic Versioning 2.0](https://semver.org/). New Python projects start
at `0.0.0`. During `0.x`, minor bumps may include breaking changes, as SemVer
permits for initial development. The template generator has its own version;
updating a project through Copier does not reset the application's version.

## Tooling

Use `make changelog` to generate `CHANGELOG.md` from Conventional Commits with
Commitizen. Generated applications begin their changelog history at the commit
that introduced `.copier-answers.yml`, so inherited template commits are not
presented as application features. Preserve that initial history for Copier
updates.

Each `make bump-{patch,minor,major}` target:

1. Requires a clean working tree on a feature branch, not `main`, `master` or a
   detached checkout.
2. Calls `uv version --bump <segment>` to update `pyproject.toml` and `uv.lock`.
3. Generates the changelog with Commitizen and formats `CHANGELOG.md` with
   mdformat.
4. Commits the release changes with the normal Git hooks enabled.
5. Creates the annotated local tag `v<new-version>` after the commit succeeds.

Every failed step stops the command. Inspect the reported error and working
tree before retrying; formatting and hook changes are not silently discarded.
The command never pushes tags or publishes to PyPI.

For coding agents, ordinary uv-managed version changes remain allowed. The
complete release operation also commits and tags, so it requires release
authorization and is not an automatic dependency-management exemption.

## Step-by-step flow

Start with a clean working tree and an up-to-date `main`.

### 1. Create the release branch

```bash
git switch main
git pull
git switch -c chore/bump-v<new-version>
```

Choose `<new-version>` from the current version (`make version`) and intended
segment. Codex uses `codex/bump-v<new-version>` for its feature branch.

### 2. Bump

```bash
make bump-patch     # or bump-minor, or bump-major
```

Review the resulting metadata, lockfile and changelog. The command creates the
bump commit and annotated tag locally. If you chose the wrong segment, inspect
the unpushed commit and tag and agree on a correction before changing history.

### 3. Push the branch only

```bash
git push -u origin chore/bump-v<new-version>
```

Use the branch name you created. Keep the tag local until the PR merges. A tag
pushed early would refer to a commit that has not reached `main`, and the release
workflow rejects it.

### 4. Open and merge the PR

- Title: `chore: bump version to v<new-version>`.
- Complete the [PR checklist](pr-checklist.md), including `make check` and
  `make docs-build`.
- Review the changelog as the exact notes that will accompany this release.
- Merge with a regular merge commit, never squash. Squashing replaces the bump
  commit and disconnects the local tag from the merged history.

### 5. Push the tag

Once the PR is merged and `main` contains the bump commit:

```bash
git switch main
git pull
git push origin v<new-version>
```

### 6. Automatic GitHub Release

The tag-triggered workflow verifies that the tag is annotated, matches the
version in `pyproject.toml`, and points to a commit contained in `origin/main`.
It takes the corresponding section from `CHANGELOG.md` and creates the GitHub
Release. A rerun keeps an already-created release instead of duplicating it.

Inspect the workflow result in Actions and the release notes in GitHub Releases.
This automation creates the GitHub Release only; package-index publishing is
not configured.
