# CI and releases

Pull requests targeting `main` and pushes to `main` run the same checks:

- Python lint for syntax errors and fatal constructs, plus Bash syntax checks.
- The full `run_tests.sh` suite: migrations, API, analytics, notifier, collector,
  installer and frontend tests, followed by Svelte compile and type checks.
- A production frontend build and Docker builds for all six services.

Dependencies are installed from committed lockfiles. CI uses Python 3.13,
Node.js 22 and uv 0.11.16. Docker builds use the same contexts as Compose;
analytics and notifier require the repository root. Actions are pinned to
commit SHAs. PRs have read-only repository permissions and do not publish images.
Test reports are retained as workflow artifacts for 14 days.

The existing `npm run lint` command also checks full frontend formatting and
ESLint conventions. It currently reports formatting and ESLint debt and is not a required
CI step; frontend static validation runs through `npm run check` instead.

## Publish a version

After merging and checking that CI passed on `main`:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

Supported tags are `vMAJOR.MINOR.PATCH` and prereleases such as
`v1.2.0-rc.1`, `v1.2.0-beta.1` or `v1.2.0-alpha.1`. The release workflow rejects
other `v*` tags and commits that are not reachable from `main`. It repeats the
checks on the tagged commit before publishing anything.

Successful checks trigger Linux AMD64 builds and publication to GitHub Container
Registry using the built-in `GITHUB_TOKEN`, with `packages: write` limited to the
image jobs. No Docker Hub credentials or custom token are needed. Images are:

```text
ghcr.io/<owner>/<repository>/api:1.2.0
ghcr.io/<owner>/<repository>/collector:1.2.0
ghcr.io/<owner>/<repository>/migrations:1.2.0
ghcr.io/<owner>/<repository>/frontend:1.2.0
ghcr.io/<owner>/<repository>/analytics:1.2.0
ghcr.io/<owner>/<repository>/notifier:1.2.0
```

Each image also receives a `sha-<short-commit>` tag. Stable versions update
`latest`; prereleases retain their full version (for example `1.2.0-rc.1`) and do
not update `latest`. A GitHub release with generated notes is created only after
all six images publish successfully. Prereleases are marked accordingly.
Image publication across multiple services is not transactional: a failed
matrix job can leave some images published without a GitHub release. Rerun
failed jobs for that tag to finish the release.

The repository must permit Actions and package publication. For anonymous
container pulls, set each GHCR package's visibility to public after its initial
publication. Configure branch protection on `main` to require CI checks before
merging. The workflow does not deploy to running servers.

All service manifests and local package entries in lockfiles must match the root
`pyproject.toml` version. CI runs `scripts/check_version.py`; release validation
also requires the Git tag to match. The initial release is `v0.1.0`. For the next
release, update manifests and lockfiles together before creating an annotated tag.
The full test runner enables PostgreSQL ingestion and scoped retention integration
tests against its disposable test database.
