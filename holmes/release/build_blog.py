"""Render blog.md to site/index.html, the staged blog: the trailer up top and each section's clip and table placed in
it (a tiny Markdown subset: headings, paragraphs, lists, tables, bold, italic, rules)."""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def inline(s):
    s = html.escape(s, quote=False)
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
    "1.": [video("irregulars_clip1_astra.mp4", "The Lone Genius (GPT6-Astra) on case 57: one cab, one door at a time. It runs out of visits."),
           image("irregulars_solo_24h_table.png", "Table 3. The Lone Genius with twice the time and visits.")],
    "2.": [video("irregulars_clip3_jev_swarm.mp4", "The Jev Swarm on case 57: boys coloured by the answer they vote for. "
                 "It converges in about 4 case hours, on the wrong culprit.")],
    "3.": [video("irregulars_clip2_astra_jev_swarm.mp4", "Holmes (GPT6-Astra) + Jev Swarm on case 57: Holmes plans at 221B, twelve "
                 "Jev boys run errands. Solved in 10.5 case hours."),
           image("irregulars_challenging_setting_results.png", "Table 2. Frame-up cases: somebody lies.")],
}
HOOK_END = image("irregulars_standard_setting_results.png", "Table 1. Standard cases, 100 each.")


def convert(md):
    out, lines, i, sections = [], md.split("\n"), 0, 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            if sections == 0:  # the results table closes the hook
                out.insert(len(out) - 1 if out and out[-1] == "<hr>" else len(out), HOOK_END)
            sections += 1
            out.append(f"<h2>{inline(ln[3:])}</h2>")
            out += MEDIA.get(ln[3:].split(" ")[0], [])
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
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
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|- |\||---)", lines[i + 1]):
                i += 1
                para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


def main():
    body = convert(open(os.path.join(HERE, "blog.md")).read())
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>One Genius or Many Minds? | The Irregulars</title>
<meta name="description" content="A lone reasoning model, a reasoning leader with a swarm of small agents, and a leaderless swarm, in 200 simulated murder mysteries."><link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital@0;1&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
body {{ margin: 0; background: #faf6ec; color: #241a10; font: 18px/1.7 "Libre Baskerville", Georgia, serif; }}
main {{ max-width: 720px; margin: 0 auto; padding: 40px 16px 80px; }}
h1 {{ font-size: 34px; line-height: 1.25; margin-bottom: 8px; }} h2 {{ font-size: 24px; margin-top: 42px; }}
hr {{ border: none; border-top: 1px solid #d8ccb0; margin: 32px 0; }}
table {{ border-collapse: collapse; width: 100%; font: 15px/1.4 Inter, sans-serif; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8ccb0; padding: 8px; text-align: right; }} th:first-child, td:first-child {{ text-align: left; }}
li {{ margin: 6px 0; }} a {{ color: #8a1c1c; }}
figure {{ margin: 22px 0 30px; }} figure img, figure video {{ width: 100%; border-radius: 6px; display: block; background: #111; }}
figcaption {{ font: 14px/1.5 Inter, sans-serif; color: #6b5c45; margin-top: 8px; }}
nav.top {{ font: 14px Inter, sans-serif; display: flex; justify-content: space-between; margin-bottom: 18px; }}
.back {{ font: 14px Inter, sans-serif; }} video {{ width: 100%; border-radius: 6px; margin: 10px 0 20px; }}
</style></head><body><main>
<nav class="top"><span>The Irregulars</span><a href="replay.html">Replay all 200 cases &rarr;</a></nav>
<video controls preload="metadata" playsinline poster="media/poster_trailer.jpg" src="media/the_irregulars_trailer.mp4"></video>
{body}
<p class="back"><a href="replay.html">Replay every case interactively: every move, clue and vote &rarr;</a></p>
</main></body></html>"""
    open(os.path.join(HERE, "site", "index.html"), "w").write(page)
    print("site/index.html")


if __name__ == "__main__":
    main()
