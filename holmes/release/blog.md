# One Genius or Many Minds? What Sherlock Holmes Taught Us About AI Swarms

*A lone reasoning model, a leaderless swarm of small agents, and a reasoning leader directing the swarm, in 200 simulated murder mysteries.*

---

Sherlock Holmes said of his street boys, the Baker Street Irregulars: "They can go everywhere, see everything, overhear every one." His secret was never one mind. Today's AI faces the same choice: one large model that reasons, or a swarm of small, fast agents?

We built *The Irregulars*, a simulated Victorian London of 100 addresses and 10 suspects. Every address holds one lead: a witness, a footprint, a red herring, or a lie. A case is **solved** only if the culprit, the motive and the hideout are all right within 12 case hours. Three detectives play every case:

- **The Lone Genius (GPT6-Astra):** one large reasoning model takes a cab from door to door, 20 visits.
- **Jev Swarm:** 100 small, fast Jev agents, no leader. Each shares what it finds with those nearby and votes; the case closes when 30 agree.
- **Holmes (GPT6-Astra) + Jev Swarm:** GPT6-Astra stays at 221B and plans; 12 Jev boys run the errands and report back.

Every number below comes from real, fully logged runs (no decision fell back to a scripted rule), and you can replay any case on the results page.

---

## 1. One case, three detectives

Case 57. Florence Fenwick, a physician, is found dead in Soho. The truth: **Beatrice Jessop**, out of **revenge**, hiding in an **opium den in Kensington**.

**The Lone Genius** starts well. Its first stop turns up an old newspaper cutting about the victim's testimony sending an innocent man to prison, and it writes: "The cutting suggests revenge, but neither culprit nor refuge is established." Muddy prints at the scene show heavy boots, which "narrow the suspects to Ashdown, Fenwick, Esterby, Wetherell and Jessop." Later it smells the opium den, then finds it. Motive and hideout are settled by midday. But the clue that separates the five suspects, a knife sold late that night to a right-handed buyer, sits at an address it never reaches. After twenty visits and ten and a half hours it has to guess, and names the wrong woman. **Unsolved.**

{{media:solo}}

**The Jev Swarm** is fast. For three hours its boys gather and share clues; then, at 3 hours 15 minutes, the first boy commits to a full answer, and within an hour one answer snowballs from 1 boy to 33. You can watch the colour spread across the map as neighbours copy each other. At 4 hours 15 minutes, 33 boys agree on Prudence Wetherell, revenge, the Kensington opium den, and the case closes. Motive and hideout are right; the culprit is a woman who merely wore the right boots. A second cluster of 8 boys had settled on yet another innocent suspect. **Unsolved.**

{{media:swarm}}

**Holmes and his Irregulars** take longer, and get it right. Holmes's first order: "Wiggins, begin with the death scene, Florence's home, and independent witnesses. Record exact observations, not rumours." By 2½ hours the boys have brought back the heavy boots and the right-handed knife buyer: "The right-handed buyer tentatively favours Maud or Beatrice. Maud's incompatible alibis demand independent checking." He sends boys to recheck the alibi. By 7½ hours: "Esterby has corroborated alibis. Two newspaper cuttings suggest revenge." At 10½ hours he names Beatrice Jessop, revenge, Kensington. **Solved**, in about two minutes of real time.

{{media:holmes}}

That is the whole study in one case. The genius reasons well about what it finds but cannot knock on enough doors. The swarm covers the city but votes on half the evidence. The leader with a swarm gets both: twelve pairs of legs to find the decisive clue, and one mind to weigh it.

---

## 2. Standard cases: the leader with a swarm wins

Across 100 standard cases (Table 1):

{{media:t1}}

- **Holmes (GPT6-Astra) + Jev Swarm: 96 solved**, median 11.0 case hours, 97 seconds of real time.
- **The Lone Genius (GPT6-Astra): 57 solved**, 10.5 case hours, 82 seconds.
- **Jev Swarm: 38 solved**, 2.2 case hours, 9 seconds.

The Jev Swarm is by far the fastest, but speed is its trap. It reaches a 30-vote agreement in 91 of 100 cases, and **53 of those agreements are wrong**. A few boys misjudge a clue, their neighbours copy the confident vote, and the wrong answer snowballs to thirty before anyone checks. Small agents turn out to be good searchers and weak judges.

The heuristic baselines make the same point from the other side. On these honest cases, where every true fact appears twice and each lie once, a Holmes that simply counts clues does just as well with the same boys (95 with Jev boys, 97 with scripted boys). What wins here is the structure, one leader and many helpers, more than the brilliance of the leader.

---

## 3. When somebody lies

So we made the cases harder. In 100 *frame-up* cases the murderer pays his own servants to describe an innocent man and swear their master never left home, and a planted clue backs them up. Now the lie appears more often than the truth. Two honest witnesses saw the bribe being paid (Table 2):

{{media:t2}}

- **Holmes (GPT6-Astra) + Jev Swarm: 93 solved.**
- The Lone Genius (GPT6-Astra): 59.
- Jev Swarm: 42.
- Replace the Astra leader with a clue-counting Holmes: **0**. Replace the Jev swarm with a counting swarm: **1**.

Counting follows the majority, and the majority is now lying. GPT6-Astra asks who is speaking. In one frame-up, Holmes wrote: "Pargeter's servants supply both his alibi and evidence against Leopold; the dry snuff-box suggests planting. Pargeter merits suspicion, not accusation." The Jev Swarm does better than any counting player because some boys read the testimony and doubt it, but without a leader it still often agrees on the framed man.

So the leader matters after all, once the case fights back. The swarm finds the evidence; only a reasoning leader decides whom to believe.

---

## 4. Why the genius loses: efficiency, not capability

Is the Lone Genius simply a worse detective? No. Case 57 already showed it reasoning well; it ran out of doors. In 59 of 100 standard cases it hit its limit, and the piece it was missing was usually the motive, never the hideout.

So we gave it twice the time and visits: 24 case hours and 40 visits (Table 3). It jumps from **57 to 91** on standard cases and from **59 to 89** on frame-ups. Given enough time, the genius can do the job. A control confirms it is the visits that matter, not the hours: a counting detective at 24 hours with the original 20 visits stays at 61, and with 40 visits reaches 99.

{{media:t3}}

But look at the cost. To reach 91, the Lone Genius needs about **15 case hours** and **two minutes of real time** per case. Holmes (GPT6-Astra) + Jev Swarm reaches **96** within the original 12 hours (median 11) and about a minute and a half, because twelve boys search in parallel while the leader thinks. Holmes's boys check about 70 addresses per case; the lone genius manages 20, or 40 with double the budget.

That is the real distinction. The lone model's limit is not capability but **efficiency**: one reasoner doing all the legwork serially. A swarm of cheap, fast agents buys parallel coverage; a strong leader turns that coverage into a correct verdict.

---

## What this suggests

Holmes knew it in 1890. The street boys were never meant to solve the case; they were meant to find the pieces. The genius was never meant to walk every street; he was meant to see the shape the pieces make. For multi-agent AI that suggests a simple division of labour: let small, fast agents make the many local "where next?" decisions, do not let a crowd of them be the judge, and put a strong reasoner at the point of judgment.

One genius, or many minds? Our answer, and Holmes's: one genius, and many minds.

---

*Methods in brief.* Cases are generated from a seed: 100 addresses on a street graph, 10 suspects with six visible traits, 6 motives, 8 candidate hideouts. In standard cases each true key fact appears at two addresses and each lie at one; frame-up cases add coordinated lies, a planted clue, timed alibis and witnesses to the bribe, and each case is checked to be solvable by a careful reader. All approaches get 12 case hours. Holmes's boys walk; the lone genius takes cabs. The Jev Swarm uses a 2 km range and closes at 30 identical votes. Model calls were allowed 30 seconds; zero decisions fell back to a rule. Wilson 95% intervals are in the tables.
