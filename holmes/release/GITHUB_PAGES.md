# Publishing the interactive site on GitHub Pages (free)

The site in `release/site/` is plain static files (HTML, CSS, JS and JSON traces, about 30 MB with the trailer), so GitHub Pages can host it for free.
GitHub Pages is free for **public** repositories. `jev-swarm` is private, so publish the site from a separate public repository.

## 1. Create a public repository
On github.com: New repository → name it e.g. `irregulars` → **Public** → Create (no README needed).

## 2. Push the site folder to it
From the `jev-swarm/holmes` folder:

```bash
cp -R release/site /tmp/irregulars-site
cd /tmp/irregulars-site
touch .nojekyll                      # serve files as-is
git init -b main
git add .
git commit -m "The Irregulars: interactive case replays"
git remote add origin https://github.com/<your-user>/irregulars.git
git push -u origin main
```

## 3. Turn on Pages
Repository → **Settings** → **Pages** → *Build and deployment* → Source: **Deploy from a branch** → Branch: **main**, folder **/ (root)** → Save.
After a minute the site is live at `https://<your-user>.github.io/irregulars/`.

- Replays: `https://<your-user>.github.io/irregulars/`
- Blog (with the trailer embedded): `https://<your-user>.github.io/irregulars/blog.html`

## 4. Updating
Re-run the exporters, copy the folder again, commit and push:

```bash
python3 release/export_traces.py     # rebuild site/data from the benchmark runs
python3 release/build_blog.py        # rebuild site/blog.html from blog.md
```

## Notes
- Files must be under 100 MB each (the trailer is ~20 MB); the whole site is ~30 MB, well within Pages limits.
- Test locally first: `cd release/site && python3 -m http.server 8790`, then open http://localhost:8790.
- If you prefer, host the trailer on YouTube and replace `media/the_irregulars_trailer.mp4` links with the YouTube URL.
