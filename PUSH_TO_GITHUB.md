# Push to GitHub — step by step

Repo: **https://github.com/balaprasannagopalvolisetty/placeupcareers.git**

Run these on your Windows machine. I cannot push from here because I
don't have your GitHub credentials.

## 0. Make sure git is installed and you're authenticated

```powershell
git --version
# Then either set up SSH (https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
# OR install GitHub CLI and run `gh auth login`.
```

## 1. Initialize the repo from the project root

```powershell
cd D:\Development_Projects\PlaceUp
git init
git branch -M main
```

## 2. Verify what will be committed (sanity check — no secrets!)

```powershell
git add .
git status                          # eyeball the list
git ls-files -i --exclude-standard  # what's being IGNORED (good)
```

You should see in the *ignored* list:
- `backend/.env` (your real API keys)
- `backend/data/placeup.db` (130 MB, regenerates from H1B Excel anyway)
- `backend/.venv/`, `frontend/node_modules/` (huge)
- `Bala_Volisetty_Resume.pdf` (personal file)

If any of those show up in `git status`, **stop and double-check
`.gitignore`** — don't push secrets to a public repo.

## 3. First commit

```powershell
git commit -m "Initial commit: PlaceUp Career platform (backend + frontend + 23K H1B records)"
```

## 4. Add the remote and push

```powershell
git remote add origin https://github.com/balaprasannagopalvolisetty/placeupcareers.git
git push -u origin main
```

If GitHub asks for credentials, use a Personal Access Token (PAT) as the
password — your normal account password won't work for HTTPS push.
Create one at https://github.com/settings/tokens (scope: `repo`).

## 5. After-the-fact: rotate the API keys you pasted earlier

You shared your **Hunter** and **FinalScout** keys in chat. Even though
the `.env` file is gitignored, treat them as compromised:

1. https://hunter.io/api-keys → revoke + regenerate
2. https://finalscout.com/dashboard → revoke + regenerate
3. Update `backend/.env` with the new keys
4. Restart uvicorn

## 6. Subsequent pushes

```powershell
git add .
git commit -m "<short message>"
git push
```

## What's in this initial commit

- `backend/` — FastAPI app, SQLite schema, scraper, H1B Excel importer,
  contacts pipeline, JWT auth.
- `frontend/` — React 18 + Vite app, all dashboard pages, Vite proxy
  config, Tailwind v4 theme.
- `AGENT_CONTEXT.md` — full state-of-app document for any new dev/AI.
- `INTEGRATION.md` — original wire-up guide.
- `SCRAPING_ROADMAP.md` — LinkedIn / FinalScout reality check.
- `.gitignore` — excludes secrets, venv, node_modules, the 130 MB DB.

## What's NOT committed (intentional)

- `backend/data/placeup.db` — regenerates from `backend/H1b_US_DataLIst.xlsx`
  on first boot.
- `backend/data/exports/`, `backend/data/resumes/` — generated artifacts.
- `backend/data/.last_scrape_at` — the scheduler marker.
- `backend/.env`, `frontend/.env.local` — real credentials.
- `Bala_Volisetty_Resume.pdf` — your personal CV.
- `backend/.venv/`, `frontend/node_modules/` — install on each clone.
