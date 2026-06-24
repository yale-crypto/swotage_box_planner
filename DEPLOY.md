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

## Notes
- **Free tier sleeps** after ~15 min idle; the first request after that takes
  ~30 s to wake. Upgrade to a paid instance to keep it always-on.
- The 3-D view and fonts load from CDNs (Plotly, Google Fonts), so the deployed
  app needs public internet — which Render has by default.
- Future `git push`es auto-deploy (`autoDeploy: true`).
