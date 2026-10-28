# First-Run Welcome & Quick Setup Plan

Status: Done in v2.1.0

This document outlines the detailed architecture, visual design, interactive onboarding flow, and choreographed animation system for the first-time welcome experience in **LuckyTwitch Downloader**.

---

## 1. Executive Summary & Design Principles

* **Purpose:** Provide a modern, welcoming, and high-fidelity first impression for first-time users, introducing the app's capabilities and providing an effortless quick-setup for essential settings before transitioning smoothly into the main workspace.
* **Window Sizing & Geometry:**
  * **Window Mode:** Standard window canvas takeover (default size `1020x910`, minimum `900x560`).
  * **Non-Intrusive:** Does not force OS-level full screen or unexpected display mode changes; instead, it renders as an immersive, full-bleed overlay widget that occupies 100% of the application window's client area.
* **Audio Strategy:** Purely visual. Fluid, high-frame-rate Qt animations with zero audio playback or system sound triggers.
* **Motion & Accessibility:** Built entirely atop `qt_ui.motion.Motion` tokens. If OS client-area animations are disabled (`SPI_GETCLIENTAREAANIMATION` on Windows) or running under pytest (`Motion.set_enabled(False)`), all transitions resolve synchronously in 0 ms.

---

## 2. Visual Architecture & Layout Breakdown

The welcome screen is composed of a responsive, centrally aligned card hierarchy anchored over a layered background canvas:

```
+-----------------------------------------------------------------------------------+
|  [Background Canvas: Deep Charcoal #1e1f22 + Dynamic Ambient Radial Glow]         |
|                                                                                   |
|                                     ( 🍀 )                                        |
|                          [App Icon: Float & Glow]                                 |
|                                                                                   |
|                         LuckyTwitch Downloader                                    |
|                       Version 2.0 · Creative Suite                                |
|                                                                                   |
|         "Fast VODs, precision clip cutting, and animated chat overlays."          |
|                                                                                   |
|     +-----------------------------------------------------------------------+     |
|     |                         QUICK SETUP (ESSENTIALS)                      |     |
|     |                                                                       |     |
|     |   📂 Download Folder:                                                 |     |
|     |      [ C:\Users\...\Downloads\LuckyTwitch             ] [ Browse... ] |     |
|     |                                                                       |     |
|     |   🎬 Preferred Format:                                                |     |
|     |      (●) MP4 (Universal)       ( ) MKV (Safe / Crash-Resistant)       |     |
|     |                                                                       |     |
|     |   👤 Twitch Account (Optional):                                       |     |
|     |      [ Sign in with Twitch ]   or   (Continue as Guest)               |     |
|     +-----------------------------------------------------------------------+     |
|                                                                                   |
|                        [  ⚡ Start Using LuckyTwitch  ]                           |
|                                                                                   |
|                         Press Esc or click to skip setup                          |
+-----------------------------------------------------------------------------------+
```

### Component Details
1. **Atmospheric Background Canvas:**
   * Deep base tone `#1e1f22` (`BG` token).
   * Soft radial gradient aura positioned behind the hero logo (Twitch Purple `#9146ff` bleeding softly into Lucky Emerald `#6bd49a` at 15–25% alpha opacity).
2. **Hero Branding:**
   * **Vector App Icon:** High-resolution clover + glitch crest (96x96 px) rendered with a soft drop shadow.
   * **Title Typography:** Crisp Segoe UI/system font (32pt, `#ffffff`, weight: 700, letter spacing: -0.5px).
   * **Version & Subtitle:** 11pt muted caption (`#a3a6ad`) and an engaging one-line mission statement.
3. **Essentials Quick Setup Card:**
   * Styled using a semi-transparent glassmorphism container (`#2b2d31` with 1px border `#35373c` and 12px corner radius).
   * **Download Directory:** Shows default path with a one-click folder picker.
   * **Preferred Container:** Segmented chip/toggle selector (`MP4` vs `MKV`).
   * **Twitch Authentication:** Quick-action button linking directly to the existing device code OAuth dialog, or an option to continue as a guest.
4. **Primary Call-to-Action (CTA):**
   * Prominent, large accent button: **"Start Using LuckyTwitch →"** (14pt font, 52px height, 240px min width).
   * Accent gradient styling (`#9146ff` → `#a46bff`), with an idle breathing glow animation.

---

## 3. Choreographed Animation Timeline

Every visual element is staggered and choreographed using Qt's `QParallelAnimationGroup`, `QSequentialAnimationGroup`, and `QPropertyAnimation`:

```
Time (ms)    0ms       150ms       350ms       550ms       750ms       950ms       Idle Loop
Glow Aura    [Bloom In: Opacity 0 -> 0.25 (300ms)]-------------------------------> [Subtle Breath]
App Icon     [Scale 0.7 -> 1.0 + Fade (250ms OutBack)]---------------------------> [Float ±4px Y]
Title Text                [Slide Up 20px + Fade (200ms OutCubic)]
Tagline                                [Slide Up + Fade (180ms)]
Setup Card                                          [Fade & Rise 15px (220ms)]
CTA Button                                                      [Pop & Scale (200ms OutBack)]
Idle Glow                                                                                   [Pulsing Glow]
```

### A. Entrance Sequence (0 ms – 950 ms)
1. **Aura Bloom (0–300 ms):** The ambient radial gradient transitions its radius and opacity (`0.0` to `0.25`) using `QEasingCurve.OutCubic`.
2. **Icon Bounce (50–300 ms):** The logo scales from 70% to 100% using `QEasingCurve.OutBack`, producing a lively, premium bounce.
3. **Hero Text Reveal (150–350 ms):** The title "LuckyTwitch Downloader" slides upward by 20px while fading from 0% to 100% opacity.
4. **Tagline Fade (280–460 ms):** The mission statement smoothly fades into place.
5. **Quick Setup Card Unfurl (400–650 ms):** The central settings card glides up 15px with an opacity fade (`QEasingCurve.OutCubic`).
6. **CTA Button Pop (600–800 ms):** The main "Start Using LuckyTwitch" button pops into view with a slight spring curve (`QEasingCurve.OutBack`).

### B. Continuous Idle Animations (Looping)
* **Icon Levitation:** A gentle, continuous sine-wave vertical offset (±4px over 3.2 seconds) gives life to the screen while waiting for user interaction.
* **CTA Breathing Glow:** An animated border/shadow pulse cycling between `#9146ff` and `#a46bff` (`DURATION_PULSE = 1200ms`), drawing the eye to the launch action without being distracting.

### C. Interactive Micro-Interactions
* **Browse Button Hover:** Smooth background tint shift (`BG3` → `HOVER`, 120ms).
* **Format Switch (MP4 / MKV):** Animated slider pill that glides between options (`QEasingCurve.OutCubic`, 140ms).
* **CTA Button Hover:** Lifts by 2px and intensifies the glow radius (`DURATION_FAST = 140ms`).
* **CTA Button Press:** Instant 2px micro-compression (`DURATION_MICRO = 80ms`).

### D. Exit / Dismiss Transition (On Button Click, ~280 ms)
* When the user clicks **"Start Using LuckyTwitch"** or presses `Enter` / `Esc`:
  1. Quick button press-down feedback.
  2. The entire welcome overlay scales slightly up (`1.0` → `1.03`) and fades out (`opacity: 1.0 -> 0.0`) over 240 ms using `QEasingCurve.InQuad`.
  3. The main window shell behind it (NavRail, CommandBar, Plan tab) smoothly fades in and settles to full brightness.
  4. The welcome widget is unparented or hidden from layout processing to release memory.

---

## 4. Technical Architecture & File Structure

### Proposed Module Organization
```
LuckyTwitchDownloader/
├── core/
│   ├── ui_state.py           # Add `has_completed_onboarding: bool = False`
│   └── settings.py           # Apply any changes made in the Quick Setup card
├── qt_ui/
│   ├── welcome/              # Dedicated welcome package
│   │   ├── __init__.py
│   │   ├── overlay.py        # WelcomeOverlay(QWidget) - full canvas & layout
│   │   ├── background.py     # AnimatedCanvas(QWidget) - radial glow & float loop
│   │   └── setup_card.py     # QuickSetupCard(QFrame) - essential settings controls
│   ├── main_window.py        # Coordinates overlay creation & first-run check
│   └── motion.py             # Reusable easing, durations, and accessibility switches
└── tests/
    └── test_welcome.py       # Deterministic headless tests
```

### State Management & First-Run Detection
1. **Persistent Flag (`luckytwitch_ui.json`):**
   * Handled inside `core/ui_state.py`:
     ```python
     @dataclass
     class UIState:
         # ... existing fields ...
         has_completed_onboarding: bool = False
     ```
2. **First Run Evaluation (`MainWindow.__init__`):**
   * If `ui_state.has_completed_onboarding is False`:
     * Instantiate `WelcomeOverlay(parent=self)`.
     * Overlay sits on top of the central stack.
     * When completed, write `has_completed_onboarding = True` via `save_ui_state()`.
3. **Replay Ability & CLI Bypass:**
   * **Menu Entry:** Added under `Help` → *"Show Welcome & Quick Setup..."* so users can revisit the experience at any time.
   * **CLI Flag:** Support `python luckytwitch_qt.py --welcome` to allow instant manual and test previewing without deleting settings.

---

## 5. Quick Setup Features (Essentials Specification)

The setup card only exposes the most essential 3 settings to keep onboarding fast and friction-free:

| Setting | Default Value | User Options | Reason for Inclusion |
| :--- | :--- | :--- | :--- |
| **Download Destination** | `~/Downloads/LuckyTwitch` | Browse directory picker | Prevents users wondering where videos are saved. |
| **File Format** | `MP4` | `MP4` (Fast/Compatible) vs `MKV` (Stream-Safe) | Most requested choice between casual viewers & video editors. |
| **Twitch Sign-in** | Guest / Logged Out | `[ Connect Twitch Account ]` button | Opens existing OAuth device code flow, unlocking sub-only VODs. |

*Any selections made immediately update `core.settings`, while unchanged items retain default values.*

---

## 6. Testing & Quality Assurance Plan

1. **Headless Pytest Suite (`tests/test_welcome.py`):**
   * **First Run Detection:** Verify overlay is created when `has_completed_onboarding=False`, and not created when `True`.
   * **Dismiss Action:** Verify clicking "Start" updates `has_completed_onboarding=True` and saves `luckytwitch_ui.json`.
   * **Setting Persistence:** Verify changing the download path or format in the quick setup saves properly to `core.settings`.
   * **Zero Motion in Tests:** Verify all animation durations evaluate to `0 ms` under `Motion.enabled() == False`.
2. **Visual Verification Checklist:**
   * Test at minimum window size (`900x560`) and larger resolutions (`1920x1080` maximized).
   * Check scaling and text sharpness on High-DPI displays (100%, 125%, 150%, 200%).
   * Ensure dark theme contrast matches WCAG AA standards.
