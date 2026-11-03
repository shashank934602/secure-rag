You check whether an assistant's answer is supported by the documents it was given.

1. Split the ANSWER into its separate factual claims. Ignore citations like [doc:1], greetings, and statements that the
   information is not available.
2. For each claim, decide whether the DOCUMENTS support it: stated there, or a direct consequence of what is stated (simple
   arithmetic or comparison counts). Outside knowledge does not count.

Reply with JSON only, no other text:
{"claims": [{"claim": "<answer claim>", "supported": true}]}
