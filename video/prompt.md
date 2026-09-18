# Visual Assets — prompt.md

> Two SVG illustrations for the GridWise presentation.
> Gemini: please generate each as a clean, flat-design SVG with the exact
> filename and dimensions specified below. Background should be transparent
> so the slides' off-white background (#f7f5f0) shows through.
>
> Style guide:
> - Flat, geometric, minimal (think Stripe / Linear / Vercel docs).
> - Off-white compatible — do NOT use pure white fills; use the colors below.
> - Color palette:
>     ink          #1a1d23    primary text/lines
>     muted        #5a6271    secondary text
>     indigo       #4f46e5    primary accent
>     teal         #0d9488    success / secondary
>     amber        #d97706    highlight / energy
>     paper        #f7f5f0    background (transparent — don't fill)
>     card         #ffffff    card fills (only when needed for contrast)
>     border       #e5e0d5    soft borders
> - Sans-serif labels (Inter or system-ui). Monospace for code-style tags.
> - No gradients, no drop shadows beyond a single very soft one.
> - Stroke widths: 1.5px for outlines, 2px for emphasis.
> - Each visual should "read" at 1280x720 inside a slide.

---

## 1. `pipeline.svg` — 1200 × 360

**Use case:** Goes on slide 3 ("Architecture"). Replaces the current
left-to-right box-and-arrow strip. Show the flow of a single request through
the system, with the LLM chain highlighted as the heart.

**Composition (left to right):**

```
[ Request box ] → [ Validate ] → ★ [ LLM Chain ] ★ → [ Guard ] → [ LP Solve ] → [ Response ]
                                                 ↓
                                       (illustrated fallback branch)
```

- **Request box** — small rounded rect with a JSON snippet icon
- **Validate** — rounded rect with a checkmark icon (Pydantic)
- **LLM Chain** — emphasized card (indigo border, soft indigo fill #eef2ff).
  Inside, show 4 stacked pills: `gpt-oss-120b` → `compound-mini` →
  `qwen-3.8-27b` → `gemini`, with a curved arrow looping from the last pill
  back to the first labeled "rotate on 429".
- **Guard** — rounded rect with a shield icon
- **LP Solve** — rounded rect with a math-y icon (matrix or sigma)
- **Response** — rounded rect with `{ }` JSON braces
- All connected by thin indigo arrows with arrowheads.
- Below the LLM Chain card, a dotted secondary arrow labeled "fallback heuristic" pointing to "LP Solve" (showing that if the LP is infeasible, the heuristic kicks in).
- Small caption beneath: "Each stage has a safety net."

**Layout grid:**
- Total width 1200, height 360.
- 6 cards in a row, each ~150px wide, ~110px tall, centered vertically.
- 30px gap between cards, arrows in the gaps.
- LLM Chain card slightly taller (~150px) to fit the 4 model pills inside.

---

## 2. `chain.svg` — 800 × 200

**Use case:** Goes on slide 5 ("Resilience"). Replaces the 4-card row of
models. Visualizes the LLM failover chain more dramatically — show the
primary highlighted, others grayed out, with a "kicked" arrow from primary
to backup if it fails.

**Composition:**

```
   ★ gpt-oss-120b  ──fail──▶  compound-mini  ──fail──▶  qwen-3.8-27b  ──fail──▶  Gemini
       (active)                  (backup)                (backup)              (last resort)
```

- 4 nodes left-to-right, each ~160px wide, ~110px tall.
- **gpt-oss-120b** — indigo border, soft indigo fill, indigo label — labeled "ACTIVE".
- **compound-mini**, **qwen-3.8-27b** — white fill, gray border, muted text.
- **Gemini** — teal border, soft teal fill, teal label — labeled "DIFFERENT PROVIDER".
- Arrows between them: a thin red dashed arrow with a small "fail / 429"
  label above each one.
- Below the chain, a small caption in monospace:
  `gpt-oss-120b  →  compound-mini  →  qwen-3.8-27b  →  gemini-flash-lite-latest`
  (with the first model name bold, the last in teal, the middle two muted).

**Layout grid:**
- Total 800 × 200.
- 4 cards ~150px wide, ~110px tall, centered.
- 40px gaps with arrows in the middle.

---

## Output instructions

For each SVG:
1. Save with the exact filename in the same directory as `presentation.html`
   (`/home/sanzid/competitions/bup-hackathon/gridwise/video/`).
2. Use `viewBox="0 0 W H"` and `width="100%" height="auto"` so the HTML
   can scale them responsively.
3. No external font dependencies — use generic `font-family="Inter, system-ui, sans-serif"`.
4. Include `<title>` and `<desc>` elements for accessibility.
5. Validate by opening the SVG in a browser; it should look clean at
   1200px wide on an off-white background.
