/* One-tap example codes for the research workbench. Fills the input only; never submits. */
(() => {
  "use strict";
  document.addEventListener("click", event => {
    const chip = event.target instanceof Element ? event.target.closest("[data-rw-example]") : null;
    if (!chip) return;
    const input = document.getElementById("research-template-subject");
    if (!input) return;
    input.value = chip.dataset.rwExample;
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.focus({preventScroll: true});
  });
})();
