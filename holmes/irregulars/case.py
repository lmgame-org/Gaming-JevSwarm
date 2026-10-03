"""Seeded, procedural cases: a London map of addresses, suspects, motive, hideout and one lead per address.

Everything is generated from `random.Random(seed)`, so the same settings and seed give the same case. Lead text is
original; the only borrowed names are public-domain Holmes characters. Each lead also carries a structured `fact`
(used by the rule baseline and by the evaluator) that model-driven detectives never see.

Fact kinds:
  trait(dim, value)      the culprit has this trait            (true, or a lie with a wrong value)
  alibi(suspect)         this suspect could not have done it   (true for an innocent, a lie for the culprit)
  motive(m)              the motive was m
  hide_district(d)       the hideout is in district d
  hide_type(t)           the hideout is a place of type t
  hide_found / hide_not  searched a candidate hideout: occupied / untouched (never lies)
  pointer(address)       go and ask at that address (it holds a true key lead)
  herring / bland        no evidential value

Holmesian cases (difficulty = holmesian) add:
  seen(suspect, address, from, to)  a timed sighting; an alibi only if it covers the time of death and the address is
                                    beyond the scene's neighbouring districts
  trace(phrase)          mud or dust that names the hideout district only through the index in the case file
  bribe(suspect)         this suspect paid witnesses to tell one story (true; the clue that exposes the frame-up)
and a frame-up: the culprit's own servants give matching false descriptions of an innocent suspect (two copies of
each lie against one copy of the truth) plus a false alibi for the culprit, and one clue at the scene is planted.
"""
import heapq
import math
import random

# Map units are 10 m; the map is 1000 x 700 units (10 x 7 km). The Thames runs west to east across the south.
DISTRICTS = [
    ("Kensington", 110, 330), ("Marylebone", 300, 170), ("Bloomsbury", 470, 150), ("Soho", 400, 300),
    ("Covent Garden", 530, 310), ("Westminster", 420, 430), ("The City", 680, 280), ("Whitechapel", 850, 230),
    ("Southwark", 640, 600), ("Limehouse", 930, 400),
]
ADJACENT = {
    "Kensington": ["Marylebone", "Soho", "Westminster"], "Marylebone": ["Kensington", "Bloomsbury", "Soho"],
    "Bloomsbury": ["Marylebone", "Soho", "Covent Garden", "The City"],
    "Soho": ["Marylebone", "Bloomsbury", "Covent Garden", "Westminster", "Kensington"],
    "Covent Garden": ["Soho", "Bloomsbury", "The City", "Westminster"],
    "Westminster": ["Soho", "Covent Garden", "Kensington", "Southwark"],
    "The City": ["Covent Garden", "Bloomsbury", "Whitechapel", "Southwark"],
    "Whitechapel": ["The City", "Limehouse"], "Southwark": ["Westminster", "The City", "Limehouse"],
    "Limehouse": ["Whitechapel", "Southwark"],
}
THAMES = [(0, 505), (160, 520), (300, 545), (420, 520), (520, 480), (640, 505), (760, 520), (880, 500), (1000, 540)]
STREETS = {
    "Kensington": ["Gloucester Road", "Earl's Court Road", "Holland Street", "Church Street", "Phillimore Place"],
    "Marylebone": ["Dorset Street", "York Place", "Blandford Street", "Paddington Street", "George Street"],
    "Bloomsbury": ["Great Russell Street", "Montague Place", "Gower Street", "Bedford Row", "Store Street"],
    "Soho": ["Wardour Street", "Frith Street", "Greek Street", "Old Compton Street", "Dean Street"],
    "Covent Garden": ["Long Acre", "Bow Street", "Floral Street", "Maiden Lane", "Henrietta Street"],
    "Westminster": ["Great Smith Street", "Horseferry Road", "Tothill Street", "Millbank", "Vincent Square"],
    "The City": ["Cheapside", "Threadneedle Street", "Fleet Street", "Ludgate Hill", "Cornhill"],
    "Whitechapel": ["Commercial Street", "Brick Lane", "Flower and Dean Street", "Hanbury Street", "Wentworth Street"],
    "Southwark": ["Borough High Street", "Bankside", "Union Street", "Tooley Street", "Clink Street"],
    "Limehouse": ["Narrow Street", "Three Colt Street", "Ropemakers Fields", "West India Dock Road", "Pennyfields"],
}
PLACE_TYPES = ["tobacconist", "pawnbroker", "chemist", "public house", "lodging house", "cab rank", "post office",
               "bank", "church", "music hall", "coffee house", "tailor", "bookshop", "bakery", "telegraph office",
               "solicitor's office", "gentlemen's club", "print shop", "laundry", "gunsmith", "hospital",
               "theatre", "butcher", "ironmonger", "chandler", "fishmonger", "hotel", "school", "workhouse"]
HIDE_TYPES = ["warehouse", "cellar", "boathouse", "disused chapel", "stables", "attic room", "opium den", "crypt"]

TRAITS = {
    "height": {"tall": "tall", "medium": "of middling height", "short": "short"},
    "hand": {"left": "left-handed", "right": "right-handed"},
    "hair": {"dark": "dark-haired", "fair": "fair-haired", "red": "red-haired", "grey": "grey-haired"},
    "tobacco": {"pipe": "smokes a pipe of coarse shag", "cigar": "smokes Havana cigars",
                "turkish": "smokes Turkish cigarettes", "snuff": "takes snuff"},
    "boots": {"large": "wears large, heavy boots", "small": "wears small, narrow boots"},
    "gait": {"limp": "walks with a limp", "brisk": "walks briskly, no limp"},
}
TRAIT_LEADS = {  # what a witness or a trace says about the culprit
    "height": ["{who} saw a figure slip away from {scene} near midnight. {Pron} is sure the person was {v}.",
               "A smear on a doorframe here sits at a height that only a {v} person would reach, says {who}."],
    "hand": ["{who} sold a pocket-knife late that night to a customer who paid and pocketed it {v}.",
             "The police surgeon's note, shown here by {who}, says the blow was struck by someone {v}."],
    "hair": ["{who} found a few strands of hair caught on the railings near {scene}: the culprit is {v}.",
             "A hat dropped in the fog and handed in by {who} holds hairs from someone {v}."],
    "tobacco": ["{who} swept up ash outside {scene} next morning; the culprit {v}.",
                "{who} says the stranger who asked the way to {scene} {v}."],
    "boots": ["{who} points out fresh prints in the mud: the culprit {v}.",
              "A cobbler, through {who}, says a customer who {v} paid in a hurry to have them cleaned of mud."],
    "gait": ["{who} watched someone hurry along the lane from {scene}; the person {v}.",
             "{who} heard the steps of the one who left {scene}: the person {v}."],
}
MOTIVES = {
    "inheritance": "inheritance: the victim was about to change a will",
    "blackmail": "blackmail: the victim was extorting someone",
    "revenge": "revenge for an old wrong done by the victim",
    "debt": "debt: the victim was calling in large loans",
    "jealousy": "jealousy: a rival in love",
    "secret": "a stolen secret: the victim held papers someone wanted",
}
MOTIVE_LEADS = {
    "inheritance": ["A clerk lets slip that {V} had summoned a solicitor to rewrite the will that very week.",
                    "Half-burnt in the grate: a draft of a new will in {V}'s hand, cutting someone out entirely."],
    "blackmail": ["A ledger hidden in {V}'s desk lists monthly payments from someone marked only with a cross.",
                  "{who} heard {V} boast of 'a letter worth a hundred pounds a month to keep quiet.'"],
    "revenge": ["An old newspaper cutting here tells how {V}'s testimony once sent an innocent man to prison.",
                "{who} remembers someone swearing, years ago, that {V} would pay for what was done to the family."],
    "debt": ["The pawnbroker's ledger shows {V} held IOUs worth eight hundred pounds, all called in that week.",
             "{who} says {V} had sent a final demand for a large debt, with a threat of the courts."],
    "jealousy": ["Unsigned love letters to {V} end with the line: 'If not me, then no one.'",
                 "{who} saw a furious quarrel over a sweetheart between {V} and someone the night before."],
    "secret": ["{V} had copied confidential papers, says {who}, and they were missing from the body.",
               "A torn envelope marked 'Admiralty, private' was found in {V}'s rooms, empty."],
}
DISTRICT_LEADS = ["{who} rowed a silent passenger toward {d} in the small hours and was paid double to forget it.",
                  "Mud on a cloak thrown away by the culprit is the sort found only in {d}, says {who}.",
                  "{who} saw a figure matching the culprit's walk heading into {d} before dawn."]
TYPE_LEADS = {
    "warehouse": "{who} sold a stranger a lamp 'to see by among the bales', with tea-dust on the coat.",
    "cellar": "{who} sold a week's worth of candles to a stranger who said they were 'for a cellar'.",
    "boathouse": "The culprit's dropped glove smells of tar and river-weed, the kind from a boathouse, says {who}.",
    "disused chapel": "{who} noticed candle wax and hymn-book dust on the sleeve of the stranger.",
    "stables": "{who} says the stranger bought liniment and smelt of straw and horses.",
    "attic room": "{who} let a slanting attic room for cash to someone who gave no name.",
    "opium den": "The stranger's coat reeked of sweet smoke, the kind from an opium den, says {who}.",
    "crypt": "{who} saw the stranger carry blankets down the steps toward a crypt.",
}
WITNESSES = ["a cabman", "a crossing-sweeper", "a flower seller", "the night watchman", "the barmaid",
             "the shop boy", "a constable on his beat", "the landlady", "the chemist's assistant", "a telegraph boy",
             "a lamplighter", "an old soldier", "the publican", "a newspaper seller", "a dock porter"]
BLAND = ["Nobody here saw anything; the fog was too thick that night.",
         "The proprietor talks only of the price of coal and the noise from the street.",
         "A drunk swears the Professor's men are behind every crime in London, then falls asleep.",
         "The shop was shut all evening; the owner was at a christening in Kent.",
         "{who} offers a long story about a missing dog. It has nothing to do with the case.",
         "The clerk is helpful but knows nothing about the victim.",
         "Everyone here was at the music hall that night and heard nothing.",
         "{who} complains that the police never come when they are wanted.",
         "The regulars argue about the cricket. No one knew the victim.",
         "A notice in the window advertises a lost umbrella. Nothing else of interest."]
HERRINGS = ["{S} was seen buying arsenic here; the chemist confirms it is for the rats that plague {S}'s lodgings.",
            "{S} quarrelled loudly with {V} last spring, but {who} says they made it up over dinner a month ago.",
            "{who} thinks {S} 'has a guilty face', but cannot say why or when.",
            "A rumour here says {V} owed money all over town, though no one can name a single creditor.",
            "{S} pawned a gold watch here on the day of the crime; the ticket shows it was a family heirloom, "
            "pawned every quarter-day.",
            "A fortune teller announces that the culprit's name begins with a letter of the alphabet.",
            "{who} saw someone in a long coat near {scene} a week before the crime, on a different errand.",
            "A letter here mentions {V} and '{S}', but it is a dinner invitation from last Christmas.",
            "{S} has a fresh bandage on one hand; {who} saw the cooking accident that caused it."]
ALIBI_LEADS = ["{who} swears {S} was here from nine until past two that night and never once left.",
               "{S} spent the whole night at the bedside of a sick child here, says {who}.",
               "The register here shows {S} signed in at ten and the night porter saw no one leave before six."]
# Holmesian cases: the mud and dust of each district (published in the case file as Holmes's index)
TRACES = {
    "Kensington": "fine yellow gravel from the walks of the Royal Gardens",
    "Marylebone": "pale sand from the riding tracks of the Regent's Park",
    "Bloomsbury": "white plaster dust from the works at the Museum",
    "Soho": "sawdust soaked in wine from the eating-house floors",
    "Covent Garden": "crushed cabbage leaf and orange peel from the market",
    "Westminster": "grey stone-dust from the Abbey masons' yard",
    "The City": "printer's ink and paper fluff from the presses",
    "Whitechapel": "the black, sour dye of the tanneries",
    "Southwark": "red brick-clay from the Bankside kilns",
    "Limehouse": "tar and loose hemp from the rope-walks by the docks",
}
TRACE_TO_DISTRICT = {v: k for k, v in TRACES.items()}
TRACE_LEADS = ["{Who} sold bread at dawn to a stranger whose boots were caked with {t}.",
               "The cloak the culprit threw into the area railings is streaked with {t}, says {who}.",
               "{Who} noticed {t} on the cuffs of a hurried stranger asking for the cheapest room going."]
SERVANTS = ["the coachman in {C}'s service", "{C}'s housekeeper", "a groom from {C}'s stables", "{C}'s valet",
            "a clerk employed by {C}", "{C}'s cook", "the boot-boy in {C}'s house"]
BRIBE_LEADS = ["The publican saw {C} hand a sovereign each to three of {C}'s own servants the morning after, saying "
               "'and mind you all tell it the same way.'",
               "A bank clerk says {C} drew twenty pounds in sovereigns at opening time the day after the murder; by "
               "noon {C}'s household staff were all wearing new boots."]
PLANTED = {
    "tobacco": {"pipe": "a clay pipe still packed with coarse shag", "cigar": "the stub of a Havana cigar",
                "turkish": "the end of a Turkish cigarette", "snuff": "a small silver snuff-box"},
}
SIGHT_PLACES = ["drinking at the {p}", "playing whist at the {p}", "seen by the doorman at the {p}",
                "arguing with a cabman outside the {p}"]
DEATH = ("23:30", "00:00")

FIRST = ["Arthur", "Edith", "Henry", "Clara", "Walter", "Agnes", "Frederick", "Maud", "Septimus", "Lydia", "Ambrose",
         "Harriet", "Cornelius", "Beatrice", "Rupert", "Florence", "Silas", "Winifred", "Jasper", "Ottilie", "Bertram",
         "Isadora", "Leopold", "Prudence"]
LAST = ["Ashdown", "Bellweather", "Carrow", "Drummond", "Esterby", "Fenwick", "Gilchrist", "Holloway", "Ingleby",
        "Jessop", "Kettering", "Lathbury", "Mottram", "Nettleship", "Ormerod", "Pargeter", "Quilliam", "Ravensworth",
        "Stainforth", "Tregarthen", "Upcott", "Vavasour", "Wetherell", "Yarrow"]
OCCUPATIONS = ["banker", "music-hall singer", "retired colonel", "ship's chandler", "governess", "solicitor's clerk",
               "art dealer", "physician", "printer", "boxing instructor", "widowed landlady", "Admiralty clerk",
               "stockbroker", "theatre manager", "curate", "jeweller"]
FEMININE = {"Edith", "Clara", "Agnes", "Maud", "Lydia", "Harriet", "Beatrice", "Florence", "Winifred", "Ottilie",
            "Isadora", "Prudence"}


def _dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


class Case:
    def __init__(self, cfg):
        self.cfg = cfg
        self.seed = cfg["seed"]
        r = random.Random(f"holmes-{cfg['seed']}")
        self.r = r
        self._build_map(cfg["n_addresses"])
        self._build_cast(cfg["n_suspects"], cfg["n_motives"], cfg["n_hideouts"])
        self.holmesian = cfg.get("difficulty") == "holmesian"
        self.framed = None
        if self.holmesian:
            for _ in range(12):  # regenerate until a careful reader can solve it
                self._place_leads_holmesian()
                if all(self.solvable.values()):
                    break
        else:
            self._place_leads()

    # ------------------------------------------------------------------ map
    def _build_map(self, n):
        r = self.r
        n = max(20, n)
        self.addresses = []
        used = set()
        per = [n // len(DISTRICTS) + (1 if i < n % len(DISTRICTS) else 0) for i in range(len(DISTRICTS))]
        for (name, cx, cy), k in zip(DISTRICTS, per):
            for _ in range(k):
                for _try in range(40):
                    x = min(990, max(10, r.gauss(cx, 48)))
                    y = min(690, max(10, r.gauss(cy, 42)))
                    south = name == "Southwark"
                    ry = _river_y(x)
                    if (south and y > ry + 22) or (not south and y < ry - 22):
                        break
                label = None
                while not label or label in used:
                    label = f"{r.randint(1, 120)} {r.choice(STREETS[name])}"
                used.add(label)
                self.addresses.append({"id": "", "street": label, "district": name, "type": r.choice(PLACE_TYPES),
                                       "x": round(x, 1), "y": round(y, 1)})
        self.addresses.sort(key=lambda a: (a["district"], a["street"]))
        for i, a in enumerate(self.addresses):
            a["id"] = f"A{i + 1:02d}" if n < 100 else f"A{i + 1:03d}"
        self.by_id = {a["id"]: a for a in self.addresses}
        # Streets: each address links to its 3 nearest, plus a spanning tree so the map is connected.
        self.edges = set()
        for a in self.addresses:
            near = sorted((b for b in self.addresses if b is not a), key=lambda b: _dist(a, b))[:3]
            for b in near:
                self.edges.add(tuple(sorted((a["id"], b["id"]))))
        inside, rest = {self.addresses[0]["id"]}, {a["id"] for a in self.addresses[1:]}
        while rest:
            best = min(((_dist(self.by_id[i], self.by_id[j]), i, j) for i in inside for j in rest))
            self.edges.add(tuple(sorted((best[1], best[2]))))
            inside.add(best[2])
            rest.discard(best[2])
        self.nbrs = {a["id"]: [] for a in self.addresses}
        for i, j in self.edges:
            w = _dist(self.by_id[i], self.by_id[j])
            self.nbrs[i].append((j, w))
            self.nbrs[j].append((i, w))
        self._paths = {}

    def path_len(self, src):
        """Street distance (map units) from src to every address (Dijkstra, cached)."""
        if src in self._paths:
            return self._paths[src]
        d = {src: 0.0}
        h = [(0.0, src)]
        while h:
            du, u = heapq.heappop(h)
            if du > d.get(u, 1e18):
                continue
            for v, w in self.nbrs[u]:
                nd = du + w
                if nd < d.get(v, 1e18):
                    d[v] = nd
                    heapq.heappush(h, (nd, v))
        self._paths[src] = d
        return d

    def hops(self, src):
        """Number of street links from src to every address (BFS, cached)."""
        if not hasattr(self, "_hops"):
            self._hops = {}
        if src not in self._hops:
            d, frontier = {src: 0}, [src]
            while frontier:
                nxt = []
                for u in frontier:
                    for v, _ in self.nbrs[u]:
                        if v not in d:
                            d[v] = d[u] + 1
                            nxt.append(v)
                frontier = nxt
            self._hops[src] = d
        return self._hops[src]

    def travel_min(self, a, b):
        return self.path_len(a)[b] * 10.0 / self.cfg["cab_m_per_min"]

    def nearest(self, src, k, pool=None):
        d = self.path_len(src)
        ids = [a for a in (pool if pool is not None else self.by_id) if a != src]
        return sorted(ids, key=lambda a: d[a])[:k]

    # ------------------------------------------------------------------ people, motive, hideout
    def _build_cast(self, n_s, n_m, n_h):
        r = self.r
        n_s, n_m, n_h = max(3, min(16, n_s)), max(2, min(6, n_m)), max(2, min(8, n_h))
        ids = [a["id"] for a in self.addresses]
        specials = {}
        baker = r.choice([a for a in ids if self.by_id[a]["district"] == "Marylebone"])
        self.by_id[baker].update(street="221B Baker Street", type="lodgings of Mr Sherlock Holmes")
        yard = r.choice([a for a in ids if self.by_id[a]["district"] == "Westminster"])
        self.by_id[yard].update(street="Scotland Yard", type="police headquarters")
        specials["baker"], specials["yard"] = baker, yard
        free = [a for a in ids if a not in (baker, yard)]
        r.shuffle(free)
        scene = free.pop()
        self.by_id[scene]["type"] = r.choice(["townhouse", "counting-house", "chambers", "bookshop"])
        names = r.sample([(f, l) for f in FIRST for l in LAST], n_s + 1)
        occ = r.sample(OCCUPATIONS, min(len(OCCUPATIONS), n_s + 1))
        vf, vl = names[0]
        victim_home = free.pop()
        self.victim = {"name": f"{vf} {vl}", "occupation": occ[0], "home": victim_home}
        # hideout candidates: one per district where possible, each with its own place type
        dists = r.sample([d[0] for d in DISTRICTS], n_h)
        types = r.sample(HIDE_TYPES, n_h)
        self.hideouts = []
        for k, (dname, t) in enumerate(zip(dists, types)):
            pool = [a for a in free if self.by_id[a]["district"] == dname] or free
            a = r.choice(pool)
            free.remove(a)
            self.by_id[a]["type"] = t
            self.hideouts.append({"id": f"H{k + 1}", "address": a, "district": dname, "type": t})
        self.suspects = []
        for k in range(n_s):
            f, l = names[k + 1]
            home = free.pop()
            self.by_id[home]["type"] = r.choice(["lodging house", "townhouse", "boarding house", "rooms above a shop"])
            self.suspects.append({"id": f"S{k + 1}", "name": f"{f} {l}", "occupation": occ[(k + 1) % len(occ)],
                                  "home": home, "fem": f in FEMININE,
                                  "traits": {d: r.choice(list(v)) for d, v in TRAITS.items()}})
        self.motives = r.sample(list(MOTIVES), n_m)
        culprit = r.choice(self.suspects)
        # make sure the culprit's full trait profile is unique (re-roll innocents that collide)
        for s in self.suspects:
            while s is not culprit and s["traits"] == culprit["traits"]:
                s["traits"] = {d: r.choice(list(v)) for d, v in TRAITS.items()}
        self.truth = {"culprit": culprit["id"], "motive": r.choice(self.motives),
                      "hideout": r.choice(self.hideouts)["id"]}
        self.scene, self.specials, self.free = scene, specials, free

    def suspect(self, sid):
        return next((s for s in self.suspects if s["id"] == sid), None)

    def hideout(self, hid):
        return next((h for h in self.hideouts if h["id"] == hid), None)

    # ------------------------------------------------------------------ leads
    def _place_leads(self):
        r, cfg = self.r, self.cfg
        culprit = self.suspect(self.truth["culprit"])
        hide = self.hideout(self.truth["hideout"])
        red = max(1, cfg["redundancy"])
        self.leads = {}
        # 1. which facts identify the culprit: trait dimensions until <= 3 suspects remain, then alibis for the rest
        dims = list(TRAITS)
        r.shuffle(dims)
        alive, used_dims = list(self.suspects), []
        for d in dims:
            if len(alive) <= 3 and len(used_dims) >= 2:
                break
            used_dims.append(d)
            alive = [s for s in alive if s["traits"][d] == culprit["traits"][d]]
        key = [("trait", d, culprit["traits"][d]) for d in used_dims]
        key += [("alibi", s["id"]) for s in alive if s is not culprit]
        key += [("motive", self.truth["motive"]), ("hide_district", hide["district"]), ("hide_type", hide["type"])]
        self.key_facts = key
        # 2. reserved addresses
        taken = {self.specials["baker"], self.specials["yard"], self.scene}
        for h in self.hideouts:
            self._set(h["address"], ("hide_found" if h is hide else "hide_not", h["address"]), h=h)
            taken.add(h["address"])
        # 3. key leads, each `redundancy` times, near where they belong
        copies = []
        for f in key:
            for _ in range(red):
                copies.append(f)
        placed_key = []
        scene_first = None
        for f in copies:
            if f[0] == "trait" and scene_first is None and f[1] in ("boots", "tobacco", "hair"):
                v = TRAITS[f[1]][f[2]]
                self._set(self.scene, f, text={
                    "boots": f"In the mud by the door of the scene, fresh prints: the culprit {v}.",
                    "tobacco": f"Ash on the hearth at the scene shows the culprit {v}.",
                    "hair": f"Strands of hair are caught in the victim's fingers: the culprit is {v}."}[f[1]])
                scene_first = f
                placed_key.append(self.scene)
                continue
            a = self._spot(f, taken)
            if a:
                self._set(a, f)
                taken.add(a)
                placed_key.append(a)
        if self.scene not in self.leads:
            self._set(self.scene, ("bland",))
        # 4. lies: single copies, each contradicting a key fact; spread over culprit / motive / hideout facts and
        #    never more copies of one lie than `redundancy - 1`, so every fact keeps a majority when all is read
        n_lies = round(cfg["lie_rate"] * len(copies))
        groups = [[f for f in key if f[0] in ("trait", "alibi")], [f for f in key if f[0] == "motive"],
                  [f for f in key if f[0].startswith("hide_")]]
        for g in groups:
            r.shuffle(g)
        r.shuffle(groups)
        targets = [g[i] for i in range(max(map(len, groups))) for g in groups if i < len(g)]
        self.lies, seen = [], {}
        k = 0
        while len(self.lies) < n_lies and k < 4 * len(targets):
            lie = self._lie(targets[k % len(targets)], culprit)
            k += 1
            if not lie or seen.get(lie, 0) >= max(1, red - 1):
                continue
            pool = [a for a in self.by_id if a not in taken]
            if not pool:
                break
            a = r.choice(pool)
            self._set(a, lie, lie=True)
            seen[lie] = seen.get(lie, 0) + 1
            taken.add(a)
            self.lies.append(a)
        # 5. pointers to key leads, from near the scene, Scotland Yard and Baker Street
        targets = [a for a in placed_key if a != self.scene]
        r.shuffle(targets)
        n_ptr = round(cfg["pointer_rate"] * len(targets))
        first = targets[0] if targets else None
        self._set(self.specials["baker"], ("pointer", first) if first else ("bland",), who="Mrs Hudson",
                  text=(f"Mrs Hudson hands over a telegram from Inspector Lestrade: 'Witness worth hearing at "
                        f"{self.label(first)}.'") if first else None)
        second = targets[1] if len(targets) > 1 else first
        self._set(self.specials["yard"], ("pointer", second) if second else ("bland",), who="Inspector Lestrade",
                  text=(f"Inspector Lestrade grumbles that the Yard has it in hand, but admits someone at "
                        f"{self.label(second)} told a constable something odd.") if second else None)
        near_scene = self.nearest(self.scene, 25)
        for t in targets[2:2 + n_ptr]:
            pool = [a for a in near_scene if a not in taken] or [a for a in self.by_id if a not in taken]
            if not pool:
                break
            a = r.choice(pool[:12])
            self._set(a, ("pointer", t))
            taken.add(a)
        # 6. everything else: herrings and bland
        for a in self.by_id:
            if a in self.leads:
                continue
            self._set(a, ("herring",) if r.random() < cfg["red_herring_rate"] else ("bland",))
        self.solvable = self._oracle()

    # ------------------------------------------------------------------ Holmesian leads
    def near_districts(self):
        """The scene's district and its neighbours: nobody beyond them could reach the scene at the time of death."""
        d = self.by_id[self.scene]["district"]
        return {d, *ADJACENT[d]}

    def clears(self, f):
        """Does a seen(...) fact give that suspect an alibi?"""
        if f[0] != "seen" or len(f) < 5:
            return False
        frm, to = _tmin(f[3]), _tmin(f[4])
        return frm <= _tmin(DEATH[0]) and to >= _tmin(DEATH[1]) and \
            self.by_id[f[2]]["district"] not in self.near_districts()

    def _place_leads_holmesian(self):
        r, cfg = self.r, self.cfg
        culprit = self.suspect(self.truth["culprit"])
        C = culprit["name"]
        hide = self.hideout(self.truth["hideout"])
        self.leads = {}
        near = self.near_districts()
        far = [a for a in self.by_id if self.by_id[a]["district"] not in near]
        close = [a for a in self.by_id if self.by_id[a]["district"] in near]
        # 1. culprit facts: traits (one copy each) until three suspects remain, then timed sightings for the others
        dims = list(TRAITS)
        r.shuffle(dims)
        alive, used = list(self.suspects), []
        for d in dims:
            if len(alive) <= 3 and len(used) >= 2:
                break
            used.append(d)
            alive = [s for s in alive if s["traits"][d] == culprit["traits"][d]]
        innocents = [s for s in self.suspects if s is not culprit]
        # the framed suspect: an innocent who differs from the culprit on as many of those traits as possible
        framed = max(innocents, key=lambda s: (sum(s["traits"][d] != culprit["traits"][d] for d in used), r.random()))
        if framed in alive:
            alive.remove(framed)
        self.framed = framed["id"]
        key = [("trait", d, culprit["traits"][d]) for d in used]
        sightings = []
        for s in alive:
            if s is culprit:
                continue
            frm, to = r.choice([("22:45", "01:00"), ("23:00", "00:30"), ("23:15", "00:15")])
            sightings.append(("seen", s["id"], None, frm, to))
        key += [("motive", self.truth["motive"])] * 2
        key += [("trace", TRACES[hide["district"]])] * 2 + [("hide_type", hide["type"])] * 2
        taken = {self.specials["baker"], self.specials["yard"], self.scene}
        for h in self.hideouts:
            self._set(h["address"], ("hide_found" if h is hide else "hide_not", h["address"]), h=h)
            taken.add(h["address"])
        placed_key = []

        def put(fact, pool, **kw):
            pool = [a for a in pool if a not in taken]
            if not pool:
                pool = [a for a in self.by_id if a not in taken]
            if not pool:
                return None
            a = r.choice(pool[:12])
            self._set(a, fact, **kw)
            taken.add(a)
            return a

        for f in key:
            a = self._spot(f, taken) if f[0] != "trace" else put(f, self.nearest(hide["address"], 22))
            if a and f[0] != "trace":
                self._set(a, f)
                taken.add(a)
            if a:
                placed_key.append(a)
        true_seen = []
        for f in sightings:
            a = put(None, r.sample(far, len(far)))
            f = ("seen", f[1], a, f[3], f[4])
            self._set(a, f)
            true_seen.append(f)
            placed_key.append(a)
        # 2. decoy sightings that clear nobody: the culprit early in the evening far away, the framed man close by
        decoys = [("seen", culprit["id"], None, "20:30", "22:00"), ("seen", framed["id"], None, "23:20", "23:50")]
        for f, pool in zip(decoys, (far, close)):
            a = put(None, r.sample(pool, len(pool)))
            if a:
                self._set(a, ("seen", f[1], a, f[3], f[4]))
        # 3. the frame-up: the culprit's servants describe the framed suspect (two copies per trait) and alibi the
        #    culprit; one clue at the scene is planted
        self.frame_addrs = []
        servants = r.sample(SERVANTS, len(SERVANTS))
        k = 0
        frame_facts = [("trait", d, framed["traits"][d]) for d in used if framed["traits"][d] != culprit["traits"][d]]
        frame_facts = [f for f in frame_facts for _ in range(2)] + [("alibi", culprit["id"])] * 2
        for f in frame_facts:
            who = servants[k % len(servants)].format(C=C)
            k += 1
            a = put(None, self.nearest(self.scene, 30))
            if not a:
                break
            if f[0] == "alibi":
                text = (f"{who[0].upper() + who[1:]} swears {C} was at home all that evening and never went out "
                        f"until breakfast.")
                self._set(a, f, lie=True, who=who, text=text)
            else:
                self._set(a, f, lie=True, who=who)
            self.leads[a]["src"] = "frame"
            self.frame_addrs.append(a)
        pd = next((d for d in ("tobacco", "boots", "hair") if framed["traits"][d] != culprit["traits"][d]), None)
        if pd:
            v = framed["traits"][pd]
            if pd == "tobacco":
                text = (f"By the body lies {PLANTED['tobacco'].get(v, 'a tobacco tin')}. Odd: it is bone-dry, though "
                        "rain fell until three in the morning and everything else on the step is soaked.")
            elif pd == "boots":
                text = (f"One sharp print of a {v} boot sits in the flower-bed by the window, yet no other prints "
                        "lead to it or away from it.")
            else:
                text = (f"A few {TRAITS['hair'][v].replace('-haired', '')} hairs lie neatly across the victim's lapel, "
                        "as if laid there, though the room shows a long and desperate struggle.")
            self._set(self.scene, ("trait", pd, v), lie=True, text=text)
            self.leads[self.scene]["src"] = "planted"
        else:
            self._set(self.scene, ("bland",))
        # 4. the clue that exposes the frame (two copies)
        bribes = []
        for t in BRIBE_LEADS:
            a = put(None, self.nearest(culprit["home"], 20))
            if a:
                self._set(a, ("bribe", culprit["id"]), text=t.format(C=C))
                bribes.append(a)
        # 5. ordinary lies, single copies, only against the motive and hideout facts (which have two true copies)
        targets = [f for f in key if f[0] in ("motive", "hide_type")] + [("hide_district", hide["district"])]
        n_lies = round(cfg["lie_rate"] * len(targets) * 2)
        self.lies = list(self.frame_addrs) + ([self.scene] if pd else [])
        seen = set()
        for _ in range(4 * max(1, n_lies)):
            if n_lies <= 0:
                break
            f = r.choice(targets)
            lie = self._lie(f, culprit)
            if not lie or lie in seen:
                continue
            if lie[0] == "hide_district":
                lie = ("trace", TRACES[lie[1]])
            a = put(None, r.sample(list(self.by_id), len(self.by_id)))
            if not a:
                break
            self._set(a, lie, lie=True)
            seen.add(lie)
            self.lies.append(a)
            n_lies -= 1
        self.key_facts = [tuple(f) for f in key] + true_seen + [("bribe", culprit["id"])]
        # 6. pointers: Mrs Hudson and Lestrade point at true leads; more tips near the scene
        targets = [a for a in placed_key + bribes if a != self.scene]
        r.shuffle(targets)
        first = targets[0] if targets else None
        self._set(self.specials["baker"], ("pointer", first) if first else ("bland",), who="Mrs Hudson",
                  text=(f"Mrs Hudson hands over a telegram from Inspector Lestrade: 'Witness worth hearing at "
                        f"{self.label(first)}.'") if first else None)
        second = targets[1] if len(targets) > 1 else first
        self._set(self.specials["yard"], ("pointer", second) if second else ("bland",), who="Inspector Lestrade",
                  text=(f"Inspector Lestrade is sure {framed['name']} did it, and has three witnesses to prove "
                        f"it; but he admits someone at {self.label(second)} told a constable something odd.")
                  if second else None)
        for t in targets[2:2 + round(cfg["pointer_rate"] * len(targets))]:
            put(("pointer", t), self.nearest(self.scene, 25))
        for a in self.by_id:
            if a not in self.leads:
                self._set(a, ("herring",) if r.random() < cfg["red_herring_rate"] else ("bland",))
        self.solvable = self._oracle()
        self.counting_fooled = self._oracle(careful=False)

    def _spot(self, f, taken):
        """A free address appropriate for fact f."""
        r = self.r
        kind = f[0]
        if kind == "trait":
            pool = self.nearest(self.scene, 18)
        elif kind == "alibi":
            home = self.suspect(f[1])["home"]
            pool = ([home] if home not in taken else []) + self.nearest(home, 8)
        elif kind == "motive":
            pool = self.nearest(self.victim["home"], 22)
        else:
            hide = self.hideout(self.truth["hideout"])["address"]
            pool = self.nearest(hide, 22)
        pool = [a for a in pool if a not in taken and a not in self.leads]
        if not pool:
            pool = [a for a in self.by_id if a not in taken and a not in self.leads]
        if not pool:
            return None
        return pool[0] if kind == "alibi" and pool[0] == self.suspect(f[1])["home"] else r.choice(pool[:10])

    def _lie(self, f, culprit):
        r = self.r
        kind = f[0]
        if kind == "trait":
            vals = [v for v in TRAITS[f[1]] if v != f[2]]
            return ("trait", f[1], r.choice(vals))
        if kind == "alibi":
            return ("alibi", culprit["id"])
        if kind == "motive":
            others = [m for m in self.motives if m != f[1]]
            return ("motive", r.choice(others)) if others else None
        if kind == "hide_district":
            others = [h["district"] for h in self.hideouts if h["district"] != f[1]]
            return ("hide_district", r.choice(others)) if others else None
        if kind == "hide_type":
            others = [h["type"] for h in self.hideouts if h["type"] != f[1]]
            return ("hide_type", r.choice(others)) if others else None
        return None

    def _set(self, a, fact, lie=False, who=None, text=None, h=None):
        r = self.r
        if fact is None:  # reserve the address; the caller sets the lead once it knows where it is
            self.leads[a] = {"address": a, "text": "", "fact": ["bland"], "lie": False}
            return
        who = who or r.choice(WITNESSES)
        text = text or self._text(fact, who, h)
        self.leads[a] = {"address": a, "text": text, "fact": list(fact), "lie": lie}

    def _text(self, f, who, h=None):
        r = self.r
        kind = f[0]
        V = self.victim["name"]
        scene = self.by_id[self.scene]["street"]
        Who = who[0].upper() + who[1:]
        if kind == "trait":
            t = r.choice(TRAIT_LEADS[f[1]])
            pron = "she" if who in ("a flower seller", "the barmaid", "the landlady") else "he"
            s = t.format(who=who, scene=scene, v=TRAITS[f[1]][f[2]], Pron=pron.capitalize())
        elif kind == "alibi":
            s = r.choice(ALIBI_LEADS).format(who=who, S=self.suspect(f[1])["name"])
        elif kind == "motive":
            s = r.choice(MOTIVE_LEADS[f[1]]).format(who=who, V=V)
        elif kind == "hide_district":
            s = r.choice(DISTRICT_LEADS).format(who=who, d=f[1])
        elif kind == "trace":
            s = r.choice(TRACE_LEADS).format(who=who, Who=Who, t=f[1])
        elif kind == "seen":
            s = (f"{Who} says {self.suspect(f[1])['name']} was " + r.choice(SIGHT_PLACES).format(p=self.by_id[f[2]]['type'])
                 + f" here, {self.label(f[2])}, from {_clock(f[3])} until {_clock(f[4])} on the night of the murder.")
        elif kind == "bribe":
            s = r.choice(BRIBE_LEADS).format(C=self.suspect(f[1])["name"])
        elif kind == "hide_type":
            s = TYPE_LEADS[f[1]].format(who=who)
        elif kind == "hide_found":
            s = (f"This {h['type']} has been lived in very recently: a cot, cold tea, a bloodied cuff. "
                 "Someone hid here after the crime.")
        elif kind == "hide_not":
            s = f"This {h['type']} is thick with undisturbed dust. Nobody has hidden here."
        elif kind == "pointer":
            s = r.choice(["{Who} says: ask at {a}; they saw more than they let on.",
                          "{Who} heard that someone at {a} knows something about the night in question.",
                          "A scrawled note here reads: 'Ask at {a}.'"]).format(Who=Who, a=self.label(f[1]))
        elif kind == "herring":
            s = r.choice(HERRINGS).format(who=who, S=r.choice(self.suspects)["name"], V=V, scene=scene)
        else:
            s = r.choice(BLAND).format(who=Who)
        return s[0].upper() + s[1:]

    def label(self, a):
        x = self.by_id[a]
        return f"{x['street']}, {x['district']}"

    def _oracle(self, careful=True):
        """Would a perfect reader who saw every lead reach the truth by majority? (evaluator only) In a Holmesian
        case a careful reader also sees through the frame-up (witnesses exposed by a bribe clue) and the planted clue;
        careful=False is plain counting, which the frame-up is built to fool."""
        from .reasoning import deduce
        bribed = {l["fact"][1] for l in self.leads.values() if l["fact"][0] == "bribe"} if careful else set()
        facts = [l["fact"] for l in self.leads.values()
                 if not (careful and (l.get("src") == "planted" or (l.get("src") == "frame" and bribed)))]
        b = deduce(facts, self)
        t = self.truth_ids()
        return {k: b[k]["best"] == t[k] for k in ("culprit", "motive", "hideout")}

    # ------------------------------------------------------------------ views
    def brief(self):
        """What every detective is told at the start (no truth)."""
        out = {
            "victim": f"{self.victim['name']}, {self.victim['occupation']}, found dead at {self.label(self.scene)} "
                      f"({self.scene}) this morning",
            "victim_home": f"{self.label(self.victim['home'])} ({self.victim['home']})",
            "suspects": {s["id"]: f"{s['name']}, {s['occupation']}; " + ", ".join(
                TRAITS[d][s["traits"][d]] for d in TRAITS) + f"; lives at {self.label(s['home'])} ({s['home']})"
                         for s in self.suspects},
            "motives": {f"M{i + 1}": MOTIVES[m] for i, m in enumerate(self.motives)},
            "possible_hideouts": {h["id"]: f"{self.label(h['address'])} ({h['address']}), a {h['type']}"
                                  for h in self.hideouts},
            "task": "Name the culprit, the motive and the hideout. Witnesses sometimes lie; true facts usually "
                    "turn up at more than one address.",
        }
        if self.holmesian:
            d = self.by_id[self.scene]["district"]
            out["task"] = ("Name the culprit, the motive and the hideout. This crime was planned. Some witnesses may "
                           "have been paid to tell the same false story, and a clue may have been planted, so weigh "
                           "who is speaking and whether a clue makes sense, not how often it is repeated. A key clue "
                           "may turn up only once.")
            out["time_of_death"] = "between 11:30 pm and midnight (the police surgeon is certain)"
            out["alibis"] = (f"The scene is in {d}. In that half hour nobody could have reached it from beyond "
                             f"{d} and its neighbouring districts ({', '.join(ADJACENT[d])}).")
            out["holmes_index"] = {k: v for k, v in TRACES.items()}
        return out

    def motive_id(self, m):
        return f"M{self.motives.index(m) + 1}"

    def truth_ids(self):
        return {"culprit": self.truth["culprit"], "motive": self.motive_id(self.truth["motive"]),
                "hideout": self.truth["hideout"]}

    def public_map(self):
        return {"addresses": [{k: a[k] for k in ("id", "street", "district", "type", "x", "y")} for a in self.addresses],
                "edges": sorted(self.edges), "districts": [{"name": n, "x": x, "y": y} for n, x, y in DISTRICTS],
                "thames": THAMES, "baker": self.specials["baker"], "yard": self.specials["yard"],
                "scene": self.scene, "victim_home": self.victim["home"],
                "suspect_homes": {s["id"]: s["home"] for s in self.suspects},
                "hideouts": {h["id"]: h["address"] for h in self.hideouts}}

    def secret(self):
        """Evaluator view: the truth and what each lead really is."""
        return {"truth": self.truth_ids(), "truth_names": {
            "culprit": self.suspect(self.truth["culprit"])["name"], "motive": MOTIVES[self.truth["motive"]],
            "hideout": self.label(self.hideout(self.truth["hideout"])["address"])},
            "lead_kinds": {a: ("lie" if l["lie"] else l["fact"][0]) for a, l in self.leads.items()},
            "solvable": self.solvable, "key_facts": [list(f) for f in self.key_facts], "lies": len(self.lies)}


def _tmin(hhmm):
    """Minutes since noon, so the night does not wrap at midnight."""
    h, m = map(int, hhmm.split(":"))
    return (h + 24 if h < 12 else h) * 60 + m - 720


def _clock(hhmm):
    h, m = map(int, hhmm.split(":"))
    if h == 0 and m == 0:
        return "midnight"
    hh = h % 12 or 12
    return f"{hh}:{m:02d} {'pm' if 12 <= h < 24 else 'am'}" if m else f"{hh} {'pm' if 12 <= h < 24 else 'am'}"


def _river_y(x):
    for (x0, y0), (x1, y1) in zip(THAMES, THAMES[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return THAMES[-1][1]
