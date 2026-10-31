# Lyric font

**Used font:** `ShadowsIntoLight-Regular.ttf` — *Shadows Into Light* by Kimberly Geswein (Google Fonts),
licensed under the **SIL Open Font License 1.1** (full text: `OFL-ShadowsIntoLight.txt`). Free for commercial use,
can be bundled; not sold on its own.

## Why this one
The reference reel's lyrics are hand-lettered (Procreate/CapCut-style monoline pen): thin round-ended strokes
~3-4 px at 1440 wide, uppercase letters of uneven height (U ~31 px, H ~49 px, B ~57 px), narrow letters
(~22-30 px wide), lowercase dotted `i`, irregular `B`/`D`/`R`, wide even spacing.

~100 free handwriting fonts were downloaded into `candidates/` and rendered on the reference background at the
same size, spacing and colour (`work/render_test/sheet_*.png`, `sheet2_*.png`, `sheet3.png`). Shortlist:
Shadows Into Light, Shadows Into Light Two, Waiting for the Sunrise, Reenie Beanie, Edu SA Beginner, Gaegu Light,
Schoolbell, Annie Use Your Telescope. *Shadows Into Light* was the closest: same monoline weight (≈4 px at cap
height 44 without any outline tweak), same slightly wobbly pen construction, an irregular `B`/`R`, a plain
dotted lowercase `i`, and no cursive/italic slant. Others were too bold (Gochi Hand, Architects Daughter), too
regular/geometric (Patrick Hand, Delius, Mali), too condensed (Sue Ellen Francisco, Amatic SC) or too scratchy
(Reenie Beanie, Rock Salt).

## Tuning in `src/render.py` (to get from "close" to "same")
* Glyphs are placed by **ink bounds**: 13.5 px between letters, 61 px between words (measured on all 4
  reference lines: letter gaps 11-18 px, word gaps 55-70 px).
* Each letter is **condensed horizontally** to the letter widths measured in the reference (`WIDTH_TARGETS`;
  Shadows Into Light is ~25 % wider than the reference hand).
* Deterministic **hand jitter** per glyph (scale 0.93-1.09, baseline σ 0.9 px, rotation σ 1.6°), seeded by the
  line text, so letters have the uneven heights of real hand lettering.
* Stroke thickened by +0.5 px (FreeType stroker, round) -> ~4.3 px like the reference.
* Cap height 44 px, ink centred at y≈543 / x≈0.511·W of a 1440x2560 frame. Fill colour `#D6BCAC`
  (214,188,172): after H.264 4:2:0 chroma subsampling on the saturated maroon background, thin strokes read back as
  ~(226,186,178), which is what the reference measures (225,186,177).
