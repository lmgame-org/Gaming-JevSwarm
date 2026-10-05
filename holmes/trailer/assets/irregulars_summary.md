Wanting to share some fun hack by putting a side by side comparison among Astra, Astra leader + Jev swarm, Jev swarm in Holmes detective game.

Setup: we built "The Irregulars", a Victorian London murder game: a seeded city of 100 addresses and 10 suspects, where each address holds one lead and some leads are lies. To solve a case you must name the culprit, the motive and the hideout within 12 case hours. Three ways to play:
- The Lone Genius (GPT6-Astra): GPT6-Astra alone, one cab, 20 visits.
- Holmes (GPT6-Astra) + Jev Swarm: GPT6-Astra as Holmes at 221B, directing a swarm of 12 Jev "street boys" who run errands and report back.
- Jev Swarm: 100 Jev boys and no leader. They share clues with the boys nearby and vote; the case closes when 30 agree.

Interesting findings (100 cases each, 0 fallbacks):
1. A leader with a swarm wins clearly: Holmes (GPT6-Astra) + Jev Swarm solves 96/100 standard cases, vs 57 for The Lone Genius (GPT6-Astra) and 38 for the leaderless Jev Swarm.
2. The Lone Genius is limited by legwork, not reasoning. With twice the time and visits (24 h, 40 visits) GPT6-Astra reaches 91/100, but takes ~15 case hours and ~2 min per case. Holmes (GPT6-Astra) + Jev Swarm gets 96 within 11 case hours by searching in parallel.
3. The Jev Swarm converges fast but often on the wrong answer. It reaches a 30-vote agreement in 91/100 cases (median 2.2 case hours, 9 s real time), but 53 of those agreements are wrong. Agreeing is not the same as being right.
4. When somebody lies, reasoning matters. In 100 frame-up cases, where the murderer bribes his servants to frame an innocent man, Holmes (GPT6-Astra) + Jev Swarm still solves 93, The Lone Genius (GPT6-Astra) 59 and the Jev Swarm 42. Holmes (heuristic) + heuristic Swarm, which simply counts clues, solves 1 (0 with Jev boys), because the coordinated lie outnumbers the truth.
5. On honest cases, a simple counting rule is enough. Holmes (heuristic) + Jev Swarm solves 95/100, ~30% faster in case time and ~20x faster in real time (5 s vs 97 s per case). The structure (one leader, a swarm of helpers) carries the easy cases; a reasoning leader is what survives deception.

Attached: the trailer, 3 clips (one per method, from the real benchmark runs of the same case) and 3 tables (standard cases; frame-up cases; The Lone Genius at 24 h / 40 visits).
