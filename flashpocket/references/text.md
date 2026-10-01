# Text mode

Create useful English chunks from a piece of English writing that is not a transcript: an article, an email, a document. The text may be a file path or pasted. Read only the file or paste the user supplies; a path grants reading only.

Prefer collocations, phrasal verbs, reusable connective phrases, and stock expressions that appear in the text and are easy to reuse. Use individual words only for important vocabulary that cannot be represented as a chunk. Skip basic words and expressions already present in the output folder. Default to at most **20 parsed cards**, counting a bidirectional line as two; accept an explicit user limit.

Every candidate needs an `example`: a short English sentence in your own words, never a sentence from the text. Do not carry over personal names, company names, figures or other specifics from the text, since emails and documents often hold internal details.

## Deck name and date

Make a short English name from the title of the text, such as `remote-work-trends`. If the text has no title or no ASCII name can be made from it, use `reading`. Pass it as `--name` without a date: the helper adds the date to the file name and heading (`YYYY-MM-DD-reading.md`). `--date` defaults to today.

## Learning settings

Read only the `Learning settings` section of `references/transcript.md` for chunk length, level, and the `--length` / `--level` options. They work exactly as in transcript mode.

```sh
python3 "<skill-directory>/scripts/decks.py" write \
  --name <deck-name> --cards "<temporary-candidates.json>" \
  [--length 短い|標準|長め] [--level やさしい|標準|高度]
```
