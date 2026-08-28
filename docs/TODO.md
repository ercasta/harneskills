# TODO

- Allow multiple components of the same type on an entity (a list)
- Represent components as plain dicts to simplify serialization - or as dataclasses. The goal is reducing boilerplate
- Maybe we don't need Deltas technically - the "pending actions" are at an above level, a metalevel: a system can directly write to the graph a "proposed" action. But we still need to track it touched something, to intercept quiescence. Actually we don't really need quiescence, but we do need to do a reasonable number of "passes" before yielding otherwise processing takes forever because for each update loop we "pass", but computation can be made of a very long cascade of passes.
- We need helper functions to be able to write rules as one liners in python (using lambdas?)


