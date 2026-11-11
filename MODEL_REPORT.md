# ContextIQ — model report

Every model below was built, trained, evaluated and modified over six rounds. Each was chosen by cross-validation on training data only, then scored once on a held-out test set built to be the hard case, and compared with a simple baseline. **All data is synthetic** (seeded, reproducible), so treat these as evidence the methods work, not as production accuracy.

Experiments run: **53** · training time: 453.0 s on CPU.

## Summary

| Model | Chosen | Test result | Baseline |
| --- | --- | --- | --- |
| Question router | char LR C=30 ngrams=(1, 6) | macro-F1 0.833 on unseen phrasings | 0.1 (random) |
| Purpose | LR C=16 class_weight=None | macro-F1 0.93 | 0.443 |
| Category | LR C=4 class_weight=None | macro-F1 0.896 | 0.004 |
| Fraud | GBM depth=2 lr=0.05 + isolation forest + rules | 91%–99% caught (known attack types) at 2.4% false alarms | — |
| Subscriptions | random forest min_leaf=1 | F1 0.997 | F1 0.785 (rule) |
| Spending forecast | profile=weekday shrink=0.6 | 18.1% error | 21.3% (repeat last month) |
| Decision model | learned weights | 100.0% agreement with written policy | 99.4% (hand-set weights) |
| Adaptive layer | Thompson sampling | 59% tap rate | 26% (fixed order) |

## How the models improved, round by round

| Round | What changed | Effect |
| --- | --- | --- |
| Round 1 | First models; router 0.56 macro-F1 on unseen phrasings; purpose/category/subscription ≈1.0. | Scores near 1.0 meant the test was too easy, not that the models were good. |
| Round 2 | Harder tests: unseen users + unseen merchant names, held-out phrasings, label noise, hard negatives (weekly shopping), 10× more router phrasings. | Router 0.70; purpose 0.94; category 0.89 — honest numbers. |
| Round 3 | Found a leak: the 'payee change' training attacks contained urgency wording, so the 'unseen' urgency attack wasn't really unseen. Removed it. | Urgency attacks: learned model drops from 100% to 7% — the truth. Caught instead by a rule (71%). |
| Round 4 | Hyperparameter search for every model (53 configurations); combined fraud layers by OR with per-layer thresholds instead of max-of-scores. | Combined fraud no longer worse than its best layer. |
| Round 5 | Moved 'invoice above purchase order' out of the fraud score into the invoice check (where every mismatch is held anyway), freeing the false-alarm budget. | Payee-change detection 66% → 91%. |
| Round 6 | Decision model stuck at 92%. Error analysis found a real bug: non-defective items were treated as eligible under the *replacement* window. Fixed in the app and the evaluator. | Decision model 92% → 100% agreement with the written refund policy on unseen scenarios. |
| Round 7 | First test on realistic unseen data (100 hand-written messages, new seed, shifted conditions). Found that keyword rules made routing worse (77%) than the trained router alone (83%). | Switched to router-first, rules only when the router is unsure (chosen on that development set: 84%). That set was then retired; final scores use a fresh set. |
| Round 8 | More realistic data: retail price points (.99), weekend dining, payday spending, night-time business payments, variable utility bills, big one-off purchases, casual/Indian-English phrasings, stealthier attackers. | All models retrained; final unseen test uses seed 2027 and 100 brand-new questions. |
| Round 9 | LoRA policy model: first attempt memorised training wording (28–41% on unseen store styles). Added a third writing style for validation, augmentation and 2× pretraining. | LoRA 54–56% (beats full fine-tune 48% with 25× fewer trainable weights); TF-IDF still best alone (79%). Ensemble 80% — deployed, gain within noise. |

## Question router

**What it does:** Turns a typed or spoken question into one of 10 topics so the right experts run.

**Data:** Templated questions written by the team (~1,200), 4 phrasings per topic held out entirely.

**Why this design:** Short, messy text (typos, slang) → character n-grams handle spelling variation; word n-grams catch meaning. A soft-voting ensemble of both was best on phrasings never seen in training.

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| char LR C=30 ngrams=(1, 6) | features=char_wb tf-idf, ngram_range=[1, 6], C=30 | 0.735 (f1_macro) | yes |
| char SVM C=0.3 | features=char_wb tf-idf, C=0.3, calibration=sigmoid, 3-fold | 0.734 (f1_macro) |  |
| char SVM C=1.0 | features=char_wb tf-idf, C=1.0, calibration=sigmoid, 3-fold | 0.733 (f1_macro) |  |
| char LR C=10 ngrams=(1, 6) | features=char_wb tf-idf, ngram_range=[1, 6], C=10 | 0.731 (f1_macro) |  |
| char LR C=30 ngrams=(2, 4) | features=char_wb tf-idf, ngram_range=[2, 4], C=30 | 0.729 (f1_macro) |  |
| ensemble char LR + word LR (soft vote) | members=char LR C=10 (2,5) + word LR C=10, voting=soft | 0.727 (f1_macro) |  |
| char LR C=10 ngrams=(2, 4) | features=char_wb tf-idf, ngram_range=[2, 4], C=10 | 0.725 (f1_macro) |  |
| char LR C=10 ngrams=(2, 5) | features=char_wb tf-idf, ngram_range=[2, 5], C=10 | 0.725 (f1_macro) |  |
| char LR C=30 ngrams=(2, 5) | features=char_wb tf-idf, ngram_range=[2, 5], C=30 | 0.725 (f1_macro) |  |
| char LR C=3 ngrams=(2, 5) | features=char_wb tf-idf, ngram_range=[2, 5], C=3 | 0.718 (f1_macro) |  |
| char LR C=3 ngrams=(1, 6) | features=char_wb tf-idf, ngram_range=[1, 6], C=3 | 0.716 (f1_macro) |  |
| char LR C=3 ngrams=(2, 4) | features=char_wb tf-idf, ngram_range=[2, 4], C=3 | 0.707 (f1_macro) |  |
| word LR C=30 | features=word 1-2gram tf-idf, C=30 | 0.633 (f1_macro) |  |
| word LR C=10 | features=word 1-2gram tf-idf, C=10 | 0.632 (f1_macro) |  |
| word LR C=3 | features=word 1-2gram tf-idf, C=3 | 0.619 (f1_macro) |  |
| word NB alpha=1.0 | alpha=1.0 | 0.613 (f1_macro) |  |
| word NB alpha=0.3 | alpha=0.3 | 0.602 (f1_macro) |  |
| word NB alpha=0.1 | alpha=0.1 | 0.6 (f1_macro) |  |

Test on unseen phrasings: accuracy 0.828, macro-F1 0.833. In the app, keyword rules answer first; the router handles the rest; below 0.25 confidence the reasoning model (Groq/Claude) is asked, or the user gets a short "did you mean…" question.

## Personal vs business

**What it does:** Decides whether a payment is personal or business.

**Data:** ~15,000 synthetic transactions from 120 simulated users, 3% deliberately wrong labels.

**Why this design:** Logistic regression on text + time/amount features: fast, well-calibrated probabilities (needed to decide when to ask the user), and easy to explain.

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| LR C=16 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=16, class_weight=None | 0.935 (f1_macro) | yes |
| LR C=1 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=1, class_weight=None | 0.934 (f1_macro) |  |
| LR C=4 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=4, class_weight=None | 0.934 (f1_macro) |  |
| LR C=0.25 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=0.25, class_weight=None | 0.928 (f1_macro) |  |
| LR C=4 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=4, class_weight=balanced | 0.917 (f1_macro) |  |
| LR C=16 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=16, class_weight=balanced | 0.917 (f1_macro) |  |
| LR C=1 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=1, class_weight=balanced | 0.916 (f1_macro) |  |
| LR C=0.25 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=0.25, class_weight=balanced | 0.906 (f1_macro) |  |

Confusion matrix (rows = truth):

| | predicted personal | predicted business |
| --- | --- | --- |
| personal | 921 | 8 |
| business | 42 | 197 |

## Spending category

**What it does:** Puts each payment in a spending category for budgets.

**Data:** Same transactions; test merchants have names the model never saw.

**Why this design:** Same design as purpose; class_weight='balanced' helps rarer categories.

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| LR C=4 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=4, class_weight=None | 1.0 (f1_macro) | yes |
| LR C=4 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=4, class_weight=balanced | 1.0 (f1_macro) |  |
| LR C=16 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=16, class_weight=None | 1.0 (f1_macro) |  |
| LR C=16 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=16, class_weight=balanced | 1.0 (f1_macro) |  |
| LR C=1 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=1, class_weight=None | 0.999 (f1_macro) |  |
| LR C=1 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=1, class_weight=balanced | 0.999 (f1_macro) |  |
| LR C=0.25 class_weight=balanced | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=0.25, class_weight=balanced | 0.995 (f1_macro) |  |
| LR C=0.25 class_weight=None | features=char tf-idf of payee|description|channel + hour, weekday, log amount, owner flag, C=0.25, class_weight=None | 0.994 (f1_macro) |  |

## Fraud detection

**What it does:** Scores how risky a payment request is.

**Data:** 16,000 normal sessions + 5 attack types from a separate red-team generator; 2 attack types never shown to the model.

**Why this design:** Gradient boosting handles mixed signals (device, amount, payee changes) and their interactions well on tabular data; shallow trees (depth 2) generalised best. An isolation forest adds a check for 'unlike anything normal', and two plain rules cover patterns that are rare but obvious.

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| GBM depth=2 lr=0.05 | max_depth=2, learning_rate=0.05, n_estimators=200, subsample=0.8 | 0.966 (average_precision) | yes |
| random forest min_leaf=5 | n_estimators=300, min_samples_leaf=5 | 0.964 (average_precision) |  |
| random forest min_leaf=1 | n_estimators=300, min_samples_leaf=1 | 0.961 (average_precision) |  |
| GBM depth=3 lr=0.05 | max_depth=3, learning_rate=0.05, n_estimators=200, subsample=0.8 | 0.96 (average_precision) |  |
| logistic regression | C=1.0 | 0.957 (average_precision) |  |
| GBM depth=3 lr=0.1 | max_depth=3, learning_rate=0.1, n_estimators=200, subsample=0.8 | 0.945 (average_precision) |  |
| GBM depth=2 lr=0.1 | max_depth=2, learning_rate=0.1, n_estimators=200, subsample=0.8 | 0.936 (average_precision) |  |

**Share of attacks caught on the test set** (false alarms held near 2%):

| Attack type | Seen in training | Learned model | Anomaly detector | Rules | All combined |
| --- | --- | --- | --- | --- | --- |
| account takeover | yes | 98% | 92% | 0% | 97% |
| amount spike | yes | 100% | 19% | 0% | 99% |
| payee change | yes | 91% | 27% | 0% | 91% |
| invoice inflation | no | 4% | 32% | 0% | 5% |
| urgency wording | no | 7% | 38% | 71% | 71% |

Invoice inflation is caught by the invoice-vs-purchase-order check: 100%. The fraud models themselves don't catch it — say so in the pitch.

PR-AUC on all test data: learned model 0.883, anomaly detector 0.904.

## Subscription detector

**What it does:** Finds recurring payments (subscriptions, memberships).

**Data:** 5,000 payment histories incl. hard negatives such as weekly grocery shopping.

**Why this design:** Random forest on 5 timing/amount features; beats a hand-written rule mostly on recall (it still finds subscriptions with a missed month or a price change).

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| random forest min_leaf=1 | n_estimators=300, min_samples_leaf=1 | 0.994 (f1) | yes |
| random forest min_leaf=3 | n_estimators=300, min_samples_leaf=3 | 0.994 (f1) |  |
| random forest min_leaf=10 | n_estimators=300, min_samples_leaf=10 | 0.993 (f1) |  |
| GBM depth=2 | max_depth=2, n_estimators=100 | 0.993 (f1) |  |
| GBM depth=3 | max_depth=3, n_estimators=100 | 0.992 (f1) |  |
| logistic regression | C=1.0 | 0.953 (f1) |  |

## Spending forecast

**What it does:** Predicts the next 30 days of everyday spending as a range.

**Data:** 180 days of daily spending for 80 simulated users; tuned on days 120–149, tested on 150–179.

**Why this design:** Per-user spending profile, shrunk toward the population (helps users with little history), plus bootstrapped day-to-day variation for the range.

**Every configuration tried** (cross-validated):

| Candidate | Hyperparameters | CV score | Chosen |
| --- | --- | --- | --- |
| profile=weekday shrink=0.6 | profile=weekday, shrink_to_population=0.6, n_sims=400 | 0.181 (validation MAPE (lower is better)) | yes |
| profile=flat shrink=0.6 | profile=flat, shrink_to_population=0.6, n_sims=400 | 0.181 (validation MAPE (lower is better)) |  |
| profile=weekday shrink=0.0 | profile=weekday, shrink_to_population=0.0, n_sims=400 | 0.182 (validation MAPE (lower is better)) |  |
| profile=weekday shrink=0.3 | profile=weekday, shrink_to_population=0.3, n_sims=400 | 0.182 (validation MAPE (lower is better)) |  |
| profile=flat shrink=0.0 | profile=flat, shrink_to_population=0.0, n_sims=400 | 0.182 (validation MAPE (lower is better)) |  |
| profile=flat shrink=0.3 | profile=flat, shrink_to_population=0.3, n_sims=400 | 0.182 (validation MAPE (lower is better)) |  |

Test: 18.1% error on the 30-day total; the P10–P90 range contained the real amount for 72% of users (ideal: 80%).

## Decision model

**What it does:** ranks the options experts propose (for example refund, replacement, warranty repair, PayPal protection) and recommends one. Options the store's terms don't allow are never ranked.

**Method:** weighted scoring over permitted options; weights learned by random local search (2,500 steps, Gaussian step 0.25 → 0.10 → 0.04, penalties constrained negative).

**Ground truth:** written refund policy (replacement for defects, refund on request or for non-defects, warranty next, otherwise PayPal protection).

| Check | Result |
| --- | --- |
| Agreement with written policy, hand-set weights | 99.4% |
| Agreement with written policy, learned weights | 100.0% |
| Same answer when options are shuffled | 100% |
| Same answer when weights are jittered ±20% | 100.0% |

Learned weights: benefit 0.471, risk -0.459, urgency 0.436, reversibility -0.145, evidence 0.121, user_preference 0.295, cost -0.261.

Order-invariance matters: LLM-as-judge setups are known to change answers when options are reordered. This model can't, by construction.

## Adaptive layer (reinforcement learning)

**What it does:** learns which shortcuts and reminder times each user actually uses. It only reorders and times things; it can never change permissions, limits or payments.

**Setup:** 150 simulated users, 9 shortcuts, 300 visits each, preferences change halfway.

| Strategy | Tap rate |
| --- | --- |
| Thompson sampling | 58.9% |
| Thompson + forgetting (cap 50) | 58.5% |
| Thompson + forgetting (cap 200) | 58.5% |
| epsilon-greedy (eps=0.1) | 52.5% |
| UCB1 | 50.7% |
| random | 27.6% |
| fixed order | 25.8% |
| best possible (knows the future) | 71.7% |

Chosen: **Thompson sampling**. The app caps each option's evidence (forgetting) so it keeps adapting when routines change, and clips each feedback event so a burst of fake taps can't take over.

## LoRA policy model (PyTorch + peft)

**What it does:** labels each sentence of a store policy (return window, replacement, warranty, exclusion, condition, return shipping, refund method, other) so plain code can read the numbers from the right sentences.

**Base model:** a 644,608-parameter byte-level Transformer (3 layers, 4 heads, width 128) pretrained from scratch with masked-byte modelling on 12,000 unlabelled shopping/finance texts (4 epochs, lr 0.001, loss 3.979 → 0.883). No pretrained model could be downloaded in the build environment.

**Data:** 4,800 training sentences (with augmentation), validation on a *different* writing style, test on 480 sentences in store styles never seen.

| Approach | Trainable parameters | Dev-style accuracy | Unseen-style accuracy | Unseen macro-F1 |
| --- | --- | --- | --- | --- |
| LoRA r=4 | 7,176 | 51.6% | 47.5% | 0.463 |
| LoRA r=8 | 13,320 | 50.0% | 56.0% | 0.536 |
| LoRA r=16 | 25,608 | 56.9% | 54.4% | 0.547 |
| full fine-tune | 645,640 | 50.6% | 47.9% | 0.482 |
| head only (frozen encoder) | 1,032 | 35.3% | 53.3% | 0.506 |
| TF-IDF + logistic regression (no neural net) | — | 92.8% | 79.2% | 0.78 |

Deployed: TF-IDF + LoRA (LoRA r=16) ensemble, weight chosen on the dev style. LoRA settings: rank r, alpha = 2r, dropout 0.05, applied to the attention query and value projections, classifier head trained, AdamW lr 3e-3, up to 6 epochs with the best epoch picked on the dev style.

**Honest reading:** LoRA did what it is designed to do — it matched or beat full fine-tuning while training 25–90× fewer weights — but a small model pretrained from scratch doesn't know enough language to beat simple n-gram features on new wording. With a real pretrained model (on a machine that can download one) the same `peft` code applies unchanged.

## Final test on unseen data

Fresh random seed (2027), shifted conditions, and 100 brand-new hand-written questions. Nothing here was used for training, tuning or any design decision.

| Model | Shift | Result |
| --- | --- | --- |
| Question routing (as the app runs it) | 100 new casual / Indian-English / typo messages | accuracy 88%, macro-F1 0.883 |
| Personal vs business | new users, new merchant naming style, 30% of business payments at night | macro-F1 0.933 (night-time business payments recognised: 86%) |
| Spending category | same | macro-F1 0.973 |
| Fraud | realistic 1% fraud rate, stealthier attackers | catches 86%; 21% of alerts are real fraud; 3.2% of normal payments get an extra check (40 alerts per 1,000 payments) |
| Subscriptions | 35% variable utility bills (5% in training) | precision 0.994, recall 0.998, F1 0.996 |
| 30-day forecast | new users with big one-off purchases | error 20%; range right for 72% of users |
| Decision model | new scenario mix | 100.0% agreement with the written policy |
| Adaptive layer | new users | 59% tap rate vs 28% fixed order (perfect knowledge: 72%) |

Fraud caught by attack type (stealthier versions): account takeover 85%, amount spike 90%, payee change 95%, invoice inflation 100%, urgency wording 60%.

Routing per topic on the new questions: refund 90%, payment status 80%, policy 80%, budget 80%, invoice 100%, fraud 80%, subscription 100%, investment 80%, price 90%, cases 100%.

Examples it still gets wrong:

- "camera lens is scratched out of the box" → price (should be refund)
- "my transfer is under review?" → invoice (should be payment_status)
- "was the capture successful for the headphones" → refund (should be payment_status)
- "do they give free return pickup" → refund (should be policy)
- "can i exchange instead of refund" → refund (should be policy)

## Limits

- All training data is synthetic; real data will be messier and scores will drop.
- Next: external fraud check on PaySim / IEEE-CIS public datasets.
- Regenerate this report any time with `python -m app.ml.train`.
