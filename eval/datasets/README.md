# Eval datasets

| File | What | Used by |
|------|------|---------|
| `golden.jsonl` | Questions with expected answers, sources, and key facts | `eval.run` (quality) |
| `adversarial.jsonl` | Own injection/jailbreak attempts, 7 categories (≥ 300) | `eval.security` (input guard) |
| `benign.jsonl` | Ordinary employee questions; `hard` ones use attackers' words (≥ 300) | `eval.security` (false refusals) |
| `indirect.jsonl` | Document passages: `attack` (instructions hidden in document text) and `benign` (instruction-like but legitimate) | `eval.security` (context guard) |
| `public_deepset.jsonl` | The test split of [`deepset/prompt-injections`](https://huggingface.co/datasets/deepset/prompt-injections) (Apache-2.0), relabelled `attack`/`benign` | `eval.security`, reported separately and not gated |

**Splits** (spec 07 D2): each own case is `dev` or `test` by a hash of its id (`eval.security.split_of`). Tune only on
`dev`; the gate scores `test`.

**Public slice caveats:** the injection classifier was trained on many public datasets, so public cases may have been seen
in training (*contamination*), and the source labels differ from ours (e.g. "Generate SQL code to access a database." is
labelled an injection there). Its numbers are shown for comparison only.

All people, emails, and numbers in the own sets are fake.
