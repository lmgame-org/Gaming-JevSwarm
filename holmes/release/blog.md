# One Leader, Many Minds: Why a Reasoning Leader with an AI Swarm Wins

By **[the LMGame Team](https://lmgame.org/#/aboutus)**

*A Sherlock Holmes detective game study. A large reasoning model (GPT6-Astra) leading a swarm of small, fast agents (Jev) solved 96 of 100 standard murder cases and 93 of 100 cases built on lies, far ahead of the Astra model alone (57, 59) and the swarm alone (38, 42).*

---

**The question.** Holmes never worked alone: his street boys, the Baker Street Irregulars, could "go everywhere, see everything." AI faces the same choice: one large reasoning model, or a swarm of small, fast agents? We tested both, and the combination, in *The Irregulars*.

**Preliminaries.** Each case is a simulated Victorian London of 100 addresses and 10 suspects, with one lead at each address: a witness, a footprint, a red herring or a lie. A case counts as **solved** only if the culprit, motive and hideout are all right within 12 case hours. Three detectives play every case:

- **Holmes (GPT6-Astra) + Jev Swarm:** GPT6-Astra stays at 221B and plans; 12 Jev boys run the errands and report back.
- **The Lone Genius (GPT6-Astra):** one large reasoning model goes door to door by cab.
- **Jev Swarm:** 100 Jev boys and no leader. They share clues with neighbours and vote on the answer.

**The finding.** **The swarm supplies coverage and the leader supplies judgment.** How much judgment you need depends on how hard the evidence is to read:

1. **Honest evidence:** coverage is the bottleneck, and a simple rule at the centre is enough.
2. **Conflicting evidence:** you need both. Neither alone is enough, and a counting rule fails completely.

**The data.** Every run is fully logged, and no model decision fell back to a scripted rule. Any case can be replayed on the results page.

---

## 1. Case Study: The Soho Physician

**The case.** Dr Florence Fenwick lies dead in Soho. At the scene: heavy bootprints, and a knife bought by a right-handed hand. Ten suspects, a hundred doors, twelve hours on the clock. Somewhere in the city the truth is waiting: **Beatrice Jessop** killed her out of **revenge** for an old wrong the doctor once did, and is hiding in an **opium den in Kensington**.

**Holmes + Jev Swarm solves it by checking before concluding.** Holmes sends the boys to the scene and the witnesses first, asking for "exact observations, not rumours." When an alibi looks shaky, he sends boys back to recheck it rather than guessing. **He accuses only once the boots, the knife and the motive all point the same way.**

{{media:holmes}}

**The Lone Genius reasons well but runs out of doors.** It narrows the culprit to five suspects early. The one clue that separates them sits at an address it never reaches, so it ends up guessing.

{{media:solo}}

**The Jev Swarm is fast but agrees too early.** One boy commits to an answer, his neighbours copy it, and the vote snowballs to a close. The motive and hideout are right, but the culprit is a woman who merely wore the right boots.

{{media:swarm}}

**Where the decisions happen.** Figure 1 replays all three side by side. Holmes makes a few deliberate plans while his boys make many small "where next?" choices. The Lone Genius spends a costly decision on every stop. The swarm makes thousands of decisions, but none of them weighs all the evidence.

{{media:sg}}

**The lesson of one case.** The genius can weigh evidence but cannot reach enough of it. The swarm reaches everything but cannot weigh it. **The leader with a swarm gets both.**

---

## 2. Standard Cases: The Leader with a Swarm Wins, and a Simple Centre Is Enough

**The winner.** Holmes (GPT6-Astra) + Jev Swarm solves nearly every standard case (Table 1).

{{media:t1}}

**The Lone Genius is short of coverage.** One cab can only visit so many doors, and the deciding clue is often behind one it never knocks on (section 4).

**The Jev Swarm is short of judgment.** It is by far the fastest, but most of its agreements are wrong. **A few boys misread a clue, their neighbours copy the confident vote, and the error spreads before anyone checks it.**

**A smaller Jev Swarm does worse.** A leaderless swarm of 12 Jev boys, the size of Holmes's team, solved none of the cases we could run, while the same 12 boys under Holmes solved almost all of them. **Left to themselves, a few boys cover too little of the city to find the key evidence, let alone agree on it.** (This was a partial check: our model credits ran out partway through.)

**On honest evidence, the reasoner barely matters.** Every true fact appears at two addresses and each lie at only one, so counting finds the truth. **A Holmes that only divides the work and counts clues does as well as GPT6-Astra, at a tiny fraction of the cost.** So does a leaderless swarm whose boys count instead of copy.

**Finding 1.** **When the analysis is simple, the architecture does the work: parallel coverage plus a simple aggregation rule.**

---

## 3. Frame-Up Cases: When Somebody Lies, You Need Both

**The setup.** The murderer bribes servants to describe an innocent man, and plants a clue to back them up. The lie is now told more often than the truth; only two honest witnesses saw the bribe paid.

**The winner.** Holmes (GPT6-Astra) + Jev Swarm barely drops (Table 2).

{{media:t2}}

**Counting collapses, because the majority is lying.** **GPT6-Astra asks who is speaking instead.** In one frame-up Holmes wrote: "Pargeter's servants supply both his alibi and evidence against Leopold; the dry snuff-box suggests planting."

**The others fall short for the same reasons as before.** The Lone Genius can see through the lies but still misses evidence it never reaches. The Jev Swarm beats every counting player, because some boys doubt the testimony, but with no one to weigh the doubt it often settles on the framed man.

**Finding 2.** **When the analysis is hard, coverage and judgment are both necessary, and neither is sufficient on its own.**

---

## 4. Why the Lone Genius Loses: Efficiency, Not Capability

**The winner on efficiency.** Holmes (GPT6-Astra) + Jev Swarm solves the most cases within the 12-hour limit, with time to spare.

**The genius is capable.** Given twice the time and visits, it nearly catches up (Table 3). **The extra visits matter, not the extra hours.**

{{media:t3}}

**But it is less efficient.** Even with double the budget it solves fewer cases, takes longer in case time and real time, and runs past the limit, at about the same cost:

| Standard cases | Solved | Case time (median) | Real time (median) | Cost per case |
|---|---|---|---|---|
| Holmes (GPT6-Astra) + Jev Swarm, 12 h | 96 | 11.0 h | 97 s | $0.58 |
| The Lone Genius (GPT6-Astra), 24 h / 40 visits | 91 | 14.8 h | 126 s | $0.60 |

**Why.** **One reasoner does all the legwork in sequence.** A cheap, fast swarm covers the city in parallel, and a strong leader turns what it finds into the right verdict.

---

## What This Suggests

**Holmes knew it in 1890.** The street boys were never meant to solve the case, only to find the pieces; the genius was never meant to walk every street, only to see the shape the pieces make.

**The design rule.** Divide the labour by how hard the analysis is:

- **Always use the swarm for coverage.** Small, fast agents make the many local "where next?" decisions in parallel.
- **For simple analysis, a simple centre will do.** If the evidence can be taken at face value, divide the work and aggregate it with a rule.
- **For hard analysis, put a reasoner at the centre.** When sources conflict or deceive, votes and counts follow the majority. A strong reasoner has to make the judgment.

**The answer.** One genius, or many minds? **One genius leading many minds.**

---

**Methods in brief.** Cases are generated from a seed: 100 addresses on a street graph, 10 suspects with six visible traits, 6 motives and 8 candidate hideouts. In standard cases each true key fact appears at two addresses and each lie at one. Frame-up cases add coordinated lies, a planted clue, timed alibis and witnesses to the bribe, and each case is checked to be solvable by a careful reader. All approaches get 12 case hours. Holmes's boys walk; the Lone Genius takes cabs (20 visits). The Jev Swarm uses a 2 km range and closes at 30 identical votes. The smaller-swarm check used 12 boys with a 4-vote quorum on 29 standard cases. Model calls were allowed 30 seconds, and no decision fell back to a rule. Wilson 95% intervals are in the tables.
