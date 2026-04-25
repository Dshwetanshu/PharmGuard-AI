# GitHub Setup Guide

How to push PharmGuard AI to a new GitHub repository for your submission.

## Prerequisites

- A GitHub account
- `git` installed on your Mac (macOS usually ships with it — check with `git --version`)

---

## Step 1 — Create a new repository on GitHub

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `pharmguard-ai`
3. **Description:** `An agentic RAG system for drug interaction detection. Final project for Generative AI Discovery, Spring 2026.`
4. **Public** (so your professor can access it without an invite)
5. **Leave all other options unchecked** (no README, no .gitignore, no license — we already have them)
6. Click **Create repository**

GitHub will show you a page with commands. Ignore them; use the ones below instead.

---

## Step 2 — Initialize the repository locally

Open Terminal and navigate to your project folder:

```bash
cd ~/Downloads/files-2/pharmguard-ai
```

Initialize git:

```bash
git init
git branch -M main
```

---

## Step 3 — Make sure your `.env` is NOT committed

**Critical.** Your `.env` has your API key and must never be pushed to a public repo. The `.gitignore` file already excludes it, but double-check:

```bash
cat .gitignore | grep env
```

Should print `.env`. If it doesn't, add it:

```bash
echo ".env" >> .gitignore
```

Also run this to preview what git is about to track:

```bash
git status --ignored
```

Confirm `.env` appears under "Ignored files" and NOT under "Untracked files."

---

## Step 4 — Stage and commit

```bash
git add .
git commit -m "Initial commit: PharmGuard AI final project"
```

Expected output: something like `81 files changed, 6500 insertions(+)`.

---

## Step 5 — Connect to GitHub and push

Replace `YOUR_USERNAME` with your actual GitHub username:

```bash
git remote add origin https://github.com/YOUR_USERNAME/pharmguard-ai.git
git push -u origin main
```

First push will ask for authentication. On modern GitHub you use a **Personal Access Token** instead of your password:

### If prompted for a password

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Name it "pharmguard-ai"
4. Scopes: check **repo** (full control of private repositories)
5. Generate, copy the token
6. Paste it as the password when git asks

Save the token in your password manager — you'll need it again if you push updates.

---

## Step 6 — Verify

Open your new repo in a browser:

```
https://github.com/YOUR_USERNAME/pharmguard-ai
```

You should see the project tree with README.md rendered on the homepage.

---

## Step 7 — Update placeholder URLs

Four files have `YOUR_USERNAME` placeholders that need your actual GitHub username:

```bash
grep -rl "YOUR_USERNAME" --include="*.md" --include="*.html"
```

Edit each and replace `YOUR_USERNAME` with your handle. Then commit:

```bash
git add .
git commit -m "Update GitHub URLs"
git push
```

---

## Step 8 — Optional: Enable GitHub Pages for the showcase site

Your project includes a standalone HTML showcase page at `website/index.html`. To publish it as a live site:

1. On your repo page, go to **Settings** → **Pages**
2. **Source:** Deploy from a branch
3. **Branch:** `main`, folder `/website`
4. Click **Save**

Within ~60 seconds, your site is live at:
```
https://YOUR_USERNAME.github.io/pharmguard-ai/
```

Add this URL to the YouTube description of your demo video.

---

## Step 9 — Submit to Canvas/your course portal

Per the assignment:
- **GitHub URL:** `https://github.com/YOUR_USERNAME/pharmguard-ai`
- **Documentation PDF:** `docs/PharmGuard_AI_Documentation.pdf` in the repo (or upload separately)
- **Video:** YouTube URL (unlisted is fine)
- **Web page:** GitHub Pages URL from Step 8

---

## Common issues

### "remote: Support for password authentication was removed"
Use a Personal Access Token (see Step 5).

### "error: src refspec main does not match any"
You forgot to commit. Run `git add . && git commit -m "first commit"` first.

### `.env` accidentally pushed
```bash
git rm --cached .env
git commit -m "Remove accidentally committed .env"
git push
```
Then **rotate your API key immediately** — it's in the public git history.

### Large files rejected
Data files over 100MB will fail. Check:
```bash
find . -type f -size +50M -not -path "./prompt_final/*"
```
The sample data in this project is tiny; you should only see issues if you've ingested real TWOSIDES. If so, those processed files are in `.gitignore` already.

### `prompt_final/` virtualenv tracked
The `.gitignore` excludes it. If it still shows up as tracked:
```bash
git rm -r --cached prompt_final
git commit -m "Stop tracking virtualenv"
git push
```

---

## Final checklist before submission

- [ ] Repo is **Public**
- [ ] `README.md` renders on the homepage
- [ ] `docs/PharmGuard_AI_Documentation.pdf` is in the repo
- [ ] `examples/` folder has 8 example outputs
- [ ] `data/sample/` has 7 CSV files (drug_vocabulary, interactions, ddinter, side_effects, ade_corpus, reviews, uci_reviews)
- [ ] `.env` is NOT in the repo (check it's absent on the GitHub page)
- [ ] All `YOUR_USERNAME` placeholders are replaced
- [ ] GitHub Pages site is live (optional but recommended)
- [ ] YouTube video uploaded and linked in README
