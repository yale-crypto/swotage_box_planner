# Deploying Stowage to Render

The repo is already initialized, committed, and pointed at
`https://github.com/yale-crypto/swotage_box_planner.git` (branch `main`).
Two steps remain: **push to GitHub**, then **connect Render**.

---

## 1. Push to GitHub

The commit is ready locally; it just needs your GitHub auth. Pick one:

**Option A — Personal Access Token (quickest)**
Create a token at https://github.com/settings/tokens (scope: `repo`), then:

```bash
cd /Users/synapsemint/Downloads/box_packer
git push -u origin main
# Username: yale-crypto
# Password: <paste your token>   (NOT your account password)
```

macOS will offer to save it in the Keychain so you only do this once.

**Option B — GitHub CLI**
```bash
brew install gh
gh auth login          # follow the browser prompt
git push -u origin main
```

**Option C — SSH** (if you have an SSH key on GitHub)
```bash
git remote set-url origin git@github.com:yale-crypto/swotage_box_planner.git
git push -u origin main
```

---

## 2. Deploy on Render

The repo includes `render.yaml`, so Render configures everything automatically.

1. Go to https://dashboard.render.com → **New +** → **Blueprint**.
2. Connect your GitHub account and pick **swotage_box_planner**.
3. Render reads `render.yaml` and proposes a free **web service** named `stowage`.
   Click **Apply**.
4. First build takes ~1–2 min. When it finishes you get a public URL like
   `https://stowage.onrender.com`.

(If you'd rather not use the Blueprint: **New +** → **Web Service** → pick the
repo, then set Build = `pip install -r requirements-web.txt` and
Start = `gunicorn webapp.app:app --bind 0.0.0.0:$PORT`.)

---

## What was configured

| File | Purpose |
|------|---------|
| `render.yaml` | Render Blueprint — free web service, build/start commands, Python 3.12.7, health check on `/` |
| `Procfile` | Same start command, for portability to other hosts |
| `requirements-web.txt` | Slim production deps (**flask + gunicorn only** — the web app doesn't need matplotlib/pytest) |
| `.python-version` | Pins Python 3.12.7 |
| `.gitignore` | Excludes `.venv/`, caches, OS junk |

Verified locally with the exact production command
(`gunicorn webapp.app:app`): `/`, `/api/pack`, and static assets all return 200.

---

## Cold starts (the slow first load)

A free service sleeps after ~15 minutes idle, and the next visitor waits
30-60s for a cold Python boot **before a single byte is served**. No code
change fixes this; it is a property of the plan. Two ways out:

**Pay for it.** A paid instance never sleeps. This is the only reliable fix,
and the only one that leaves the free instance-hour allowance alone.

**Keep it warm with traffic.** `.github/workflows/keep-warm.yml` pings
`/healthz` every 5 minutes. Set the repo variable `STOWAGE_URL` (Settings ->
Secrets and variables -> Actions -> Variables) to the service origin, e.g.
`https://stowage.onrender.com`, or the workflow no-ops. Know what it costs:

| | |
|---|---|
| Render instance hours | A warm instance runs ~730 h/month against the 750 h free allowance. Nearly all of it, spent on fast first loads. |
| GitHub Actions minutes | Free on public repos. On a **private** repo each run bills a 1-minute minimum — ~8,600 min/month against a 2,000-minute allowance. Use an external pinger there (cron-job.org, UptimeRobot); same effect, no minutes. |
| Reliability | Scheduled workflows are best-effort and GitHub delays them under load, sometimes past the 15-minute sleep window. This *reduces* cold starts rather than eliminating them. |
| Repo activity | GitHub disables scheduled workflows after 60 days without repo activity. |

## Front-end assets

Plotly is **self-hosted and gl3d-only** (`webapp/static/vendor/`), served by the
`/vendor/<file>` route: the full bundle is 4.5 MB (1.3 MB gzipped) for a library
this app uses two trace types from, against 1.7 MB (0.5 MB gzipped) for the
partial build. The route serves the `.gz` sitting beside the file when the
client accepts gzip — self-hosting only beats a CDN if the bytes are compressed,
and nothing in front of this app compresses for us. Filenames carry their
version, so responses are `immutable` with a one-year max-age.

To upgrade Plotly: drop the new `plotly-gl3d-<version>.min.js` in that
directory, `gzip -9 -k` it, and point the `<script>` in `index.html` at the new
filename. Keep both files — the `.gz` is not generated at runtime.

Fonts still come from Google Fonts, so the deployed app needs public internet.

## Notes
- Future `git push`es auto-deploy (`autoDeploy: true`).
- `/healthz` is the liveness probe: no template, no packing.
- Request limits (problem size, rate limit, search budget) live in
  `webapp/app.py` and are all environment-overridable; `render.yaml` sets the
  ones that differ from the defaults.
