# ContextIQ model card

Synthetic, seeded, generated in app/ml/synth.py; attacks in app/ml/redteam.py (separate generator).
Every model was chosen by cross-validation on training data only, then scored once on a held-out test set designed to be the hard case, and compared with a simple baseline.

## Results at a glance

| Model | Test set | Score | Simple baseline |
| --- | --- | --- | --- |
| Question router | phrasings never seen | macro-F1 0.833 (accuracy 0.844 on the 85% it is confident about) | random guess 0.1 |
| Personal vs business | unseen users and merchants | macro-F1 0.93 | 0.443 (always the most common) |
| Spending category | unseen users and merchants | macro-F1 0.896 | 0.004 (always the most common) |
| Subscription detector | incl. missed payments, price changes, weekly habits | F1 0.997 | F1 0.785 (simple rule) |
| 30-day spending forecast | last 30 days of 80 users | error 18%, range right 72% of the time | error 21% (repeat last month) |

## Fraud — share of attacks caught, by attack type

False alarms on normal payments are held near 2% for every column.

| Attack type | Seen in training | Learned model | Anomaly detector | Rules | All combined |
| --- | --- | --- | --- | --- | --- |
| account takeover | yes | 98% | 92% | 0% | 97% |
| amount spike | yes | 100% | 19% | 0% | 99% |
| payee change | yes | 91% | 27% | 0% | 91% |
| invoice inflation | no | 4% | 32% | 0% | 5% |
| urgency wording | no | 7% | 38% | 71% | 71% |

False alarms on unseen normal payments: learned 2.4%, combined 2.4%.
Learned model chosen: GBM depth=2 lr=0.05 (cross-validated average precision 0.966).

Held-out families were written in a separate generator and never used in training. Invoice inflation is caught by the invoice-vs-purchase-order check (a separate, deterministic step that holds every mismatch), not by the fraud models — report it that way.

## Limits

- Synthetic data is cleaner than real data; treat these as evidence the pipeline works, not production accuracy.
- Next step: an external check on PaySim / IEEE-CIS public fraud data.
- Training time: 453.0 s on a laptop CPU.
