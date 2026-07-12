"""Multi-stage AI payout-estimate pipeline.

The LLM never produces a dollar figure: model stages return judgments
(canonical extraction, severity tier, liability percentage, adversarial
critique, comparable results) and pure Python computes the ranges.
"""
