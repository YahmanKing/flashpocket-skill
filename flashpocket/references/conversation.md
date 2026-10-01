# Conversation mode

Make cards from the current conversation with the user, or from a list of expressions they pass directly. The conversation is the input, so do not ask for a file. Act only after the user invokes the skill or asks for cards; never watch the conversation or save on your own.

## What to pick

Pick from the conversation before the invocation and the one after it. Four signals only:

1. An expression the user asked how to say ("how do you say …in English?").
2. A passage of the user's English that was corrected. Take the corrected expression.
3. An English expression the user asked the meaning of.
4. An expression the user said they want to remember or use, or a list they passed directly ("make cards of these").

Do not pick words that are too generic, or the topic of the conversation itself (code, proper nouns, product names). Skip expressions already in the output folder. Default to at most **20 parsed cards**, counting a bidirectional line as two.

A list passed directly (signal 4) is never reduced: every item becomes a candidate. Fill in a missing meaning yourself; an example is optional for these. Count the cards (a bidirectional line is two) and pass that number as `--limit`, otherwise the default 20 silently drops the rest. Signals 1 to 3 keep the default limit unless the user names another.

Every candidate from signals 1 to 3 needs an `example`: a short English sentence in your own words, never a line from the conversation (it may hold internal details). `meaning` and `chunk` stay as they appeared, because the expression is the card.

## Keeping candidates

After the skill is invoked, keep picking in the same session. Do not rely on memory, since a long conversation may be compacted: append each candidate to a temporary JSON file in the current working directory.

- Name it `.flashpocket-conversation-<random id>.json` (hidden, so parallel sessions never collide and it is unlikely to be committed). Do not edit `.gitignore`.
- Tell the user once, when you create it, that candidates are kept in this file and it is deleted after saving. Write the file name in the conversation.
- This is the one exception to "use a new temporary filename": you may keep appending to the file you made yourself in this session. Never overwrite any other file.
- If you forget the path, look for `.flashpocket-conversation-*.json` in the working directory; ask which one only when there are several.
- Delete it after saving. If saving fails or stops, report the leftover path.

## Confirm and save

Show the candidate list and the destination question, once, only when the user asks to save ("保存して", or an invocation that is itself a request such as "make cards from this conversation"). If the invocation did not ask to save, only report how many candidates you have. Start with every candidate selected; the user names only what to exclude. Candidates added later are in the same list, so nothing is saved unconfirmed.

## Deck name and date

Default name `conversation` (file `YYYY-MM-DD-conversation.md`); use another neutral name if the user gives one. Pass it as `--name`; `--date` defaults to today. Duplicate removal and appending follow the core rules.

```sh
python3 "<skill-directory>/scripts/decks.py" write \
  --name conversation --cards ".flashpocket-conversation-<id>.json" [--limit N]
```
