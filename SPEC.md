# Song-profile reel pipeline — shared spec (all agents follow this)

Goal: fully local Python pipeline (Windows, Python 3.14 at `python`, ffmpeg 8 on PATH, node 24) that produces
Instagram reels that look **indistinguishable in style** from the reference reel:
`reference/reel.mp4` (frames in `reference/frames/`: `f_NN.png` = 1 fps, `t_<sec>.png` = sub-second early frames).

## Reference facts (measured)
- 1440x2560, 60 fps, H.264 + AAC 44.1k. Reference is 15.6 s; **ours = 30 s** (user requirement).
- Image: flat, painterly digital illustration, soft paper grain, warm caramel skin, faceless/hidden-eyes couple,
  solid deep maroon background (~#560006) with subtle texture, subject in lower ~65%, big empty space on top.
- Motion: piecewise-linear camera move (zoom+drift) changing direction at lyric changes; see src/render.py.
- Lyrics: ONE line at a time, centred, at ~y=21% of height (≈ y 543 on 2560, x≈740), cream/off-white (~#EAD6CF),
  thin monoline handwritten pen font, ALL CAPS with wide letter-spacing, **but every letter i stays lowercase**
  ("BHi", "TERi", "ZiDDi"). Cap height ≈ 40–45 px at 1440 wide. Line changes are synced to the singing.
- Language: Roman-script Hinglish lyrics (e.g. "THODA SA ZiDDi HOON").

## Layout
```
src/gemini.py        shared REST client (DONE — use it: generate(), text_of(), parse_json(), upload_file(), list_models())
src/song.py          [audio agent]  pick song, yt-dlp download, Gemini 30 s segment + timed Hinglish lyrics, cut audio
src/image_gen.py     [image agent]  Gemini scene prompt + Nano Banana image -> 1440x2560 PNG
src/render.py        [render agent] zoom + lyric overlay + mux -> final MP4
src/instagram.py     [publish agent] Graph API reel upload (off unless IG_USER_ID/IG_ACCESS_TOKEN set)
src/caption.py       [publish agent] Instagram caption + hashtags via Gemini
make_reel.py         [publish agent] orchestrator: `python make_reel.py [--count N] [--song "name"] [--post]`
fonts/               lyric font(s), OFL/free only, stored locally
work/<run_id>/       intermediates; output/<run_id>.mp4 + output/<run_id>.txt (caption)
history.json         songs already used (avoid repeats)
```

## Data contracts (JSON-serialisable dicts)
song = {"title": str, "artist": str, "film": str|None, "year": int|None, "mood": str,
        "youtube_query": str}
segment = {"audio_path": "work/<id>/clip.m4a", "duration": 30.0,
           "source_start": float, "source_end": float,
           "lines": [{"text": "THODA SA ZiDDi HOON", "start": 1.20, "end": 3.85}, ...]}   # times relative to clip
           (text already formatted: uppercase with lowercase i)
image  = "work/<id>/image.png"  (1440x2560 or larger, same 9:16)
render_video(image_path, segment, out_path) -> out_path

Each module exposes a function for the orchestrator + a `if __name__ == '__main__'` CLI for standalone testing.

## Gemini rules
- Key: `.env` GEMINI_API_KEY (already present). Never print/log it.
- Call `list_models()` once to pick the best currently available models (prefer newest pro for lyrics/audio,
  newest image model for "Nano Banana" e.g. gemini-*-image / *-image-preview), keep a fallback list.
- Lyrics MUST come from Gemini listening to the actual audio (Files API upload), not from Whisper.

## Quality bar
Every agent verifies its own output visually/aurally against the reference (Read the PNGs, extract frames)
before reporting. Report honestly what does not match yet.
