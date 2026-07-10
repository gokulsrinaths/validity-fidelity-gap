# Token Matching Audit (Using True Prompt Tokens)

This audit uses `usage.json.prompt_tokens` (backend-reported) as the token-length proxy.
This includes the system+user prompt wrapper, so it is a *prompt-level* token match check, not pure-document-only.

- control_root: `data\runs\full_pilot_control_20260520_235546`
- redundancy_root: `data\runs\full_pilot_20260520_192127`

## By repetition (mean prompt_tokens)
```
 repetition  redundancy_prompt_tokens_mean  control_prompt_tokens_mean   delta  delta_frac  within_5pct
          1                          320.1                       320.1     0.0    0.000000            1
          2                          498.2                       413.2   -85.0   -0.170614            0
          5                         1032.5                       676.3  -356.2   -0.344988            0
         10                         1923.0                      1105.6  -817.4   -0.425065            0
         16                         2991.6                      1637.2 -1354.4   -0.452734            0
         32                         5841.2                      3007.7 -2833.5   -0.485089            0
```

## Pass/fail (±5%)
- repetitions within ±5%: `1/6`

