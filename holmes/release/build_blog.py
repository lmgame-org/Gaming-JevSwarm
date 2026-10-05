"""Render blog.md to site/blog.html (a tiny Markdown subset: headings, paragraphs, lists, tables, bold, italic, rules)."""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def convert(md):
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
        elif ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
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
<title>One Genius or Many Minds?</title><link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital@0;1&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
body {{ margin: 0; background: #faf6ec; color: #241a10; font: 18px/1.7 "Libre Baskerville", Georgia, serif; }}
main {{ max-width: 720px; margin: 0 auto; padding: 40px 16px 80px; }}
h1 {{ font-size: 34px; line-height: 1.25; margin-bottom: 8px; }} h2 {{ font-size: 24px; margin-top: 42px; }}
hr {{ border: none; border-top: 1px solid #d8ccb0; margin: 32px 0; }}
table {{ border-collapse: collapse; width: 100%; font: 15px/1.4 Inter, sans-serif; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8ccb0; padding: 8px; text-align: right; }} th:first-child, td:first-child {{ text-align: left; }}
li {{ margin: 6px 0; }} a {{ color: #8a1c1c; }}
.back {{ font: 14px Inter, sans-serif; }} video {{ width: 100%; border-radius: 6px; margin: 10px 0 20px; }}
</style></head><body><main>
<p class="back"><a href="index.html">&larr; Replay the cases</a></p>
<video controls preload="metadata" src="media/the_irregulars_trailer.mp4"></video>
{body}
<p class="back"><a href="index.html">Replay every case interactively &rarr;</a></p>
</main></body></html>"""
    open(os.path.join(HERE, "site", "blog.html"), "w").write(page)
    print("site/blog.html")


if __name__ == "__main__":
    main()
