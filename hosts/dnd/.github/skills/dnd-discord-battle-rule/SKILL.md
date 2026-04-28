---
name: dnd-discord-battle-rule
description: "D&D Discord battle procedure - focused on initiative, round flow, battlefield tracking, pacing, and combat presentation for text-based play."
---

# D&D Discord Battle Procedure

This skill is for running **Discord text-based combat** well. It does not replace the PHB combat rules. Instead, it defines how to present, pace, track, and narrate combat clearly and efficiently in a text medium.

- **Mechanical baseline:** `dnd-core-rules`
- **This skill covers:** combat presentation, round flow, pacing, compression, battlefield tracking, and narration

---

## When to Use It

Treat this skill as the default operating procedure whenever any of the following is true:

- Combat begins and initiative is about to be rolled
- The scene becomes dangerous enough to require round-by-round resolution
- Positioning, cover, concentration, conditions, or objective points matter
- The fight needs to be clearly communicated in Discord instead of resolved as a vague abstraction

For tiny, low-stakes, tactically irrelevant scuffles, you can resolve the outcome narratively. Once the scene truly becomes turn-based, use this skill.

---

## Core Principles

1. **Combat must be clear**
   - Players should know whose turn it is, what the battlefield broadly looks like, and what the immediate dangers and opportunities are.

2. **Combat must stay fast**
   - Discord is a text medium. It does not benefit from bloated play-by-play for every unimportant action.

3. **Combat must feel dramatic**
   - Combat should not be a pure exchange of numbers. Ideally, each round changes the situation, pressure, mood, injuries, terrain, or objectives.

4. **Combat must respect the rules without being slowed by formatting**
   - The mechanics should be accurate, but the presentation should stay lean.

---

## Opening a Combat Scene

### 1. Review Character State in `characters.md`

- Before initiative is rolled, read the latest character state from `characters.md`.
- Confirm the current combat-ready state for each involved PC, especially:
  - current HP and max HP
  - AC, speed, and currently equipped combat gear
  - active conditions, exhaustion, or other persistent penalties
  - spell slots, limited-use features, and consumable combat resources
  - any unresolved consequences from the previous scene that still matter in battle
- If the stored sheet and the live fiction conflict, reconcile that before the first turn begins.

### 2. Roll Initiative

- Roll initiative for each combatant, or for sensible enemy groups.
- Present the initiative order clearly.
- If many enemies are functionally similar, grouped initiative is appropriate for pacing.

### 3. Establish a Battlefield Overview

At the start of combat, give a **brief but actionable** overview that prioritizes:

- Relative positions of player characters and enemies
- Cover
- Chokepoints, doors, bridges, stairs, and other terrain anchors
- Hazard zones and interactable objects
- Elevation, visibility, and lighting
- Current objective points such as an altar, exit, hostage, or ritual circle

The goal is to make the battlefield easy to grasp at a glance, not to redraw a full text map every round.

---

## What Each Meaningful Turn Should Show

Each meaningful turn should communicate, as needed:

- The active combatant
- The declared action
- Relevant rolls and results
- Damage or effects
- Updated HP, conditions, concentration, or positioning when relevant

If a character has a `default combat rule` in `characters.md`, follow it unless the player explicitly declares a different approach for that turn.

---

## Action Economy

Combat should always respect:

- **Action**
- **Bonus Action**
- **Movement**
- **Reaction**
- **Free Object Interaction** when appropriate

Do not quietly allow illegal actions just to speed things up, and do not ignore action economy because the game is text-based.

---

## Tactical Factors to Track

At minimum, make sure the following are tracked when they matter:

- Cover
- Range
- Light and vision
- Terrain and elevation
- Conditions
- Opportunity attacks
- Concentration

You do not need to restate all of them every round, but you must not omit a factor that meaningfully changes the ruling.

---

## Discord-Specific Pacing Rules

### Routine Fights

If the fight is non-critical, low-risk, low-drama, and the players are not trying unusual tactics:

- Aim to resolve it in about **2 rounds of meaningful player actions**
- Group mook actions
- Summarize repeated attacks
- Drop unnecessary positional detail after the opening exchange
- Focus on consequences, not arithmetic blow-by-blow

### Important Fights

If the fight is a story battle, elite encounter, miniboss, or tactically important scene:

- Let the fight breathe, often around **6 rounds**
- Each round should introduce or reflect some change: reinforcements, collapse, shifting objectives, spell effects, morale shifts, environmental turns

### Final Battles / Climactic Fights

If the fight is a final boss, arc climax, or major showdown:

- It can stretch to around **10 rounds**
- Only do so if the scene keeps changing, the tension remains high, and the players still have meaningful choices

These are pacing targets, not hard caps. End early if the outcome is already obvious; go longer only if the scene remains interesting.

---

## Compression Rules

In routine fights, compress aggressively:

- Merge repetitive enemy actions
- Do not expand every irrelevant miss
- Do not repeat the full battlefield state every round
- Do not over-explain simple arithmetic

Compression does not mean hiding important information. Keep:

- Hits and major misses
- Significant damage
- Status changes
- Being downed, broken concentration, or major repositioning
- New dangers or new openings

---

## How to Open an Important Fight

For important fights, begin with a short top-down tactical overview that at least covers:

- Relative positions of the PCs and enemies
- Cover and blockers
- Chokepoints and routes
- Hazardous terrain
- Elevation
- The objective

Once the battlefield is clear, do not keep printing a full text-map every round unless the field changes in a major way.

---

## Alternative Victory Paths

If the players are clearly more interested in solving the situation than grinding every enemy to 0 HP, allow other victory paths:

- Negotiation
- Breaking morale
- Disabling a ritual
- Escaping with the objective
- Using terrain, traps, or mechanisms
- Forcing surrender, retreat, or redirection

The point of combat is to change the situation, not to force every conflict into a last-hit-point slugfest.

---

## Closing a Combat Scene

When combat ends, do not stop at the final blow. Resolve the full post-combat procedure:

1. **Confirm the end state**
   - Identify who is dead, unconscious, stable, fleeing, captured, surrendered, or otherwise neutralized.
   - Resolve any immediate end-of-fight effects that still matter, such as concentration ending, death save consequences, or ongoing hazards.

2. **Calculate encounter experience**
   - Calculate XP for the encounter once the outcome is clear.
   - Include enemies that were defeated, routed, captured, bypassed through meaningful victory, or otherwise neutralized as appropriate to the actual outcome.
   - If the campaign uses milestone leveling, you may still record the encounter's XP value for bookkeeping, but it must not override the campaign's leveling method unless the campaign explicitly uses XP advancement.

3. **Write the final character state back to `characters.md`**
   - Update the final post-combat state for every affected PC, including as relevant:
     - current HP and max HP
     - conditions and exhaustion
     - spell slots and limited-use features
     - expended consumables and ammunition
     - concentration loss, deaths, stabilization, and other persistent consequences
     - treasure, loot, and XP awarded
   - Do not rely on short-term memory alone after combat. Persist the final state before moving on.

4. **Give a concise aftermath summary**
   - Briefly state the outcome of the fight, the cost to the party, and the immediate next-state of the scene.

---

## Enemy Behavior Principles

- Enemies should act according to **intelligence, motives, fear, loyalties, and training**
- Do not run enemies with omniscient perfect optimization
- Beasts, mooks, zealots, veteran commanders, and cunning spellcasters should fight differently

---

## Roll and Result Presentation

Show important rolls clearly, but keep the format concise.

Example:

```text
Attack Roll (Longsword)
Attack Bonus: +6  |  Target AC: 14  |  Roll: [8] + 6 = 14
Result: ✓ Hit
Base Damage: 1d8 + 4 = [7 slashing]
Resistance: target resists slashing -> 7 / 2 = 3
Final Damage Applied: 3
```

Include the following when relevant:

- Advantage or disadvantage
- Whether a concentration check is triggered
- Whether an opportunity attack occurs
- Whether the result causes prone, restrained, unconscious, or similar states
- Whether resistance, vulnerability, or immunity modifies the damage

When damage is rolled, show the sequence clearly when it matters:

1. roll the base damage
2. identify the damage type
3. apply resistance, vulnerability, or immunity
4. report the final damage that actually changes HP

---

## Combat Narration Rules

Combat should not feel like abstract number trading.

### On a Hit

Do not just say "12 damage." Translate the hit into visible or felt consequences, such as:

- Armor splitting
- Staggered footing
- Blood on stone
- A broken shield strap
- Arcane backlash cracking through the air
- A monster suddenly shifting into fear or rage

### On a Miss

Misses should not always be rendered as a flat "you miss." Depending on context, they can look like:

- Deflected by a shield
- Barely passing by
- Stopped by terrain
- Awkwardly dodged
- Thrown off by fear, darkness, or smoke

### Narration Pace

- Keep it brisk
- Let narration support the ruling rather than slow the turn down
- But in important fights, make the battle feel like an event, not a spreadsheet exchange

---

## Division of Responsibility with Other Skills

- **`dnd-core-rules`** provides the PHB combat mechanics
- **`dnd-monsters`** provides monster abilities, tendencies, and tactical behavior
- **`dnd-dm-guide`** provides encounter design, difficulty guidance, rewards, and DM adjudication support
- **This skill** turns those sources into a practical combat procedure for Discord text play
