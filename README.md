# Switch Icons — Nintendo Switch Icon Archive

A searchable, browsable archive of every base-game icon on the Nintendo Switch eShop — 18,701 titles at time of writing.

## What it is
- **`index.html` / `style.css` / `app.js`** — a plain static site, no build step, no framework.
- **`data.json`** — a compact dataset (title, publisher, categories, release date, and an icon reference) built from the open-source [titledb](https://github.com/blawar/titledb) project (MIT licensed).
- **`scripts/build_data.py`** — regenerates `data.json` from a fresh copy of titledb.
- **`.github/workflows/update.yml`** — runs that script every day and redeploys automatically (see below).
- Icons are **not stored in this project**. Every tile hotlinks directly to Nintendo's own eShop CDN (`img-eshop.cdn.nintendo.net`), the same servers the Switch itself and the Nintendo eShop website use. Nothing is downloaded or rehosted.

## Does it update itself?
Not out of the box — `data.json` is a snapshot from whenever it was generated. But the included GitHub Actions workflow will keep it current for you automatically if you host on GitHub Pages (see below): every day it re-runs `build_data.py` against the latest titledb data, commits `data.json` if anything changed, and redeploys the site. No server, database, or always-on process required — it only runs briefly once a day on GitHub's infrastructure, which is free for public repos.

If you host elsewhere instead, you can still run `python3 scripts/build_data.py` manually (or on your own schedule) whenever you want fresh data — see [Keeping it up to date](#keeping-it-up-to-date).

## Running it locally
Any static file server works, e.g.:
```
python3 -m http.server 8000
```
then open `http://localhost:8000`.

You can't just double-click `index.html` — browsers block the `fetch("data.json")` call on the `file://` protocol, so it needs to be served over `http://`.

## Hosting it for free

**GitHub Pages (recommended — pairs with the auto-updater above):**
1. Create a new GitHub repository and push this whole folder to it.
2. In the repo, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
3. That's it — the included workflow (`.github/workflows/update.yml`) builds and deploys the site on every push, and again automatically every day at 06:00 UTC to pick up new titledb data. Your site will be live at `https://<your-username>.github.io/<repo-name>/`.
4. You can also trigger a deploy manually any time from the repo's **Actions** tab → "Update data and deploy" → **Run workflow**.

**Alternatives (no auto-updates built in, but just as free):**
- **Netlify / Vercel / Cloudflare Pages** — drag-and-drop the folder for an instant deploy, or connect the GitHub repo for deploys on every push. All have generous free tiers that comfortably cover a static site this size (~3 MB total).

## Keeping it up to date manually
If you're not using the GitHub Action, regenerate the dataset yourself any time — the script only needs Python's standard library, nothing to install:
```
python3 scripts/build_data.py --out data.json
```
This re-pulls titledb's `US.en.json`, filters for base games with valid icons, and rewrites `data.json` in place.

## Notes on scope
This build uses the **US/English** listing from titledb. Nintendo's catalog varies by region — a Japan-only or Europe-only title won't show up here. You can point `build_data.py --region` at a different titledb region file (e.g. `JP.ja`, `GB.en`) or extend the script to merge several regions if you want broader coverage.

Unofficial fan project. Not affiliated with or endorsed by Nintendo. All icons, names, and artwork are property of Nintendo and their respective publishers.
