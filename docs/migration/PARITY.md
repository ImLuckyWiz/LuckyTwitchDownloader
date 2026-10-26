# PARITY: behaviours to keep in the Qt app

One section per screen. Built in Phase 0 from the tkinter source (v1.16.0) and from the names of the GUI tests, which are the best index of behaviour. Tick a box when the behaviour is ported **and** a Qt test covers it. A box that cannot be ported as is gets an entry in `MIGRATION_LOG.md` instead.

How to read it: each box is one test of the tkinter suite (name in words, test id below it). The `Structure` text under each heading comes from reading the source; it lists what is on the screen and the exact texts. It is a starting point: the phase that ports a screen re-reads that screen's source and adds anything missing here before writing code.

Tests that need no GUI (engine, planning, naming, weblink, Premiere JSON) are not listed here: they test code that does not change.

| Screen | Phase | tkinter GUI tests |
| --- | --- | --- |
| Search tab and Twitch sign-in dialog | Phase 4 | 18 |
| Queue and log tab | Phase 3 | 41 |
| Plan tab (without the timeline), Get info, links | Phase 6 | 57 |
| Timeline | Phase 7 (7a to 7e) | 57 |
| Options tab | Phase 5 | 40 |
| Theme, icon and widgets | Phases 1 and 2 | 13 |
| Window, focus and tab order | Phase 1 (window), all phases (tab order) | 6 |
| Timeline, muted-audio file | Phase 7 | 3 |
| **Total** | | **235** |

Unique test functions are listed once even when parametrised; the count column counts every parametrised case, as pytest does.

Three more tkinter tests live in `tests/test_muted_audio.py` (after its `importorskip("tkinter")`); they belong to the Timeline section and are listed there. `tests/conftest.py` only puts the project root on `sys.path`; the `gui` fixtures are defined inside each `test_gui_*.py` file (and in `test_muted_audio.py`), so check them when porting each screen.

## Search tab and Twitch sign-in dialog  (Phase 4)

**Structure (from `build_search_tab`, `ask_credentials`):**
- Top row: label `Streamer:`, text entry (Enter searches), `Search` (Accent) button.
- Sign-in bar under it (shown when there is no client): text `Sign in with Twitch to search streamers and list their VODs.` and an Accent `Sign in…` button.
- Left column: cards with channel lists (Treeview, no headings, single selection, select = load that channel's VODs): search results, and recent streamers with a `Clear recent` (Ghost) button. Recent list: `luckytwitch_recent.json`, newest first, at most `MAX_RECENT` (12).
- Right column: heading (title of the loaded channel), a read-only combobox of video kinds (`VIDEO_KINDS`), the VOD table (tree + columns title, date, duration, views, with thumbnails, tall rows, vertical scrollbar), empty-state text over the table, buttons `Load more` (disabled until there is a cursor), `Use this VOD` (Accent), hint `Double-click a VOD to use it`. Double-click or Enter on a row uses the VOD.
- Thumbnails: 4 daemon workers; arrive by message (`on_thumb`, generation counter drops stale ones). Without Pillow: the log says `Pillow is not installed: thumbnails are disabled in the Search tab (pip install pillow).`
- Message boxes: `Search` (error, search and video-list failures), `Select a VOD` (info, `Select a VOD in the list first.`).
- Sign-in dialog (`Twitch API…` button in the top bar, `Sign in…` in the search tab): text about the optional use for clips; status line, device code in large mono bold accent text; buttons `Sign in with Twitch`, `Open page again`, `Sign out`; group `Advanced: use your own Twitch app instead` with `Client ID:` and `Client Secret:` (masked) entries and `Save own app`; line `Saved in: <config path>`; `Close`. Message boxes (parent = dialog): `Twitch sign-in` error, `Missing data` (`Fill in both fields.`), `Error`, `Network error`. Login runs in a worker, a `pump` on the GUI thread polls its result.


**Phase 4 (Qt) notes.** Where the Qt code is: `qt_ui/tabs/search.py` (tab), `qt_ui/search_models.py` (`ChannelModel`, `VodModel`, `ThumbCache`, `ThumbDelegate`), `qt_ui/thumbs.py` (4 worker threads), `qt_ui/twitch_dialog.py` (dialog), `core/search.py` (constants). The window owns the Twitch client (`MainWindow.client`; setting it refreshes the Search tab). The old messages are `Bridge.search_ok`, `search_err`, `videos_ok`, `videos_err`, `thumb`; the dialog's own four (code, ok, error, cancelled) are `LoginSignals` on the dialog. Differences are in `MIGRATION_LOG.md` no. 8 to 12.

Extra Qt tests beyond the 18 (all in `test_qt_search_tab.py` unless noted): a search runs in a worker and fills the list; Enter searches; empty query, no session; exact login match opens the streamer; failed search and expired session; picking from one list clears the other; a new streamer bumps the generation and empties the table; a slow answer for the first of two streamers is dropped (real threads); the kind drop-down reloads without touching the recent list; Load more with the cursor; recent list order, cap of 12, saved file; double click, Enter and the message box of «Use this VOD»; the window hands the link to the entry and «Get info»; thumbnails (fetched off the GUI thread, pixmaps on it, painted by the delegate, stale and unreadable ones, cache cap, workers start lazily and stop); and in `test_qt_twitch_dialog.py` (37): every text, the three status states, the whole device-code flow with a fake API and with the real engine functions over fake HTTP, errors, cancel, closing in each way, late answers dropped, sign out, own app (missing data, wrong credentials, network error, saved), and the dialog inside the main window.

#### `test_gui_search_tab.py` (18 tests)

- [x] without a session the banner shows and searching is off  
  `test_gui_search_tab.py::test_without_a_session_the_banner_shows_and_searching_is_off` -> same name in `test_qt_search_tab.py`
- [x] signing in hides the banner and enables searching  
  `test_gui_search_tab.py::test_signing_in_hides_the_banner_and_enables_searching` -> same name in `test_qt_search_tab.py`
- [x] the banner button opens the sign in dialog  
  `test_gui_search_tab.py::test_the_banner_button_opens_the_sign_in_dialog` -> `test_qt_search_tab.py::test_the_banner_text_and_button`, `::test_the_banner_button_asks_for_the_sign_in_dialog`; the dialog opens: `test_qt_twitch_dialog.py::test_the_twitch_api_button_and_the_banner_open_the_dialog`
- [x] the lists start with a hint each  
  `test_gui_search_tab.py::test_the_lists_start_with_a_hint_each` -> same name in `test_qt_search_tab.py`
- [x] a search without results says what was searched  
  `test_gui_search_tab.py::test_a_search_without_results_says_what_was_searched` -> same name in `test_qt_search_tab.py`
- [x] search results replace the message and a new empty search brings it back  
  `test_gui_search_tab.py::test_search_results_replace_the_message_and_a_new_empty_search_brings_it_back` -> same name in `test_qt_search_tab.py`
- [x] recent streamers toggle their message and the clear button  
  `test_gui_search_tab.py::test_recent_streamers_toggle_their_message_and_the_clear_button` -> same name in `test_qt_search_tab.py`
- [x] vods hide the message and the header counts them  
  `test_gui_search_tab.py::test_vods_hide_the_message_and_the_header_counts_them` -> same name in `test_qt_search_tab.py`
- [x] the header says there is more and uses the singular  
  `test_gui_search_tab.py::test_the_header_says_there_is_more_and_uses_the_singular` -> same name in `test_qt_search_tab.py`
- [x] a streamer without vods gets an explanation  
  `test_gui_search_tab.py::test_a_streamer_without_vods_gets_an_explanation` -> same name in `test_qt_search_tab.py`
- [x] loading is announced and a failure ends it  
  `test_gui_search_tab.py::test_loading_is_announced_and_a_failure_ends_it` -> same name in `test_qt_search_tab.py`
- [x] an answer for an older streamer changes nothing  
  `test_gui_search_tab.py::test_an_answer_for_an_older_streamer_changes_nothing` -> same name in `test_qt_search_tab.py`
- [x] vod headings line up with their columns  
  `test_gui_search_tab.py::test_vod_headings_line_up_with_their_columns` -> same name in `test_qt_search_tab.py` (the model's heading alignment equals its cells' alignment)
- [x] the use hint sits next to the button and the header has no instruction  
  `test_gui_search_tab.py::test_the_use_hint_sits_next_to_the_button_and_the_header_has_no_instruction` -> same name in `test_qt_search_tab.py`
- [x] the streamer lists keep working as before  
  `test_gui_search_tab.py::test_the_streamer_lists_keep_working_as_before` -> same name in `test_qt_search_tab.py` (a QListView has no heading at all; the VOD table has the columns thumbnail, Title, Date, Length, Views)
- [x] empty state shows hides and refills  
  `test_gui_search_tab.py::test_empty_state_shows_hides_and_refills` -> same name in `test_qt_widgets.py` (Phase 2)
- [x] empty state can carry a button  
  `test_gui_search_tab.py::test_empty_state_can_carry_a_button` -> same name in `test_qt_widgets.py` (Phase 2)
- [x] empty state leaves room for the column headings  
  `test_gui_search_tab.py::test_empty_state_leaves_room_for_the_column_headings` -> same name in `test_qt_widgets.py` (Phase 2)

## Queue and log tab  (Phase 3)

**Structure (from `build_queue_tab`, `poll_queue`, `refresh_queue_summary`):**
- Card with a summary line (`queue_summary`), the job table (headings only, no tree column, vertical scrollbar, row tags coloured by status; icons `○ ▶ ✓ ✕ ■`), empty-state text over it.
- Buttons: `Start queue` (Accent), `Cancel current` (starts disabled), `Remove selected`, `Clear finished` (right side), `Open folder` (right side).
- Log card: read-only text with timestamps `[HH:MM:SS]`, coloured by `log_kind`, auto-scroll; `Copy log`, `Clear log`.
- Bottom of the window (all tabs): determinate progress bar and a status line (`set_progress`, `set_status`).
- Message boxes: `Running` (`Cancel the running job first.`), `Open folder`, `Error`, `Tools`, `Chat overlay`, `Quit` (yes/no, `A job is running. Cancel it and quit?`), `Busy`.
- Worker to GUI messages: tagged tuples through a queue, drained by `poll_queue` on a timer (to be replaced by Bridge signals, decision D3).
- Saved-chat overlay: `render_saved_chat` (file dialog, `Draw the chat overlay?` ok/cancel confirm with a summary).

#### `test_gui_queue_tab.py` (41 tests)

- [x] status word is the first word  
  `test_gui_queue_tab.py::test_status_word_is_the_first_word`
- [x] status label puts an icon in front of known statuses  
  `test_gui_queue_tab.py::test_status_label_puts_an_icon_in_front_of_known_statuses`
- [x] every status has an icon and a colour  
  `test_gui_queue_tab.py::test_every_status_has_an_icon_and_a_colour`
- [x] log lines are classified  
  `test_gui_queue_tab.py::test_log_lines_are_classified`
- [x] queue summary counts in a fixed order  
  `test_gui_queue_tab.py::test_queue_summary_counts_in_a_fixed_order`
- [x] the empty queue says what to do and the button goes to the plan tab  
  `test_gui_queue_tab.py::test_the_empty_queue_says_what_to_do_and_the_button_goes_to_the_plan_tab`
- [x] a queued job is listed with its icon colour and count  
  `test_gui_queue_tab.py::test_a_queued_job_is_listed_with_its_icon_colour_and_count`
- [x] a job changes colour and icon with its status  
  `test_gui_queue_tab.py::test_a_job_changes_colour_and_icon_with_its_status`
- [x] the row colours match the palette  
  `test_gui_queue_tab.py::test_the_row_colours_match_the_palette`
- [x] the summary follows every change of the queue  
  `test_gui_queue_tab.py::test_the_summary_follows_every_change_of_the_queue`
- [x] a running job cannot be removed  
  `test_gui_queue_tab.py::test_a_running_job_cannot_be_removed`
- [x] headings line up with their columns  
  `test_gui_queue_tab.py::test_headings_line_up_with_their_columns`
- [x] the queue still runs on the plain status words  
  `test_gui_queue_tab.py::test_the_queue_still_runs_on_the_plain_status_words`
- [x] a failing job is marked failed and logged in red  
  `test_gui_queue_tab.py::test_a_failing_job_is_marked_failed_and_logged_in_red`
- [x] log lines get a muted time stamp and a colour by kind  
  `test_gui_queue_tab.py::test_log_lines_get_a_muted_time_stamp_and_a_colour_by_kind`
- [x] the log is read only and follows the newest line  
  `test_gui_queue_tab.py::test_the_log_is_read_only_and_follows_the_newest_line`
- [x] clear log empties it  
  `test_gui_queue_tab.py::test_clear_log_empties_it`
- [x] copy log puts the text on the clipboard  
  `test_gui_queue_tab.py::test_copy_log_puts_the_text_on_the_clipboard`
- [x] the two sections are cards  
  `test_gui_queue_tab.py::test_the_two_sections_are_cards`

**Ported in Phase 3** (`tests/test_qt_queue_tab.py`; the tkinter test ids above map one to one onto Qt tests with the same names, the pure helpers are tested on `core/status.py`). Also covered there, from the plan and the source, though no tkinter test had them: cancelling a running job (the rest stays queued), a failing job does not stop the run, start with nothing queued, start while the tools or a chat overlay are busy, a second press while it runs, the queue tab opens when the queue starts, the `Job n/m` prefix, determinate and indeterminate progress, a whole run end to end, `Open folder` (selected item, last finished item, output folder, error box), closing (asks while a job runs, cancels, saves the settings, removes `BEAT_PATH`), workers touch the GUI only through signals.

## Plan tab (without the timeline), Get info, links  (Phase 6)

**Structure (from `ui/plan_tab.py`, `on_get_info`, `open_link`, and the baseline screenshots):**
- Top bar of the main window (all tabs): `VOD URL or ID:` entry (Enter = Get info), `Get info` (Accent, animated busy state), `Twitch API…`; muted info line under it (`No VOD loaded.` at start).
- Plan tab is a scrolling page with a fixed footer. Cards from the top:
  1. `Timeline`: buttons `−`, `+`, `Fit`, `Undo`, then the timeline strip (see the Timeline section) and its hint line.
  2. `Cut points`: multi-line cut text, hint `Boundaries in order, e.g.  0:00:00 - 0:30:00 - 1:30:00 - end   (end = end of the VOD).` plus the line about skipping a section with `;` or a new line, and a live preview (coloured by kind: ok, err, muted) listing each part and the plan (for example `→ download the full VOD once, then split it`).
  3. `Clips → chapters` (`Optional: put the VOD's clips in the files as chapters.`): a toggle `Add clips as chapters` (the `chapters` setting), the number fields `Min views`, `Min duration (s)`, `Top N by views (0 = all)`, `Lead-in (s)`, and the clip table (columns at, views, dur, title, creator, chap) with buttons `Split at selected clip` and `Download only selected clip`.
- Footer bar (always visible): the summary line (for example `3 parts · 2:00:00 in total`, red when the cut text is invalid), `Add to queue`, `Add & start` (Accent). Tab order ends with those two buttons, left to right (`test_gui_final_pass.py`).
- Message boxes: `Select a clip`, `Select one clip`, `No VOD`, `No offset`, `Can't split here`, `Cut points`, `Clip`, `Link`.
- Links (`weblink.py`, not to be changed): link listener thread, `poll_links`, `bring_to_front`, macOS launch URL event; Windows setting in Options > Tools with the message box `Links`.

#### `test_gui_plan_tab.py` (31 tests)

**Ported in Phase 6** (`tests/test_qt_plan_tab.py`; the tkinter test names below map one-to-one onto Qt tests with the same names, plus extra tests for `Get info` running in a worker with animation, preview text colours, muted stretch overlap notes, and `Add to queue` / `Add & start`).

- [x] app uses the plan tab mixin  
  `test_gui_plan_tab.py::test_app_uses_the_plan_tab_mixin` -> `test_qt_plan_tab.py::test_window_has_the_plan_tab`
- [x] tabs are in the expected order  
  `test_gui_plan_tab.py::test_tabs_are_in_the_expected_order` -> same name in `test_qt_plan_tab.py`
- [x] plan tab has its widgets  
  `test_gui_plan_tab.py::test_plan_tab_has_its_widgets` -> same name in `test_qt_plan_tab.py`
- [x] preview empty hint  
  `test_gui_plan_tab.py::test_preview_empty_hint` -> same name in `test_qt_plan_tab.py`
- [x] preview end needs get info  
  `test_gui_plan_tab.py::test_preview_end_needs_get_info` -> same name in `test_qt_plan_tab.py`
- [x] preview lists the parts  
  `test_gui_plan_tab.py::test_preview_lists_the_parts` -> same name in `test_qt_plan_tab.py`
- [x] preview picks sections for small coverage  
  `test_gui_plan_tab.py::test_preview_picks_sections_for_small_coverage` -> same name in `test_qt_plan_tab.py`
- [x] preview follows the strategy option  
  `test_gui_plan_tab.py::test_preview_follows_the_strategy_option` -> same name in `test_qt_plan_tab.py`
- [x] preview shows errors  
  `test_gui_plan_tab.py::test_preview_shows_errors` -> same name in `test_qt_plan_tab.py`
- [x] typing in the box updates the preview  
  `test_gui_plan_tab.py::test_typing_in_the_box_updates_the_preview` -> same name in `test_qt_plan_tab.py`
- [x] build options reads the cut text from the tab  
  `test_gui_plan_tab.py::test_build_options_reads_the_cut_text_from_the_tab` -> same name in `test_qt_plan_tab.py`
- [x] clips table rows and label  
  `test_gui_plan_tab.py::test_clips_table_rows_and_label` -> same name in `test_qt_plan_tab.py`
- [x] clips table follows the filter and chapters switch  
  `test_gui_plan_tab.py::test_clips_table_follows_the_filter_and_chapters_switch` -> same name in `test_qt_plan_tab.py`
- [x] clips table empty messages  
  `test_gui_plan_tab.py::test_clips_table_empty_messages` -> same name in `test_qt_plan_tab.py`
- [x] double click target opens the clip url  
  `test_gui_plan_tab.py::test_double_click_target_opens_the_clip_url` -> same name in `test_qt_plan_tab.py`
- [x] split needs a selection  
  `test_gui_plan_tab.py::test_split_needs_a_selection` -> same name in `test_qt_plan_tab.py`
- [x] split needs exactly one clip  
  `test_gui_plan_tab.py::test_split_needs_exactly_one_clip` -> same name in `test_qt_plan_tab.py`
- [x] split needs a loaded vod  
  `test_gui_plan_tab.py::test_split_needs_a_loaded_vod` -> same name in `test_qt_plan_tab.py`
- [x] split needs a clip with a position  
  `test_gui_plan_tab.py::test_split_needs_a_clip_with_a_position` -> same name in `test_qt_plan_tab.py`
- [x] split inserts a cut point before the clip and refreshes the preview  
  `test_gui_plan_tab.py::test_split_inserts_a_cut_point_before_the_clip_and_refreshes_the_preview` -> same name in `test_qt_plan_tab.py`
- [x] split with empty text starts from the whole vod  
  `test_gui_plan_tab.py::test_split_with_empty_text_starts_from_the_whole_vod` -> same name in `test_qt_plan_tab.py`
- [x] split outside every part explains why  
  `test_gui_plan_tab.py::test_split_outside_every_part_explains_why` -> same name in `test_qt_plan_tab.py`
- [x] split respects the lead in setting  
  `test_gui_plan_tab.py::test_split_respects_the_lead_in_setting` -> same name in `test_qt_plan_tab.py`
- [x] splitting twice at the same clip keeps a valid plan  
  `test_gui_plan_tab.py::test_splitting_twice_at_the_same_clip_keeps_a_valid_plan` -> same name in `test_qt_plan_tab.py`
- [x] get info result fills the plan tab  
  `test_gui_plan_tab.py::test_get_info_result_fills_the_plan_tab` -> same name in `test_qt_plan_tab.py`
- [x] get info keeps cut points the user already typed  
  `test_gui_plan_tab.py::test_get_info_keeps_cut_points_the_user_already_typed` -> same name in `test_qt_plan_tab.py`
- [x] download selected clips queues one job per clip  
  `test_gui_plan_tab.py::test_download_selected_clips_queues_one_job_per_clip` -> same name in `test_qt_plan_tab.py`

#### `test_gui_plan_redesign.py` (10 tests)

- [x] the plan tab is a scroll page with a footer  
  `test_gui_plan_redesign.py::test_the_plan_tab_is_a_scroll_page_with_a_footer` -> same name in `test_qt_plan_tab.py`
- [x] the footer stays visible when the page scrolls  
  `test_gui_plan_redesign.py::test_the_footer_stays_visible_when_the_page_scrolls` -> same name in `test_qt_plan_tab.py`
- [x] the three sections are cards  
  `test_gui_plan_redesign.py::test_the_three_sections_are_cards` -> same name in `test_qt_plan_tab.py`
- [x] the chapters switch drives the clips table  
  `test_gui_plan_redesign.py::test_the_chapters_switch_drives_the_clips_table` -> same name in `test_qt_plan_tab.py`
- [x] the footer summary follows the cut points  
  `test_gui_plan_redesign.py::test_the_footer_summary_follows_the_cut_points` -> same name in `test_qt_plan_tab.py`
- [x] the summary is red only while the cuts are wrong  
  `test_gui_plan_redesign.py::test_the_summary_is_red_only_while_the_cuts_are_wrong` -> same name in `test_qt_plan_tab.py`
- [x] table headings line up with their columns  
  `test_gui_plan_redesign.py::test_table_headings_line_up_with_their_columns` -> same name in `test_qt_plan_tab.py`
- [x] the chapter column is wide enough for its title  
  `test_gui_plan_redesign.py::test_the_chapter_column_is_wide_enough_for_its_title` -> same name in `test_qt_plan_tab.py`
- [x] hints wrap to the width of their card  
  `test_gui_plan_redesign.py::test_hints_wrap_to_the_width_of_their_card` -> same name in `test_qt_plan_tab.py`
- [x] nothing on the plan tab is wider than the page  
  `test_gui_plan_redesign.py::test_nothing_on_the_plan_tab_is_wider_than_the_page` -> same name in `test_qt_plan_tab.py`

#### `test_gui_weblink.py` (16 tests)

- [x] a link fills the plan tab and reads the vod  
  `test_gui_weblink.py::test_a_link_fills_the_plan_tab_and_reads_the_vod` -> same name in `test_qt_plan_tab.py`
- [x] without cut points the default is the whole vod  
  `test_gui_weblink.py::test_without_cut_points_the_default_is_the_whole_vod` -> same name in `test_qt_plan_tab.py`
- [x] a link replaces the cut points that were there  
  `test_gui_weblink.py::test_a_link_replaces_the_cut_points_that_were_there` -> same name in `test_qt_plan_tab.py`
- [x] a link never adds to the queue or starts a download  
  `test_gui_weblink.py::test_a_link_never_adds_to_the_queue_or_starts_a_download` -> same name in `test_qt_plan_tab.py`
- [x] the previous vod is forgotten so its cuts cannot be reused  
  `test_gui_weblink.py::test_the_previous_vod_is_forgotten_so_its_cuts_cannot_be_reused` -> same name in `test_qt_plan_tab.py`
- [x] a bad link says why and changes nothing  
  `test_gui_weblink.py::test_a_bad_link_says_why_and_changes_nothing` -> same name in `test_qt_plan_tab.py`
- [x] a link waits while the tools are being prepared  
  `test_gui_weblink.py::test_a_link_waits_while_the_tools_are_being_prepared` -> same name in `test_qt_plan_tab.py`
- [x] a link left in the folder is picked up by the window  
  `test_gui_weblink.py::test_a_link_left_in_the_folder_is_picked_up_by_the_window` -> same name in `test_qt_plan_tab.py`
- [x] the window says it is alive and stops saying so when it closes  
  `test_gui_weblink.py::test_the_window_says_it_is_alive_and_stops_saying_so_when_it_closes` -> same name in `test_qt_plan_tab.py`
- [x] a second launch hands its link to the open window  
  `test_gui_weblink.py::test_a_second_launch_hands_its_link_to_the_open_window` -> same name in `test_qt_plan_tab.py`
- [x] the tools card shows the state of the links  
  `test_gui_weblink.py::test_the_tools_card_shows_the_state_of_the_links` -> `test_qt_options_tab.py::test_the_tools_card_shows_the_state_of_the_links` (Phase 5)
- [x] pressing the button registers and updates the card  
  `test_gui_weblink.py::test_pressing_the_button_registers_and_updates_the_card` -> `test_qt_options_tab.py::test_pressing_the_links_button_registers_and_updates_the_card` (Phase 5)
- [x] a refusal from the system is shown  
  `test_gui_weblink.py::test_a_refusal_from_the_system_is_shown` -> `test_qt_options_tab.py::test_a_refusal_from_the_system_is_shown` (Phase 5)
- [x] where the app cannot set itself up there is no button  
  `test_gui_weblink.py::test_where_the_app_cannot_set_itself_up_there_is_no_button` -> `test_qt_options_tab.py::test_where_the_app_cannot_set_itself_up_there_is_no_button` (Phase 5)

## Timeline  (Phase 7 (7a to 7e))

**Structure (from `ui/timeline.py`):** one custom canvas widget, rows from top: ruler, games bar (with a red muted stretch line), thumbnails, parts; cut lines (white), edge highlight, clip marks; hover preview of the frame; constants `EDGE_TOL_PX=6`, `SNAP_PX=6`, `PREVIEW_MAX_W=160`, `PADX=8`; `Viewport` (time to pixel, zoom 30 s to whole VOD, pan), `nice_step`, `game_colour`, `zone_at`. States: no VOD, loading frames, ready, unavailable, no storyboard, no Pillow, error text. Idle hint text in `IDLE_HINT`. The two tests that used to fail on `clip_start()` (600 vs 600.4) are fixed in this repo and pass.

#### `test_gui_timeline.py` (57 tests)

- [ ] viewport maps time to pixels and back  
  `test_gui_timeline.py::test_viewport_maps_time_to_pixels_and_back`
- [ ] zoom keeps the moment under the mouse in place  
  `test_gui_timeline.py::test_zoom_keeps_the_moment_under_the_mouse_in_place`
- [ ] zoom is limited to the whole vod and to 30 seconds  
  `test_gui_timeline.py::test_zoom_is_limited_to_the_whole_vod_and_to_30_seconds`
- [ ] panning stays inside the vod and fit resets  
  `test_gui_timeline.py::test_panning_stays_inside_the_vod_and_fit_resets`
- [ ] ruler step is the smallest round one that leaves room  
  `test_gui_timeline.py::test_ruler_step_is_the_smallest_round_one_that_leaves_room`
- [ ] a game always gets the same colour  
  `test_gui_timeline.py::test_a_game_always_gets_the_same_colour`
- [ ] rows of the widget are found by height  
  `test_gui_timeline.py::test_rows_of_the_widget_are_found_by_height`
- [ ] without a vod it says so and ignores the mouse  
  `test_gui_timeline.py::test_without_a_vod_it_says_so_and_ignores_the_mouse`
- [ ] clicking the thumbnails cuts there  
  `test_gui_timeline.py::test_clicking_the_thumbnails_cuts_there`
- [ ] cuts snap to game changes but only when close  
  `test_gui_timeline.py::test_cuts_snap_to_game_changes_but_only_when_close`
- [ ] cuts snap to clips too  
  `test_gui_timeline.py::test_cuts_snap_to_clips_too`
- [ ] clicking on a cut line grabs it instead of adding another  
  `test_gui_timeline.py::test_clicking_on_a_cut_line_grabs_it_instead_of_adding_another`
- [ ] dragging a cut line moves it and one undo takes the whole drag back  
  `test_gui_timeline.py::test_dragging_a_cut_line_moves_it_and_one_undo_takes_the_whole_drag_back`
- [ ] a cut line cannot be dragged past its neighbour  
  `test_gui_timeline.py::test_a_cut_line_cannot_be_dragged_past_its_neighbour`
- [ ] dragging the start of a part next to a skipped section  
  `test_gui_timeline.py::test_dragging_the_start_of_a_part_next_to_a_skipped_section`
- [ ] right click removes a cut line between two parts  
  `test_gui_timeline.py::test_right_click_removes_a_cut_line_between_two_parts`
- [ ] right click on the border of a skipped section explains instead  
  `test_gui_timeline.py::test_right_click_on_the_border_of_a_skipped_section_explains_instead`
- [ ] clicking a part skips it and clicking the gap brings it back  
  `test_gui_timeline.py::test_clicking_a_part_skips_it_and_clicking_the_gap_brings_it_back`
- [ ] the last remaining part cannot be skipped  
  `test_gui_timeline.py::test_the_last_remaining_part_cannot_be_skipped`
- [ ] clicking a skipped section in the thumbnails explains instead of cutting  
  `test_gui_timeline.py::test_clicking_a_skipped_section_in_the_thumbnails_explains_instead_of_cutting`
- [ ] an empty plan starts with the whole vod on a click  
  `test_gui_timeline.py::test_an_empty_plan_starts_with_the_whole_vod_on_a_click`
- [ ] double clicking a game makes it its own part  
  `test_gui_timeline.py::test_double_clicking_a_game_makes_it_its_own_part`
- [ ] shift double click keeps only that game  
  `test_gui_timeline.py::test_shift_double_click_keeps_only_that_game`
- [ ] double click outside the game row acts like a click  
  `test_gui_timeline.py::test_double_click_outside_the_game_row_acts_like_a_click`
- [ ] with an invalid cut text the timeline does not edit  
  `test_gui_timeline.py::test_with_an_invalid_cut_text_the_timeline_does_not_edit`
- [ ] mouse wheel zooms around the mouse and shift wheel moves  
  `test_gui_timeline.py::test_mouse_wheel_zooms_around_the_mouse_and_shift_wheel_moves`
- [ ] dragging the ruler pans a zoomed timeline  
  `test_gui_timeline.py::test_dragging_the_ruler_pans_a_zoomed_timeline`
- [ ] a new vod forgets the old one  
  `test_gui_timeline.py::test_a_new_vod_forgets_the_old_one`
- [ ] hovering names the time and the game  
  `test_gui_timeline.py::test_hovering_names_the_time_and_the_game`
- [ ] without game information the games row says so  
  `test_gui_timeline.py::test_without_game_information_the_games_row_says_so`
- [ ] thumbnails show loading then pictures  
  `test_gui_timeline.py::test_thumbnails_show_loading_then_pictures`
- [ ] zooming in shows more of the frames  
  `test_gui_timeline.py::test_zooming_in_shows_more_of_the_frames`
- [ ] frames that all failed say unavailable  
  `test_gui_timeline.py::test_frames_that_all_failed_say_unavailable`
- [ ] a vod without a storyboard says so  
  `test_gui_timeline.py::test_a_vod_without_a_storyboard_says_so`
- [ ] without pillow the timeline still works and says why  
  `test_gui_timeline.py::test_without_pillow_the_timeline_still_works_and_says_why`
- [ ] the hover preview appears only when the pictures are ready  
  `test_gui_timeline.py::test_the_hover_preview_appears_only_when_the_pictures_are_ready`
- [ ] skipped parts are dimmed in the thumbnails  
  `test_gui_timeline.py::test_skipped_parts_are_dimmed_in_the_thumbnails`
- [ ] the timeline sits above the cut points  
  `test_gui_timeline.py::test_the_timeline_sits_above_the_cut_points`
- [ ] loading a vod feeds the timeline  
  `test_gui_timeline.py::test_loading_a_vod_feeds_the_timeline`
- [ ] the timeline follows the cut text  
  `test_gui_timeline.py::test_the_timeline_follows_the_cut_text`
- [ ] a broken cut text switches the timeline to its error state  
  `test_gui_timeline.py::test_a_broken_cut_text_switches_the_timeline_to_its_error_state`
- [ ] an edit on the timeline rewrites the cut text and the preview  
  `test_gui_timeline.py::test_an_edit_on_the_timeline_rewrites_the_cut_text_and_the_preview`
- [ ] skipping the first part moves the start  
  `test_gui_timeline.py::test_skipping_the_first_part_moves_the_start`
- [ ] skipping a middle part writes a second line  
  `test_gui_timeline.py::test_skipping_a_middle_part_writes_a_second_line`
- [ ] the timeline and the text agree after a long series of edits  
  `test_gui_timeline.py::test_the_timeline_and_the_text_agree_after_a_long_series_of_edits`
- [ ] split at a clip updates the timeline and a second split changes nothing  
  `test_gui_timeline.py::test_split_at_a_clip_updates_the_timeline_and_a_second_split_changes_nothing`
- [ ] frames arrive in the background and reach the timeline  
  `test_gui_timeline.py::test_frames_arrive_in_the_background_and_reach_the_timeline`
- [ ] frames of a vod that was replaced are ignored  
  `test_gui_timeline.py::test_frames_of_a_vod_that_was_replaced_are_ignored`
- [ ] a crash while loading frames only costs the thumbnails  
  `test_gui_timeline.py::test_a_crash_while_loading_frames_only_costs_the_thumbnails`
- [ ] without pillow no frames are requested  
  `test_gui_timeline.py::test_without_pillow_no_frames_are_requested`
- [ ] a vod without game info or thumbnails still gets a working timeline  
  `test_gui_timeline.py::test_a_vod_without_game_info_or_thumbnails_still_gets_a_working_timeline`
- [ ] with no vod the timeline waits  
  `test_gui_timeline.py::test_with_no_vod_the_timeline_waits`
- [ ] refreshing the clips updates the marks without a vod change  
  `test_gui_timeline.py::test_refreshing_the_clips_updates_the_marks_without_a_vod_change`

#### `test_muted_audio.py` (3 tkinter tests)

- [ ] the timeline draws a red line for each muted stretch and says how much  
  `test_muted_audio.py::test_the_timeline_draws_a_red_line_for_each_muted_stretch_and_says_how_much`
- [ ] the red line can be switched off  
  `test_muted_audio.py::test_the_red_line_can_be_switched_off`
- [ ] a new vod forgets the old muted stretches  
  `test_muted_audio.py::test_a_new_vod_forgets_the_old_muted_stretches`

## Options tab  (Phase 5)

**Structure (from `ui/options_tab.py`):** side navigation on the left with sections `Output`, `Cuts`, `Chapters`, `Premiere Pro`, `Chat`, `Clips`, `Tools`; one scrolling section at a time on the right (scroll resets to the top when changing section); cards with a title and a hint, setting rows (title and one-line hint left, control right), collapsible `Advanced` areas, toggles (on/off switch), token chips for templates, live name examples (`refresh_name_examples`). All 38 keys are listed in `SETTINGS_KEYS.md`. Folder button uses a directory dialog (`pick_folder`). `Tools` section: auto-update toggle, update now, open tools folder, Windows link setting.

#### `test_gui_options_tab.py` (40 tests)

- [x] app uses the options tab mixin and the sidebar  
  `test_gui_options_tab.py::test_app_uses_the_options_tab_mixin_and_the_sidebar`  
  Qt: `test_qt_options_tab.py::test_the_sidebar_has_the_seven_sections_and_starts_on_output`
- [x] only one section is visible at a time  
  `test_gui_options_tab.py::test_only_one_section_is_visible_at_a_time`  
  Qt: `test_qt_options_tab.py::test_only_one_section_is_visible_at_a_time`
- [x] switching sections scrolls back to the top  
  `test_gui_options_tab.py::test_switching_sections_scrolls_back_to_the_top`  
  Qt: `test_qt_options_tab.py::test_switching_sections_scrolls_back_to_the_top`
- [x] arrow keys move through the sidebar  
  `test_gui_options_tab.py::test_arrow_keys_move_through_the_sidebar`  
  Qt: `test_qt_options_tab.py::test_arrow_keys_move_through_the_sidebar`
- [x] every old setting still has its variable and a control  
  `test_gui_options_tab.py::test_every_old_setting_still_has_its_variable_and_a_control`  
  Qt: `test_qt_options_tab.py::test_every_old_setting_has_a_control_bound_to_it`
- [x] booleans are switches not checkboxes  
  `test_gui_options_tab.py::test_booleans_are_switches_not_checkboxes`  
  Qt: `test_qt_options_tab.py::test_booleans_are_switches`, `test_qt_options_tab.py::test_numbers_are_spin_boxes_and_lists_are_combo_boxes`
- [x] the chapters switch stays in the plan tab  
  `test_gui_options_tab.py::test_the_chapters_switch_stays_in_the_plan_tab`  
  Qt: `test_every_old_setting_has_a_control_bound_to_it` (no Options control for `chapters`)
- [x] up front and advanced settings are split as agreed  
  `test_gui_options_tab.py::test_up_front_and_advanced_settings_are_split_as_agreed`  
  Qt: `test_qt_options_tab.py::test_up_front_and_advanced_settings_are_split_as_agreed`
- [x] chapters clips and tools have no advanced area  
  `test_gui_options_tab.py::test_chapters_clips_and_tools_have_no_advanced_area`  
  Qt: `test_qt_options_tab.py::test_chapters_clips_and_tools_have_no_advanced_area`
- [x] advanced starts collapsed and opens on click  
  `test_gui_options_tab.py::test_advanced_starts_collapsed_and_opens_on_click`  
  Qt: `test_qt_options_tab.py::test_advanced_starts_collapsed_and_opens_on_click`
- [x] a value inside a collapsed advanced area is still used  
  `test_gui_options_tab.py::test_a_value_inside_a_collapsed_advanced_area_is_still_used`  
  Qt: `test_qt_options_tab.py::test_a_value_inside_a_collapsed_advanced_area_is_still_used`
- [x] the chat overlay settings reach the options  
  `test_gui_options_tab.py::test_the_chat_overlay_settings_reach_the_options`  
  Qt: `test_qt_options_tab.py::test_the_chat_overlay_settings_reach_the_options`
- [x] the default overlay type is animation  
  `test_gui_options_tab.py::test_the_default_overlay_type_is_animation`  
  Qt: `test_qt_options_tab.py::test_the_default_overlay_type_is_animation`
- [x] a switch changes the setting and saves  
  `test_gui_options_tab.py::test_a_switch_changes_the_setting_and_saves`  
  Qt: `test_qt_options_tab.py::test_a_switch_writes_a_real_boolean_and_a_number_field_writes_a_string`, `test_qt_options_tab.py::test_the_settings_the_options_tab_edits_are_saved_when_the_window_closes`
- [x] the markers switches refresh the clips like the checkboxes did  
  `test_gui_options_tab.py::test_the_markers_switches_refresh_the_clips_like_the_checkboxes_did`  
  Qt: `test_qt_options_tab.py::test_the_premiere_switches_ask_for_a_clip_refresh_only_when_clicked`
- [x] clicking a chip inserts the token at the cursor  
  `test_gui_options_tab.py::test_clicking_a_chip_inserts_the_token_at_the_cursor`  
  Qt: `test_qt_options_tab.py::test_clicking_a_chip_inserts_the_token_at_the_cursor`
- [x] a chip replaces the selected text  
  `test_gui_options_tab.py::test_a_chip_replaces_the_selected_text`  
  Qt: `test_qt_options_tab.py::test_a_chip_replaces_the_selected_text`
- [x] every template field has chips for its tokens  
  `test_gui_options_tab.py::test_every_template_field_has_chips_for_its_tokens`  
  Qt: `test_qt_options_tab.py::test_every_template_field_has_chips_for_its_tokens`
- [x] examples use a sample vod until one is loaded then the real one  
  `test_gui_options_tab.py::test_examples_use_a_sample_vod_until_one_is_loaded_then_the_real_one`  
  Qt: `test_qt_options_tab.py::test_examples_use_a_sample_vod_until_one_is_loaded_then_the_real_one`
- [x] the example line follows the template as you type  
  `test_gui_options_tab.py::test_the_example_line_follows_the_template_as_you_type`  
  Qt: `test_qt_options_tab.py::test_the_example_line_follows_the_template_and_the_format_as_you_type`
- [x] a half typed template never breaks the example  
  `test_gui_options_tab.py::test_a_half_typed_template_never_breaks_the_example`  
  Qt: `test_qt_options_tab.py::test_a_half_typed_template_never_breaks_the_example`, `test_core_options.py::test_a_half_typed_template_never_raises`
- [x] the example matches what the engine really names the file  
  `test_gui_options_tab.py::test_the_example_matches_what_the_engine_really_names_the_file`  
  Qt: `test_qt_options_tab.py::test_the_example_matches_what_the_engine_really_names_the_file`
- [x] clip and chapter examples  
  `test_gui_options_tab.py::test_clip_and_chapter_examples`  
  Qt: `test_qt_options_tab.py::test_clip_and_chapter_examples`
- [x] turning subfolders off greys out the stream folder field  
  `test_gui_options_tab.py::test_turning_subfolders_off_greys_out_the_stream_folder_field`  
  Qt: `test_qt_options_tab.py::test_turning_subfolders_off_greys_out_the_stream_folder_field`, `test_qt_options_tab.py::test_a_saved_file_with_subfolders_off_starts_with_the_field_greyed_out`
- [x] tools status is still driven by the apps message loop  
  `test_gui_options_tab.py::test_tools_status_is_still_driven_by_the_apps_message_loop`  
  Qt: `test_qt_options_tab.py::test_the_tools_text_comes_from_the_window_and_the_button_follows_the_busy_state`, `test_qt_options_tab.py::test_the_tools_setup_runs_in_the_background_and_gives_the_controls_back`
- [ ] the scroll frame is still importable from the main module  
  `test_gui_options_tab.py::test_the_scroll_frame_is_still_importable_from_the_main_module`  
  Qt: no counterpart (a tkinter import detail of the old main module); stays open, drop it at cutover.
- [x] opening advanced makes the page scroll to the new content  
  `test_gui_options_tab.py::test_opening_advanced_makes_the_page_scroll_to_the_new_content`  
  Qt: `test_qt_widgets.py::test_opening_advanced_makes_the_page_scroll_to_the_new_content` (Phase 2)
- [x] the saved chat button is in the chat section up front  
  `test_gui_options_tab.py::test_the_saved_chat_button_is_in_the_chat_section_up_front`  
  Qt: `test_qt_options_tab.py::test_the_saved_chat_button_is_in_the_chat_section_up_front`
- [x] choosing a chat asks for confirmation with what it will do  
  `test_gui_options_tab.py::test_choosing_a_chat_asks_for_confirmation_with_what_it_will_do`  
  Qt: `test_qt_options_tab.py::test_choosing_a_chat_asks_for_confirmation_with_what_it_will_do`
- [x] cancelling the file dialog does nothing  
  `test_gui_options_tab.py::test_cancelling_the_file_dialog_does_nothing`  
  Qt: `test_qt_options_tab.py::test_cancelling_the_file_dialog_does_nothing`
- [x] a file that is not a chat shows why and starts nothing  
  `test_gui_options_tab.py::test_a_file_that_is_not_a_chat_shows_why_and_starts_nothing`  
  Qt: `test_qt_options_tab.py::test_a_file_that_is_not_a_chat_shows_why_and_starts_nothing`
- [x] the file dialog opens in the output folder  
  `test_gui_options_tab.py::test_the_file_dialog_opens_in_the_output_folder`  
  Qt: `test_qt_options_tab.py::test_the_file_dialog_opens_in_the_output_folder`
- [x] drawing a saved chat runs in the background and gives the controls back  
  `test_gui_options_tab.py::test_drawing_a_saved_chat_runs_in_the_background_and_gives_the_controls_back`  
  Qt: `test_qt_options_tab.py::test_drawing_a_saved_chat_runs_in_the_background_and_gives_the_controls_back`
- [x] a failed render shows the reason and frees the controls  
  `test_gui_options_tab.py::test_a_failed_render_shows_the_reason_and_frees_the_controls`  
  Qt: `test_qt_options_tab.py::test_a_failed_render_shows_the_reason_and_frees_the_controls`
- [x] cancelling a saved chat render is quiet  
  `test_gui_options_tab.py::test_cancelling_a_saved_chat_render_is_quiet`  
  Qt: `test_qt_options_tab.py::test_cancelling_a_saved_chat_render_is_quiet`, `test_qt_options_tab.py::test_cancel_current_stops_a_chat_overlay`
- [x] only one thing runs at a time  
  `test_gui_options_tab.py::test_only_one_thing_runs_at_a_time`  
  Qt: `test_qt_options_tab.py::test_only_one_thing_runs_at_a_time`
- [x] the queue does not start while an overlay is being drawn  
  `test_gui_options_tab.py::test_the_queue_does_not_start_while_an_overlay_is_being_drawn`  
  Qt: `test_drawing_a_saved_chat_runs_in_the_background_and_gives_the_controls_back` (Start disabled), `test_qt_queue_tab.py::test_the_window_gives_the_two_busy_reasons`

## Theme, icon and widgets  (Phases 1 and 2)

**Structure (from `ui/theme.py`, `ui/widgets.py`, `ui/common.py`):** dark palette with purple accent `#9146ff`; flat buttons (Accent, Ghost, Card variants) with hover and pressed states; focus outline; rounded checkboxes; slim scrollbars; flat tabs; font size 10; window and taskbar icon from `assets/` (Windows AppUserModelID); dark title bar on Windows (`dark_titlebar`). Widgets to rebuild: `Toggle`, `Tooltip` and info icon, `Card`, `SettingRow`, `ScrollFrame`, `ScrollPage`, `SideNav`, `Collapsible`, `TokenChips`, `EmptyState`.

#### `test_gui_theme_and_icon.py` (13 tests)

Phase 1 ported the first four (Qt tests: `test_qt_theme.py::test_icon_files_are_where_the_qt_app_looks_for_them`, `test_set_app_icon_installs_an_icon`, `test_set_app_icon_is_silent_when_the_files_are_missing`; `core/resources.py` is covered by `test_core_helpers.py::test_resource_path_points_into_the_project`). The "build scripts use the icon" test is about the packaging scripts (Phase 8); the rest are the widget kit (Phase 2, done: `tests/test_qt_widgets.py`, 92 tests). "Checkbutton still toggles with the custom indicator" is NOT ported in Phase 2: check boxes are not part of the Phase 2 widget list; the Qt check box gets its look in the first phase that uses one (Phase 4 or 5). Also done in Phase 1, without a tkinter counterpart: palette tokens equal `ui/common.py`, the QSS parses without Qt warnings.

- [x] icon files exist and have the sizes windows needs  
  `test_gui_theme_and_icon.py::test_icon_files_exist_and_have_the_sizes_windows_needs`
- [x] resource path points into the project  
  `test_gui_theme_and_icon.py::test_resource_path_points_into_the_project`
- [x] set app icon installs an icon and never raises  
  `test_gui_theme_and_icon.py::test_set_app_icon_installs_an_icon_and_never_raises`
- [x] set app icon is silent when the files are missing  
  `test_gui_theme_and_icon.py::test_set_app_icon_is_silent_when_the_files_are_missing`
- [ ] build scripts use the icon  
  `test_gui_theme_and_icon.py::test_build_scripts_use_the_icon`
- [x] theme defines the styles the ui uses  
  `test_gui_theme_and_icon.py::test_theme_defines_the_styles_the_ui_uses`  
  Qt: `test_qt_widgets.py::test_the_stylesheet_has_the_rules_of_the_widget_kit`, `::test_a_card_is_a_bordered_surface`, `::test_the_selected_entry_is_purple_tinted_and_the_others_flat`, `::test_chips_are_small_flat_buttons`
- [ ] checkbutton still toggles with the custom indicator  
  `test_gui_theme_and_icon.py::test_checkbutton_still_toggles_with_the_custom_indicator`
- [x] toggle follows the variable and the user  
  `test_gui_theme_and_icon.py::test_toggle_follows_the_variable_and_the_user`  
  Qt: `test_qt_widgets.py::test_a_click_flips_the_toggle_and_runs_the_command_once`, `::test_setting_the_value_from_code_follows_without_running_the_command`
- [x] toggle works with int variables too  
  `test_gui_theme_and_icon.py::test_toggle_works_with_int_variables_too`  
  Qt: `test_qt_widgets.py::test_a_toggle_starts_in_the_state_it_was_given` (a Qt toggle holds a bool; int/BooleanVar variables go with the SettingsBinder, Phase 5)`
- [x] disabled toggle ignores clicks  
  `test_gui_theme_and_icon.py::test_disabled_toggle_ignores_clicks`  
  Qt: `test_qt_widgets.py::test_a_disabled_toggle_ignores_clicks_and_keys`
- [x] destroying a toggle removes its trace  
  `test_gui_theme_and_icon.py::test_destroying_a_toggle_removes_its_trace`  
  Qt: `test_qt_widgets.py::test_destroying_a_toggle_in_the_middle_of_its_animation_is_harmless`
- [x] tooltip shows and hides  
  `test_gui_theme_and_icon.py::test_tooltip_shows_and_hides`  
  Qt: `test_qt_widgets.py::test_a_tooltip_shows_and_hides`
- [x] card collects setting rows  
  `test_gui_theme_and_icon.py::test_card_collects_setting_rows`  
  Qt: `test_qt_widgets.py::test_a_card_collects_setting_rows`

Widget behaviours that the tkinter tests check in other files (the screens that use them tick their own boxes in their phases; the widget part is covered in Phase 2 by `tests/test_qt_widgets.py`):

- [x] sidebar: Up/Down move the selection and stop at the ends (`test_gui_options_tab.py::test_arrow_keys_move_through_the_sidebar`) -> `test_arrow_keys_move_through_the_sidebar`, `test_the_arrow_keys_move_the_focus_with_the_selection`, `test_every_entry_is_a_tab_stop_and_space_picks_it`; selected entry tinted -> `test_the_selected_entry_is_purple_tinted_and_the_others_flat`
- [x] Advanced starts collapsed, opens and closes on click, arrow and text of the header (`test_advanced_starts_collapsed_and_opens_on_click`) -> same name in `test_qt_widgets.py`; opening it makes the page scroll (`test_opening_advanced_makes_the_page_scroll_to_the_new_content`) -> same name
- [x] chips insert at the cursor and replace a selection (`test_clicking_a_chip_inserts_the_token_at_the_cursor`, `test_a_chip_replaces_the_selected_text`) -> same names, plus a real mouse click and the disabled / read-only field
- [x] empty state shows, hides, refills, carries a button, leaves room for the headings (`test_gui_search_tab.py::test_empty_state_*`) -> same names in `test_qt_widgets.py`
- [x] scroll page with a fixed footer (`test_gui_plan_redesign.py::test_the_footer_stays_visible_when_the_page_scrolls`, `test_the_plan_tab_is_a_scroll_page_with_a_footer`) -> `test_the_footer_stays_visible_when_the_page_scrolls`, `test_a_scroll_page_has_a_body_and_a_footer`
- [x] the footer is the last Tab stop and Shift+Tab is the reverse (widget part of `test_gui_final_pass.py::test_plan_tab_footer_buttons_are_the_last_stops_left_to_right`, `test_plan_tab_shift_tab_is_the_exact_reverse`) -> `test_the_footer_is_the_last_tab_stop_even_though_it_was_built_first`, `test_tab_and_shift_tab_walk_the_page_in_that_order`
- [x] switching a sidebar section scrolls back to the top (widget part of `test_switching_sections_scrolls_back_to_the_top`) -> `test_the_sidebar_and_a_scroll_frame_work_together_like_the_options_tab`
- [x] the mouse wheel over a combo box or spin box changes nothing until the box has the focus (MIGRATION_LOG no. 14) -> `test_qt_options_tab.py::test_the_wheel_over_a_drop_down_or_number_field_changes_nothing_without_focus` (the page-scrolls-instead half: `test_qt_widgets.py::test_the_mouse_wheel_scrolls_the_page`)

## Window, focus and tab order  (Phase 1 (window), all phases (tab order))

**Structure (from `App.__init__`, `build_ui`, `on_close`):** window `1020x910`, minimum `900x560`; four tabs `Search`, `Plan`, `Options`, `Queue & log`; with no Twitch client the app starts on the Plan tab; on start the status says `Ready. Paste a VOD URL or ID and press «Get info».`; tools setup starts in the background; closing while a job runs asks `A job is running. Cancel it and quit?`.

Phase 1 covers the frame of this screen in `test_qt_main_window.py`: title, size 1020x910, minimum 900x560, the four tab names in order (`Queue & log` shows a real ampersand), start on the Plan tab without a Twitch client, the ready text, the progress bar and status line that stay visible on every tab, top-bar keyboard order (entry, Get info, Twitch API…, tabs). Not yet: tools setup at start, the close question while a job runs (Phase 3), the 6 tab-order tests below (each tab's phase).

#### `test_gui_final_pass.py` (6 tests)

- [x] plan tab footer buttons are the last stops left to right  
  `test_gui_final_pass.py::test_plan_tab_footer_buttons_are_the_last_stops_left_to_right` -> same name in `test_qt_plan_tab.py` (Phase 6)
- [x] plan tab shift tab is the exact reverse  
  `test_gui_final_pass.py::test_plan_tab_shift_tab_is_the_exact_reverse` -> same name in `test_qt_plan_tab.py` (Phase 6)
- [x] plan tab footer is still packed at the bottom  
  `test_gui_final_pass.py::test_plan_tab_footer_is_still_packed_at_the_bottom` -> same name in `test_qt_plan_tab.py` (Phase 6)
- [x] tab order of search queue and options has nothing decorative  
  `test_gui_final_pass.py::test_tab_order_of_search_queue_and_options_has_nothing_decorative` -> Search: `test_qt_search_tab.py::test_keyboard_order_has_nothing_decorative`; Queue: `test_qt_queue_tab.py::test_the_tab_order_has_nothing_decorative` (Phase 4); Options: `test_qt_options_tab.py::test_the_tab_order_has_nothing_decorative` (Phase 5); Plan: `test_qt_plan_tab.py::test_plan_tab_order_has_nothing_decorative` (Phase 6)
- [x] timeline hint wraps to the width of the strip  
  `test_gui_final_pass.py::test_timeline_hint_wraps_to_the_width_of_the_strip` -> same name in `test_qt_plan_tab.py` (Phase 6)
- [x] search type list is never squeezed by a long title  
  `test_gui_final_pass.py::test_search_type_list_is_never_squeezed_by_a_long_title` -> same name in `test_qt_search_tab.py` (Phase 4)
