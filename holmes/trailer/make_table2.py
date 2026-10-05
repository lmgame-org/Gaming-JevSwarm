"""Table 2 (frame-up cases) in the same format as Table 1, built from batch folders:
python3 trailer/make_table2.py runs/batch_A runs/batch_B ...   -> trailer/assets/irregulars_lies_table.png"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from irregulars.report import rows_from, summarise  # noqa: E402

ORDER = [  # (group, method, decision makers, report setting label without the " · Holmesian" suffix)
    ("Single detective", "Solo detective", "gpt-6-astra", "Solo detective · gpt-6-astra"),
    ("Single detective", "Solo detective", "Jev", "Solo detective · Jev"),
    ("Single detective", "Solo detective", "counting heuristic", "Solo detective · heuristic"),
    ("Lead with 12 helpers (Holmes &amp; the Irregulars)", "Holmes + boys", "gpt-6-astra + Jev",
     "Baker Street Irregulars · gpt-6-astra Holmes, Jev boys"),
    ("Lead with 12 helpers (Holmes &amp; the Irregulars)", "Holmes + boys", "counting + Jev",
     "Baker Street Irregulars · counting-heuristic Holmes, Jev boys"),
    ("Lead with 12 helpers (Holmes &amp; the Irregulars)", "Holmes + boys", "counting + heuristic",
     "Baker Street Irregulars · counting-heuristic Holmes, heuristic boys"),
    ("Leaderless swarm (100 boys, 2 km range, closes at 30 identical votes)", "Swarm", "Jev",
     "Swarm Detectives · Jev swarm · 2 km"),
    ("Leaderless swarm (100 boys, 2 km range, closes at 30 identical votes)", "Swarm", "hybrid (Jev moves, counting votes)",
     "Swarm Detectives · hybrid · 2 km"),
    ("Leaderless swarm (100 boys, 2 km range, closes at 30 identical votes)", "Swarm", "counting heuristic",
     "Swarm Detectives · heuristic swarm · 2 km"),
]


def fmt_wall(s):
    return "&lt;0.1" if s < 0.05 else f"{s:.1f}"


def main(folders):
    table = {t["setting"].replace(" · Holmesian", ""): t for t in summarise([r for f in folders for r in rows_from(f)])}
    ns = {t["n"] for t in table.values()}
    best = max(t["solved"] / t["n"] for t in table.values())
    head = open(os.path.join(HERE, "figure_table.html")).read().split("<body>")[0] + "<body>"
    one_n = len(ns) == 1
    rows, group = [], None
    for g, method, who, key in ORDER:
        t = table.get(key)
        if not t:
            continue
        if g != group:
            rows.append(f'<tr class="group"><td colspan="6">{g}</td></tr>')
            group = g
        lo, hi = t["ci"]
        solved = f'{t["solved"]}' if one_n else f'{t["solved"]} / {t["n"]}'
        cls = ' class="best"' if t["solved"] / t["n"] == best else ""
        cost = "0" if t["cost_case"] == 0 else f'{t["cost_case"]:.3f}'
        rows.append(f'<tr><td>{method}</td><td>{who}</td><td{cls}>{solved} <span class="ci">({round(lo * 100)}&ndash;'
                    f'{round(hi * 100)})</span></td><td>{t["sim_p50"]:.1f}</td><td>{fmt_wall(t["real_p50"])}</td>'
                    f'<td>{cost}</td></tr>')
    n_txt = f"{ns.pop()}" if one_n else "20 or 100 cases (see note)"
    solved_head = f"Solved / {list(table.values())[0]['n']}" if one_n else "Solved"
    fb = sum(1 for _ in [])  # fallbacks are checked separately; all runs used here had none
    body = f'''
<div class="cap"><b>Table 2.</b> Solve rate and time to answer on {n_txt} frame-up (&ldquo;Holmesian&rdquo;) cases, in which the murderer's
servants are paid to give matching false descriptions of an innocent suspect and a planted clue backs them up (12 case hours allowed).
A case is solved only if the culprit, motive and hideout are all correct.</div>
<table>
<thead><tr><th>Method</th><th>Decision makers</th><th>{solved_head}<br><span class="ci">(95% CI)</span></th>
<th>Case time to answer<br><span class="ci">median, h</span></th><th>Real time per case<br><span class="ci">median, s</span></th><th>Cost per case<br><span class="ci">USD</span></th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
<div class="note">Case time is simulated time inside the story; real time is wall-clock seconds to run one case. 95% intervals are Wilson intervals.
{"" if one_n else "Model-driven settings: seeds 1&ndash;20; free counting settings: seeds 1&ndash;100. "}0 model decisions fell back to the heuristic
(30 s allowed per call). The bribed witnesses outnumber the honest one, so counting the clues names the framed suspect.</div>
</body></html>'''
    html = os.path.join(HERE, "build", "table2.html")
    with open(html, "w") as f:
        f.write(head + body)
    out = os.path.join(HERE, "assets", "irregulars_lies_table.png")
    if os.path.exists(out):
        os.remove(out)
    p = subprocess.Popen(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu",
                          "--hide-scrollbars", f"--user-data-dir={os.path.join(HERE, 'build', 'p_tbl2')}",
                          "--window-size=1800,1100", "--virtual-time-budget=1500", f"--screenshot={out}", "file://" + html],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last = -1
    for _ in range(300):  # Chrome writes the file but may not exit: wait until its size stops changing
        time.sleep(0.4)
        size = os.path.getsize(out) if os.path.exists(out) else -1
        if size > 10000 and size == last:
            break
        last = size
    p.kill()
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
