"""
coffee_kb — the coffee planning domain, packaged for the TUI.

Same problem instance as `examples/coffee.py`, exposed through the KB-module contract the
TUI's HarnessRunner expects:

  build()            -> a Graph seeded with operators + initial state (NO goal; the TUI
                        seeds the goal from /goal, falling back to DEFAULT_GOAL).
  DEFAULT_GOAL       -> the condition used when /run is given no explicit goal.
  FAILURES           -> {op_name: withhold_count}; withholding make_coffee's effect once
                        drives a real divergence -> control teardown -> replan, so the TUI
                        visibly re-plans and re-executes from the observed state.

Launch:  python -m harneskills_tui
         /kb examples/coffee_kb.py
         /goal have_coffee
         /run
"""
from __future__ import annotations

import harneskills as h

DEFAULT_GOAL = "have_coffee"

# Withhold make_coffee's effect exactly once, so the first attempt diverges and the planner
# tears down control and re-plans from the new state (then succeeds). Delete this to see a
# clean straight-line run.
FAILURES = {"make_coffee": 1}


def build() -> h.Graph:
    """Author the problem as graph data (operators = monotone facts; state = seed)."""
    g = h.Graph()
    # domain causal knowledge
    h.seed_operator(g, "make_coffee", pre=["water", "beans"], add=["have_coffee"])
    h.seed_operator(g, "get_beans", add=["beans"])
    # a DEAD option: also makes coffee, but needs money nothing can produce -> never viable
    h.seed_operator(g, "buy_latte", pre=["money"], add=["have_coffee"])
    # TWO viable ways to get water -> commitment ranks them by the fact-layer cost criterion
    h.seed_operator(g, "fetch_water", add=["water"], cost=1)
    h.seed_operator(g, "deliver_water", add=["water"], cost=5)
    h.seed_state(g, [])                       # empty larder: no water, no beans, no money
    return g
