"""Render blog.md to site/index.html, the staged blog: the trailer up top and each section's clip and table placed in
it (a tiny Markdown subset: headings, paragraphs, lists, tables, bold, italic, rules)."""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def video(src, cap):
    poster = "poster_" + src.replace(".mp4", ".jpg")
    return (f'<figure><video controls preload="metadata" playsinline poster="media/{poster}" src="media/{src}"></video>'
            f"<figcaption>{cap}</figcaption></figure>")


def image(src, cap):
    return f'<figure><a href="media/{src}"><img src="media/{src}" alt="{html.escape(cap)}"></a><figcaption>{cap}</figcaption></figure>'


# what each section shows, placed right under its heading
MEDIA = {
    "solo": [video("irregulars_clip1_astra.mp4", "The Lone Genius on case 57. It never reaches the address that holds the deciding clue.")],
    "swarm": [video("irregulars_clip3_jev_swarm.mp4", "The Jev Swarm on case 57. Each colour shows one answer that the boys are voting for.")],
    "holmes": [video("irregulars_clip2_astra_jev_swarm.mp4", "Holmes (GPT6-Astra) + Jev Swarm on case 57. Holmes plans at 221B while the boys search the city.")],
    "sg": ['<link rel="stylesheet" href="sg.css?v=8"><figure class="wide"><div id="sg" data-kind="standard" data-seed="57"></div>'
           "<figcaption>Figure 1. How each detective spreads out over the city and gathers the evidence back into an answer, shown for case 57 "
           "(you can pick any other case). Each lane is one agent, the diamonds and ticks mark decisions, and the lines carry evidence to the answer. "
           "You can zoom in with the + button or a double-click.</figcaption></figure>"
           '<script src="sg.js?v=8" defer></script>'],
    "t1": [image("irregulars_standard_setting_results.png", "Table 1. Results on the 100 standard cases.")],
    "t2": [image("irregulars_challenging_setting_results.png", "Table 2. Results on the 100 frame-up cases, in which somebody lies.")],
    "t3": [image("irregulars_solo_24h_table.png", "Table 3. The Lone Genius with twice as much time and twice as many visits.")],
}
HOOK_END = ""


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
<link rel="icon" type="image/png" sizes="32x32" href="media/lmgame_icon_32.png"><link rel="icon" type="image/png" sizes="64x64" href="media/lmgame_icon_64.png"><link rel="apple-touch-icon" href="media/lmgame_icon_180.png">
<meta name="description" content="One large reasoning model (GPT6-Astra), a swarm of small, fast agents (Jev), and the reasoner leading the swarm, on 200 simulated murder cases."><link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
body {{ margin: 0; background: #faf6ec; color: #241a10; font: 18px/1.7 "Libre Baskerville", Georgia, serif; }}
main {{ max-width: {width}px; margin: 0 auto; padding: 28px 16px 80px; }}
h1 {{ font-size: 34px; line-height: 1.25; margin-bottom: 8px; }} h2 {{ font-size: 24px; margin-top: 42px; }}
hr {{ border: none; border-top: 1px solid #d8ccb0; margin: 32px 0; }}
table {{ border-collapse: collapse; width: 100%; font: 15px/1.4 Inter, sans-serif; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8ccb0; padding: 8px; text-align: right; }} th:first-child, td:first-child {{ text-align: left; }}
li {{ margin: 6px 0; }} a {{ color: #8a1c1c; }}
figure {{ margin: 22px 0 30px; }} figure img, figure video {{ width: 100%; border-radius: 6px; display: block; background: #111; }}
figcaption {{ font: 14px/1.5 Inter, sans-serif; color: #6b5c45; margin-top: 8px; }}
nav.top {{ font: 15px Inter, sans-serif; display: flex; flex-wrap: wrap; gap: 18px; align-items: center; padding-bottom: 14px;
  margin-bottom: 22px; border-bottom: 1px solid #d8ccb0; }}
nav.top b {{ font-family: "Libre Baskerville", Georgia, serif; font-weight: 400; margin-right: auto; }}
nav.top a {{ text-decoration: none; }} nav.top a.on {{ color: #241a10; border-bottom: 2px solid #8a1c1c; }}
.back {{ font: 14px Inter, sans-serif; }} video {{ width: 100%; border-radius: 6px; }}
.lead {{ font-size: 17px; color: #4a3d2c; }}
p > b:first-child, li > b:first-child {{ font-weight: 700; color: #8a1c1c; }}
</style></head><body><main>
"""


def nav(on):
    links = [("index.html", "Home"), ("trailer.html", "Trailer"), ("blog.html", "Blog"), ("results.html", "Results")]
    items = "".join(f'<a href="{h}" class="{"on" if h == on else ""}">{t}</a>' for h, t in links)
    return f'<nav class="top"><b>The Irregulars</b>{items}</nav>'


def write(name, title, body, width=720):
    page = HEAD.format(title=title, width=width) + nav(name) + body + "</main></body></html>"
    open(os.path.join(HERE, "site", name), "w").write(page)
    print("site/" + name)


def main():
    blog = convert(open(os.path.join(HERE, "blog.md")).read())
    write("blog.html", "One Leader, Many Minds: A Sherlock Holmes Detective Game Study",
          blog + '<p class="back"><a href="trailer.html">Watch the trailer</a> \u00b7 '
          '<a href="results.html">Results, and a replay of every case (try case 57): every move, clue and vote &rarr;</a></p>')
    write("trailer.html", "Trailer | The Irregulars", """
<h1>The Irregulars: the trailer</h1>
<p class="lead">One genius, or many minds? Three ways to solve a murder in Victorian London: GPT6-Astra alone, GPT6-Astra leading
a swarm of Jev agents, and a leaderless Jev swarm. Every move in the trailer is from a real benchmark run.</p>
<figure><video controls preload="metadata" playsinline poster="media/poster_trailer.jpg" src="media/the_irregulars_trailer.mp4"></video>
<figcaption>1:35. Narration: synthesised speech; music: an original score generated in code.</figcaption></figure>
<h2>The three runs, one case</h2>""" + video("irregulars_clip1_astra.mp4", "The Lone Genius (GPT6-Astra): unsolved, out of visits.")
          + video("irregulars_clip2_astra_jev_swarm.mp4", "Holmes (GPT6-Astra) + Jev Swarm: solved in 10.5 case hours.")
          + video("irregulars_clip3_jev_swarm.mp4", "Jev Swarm: converged in about 4 case hours, on the wrong culprit.")
          + '<p class="back"><a href="blog.html">Read the blog &rarr;</a></p>', width=900)



if __name__ == "__main__":
    main()
