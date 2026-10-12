## v1.4.0

### Added
- **Search tab.** Find a VOD without leaving the app or copying links from Twitch:
  - Type a streamer name and press Enter. An exact channel name opens right away; otherwise pick one from the results (● marks channels that are live).
  - See their VODs with thumbnails, title, date, length and views. Switch between **Past broadcasts**, **Highlights** and **Uploads**, and press **Load more** for older ones.
  - Double-click a VOD (or press **Use this VOD**) to load it in the Plan tab, ready for cut points.
  - **Recent streamers**: the channels you open are remembered for next time (**Clear recent** empties the list).
  - Searching needs the Twitch sign-in. When you are not signed in, the tab shows a warning with a **Sign in…** button.
- **Scrolling.** Every tab now has a scrollbar (and mouse-wheel support) when the window is too short to show everything, so no option is hidden any more. The minimum window height is lower too.

### Notes
- Thumbnails are cached in the app's data folder (`cache/thumbs`), so repeat searches load fast.
- Running from source now also needs Pillow: `pip install requests pillow` (it is in `requirements.txt`). The packaged apps include it.
- Twitch deletes VODs after a while and some streamers do not save them, so older broadcasts may not appear.
