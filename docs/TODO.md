# TODO

- Allow multiple components of the same type on an entity (a list)
- Represent components as plain dicts to simplify serialization - or as dataclasses. The goal is reducing boilerplate. Dataclasses provide IDE help. Each component type must have a unique id (see below, like GENERAL.REQUEST; it could also be the fully qualified class name of the Dataclass to that we also get ide help for the return type) 
- Maybe we don't need Deltas technically - the "pending actions" are at an above level, a metalevel: a system can directly write to the graph a "proposed" action. But we still need to track it touched something, to intercept quiescence. Actually we don't really need quiescence, but we do need to do a reasonable number of "passes" before yielding otherwise processing takes forever because for each update loop we "pass", but computation can be made of a very long cascade of passes.
- We need helper functions to be able to write rules as one liners in python (using lambdas?)

- The engine must allow rules (i.e. systems, systems are just logical collections of rules, but the engine just sees rules)

- General protocol for request - response between sets of rules:
    - A rule create a "request" component (GENERAL.REQUEST) on a singleton (but this is a detail) that is watched by "interest signalling" rules. The request component contains an entity where to find extra components (that entity has a GENERAL.REQUEST.DETAILS plus specific components that further characterize it) that further characterize the request
    - All "interested" rules constantly monitor the "request" component (GENERAL.REQUEST). If they find a request, they look at the components of the referenced entity. If the components are of interest for that rule, they attach a "working on it" component on the entity that has the "extra info". 
    - Meanwhile another set of rules, beloning to the "general request response protocol" monitors the request. At each tick they increment a counter (another component). They wait up to N ticks, then they start to monitor the completions
    - The specific rules, when they are done, change the status of their component from "working on it" to "done".
    - The general request - response protocol rules wait  for all request to complete, or up to a "tick timeout" budget, then they remove the request from the singleton
    - Note: the responders might also have a way to request a "tick budget extension"

This mechanism could be exploited by e.g. ../pystrider to handle analysis requests of python programs, where many many "analyzer" rules work on it and provide different "points of view". This mechanism can in fact cascade: a first generic python rule can catch the request to analyze a python program and create another, more specific request, that is managed by specific rules.

Moreover: i want the ugm engine in this repo to replace the ../ugm engine (but i thought we already migrated it to ../ugm)

