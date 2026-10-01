# Transcript mode

Create useful English chunks from expressions actually spoken in the transcript. Prefer collocations, phrasal verbs, reusable connective phrases, and stock expressions. Use individual words only for important vocabulary that cannot be represented as a chunk. Skip basic words such as “meeting” and “today”, and expressions already present in the output folder. Default to at most **20 parsed cards**, counting a bidirectional line as two; accept an explicit user limit.

Every candidate needs an `example`: a short English sentence in your own words from this meeting, not a quotation.

## Deck name and date

Use the meeting date/name if supplied, otherwise today's local date and a neutral short English name such as `weekly-sync`. Ask only if that would materially misidentify the meeting. Pass them as `--date` and `--name`.

## Learning settings

Two fixed choices; accept no number, free-text length or other level. If the user gives no choice, use the default and do not ask again. Apply the choices to this run's extraction only.

- Chunk length: `短い` (collocations and stock phrases) / `標準` (default; short expressions that are easy to reuse at work) / `長め` (expressions with surrounding context).
- Level: `やさしい (A2–B1)` / `標準 (B1–B2)` (default) / `高度 (B2–C1)`.

Pass them as `--length` and `--level` (`やさしい` / `標準` / `高度` without the CEFR range); the helper rejects anything else.

```sh
python3 "<skill-directory>/scripts/decks.py" write \
  --date YYYY-MM-DD --name weekly-sync --cards "<temporary-candidates.json>" \
  [--length 短い|標準|長め] [--level やさしい|標準|高度]
```
