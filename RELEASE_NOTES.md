## v1.11.0

A redesign of the rest of the app, to match the new Options tab from v1.10. Nothing was removed and nothing works differently: saved settings, the queue and the files the app writes are the same as before.

### Search tab
- When you are not signed in, a purple banner says so and has a **Sign in...** button. Searching is switched off until you sign in.
- Every list explains itself while it is empty: what to do first, "nothing found for ..." after a search with no results, "this streamer has no VODs" with the reason, and "loading..." while a page is being fetched.
- The VOD header counts the videos (and says when there are more to load). "Double-click a VOD to use it" now sits next to the **Use this VOD** button.
- Results and Recent streamers are cards. Column headings line up with their columns.
- At the smallest window size the title above the VOD list wraps instead of squeezing the video-type drop-down.

### Plan tab
- The page is three cards: **Timeline**, **Cut points** and **Clips -> chapters**.
- The chapters option is a switch, like the ones in Options (the last checkbox in the app is gone).
- The **Add to queue** buttons and the one-line summary of your cuts stay visible at the bottom while you scroll. The summary turns red only while the cuts are wrong.
- Hints wrap to the width of their card, and the chapter column is wide enough for its title.
- The timeline's help line wraps instead of being cut off at the smallest window size.
- Keyboard: Tab now goes through the Plan tab from top to bottom and ends on **Add to queue**, then **Add & start** (before, the bottom bar came first).

### Queue & log tab
- Each job is coloured by its status, with a small icon in front: grey `○ queued`, purple `▶ running...`, green `✓ done (3 files)`, red `✕ failed`, amber `■ cancelled`.
- A one-line count sits above the list, for example "1 running · 2 queued · 1 done · 1 failed".
- An empty queue says "Nothing in the queue yet" and has a **Go to the Plan tab** button.
- The log is coloured: errors red, warnings amber, successes green, timestamps and "Queued:" lines muted.
- New **Copy log** and **Clear log** buttons under the log, handy for bug reports.
