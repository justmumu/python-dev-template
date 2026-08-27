# Release process

This project ships versioned releases from `main` with a local tag that is pushed after the release PR merges. The flow is identical for every segment (patch, minor, major); only the segment name changes.

## Versioning policy

We follow [Semantic Versioning 2.0](https://semver.org/). During `0.x` we may break compatibility on minor bumps (SemVer permits this for initial development).

## Tooling

Version bumps go through the `bump-*` Make targets. Each target:

1. Calls `uv version --bump <segment>`, which rewrites `version = "…"` in `pyproject.toml` and updates `uv.lock`.
2. Regenerates `CHANGELOG.md` from Conventional Commits via `cz changelog --unreleased-version v<new-version>` (commitizen).
3. Commits the change on the current branch.
4. Creates an annotated tag `v<new-version>` locally.
5. Prints the exact push commands you need to run next.

The tag is **not** pushed automatically — that is the final step of the release flow, and only happens after the bump PR is merged into `main`.

Because the changelog is generated from commit history, keeping Conventional Commit subjects accurate is what makes releases self-documenting. `make changelog` regenerates `CHANGELOG.md` at any time without bumping.

**Never hand-edit `CHANGELOG.md`** — every bump regenerates the file in full from commit history, so manual edits are silently lost on the next release. If an entry reads badly, fix the commit subject (rebase/amend before merge), not the changelog.

The `bump-*` targets refuse to run on a dirty working tree — commit or stash first, so unrelated edits can't leak into the bump commit.

## Step-by-step flow

All steps below assume a clean working tree and that `main` is up to date.

### 1. Create the release branch

```bash
git switch main
git pull
git switch -c chore/bump-v<new-version>
```

Pick `<new-version>` by knowing the current version (`make version`) and the segment you intend to bump.

### 2. Bump

```bash
make bump-patch     # or bump-minor, or bump-major
```

This creates the bump commit (version + `CHANGELOG.md`) and the `v<new-version>` tag locally. The target prints the next commands you need to run — follow them.

If you picked the wrong segment, `git reset --hard HEAD~1 && git tag -d v<wrong>` before pushing, then re-run.

**If review requires changes after the bump:** the bump commit must stay the last commit on the branch (the tag points at it, and the changelog must include every commit). Drop and redo: `git tag -d v<new>`, `git reset --hard HEAD~1`, apply the review fixes as normal commits, then re-run `make bump-<segment>`. If the branch was already pushed, update it with `git push --force-with-lease`.

### 3. Push the branch only

```bash
git push -u origin chore/bump-v<new-version>
```

Do **not** push the tag yet. Pushing the tag before the branch is merged would create a tag that points at a commit on a feature branch — if the branch gets rebased or the merge commit changes SHAs, the tag becomes orphaned.

### 4. Open and merge the PR

- Title: `chore: bump version to v<new-version>`.
- Walk the PR checklist in `docs/contributing/pr-checklist.md`. `make check` and `make docs-build` must pass.
- Merge with a regular merge commit (never squash). Squashing changes the bump-commit SHA and orphans the local `v<new-version>` tag.

### 5. Push the tag

Once the PR is merged and `main` contains the bump commit:

```bash
git switch main
git pull
git push origin v<new-version>
```

Pushing the tag is what makes the release "real" — downstream tooling keys off tags, not off the commit.

### 6. GitHub Release (automatic)

Pushing the tag triggers the `Release` workflow (`.github/workflows/release.yml`), which creates the GitHub Release automatically with the matching `CHANGELOG.md` section as release notes. Verify it appeared under **Releases**.

Manual fallback (workflow failed or Actions disabled): **Releases → Draft a new release**, pick the tag, paste the matching section from `CHANGELOG.md`.
