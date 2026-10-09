# One Leader, Many Minds: Why a Reasoning Leader with an AI Swarm Wins

*A Sherlock Holmes detective game study. A large reasoning model (GPT6-Astra) leading a swarm of small, fast agents (Jev) solved 96 of 100 standard murder cases and 93 of 100 cases built on lies, ahead of the model alone (57, 59) and the swarm alone (38, 42).*

---

Sherlock Holmes never worked alone: his street boys, the Baker Street Irregulars, could "go everywhere, see everything." AI faces the same choice today: one large model that reasons, or a swarm of small, fast agents? We tested both, and the combination, in *The Irregulars*.

**Preliminaries.** Each case is a simulated Victorian London with 100 addresses, 10 suspects and one lead per address (a witness, a footprint, a red herring or a lie). A case is **solved** only if the culprit, motive and hideout are all right within 12 case hours. Three detectives play every case:

- **The Lone Genius (GPT6-Astra):** one large reasoning model takes a cab from door to door, 20 visits.
- **Jev Swarm:** 100 small, fast Jev agents, no leader. They share clues with neighbours and vote; the case closes when 30 agree.
- **Holmes (GPT6-Astra) + Jev Swarm:** GPT6-Astra stays at 221B and plans; 12 Jev boys run the errands and report back.

**The finding.** The leader with a swarm wins, and the two parts do different jobs. The swarm supplies **coverage**: many agents searching in parallel. The leader supplies **judgment**: deciding what the evidence means. How much judgment is needed depends on how hard the analysis is:

1. **When the evidence is honest** (standard cases), coverage is the bottleneck. A swarm under a simple central rule (divide the city, count corroborated clues) is enough.
2. **When the evidence conflicts** (frame-up cases, where witnesses lie), you need both: the swarm to find the evidence and a reasoning leader to decide whom to believe. Neither one alone is enough, and a counting rule fails completely.

All numbers come from fully logged runs (no model decision fell back to a scripted rule); every case can be replayed on the results page.

---

## 1. One case, three detectives

Case 57. Florence Fenwick, a physician, is found dead in Soho. The truth: **Beatrice Jessop**, out of **revenge**, hiding in an **opium den in Kensington**.

**The Lone Genius** starts well. Its first stop turns up an old newspaper cutting about the victim's testimony sending an innocent man to prison, and it writes: "The cutting suggests revenge, but neither culprit nor refuge is established." Muddy prints at the scene show heavy boots, which "narrow the suspects to Ashdown, Fenwick, Esterby, Wetherell and Jessop." Later it smells the opium den, then finds it. Motive and hideout are settled by midday. But the clue that separates the five suspects, a knife sold late that night to a right-handed buyer, sits at an address it never reaches. After twenty visits and ten and a half hours it has to guess, and names the wrong woman. **Unsolved.**

{{media:solo}}

**The Jev Swarm** is fast. For three hours its boys gather and share clues; then, at 3 hours 15 minutes, the first boy commits to a full answer, and within an hour one answer snowballs from 1 boy to 33. You can watch the colour spread across the map as neighbours copy each other. At 4 hours 15 minutes, 33 boys agree on Prudence Wetherell, revenge, the Kensington opium den, and the case closes. Motive and hideout are right; the culprit is a woman who merely wore the right boots. A second cluster of 8 boys had settled on yet another innocent suspect. **Unsolved.**

{{media:swarm}}

**Holmes and his Irregulars** take longer, and get it right. Holmes's first order: "Wiggins, begin with the death scene, Florence's home, and independent witnesses. Record exact observations, not rumours." By 2½ hours the boys have brought back the heavy boots and the right-handed knife buyer: "The right-handed buyer tentatively favours Maud or Beatrice. Maud's incompatible alibis demand independent checking." He sends boys to recheck the alibi. By 7½ hours: "Esterby has corroborated alibis. Two newspaper cuttings suggest revenge." At 10½ hours he names Beatrice Jessop, revenge, Kensington. **Solved**, in about two minutes of real time.

{{media:holmes}}

Figure 1 replays all three side by side. Watch how each one **scatters** over the city and how the evidence is **gathered** back into an answer:

{{media:sg}}

That is the whole study in one case. The genius reasons well about what it finds but cannot knock on enough doors. The swarm covers the city but votes on half the evidence. The leader with a swarm gets both: twelve pairs of legs to find the decisive clue, and one mind to weigh it.

---

## 2. Standard cases: a swarm with a simple central rule is enough

Across 100 standard cases (Table 1):

{{media:t1}}

- **Holmes (GPT6-Astra) + Jev Swarm: 96 solved**, median 11.0 case hours, 97 seconds of real time.
- **The Lone Genius (GPT6-Astra): 57 solved**, 10.5 case hours, 82 seconds.
- **Jev Swarm: 38 solved**, 2.2 case hours, 9 seconds.

The Jev Swarm is by far the fastest, but speed is its trap. It reaches a 30-vote agreement in 91 of 100 cases, and **53 of those agreements are wrong**. A few boys misjudge a clue, their neighbours copy the confident vote, and the wrong answer snowballs to thirty before anyone checks. Small agents turn out to be good searchers and weak judges.

The baselines with no model at the top isolate what matters here. In standard cases every true fact appears at two addresses and each lie at only one, so the analysis is simple: the corroborated answer is the right one. Here a Holmes who only divides the work and counts clues does as well as GPT6-Astra: **95** with Jev boys and **97** with scripted boys, against **96**, at $0.002 or less per case instead of $0.58. (A leaderless swarm whose boys count rather than copy reaches 95 too.)

**Finding 1.** When the analysis is simple, performance comes from the architecture: parallel coverage plus a simple aggregation rule. A strong reasoner at the top adds little.

---

## 3. Frame-up cases: when the analysis gets hard, you need both

So we made the cases harder. In 100 *frame-up* cases the murderer pays his own servants to describe an innocent man and swear their master never left home, and a planted clue backs them up. Now the lie appears more often than the truth. Two honest witnesses saw the bribe being paid (Table 2):

{{media:t2}}

- **Holmes (GPT6-Astra) + Jev Swarm: 93 solved.**
- The Lone Genius (GPT6-Astra): 59.
- Jev Swarm: 42.
- The same swarm under a clue-counting Holmes: **0**. A counting Holmes with counting boys: **1**. A leaderless counting swarm: **1**.

Counting follows the majority, and the majority is now lying. GPT6-Astra asks who is speaking. In one frame-up, Holmes wrote: "Pargeter's servants supply both his alibi and evidence against Leopold; the dry snuff-box suggests planting. Pargeter merits suspicion, not accusation." The Jev Swarm does better than any counting player because some boys read the testimony and doubt it, but without a leader it still often agrees on the framed man.

**Finding 2.** When the analysis is hard, coverage and judgment are both necessary, and neither alone is sufficient. Without the swarm, the reasoner misses evidence (the Lone Genius, 59). Without the reasoner, the swarm is misled (Jev Swarm, 42; any counting rule, 0 to 1). Together they solve 93.

---

## 4. Why the genius loses: efficiency, not capability

Is the Lone Genius simply a worse detective? No. Case 57 showed it reasoning well; it ran out of doors. In 59 of 100 standard cases it used up its visits or its hours, and of its 43 failures, 32 had the motive wrong, 17 the culprit, and none the hideout.

So we gave it twice the budget: 24 case hours and 40 visits (Table 3). It climbs from **57 to 91** on standard cases and from **59 to 89** on frame-ups. Given the legwork, the genius can solve the case. A control shows the visits matter, not the hours: a counting detective at 24 hours with the original 20 visits stays at 61, and with 40 visits reaches 99.

{{media:t3}}

The gap is efficiency. On standard cases:

| | Solved | Case time (median) | Real time (median) | Cost per case |
|---|---|---|---|---|
| The Lone Genius (GPT6-Astra), 24 h / 40 visits | 91 | 14.8 h | 126 s | $0.60 |
| Holmes (GPT6-Astra) + Jev Swarm, 12 h | 96 | 11.0 h | 97 s | $0.58 |

With double the budget, the Lone Genius still solves fewer cases. It needs about 35% more case time (3.8 more hours, which breaks the 12-hour rule) and about 30% more real time (29 more seconds), at roughly the same cost. Holmes's boys cover a median of 74 addresses per case, searching in parallel while the leader thinks; the genius covers 40 at most, one cab ride after another. On frame-ups the gap is smaller: the doubled Lone Genius solves 89 in 12.4 h and 104 s at $0.52 a case, against 93 in 12.0 h and 99 s at $0.60 for Holmes + Jev. There it is a little cheaper, but still slower and still less accurate, and still past the 12-hour limit.

So the lone model is not short of capability; it is short of **efficiency**, because one reasoner does all the legwork serially. The cheap, fast swarm buys parallel coverage, and a strong leader turns that coverage into the right verdict.

---

## What this suggests

Holmes knew it in 1890. The street boys were never meant to solve the case; they were meant to find the pieces. The genius was never meant to walk every street; he was meant to see the shape the pieces make.

For multi-agent AI the lesson is a division of labour that scales with the difficulty of the analysis:

- **Always use the swarm for coverage.** Small, fast agents make the many local "where next?" decisions in parallel, far more efficiently than one reasoner working through them one at a time (section 4).
- **For simple analysis, a simple centre will do.** If the evidence can be taken at face value, divide the work and aggregate it with a rule. No expensive reasoner is needed.
- **For hard analysis, put a reasoner at the centre.** When sources conflict or deceive, a crowd's vote and a counting rule both follow the majority. A strong reasoner has to make the judgment.

One genius, or many minds? Our answer, and Holmes's: one genius leading many minds.

---

*Methods in brief.* Cases are generated from a seed: 100 addresses on a street graph, 10 suspects with six visible traits, 6 motives, 8 candidate hideouts. In standard cases each true key fact appears at two addresses and each lie at one; frame-up cases add coordinated lies, a planted clue, timed alibis and witnesses to the bribe, and each case is checked to be solvable by a careful reader. All approaches get 12 case hours. Holmes's boys walk; the lone genius takes cabs. The Jev Swarm uses a 2 km range and closes at 30 identical votes. Model calls were allowed 30 seconds; zero decisions fell back to a rule. Wilson 95% intervals are in the tables.
