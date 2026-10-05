# One Genius or Many Minds? What Sherlock Holmes Taught Us About AI Swarms

*A side-by-side study of a lone reasoning model, a reasoning leader with a swarm of small agents, and a leaderless swarm, in 200 simulated murder mysteries.*

---

In *The Sign of Four*, Sherlock Holmes explains why he pays a gang of street children a shilling a day: "They can go everywhere, see everything, overhear every one." The great detective's real secret was never one mind. It was a swarm: a dozen boys fanning out across London, bringing back fragments that only he could assemble.

A century later, AI faces the same choice. Do you build one brilliant model and ask it to do everything? Or do you deploy many small, fast agents and let intelligence emerge from the crowd? Or some mix of the two?

We decided to find out the Holmesian way: with a murder.

We built *The Irregulars*, a simulated Victorian London with 100 addresses and 10 suspects. A murder has been committed. Every address holds one lead: a witness, a footprint, a receipt, a red herring, a lie, or nothing at all. To solve the case, an investigator must name the **culprit**, the **motive** and the **hideout**, all three correct, within twelve hours of case time.

Then we sent three kinds of detective to Baker Street:

- **The Lone Genius (GPT6-Astra).** One large reasoning model takes a cab from address to address, reads every lead itself, and decides when to accuse. It gets 20 visits.
- **Holmes (GPT6-Astra) + Jev Swarm.** GPT6-Astra plays Holmes. He never leaves 221B. He sends twelve street boys, each a small, fast **Jev** model, out on errands, reads their reports, and decides what to check next and when to name the culprit.
- **Jev Swarm.** A hundred Jev boys and no leader. Each boy keeps his own notebook, shares what he finds with the boys nearby, and votes. When thirty boys name the same culprit, motive and hideout, the case closes.

We ran each on the same 100 seeded cases, then on 100 harder "frame-up" cases where the murderer bribes witnesses to lie. Every number below comes from those 600 runs. No model decision fell back to a scripted rule; we logged every move, clue and vote, and you can replay any case yourself on the interactive site.

The short version: **the leader with a swarm solved 96 of 100 cases, the lone genius 57, and the leaderless swarm 38.** But the interesting part is *why*.

---

## 1. The genius is limited by legwork, not by brains

Start with the Lone Genius. GPT6-Astra is a strong reasoner. Watch its notes during a case and you see good detective work: "Repeated cigar ash and dark hairs identify Henry Pargeter; chapel evidence corroborates his refuge." When it finds the evidence, it almost always draws the right conclusion.

The problem is that it does not find the evidence. In 59 of 100 standard cases it ran out of visits or time before accusing. Its misses are telling. It gets the hideout right every single time, the culprit 83 times out of 100, but the motive only 68 times. The clues about motive tend to sit near the victim's home, a short detour from the trail of footprints. A single detective, one cab and one door at a time, keeps following the hottest trail and never gets to them.

We checked this directly. We gave the Lone Genius twice the budget, 24 hours and 40 visits, and re-ran all 100 cases. Its solve rate jumped from **57 to 91**. Nothing about its reasoning changed. It simply got to knock on more doors.

But that improvement comes at a cost: about 15 hours of case time and two minutes of real time per case. Meanwhile, Holmes (GPT6-Astra) + Jev Swarm solves **96** cases within the original twelve hours, in about 11 case hours and a minute and a half of real time.

That is the first lesson. A single strong model is serial. It can only be in one place at a time, and every clue costs it a full round trip. Twelve small agents searching in parallel buy you coverage that no amount of reasoning can substitute for. Holmes's boys check about 70 addresses per case (median); the lone genius manages 20.

There is a cheaper way to see the same point. A simple scripted detective that just counts clues, with no language model at all, solves 61 of the standard cases alone, slightly more than GPT6-Astra alone. Give it 40 visits and it reaches 99. On these honest cases, where every true fact appears twice and each lie only once, careful counting is enough. What is missing is the legwork.

---

## 2. The swarm agrees fast, but agreeing is not the same as being right

If coverage is the bottleneck, why not go all the way: a hundred agents, no leader, maximum parallelism?

The Jev Swarm is genuinely fast. A hundred boys start spread across the city, share leads with their neighbours, and converge. It reaches a thirty-vote agreement in 91 of 100 cases, with a median of just 2.2 case hours and about nine seconds of real time. On the map you can watch it happen: the boys' colours (each colour is one answer) spread from a few clusters until one answer dominates the city.

But it is often wrong. Of those 91 agreements, **53 were on the wrong answer**. The swarm solves only 38 cases.

Look at how it fails and the pattern is clear. A few boys misjudge a clue, say they weigh a lying witness too heavily or misread a description. Their neighbours, who have not seen the evidence themselves, copy the confident vote. The wrong answer snowballs through the gossip network and hits thirty votes before anyone checks. In one case we show in the trailer, two clusters formed around two different innocent suspects, both with the right motive and the right hideout, and the swarm closed on one of them.

This is not a problem with searching. The swarm covers the map beautifully. It is a problem with *judging*. To prove it, we ran a hybrid swarm in which Jev chooses where to go and what to share, but a simple counting rule casts the votes. On standard cases that lifted a 2 km swarm from 11 to 16 solved out of 20 in our earlier benchmark, and a fully scripted counting swarm solves 95 of 100. The small model is good at the many quick, local "where next?" decisions. It is weak as an independent voter, where small misjudgments compound with no one in charge.

The second lesson: parallelism without judgment converges, confidently, on whatever the crowd happens to amplify.

---

## 3. When somebody lies, only a reasoning leader sees through it

So far a skeptic could say: on these cases a simple counting Holmes with a swarm of boys does just as well as GPT6-Astra. And they would be right. Holmes (heuristic) + Jev Swarm solves 95 of 100 standard cases, about 30% faster in case time and twenty times faster in real time. If the world were honest, you would not need a frontier model as the leader.

The world is not honest. So we built a hundred more cases in which **somebody lies on purpose**. In each "frame-up" case, the murderer pays his own servants to describe an innocent suspect and to swear their master never left the house. A planted clue at the scene backs them up. Each false detail now appears twice, matching the true one, and the lie outnumbers the truth. Somewhere in the city, two honest witnesses saw the bribe being paid.

Here the results split cleanly:

| Method | Standard cases | Frame-up cases |
|---|---|---|
| The Lone Genius (GPT6-Astra) | 57 | 59 |
| **Holmes (GPT6-Astra) + Jev Swarm** | **96** | **93** |
| Jev Swarm | 38 | 42 |
| Holmes (heuristic) + Jev Swarm | 95 | **0** |
| Holmes (heuristic) + heuristic Swarm | 97 | 1 |

Every method that counts collapses. The counting Holmes names the framed man almost every time, because two matching lies beat one true clue. It still gets the motive and hideout right, but it never catches the real murderer.

GPT6-Astra does not fall for it. As Holmes, reading his boys' reports, he writes things like: "Pargeter's servants supply both his alibi and the evidence against Leopold; the dry snuff-box suggests planting. Pargeter merits suspicion, not accusation." It notices who is speaking, not just how often something is said. Holmes (GPT6-Astra) + Jev Swarm solves 93 of 100 frame-ups. The Lone Genius reasons just as well, it names the right culprit almost every time, but still runs out of doors before the motive. The leaderless Jev Swarm does better than any counting player, because some boys read the testimony and doubt it, yet without a leader it still often agrees on the framed man.

(A note of honesty: the lone genius and the swarm score a few points higher on frame-ups than on standard cases. That is within chance, the 95% intervals overlap almost entirely, and the frame-up cases include extra handles a careful reader can use, like the witnesses who saw the bribe. The lie is built to fool counting, and it does.)

The third lesson is the synergy. The swarm brings coverage and speed. The reasoning leader brings judgment. On easy cases you can get away with either one alone being simple. On cases built to deceive, you need both: the many minds to go everywhere and overhear everyone, and the one mind to decide whom to believe.

---

## What this suggests

Holmes knew it in 1890. The street boys were never meant to solve the case; they were meant to find the pieces. The genius was never meant to walk every street; he was meant to see the shape the pieces make.

For multi-agent AI, our toy London suggests a simple division of labour:

- **Use small, fast agents for the many local decisions**: where to look next, what to report, when to come back. They are cheap, they parallelize, and they are good at it. In our runs, Jev's errand decisions were as useful as a carefully scripted rule.
- **Do not let a crowd of small agents be the judge.** Voting among small models converges fast and wrong, especially under deception.
- **Put a strong reasoner at the point of judgment**, reading everything the swarm brings back. That is where a frontier model earns its cost, and where it turns a fast, error-prone crowd into a detective agency that solves 96 of 100 cases, and 93 of 100 when the witnesses lie.

One genius, or many minds? Holmes's answer, and ours: one genius, and many minds.

---

*Methods in brief.* Cases are generated from a seed: 100 addresses on a street graph, 10 suspects with six visible traits, 6 motives, 8 candidate hideouts; true key facts appear at two addresses, lone lies at one; frame-up cases add coordinated lies, a planted clue, timed alibis and witnesses to the bribe, and each is checked to be solvable by a careful reader. All approaches get 12 case hours. Holmes's boys walk; the lone genius takes cabs. The Jev swarm uses a 2 km shouting range and closes at 30 identical votes. Model calls were allowed 30 seconds; zero decisions fell back to a rule. 95% Wilson intervals are in the tables. Replay every case at the interactive site.
