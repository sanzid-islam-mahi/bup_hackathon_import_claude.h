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
>     indigo       #4f46e5    primary accent (OpenAI / primary)
>     violet       #7c3aed    OpenAI secondary (gpt-4o-mini)
>     teal         #0d9488    success / Gemini
>     amber        #d97706    Groq chain / highlight
>     paper        #f7f5f0    background (transparent — don't fill)
>     card         #ffffff    card fills (only when needed for contrast)
>     border       #e5e0d5    soft borders
>     red          #dc2626    fail / 429 arrows
> - Sans-serif labels (Inter or system-ui). Monospace for code-style tags.
> - No gradients, no drop shadows beyond a single very soft one.
> - Stroke widths: 1.5px for outlines, 2px for emphasis.
> - Each visual should "read" at 1280×720 inside a slide.

---

## 1. `pipeline.svg` — 1200 × 380

**Use case:** Goes on slide 3 ("Architecture"). Shows the flow of a single
request through the system, with the multi-provider LLM chain highlighted
as the heart.

**Composition (left to right):**

```
[ Request ] → [ Validate ] → ★ [ LLM Chain ] ★ → [ Guard ] → [ LP Solve ] → [ Response ]
                                          ↓
                                (illustrated fallback branch)
```

- **Request** — small rounded rect with a JSON snippet icon, label "ingest".
- **Validate** — rounded rect with a checkmark icon, label "pydantic".
- **LLM Chain** — emphasized card (indigo border, soft indigo fill #eef2ff).
  Inside, **6 model pills stacked** in two visual groups:

  Group A — OpenAI (indigo / violet, with a small "PRIMARY" pill above):
  - `gpt-4.1-mini`  (indigo, filled — **active**)
  - `gpt-4o-mini`   (violet, outlined — OpenAI backup)

  Group B — Groq + Gemini (amber / teal, with a small "FALLBACK" pill above):
  - `gpt-oss-120b`   (amber outlined)
  - `compound-mini`  (amber outlined)
  - `qwen-3.8-27b`   (amber outlined)
  - `gemini-flash-lite-latest`  (teal filled)

  A thin curved arrow loops from the bottom pill back to `gpt-4.1-mini`,
  labeled "rotate on 429 / 5xx".

- **Guard** — rounded rect with a shield icon, label "safe-fail → no_op".
- **LP Solve** — rounded rect with a math-y icon (matrix or sigma),
  label "HiGHS · ~20 ms".
- **Response** — rounded rect with `{ }` braces, label "JSON 200".
- All connected by thin indigo arrows with arrowheads.
- Below the LLM Chain card, a dotted secondary arrow labeled "fallback heuristic" pointing to "LP Solve" (showing that if the LP is infeasible, the heuristic kicks in).
- Small caption beneath: "Each stage has a safety net."

**Layout grid:**
- Total width 1200, height 380.
- 6 cards in a row, each ~150 px wide, ~110 px tall, centered vertically.
- 30 px gap between cards, arrows in the gaps.
- LLM Chain card is wider (~220 px) and taller (~190 px) to fit the 6 model pills.
- Pills inside the chain card: ~150 px wide, ~18 px tall, 4 px vertical gap.

---

## 2. `chain.svg` — 900 × 220

**Use case:** Goes on slide 5 ("Resilience"). Visualizes the 6-model
failover chain across **three providers** (OpenAI / Groq / Gemini).

**Composition:**

```
   ┌──────────── OPENAI ────────────┐    ┌──── GROQ ────┐    ┌─ GEMINI ─┐
   │ ★ gpt-4.1-mini → gpt-4o-mini   │ →  │ gpt-oss-120b │ →  │ gemini   │
   │            ACTIVE              │    │ compound-mini│    │ different│
   └────────────────────────────────┘    │ qwen-3.8-27b │    │ provider │
                                         └──────────────┘    └──────────┘
```

- **4 visible nodes** left-to-right, but visually grouped into the three
  provider clusters above. Each cluster is a soft-bordered rounded rect
  with a tiny provider label in the top-left corner.

  - **Node 1 (OpenAI cluster)** — two pills stacked: `gpt-4.1-mini` (filled
    indigo, **ACTIVE**) and `gpt-4o-mini` (violet outline). Cluster label
    "OPENAI · PRIMARY" in indigo.
  - **Node 2 (Groq cluster)** — three pills stacked: `gpt-oss-120b`,
    `compound-mini`, `qwen-3.8-27b` (all amber outlined, muted text).
    Cluster label "GROQ · FALLBACK" in amber.
  - **Node 3 (Gemini cluster)** — one pill: `gemini-flash-lite-latest`
    (teal filled). Cluster label "GEMINI · LAST RESORT" in teal.

- Arrows between clusters: a thin red dashed arrow with a small
  "fail / 429 / 5xx" label above each one.
- Below the chain, a small caption in monospace:
  `gpt-4.1-mini  →  gpt-4o-mini  →  gpt-oss-120b  →  compound-mini  →  qwen-3.8-27b  →  gemini-flash-lite-latest`
  (with the first model name bold indigo, the last in teal, the middle four muted).

**Layout grid:**
- Total 900 × 220.
- 3 clusters, each ~250 px wide, ~140 px tall, centered.
- 30 px gap between clusters with arrows in the middle.
- 8 px gap between pills inside a cluster.

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
   1200 px wide on an off-white background.

---

## Visual notes (do not skip)

- The **two-pill OpenAI cluster** is the most important visual change from
  the previous version — it shows the cherry-picked OpenAI primary tier
  that is what `app/llm.py` now prefers when `OPENAI_API_KEY` is set.
- The cluster header (e.g. "OPENAI · PRIMARY") must be a small uppercase
  monospace tag at the top-left corner of each cluster card.
- Do NOT collapse the OpenAI pills into the Groq cluster — keeping the
  provider separation is the entire point of this slide.
- The `→` between clusters must be the red dashed "fail / 429" arrow — that
  is what makes it read as failover rather than pipeline.
