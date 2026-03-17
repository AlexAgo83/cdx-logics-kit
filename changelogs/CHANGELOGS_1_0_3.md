# Changelog (`1.0.2 -> 1.0.3`)

## Highlights

- Split the flow-manager decision-framing logic into a focused support module so the main workflow helper keeps clearer ownership boundaries.
- Preserved generated workflow behavior while making the decision heuristics easier to test, review, and evolve.
- Refreshed kit version metadata and release documentation for the `1.0.3` cut.

## Flow-manager modularization

- Extracted decision-framing and companion-doc rendering helpers from `logics-flow-manager/scripts/logics_flow_support.py` into `logics-flow-manager/scripts/logics_flow_decision_support.py`.
- Kept `logics_flow_support.py` focused on workflow support and document operations while importing the extracted decision helpers explicitly.
- Maintained the generated `Decision framing` and companion follow-up behavior without changing the CLI contract.

## Documentation

- Updated the kit `VERSION`, README version badge, versioned examples, and changelog index for `1.0.3`.
