# D&D host Copilot instructions

## Build, test, and lint commands

- This subtree does not include a local build, test, or lint toolchain. Under `hosts\dnd`, there is no `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Makefile`, or lint config.
- There is no single-test command in this subtree. Treat changes here as data edits rather than application-code changes.

## High-level architecture

- `rule\` is a trimmed D&D rules asset bundle. Its README notes that most of the original 5etools site code, styles, and build scripts were intentionally removed, so this area is maintained as content/assets, not as a standalone app.
- `rule\data\` is the authoritative rules dataset. Top-level files such as `races.json`, `items.json`, `feats.json`, and `optionalfeatures.json` are the main entry points for broad rule categories.
- Large content families are split by source or type:
  - `rule\data\class\index.json` maps class ids like `fighter` or `wizard` to the class payload file that holds the real content.
  - `rule\data\spells\index.json` and `rule\data\bestiary\index.json` map source abbreviations like `PHB`, `XGE`, or `HotDQ` to source-specific JSON files.
  - `rule\data\adventures.json` and `rule\data\books.json` are indexes/metadata; the actual long-form bodies live in `rule\data\adventure\*.json` and `rule\data\book\*.json`.
- Fluff is stored separately from mechanics. Files such as `fluff-races.json` and `bestiary\fluff-index.json` mirror the main rules data and should stay aligned by `name` plus `source`.
- `rule\data\generated\` contains generated artifacts. `rule\data\generated\README.md` explicitly says those files should not be edited directly.
- `rule\img\` holds supporting artwork referenced by the rule content.

## Key conventions

- Preserve each file's JSON shape instead of normalizing everything into one schema:
  - many files use `{"_meta": {...}, "<entityArray>": [...]}`;
  - index files are plain key/value maps;
  - adventures and books use nested `{"data": [...]}` document trees;
  - fluff files use companion arrays such as `raceFluff`, `spellFluff`, or `monsterFluff`.
- Keep index files as dictionaries. Do not convert `class\index.json`, `spells\index.json`, `bestiary\index.json`, or similar files into arrays or richer objects.
- Preserve existing field order and formatting. `rule\README.md` says to format JSON with tabs using the style produced by JavaScript `JSON.stringify`.
- This dataset uses 5etools-style inline tags inside strings, such as `{@damage 1d6}`, `{@creature goblin}`, and `{@adventure The Rise of Tiamat|RoT}`. Keep those tags only where they are intended to be mechanical/content references; avoid adding them to flavor text or quoted prose.
- Many entities carry both localized and English labels, for example `name` and `ENG_name`. Keep both when present.
- When editing fluff, keep it synchronized with the matching mechanical entry by `name` and `source`.
- Follow the text normalization rules from `rule\README.md`:
  - replace smart quotes with ASCII `'` and `"`;
  - keep `\u2014`, `\u2013`, and `\u2212` as Unicode escape sequences when those dash/minus forms are needed;
  - use `-` for hyphenated words like `60-foot`, `\u2013` for numeric ranges, and `\u2014` for parenthetical/em-dash usage;
  - use `60 ft.` for noun measurements and `60-foot` for adjective forms.
- Source-sliced areas usually require editing the payload file named by an index, not just the index itself. If you introduce a new source-split file, update the relevant index map as part of the change.
- If a story/module references images from `rule\img\` or `img/...`, do not return local file paths. Convert them into public URLs using `https://raw.githubusercontent.com/fvtt-cn/5etools/develop/img/` plus the relative path under `img/`, preserving casing and subdirectories, so the result can be pasted directly into Discord.
