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

  function initBudgetSim() {
    var root = document.getElementById("budget-sim");
    if (!root) return;

    var maxTools = parseInt(root.getAttribute("data-max-tool-calls"), 10);
    var maxTurns = parseInt(root.getAttribute("data-max-turns"), 10);
    var maxSeconds = parseInt(root.getAttribute("data-max-seconds"), 10);
    var callBtn = document.getElementById("budget-call");
    var waitBtn = document.getElementById("budget-wait");
    var resetBtn = document.getElementById("budget-reset");
    var log = root.querySelector(".budget-log");
    if (!callBtn || !waitBtn || !resetBtn || !log) return;

    var state = { tools: 0, turns: 0, seconds: 0, stopped: false };

    function meter(name) {
      return root.querySelector('[data-meter="' + name + '"]');
    }

    function bar(name) {
      return root.querySelector('[data-bar="' + name + '"]');
    }

    function paint(name, value, max, suffix) {
      var label = meter(name);
      var fill = bar(name);
      if (label) label.textContent = value + " / " + max + (suffix || "");
      if (fill) {
        fill.style.width = Math.min(100, (value / max) * 100) + "%";
        fill.classList.toggle("is-warn", value >= max);
      }
    }

    function render() {
      paint("tools", state.tools, maxTools, "");
      paint("turns", state.turns, maxTurns, "");
      paint("seconds", state.seconds, maxSeconds, " 秒");
    }

    function addLog(text, bell) {
      var p = document.createElement("p");
      if (bell) p.className = "bell";
      p.textContent = text;
      log.appendChild(p);
      while (log.children.length > 6) log.removeChild(log.firstChild);
    }

    function stop(status, message) {
      state.stopped = true;
      root.classList.add("is-closed");
      addLog("叮——打烊铃。状态：" + status, true);
      addLog("给顾客的小票：" + message, false);
      callBtn.disabled = true;
      waitBtn.disabled = true;
      render();
    }

    function check() {
      if (state.seconds >= maxSeconds) {
        stop("timeout", "现在排队比较久，我先帮您留单，稍后再试。");
        return true;
      }
      if (state.turns >= maxTurns) {
        stop("max_turns", "今天先聊到这里，您要的我都记下了，稍后人工同事跟进。");
        return true;
      }
      if (state.tools >= maxTools) {
        stop("max_tool_calls", "今天先做到这里，您这杯已经排上，稍后确认。");
        return true;
      }
      return false;
    }

    callBtn.addEventListener("click", function () {
      if (state.stopped || check()) return;

      state.turns += 1;
      state.tools += 1;
      addLog("第 " + state.turns + " 轮：模型决定调用工具，后厨开做。");

      if (state.tools >= maxTools) {
        addLog("工具额度用完了；下一次调用会被打烊铃拦下。");
      } else if (state.turns >= maxTurns) {
        addLog("对话轮数额度用完了；下一轮会被拦下。");
      }
      render();
    });

    waitBtn.addEventListener("click", function () {
      if (state.stopped) return;
      state.seconds += 10;
      addLog("顾客又等了 10 秒。");
      render();
      check();
    });

    resetBtn.addEventListener("click", function () {
      state.tools = 0;
      state.turns = 0;
      state.seconds = 0;
      state.stopped = false;
      root.classList.remove("is-closed");
      callBtn.disabled = false;
      waitBtn.disabled = false;
      log.innerHTML = "<p>店刚开门，预算充足。</p>";
      render();
    });

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initLoop();
      initQuizzes();
      initScenarios();
      initBudgetSim();
    });
  } else {
    initLoop();
    initQuizzes();
    initScenarios();
    initBudgetSim();
  }
})();
