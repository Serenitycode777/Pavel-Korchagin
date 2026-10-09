// Модальные окна «Подробнее о выполнении практики».
(function () {
  function closeDialog(d) { if (d.open) d.close(); document.documentElement.style.overflow = ""; }
  document.querySelectorAll("[data-open]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var d = document.getElementById(btn.dataset.open);
      if (!d) return;
      if (typeof d.showModal === "function") { d.showModal(); } else { d.setAttribute("open", ""); }
      document.documentElement.style.overflow = "hidden";
      var body = d.querySelector(".modal-body"); if (body) body.scrollTop = 0;
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("dialog.modal[open]").forEach(closeDialog);
  });
  document.querySelectorAll("dialog.modal").forEach(function (d) {
    d.addEventListener("click", function (e) { if (e.target === d) closeDialog(d); }); // клик по затемнению
    d.addEventListener("close", function () { document.documentElement.style.overflow = ""; });
    d.querySelectorAll("[data-close]").forEach(function (b) { b.addEventListener("click", function () { closeDialog(d); }); });
  });
})();

// Видео открывается по нажатию на обложку: плеер (свой файл или YouTube) подгружается только тогда.
(function () {
  document.querySelectorAll("button.poster[data-video], button.poster[data-video-file]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var box = document.createElement("div");
      box.className = "video";
      if (btn.dataset.videoFile) {
        var v = document.createElement("video");
        v.src = btn.dataset.videoFile;
        v.controls = true;
        v.autoplay = true;
        v.playsInline = true;
        box.appendChild(v);
      } else {
        var f = document.createElement("iframe");
        f.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(btn.dataset.video) + "?autoplay=1&rel=0";
        f.title = btn.dataset.title || "Видео";
        f.allow = "autoplay; accelerometer; encrypted-media; picture-in-picture";
        f.setAttribute("allowfullscreen", "");
        box.appendChild(f);
      }
      btn.replaceWith(box);
    });
  });
})();

// Инструктаж при первом входе: карточки листаются кнопкой «Далее», показывается один раз.
(function () {
  var d = document.getElementById("intro");
  if (!d) return;
  var steps = d.querySelectorAll(".intro-step");
  var pos = d.querySelector("#introPos");
  var btn = d.querySelector("#introNext");
  var i = 0;
  function render() {
    steps.forEach(function (s, idx) { s.hidden = idx !== i; });
    if (pos) pos.textContent = i + 1;
    if (btn) btn.textContent = (i === steps.length - 1) ? btn.dataset.finishLabel : btn.dataset.nextLabel;
  }
  if (btn && steps.length) {
    btn.addEventListener("click", function () {
      if (i < steps.length - 1) { i++; render(); } else if (d.open) { d.close(); }
    });
  }
  var KEY = "celostnost-intro-seen";
  try {
    if (localStorage.getItem(KEY)) return;
    if (typeof d.showModal === "function") { d.showModal(); } else { d.setAttribute("open", ""); }
    document.documentElement.style.overflow = "hidden";
    localStorage.setItem(KEY, "1");
  } catch (e) {}
})();

// Практики-аккордеон: адрес вида /practices#p3 раскрывает нужную практику и прокручивает к ней.
(function () {
  var items = document.querySelectorAll("details.practice");
  if (!items.length) return;
  function openFromHash() {
    var m = /^#p(\d+)$/.exec(location.hash);
    if (!m) return;
    var art = document.getElementById("p" + m[1]);
    if (!art) return;
    art.open = true;
    art.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();
})();
