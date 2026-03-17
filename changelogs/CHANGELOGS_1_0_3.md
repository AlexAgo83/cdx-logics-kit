# Changelog (`1.0.2 -> 1.0.3`)

## Highlights

- Added the internal `logics-ui-steering` skill and agent with a reusable UI/UX reference pack for palettes, primitives, and banned patterns.
- Split the flow-manager decision-framing logic into a focused support module so the main workflow helper keeps clearer ownership boundaries.
- Expanded the kit README with a clearer AI-project value proposition in addition to the `1.0.3` versioning updates.
- Preserved generated workflow behavior while making the decision heuristics easier to test, review, and evolve.

## UI/UX steering

- Added the `logics-ui-steering` skill so UI and frontend work can be guided by a dedicated corpus instead of ad hoc style guidance.
- Added the companion `openai.yaml` agent manifest for the UI steering workflow.
- Added reusable UI/UX references for palettes, primitives, and banned patterns to make the guidance more concrete and repeatable.

## Flow-manager modularization

- Extracted decision-framing and companion-doc rendering helpers from `logics-flow-manager/scripts/logics_flow_support.py` into `logics-flow-manager/scripts/logics_flow_decision_support.py`.
- Kept `logics_flow_support.py` focused on workflow support and document operations while importing the extracted decision helpers explicitly.
- Maintained the generated `Decision framing` and companion follow-up behavior without changing the CLI contract.

## Documentation

- Added a clearer `Why This Matters For AI Projects` framing in the kit README.
- Updated the kit `VERSION`, README version badge, versioned examples, and changelog index for `1.0.3`.
