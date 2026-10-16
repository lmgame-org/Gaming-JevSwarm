# Release kit: Catch Murderer with Jev Swarm

## Links

- Blog: https://snyhlx.github.io/the_irregulars_detective_game/blog.html
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

## Twitter / X thread (Friday version)

Seven tweets: the hook with a one-line takeaway, the setup, two tweets on the easier cases, one on simple rules, one on the harder cases, and the moral with links. Each is under 280 characters.

**1/**
Happy Friday! 🕵️🔍

Can a swarm of fast decision agents catch a murderer?

Takeaway: the swarm covers the evidence, a simple rule can count it, but it takes a reasoning leader to spot contradictions and dig deeper.

More in this thread 🧵 and the blog 👇
https://snyhlx.github.io/the_irregulars_detective_game/blog.html

[media: tweet_1_trailer.mp4]

**2/**
The setup: every case has 100 addresses, 10 suspects and 12 hours to name the culprit, motive and hideout.

Two roles, any player:
🕵️ Holmes reasons and decides: GPT6-Astra, Jev, a rule, or nobody
👦 The Irregulars search: Jev agents, a rule, or nobody

[media: tweet_2a_role_holmes.jpg + tweet_2b_role_irregulars.jpg]

**3/**
1️⃣ Legs + brains wins.

On 100 easier cases, where few witnesses lie:
• GPT6-Astra leading 12 Jev agents: 96 🏆
• GPT6-Astra alone: 57
• Jev swarm alone: 38

The swarm knocks on doors. The leader does the thinking.

[media: tweet_3_table1_easier_cases.png]

**4/**
2️⃣ Alone, each one fails in its own way.

A leaderless swarm is a rumour mill 🗣️: one kid misreads a clue, his mates copy the vote, and the street agrees on the wrong answer.

The lone genius runs out of shoe leather 👞: one cab never reaches the door with the deciding clue.

[media: tweet_4_spatiotemporal_all_three.png]

**5/**
3️⃣ When lies are few, elementary counting wins 📏

Every true fact turns up twice and each lie only once, so just count the clues: a rule-based leader with rule-based agents solves 97/100 for $0.

Elementary, my dear Watson.

[media: tweet_5_soho_case.jpg]

**6/**
4️⃣ But when the servants are bribed… 💰

In 100 harder cases, paid witnesses outnumber honest ones:
• GPT6-Astra + Jev swarm: 93
• GPT6-Astra alone: 59
• Jev swarm alone: 42
• Rule-based: 0–1

Takeaway: against organized lies, you need a reasoning leader who asks who's talking.

[media: tweet_6_table2_harder_cases.png]

**7/**
The moral: let fast agents do the legwork and a strong reasoner do the thinking. One genius, many minds. 🧠👣

Replay all 200 cases:
https://snyhlx.github.io/the_irregulars_detective_game/results.html

Code + more Jev games:
https://github.com/lmgame-org/Gaming-JevSwarm

Happy sleuthing! — LMGame

## Twitter / X thread

Seven tweets. The first leads with the trailer, tweets 2–6 carry the five main conclusions, and the last has the links. Each is under 280 characters (a link counts as 23). Media files are in `~/Downloads/irregulars_release/site/media/`.

**1/**
Can a swarm of small, fast AI agents catch a murderer? 🕵️

We built a Sherlock Holmes game and let three detectives solve 200 cases: a Jev swarm on its own, GPT6-Astra on its own, and GPT6-Astra leading a Jev swarm.

Blog 👇
https://snyhlx.github.io/the_irregulars_detective_game/blog.html

[media: the_irregulars_trailer.mp4]

**2/**
1️⃣ The swarm supplies evidence coverage; the leader reasons.

On 100 easier cases, where few witnesses lie:
• GPT6-Astra leading 12 Jev agents: 96
• GPT6-Astra alone: 57
• Jev swarm alone: 38

[media: irregulars_standard_setting_results.png]

**3/**
2️⃣ A swarm on its own agrees too early.

A few agents misread a clue, their neighbours copy the confident vote, and the error spreads. Jev also can't hold a whole case in mind (25/100 alone), so in the winning team it only makes small local decisions.

[media: irregulars_clip3_jev_swarm.mp4]

**4/**
3️⃣ A genius on its own runs out of doors.

GPT6-Astra reasons well, but one cab reaches only so many addresses, and the deciding clue is often behind a door it never knocks on. The swarm covers the whole city but can't weigh what it finds. Together, they get both.

[media: irregulars_clip1_astra.mp4]

**5/**
4️⃣ With few lies, a simple leader is enough.

In the easier cases, each lie comes from a lone witness while every true fact turns up twice, so counting clues finds the truth: a rule-based leader with rule-based agents solves 97/100 at zero cost.

[media: case57_soho.jpg]

**6/**
5️⃣ With organized lies, you need a reasoning leader.

In 100 harder cases, bribed witnesses outnumber honest ones:
• GPT6-Astra + Jev swarm: 93
• GPT6-Astra alone: 59
• Jev swarm alone: 42
• Rule-based: 0–1

Counting follows the lying majority; GPT6-Astra asks who's speaking.

[media: irregulars_challenging_setting_results.png]

**7/**
The lesson: divide and conquer. Fast agents cover the evidence, and a strong reasoner judges it whenever the pieces disagree.

Replay all 200 cases:
https://snyhlx.github.io/the_irregulars_detective_game/results.html

Code and more Jev games:
https://github.com/lmgame-org/Gaming-JevSwarm

By the LMGame team.

## Short version (single post)

Can a swarm of small, fast AI agents catch a murderer? In our Sherlock Holmes game, GPT6-Astra leading a Jev swarm solved 96/100 cases, against 57 for GPT6-Astra alone and 38 for the swarm alone. The swarm covers the evidence; the leader reasons.
https://snyhlx.github.io/the_irregulars_detective_game/blog.html
