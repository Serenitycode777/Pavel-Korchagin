// Тема: по умолчанию как в настройках телефона, переключатель запоминает выбор на этом устройстве.
(function () {
  var doc = document.documentElement;
  var link = document.getElementById("dark-css");
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function saved() { try { return localStorage.getItem("theme"); } catch (e) { return null; } }
  function save(v) { try { localStorage.setItem("theme", v); } catch (e) {} }
  function current() { var s = saved(); return s === "dark" || s === "light" ? s : (mq && mq.matches ? "dark" : "light"); }
  function apply(t) {
    doc.setAttribute("data-theme", t);
    if (link) link.media = t === "dark" ? "all" : "not all";
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "dark" ? "#0b0e20" : "#5b3d9b");
  }
  apply(current());
  if (mq && mq.addEventListener) mq.addEventListener("change", function () { if (!saved()) apply(current()); });
  // Переключатель: обработчик на всём документе, поэтому работает, даже если кнопка появилась позже скрипта.
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("[data-theme-toggle]") : null;
    if (!b) return;
    var next = doc.getAttribute("data-theme") === "dark" ? "light" : "dark";
    save(next); apply(next);
  });
})();
