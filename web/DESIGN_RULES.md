# SHBExpert AI — Design Rules

Authoritative reference for all UI decisions in this codebase. When adding or editing any component, check here first. Conflicts between this file and individual component styles resolve in favor of this file.

---

## 1. Token Hierarchy

Three layers, in priority order:

```
globals.css compat vars  ← always use these in components
    ↓
SHB Design System tokens  ← color/type/spacing primitives
    ↓
Raw hex values  ← never reference directly in component CSS
```

**Always use the compat variables.** Never write `#2F2E79` in a component — write `var(--navy-700)`. Never write `#F37021` — write `var(--accent)`.

### Available tokens

| Role | Variable |
|---|---|
| Page background | `--bg` |
| Card surface | `--surface` |
| Primary border | `--border` |
| Strong border | `--border-strong` |
| Primary text | `--text` |
| Secondary text | `--text-muted` |
| Brand accent (orange) | `--accent` / `--accent-hover` |
| Navy 900/700/500 | `--navy-900` / `--navy-700` / `--navy-500` |
| Success fg/bg | `--support` / `--support-bg` |
| Warning fg/bg | `--caution` / `--caution-bg` |
| Danger fg/bg | `--oppose` / `--oppose-bg` |
| No-data fg/bg | `--need-data` / `--need-data-bg` |
| Base radius | `--radius` |

---

## 2. Color

### Brand palette

- **Navy `#2F2E79`** — structural color: sidebar, case hero banner, decision support header, workflow rail, section dividers. Never used as a card background on white pages.
- **Orange `#F37021`** — accent only: primary CTA buttons, active tab underline, left-border on the AI Brief card, links. One accent per screen. Do not use as a fill on large surfaces.
- **Gray-50 `#F7F8FA`** — page ground. Cards sit on top as white (`#FFFFFF`).

### Semantic colors

Three-state system. **Never use brand orange for semantic status.**

| State | Foreground | Background | Use |
|---|---|---|---|
| Success / Support | `--support` | `--support-bg` | Passing gate, positive finding, approve recommendation |
| Warning / Caution | `--caution` | `--caution-bg` | Borderline finding, conditions, near-limit LTV |
| Danger / Oppose | `--oppose` | `--oppose-bg` | Failing gate, reject, missing doc, conflict |
| No data | `--need-data` | `--need-data-bg` | Agent not implemented, placeholder |

Semantic color is separate from accent. A success badge is green even if the brand accent is orange.

### Navy dark surfaces

Case hero, decision support header, sidebar: `--color-navy-800` (`#201F5C`). Text on these surfaces uses `#ffffff` for primary and `var(--color-navy-300)` for secondary/muted. Never use gray text on navy — it disappears.

---

## 3. Typography

| Role | Font | Weight | Size |
|---|---|---|---|
| Display headings (hero, decision rec) | `var(--font-display)` — Poppins | 700–800 | 18–22px |
| UI labels, card titles | `var(--font-body)` — Inter | 600–700 | 12–14px |
| Body / finding claims | Inter | 400 | 12.5–13px |
| Eyebrows / uppercase labels | Inter | 700 | 10–11px + `letter-spacing: .7px` |
| Case IDs, agent IDs, citations | `var(--font-mono)` — JetBrains Mono | 400–500 | 10.5–12px |
| Financial figures | Inter | 700 + `font-variant-numeric: tabular-nums` | context-dependent |

### Rules

- Eyebrow labels (section headers above cards) are always uppercase, 10–11px, `letter-spacing: .7px`, color `--text-muted`.
- Financial amounts always use `font-variant-numeric: tabular-nums` so digits align in columns.
- Headings on dark (navy) surfaces use Poppins at weight 700–800. UI labels on dark surfaces stay Inter.
- Never set body text below 12px. Muted helper text minimum is 11px.
- `text-wrap: balance` on headings ≥ 2 lines.

---

## 4. Cards

### Base card

```css
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--radius);   /* 6px */
box-shadow: var(--shadow-sm);
```

### Hover — clickable cards

```css
cursor: pointer;
transition: box-shadow .15s, border-color .15s;

:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-strong);
}
```

Use class `card-clickable` for any card the user can click into (opens drawer, navigates, expands). Do not add hover effects to non-interactive cards.

### Card internal padding

- Standard body: `16px`
- Compact rows (proposal table, risk items): `10–12px 14–16px`
- Section eyebrow inside card: `10–12px 16px`, separated from body by `1px solid var(--border)`

### Left-border accent cards

Risk items, AI Brief card: use a `3–4px` left border in the semantic color to convey severity without coloring the entire card surface. Background stays white.

```css
border-left: 3px solid var(--support | --caution | --oppose);
```

### Placeholder / not-yet-built cards

```css
border-style: dashed;
background: var(--bg);
color: var(--text-muted);
```

Label content "Sắp có" with a `--need-data` badge. Never fabricate numbers.

---

## 5. Buttons

### Primary

```css
background: var(--accent);
border: 1px solid var(--accent);
color: #fff;
padding: 9px 18px;
border-radius: 6px;
font-size: 14px;
font-weight: 600;

:hover  { background: var(--accent-hover); border-color: var(--accent-hover); }
:active { transform: scale(.98); }
:disabled { opacity: 0.45; cursor: not-allowed; }
```

### Secondary (default)

```css
background: var(--surface);
border: 1px solid var(--border);
color: var(--text);

:hover { border-color: var(--border-strong); background: var(--bg); }
```

### Ghost (on navy surfaces)

```css
background: rgba(255,255,255,.08);
border: 1px solid rgba(255,255,255,.25);
color: #fff;
font-size: 13px;
font-weight: 600;

:hover { background: rgba(255,255,255,.16); }
```

Use only on `--color-navy-800` or darker backgrounds. Never on white cards.

### Destructive / danger

Use `--oppose` as border and focus ring. Background stays white (secondary style) unless the action is irreversible, in which case background `--oppose`, color `#fff`.

### Disabled state rule

All disabled buttons: `opacity: 0.45; cursor: not-allowed;`. Always add a `title` attribute explaining why (`"Chỉ dùng được khi READY_FOR_REVIEW"`). Never hide disabled buttons — grey them in place.

### Button sizing

| Variant | Padding | Font size |
|---|---|---|
| Large (decision panel CTA) | `10px 18px` | 13px |
| Default | `9px 18px` | 14px |
| Small (inline table) | `5px 12px` | 12px |
| Icon-only | `6px 8px` | — |

---

## 6. Status Chips & Badges

### Stance badges (finding stances)

Small pill, no border, rounded-full:

```css
.badge-SUPPORT  { background: var(--support-bg);   color: var(--support); }
.badge-CAUTION  { background: var(--caution-bg);   color: var(--caution); }
.badge-OPPOSE   { background: var(--oppose-bg);    color: var(--oppose);  }
.badge-NEED_DATA { background: var(--need-data-bg); color: var(--need-data); }
```

Padding: `2px 8px`. Font: 10.5–12px, weight 700. Use `<span>` — not interactive.

### State chips (workflow state, hard gate status)

Slightly larger, can have an uppercase label. Hard gate chips use mono font.

### Recommendation pill (case hero)

Uses inline `background` and `border` set dynamically from `REC_COLOR`. Not a static class. Alpha-blended: `background: ${color}22; border: 1px solid ${color}55`. Always includes a 7px colored dot.

### Tag (informational, non-semantic)

```css
background: var(--need-data-bg);
border: 1px solid var(--border-strong);
border-radius: 4px;
font-size: 10.5px;
font-weight: 600;
```

---

## 7. Progress & Meter Bars

All meter tracks:

```css
height: 6–8px;
border-radius: 999px;
background: var(--bg);
border: 1px solid var(--border);
overflow: hidden;
```

Fill color follows semantic rules: green (`--support`) for good, amber (`--caution`) for borderline, red (`--oppose`) for bad. Use `--navy-500` or `--navy-600` for neutral/informational bars (e.g. doc completeness).

**DSCR bar specifically:** renders a `2px` threshold marker at `(1.2 / scale) * 100%` using `--oppose` color. This is the policy minimum — always show it.

**LTV donut:** SVG circle, radius 35, stroke-width 11, `stroke-dasharray` fill based on percentage, `transform="rotate(-90 45 45)"` to start at 12 o'clock. Color: `--support` < 70%, `--caution` 70–79%, `--oppose` ≥ 80%.

---

## 8. Tables

### Agent matrix table

- `border-collapse: collapse`
- `thead` rows: 10px uppercase labels, `--text-muted` color, `--bg` background, `2px solid var(--border)` bottom
- `tbody` rows: `1px solid var(--border)` between rows, hover `background: var(--bg)`
- Expandable detail rows: `background: var(--bg)`, indented `52px` from left to clear the agent icon column

### Audit table

- Same base style
- `thead` background `#eef3fb` (fixed — audit trail is a document, not interactive)
- `tbody` `border-bottom: 1px solid #f0f0f0`
- Seq column: mono font, muted

### Overflow rule

Any table sits inside `overflow-x: auto` so the page body never scrolls horizontally.

---

## 9. Form & Interactive States

### Focus

All interactive elements must have a visible focus ring:
```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

Never `outline: none` without an alternative.

### Expand/collapse toggles

Plain text `▼` / `▲`, no border, hover background `var(--bg)`. `stopPropagation()` when nested inside a clickable row. Never use a chevron SVG for this — keep it a character.

### Loading / busy states

Spinner: `14px` border + `border-top-color: var(--accent)` + `animation: spin 0.8s linear infinite`. Show in-place where the data will appear, not in a modal overlay.

---

## 10. Layout

### App shell

```
[brand stripe 3px orange+navy]
[sidebar — fixed left]  [app-content — flex 1]
                            [app-shell — max-width 1400px, padding 24px 32px 40px]
```

### Case detail page section order (top to bottom)

1. **Case Hero** — navy banner, always visible, not in a card
2. **Page toolbar** — re-run button + log line
3. **Tab bar** — 5 tabs
4. Tab content:
   - **AI Brief** — full-width, orange left-border
   - **Two-column: Credit Proposal | Risk Panel** — 5:4 ratio
   - **Agent Matrix** — full-width table
   - **Decision Support** — full-width, navy header

### Two-column grid

```css
grid-template-columns: 5fr 4fr;   /* proposal : risk */
gap: 16px;
align-items: start;   /* columns don't stretch to match height */
```

### Spacing rhythm

| Context | Gap |
|---|---|
| Between major sections | `16px` (margin-bottom on sections) |
| Between cards in a grid | `16px` |
| Between risk items | `0` (border-bottom separates) |
| Inside card padding | `16px` |
| Compact row padding | `10px 14–16px` |
| Between inline chips/tags | `6–8px` |

### Decision Support column grid

```css
grid-template-columns: 1fr 1fr 200px;  /* evidence | conditions | actions */
```

Actions column is fixed at `200px`. Never stretch buttons to full width inside the evidence or conditions columns.

---

## 11. Dark-surface Patterns

Used in: case hero, decision support header, sidebar.

| Element | Token |
|---|---|
| Background | `var(--color-navy-800)` `#201F5C` |
| Primary text | `#ffffff` |
| Secondary / muted text | `var(--color-navy-300)` `#9998CC` |
| Subtle dividers | `var(--color-navy-600)` |
| Ghost button border | `rgba(255,255,255,.25)` |
| Ghost button bg | `rgba(255,255,255,.08)` |
| State chip bg | `rgba(255,255,255,.10)` |

Do not use `--text-muted` or any gray variable on navy surfaces — it renders too light or too dark depending on context.

---

## 12. Workflow Timeline

States per node:
- **Done** (step < active): `--color-success-600` fill, white `✓` text
- **Active** (current step): `--color-orange-600` fill, `box-shadow: 0 0 0 4px rgba(243,112,33,.25)` pulse ring
- **Pending** (future): transparent fill, `2px solid --color-navy-500` border, `--color-navy-300` text

Connector line: `2px` height, `--color-navy-600` default, `--color-success-600` when passed. Margin-bottom `14px` to vertically align with dot center (accounting for label below).

Labels below dots: 9.5px, weight 600, `--color-navy-300` for inactive, `#fff` for active. Hidden below 600px viewport width (`display: none`).

---

## 13. Things Never to Do

- **Don't put financial numbers without `font-variant-numeric: tabular-nums`** — digits misalign in columns.
- **Don't use orange as a semantic status color** — orange is brand/accent only.
- **Don't fabricate placeholder data** — use NEED_DATA stance and "Sắp có" label.
- **Don't add hover effects to non-clickable cards** — reserve pointer cursor and shadow lift for genuinely interactive elements.
- **Don't hide disabled buttons** — always render them at `opacity: 0.45` with an explanatory `title`.
- **Don't put `overflow: hidden` on the page body** — only on individual wide containers (tables, code blocks).
- **Don't nest dark (navy) surfaces** — one level of navy only. Cards inside a navy section stay white.
- **Don't use `margin-bottom` on sibling groups** — use `gap` on a flex/grid container.
- **Don't reference raw hex values in component CSS** — always use the token variables.
- **Don't use emoji as section markers** — use them only in agent icons and risk card icons where they encode type (📊 financial, 🏠 collateral, etc.).

---

## 14. Responsive Breakpoints

| Breakpoint | Layout change |
|---|---|
| `< 1200px` | Exec brief grid collapses from 5-col to 3-col |
| `< 900px` | Two-column (proposal/risk) stacks; decision columns stack; brief grid goes 2-col |
| `< 600px` | Brief grid goes 1-col; workflow labels hidden; agent table font shrinks to 12px |

---

## 15. Naming Conventions (CSS classes)

- **Layout containers**: `.detail-cols`, `.decision-body-cols`, `.exec-brief-grid` — describe content relationship, not visual style
- **Component blocks**: `.risk-item`, `.agent-row`, `.wf-dot` — block or element name
- **State modifiers**: `.ok`, `.warn`, `.bad`, `.pending`, `.done`, `.active` — semantic state, not color
- **Phase-scoped classes**: prefix new class blocks with a comment `/* Phase N redesign */` and group them at the bottom of `globals.css`

Avoid one-off inline styles for anything that appears more than once. Move recurring patterns to `globals.css`.
