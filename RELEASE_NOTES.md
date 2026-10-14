## v1.10.1

### Fixed
- **Long parts crashed Premiere Pro when imported.** Parts longer than about 1 h 40 min (a 2 h 09 min part was the one that showed it) opened fine in video players but made Premiere Pro quit while importing them. Newer ffmpeg builds write the MP4 header with a very fine time unit (1/720000 s instead of 1/1000 s), and on long parts the numbers in the edit list stop fitting in 32 bits, which Premiere's importer cannot handle. The app now always asks ffmpeg for the normal unit. Audio and video stay in sync, nothing is re-encoded, and the parts are the same size.
- A part that was already finished by yt-dlp with the wrong header is rewritten (stream copy, header only, a few seconds) instead of just being moved.

### Good to know
- Parts you already downloaded keep the problem. To fix one without downloading it again: `ffmpeg -i "part.mp4" -map 0 -c copy -movie_timescale 1000 "part-fixed.mp4"`
- MKV output is not affected.
