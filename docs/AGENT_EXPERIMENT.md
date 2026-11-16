# Preserve-vs-challenge experiment: frozen evidence, independent evaluation

## Hypothesis

Does adversarial framing surface real model defects more often than preservation
framing **when evidence, temperature, model version, tools and token budget are
held constant**? Compare to a third neutral review to test prompt effects.

1. Freeze one evidence packet (data SHA, strategy SHA, trade history as-of time,
   cost model, universe, feature definitions, walk-forward test IDs).
2. For **every** evaluated result, including profitable and unprofitable trades,
   invoke both `PRESERVE_PROMPT` and `CHALLENGE_PROMPT` on the identical packet.
3. Force structured response: claim, referenced evidence, falsifiable test,
   expected failure mode, proposed change. Allow `no_change` proposals.
4. Require independent tests against a previously untouched period. No LLM can
   change the active model, the deployed risk config, or the broker order layer.
5. Store prompt/version/agent output, hashes and review findings. Add controlled
   neutral baseline and, when enough data, randomized order/seed repetitions.
6. Promote a challenger only after reproducible economic improvement **net** of
   costs without worsening risk metrics past fixed gates; use manual approval.

Not scientific evidence: a better-sounding answer; a single winning/losing
trade; backtest improvements selected by trying many ideas on the same holdout.

## Why the literal user phrasing is only a treatment, not factual instruction

The 'preserve' treatment asks the reviewer to defend the present model even
when it may be flawed; the 'challenge' treatment asks it to find flaws even
when no flaw exists. Both tend to produce biased narratives. That bias is
precisely why proposals are quarantined and evaluated by objective tests.

## Suggested success metrics

- Confirmed defect discoveries per 100 review runs
- Out-of-sample incremental net P&L after realistic execution costs
- Maximum drawdown, variability across walk-forward periods
- False-positive proposed changes and time spent reviewing them
- Reproducibility of agent reasoning against identical evidence hashes
