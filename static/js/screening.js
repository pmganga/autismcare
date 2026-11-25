/* One question per screen.
 * Without JavaScript the whole form shows on one page and still works.
 * Choosing an answer moves straight to the next question. Back goes to the previous one.
 * No animations (SRS 3.1).
 */
(function () {
  "use strict";
  var form = document.getElementById("screening-form");
  if (!form) return;
  document.documentElement.classList.add("js");

  var steps = Array.prototype.slice.call(form.querySelectorAll(".step"));
  var nav = form.querySelector(".step-nav");
  var err = document.getElementById("step-error");
  var age = document.getElementById("age");
  var current = 0;

  function showError(msg) { err.textContent = msg || ""; err.hidden = !msg; }

  function show(i) {
    current = Math.max(0, Math.min(i, steps.length - 1));
    steps.forEach(function (s, k) { s.hidden = k !== current; });
    nav.hidden = current === 0;
    showError("");
    var target = steps[current].querySelector("input:checked, input, button[type=submit]");
    if (target) target.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }

  function ageIsValid() {
    var v = parseInt(age.value, 10);
    if (isNaN(v)) { showError("Enter your child's age in months, as a number."); return false; }
    if (v < parseInt(age.min, 10) || v > parseInt(age.max, 10)) {
      form.submit(); // let the server explain the age range and link to the directory
      return false;
    }
    return true;
  }

  form.addEventListener("click", function (e) {
    var action = e.target.getAttribute("data-action");
    if (action === "next" && ageIsValid()) show(current + 1);
    if (action === "back") show(current - 1);
  });

  age.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); if (ageIsValid()) show(current + 1); }
  });

  form.addEventListener("change", function (e) {
    if (e.target.type === "radio") show(current + 1);
  });

  form.addEventListener("submit", function (e) {
    var unanswered = steps.filter(function (s) {
      return s.classList.contains("question") && !s.querySelector("input:checked");
    });
    if (unanswered.length) {
      e.preventDefault();
      show(steps.indexOf(unanswered[0]));
      showError("Please answer this question.");
    }
  });

  // Start where the parent needs to be (e.g. after a server-side error).
  var hasAgeError = !!form.querySelector(".has-error #age");
  var firstUnanswered = steps.findIndex(function (s) {
    return s.classList.contains("question") && !s.querySelector("input:checked");
  });
  show(hasAgeError || !age.value ? 0 : (firstUnanswered === -1 ? steps.length - 1 : firstUnanswered));
})();
