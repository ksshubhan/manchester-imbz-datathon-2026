# Later

Ideas parked so they don't distract from the MVP. Don't start any of these unless every must-have in `SCOPE.md` is done.

- Predicting mules at account opening (before any money arrives)
- Cross-bank privacy / federated learning
- Real mobile app or bank integration
- Training on HI-Medium / HI-Large datasets
- Fine-tuning the LLM
- Use `HI-Small_Patterns.txt` (already in ~/shared) to name the laundering pattern in analyst explanations, e.g. "matches a fan-out pattern"


## Stronger actions on the same scores (parked 17 Oct, 15:21)
- **Friction before the outgoing transfer**: a "Has someone asked you to move this money?" check or a short delay. Needs its own cut-off and UI.
- **Hold the outgoing transfer until reviewed**: shown in the StudentShield story, but not wired to the model. Only sensible at high precision; at today's 3-29% precision it would hold many innocent students.
- **Freeze / report (SAR) / recall funds**: the bank's existing hard actions. Out of scope; our point is the soft, early step.

## Per-payment decisions on the phone (parked 17 Oct, 16:22)
- After the student pauses, let them mark each new incoming payment "I know this person" / "I don't recognise this". Not needed for the story: pausing already holds everything going out, and the student can't refuse or return incoming money themselves (the bank does that through a recall after review). Value would be extra evidence for the analyst, e.g. unknown senders raised as a reason in the case.
