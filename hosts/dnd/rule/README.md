## D&D Rule Assets

This directory has been trimmed down to the assets still used for rule content:

- `data\`: JSON rule data and reference content
- `img\`: story, book, creature, and related images

Most of the original 5etools website code, styles, build scripts, and page files were intentionally removed.

## Data Inventory

The `data\` directory currently contains `278` JSON files.

- Root level: `47` JSON files
- `adventure\`: `40` files
- `bestiary\`: `98` files
- `book\`: `19` files
- `class\`: `18` files
- `roll20-module\`: `31` files
- `spells\`: `25` files

### Root-Level Files

These top-level files are the main entry points for the dataset:

- Core player and rules data: `actions.json`, `backgrounds.json`, `charcreationoptions.json`, `feats.json`, `languages.json`, `optionalfeatures.json`, `races.json`
- Equipment and treasure: `items.json`, `items-base.json`, `magicvariants.json`, `loot.json`, `rewards.json`
- GM and worldbuilding data: `conditionsdiseases.json`, `cultsboons.json`, `deities.json`, `encounters.json`, `monsterfeatures.json`, `names.json`, `objects.json`, `psionics.json`, `recipes.json`, `tables.json`, `trapshazards.json`, `variantrules.json`, `vehicles.json`, `life.json`
- Book and adventure indexes: `books.json`, `adventures.json`
- Fluff companions: `fluff-backgrounds.json`, `fluff-charcreationoptions.json`, `fluff-conditionsdiseases.json`, `fluff-items.json`, `fluff-languages.json`, `fluff-races.json`, `fluff-recipes.json`, `fluff-vehicles.json`
- Tool/export files: `foundry-feats.json`, `foundry-items.json`, `foundry-optionalfeatures.json`, `foundry-races.json`, `roll20-items.json`, `roll20-tables.json`, `makebrew-creature.json`, `makecards.json`, `msbcr.json`, `renderdemo.json`
- Metadata: `changelog.json`

### Subdirectories

- `adventure\`: full adventure text payloads. `adventures.json` is the adventure index, while each file in `adventure\` stores the actual chapter/section content under a top-level `data` array.
- `book\`: sourcebook text payloads. `books.json` is the index, while `book\` contains the actual structured book sections.
- `bestiary\`: monster stat blocks split by source book, plus fluff and shared support files such as indexes and reusable trait/group data.
- `class\`: class definitions, class features, and subclass features. `class\index.json` maps class ids such as `fighter` or `wizard` to their file names.
- `spells\`: spell lists split by source, plus `index.json` source mapping and fluff files.
- `roll20-module\`: Roll20 export bundles with fields such as `schema_version`, `maps`, `handouts`, `characters`, `journal`, and `rolltables`.

## Common JSON Shapes

Most content files use one of these patterns:

- A metadata wrapper plus one entity array, for example:
  - `{"_meta": {...}, "race": [...]}`
  - `{"_meta": {...}, "item": [...]}`
  - `{"optionalfeature": [...]}`
- An index object which maps source or ids to file names, for example:
  - `spells\index.json`
  - `bestiary\index.json`
  - `class\index.json`
- A text payload wrapper for long-form books or adventures:
  - `{"data": [...]}`
- A fluff companion file:
  - `{"raceFluff": [...]}`
  - `{"spellFluff": [...]}`
  - `{"monsterFluff": [...]}`

### Frequently Seen Entity Fields

Many rule entities share these fields:

- `name`
- `ENG_name`
- `source`
- `page`
- `entries`
- `otherSources`

Some categories add their own common fields:

- Races: `size`, `speed`, `ability`, `languageProficiencies`, `traitTags`
- Items: `rarity`, `reqAttune`, `wondrous`, `weight`, `focus`
- Spells: `level`, `school`, `time`, `range`, `components`, `duration`, `classes`
- Monsters: `size`, `type`, `alignment`, `ac`, `hp`, `speed`, ability scores, `trait`, `action`, `cr`
- Loot tables: `mincr`, `maxcr`, `table`
- Names: `tables`, `diceType`, `table`

### Monster Token Image Resolution

Bestiary token images follow the same convention used by 5etools:

- If a monster entry has `tokenUrl`, use that URL directly.
- Otherwise, if the entry has `hasToken: true`, derive the image path as `img\<SOURCE_ABV>\<TOKEN_NAME>.png`.
- `<SOURCE_ABV>` comes from the monster `source` field and must stay as the 5etools source abbreviation, such as `MM`, `VGM`, `MTF`, or `XGE`.
- `<TOKEN_NAME>` comes from `ENG_name` when present, otherwise `name`, then normalized by converting to ASCII and removing double quotes.
- In this repository, that derived `img\...` path maps to `rule\img\...`.
- Variant or alternate-art tokens should use the variant token metadata's own `name`, `source`, and optional `tokenUrl`.

Examples:

- `source: "MM"` plus a token-safe name of `Aarakocra` resolves to `rule\img\MM\Aarakocra.png`.
- If `tokenUrl` is present, do not rewrite it into the derived `img\...` form.

## Editing Guide by File Type

### Simple Entity Files

Files such as `races.json`, `items.json`, `feats.json`, and `optionalfeatures.json` usually contain a single entity array. Edit the objects in that array and preserve the existing field order and tag style.

### Index Files

Files such as `spells\index.json`, `bestiary\index.json`, and `class\index.json` are lookup maps. They should stay as plain key/value dictionaries and should not be converted into arrays.

### Fluff Files

Files prefixed with `fluff-` or entries such as `monsterFluff` hold descriptive or narrative text rather than mechanical rules. Keep them aligned with the matching rule entity by `name` and `source`.

### Long-Form Content

Adventure and book payloads are stored as nested `data` arrays with sections, headers, read-aloud blocks, and other structured entry types. These files are closer to document trees than flat records.

## JSON Editing Notes

The JSON files should stay close to the source material and keep a stable structure.

- Format JSON with tabs for indentation, following the default output style of JavaScript's `JSON.stringify`.
- Keep one line per bracket and one line per value.
- Only tag references that are intended to be mechanical references, such as `{@creature goblin}`.
- Avoid tagging flavor text and quoted text blocks.
- Avoid referencing content from sources published after the source currently being edited.

## Text Normalization

- Replace `’` with `'`
- Replace `“` and `”` with `"`
- Replace `—` with `\u2014`
- Replace `–` with `\u2013`
- Replace `−` with `\u2212`
- Do not use `•` when the content should be represented as a JSON list
- Only `\u2014`, `\u2013`, and `\u2212` should be kept as Unicode escape sequences

## Formatting Conventions

### Dashes

- Use `-` only for hyphenated words such as `60-foot`
- Use `\u2014` for parenthetical dash pairs or empty table rows
- Use `\u2013` for numeric ranges
- Use `\u2212` for unary minus values

### Measurement

- Adjectives use a hyphen and full unit name, for example `60-foot line`
- Nouns use a space and abbreviated unit, for example `darkvision 60 ft.`
- Time uses `/` with no surrounding spaces, for example `2/Day`

### Dice

Write dice as `[X]dY[ <+|-|×> Z]`, for example `d6`, `2d6`, or `2d6 + 1`.

### Item Names

Use title case for item names. If a unit appears in parentheses, keep the unit sentence case.
