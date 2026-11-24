/* Child-facing flashcard session (FR 4.1, FR 4.2; activity diagram B.4).
 * Low stimulation: no animations, one card at a time, child-paced "Next".
 * Audio (if on): the word is spoken with the browser's speech synthesis, and a
 * soft two-note chime plays for a correct answer (SRS 3.2 audio output).
 * Wrong answers get a gentle visual hint: the right word is outlined and named.
 */
(function () {
  "use strict";
  var cfg = window.PLAY;
  var $ = function (id) { return document.getElementById(id); };
  var csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
  var shownAt = 0, busy = false, audioCtx = null;

  function post(url, body) {
    var ctrl = new AbortController();
    var t = setTimeout(function () { ctrl.abort(); }, 8000);
    return fetch(url, {
      method: "POST",
      signal: ctrl.signal,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, Accept: "application/json" },
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.detail || "Something went wrong. Please try again.");
        return data;
      });
    }).catch(function (e) {
      if (e.name === "AbortError") throw new Error("The connection is slow. Please try again.");
      throw e;
    }).finally(function () { clearTimeout(t); });
  }

  function showError(msg) { $("play-error").textContent = msg || ""; $("play-error").hidden = !msg; }

  function show(screen) {
    ["start-screen", "card-screen", "done-screen"].forEach(function (id) { $(id).hidden = id !== screen; });
  }

  // ---------- audio ----------
  function speak(text) {
    if (!cfg.audio || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.rate = 0.85; u.pitch = 1.0; u.volume = 0.8;
    window.speechSynthesis.speak(u);
  }

  function chime() {
    if (!cfg.audio) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      [523.25, 659.25].forEach(function (freq, i) {   // C5 then E5, soft sine
        var osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
        var start = audioCtx.currentTime + i * 0.18;
        osc.type = "sine"; osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.12, start + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.45);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(start); osc.stop(start + 0.5);
      });
    } catch (e) { /* audio is optional */ }
  }

  // ---------- flow ----------
  function loadNext() {
    showError("");
    busy = true;
    post(cfg.nextUrl).then(function (data) {
      if (data.done) { show("done-screen"); speak("All done. Well done!"); return; }
      renderCard(data.card);
    }).catch(function (e) { showError(e.message); }).finally(function () { busy = false; });
  }

  function renderCard(card) {
    show("card-screen");
    $("progress").textContent = "Card " + card.number + " of " + card.total;
    $("level").textContent = card.level;
    if (card.image_url) {
      $("card-image").src = card.image_url; $("card-image").hidden = false; $("card-symbol").hidden = true;
    } else {
      $("card-symbol").textContent = card.symbol; $("card-symbol").hidden = false; $("card-image").hidden = true;
    }
    var box = $("choices");
    box.textContent = "";
    box.className = "choices choices-" + card.choices.length;
    card.choices.forEach(function (label) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "choice"; b.textContent = label; b.dataset.label = label;
      box.appendChild(b);
    });
    $("feedback").textContent = "";
    $("next").hidden = true;
    shownAt = performance.now();
    speak("What is this?");
  }

  $("choices").addEventListener("click", function (e) {
    var btn = e.target.closest(".choice");
    if (!btn || busy) return;
    busy = true;
    var buttons = Array.prototype.slice.call(this.querySelectorAll(".choice"));
    buttons.forEach(function (b) { b.disabled = true; });
    post(cfg.answerUrl, { choice: btn.dataset.label, response_time_ms: Math.round(performance.now() - shownAt) })
      .then(function (r) {
        buttons.forEach(function (b) {
          if (b.dataset.label === r.correct_label) b.classList.add(r.correct ? "is-correct" : "is-hint");
          else if (b === btn) b.classList.add("is-chosen");
        });
        // No "a/an" before the word, so it reads correctly for every label (e.g. "apple").
        if (r.correct) {
          $("feedback").textContent = "Well done! That's right: " + r.correct_label + ".";
          chime(); speak(r.correct_label + ". Well done.");
        } else {
          $("feedback").textContent = "This one is: " + r.correct_label + ".";
          speak("This one is " + r.correct_label + ".");
        }
        $("level").textContent = r.level;
        $("progress").textContent = "Card " + r.number + " of " + r.total;
        if (r.done) {
          $("next").textContent = "Finish";
        }
        $("next").hidden = false;
        $("next").dataset.done = r.done ? "1" : "";
        $("next").focus();
      })
      .catch(function (err) {
        showError(err.message);
        buttons.forEach(function (b) { b.disabled = false; });
      })
      .finally(function () { busy = false; });
  });

  $("next").addEventListener("click", function () {
    if (this.dataset.done) { window.location.href = cfg.summaryUrl; return; }
    loadNext();
  });

  // A tap is needed before audio can play on phones, so the session starts with "Start".
  $("start").addEventListener("click", loadNext);

  $("end-session").addEventListener("click", function () {
    if (!window.confirm("End this session and see the summary?")) return;
    post(cfg.endUrl).then(function (d) { window.location.href = d.summary_url || cfg.summaryUrl; })
      .catch(function (e) { showError(e.message); });
  });
})();
