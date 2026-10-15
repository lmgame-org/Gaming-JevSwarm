# Reddit post: Catch Murderer with Jev Swarm

## Where to post

- **r/MachineLearning**: title must start with `[P]` (project). Text post; link the blog and the repo in the body.
- **r/LocalLLaMA** and **r/artificial**: text post with the trailer or Table 1 as the first image.
- Check each subreddit's self-promotion rules first, post from an account with some history, and reply to comments in the first hour.

## Title options

1. `[P] Can a swarm of small, fast AI agents catch a murderer? We tested a lone LLM, a leaderless agent swarm, and an LLM leading the swarm on 200 Sherlock Holmes cases`
2. `[P] One genius or many minds? An LLM leading a swarm of small agents solved 96/100 murder cases; the LLM alone solved 57 and the swarm alone 38`
3. `[P] A Sherlock Holmes game as a test bed for agent swarms: the swarm covers the evidence, the leader reasons`

## Media

Lead with one asset (Reddit shows the first image or video large):

- `the_irregulars_trailer.mp4` (1:35), or
- `irregulars_standard_setting_results.png` (Table 1) if the subreddit prefers results over video.

Files are in `~/Downloads/irregulars_release/site/media/`.

## Body

---

We built a Sherlock Holmes detective game to ask a simple question: **can a swarm of small, fast AI agents (Jev) gather clues and name a murderer, and if not, what does it take?**

**Blog (with an interactive replay of a case):** https://snyhlx.github.io/the_irregulars_detective_game/blog.html?v=lmgame-holmes-game
**Code and more games:** https://github.com/lmgame-org/Gaming-JevSwarm
**Trailer:** https://snyhlx.github.io/the_irregulars_detective_game/trailer.html

**The setup**

Each case is a procedurally generated Victorian London: 100 addresses, 10 suspects, and one lead at every address (a witness, a footprint, a red herring or a lie). A case counts as solved only if the detective names the right culprit, motive and hideout within 12 hours of case time.

The game has two roles, and we let different models and algorithms play each one:

- **Holmes**, who reasons and decides: GPT6-Astra, Jev, a rule-based heuristic, or nobody
- **The Irregulars**, who search: Jev agents, a rule-based heuristic, or nobody

That gives three main detectives:

- **Holmes (GPT6-Astra) + Jev Swarm:** GPT6-Astra stays at 221B Baker Street and plans; 12 Jev agents run the errands and report back.
- **The Lone Genius (GPT6-Astra):** one large reasoning model goes door to door by cab and does everything itself.
- **Jev Swarm:** 100 Jev agents with no leader. They share clues with neighbours and vote; the case closes when 30 agree.

**Results (solved out of 100)**

| Detective | Standard cases (few lies) | Frame-up cases (organized lies) |
|---|---|---|
| Holmes (GPT6-Astra) + Jev Swarm | **96** | **93** |
| The Lone Genius (GPT6-Astra) | 57 | 59 |
| Jev Swarm (no leader) | 38 | 42 |
| Rule-based Holmes + Jev agents | 95 | 0 |

**What we learned**

- **The swarm supplies evidence coverage, while the leader reasons.** Small agents search the city in parallel; the leader decides what the evidence means and when to accuse.
- **Alone, the swarm agrees too early.** It is by far the fastest (median 2.2 case hours, about 9 s of real time), but most of the answers it agrees on are wrong: a few agents misread a clue, their neighbours copy the confident vote, and the error spreads before anyone checks it.
- **Alone, the genius runs out of doors.** It reasons well, but the deciding clue is often at an address it never reaches. With twice the time and visits it climbs to 91, but it is still slower and goes past the time limit.
- **On honest evidence, a simple centre is enough.** A rule-based Holmes that only counts clues matches GPT6-Astra (95 vs 96) at a tiny fraction of the cost.
- **When somebody lies, you need both.** In frame-ups the murderer bribes witnesses, so counting follows the lying majority and solves 0 of 100. GPT6-Astra asks who is giving the evidence and why, and solves 93.

Our takeaway: a detective case is a divide-and-conquer problem. Fast agents suit the divide step (covering the evidence); a strong reasoner is needed for the conquer step whenever the pieces disagree.

**Details and limitations**

- Every run is fully logged, and no model decision fell back to a scripted rule (30 s allowed per call). You can replay all 200 cases move by move: https://snyhlx.github.io/the_irregulars_detective_game/results.html
- Cost per standard case: about $0.58 for Holmes (GPT6-Astra) + Jev Swarm, $0.34 for GPT6-Astra alone, $0.15 for the Jev Swarm, and nothing for the rule-based players.
- This is a simulated game with one large model (GPT6-Astra) and one small model (Jev), so the numbers say more about this kind of task than about the models in general.
- A leaderless swarm of only 12 Jev agents (the size of Holmes's team) solved none of the 29 standard cases we ran, so the swarm's size matters as well as its leader.

The repo has the same setup in other environments too: CPU debugging, fish schooling under predator attack, and honeybee nest-site selection. Every game runs from one launcher with presets, and the rule-based players need no API key.

We'd love feedback, especially on other games where a fast swarm plus a slow reasoner might help, or where it would fail.

By the LMGame team: https://lmgame.org/#/aboutus

---
