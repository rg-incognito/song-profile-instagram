# Song-profile Instagram reels

A local Python pipeline that makes 30-second Hindi song-lyric reels: a painterly couple illustration with a
slow push-in, one handwritten lyric line at a time synced to the singing, and the song in the audio track.
It can post the reels to Instagram on its own. Style target: `reference/reel.mp4` (see `SPEC.md`).

## Pipeline

```
history.json ─┐
              ▼
  song.pick_song ──► song.download_audio ──► song.select_segment ──► segment.json + clip.m4a (30 s,
  (Gemini, avoids     (yt-dlp, official        (Gemini listens to the       timed Hinglish lyrics)
   used songs)         audio, cached)           audio, picks the hook)            │
              │                                                                    │
              └──► image_gen.generate_image ──► image.png (1440x2560)              │
                   (Gemini scene + Nano Banana)        │                           │
                                                       ▼                           ▼
                                      render.render_video ──► output/<run_id>.mp4 (1440x2560, 60 fps)
                                                       │
                          caption.make_caption ──► output/<run_id>.txt
                                                       │
                          qa.run_qa (ffprobe spec + volume + Gemini vision on 3 frames)
                                                       │ pass
                          instagram.publish_reel (only with --post and IG creds in .env)
                                                       │
                                                history.json += song
```

## Setup

1. Install Python 3.12+ (developed on 3.14) and ffmpeg/ffprobe, and put both on PATH:
   `winget install Gyan.FFmpeg.Essentials`.
2. Install the Python packages: `pip install -r requirements.txt`.
3. Create `.env` in the project root:
   ```
   GEMINI_API_KEY=...
   IG_USER_ID=          # optional, for --post
   IG_ACCESS_TOKEN=     # optional, for --post (see docs/INSTAGRAM_SETUP.md)
   ```

## Usage

```
python make_reel.py                         # one reel, Gemini picks an unused song
python make_reel.py --count 5               # batch; one failed reel doesn't stop the rest
python make_reel.py --song "Tum Hi Ho"      # a specific song
python make_reel.py --post                  # publish after QA passes (needs IG_* in .env)
python make_reel.py --dry-run --count 5     # only pick songs and print them
python make_reel.py --resume <run_id>       # continue a failed/QA-failed run, reusing its artifacts
python make_reel.py --keep-work             # keep work/<run_id>/ even after success
python make_reel.py --no-vision-qa          # skip the Gemini frame check (ffprobe checks still run)
```

Outputs:
- `output/<run_id>.mp4`: the reel.
- `output/<run_id>.txt`: the caption.
- `history.json`: songs already used, with QA and post status.
- `logs/YYYYMMDD.log`: per-step log with timings.

`run_id` is `YYYYMMDD-HHMMSS-<song-slug>`.

Intermediates go in `work/<run_id>/`: `song.json`, `segment.json`, `clip.m4a`, `image.png`, `qa.json` and
`run.json` (step timings and errors). The folder is kept when a run fails or fails QA, so `--resume` can
reuse whatever is already there. To redo a step, delete its file (for example `image.png`) and resume. To
re-render, also delete `output/<run_id>.mp4`.

### Running modules on their own

```
python src/song.py --song "Mere Naam Tu" --out work/test_audio
python src/image_gen.py ...
python src/render.py ...
python src/caption.py --title "Tum Hi Ho" --artist "Arijit Singh"
python src/qa.py output/<run_id>.mp4 [--segment work/<run_id>/segment.json] [--no-vision]
python src/instagram.py --check
python src/instagram.py output/<run_id>.mp4 --caption-file output/<run_id>.txt
```

## QA (blocks posting on failure)

`src/qa.py` checks the following:

- **Format:** 1440x2560, 60 fps, H.264 yuv420p, AAC at 48 kHz or less, duration 29.5 to 30.5 s.
- **Audio:** not silent. Mean volume must be above -45 dB, measured with ffmpeg `volumedetect`.
- **Instagram upload spec:** moov atom first (fixed automatically by a lossless remux), 25 Mbps or less,
  300 MB or less.
- **Visual (Gemini):** three frames taken at the middle of the first, middle and last lyric lines. Each must
  have legible lyric text that doesn't overlap a face, with no garbled letters and no stray text in the art.
  If the vision check can't run, QA fails.

## Notes

- Reels posted through the API can't use Instagram's music library. The song is mixed into the video's own
  audio instead.
- Keys are read from `.env` and are never printed. `.env`, `work/`, `output/`, `songs_cache/` and `logs/`
  are git-ignored.

## Free-tier mode (default)
- Images: Gemini web app in the pipeline Chrome profile (`chrome_profile/`, Plus account) - no API quota used.
- Text/audio: free `GEMINI_API_KEY` (~20 requests/model/day). Every call walks one shared ranking
  (`gemini.ranked_models()`: pro -> flash -> flash-lite, newest first) and moves down a model as soon as a
  model's quota is gone. When every model is exhausted the batch stops and prints
  `python make_reel.py --resume <run_id>`; the quota resets at midnight Pacific (~1:30 PM IST).
- A reel whose vision QA could not run is never auto-posted.
