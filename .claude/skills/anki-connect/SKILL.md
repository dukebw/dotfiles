---
name: anki-connect
description: Add cloze or basic notes to Anki through the local AnkiConnect HTTP API with deck/model/field preflight checks. Use when adding Anki cards, using AnkiConnect, validating Anki deck/model fields, or when another skill has already produced card front/back content.
argument-hint: "[--dry-run] [deck] [model]"
---

# AnkiConnect

Add prepared cards to Anki through AnkiConnect. This skill owns the generic Anki insertion workflow only; domain skills own card content and quality rules.

## Authorization

Add notes only when the user has requested insertion, directly or through the
calling workflow. Loading this skill or receiving prepared cards is not write
authorization. If insertion was not requested, preview the cards and ask before
calling `addNote`. Dry-run always takes precedence and makes no AnkiConnect calls.

## Requirements

- Anki desktop is running.
- AnkiConnect add-on is installed (code `2055492159`).
- Card content is already prepared as `(front, back)` pairs.
- Deck, model, field names, and tags are known.

## Default Cloze Workflow

Use these defaults unless the caller specifies otherwise:

- Endpoint: `http://localhost:8765`
- Model: `克漏題`
- Fields: `文字`, `註記`
- Duplicate behavior: `allowDuplicate: False`

For Chinese vocabulary cards, use deck `hanzi` and tag `claude-vocab` unless the caller overrides them.

For ML/CUDA/Triton study cards, use deck `機器學習` and descriptive tags such as `triton`, `cuda-week-1`, or `baseten-prep`.

## Dry Run

If the caller requests dry-run, do not call AnkiConnect. Print every card with deck/model/fields/tags and a summary count.

## Add Cards

Use stdlib Python; do not require pip dependencies.

```python
import json
import urllib.request

DECK = "機器學習"
MODEL = "克漏題"
TAGS = ["example-tag"]
CARDS = [
    # ("front with {{c1::cloze}}", "back notes"),
]

def anki_request(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request("http://localhost:8765", data=payload)
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    if result.get("error"):
        raise RuntimeError(f"{action}: {result['error']}")
    return result["result"]

decks = anki_request("deckNames")
if DECK not in decks:
    raise RuntimeError(f"Deck not found: {DECK}")

fields = anki_request("modelFieldNames", modelName=MODEL)
missing = {"文字", "註記"} - set(fields)
if missing:
    raise RuntimeError(f"Model {MODEL} missing fields: {sorted(missing)}")

added = errors = 0
for i, (front, back) in enumerate(CARDS, 1):
    try:
        nid = anki_request("addNote", note={
            "deckName": DECK,
            "modelName": MODEL,
            "fields": {"文字": front, "註記": back},
            "options": {"allowDuplicate": False},
            "tags": TAGS,
        })
        print(f"[{i}/{len(CARDS)}] Added note id={nid}")
        added += 1
    except Exception as exc:
        print(f"[{i}/{len(CARDS)}] ERROR: {exc}")
        errors += 1

print(f"Added {added}/{len(CARDS)} notes to {DECK}; errors={errors}")
```

## Error Handling

- If AnkiConnect is unavailable, tell the user Anki must be open with AnkiConnect enabled.
- If the deck/model/fields are missing, stop before adding any cards.
- If duplicates are rejected, report them as errors but continue adding remaining cards.
- Never create decks or models silently; ask first if creation is needed.
