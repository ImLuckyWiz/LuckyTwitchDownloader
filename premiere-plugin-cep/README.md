# LuckyTwitch Markers: Premiere Pro panel (CEP edition)

The second Premiere Pro panel for LuckyTwitch Downloader. It reads the same `.markers.json` as the [UXP panel](../premiere-plugin) and does the whole edit of a Twitch VOD for you, in one button:

1. **adds the markers** (games and clips, colored) to the video,
2. **cuts** the timeline around every clip (with the padding you choose),
3. **deletes the gaps** between the clips (ripple delete, so the clips end up back to back),
4. **links** each video piece to its audio piece again,

and then **reads the whole result back** from Premiere and only says "done" if everything matches the plan.

Both panels stay in the project. Pick the one that suits you; they can even be installed side by side (different ids, different menu entries).

| | UXP panel (`premiere-plugin/`) | CEP panel (this folder) |
|---|---|---|
| Install | double-click the `.ccx` (Creative Cloud) | unzip, run the installer script, restart Premiere |
| Cutting | clone-and-trim (Premiere's UXP has no razor); needs empty tracks above the clip; makes a backup copy of the sequence first | **the real razor**; needs nothing above the clip; no backup copy (save the project first) |
| Speed | rounds of timeline edits | about 50 s for 110 markers, 199 cuts, 100 deletes and 100 links (measured on Premiere 26.5) |
| Timeline it accepts | any timeline, also one you already trimmed or cut | **one whole clip alone on V1/A1** (video + audio), or its own half-finished run; anything else is refused with the reason |
| Markers go | on the clip or on the sequence | on the clip (they follow your cuts) |
| After the delete | you check the result | **links video and audio again**, and reads the **whole result back** against the plan (pieces, sync, holes, length, links, markers) |

Choose CEP when you start from a fresh VOD on a fresh sequence and want the whole edit in one click. Choose UXP when you want the easy install, or the timeline is not a single clip any more.

## Install

Premiere's CEP panels are folders, not a single file like a `.ccx`. The installer copies the panel to the right place and switches on Adobe's "allow unsigned panels" flag (`PlayerDebugMode`, per user, harmless).

**Windows**
1. Unzip `LuckyTwitch-Premiere-Plugin-CEP.zip`.
2. Double-click **`install.bat`**. The window lists every file it installed.
3. Restart Premiere Pro and open **Window > Extensions > LuckyTwitch Markers**.

**macOS** (written to the same rules, but not yet tried on a real Mac: tell us if it does not work)
1. Unzip, then double-click **`install-mac.command`** (if macOS blocks it: right-click > Open, or run `bash install-mac.command` in Terminal).
2. Restart Premiere Pro and open **Window > Extensions > LuckyTwitch Markers**.

To remove it: `install.bat -Uninstall` (Windows) or `./install-mac.command --uninstall` (macOS). The installer also removes the panel's old test build (`com.luckytwitch.ceptest`) if you had it.

The manifest allows Premiere Pro 14.0 (2020) and newer; it was checked on Premiere Pro 26.5 on Windows only.

## Use

1. In LuckyTwitch Downloader tick **Also export a .markers.json for the LuckyTwitch Premiere plugin** (and **Also mark the game / category changes** if you want games), and download as usual.
2. In Premiere, make a **new sequence from the video** (video on V1, its audio on A1, nothing else) and **save the project (Ctrl+S)**.
3. Open the panel. It finds the `.markers.json` next to the video (or next to the project) by itself, reads the timeline, and shows **what will happen**: how many markers, cuts, deletes and links, and a rough time.
4. Press **Do it all**, confirm once, and leave Premiere alone until it says *Done*. The bar and the four rows show where it is.

If something is wrong the panel tells you before you press anything (the big button turns into *Check again*), and a run stops at the first failed check without retrying anything. If a run is stopped (Stop button, or a failed check), pressing the button again **continues where it stopped**: it works out what is left.

**Single steps** (collapsed under the button) run one part alone: only the markers, only the cuts, only the deletes, only the relink. **Detailed check (log)** prints every safety check without touching anything; **Remove the plan's markers** takes exactly the markers the plan adds off the clip again.

### Settings

| Setting | Meaning |
|---|---|
| Before / after each clip | seconds kept around every clip (the "safety cut"). 10 and 10 keeps 10 s before and after |
| Merge clips closer than | clips that touch after padding become one piece |
| Also cut at every game / category change | adds a cut at each game change |
| Also add the markers | the first step of Do it all. Markers can only be added **before the first cut** |
| Refuse to delete more than | the delete limit, in % of the timeline (default 99) |
| Need at least N pieces to keep | refuse if fewer would be left |

They are remembered. Keep them the same from the first cut to the delete: if you change the padding after cutting, the delete refuses (the cuts no longer match the plan); change it back, or undo.

### What it checks first (the failsafe)

It refuses to start, and says why, if: anything is on V2+/A2+; V1 or A1 is not exactly one whole clip (or a run of its own pieces); the clip is trimmed, sped up, or does not start at the start of the sequence; the audio is not the video's audio; the sequence uses drop-frame timecode; the markers file is for another video; or the delete plan is unsafe (more than the limit, or too few pieces left). Before every step it reads the timeline again, and after every chunk of work it checks the result.

## Troubleshooting

- **The panel is not in Window > Extensions:** restart Premiere after installing. Check that `%APPDATA%\Adobe\CEP\extensions\com.luckytwitch.markers` (macOS: `~/Library/Application Support/Adobe/CEP/extensions/com.luckytwitch.markers`) exists and that the installer said `manifest.xml OK`.
- **A run stopped:** open **Log** at the bottom, press **Copy log**, and read the last `[STOP]` / `check: FAIL` line. Nothing is retried by itself.
- **Undo:** Ctrl+Z undoes edits one by one; the saved project is untouched until you save again, so reopening it also works.
- **Debugger (optional):** with the panel open, `http://localhost:8099` in Chrome.

## For developers

See [`DEVELOPMENT.md`](DEVELOPMENT.md) (layout, tests, how the panel was verified). `src/markers-core.js` is **the UXP plugin's file, byte for byte**: never edit it here (a test fails if the two differ). Tests: `cd premiere-plugin-cep && npm test` (Node 20+, no dependencies).
