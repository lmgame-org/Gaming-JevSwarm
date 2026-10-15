"""Render blog.md to site/index.html, the staged blog: the trailer up top and each section's clip and table placed in
it (a tiny Markdown subset: headings, paragraphs, lists, tables, bold, italic, rules)."""
import html

from brand_head import icons, social
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\(((?:https?://|[\w-]+\.html)[^)\s]*)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def video(src, cap):
    poster = "poster_" + src.replace(".mp4", ".jpg")
    return (f'<figure><video controls preload="metadata" playsinline poster="media/{poster}" src="media/{src}"></video>'
            f"<figcaption>{cap}</figcaption></figure>")


def image(src, cap):
    return f'<figure><a href="media/{src}"><img src="media/{src}" alt="{html.escape(cap)}"></a><figcaption>{cap}</figcaption></figure>'


# the two roles, each with clickable choices; the pairing picked shows its results (Tables 1 and 2)
ROLES = """<figure class="roles" id="roles">
<div class="case-tabs" role="tablist" aria-label="Case set"><button role="tab" data-c="std" aria-selected="true">Standard cases (rare, isolated lies)</button><button role="tab" data-c="lie" aria-selected="false">Frame-up cases (organised lies)</button></div>
<div class="role"><img src="media/role_holmes.jpg" alt="Holmes"><b>Holmes</b><span>the one who reasons and decides:</span>
<select class="pick" data-role="h" autocomplete="off" aria-label="Who plays Holmes"><option value="astra">GPT6-Astra</option><option value="jev">Jev</option><option value="rule">a rule-based heuristic</option><option value="none">nobody at all</option></select></div>
<div class="role"><img src="media/role_irregulars.jpg" alt="The Irregulars"><b>The Irregulars</b><span>the many who search:</span>
<select class="pick" data-role="i" autocomplete="off" aria-label="Who plays the Irregulars"><option value="jev">Jev agents</option><option value="rule">a rule-based heuristic</option><option value="none">nobody (Holmes works alone)</option></select></div>
<figcaption><span id="roles-out"></span><br>Two roles, and we let different models and algorithms play each one. Choose a case set and one player for each role.</figcaption></figure>
<script>
(function () {
  const R = {  // [name, standard solved /100, frame-up solved /100]
    "astra|jev": ["Holmes (GPT6-Astra) + Jev Swarm", 96, 93], "astra|none": ["The Lone Genius (GPT6-Astra)", 57, 59],
    "jev|none": ["The Lone Genius (Jev)", 25, 14], "rule|jev": ["Holmes (heuristic) + Jev Swarm", 95, 0],
    "rule|rule": ["Holmes (heuristic) + heuristic Swarm", 97, 1], "rule|none": ["The Lone Genius (heuristic)", 61, 4],
    "none|jev": ["Jev Swarm (100 boys, no leader)", 38, 42], "none|rule": ["heuristic Swarm (100 boys, no leader)", 95, 1]};
  const pick = {h: "astra", i: "jev", c: "std"}, out = document.getElementById("roles-out");
  function show() {
    document.querySelectorAll("#roles .case-tabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.c === pick.c));
    const k = pick.h + "|" + pick.i, r = R[k], std = pick.c === "std";
    out.innerHTML = k === "none|none" ? "Somebody has to do the work, so choose a Holmes, some Irregulars, or both."
      : r ? `<b>${r[0]}</b> solved <b>${std ? r[1] : r[2]}</b> of 100 ${std ? "standard cases, in which any lie is a lone witness" : "frame-up cases, in which bribed witnesses tell the same lie"}.`
      : "We did not run this pairing.";
  }
  document.querySelectorAll("#roles .case-tabs button").forEach(b => b.addEventListener("click", () => { pick.c = b.dataset.c; show(); }));
  document.querySelectorAll("#roles .pick").forEach(sel => { sel.value = pick[sel.dataset.role];
    sel.addEventListener("change", () => { pick[sel.dataset.role] = sel.value; show(); }); });
  show();
})();
</script>"""


# what each section shows, placed right under its heading
MEDIA = {
    "solo": [video("irregulars_clip1_astra.mp4", "The Lone Genius on case 57. It never reaches the address that holds the deciding clue.")],
    "swarm": [video("irregulars_clip3_jev_swarm.mp4", "The Jev Swarm on case 57. Each colour shows one answer that the boys are voting for.")],
    "holmes": [video("irregulars_clip2_astra_jev_swarm.mp4", "Holmes (GPT6-Astra) + Jev Swarm on case 57. Holmes plans at 221B while the boys search the city.")],
    "sg": ['<link rel="stylesheet" href="sg.css?v=10"><figure class="wide"><div id="sg" data-kind="standard" data-seed="57"></div>'
           "<figcaption>Figure 1. How each detective spreads out over the city and gathers the evidence back into an answer, shown for case 57 "
           "(you can pick any other case). Each row is a district of London and each thin line is one agent moving through the city; the diamonds and ticks mark decisions, and the coloured lines carry evidence to the answer. "
           "You can zoom in with the + button or a double-click.</figcaption></figure>"
           '<script src="sg.js?v=10" defer></script>'],
    "case": [image("case57_soho.jpg", "Soho, the night of the murder: the doctor's bag, the bootprints and the knife, suspects in the street, and a red glow far to the west.")],
    "roles": [ROLES],
    "t1": [image("irregulars_standard_setting_results.png", "Table 1. Results on the 100 standard cases.")],
    "t2": [image("irregulars_challenging_setting_results.png", "Table 2. Results on the 100 frame-up cases, in which bribed witnesses tell the same lie.")],
    "t3": [image("irregulars_solo_24h_table.png", "Table 3. The Lone Genius with twice as much time and twice as many visits.")],
}
HOOK_END = ""
DESC = "One large reasoning model (GPT6-Astra), a swarm of small, fast agents (Jev), and the reasoner leading the swarm, on 200 simulated murder cases."


def convert(md):
    out, lines, i, sections = [], md.split("\n"), 0, 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            sections += 1
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("{{media:"):
            out += MEDIA[ln.strip()[8:-2]]
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif re.match(r"^\d+\. ", ln):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                items.append(f"<li>{inline(lines[i].split('. ', 1)[1])}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[-| ]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        elif ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|- |\d+\. |\||---|\{\{)", lines[i + 1]):
                i += 1
                para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{icons}
<meta name="description" content="One large reasoning model (GPT6-Astra), a swarm of small, fast agents (Jev), and the reasoner leading the swarm, on 200 simulated murder cases.">{social}<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
body {{ margin: 0; background: #faf6ec; color: #241a10; font: 18px/1.7 "Libre Baskerville", Georgia, serif; }}
main {{ max-width: {width}px; margin: 0 auto; padding: 28px 16px 80px; }}
h1 {{ font-size: 34px; line-height: 1.25; margin-bottom: 8px; }} h2 {{ font-size: 24px; margin-top: 42px; }}
hr {{ border: none; border-top: 1px solid #d8ccb0; margin: 32px 0; }}
table {{ border-collapse: collapse; width: 100%; font: 15px/1.4 Inter, sans-serif; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8ccb0; padding: 8px; text-align: right; }} th:first-child, td:first-child {{ text-align: left; }}
@media (max-width: 520px) {{ table {{ font-size: 12.5px; }} th, td {{ padding: 6px 4px; }} }}
li {{ margin: 6px 0; }} a {{ color: #8a1c1c; }}
figure {{ margin: 22px 0 30px; }} figure img, figure video {{ width: 100%; border-radius: 6px; display: block; background: #111; }}
figcaption {{ font: 14px/1.5 Inter, sans-serif; color: #6b5c45; margin-top: 8px; }}
nav.top {{ font: 15px Inter, sans-serif; display: flex; flex-wrap: wrap; gap: 18px; align-items: center; padding-bottom: 14px;
  margin-bottom: 22px; border-bottom: 1px solid #d8ccb0; }}
nav.top b {{ font-family: "Libre Baskerville", Georgia, serif; font-weight: 400; margin-right: auto; }}
nav.top a {{ text-decoration: none; }} nav.top a.on {{ color: #241a10; border-bottom: 2px solid #8a1c1c; }}
.back {{ font: 14px Inter, sans-serif; }} video {{ width: 100%; border-radius: 6px; }}
.lead {{ font-size: 17px; color: #4a3d2c; }}
figure.roles {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 12px 48px; }} .role {{ width: 230px; text-align: center; font: 15px/1.4 Inter, sans-serif; }} .role img {{ width: 190px; height: 190px; display: block; margin: 0 auto 8px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.18); }} .role b {{ display: block; font: 700 18px "Libre Baskerville", Georgia, serif; }} .role span {{ color: #6b5c45; }} figure.roles figcaption {{ flex-basis: 100%; text-align: center; }} .case-tabs {{ flex-basis: 100%; display: flex; justify-content: center; gap: 0; margin-bottom: 4px; }} .case-tabs button {{ font: 14px Inter, sans-serif; padding: 6px 12px; border: 1px solid #cdbf9f; background: #fff; color: #4a3d2c; cursor: pointer; }} .case-tabs button:first-child {{ border-radius: 6px 0 0 6px; }} .case-tabs button:last-child {{ border-radius: 0 6px 6px 0; border-left: 0; }} .case-tabs button[aria-selected="true"] {{ background: #8a1c1c; border-color: #8a1c1c; color: #fff; }} .pick {{ display: block; margin: 6px auto 0; max-width: 100%; font: 14px Inter, sans-serif; padding: 5px 8px; border: 1px solid #cdbf9f; border-radius: 6px; background: #fff; color: #241a10; cursor: pointer; }} .pick:hover, .pick:focus {{ border-color: #8a1c1c; outline: none; }} #roles-out {{ display: inline-block; margin-top: 4px; font-size: 15px; color: #241a10; }} @media (max-width: 520px) {{ figure.roles {{ gap: 12px 16px; }} .role {{ width: 150px; font-size: 13px; }} .role img {{ width: 120px; height: 120px; }} }}
p > b:first-child, li > b:first-child {{ font-weight: 700; color: #8a1c1c; }}
</style></head><body><main>
"""


def nav(on):
    links = [("index.html", "Home"), ("trailer.html", "Trailer"), ("blog.html", "Blog"), ("results.html", "Results")]
    items = "".join(f'<a href="{h}" class="{"on" if h == on else ""}">{t}</a>' for h, t in links)
    return f'<nav class="top"><b>The Irregulars</b>{items}</nav>'


def write(name, title, body, width=720):
    page = HEAD.format(title=title, width=width, icons=icons(),
                       social=social(title, DESC, name)) + nav(name) + body + "</main></body></html>"
    open(os.path.join(HERE, "site", name), "w").write(page)
    print("site/" + name)


def main():
    blog = convert(open(os.path.join(HERE, "blog.md")).read())
    write("blog.html", "Catch Murderer with Jev Swarm — A Detective Game Case Study",
          blog + '<p class="back"><a href="trailer.html">Watch the trailer</a> \u00b7 '
          '<a href="results.html">Results, and a replay of every case (try case 57): every move, clue and vote &rarr;</a></p>')
    write("trailer.html", "Trailer | The Irregulars", """
<h1>The Irregulars: the trailer</h1>
<p class="lead">Can a Jev swarm catch a murderer? Three ways to solve a murder in Victorian London: GPT6-Astra alone, GPT6-Astra leading
a swarm of Jev agents, and a leaderless Jev swarm. Every move in the trailer is from a real benchmark run.</p>
<figure><video controls preload="metadata" playsinline poster="media/poster_trailer.jpg" src="media/the_irregulars_trailer.mp4?v=8"></video>
<figcaption>1:35. Narration: synthesised speech; music: an original score generated in code.</figcaption></figure>"""
          + '<p class="back"><a href="blog.html">Read the blog &rarr;</a></p>', width=900)



if __name__ == "__main__":
    main()
