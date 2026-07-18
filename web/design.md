# SHBExpert AI — Design System Reference

Design tokens live in `/web/SHB Design System/tokens/`. Global CSS is `/web/app/globals.css`. This doc is the authoritative reference for how to apply them.

---

## 1. Color

### Brand palette

| Token | Value | Usage |
|-------|-------|-------|
| `--color-orange-600` | `#F37021` | Primary CTAs, active states, links, accent headings, bullet markers |
| `--color-navy-700` | `#2F2E79` | Headings, structural text, brand secondary |
| `--color-navy-800` | `#201F5C` | Sidebar background, deep navy surfaces |
| `--color-navy-900` | `#16153F` | Darkest surface, decision hub header |

### Semantic aliases (prefer these over raw palette)

```css
--brand-primary          /* #F37021 orange — CTAs, links, active tab underline */
--brand-accent           /* #2F2E79 navy — structural surfaces */
--surface-page           /* gray-50  — page background */
--surface-card           /* white    — card background */
--surface-sunken         /* gray-100 — table headers, input backgrounds */
--surface-accent-soft    /* orange-50 — selected row tint */
--text-primary           /* gray-900 */
--text-secondary         /* gray-600 */
--text-link              /* orange-600 */
--border-subtle          /* gray-200 */
--status-success-*       /* green variants */
--status-warning-*       /* amber variants */
--status-danger-*        /* red variants */
```

### Color rules
- **Orange is the action color.** Use it for primary buttons, active nav indicators, card titles, and highlight text.
- **Navy is the structure color.** Use it for sidebars, deep headers, and primary headings.
- Never use raw hex in component files — always reference a token.
- Status colors (success/warning/danger) are reserved for data states only, not decoration.

---

## 2. Typography

### Fonts
| Role | Family | Import |
|------|--------|--------|
| Display (headings, large numbers) | `Poppins` 500–800 | Google Fonts |
| Body / UI labels | `Inter` 400–700 | Google Fonts |
| Code / monospace data | `JetBrains Mono` 400–500 | Google Fonts |

> When SHB provides official brand fonts, swap the `@font-face` in `typography.css` — all references will update automatically.

### Type scale tokens
```css
--text-xs: 12px   /* labels, captions, badge text */
--text-sm: 14px   /* body, table cells, meta */
--text-base: 16px /* default body size */
--text-lg: 18px   /* card titles */
--text-xl: 20px   /* section headings */
--text-2xl: 24px  /* KPI values, hero numbers */
--text-3xl: 30px  /* score display */
```

### Weight tokens
```css
--weight-regular:  400
--weight-medium:   500
--weight-semibold: 600
--weight-bold:     700
--weight-extrabold: 800  /* KPI numbers, hero scores, verdict text */
```

### SHB two-tone headline pattern
A signature SHB pattern — first line in navy, second line in orange:
```html
<h2 class="shb-two-tone-heading">
  <span>Giải pháp tín dụng</span>
  <span>Phù hợp doanh nghiệp</span>
</h2>
```
```css
/* defined in globals.css */
.shb-two-tone-heading > span:first-child { color: var(--color-navy-700); }
.shb-two-tone-heading > span:last-child  { color: var(--color-orange-600); }
```

---

## 3. Spacing & Geometry

### Border radius
| Token | Value | Use |
|-------|-------|-----|
| `--radius-xs` | 4px | Tight badges, chips, micro-components |
| `--radius-sm` | 8px | Buttons, input fields, small cards |
| `--radius-md` | 12px | Standard cards, panels, modals |
| `--radius-lg` | 16px | Hero cards, large surface components |
| `--radius-full` | 999px | Pills, avatar circles, full-round chips |

Default `--radius` resolves to `--radius-md` (12px). This matches the ~16px rounding visible on SHB's public website cards — close enough for internal tool use.

### Shadows (elevation)
| Token | Value | Use |
|-------|-------|-----|
| `--shadow-xs` | 1px/2px navy tint | Icon buttons, inline elements |
| `--shadow-sm` | 2px/6px navy tint | Standard cards, filter bars |
| `--shadow-md` | 6px/16px navy tint | Hero cards, popovers, drawers |
| `--shadow-lg` | 16px/32px navy tint | Modals, dialogs |

Cards are **flat-first**: prefer `--shadow-sm` over `--shadow-md` unless something needs to feel elevated.

### Layout constants
```css
.app-shell     { max-width: 1400px; padding: 24px 32px 40px; }
.aq-shell      { max-width: 1480px; padding: 20px 28px 48px; }
sidebar width  { 230px, fixed }
```

---

## 4. Components

### Cards
```css
.card {
  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);  /* 12px */
  box-shadow: var(--shadow-sm);
}
```
- Card titles use **orange** (`--color-orange-600`), bold, `--text-lg`
- Card subtitles use navy (`--text-primary`), regular weight
- Internal card padding: `16–24px`

### Buttons
| Class | Background | Text | Border-radius | Use |
|-------|-----------|------|---------------|-----|
| `.btn-primary` | `--brand-primary` (orange) | white | `--radius-sm` | Primary actions |
| `.btn` | `--surface-card` | `--text` | `--radius-sm` | Secondary / outline |
| `.btn-ghost` | transparent | white | `--radius-sm` | On dark backgrounds |

CTA pattern from SHB public site: full-width button, orange fill, white text, 48px height.

### Badges / Status chips
```css
/* Stance variants */
.badge-SUPPORT   { background: --status-success-bg; color: --status-success-fg; }
.badge-CAUTION   { background: --status-warning-bg; color: --status-warning-fg; }
.badge-OPPOSE    { background: --status-danger-bg;  color: --status-danger-fg; }

/* Priority variants */
.aq-priority--critical  /* red   */
.aq-priority--high      /* amber */
.aq-priority--medium    /* navy  */
.aq-priority--low       /* green */
```

shadcn Badge variants available: `default`, `success`, `warning`, `danger`, `navy`, `orange`, `muted`

### Filter chips
```css
.aq-chip           /* default: white bg, gray border */
.aq-chip--active   /* orange bg, white text */
.aq-chip--clear    /* borderless, gray text */
```
Chips use `--radius-full` (pill shape).

### Sidebar
- Background: `--color-navy-800` (dark navy)
- Active item: `rgba(255,255,255,0.12)` background + `--color-orange-500` text
- Hover: `rgba(255,255,255,0.08)` background + white text
- Logo mark: orange square (`--color-orange-600`), white "S"
- Footer: user avatar with orange background, divider `rgba(255,255,255,0.08)`

### Orange bullet list pattern (from SHB website)
```html
<ul class="shb-bullet-list">
  <li>Item one</li>
  <li>Item two</li>
</ul>
```
```css
/* defined in globals.css */
.shb-bullet-list li::before {
  content: "";
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--color-orange-600);
  margin-right: 8px;
  vertical-align: middle;
  flex-shrink: 0;
}
```

---

## 5. Page-level Patterns

### SHB brand stripe
Full-width orange bar with navy underline — used at top of pages:
```html
<div class="shb-stripe"></div>
```

### Application Queue page (/)
- Shell: `.aq-shell`
- Top: KPI strip → 3 cards (SLA sparkline, Portfolio RadialBar, Queue summary)
- Filter bar: product chips + Đơn vị select + Hạn mức range
- Body: 2-col — CaseTable + ProcessingFunnel chevrons (left) | ProductDonut + HighPriority (right)

### Case Detail page (/cases/[caseId]/)
- Sticky 2-row header: main bar + sub-header with breadcrumb + action buttons
- Hero card: dark navy, case ID mono + company name + meta + badges
- Planner workflow: 5-step progress rail (navy circles, orange active, green done)
- 4 Agent cards: Legal (navy) / Financial (green) / Collateral (amber) / Risk (red)
- Bottom 3-col: ScoreSummary + VerdictCard + RAGEvidence
- Tabs: AI Review | 360° Overview | Decision Hub

### 360° Overview tab
- KYCCard: 3-col (legal info / persons with eKYC / company profile)
- CreditRequestCard: loan amount + 5-step vertical timeline
- FinancialTable: 5-row BCTC (revenue/EBITDA/net profit/DSCR/equity)
- CollateralSection: details dl + PieChart donut (navy/green/amber cells)
- ScoreSidebar: 6 dimension scores + composite + credit rating

---

## 6. Motion

All transitions use design-system easing and duration tokens:
```css
transition: background var(--duration-fast) var(--ease-standard);  /* 120ms */
transition: opacity   var(--duration-base) var(--ease-standard);   /* 180ms */
transition: width     var(--duration-slow) var(--ease-out);        /* 260ms — progress bars */
```
No bounce, no spring. Banking UI = calm, deliberate motion.

---

## 7. Do / Don't

| Do | Don't |
|----|-------|
| Use `--brand-primary` for CTAs and links | Use raw `#F37021` in component files |
| Use `--surface-card` + `--border-subtle` for cards | Mix different card shadow levels in the same section |
| Use orange for card titles, active states, bullet markers | Use orange for status indicators (use semantic colors) |
| Use navy for structural surfaces (sidebar, hero banners) | Use navy for body text — use `--text-primary` (gray-900) |
| Round cards at `--radius-md` (12px) | Use `border-radius: 4px` on cards |
| Keep motion under 200ms for interactive states | Add CSS animations to data cells or tables |
| Use `font-variant-numeric: tabular-nums` on all numbers | Left-align currency/percentage columns in tables |
