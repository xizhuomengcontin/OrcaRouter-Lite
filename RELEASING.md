# Releasing

OrcaRouter Lite ships three artifacts. `.github/workflows/release.yml` publishes
all of them; this file covers the one-time setup each one needs and the steps to
cut a release.

| Artifact | Where | Published by |
|---|---|---|
| Container image | `ghcr.io/continuum-ai-corp/orcarouter-lite` | `release.yml` — `image` job |
| Python package | [pypi.org/p/orcarouter-lite](https://pypi.org/p/orcarouter-lite) | `release.yml` — `pypi` job |
| Railway template | [railway.com](https://railway.com) marketplace | manual, see below |

---

## One-time setup

### 1. PyPI — trusted publishing

The `pypi` job authenticates over OIDC, so there is no API token to store or
rotate. It will fail until PyPI knows about this repo.

At <https://pypi.org/manage/account/publishing/>, add a **pending publisher**:

| Field | Value |
|---|---|
| PyPI project name | `orcarouter-lite` |
| Owner | `Continuum-AI-Corp` |
| Repository name | `OrcaRouter-Lite` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

The environment name has to match the `environment: name: pypi` block in the
workflow. GitHub creates that environment on the first run; add reviewers to it
under **Settings → Environments** if releases should need approval.

`orcarouter-lite` was unclaimed on PyPI as of the last check — confirm it still
is before the first publish, because the name cannot be changed afterwards
without renaming the distribution.

### 2. GHCR — package visibility and repo link

The first push creates the package as **private**, owned by the org. Make it
public once:

**github.com/orgs/Continuum-AI-Corp/packages → orcarouter-lite → Package
settings → Change visibility → Public.**

While there, under **Manage Actions access**, confirm the `OrcaRouter-Lite`
repository has `Write` — that is what lets `GITHUB_TOKEN` push on later runs.
The `org.opencontainers.image.source` label in the Dockerfile is what links the
package back to this repo on the GHCR page.

No secrets are needed: the job uses the built-in `GITHUB_TOKEN` with
`packages: write`.

### 3. Railway — publish the template

Railway serves a real one-click deploy only for a **published template code**:
`https://railway.com/new/template/<code>`. A URL without one deploys nothing —
the legacy `?template=<github-url>` form the READMEs used to carry is dead, and
so is `/new/template` on its own; both render the generic marketplace page.

Codes cannot be minted from a repo URL. Railway's `templateGenerate` snapshots
an existing project, so the project has to exist first. The button in the
READMEs points at `https://railway.com/new` until then — it reaches Railway's
deploy flow, but costs the visitor two extra clicks.

1. Deploy the repo once: **railway.com → New Project → Deploy from GitHub repo
   → OrcaRouter-Lite**. `railway.toml` supplies the Dockerfile build, the
   `/health` check and the restart policy.
2. Add a **Volume** mounted at `/data`, then set the variables listed in the
   comments at the top of [`railway.toml`](./railway.toml) — at minimum
   `DATABASE_URL`, `CREDENTIAL_ENCRYPTION_KEY` and `API_KEY_PEPPER`. Whatever
   this project looks like is exactly what one-click deployers get, volume
   included, so get it healthy before moving on.
3. Create an account token at <https://railway.com/account/tokens> and run:

   ```bash
   export RAILWAY_TOKEN=...
   python scripts/publish_railway_template.py --list-projects
   python scripts/publish_railway_template.py --project-id <id> --write-readmes
   ```

   That snapshots the project (`templateGenerate`), publishes it
   (`templatePublish`), prints the code, and rewrites the Railway row in all
   twelve `README*.md` files to:

   ```md
   | Railway | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/YOURCODE?utm_medium=integration&utm_source=button&utm_campaign=orcarouter-lite) |
   ```

   Add `--dry-run` first to see the diff. If you would rather publish from the
   dashboard (**project → ⋯ → Create Template from Project**), the script still
   wires up the buttons: `--code YOURCODE --write-readmes`.

4. Commit the README change. From then on the button is genuinely one click.

---

## Cutting a release

1. Bump `version` in `pyproject.toml`. The `pypi` job refuses to publish if it
   does not match the tag, so this is the only place the number lives.
2. Merge to `main`. That publishes `ghcr.io/…:edge` (amd64) — a good check that
   the image job is healthy before you tag.
3. Tag and push:

   ```bash
   git tag -a v0.1.1 -m "v0.1.1"
   git push origin v0.1.1
   ```

That produces:

- `ghcr.io/continuum-ai-corp/orcarouter-lite:latest`, `:0.1.1`, `:0.1`,
  `:sha-<short>` — linux/amd64 + linux/arm64, with a provenance attestation
  (`gh attestation verify oci://… --repo Continuum-AI-Corp/OrcaRouter-Lite`)
- `orcarouter-lite 0.1.1` on PyPI (wheel + sdist)
- both dists attached to the GitHub release

Before publishing, the `pypi` job installs the wheel into a clean venv, boots
it, and fails the release if `/health` or the dashboard at `/` does not answer.
The `image` job runs the same smoke test against the pushed image.

### The already-tagged v0.1.0

`v0.1.0` was tagged before this workflow existed, and it cannot be released
as-is. `workflow_dispatch` runs the workflow file *from the ref you select*, and
that tag carries only `ci.yml` and `benchmark.yml` — there is no `release.yml`
at `v0.1.0` for the dispatch to run.

Cut `v0.1.1` instead. (Force-moving the `v0.1.0` tag onto a commit that has the
workflow would also work — nothing has consumed that tag yet — but re-pointing a
published tag is not a habit worth starting.)

### Rehearsing on a fork

The `image` job pushes to `ghcr.io/<whatever repo it runs in>`, so a fork can
exercise the whole thing against its own namespace with no secrets: enable
Actions on the fork, then either open a pull request (runs `ci.yml`, which
builds the image and boots it without pushing) or push to the fork's `main`
(runs `release.yml`, which publishes `:edge`). The `pypi` job is scoped to
`Continuum-AI-Corp`, so it skips on forks rather than failing at the OIDC
exchange.

Note that the **Run workflow** button only appears for workflows that exist on
the repository's default branch — until `release.yml` is merged to `main`, there
is nothing to dispatch.

## Local checks

CI's `package` job runs these on every PR, but to reproduce it:

```bash
python -m build
twine check --strict dist/*

python -m venv /tmp/verify
/tmp/verify/bin/pip install dist/*.whl
/tmp/verify/bin/orcarouter-lite --port 8123 &
curl -sf localhost:8123/health          # {"status":"ok"}
curl -sf localhost:8123/ | head -1      # <!DOCTYPE html> — dashboard came along
```

The last line is the one that matters: `design/` lives at the repo root but is
force-included into the wheel as `app/design/` (see the comment above
`[tool.hatch.build.targets.wheel]` in `pyproject.toml`). If that mapping is
dropped, everything still builds and boots — only the UI silently disappears.
