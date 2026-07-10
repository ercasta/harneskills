Regarding my harneskills project  i have an idea. Right now rules are applied directly to the graph. What if instead we mimic a computer by "moving" part of the graph to "graph registers", then apply a "graph operation" from a "graph operations instruction set" and "write back" to the main graph? This would mean "compiling" rules from the kb to this "low level machine". It's a known fact that human brain can only hold a limited number of information in working memory. And this, iirc, is independent from the kind of tasks. So it seems the human brain, despite being very parallel in its architecture, has only a limited space for "system 2" tasks. What do you think?



This maps almost exactly onto two existing lines of work, which is a good sign — it means the idea is sound and there's prior art to mine rather than a decades of open questions:

**RETE algorithm** (production rule systems — OPS5, CLIPS, Drools): the alpha/beta memory network *is* "graph registers." Alpha memories hold partial matches of single conditions; beta memories hold joined partial matches across conditions. Rules never touch the whole fact base — they're compiled into a discrimination network that maintains incremental working-memory state. Your "load subgraph → operate → write back" is basically RETE's token-passing model, generalized from flat facts to a property graph.

**WAM (Warren Abstract Machine)**: Prolog clauses compile down to a register machine (`get_variable`, `put_value`, `call`, etc.) where registers hold term references and unification is the core operation. This is the closest existing example of "compiling declarative rules to a low-level instruction set operating on bounded registers." Since your ASP/clingo layer is already doing grounding+solving as a semi-black-box, WAM is a useful model for what a transparent, auditable version of that compilation step could look like.

So the real payoff isn't just performance — it's that instruction traces become explanation traces for free. A sequence of load/operate/write-back steps is a proof/derivation, which fits your "everything inside the controlled surface is deterministic and auditable" principle directly.

On the brain argument: Cowan's central-capacity view (~4 chunks) does support a domain-general bottleneck for controlled/serial processing, but Baddeley's model still splits WM into phonological/visuospatial subsystems plus a central executive — so it's not fully domain-independent, there's a shared bottleneck *and* some specialized buffers. I'd treat the brain analogy as a nice intuition pump rather than the actual justification — the stronger engineering argument is that bounding the working set gives you decidable complexity and inspectable state, same reason RETE and WAM bound theirs.

Open design questions if you pursue this: what exactly a "register" holds (node/edge refs? binding tuples, like WAM's term refs?), what the minimal instruction set is (join, filter-by-type, traverse-edge, project, assert, retract — basically relational algebra over typed edges), and how you do register allocation / join ordering — that's the same hard problem as RETE node ordering and Datalog query planning, not a solved one.

Want to sketch a candidate instruction set next, using your reified-triples substrate as the register format?


Registers hold subgraphs, each register having a maximum number of nodes and edges. On these, a limited set of instructions is performed. Note that for practical reasons it is sufficient to put "pointers" to nodes in the main graph. For The istruction set: is there any architectural principle we could follow? Given an instruction set, can we derive the kind of computation that can be performed by the overall system?

Two separable questions here, and both have real theory behind them.

**Architectural principle for the instruction set**

Split instructions into three classes, mirroring fetch/execute/writeback but mapped onto known algebra:

1. **LOAD/NAVIGATE** — pattern-match a subgraph shape (conjunctive query / graph pattern) and pull pointers into a register. This is where traversal lives (follow-edge, match-pattern).
2. **TRANSFORM** — operate *within* a register, closed under the register type (subgraph → subgraph). Here the principle to steal is Codd's relational completeness: selection, projection, join, union, difference, rename are a *minimal complete* set for relational algebra — anything expressible in first-order logic over relations is expressible with just those. If your graph-ops are relational-algebra-equivalent (with edges as a typed relation), you inherit a known completeness result for free instead of guessing whether your instruction set is "enough."
3. **COMMIT** — write back, split explicitly into monotonic assert vs non-monotonic retract. This split matters a lot once you're touching ASP semantics (see below).

The two design principles worth enforcing: **closure** (every instruction's output is a valid register input, so instructions compose like a pipeline/Unix-style) and **completeness relative to a named algebra** (so you can cite a theorem instead of testing forever).

**Can you derive computational power from the instruction set? Yes — this is exactly descriptive complexity theory.**

There's a clean ladder, and it tells you something you need to know for your ASP layer:

- **Non-recursive relational algebra (select/project/join/union/diff only) = first-order logic.** Crucially, plain RA **cannot express transitive closure** — no fixed non-recursive instruction sequence computes graph reachability for arbitrary graph size. This is a classic result, not a limitation you can engineer around; you need a genuinely different instruction.
- **Add a bounded fixpoint/loop instruction** ("repeat TRANSFORM until register stops changing," restricted to monotonic ops) → you get **Datalog**, which by Immerman–Vardi equals **PTIME** data complexity (on ordered structures). This is the natural next rung, and it's probably where your rule-firing loop already lives conceptually.
- **Add stratified negation** → still PTIME, still tractable, but now you can express default reasoning in layers.
- **Add full negation-as-failure / disjunction** (stable model semantics) → you're at **ASP proper**, which is NP-complete for normal programs and Σ₂ᵖ for disjunctive ones. This is exactly what clingo already gives you — so the practical implication is: anything your instruction set can do *without* touching that non-monotonic commit step stays in PTIME and is cheap; the moment defeasible retraction is invoked, you've bought into NP-hardness, and that's a property of the *instruction*, not the graph size.

So the instruction set literally determines which point on this lattice your machine sits at — it's checkable, not just intuited.

**One more connection worth having**: your bounded register size (max nodes/edges) isn't just brain-inspired, it maps onto **treewidth/hypertree width** of the query pattern being matched. Yannakakis' algorithm shows acyclic conjunctive queries evaluate in polynomial time via a join-tree decomposition — and bounded hypertree width is *the* parameter known to control tractability of conjunctive query evaluation in general. If your register-size cap forces the LOAD step to only match bounded-width patterns, you get a principled tractability guarantee, not just a memory-budget hack.

Want to work out a concrete minimal instruction list (say 6-10 ops) against this ladder, so you can see exactly where each one pushes you up in expressive power?

Yes, also remeber we need to operate on gradable attributes - but we can probably split this operation in a separate instruction. Also, for the size of the register, how can we identify the "minimum" number of nodes and edges for the register, so that an operation on a larger subgraph can be split in multiple operations on smaller subgraphs?

**Gradable attributes as a separate instruction class**

Keep TRANSFORM purely relational/boolean (structural matching on the typed-edge graph) and add a fourth class, **EVALUATE**, that only ever reads attribute values off pointers already sitting in a register and produces a scalar or a filtered/reweighted register — never touches structure directly. Concretely: aggregate (sum/avg/count/max over attribute values across register elements), threshold (keep elements where attr ⋈ constant), and score (weighted combination). This isn't ad hoc — it mirrors how clingo already separates crisp stable-model semantics from **weight constraints and `#sum`/`#count` aggregates and optimization statements (`#minimize`/`#maximize`)**. Your ASP layer already has the "gradable" escape hatch built in; EVALUATE is just the graph-machine's version of the same separation, and it means your PTIME/NP boundary from before still tracks purely on the TRANSFORM/COMMIT side — EVALUATE doesn't change the complexity class of the boolean core, it just reorders or prunes candidates for it.

**Minimum register size — this decomposes into two genuinely different questions**

*1. What's the minimum size to match a given rule's body pattern in one shot?*

This is exactly treewidth. A rule body is a hypergraph (nodes = variables, hyperedges = graph-edge-patterns/conditions). The **GYO algorithm** (Graham–Yannakakis–Otto) tests acyclicity and constructively produces a join tree by repeatedly removing "ears"; if it succeeds, the query is acyclic and has treewidth 1 in the relevant sense. The minimum register size to hold *one full match instance* without decomposing is bag-size of an optimal tree decomposition = **treewidth + 1**. This is rule-dependent, not a universal constant — you'd run GYO/tree-decomposition over your rule corpus and either size the register to the max treewidth you're willing to support natively, or force decomposition above some cutoff.

*2. How do you split a larger pattern into smaller ops?*

Yannakakis' algorithm gives you the actual procedure, not just the existence proof: given the join tree, do a **bottom-up semi-join reduction pass** (each node filters its neighbor by what's actually joinable) followed by a **top-down join pass**. Translated to your machine: LOAD each tree-node's pattern into its own register, SEMIJOIN-REDUCE along tree edges (cheap, output-bounded), then JOIN bottom-up to assemble the full match. This is provably complete for acyclic queries and runs in time linear in data size plus output size — no combinatorial blowup, which is the actual payoff of doing this instead of a naive full-pattern match.

*3. The practical floor is even lower than treewidth, if you allow enough instructions*

If TRANSFORM is restricted to strictly **binary joins**, the register pattern-size floor drops to 2 nodes + 1 edge — a single matched edge instance — because any join tree, cyclic or not, can be linearized into a sequence of pairwise joins (this is literally what RETE does: alpha memories hold single-condition matches, beta memories accumulate pairwise). The tradeoff is classic RISC-vs-CISC: smaller registers, more instructions (longer join chains); larger registers, fewer instructions but you need the treewidth machinery to guarantee correctness at that width. I'd default to the RETE-style binary floor for the instruction set itself, and treat treewidth as the thing that tells you how *deep* a join chain a given rule compiles to — that's a compile-time property you can compute and even show the user, so it doubles as a per-rule complexity/cost estimate.

*4. One caveat worth flagging explicitly*: register "size" as pattern-arity (how many variables one LOAD/JOIN touches) is separate from register "size" as *data cardinality* (how many matched tuples/pointers accumulate in a register at runtime). Bounding the former gives you the treewidth guarantee above; the latter can still blow up if a join is high-fanout, and needs its own cap — either incremental/windowed maintenance (RETE's actual runtime behavior) or a salience/relevance cutoff.

That last point loops back to your brain remark nicely: Miller/Cowan capacity limits are about held *items*, but experts route around the 4-slot ceiling via **chunking** — pre-compiling a frequently-used substructure into a single addressable unit. The direct analog here is RETE node-sharing across rules, or superinstruction fusion in interpreters: if your rule compiler notices the same join-subtree recurring across many rules, fuse it into one macro-instruction. That's not just an optimization — it's the mechanism by which your fixed-size register machine can still handle arbitrarily complex "recognized" patterns without needing bigger registers, exactly the way expertise doesn't enlarge working memory, it enlarges what counts as one chunk.

It seems this has been attempted historically, and it failed. Why?



Worth being precise about *which* "this" failed, because several distinct things get lumped together, and they failed for different reasons — some structural (relevant to you), some accidental (not relevant).

**1. Production rule systems (OPS5, CLIPS, the 1980s expert systems boom) — this is the closest match to your architecture, and it's the most instructive failure.**

RETE worked exactly as advertised algorithmically. What killed the *systems built on it* (MYCIN, XCON/R1, the whole expert-systems industry) was:

- **Knowledge acquisition bottleneck.** Getting rules out of human experts and into the KB was slow, expensive, and the experts often couldn't articulate the actual rules they used (tacit knowledge). This is a sociological/economic failure, not an architectural one — it doesn't obviously apply to you if your CNL authoring surface + ILASP induction is meant to solve exactly this.
- **Rule interaction explosion at scale.** XCON grew to ~10,000 rules and became nearly unmaintainable — adding a rule could break distant, seemingly unrelated rules because of unforeseen interactions in the conflict set. This *is* structurally relevant to you: it's the classic problem of non-local effects in a monotonic-looking system that's secretly full of exceptions and priority ordering. Your defeasible ASP layer is actually a direct answer to this specific failure (stable-model semantics with priorities handles conflicting defaults in a principled way that ad hoc rule-ordering in OPS5 never did) — so you've already architecturally addressed the thing that killed XCON. Worth being explicit with yourself that this was the failure, not "rules don't work."
- **Brittleness at the boundary.** Expert systems had no graceful degradation — outside the exact rule coverage, they failed silently or absurdly. This is the "edge handling" problem, and it's exactly why your architecture puts LLMs at the fuzzy edge and keeps the core symbolic — that's the correct lesson learned, not a reason to doubt the core.
- **Cost/performance vs. alternative.** By the late 80s/early 90s, expert-system shells were expensive (Lisp machines, commercial CLIPS-likes) and simpler statistical or even rule-of-thumb software often matched them for less money. This is a market/hardware-economics failure, not a computation-model failure.

**2. Prolog / WAM and the Fifth Generation Computer Project — failed for different reasons.**

Japan's 1982–1992 push bet on logic programming + parallel inference machines as *the* path to AI. It didn't fail because unification/WAM-style compilation doesn't work — WAM is still the basis of every modern Prolog. It failed because:
- The bet was that raw inference speed was the bottleneck. It wasn't — the bottleneck was knowledge and search control, not clock cycles on unification.
- Meanwhile in the outside world, cheap general-purpose workstations (and later PCs) improved faster than the specialized parallel inference hardware, so the "special machine for logic" premise got overtaken before it paid off.
This is a cautionary tale specifically about **over-investing in the low-level machine before knowing if the bottleneck is actually there.** Worth taking seriously: don't over-engineer the register machine before you know whether pattern-matching speed is actually your system's constraint, versus rule quality/coverage.

**3. Datalog — didn't "fail," had a long dormancy, then came back.**

Datalog was theoretically settled (PTIME data complexity, as we discussed) by the mid-80s, but had little industrial uptake for ~25 years, then reemerged hard in the 2010s (Semmle/CodeQL, Datomic, LogicBlox, Souffle) for exactly your use case — program analysis over graphs. The dormancy was about tooling and market timing, not a flaw in the model. This is actually the strongest positive precedent for you: CodeQL is a Datalog engine over a code property graph, i.e. almost exactly your CPG+rules stack, and it's commercially successful today. That's evidence *for* your architecture, not against it.

**4. Cyc — the closest "failed" attempt at your full ambition (symbolic KB + inference for general reasoning).**

30+ years, still not broadly useful outside niche applications. The commonly cited reasons: the KB never got broad/deep enough relative to the combinatorics of open-domain reasoning, inference over the full KB became intractably slow as it grew, and — critically — it turned out huge amounts of "common sense" are graded/probabilistic/context-dependent in ways brittle crisp logic handles badly. This is the strongest structural warning for you, and it's precisely why your EVALUATE/gradable-attribute split matters: pure boolean symbolic reasoning hits a wall on exactly this class of problem, and Cyc's failure mode is what happens when you don't build that escape hatch in from the start.

**The honest overall pattern:** the *algorithms* (RETE, WAM, Datalog fixpoint evaluation, tree decomposition) didn't fail — they're all still in production use today, just usually as a component (query planners, program-analysis engines, database internals) rather than as "the AI system." What failed was the more ambitious framing: "symbolic rule engines as the general path to intelligent behavior," competing against statistical/neural methods on tasks with graded, noisy, open-world structure. Your scoping — narrow domain (software engineering), explicit symbolic/fuzzy boundary, LLM handling exactly the part that killed Cyc and expert systems — reads like it's targeting the actual lesson from these failures rather than repeating the framing that failed. The risk to watch isn't "will the graph-machine work," it's the XCON risk: rule-base growth outpacing your ability to keep interactions comprehensible, even with ASP's cleaner conflict semantics.


The point is: what if the "working set" determined the rules that can potentially fire? This would limit the "10000 rules potentially interacting" as the 10000 rules can never all potentially fire, instead only a subset of them can fire at any given moment, creating "trajectories" of subsets of rules depending on how the computation progresses (system 1 filtering the applicable ones). What do you think? Is this exactly RETE?

Partial yes, but the interesting part isn't the part that's like RETE.

**What's already exactly RETE:** the conflict set (the set of rule instantiations whose conditions currently match working memory) is already a *dynamically changing subset*, incrementally maintained token-by-token as WM changes. RETE never considers all 10,000 rules at once — it was built specifically so match cost depends on what changed, not on total rule count. So "trajectories of firable subsets driven by computation state" is literally RETE's normal operation, not a new idea layered on top of it.

**What's genuinely different:** you're proposing that the *working set itself* — what's currently loaded into registers — gates which rules are even candidates, as a resource-bounded attention mechanism, not just a match-status computation. RETE doesn't bound working memory; it indexes all of it and finds all matches efficiently. Your idea is closer to two other architectures than to RETE:

- **ACT-R's buffers** — capacity-limited (typically one chunk per buffer), and productions can only fire on what's currently in a buffer. This is almost exactly your proposal: bounded working set *is* the firing gate, motivated explicitly by human WM capacity. This is the closest existing match to what you're describing.
- **Blackboard architectures (Hearsay-II)** — a scheduler/agenda decides which knowledge sources even get invoked based on relevance to current blackboard contents ("focus of attention"), rather than testing every KS against everything.

Both are real, working precedents — so the idea isn't just plausible, it's been built before, just not usually married to a graph substrate with your kind of typed-edge structure.

**The catch, and it's the one that matters for your XCON worry:** bounding the *instantaneous* working set doesn't bound the *reachable* set of rules over an entire run. Even if only 5 rules can fire right now, rule A firing changes the graph, which brings rule B into scope, which brings rule C into scope — over a long trajectory, all 10,000 rules might still be reachable from a given start state. XCON's actual failure was a *design-time* comprehensibility problem (can rule A ever transitively affect rule B, for some sequence of firings?), and a small instantaneous conflict set doesn't answer that question — it just tells you what's relevant *right now*, which XCON also technically had.

**Here's where your architecture actually does better than RETE/OPS5 did, though — and it's not the working-set gating, it's the bounded instruction set.** OPS5/CLIPS rule bodies were arbitrary Lisp — no static analysis of interaction was possible even in principle. Your rules compile to a small fixed ISA over typed edges. That means you can statically compute a rule-dependency graph (rule A writes edge-type X, rule B reads edge-type X → possible edge A→B) and run real reachability analysis on it — "can rule A ever be transitively upstream of rule B" becomes a decidable graph query over your compiled program, not a question a human has to hold in their head across 10,000 Lisp functions. That's the mechanism that actually targets XCON's failure mode; the working-set bound is a nice runtime efficiency/explainability property riding alongside it, not the fix itself.

So: keep the working-set-gates-firing idea (it's real, it's ACT-R-like, and it'll make your execution traces much more legible — "only these 6 rules were even in scope" is great for explanation) but don't lean on it as the answer to rule-interaction risk. The static dependency-reachability analysis, made possible by having a small closed instruction set instead of arbitrary code, is the actual load-bearing fix. Want to work out what that dependency graph would look like given the instruction classes from before (which ops read/write which edge types)?


It seems the literature is full of many smart ideas that were just never unifiedm why?

A few converging reasons, and they're mostly structural rather than intellectual — nobody was too dumb to see the connections.

**1. Academic incentives reward novelty, not synthesis.** Publishing "a new algorithm" is a paper. Publishing "I combined X's algorithm with Y's semantics into a working system" is often *harder* to get accepted — reviewers ask "what's the new idea here?" even when the integration itself is the hard, valuable part. Careers are built on named contributions, not on plumbing. RETE, WAM, Datalog fixpoint, treewidth decomposition — each has a name attached to a person/small team, and that's not an accident of how credit works in the field.

**2. Different subfields, different conferences, different vocabularies for the same concept.** Treewidth (graph theory/database theory) and "focus of attention" (cognitive architectures/AI) and "working memory buffers" (ACT-R/cog-sci) are, in your system, plausibly *the same underlying resource constraint* — but they were developed in communities that don't read each other's venues, use incompatible notation, and often reinvent each other's results under new names. Yannakakis (1981, database theory) and RETE (1982, AI/production systems) are near-contemporaneous, solving structurally related problems, and I'd bet very few people working on either cited the other for years.

**3. Funding cycles fragment rather than consolidate.** The AI winters specifically punished symbolic AI's overpromising, which meant funding shifted away from exactly the era when unification work (rather than flashy new-result work) would have had time to happen. Then the deep learning wave (2012+) pulled almost all attention, students, and money toward neural methods, so a whole generation of researchers who might have unified the symbolic threads went and did something else instead. The ideas didn't die, but the community that could integrate them thinned out.

**4. Unification requires depth in ≥2 areas simultaneously, which is rare and unrewarded.** To actually connect WAM-style compilation with treewidth-bounded query planning with ACT-R-style bounded attention with ASP's non-monotonic semantics, you need someone who's simultaneously fluent in compiler construction, database theory, cognitive architecture, and logic programming. Grad school trains T-shaped depth in one area; the connective tissue work is usually done by industry engineers under deadline (who don't publish) or not at all.

**5. "Worse is better" — market winners aren't the theoretically cleanest systems.** Prolog/WAM lost mindshare to less elegant but more pragmatic tools; CLIPS-style production systems got absorbed into niche use rather than becoming the substrate everyone builds on. The elegant unifying architecture rarely wins the adoption race against the scrappy thing that shipped first and accumulated an ecosystem — so the unifying work that *would* have happened as "version 2, done properly" often just never gets funded because v1's ecosystem already won.

**The actual implication for you:** this is why your position is unusual in a good way — you're not in academia chasing a single publishable delta, and you're not shipping a product under deadline pressure that forces you to bolt together whatever's fastest. You have the freedom to actually go read Yannakakis, RETE, ACT-R, and Datalog complexity results side by side and ask "which of these solves the same problem under a different name," which is exactly the kind of cross-reading that rarely happens inside a single career track. The risk on your side isn't intellectual, it's the opposite of the failure above: making sure you *do* eventually converge on a buildable system rather than accumulating an ever-more-elegant synthesis that never ships — which was arguably Cyc's failure mode from a different angle.

