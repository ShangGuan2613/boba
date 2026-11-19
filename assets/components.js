/* Boba · shared interactive components
   Usage:
   - Loop stepper: <div class="loop" id="loop"> with .loop-card[data-caption]
     and buttons #next-step / #reset-step, caption #loop-caption.
   - Quiz: <div class="quiz" data-answer="N" data-hint="..." data-explanation="...">
     with .option buttons and .feedback. */

(function () {
  function initLoop() {
    var loop = document.getElementById("loop");
    if (!loop) return;

    var cards = Array.prototype.slice.call(loop.querySelectorAll(".loop-card"));
    var caption = document.getElementById("loop-caption");
    var next = document.getElementById("next-step");
    var reset = document.getElementById("reset-step");
    if (!cards.length || !caption || !next) return;

    var current = 0;

    function render() {
      cards.forEach(function (card, i) {
        card.classList.toggle("is-active", i === current);
        card.classList.toggle("is-done", i < current);
      });
      caption.textContent = cards[current].getAttribute("data-caption") || "";
      next.textContent = current === cards.length - 1 ? "从头再看" : "下一步";
    }

    next.addEventListener("click", function () {
      current = (current + 1) % cards.length;
      render();
    });

    if (reset) {
      reset.addEventListener("click", function () {
        current = 0;
        render();
      });
    }

    render();
  }

  function initQuizzes() {
    var quizzes = document.querySelectorAll(".quiz");

    quizzes.forEach(function (quiz) {
      var answer = parseInt(quiz.getAttribute("data-answer"), 10);
      var hint = quiz.getAttribute("data-hint") || "再想一步。";
      var explanation = quiz.getAttribute("data-explanation") || "对。";
      var options = Array.prototype.slice.call(quiz.querySelectorAll(".option"));
      var feedback = quiz.querySelector(".feedback");
      if (!options.length || !feedback) return;

      options.forEach(function (option, i) {
        option.addEventListener("click", function () {
          options.forEach(function (btn) { btn.disabled = true; });
          options[answer].classList.add("correct");

          if (i === answer) {
            feedback.textContent = explanation;
          } else {
            option.classList.add("wrong");
            feedback.textContent = hint + " 正确答案已标出——" + explanation;
          }
        });
      });
    });
  }

  function initScenarios() {
    var scenarios = document.querySelectorAll(".scenario");

    scenarios.forEach(function (scenario) {
      var tabs = Array.prototype.slice.call(scenario.querySelectorAll(".scenario-tab"));
      var panels = Array.prototype.slice.call(scenario.querySelectorAll(".scenario-panel"));
      if (!tabs.length || !panels.length) return;

      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          var target = tab.getAttribute("data-target");

          tabs.forEach(function (item) {
            var active = item === tab;
            item.classList.toggle("is-active", active);
            item.setAttribute("aria-selected", active ? "true" : "false");
          });

          panels.forEach(function (panel) {
            panel.classList.toggle("is-active", panel.id === target);
          });
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initLoop();
      initQuizzes();
      initScenarios();
    });
  } else {
    initLoop();
    initQuizzes();
    initScenarios();
  }
})();
