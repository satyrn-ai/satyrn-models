# Telemetry summary: Qwen3.8-27B base vs py3.15 tune (agentic campaign)

40 cells from slots/NN.json (non-replaced). delivered = verdict==pass. Medians over cells with data; budget-refused cells may lack transcript data.

### By model

Numeric cells are median (count with data).

| group | n | delivered | codes | turns | out_tokens_total | out_tokens_median_turn | max_input_tokens | wall_min | calls_total | calls_read | calls_bash | calls_edit | calls_write | first_edit_turn | files_edited | tests_run | bash_inspect | bash_heredoc_write | repeated_calls | longest_bash_run | tool_errors | thinking_chars_median_turn | thinking_chars_total | empty_text_turn_share | phrase_total | tests_after_last_edit | tried_to_finish_early | final_announces_completion | final_stop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 20 | 16 | {'OK': 20} | 14.0 (20) | 10106.5 (20) | 244.8 (20) | 5170.0 (20) | 12.9 (20) | 22.5 (20) | 5.0 (20) | 14.0 (20) | 2.0 (20) | 0.0 (20) | 9.5 (20) | 2.0 (20) | 2.0 (20) | 4.0 (20) | 0.5 (20) | 0.0 (20) | 7.0 (20) | 0.0 (20) | 193.0 (20) | 27424.0 (20) | 0.5 (20) | 0.0 (20) | 13/20 | 0/20 | 9/20 | {'stop': 19, 'error': 1} |
| tune | 20 | 2 | {'BUDGET_EXCEEDED': 17, 'OK': 2, 'NO_PATCH': 1} | 72.0 (20) | 17775.0 (20) | 246.5 (20) | 2996.0 (20) | 27.0 (20) | 72.0 (20) | 5.5 (20) | 68.0 (20) | 1.0 (20) | 0.0 (20) | 3.0 (18) | 2.0 (20) | 2.0 (20) | 2.0 (20) | 0.0 (20) | 57.5 (20) | 66.0 (20) | 1.0 (20) | 272.0 (20) | 20973.0 (20) | 0.0 (20) | 0.0 (20) | 15/18 | 0/20 | 14/20 | {'toolUse': 17, 'stop': 2, 'length': 1} |

### By (task, model)

Numeric cells are median (count with data).

| group | n | delivered | codes | turns | out_tokens_total | out_tokens_median_turn | max_input_tokens | wall_min | calls_total | calls_read | calls_bash | calls_edit | calls_write | first_edit_turn | files_edited | tests_run | bash_inspect | bash_heredoc_write | repeated_calls | longest_bash_run | tool_errors | thinking_chars_median_turn | thinking_chars_total | empty_text_turn_share | phrase_total | tests_after_last_edit | tried_to_finish_early | final_announces_completion | final_stop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base/agentclinic-complaint-lifecycle | 4 | 0 | {'OK': 4} | 57.5 (4) | 33062.5 (4) | 230.8 (4) | 7569.0 (4) | 45.5 (4) | 65.5 (4) | 2.0 (4) | 40.5 (4) | 13.0 (4) | 12.0 (4) | 14.0 (4) | 11.0 (4) | 12.5 (4) | 5.0 (4) | 3.0 (4) | 2.0 (4) | 15.0 (4) | 3.0 (4) | 181.0 (4) | 48955.5 (4) | 0.5 (4) | 0.5 (4) | 3/4 | 0/4 | 3/4 | {'stop': 3, 'error': 1} |
| tune/agentclinic-complaint-lifecycle | 4 | 0 | {'BUDGET_EXCEEDED': 4} | 72.0 (4) | 29009.0 (4) | 335.0 (4) | 2794.5 (4) | 40.0 (4) | 72.0 (4) | 2.5 (4) | 61.0 (4) | 3.0 (4) | 3.0 (4) | 1 (3) | 1.5 (4) | 0.0 (4) | 1.0 (4) | 0.0 (4) | 56.0 (4) | 52.0 (4) | 2.5 (4) | 729.0 (4) | 56030.0 (4) | 0.0 (4) | 0.0 (4) | 0/3 | 0/4 | 2/4 | {'toolUse': 4} |
| base/agentclinic-repair-depth-2 | 4 | 4 | {'OK': 4} | 13.0 (4) | 8285.5 (4) | 307.5 (4) | 4202.5 (4) | 10.4 (4) | 19.0 (4) | 7.0 (4) | 10.0 (4) | 2.0 (4) | 0.0 (4) | 9.5 (4) | 2.0 (4) | 2.0 (4) | 2.0 (4) | 2.0 (4) | 0.0 (4) | 5.0 (4) | 0.5 (4) | 185.5 (4) | 19890.5 (4) | 0.5 (4) | 0.0 (4) | 2/4 | 0/4 | 0/4 | {'stop': 4} |
| tune/agentclinic-repair-depth-2 | 4 | 1 | {'BUDGET_EXCEEDED': 3, 'OK': 1} | 72.0 (4) | 19891.0 (4) | 272.0 (4) | 2946.5 (4) | 32.0 (4) | 77.0 (4) | 6.5 (4) | 68.0 (4) | 2.0 (4) | 0.0 (4) | 5.0 (4) | 2.0 (4) | 49.5 (4) | 2.0 (4) | 0.0 (4) | 62.0 (4) | 64.5 (4) | 1.0 (4) | 187.0 (4) | 13773.5 (4) | 0.0 (4) | 0.0 (4) | 4/4 | 0/4 | 4/4 | {'toolUse': 3, 'stop': 1} |
| base/agentclinic-repair-depth-3 | 4 | 4 | {'OK': 4} | 11.5 (4) | 10030.5 (4) | 345.8 (4) | 8063.0 (4) | 12.8 (4) | 20.0 (4) | 6.0 (4) | 10.5 (4) | 3.0 (4) | 0.0 (4) | 8.0 (4) | 3.0 (4) | 2.0 (4) | 5.0 (4) | 1.0 (4) | 0.0 (4) | 6.0 (4) | 0.0 (4) | 177.5 (4) | 27424.0 (4) | 0.4 (4) | 0.0 (4) | 1/4 | 0/4 | 0/4 | {'stop': 4} |
| tune/agentclinic-repair-depth-3 | 4 | 0 | {'BUDGET_EXCEEDED': 3, 'NO_PATCH': 1} | 48.5 (4) | 16325.5 (4) | 173.8 (4) | 3208.0 (4) | 23.5 (4) | 54.5 (4) | 6.0 (4) | 45.5 (4) | 2.5 (4) | 0.0 (4) | 5 (3) | 2.5 (4) | 2.0 (4) | 1.5 (4) | 0.0 (4) | 34.0 (4) | 43.0 (4) | 0.0 (4) | 265.2 (4) | 48011.0 (4) | 0.1 (4) | 0.0 (4) | 3/3 | 0/4 | 2/4 | {'toolUse': 3, 'length': 1} |
| base/agentclinic-repair-misleading-locus | 4 | 4 | {'OK': 4} | 8.0 (4) | 1768.0 (4) | 217.8 (4) | 3556.5 (4) | 2.1 (4) | 10.0 (4) | 5.0 (4) | 4.5 (4) | 1.0 (4) | 0.0 (4) | 4.5 (4) | 1.0 (4) | 2.0 (4) | 2.0 (4) | 0.0 (4) | 0.5 (4) | 2.0 (4) | 0.0 (4) | 177.2 (4) | 2557.0 (4) | 0.4 (4) | 0.0 (4) | 3/4 | 0/4 | 2/4 | {'stop': 4} |
| tune/agentclinic-repair-misleading-locus | 4 | 1 | {'BUDGET_EXCEEDED': 3, 'OK': 1} | 72.0 (4) | 17035.0 (4) | 236.0 (4) | 2735.0 (4) | 24.7 (4) | 74.0 (4) | 3.5 (4) | 69.0 (4) | 1.0 (4) | 0.0 (4) | 3.5 (4) | 1.0 (4) | 35.0 (4) | 1.5 (4) | 0.0 (4) | 60.0 (4) | 66.0 (4) | 0.0 (4) | 213.5 (4) | 14593.0 (4) | 0.0 (4) | 0.0 (4) | 4/4 | 0/4 | 2/4 | {'toolUse': 3, 'stop': 1} |
| base/selfhost-review-script | 4 | 4 | {'OK': 4} | 21.5 (4) | 14255.0 (4) | 197.5 (4) | 5774.5 (4) | 18.2 (4) | 24.0 (4) | 1.5 (4) | 20.5 (4) | 0.0 (4) | 2.0 (4) | 13.0 (4) | 2.0 (4) | 4.0 (4) | 10.0 (4) | 0.0 (4) | 0.0 (4) | 12.5 (4) | 0.0 (4) | 290.0 (4) | 40179.0 (4) | 0.6 (4) | 0.0 (4) | 4/4 | 0/4 | 4/4 | {'stop': 4} |
| tune/selfhost-review-script | 4 | 0 | {'BUDGET_EXCEEDED': 4} | 72.0 (4) | 16438.5 (4) | 186.5 (4) | 3078.5 (4) | 24.8 (4) | 72.0 (4) | 0.0 (4) | 68.5 (4) | 0.5 (4) | 3.0 (4) | 1.0 (4) | 3.0 (4) | 2.0 (4) | 46.0 (4) | 0.0 (4) | 57.5 (4) | 67.5 (4) | 1.5 (4) | 292.0 (4) | 22021.5 (4) | 0.0 (4) | 0.0 (4) | 4/4 | 0/4 | 4/4 | {'toolUse': 4} |


## Five most telling differences

1. Delivery: base 16/20 pass; tune 2/20 (17 BUDGET_EXCEEDED at the 72-turn cap, 1 NO_PATCH). Base's 4 non-passes are all complaint-lifecycle with verdict "unavailable" (not a model-fail verdict), code OK.
2. Loops, not finishing: 17 of 20 tune cells end on stopReason toolUse at turn 72; median 68 bash calls vs base 14. 954 of 1252 tune tool calls (76%) repeat an earlier identical name+args call, vs 11 of 565 (2%) for base. Median longest consecutive bash run: 66 vs 7.
3. Tune announces completion and keeps going: 14/20 tune final messages say done/complete/summary, yet the cell ends mid tool use. No cell in either model ended a turn with "stop" before its last turn (0/20 both), so the tune never stops by itself; the base always stops itself (19/20; one ends in 'error').
4. Verification churn: tune made 342 test-run and 338 git bash calls (base 83 and 38) and wrote zero heredoc files (base 32). Tune's first edit comes early (median turn 3 vs 9.5); the remaining ~65 turns re-run tests and git. Tests after last edit: 15/18 tune, 13/20 base, so verification is present in both; repetition is the gap.
5. Cost: median output tokens per turn is the same (~245), but the tune spends more total (17.8k vs 10.1k) and wall time (27 vs 12.9 min) for far less delivered. Tune max input context is smaller (median 3.0k vs 5.2k tokens). Thinking per turn is similar on median (272 vs 193 chars) except complaint-lifecycle (729 vs 181).

Flags: SFT-trace phrasing is essentially absent from thinking in both models (base "demonstrates" x4 in 3 cells; tune x1 in 1 cell; zero "Python 3.15", "Python 3.14", "PEP", "ideal for training", "this example"). One tune complaint-lifecycle cell's final text is about a "minimal Express + Pug app" (off-task) and never edited a file; check it. Tune NO_PATCH cell ended after 4 turns (stopReason length). Definitions: call counts come from tool_execution_start; tests_after_last_edit treats heredoc writes as edits; transcripts exist for all 40 cells.
