# Release kit: Catch Murderer with Jev Swarm

## Links

- Blog: https://snyhlx.github.io/the_irregulars_detective_game/blog.html?v=lmgame-holmes-game
- Trailer: https://snyhlx.github.io/the_irregulars_detective_game/trailer.html
- Replays of all 200 cases: https://snyhlx.github.io/the_irregulars_detective_game/results.html
- Code and more Jev games: https://github.com/lmgame-org/Gaming-JevSwarm
- By the LMGame team: https://lmgame.org/#/aboutus

## Main takeaways

1. **Leader plus swarm wins.** GPT6-Astra leading 12 Jev agents solved 96 of 100 standard cases and 93 of 100 frame-up cases, against 57 and 59 for GPT6-Astra alone and 38 and 42 for a leaderless Jev swarm.
2. **The swarm supplies evidence coverage; the leader reasons.** Small, fast agents search the city in parallel, and the leader decides what the evidence means.
3. **Alone, the swarm agrees too early.** It is by far the fastest, but most of the answers it agrees on are wrong: a few agents misread a clue, their neighbours copy the confident vote, and the error spreads.
4. **Alone, the genius runs out of doors.** One reasoner has to do all the legwork in sequence. With twice the time and visits it nearly catches up (91), but it is still slower and goes past the time limit.
5. **On honest evidence, a simple centre is enough.** A rule-based Holmes that only counts clues does as well as GPT6-Astra, at a tiny fraction of the cost.
6. **When somebody lies, you need both.** Counting follows the majority, and the majority is lying (0 of 100 solved). GPT6-Astra asks who is giving the evidence and why.
7. **Divide and conquer.** Fast agents are well suited to the divide step; a strong reasoner is needed for the conquer step whenever the pieces disagree. One genius leading many minds.

## Twitter / X thread

Each tweet is under 280 characters (a link counts as 23). Media files are in `~/Downloads/irregulars_release/site/media/`.

**1/**
Can a swarm of small, fast AI agents catch a murderer? 🕵️

We built a Sherlock Holmes game and let three detectives solve 200 cases: a Jev swarm on its own, GPT6-Astra on its own, and GPT6-Astra leading a Jev swarm.

Blog and trailer 👇
https://snyhlx.github.io/the_irregulars_detective_game/blog.html?v=lmgame-holmes-game

[media: the_irregulars_trailer.mp4]

**2/**
Each case is a simulated Victorian London: 100 addresses, 10 suspects, and one lead at every address (a witness, a footprint, a red herring or a lie).

To solve it, a detective must name the culprit, the motive and the hideout within 12 case hours.

[media: case57_soho.jpg]

**3/**
The game has two roles, and different models can play each one:

🕵️ Holmes, who reasons and decides: GPT6-Astra, Jev, a rule-based heuristic, or nobody
👦 The Irregulars, who search: Jev agents, a rule-based heuristic, or nobody

[media: role_holmes.jpg + role_irregulars.jpg]

**4/**
Results on 100 standard cases:

• Holmes (GPT6-Astra) + Jev Swarm: 96
• The Lone Genius (GPT6-Astra): 57
• Jev Swarm, no leader: 38

The swarm supplies evidence coverage, while the leader reasons.

[media: irregulars_standard_setting_results.png]

**5/**
Why the swarm alone falls short: it is by far the fastest, but most of the answers it agrees on are wrong.

A few agents misread a clue, their neighbours copy the confident vote, and the error spreads before anyone checks it.

[media: irregulars_clip3_jev_swarm.mp4]

**6/**
Why the genius alone falls short: legwork, not brains.

One cab can only reach so many doors, and the deciding clue is often behind one it never knocks on. With twice the time and visits it climbs to 91, but it is still slower than the leader with a swarm.

[media: irregulars_clip1_astra.mp4]

**7/**
The winning team: GPT6-Astra stays at 221B Baker Street and plans, while 12 Jev agents make the quick "where next?" decisions and report back.

It checks before it concludes, and accuses only when the evidence points to one person.

[media: irregulars_clip2_astra_jev_swarm.mp4]

**8/**
Then somebody lies. In 100 frame-up cases, the murderer bribes servants to frame an innocent man, so the lie is told more often than the truth.

• Holmes (GPT6-Astra) + Jev Swarm: 93
• Lone Genius: 59
• Jev Swarm: 42
• Rule-based Holmes + Jev agents: 0

[media: irregulars_challenging_setting_results.png]

**9/**
On honest cases, a rule-based Holmes that just counts clues does as well as GPT6-Astra, at a tiny fraction of the cost.

When somebody lies, counting follows the majority, and the majority is lying. GPT6-Astra asks who is giving the evidence and why.

**10/**
The lesson: a detective case is a divide-and-conquer problem.

Fast agents are well suited to the divide step: covering the evidence. A strong reasoner is needed for the conquer step whenever the pieces disagree.

One genius leading many minds.

**11/**
Every run is logged. Replay any of the 200 cases, move by move:
https://snyhlx.github.io/the_irregulars_detective_game/results.html

Code and more Jev games (CPU debugging, fish schooling, honeybee nest-site selection):
https://github.com/lmgame-org/Gaming-JevSwarm

By the LMGame team.

## Short version (single post)

Can a swarm of small, fast AI agents catch a murderer? In our Sherlock Holmes game, GPT6-Astra leading a Jev swarm solved 96/100 cases, against 57 for GPT6-Astra alone and 38 for the swarm alone. The swarm covers the evidence; the leader reasons.
https://snyhlx.github.io/the_irregulars_detective_game/blog.html?v=lmgame-holmes-game
