# Harvest vs Phase 5: lengths and common-key gate-pass

- zeroshot: greedy outputs over 400 tokens: 9/321; cut off (done_reason=length): 4
  common keys 181: harvest pass 20 (0.110) vs Phase 5 20 (0.110); harvest-only 0, Phase 5-only 0
- sft: greedy outputs over 400 tokens: 0/321; cut off (done_reason=length): 0
  common keys 181: harvest pass 180 (0.994) vs Phase 5 180 (0.994); harvest-only 0, Phase 5-only 0
- rft: greedy outputs over 400 tokens: 0/321; cut off (done_reason=length): 0
  common keys 181: harvest pass 178 (0.983) vs Phase 5 174 (0.961); harvest-only 5, Phase 5-only 1
- rft_v2: greedy outputs over 400 tokens: 4/321; cut off (done_reason=length): 2

Rates over different input sets are not comparable; only the common-key line counts.
