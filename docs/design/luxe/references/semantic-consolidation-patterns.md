# Semantic Consolidation Pattern Library

Use this reference when a surface has several labels, legends, filters, summaries, or navigation elements that explain the same state.

## Core Rule

Consolidate by **shared user question**, not by visual proximity.

- If two elements answer “what am I looking at?”, merge scope, count, and title.
- If two elements answer “what does this encoding mean?”, make the legend operate on the marks.
- If two elements answer “what state is this in?”, make the status indicator the state-changing control.
- If two elements answer “where am I and what remains?”, make navigation carry progress.
- If two elements answer “what happens next?”, put progress, validation, or outcome into the action.

The goal is not the fewest components. The goal is the fewest separate ideas the user must reconcile.

## Claim-Control Sentence

A claim-control sentence is a readable statement of the current view with stateful words embedded in it.

```text
showing [projects] grouped by [clusters] sized by [maturity] · coloured by [● ● ● ●]
```

At rest it explains the view. On interaction it changes the view. The current value is the trigger; the menu is not a separate label-and-input pair.

### Anatomy

1. **Stable grammar** — plain words that remain true: `showing`, `grouped by`, `as of`, `toward`.
2. **Stateful token** — the current answer, rendered as the trigger: `[projects]`, `[clusters]`, `[maturity]`.
3. **Consequence-rich options** — each option includes its meaning and, when useful, a count from the unfiltered source set.
4. **Interactive encoding key** — swatches, line styles, or status marks preview on hover/focus and isolate on click.
5. **Quiet truth tail** — a passive encoding that is useful but not worth controlling: `rim = depended-on`.
6. **Live fact** — coverage or scope stated once: `18/26 read`, `9 on record`, `67 unconfirmed`.

The bar should be the claim the visualization makes, not a toolbar followed by a second paragraph that restates it.

## Proven Scenario Family

These patterns came from a single cohort product but generalize beyond it.

| Scenario | Consolidated grammar | What it replaces |
|---|---|---|
| Directory | `listing [teams & projects] · [cohort teams 32]` | Kind tabs, membership chip row, duplicate counts |
| Relationship map | `showing [people] · linked by [same team 18] [profile 9] [shared context 12]` | Link legend plus a separate relationship filter |
| Bubble map | `showing [projects] grouped by [clusters] sized by [maturity] · coloured by [domain key]` | Scope, grouping, size legend, color legend, domain filter |
| Evidence scatter | `PMF read for [teams] + [projects] · coloured by [bottleneck key] · sized by upside · 18/26 read` | Include toggles, color legend, bottleneck filter, size key, coverage note |
| Standing view | `tracking 26 teams toward graduation · by standing [behind 7] [on plan 13] [ahead 6]` | Summary sentence, status legend, status filter |
| Time travel | `as of [Total]` or `as of [Week 6]` | Date label, separate period picker, “current snapshot” badge |

What made these work:

- Every sentence remains useful when no one clicks it.
- Every token shows the current state rather than a category label alone.
- Counts explain the consequence before selection.
- Legend interactions preserve the same hover-preview and click-pin behavior as the marks.
- Passive encodings stay passive; not every word becomes a button.
- The change removes duplicate claims elsewhere on the page.

## Scenario Generator

For a substantial surface, produce at least three candidate consolidations before building. Scan these pairings.

| Existing pieces | Candidate move |
|---|---|
| Page title + scope filter + result count | `showing [scope] · N results` as the page claim |
| Chart legend + category filter | Clickable legend: hover previews, click isolates, second click clears |
| Static size/color legend + metric selector | `sized by [metric] · coloured by [dimension]` |
| Date caption + range picker | `as of [period]` or `during [range]` |
| KPI + sparkline + drill-down link | One metric surface: value at glance, trend on hover, detail on click |
| Table column unit + repeated cell units | Put the unit once in the header; cells carry values only |
| Search label + input + result count | Input sentence or command surface that reports the live result count |
| Status badge + status dropdown | Badge is the dropdown trigger and current state |
| Nav link + unread count + progress | Link carries count/progress; opening it is the action |
| Button + spinner + completion meter | Progress fills the button; label changes with the phase |
| Form label + helper + placeholder | Keep the strongest line; make examples options or inline completion |
| Validation summary + field errors | Field owns its error; summary points to fields rather than restating them |
| Map + region list + region filter | Regions are the navigation/filter; selected region owns its summary |
| Timeline + pagination + date picker | Pannable timeline is navigation; overview window controls detail |
| Tabs + explanatory subheads | Active tab label carries the framing; remove the repeated subhead |
| Card action row + row click | Make the card’s primary object the target; reveal only secondary actions |
| Selection banner + clear button | One selection chip names state and clears it |
| Compare mode + two independent pickers | `comparing [A] with [B]` as one reversible control |
| Sort label + sort control + direction icon | Current sort phrase is the control: `ordered by [recent ↓]` |
| Permission state + access action | `visible to [team]` as both state and editor |
| Playback label + scrubber + elapsed text | Timeline position is the status and the control |
| Onboarding checklist + primary CTA | CTA names the next unfinished step and carries overall progress |
| System health legend + service filter | Health key isolates services; service rows carry their current state |
| Pricing interval toggle + price label | Price sentence owns interval: `$24 / [month]` |

Do not copy these literally. Use them to generate a grammar that fits the product’s nouns and the user’s question.

## Decision Procedure

### 1. Name the question

Write the question the user is answering in this region:

- What is included?
- What does position, color, size, or line style mean?
- Which state needs attention?
- What changed over time?
- What can I do next?

If elements answer different questions, keep them separate even when they are adjacent.

### 2. Inventory repeated answers

Mark every title, label, legend key, filter, badge, count, helper line, and summary that answers the question. Identify the canonical fact and remove restatements.

### 3. Draft three grammars

Draft three distinct candidate sentences or compound controls. For each, state:

- what it explains at rest;
- what becomes interactive;
- what it eliminates;
- what becomes less discoverable.

Choose the candidate with the lowest reconciliation cost, not automatically the shortest.

### 4. Assign interaction layers

- **Rest:** current scope and meaning are readable.
- **Hover/focus:** preview the consequence without committing.
- **Click/press:** apply or pin the state.
- **Repeat/Escape:** clear or return to the previous state.

For touch, provide tap-to-open or tap-to-preview; never depend on hover alone.

### 5. Delete the old explanation

After the compound control works, remove the old legend, label, helper line, duplicate count, or panel. Consolidation has failed if all the old chrome remains “for clarity.”

### 6. Test the sentence in every state

Read it aloud with default, active, empty, loading, error, and narrow-width values. The grammar must remain truthful when a token changes.

## Token and Menu Contract

- Render the token as a real button with `aria-haspopup="listbox"` and live `aria-expanded`.
- Put options in a listbox; use `role="option"` and live `aria-selected`.
- Move focus to the selected option on open.
- Support arrow keys, Enter, Escape, outside press, and focus-leave dismissal.
- Return focus to the token when Escape closes its menu.
- Use an explicit group label for the whole sentence.
- Keep interactive legend keys as buttons with `aria-pressed`; do not encode selection by color alone.
- Give every swatch a text name in the accessible label.
- Show disabled or empty options honestly; do not silently remove a category with zero results when its absence is informative.
- Compute option counts from the unfiltered source when the count describes what selecting the option would reveal.

## Responsive Contract

- Wrap at semantic boundaries, not inside a token.
- Keep each stable phrase with its following token when possible.
- Allow the sentence to become two calm lines; do not force a tiny single-line scroller merely to preserve the concept.
- Move rare actions to overflow before hiding the sentence’s current state.
- On very narrow screens, retain the claim and collapse secondary encodings into one `details` or popover surface.

## Failure Modes

- **Mad Lib overload:** five or more bright dropdown tokens make prose harder to read than a toolbar. Keep frequent/high-value choices visible; move rare power filters into one token or overflow.
- **False consolidation:** controls share a row but still require a separate legend and paragraph to explain them.
- **Grammar drift:** an option changes the noun so the surrounding sentence becomes untrue.
- **Hidden frequent action:** a two-choice, high-frequency switch was buried in a menu. Prefer a segmented control when comparison and one-click switching matter.
- **Everything is interactive:** punctuation, passive facts, and quiet encoding notes should remain text.
- **Legend theater:** keys look clickable but do not update the data, URL/state, or selected styling.
- **Count mismatch:** token count reflects the already-filtered result even though the menu promises the size of each alternative.
- **Hover-only meaning:** touch and keyboard users cannot preview or isolate.
- **Color-only state:** swatches lack labels, shapes, line styles, or accessible names.
- **Duplicate survival:** the old legend or status block remains elsewhere, so the user now reconciles two sources of truth.
- **Mobile confetti:** every token wraps alone. Group stable phrase + token units and reduce optional facts.

## Harvest New Patterns from Finished Work

When a user says a finished interface contains a “cool thing” worth reusing, record the move as a pattern, not as a screenshot description.

Capture exactly:

1. **Context:** what the user was trying to understand or change.
2. **Before:** which separate elements or repeated claims existed.
3. **Move:** which shared question allowed them to consolidate.
4. **Grammar:** one representative state and one changed state.
5. **Interaction:** rest, hover/focus, click, clear, keyboard, touch.
6. **Eliminated:** panels, labels, legends, routes, or duplicate facts removed.
7. **Trade-off:** what became less visible or more indirect.
8. **Boundary:** when not to reuse it.

Add a new scenario only when it teaches a different semantic relationship. Do not add cosmetic variants of an existing pattern.

## Review Output

When recommending a consolidation, report:

```text
Question: [the user question these elements share]
Current fragments: [labels / controls / legends / counts]
Candidate grammars: [at least three]
Chosen move: [the compound element]
Eliminates: [old chrome removed]
Interaction: [rest → preview → commit → clear]
Trade-off: [discoverability or density cost]
```
