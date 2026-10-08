# Publishing the site at https://snyhlx.github.io/the_irregulars_detective_game/

GitHub Pages does not hand out subdomains like `something.snyhlx.github.io`. Everything under your account is served as a
**path** on `snyhlx.github.io`, so the address will be:

    https://snyhlx.github.io/the_irregulars_detective_game/          (replays)
    https://snyhlx.github.io/the_irregulars_detective_game/blog.html (blog + trailer)

Your user site (`snyhlx/snyhlx.github.io`, branch `main`, root folder) is already live, so either option below works.
The site is static (HTML/CSS/JS + JSON traces + the trailer, ~30 MB).

## Option A (recommended): a project repo with the same name
A repository called `the_irregulars_detective_game` with Pages turned on is served automatically at
`snyhlx.github.io/the_irregulars_detective_game/`, and it keeps the 30 MB of traces out of your main site's repo.

```bash
cd jev-swarm/holmes
rm -rf /tmp/the_irregulars_detective_game && cp -R release/site /tmp/the_irregulars_detective_game
cd /tmp/the_irregulars_detective_game
touch .nojekyll
git init -b main && git add . && git commit -m "The Irregulars detective game: replays, blog, trailer"
gh repo create snyhlx/the_irregulars_detective_game --public --source . --push
gh api -X POST repos/snyhlx/the_irregulars_detective_game/pages -f "source[branch]=main" -f "source[path]=/"
```

(Or in the browser: create the repo, push, then Settings → Pages → Deploy from a branch → `main` / root.)
Pages from a private repo also works on your plan; drop `--public` if you want the source private.

## Option B: a folder inside snyhlx.github.io
Everything in the user-site repo is served as-is, so a folder becomes a path:

```bash
git clone https://github.com/snyhlx/snyhlx.github.io.git /tmp/userpage
cp -R jev-swarm/holmes/release/site /tmp/userpage/the_irregulars_detective_game
cd /tmp/userpage && git add the_irregulars_detective_game && git commit -m "Add The Irregulars detective game" && git push
```

If that repo builds with Jekyll (it does unless it has a `.nojekyll`), the folder is still copied through unchanged.

## A real subdomain
Only with your own domain: add a `CNAME` file (e.g. `irregulars.example.com`) to the project repo, set the domain under
Settings → Pages, and create a DNS CNAME record `irregulars → snyhlx.github.io`.

## Updating
```bash
python3 release/export_traces.py   # rebuild site/data from the benchmark runs
python3 release/build_blog.py      # rebuild site/blog.html from blog.md
```
then copy `release/site` again, commit and push. Test locally first: `cd release/site && python3 -m http.server 8790`.
