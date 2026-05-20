// Walk every <div class="brunch-cast" data-cast="..."> on the page and
// instantiate an asciinema-player against the referenced .cast file.
// Loaded after asciinema-player.min.js (see mkdocs.yml extra_javascript).
(function () {
  function init() {
    if (typeof AsciinemaPlayer === "undefined") {
      console.warn("asciinema-player not loaded yet; retrying in 100ms");
      setTimeout(init, 100);
      return;
    }
    document.querySelectorAll(".brunch-cast[data-cast]").forEach(function (el) {
      if (el.dataset.brunchCastInitialized === "true") return;
      el.dataset.brunchCastInitialized = "true";
      const src = el.dataset.cast;
      const opts = {
        // Reasonable defaults for tutorial-style casts.
        idleTimeLimit: 2,
        theme: "asciinema",
        fit: "width",
        terminalFontSize: "medium",
      };
      // Mount the player into a fresh inner div so re-renders don't double-mount.
      const inner = document.createElement("div");
      inner.className = "asciinema-player-wrapper";
      el.appendChild(inner);
      AsciinemaPlayer.create(src, inner, opts);
    });
  }

  // Material for MkDocs replaces page DOM on navigation; re-init each time.
  if (typeof document$ !== "undefined") {
    document$.subscribe(init);
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
