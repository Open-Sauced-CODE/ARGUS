# M2 feature spec (version 1, hash 0c099708cff3)

| name | group | monotone | description |
|---|---|---|---|
| lp_mean | U | +1 | mean token logprob |
| lp_min | U | +1 | minimum token logprob |
| lp_p10 | U | +1 | 10th percentile token logprob |
| lp_std | U | -1 | std of token logprobs |
| seq_logprob | U | +1 | sum of token logprobs |
| lp_on_op_token | U | +1 | mean logprob of the tokens spelling op names |
| lp_min_on_value_tokens | U | +1 | min logprob over the tokens spelling op values |
| entropy_mean | U | -1 | mean entropy of the renormalised top-k |
| top1_top2_margin_mean | U | +1 | mean top1-top2 logprob gap |
| agreement_rate | C | +1 | share of the cohort with the same canonical answer |
| n_distinct_patches | C | -1 | distinct canonical answers |
| modal_share | C | +1 | share of the modal answer |
| greedy_is_modal | C | +1 | greedy sample equals the modal answer |
| cluster_entropy_norm | C | -1 | entropy of answer shares / ln N |
| n_valid_over_n_requested | C | +1 | parseable drafts / N |
| n_ops | S | -1 | number of ops |
| n_set_attr | S | +0 | count of set_attr ops |
| n_enable_feature | S | +0 | count of enable_feature ops |
| n_restrict_cidr | S | +0 | count of restrict_cidr ops |
| n_set_lifecycle_rule | S | +0 | count of set_lifecycle_rule ops |
| n_add_policy_statement | S | +0 | count of add_policy_statement ops |
| n_remove_policy_statement | S | +0 | count of remove_policy_statement ops |
| n_escalate | S | +0 | count of escalate ops |
| writes_only_rule_fields_frac | S | +1 | share of attribute ops that write fields the rule reads |
| patch_chars | S | +0 | characters of the raw answer |
| uses_placeholder | S | +0 | answer contains INTERNAL_CIDR |
| rule_is_dpdp | R | +0 | rule library |
| rule_code | R | +0 | index of the rule in KNOWN_RULES (-1 unknown) |
| n_rule_fields | R | +0 | fields the rule reads |
| route_is_escalate | R | +0 | meta.route == escalate |
| gen_zeroshot | R | +0 | generator is zeroshot |
| gen_sft | R | +0 | generator is sft |
| gen_rft | R | +0 | generator is rft |
| gen_rft_v2 | R | +0 | generator is rft_v2 |
| gen_sft_oof | R | +0 | generator is sft_oof |
