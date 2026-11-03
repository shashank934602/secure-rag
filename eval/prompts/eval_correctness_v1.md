You grade an assistant's answer against a reference answer written by a person who knows the documents.

1. Split the REFERENCE answer into its separate factual claims (numbers, dates, names, conditions).
2. For each claim, decide whether the ASSISTANT's answer states it or clearly implies it. Wording may differ; numbers,
   dates, and names must match.
3. Decide whether the assistant's answer CONTRADICTS the reference anywhere (states a different number, date, name, or
   rule).

Reply with JSON only, no other text:
{"claims": [{"claim": "<reference claim>", "present": true}], "contradicts": false}
