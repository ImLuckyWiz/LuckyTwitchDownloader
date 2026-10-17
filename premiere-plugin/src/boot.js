"use strict";
/* Loaded first, uses no require(): shows in the panel's log that scripts run at all, and catches errors of the later scripts. */
window.__ltLog = function (text, isError) {
  try {
    const box = document.getElementById("log");
    if (!box) return;
    box.value = (box.value || "") + (isError ? "ERROR: " : "") + text + "\n"; // `|| ""`: an empty UXP textarea can report null // a textarea, so the text can be selected and copied
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    /* nothing more we can do */
  }
};
window.addEventListener("error", function (ev) {
  window.__ltLog("Error: " + (ev && ev.message ? ev.message : ev), true);
});
window.__ltLog("boot.js running.");
