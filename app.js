(function () {
  "use strict";

  var ICON_PREFIX = "https://img-eshop.cdn.nintendo.net/i/";
  var ICON_SUFFIX = ".jpg";
  var GAP = 6;
  var GRID_PAD = 8; // horizontal breathing room so hover-scaled edge tiles don't clip against overflow:hidden
  var BUFFER_ROWS = 3;

  var els = {
    scroller: document.getElementById("scroller"),
    sizer: document.getElementById("sizer"),
    win: document.getElementById("window"),
    search: document.getElementById("search-input"),
    searchClear: document.getElementById("search-clear"),
    sort: document.getElementById("sort-select"),
    randomBtn: document.getElementById("random-btn"),
    chipRow: document.getElementById("chip-row"),
    clearFilters: document.getElementById("clear-filters"),
    azRail: document.getElementById("az-rail"),
    backToTop: document.getElementById("back-to-top"),
    countVisible: document.getElementById("count-visible"),
    countTotal: document.getElementById("count-total"),
    empty: document.getElementById("empty-state"),
    emptyQuery: document.getElementById("empty-query"),
    emptyClear: document.getElementById("empty-clear"),
    modalBackdrop: document.getElementById("modal-backdrop"),
    modal: document.getElementById("modal"),
    modalClose: document.getElementById("modal-close"),
    modalIcon: document.getElementById("modal-icon"),
    modalTitle: document.getElementById("modal-title"),
    modalPub: document.getElementById("modal-pub"),
    modalDate: document.getElementById("modal-date"),
    modalCats: document.getElementById("modal-cats"),
    modalId: document.getElementById("modal-id"),
    modalOpen: document.getElementById("modal-open")
  };

  var state = {
    all: [],       // full game list [id, name, iconHash, pub, catIdx[], date]
    cats: [],       // category names
    filtered: [],   // current filtered+sorted view
    activeCats: new Set(),
    query: "",
    sort: "name-asc",
    cols: 4,
    tileWidth: 128,
    rowHeight: 134
  };

  function iconUrl(hash) {
    // titledb entries store just a hash fragment (shared prefix/suffix) to
    // keep the dataset small; the Nintendo.com Switch 2 supplement stores
    // full URLs directly since they don't share that pattern.
    if (hash.indexOf("http") === 0) return hash;
    return ICON_PREFIX + hash + ICON_SUFFIX;
  }

  function fmtDate(d) {
    if (!d) return "Unknown";
    var s = String(d);
    if (s.length !== 8) return "Unknown";
    var y = s.slice(0, 4), m = s.slice(4, 6), day = s.slice(6, 8);
    var months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return months[parseInt(m, 10)] + " " + parseInt(day, 10) + ", " + y;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Official Nintendo titles are full of ™/®/© marks and accented characters
  // ("Mario Kart™ World", "Pokémon") that nobody types when searching. Strip
  // those out (and fold accents) on both sides of the comparison so a plain
  // "mario kart world" still finds it.
  function normalizeSearch(str) {
    var s = String(str).toLowerCase();
    if (s.normalize) s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return s.replace(/[™®©]/g, "").replace(/\s+/g, " ").trim();
  }

  // ---------- Load data ----------
  els.win.innerHTML = '<p style="grid-column:1/-1;color:var(--text-muted);padding:40px 0;text-align:center;">Loading the archive…</p>';

  fetch("data.json")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      state.cats = data.cats;
      state.all = data.games;
      state.searchIndex = state.all.map(function (g) { return normalizeSearch(g[1]); });
      els.countTotal.textContent = state.all.length.toLocaleString();
      buildChips();
      buildAzRail();
      applyFilters();
      window.addEventListener("resize", debounce(onResize, 120));
      onResize();
    })
    .catch(function (err) {
      els.win.innerHTML = '<p style="grid-column:1/-1;color:var(--text-muted);padding:40px 0;text-align:center;">Could not load the archive data. (' + escapeHtml(err.message) + ")</p>";
    });

  // ---------- Chips ----------
  function buildChips() {
    els.chipRow.innerHTML = "";
    state.cats.forEach(function (cat, i) {
      var chip = document.createElement("button");
      chip.className = "chip";
      chip.type = "button";
      chip.textContent = cat;
      chip.dataset.idx = i;
      chip.addEventListener("click", function () {
        if (state.activeCats.has(i)) {
          state.activeCats.delete(i);
          chip.classList.remove("active");
        } else {
          state.activeCats.add(i);
          chip.classList.add("active");
        }
        applyFilters();
      });
      els.chipRow.appendChild(chip);
    });
  }

  // ---------- A-Z rail ----------
  function buildAzRail() {
    var letters = ["#"];
    for (var c = 65; c <= 90; c++) letters.push(String.fromCharCode(c));
    els.azRail.innerHTML = "";
    letters.forEach(function (L) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = L;
      btn.addEventListener("click", function () { jumpToLetter(L); });
      els.azRail.appendChild(btn);
    });
  }

  function letterOf(name) {
    var c = (name || "").trim().charAt(0).toUpperCase();
    return c >= "A" && c <= "Z" ? c : "#";
  }

  function jumpToLetter(letter) {
    var list = state.filtered;
    if (!list.length) return;
    var desc = state.sort === "name-desc";
    var idx = -1;
    if (state.sort === "name-asc" || state.sort === "name-desc") {
      for (var i = 0; i < list.length; i++) {
        var li = desc ? list.length - 1 - i : i;
        if (letterOf(list[li][1]) === letter) { idx = li; break; }
      }
    } else {
      // Not name-sorted: fall back to a plain alphabetical scan of current set.
      var best = -1;
      for (var j = 0; j < list.length; j++) {
        if (letterOf(list[j][1]) === letter) { best = j; break; }
      }
      idx = best;
    }
    if (idx === -1) return;
    scrollToIndex(idx);
    flashTileAtIndex(idx);
  }

  function scrollToIndex(idx, center) {
    var row = Math.floor(idx / state.cols);
    var top = row * state.rowHeight;
    if (center) top -= (els.scroller.clientHeight / 2) - (state.rowHeight / 2);
    els.scroller.scrollTop = Math.max(0, top);
    renderWindow();
  }

  function flashTileAtIndex(idx) {
    window.requestAnimationFrame(function () {
      var tile = els.win.querySelector('.tile[data-idx="' + idx + '"]');
      if (!tile) return;
      tile.classList.add("flash");
      setTimeout(function () { tile.classList.remove("flash"); }, 900);
    });
  }

  // ---------- Filtering / sorting ----------
  function applyFilters() {
    var q = normalizeSearch(state.query);
    var cats = state.activeCats;
    var out = [];
    for (var i = 0; i < state.all.length; i++) {
      var g = state.all[i];
      if (q && state.searchIndex[i].indexOf(q) === -1) continue;
      if (cats.size > 0) {
        var match = false;
        var gc = g[4];
        for (var j = 0; j < gc.length; j++) {
          if (cats.has(gc[j])) { match = true; break; }
        }
        if (!match) continue;
      }
      out.push(g);
    }

    switch (state.sort) {
      case "name-desc":
        out.sort(function (a, b) { return b[1].localeCompare(a[1]); });
        break;
      case "date-desc":
        out.sort(function (a, b) { return (b[5] || 0) - (a[5] || 0); });
        break;
      case "date-asc":
        out.sort(function (a, b) { return (a[5] || 0) - (b[5] || 0); });
        break;
      default:
        out.sort(function (a, b) { return a[1].localeCompare(b[1]); });
    }

    state.filtered = out;
    els.countVisible.textContent = out.length.toLocaleString();
    els.searchClear.hidden = state.query.length === 0;
    els.clearFilters.hidden = !(state.query || state.activeCats.size > 0);

    if (out.length === 0) {
      els.empty.hidden = false;
      els.emptyQuery.textContent = state.query ? '"' + state.query + '"' : "your filters";
    } else {
      els.empty.hidden = true;
    }

    els.scroller.scrollTop = 0;
    renderWindow(true);
  }

  // ---------- Virtualized rendering ----------
  function onResize() {
    var width = els.scroller.clientWidth - GRID_PAD * 2;
    var minTile = window.innerWidth < 640 ? 84 : 108;
    var cols = Math.max(2, Math.floor((width + GAP) / (minTile + GAP)));
    var tileWidth = (width - GAP * (cols - 1)) / cols;
    state.cols = cols;
    state.tileWidth = tileWidth;
    state.rowHeight = tileWidth + GAP;
    els.win.style.setProperty("--cols", cols);
    renderWindow(true);
  }

  // DOM recycling: els.win's children always correspond to one contiguous
  // range of `state.filtered` indices, tracked in `rendered`. On scroll we
  // only add/remove nodes at the edges of that range instead of rebuilding
  // everything — rebuilding on every scroll tick was cancelling in-flight
  // image requests for icons still on screen, which is what caused icons to
  // randomly stop loading.
  var rendered = { start: 0, end: 0 };

  function makeTile(list, i) {
    var g = list[i];
    var tile = document.createElement("div");
    tile.className = "tile";
    tile.dataset.idx = i;
    tile.setAttribute("role", "listitem");
    tile.tabIndex = 0;
    tile.title = g[1];

    var img = document.createElement("img");
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = "";
    img.addEventListener("load", function () { img.classList.add("loaded"); });
    img.addEventListener("error", function () {
      tile.classList.add("broken");
      img.remove();
    });
    img.src = iconUrl(g[2]);

    var bar = document.createElement("div");
    bar.className = "tile-bar";
    var name = document.createElement("div");
    name.className = "tile-name";
    name.textContent = g[1];

    tile.appendChild(img);
    tile.appendChild(bar);
    tile.appendChild(name);
    return tile;
  }

  function renderWindow(forceRebuild) {
    var list = state.filtered;
    var cols = state.cols;
    var rowH = state.rowHeight;
    var totalRows = Math.ceil(list.length / cols);
    var totalHeight = totalRows * rowH;
    els.sizer.style.height = totalHeight + "px";

    var scrollTop = els.scroller.scrollTop;
    var viewH = els.scroller.clientHeight;
    var startRow = Math.max(0, Math.floor(scrollTop / rowH) - BUFFER_ROWS);
    var endRow = Math.min(totalRows, Math.ceil((scrollTop + viewH) / rowH) + BUFFER_ROWS);

    var startIdx = startRow * cols;
    var endIdx = Math.min(list.length, endRow * cols);

    els.win.style.transform = "translateY(" + (startRow * rowH) + "px)";

    var noOverlap = startIdx >= rendered.end || endIdx <= rendered.start;
    if (forceRebuild || noOverlap) {
      var frag = document.createDocumentFragment();
      for (var i = startIdx; i < endIdx; i++) frag.appendChild(makeTile(list, i));
      els.win.innerHTML = "";
      els.win.appendChild(frag);
      rendered.start = startIdx;
      rendered.end = endIdx;
      return;
    }

    // Trim off the front/back edges that scrolled out of range.
    while (rendered.start < startIdx && els.win.firstChild) {
      els.win.removeChild(els.win.firstChild);
      rendered.start++;
    }
    while (rendered.end > endIdx && els.win.lastChild) {
      els.win.removeChild(els.win.lastChild);
      rendered.end--;
    }
    // Grow to cover the new range — existing nodes in the middle are untouched.
    for (var f = rendered.start - 1; f >= startIdx; f--) {
      els.win.insertBefore(makeTile(list, f), els.win.firstChild);
    }
    rendered.start = startIdx;
    for (var b = rendered.end; b < endIdx; b++) {
      els.win.appendChild(makeTile(list, b));
    }
    rendered.end = endIdx;
  }

  var scrollTicking = false;
  els.scroller.addEventListener("scroll", function () {
    if (!scrollTicking) {
      window.requestAnimationFrame(function () {
        renderWindow();
        els.backToTop.hidden = els.scroller.scrollTop < 800;
        scrollTicking = false;
      });
      scrollTicking = true;
    }
  });

  els.backToTop.addEventListener("click", function () {
    els.scroller.scrollTo({ top: 0, behavior: "smooth" });
  });

  // ---------- Search / sort controls ----------
  els.search.addEventListener("input", debounce(function () {
    state.query = els.search.value;
    applyFilters();
  }, 140));

  els.searchClear.addEventListener("click", function () {
    els.search.value = "";
    state.query = "";
    applyFilters();
    els.search.focus();
  });

  els.sort.addEventListener("change", function () {
    state.sort = els.sort.value;
    applyFilters();
  });

  function clearAllFilters() {
    els.search.value = "";
    state.query = "";
    state.activeCats.clear();
    Array.prototype.forEach.call(els.chipRow.children, function (c) { c.classList.remove("active"); });
    applyFilters();
  }
  els.emptyClear.addEventListener("click", clearAllFilters);
  els.clearFilters.addEventListener("click", clearAllFilters);

  var brandHome = document.getElementById("brand-home");
  if (brandHome) {
    brandHome.addEventListener("click", function (e) {
      e.preventDefault();
      clearAllFilters();
      els.scroller.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // "/" focuses search, unless already typing somewhere
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/") return;
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();
    els.search.focus();
  });

  // ---------- Random ----------
  els.randomBtn.addEventListener("click", function () {
    var list = state.filtered;
    if (!list.length) return;
    var idx = Math.floor(Math.random() * list.length);
    scrollToIndex(idx, true);
    openModal(list[idx]);
  });

  // ---------- Modal ----------
  els.win.addEventListener("click", function (e) {
    var tile = e.target.closest(".tile");
    if (!tile) return;
    openModal(state.filtered[parseInt(tile.dataset.idx, 10)]);
  });
  els.win.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var tile = e.target.closest(".tile");
    if (!tile) return;
    e.preventDefault();
    openModal(state.filtered[parseInt(tile.dataset.idx, 10)]);
  });

  var lastFocused = null;
  function openModal(g) {
    if (!g) return;
    lastFocused = document.activeElement;
    var url = iconUrl(g[2]);
    els.modalIcon.onerror = function () { els.modalIcon.style.visibility = "hidden"; };
    els.modalIcon.style.visibility = "visible";
    els.modalIcon.src = url;
    els.modalIcon.alt = g[1];
    els.modalTitle.textContent = g[1];
    els.modalPub.textContent = g[3] || "Unknown";
    els.modalDate.textContent = fmtDate(g[5]);
    els.modalCats.textContent = g[4].length ? g[4].map(function (i) { return state.cats[i]; }).join(", ") : "—";
    els.modalId.textContent = g[0];
    els.modalOpen.href = url;
    els.modalBackdrop.hidden = false;
    requestAnimationFrame(function () { els.modalBackdrop.classList.add("open"); });
    els.modalClose.focus();
  }
  function closeModal() {
    els.modalBackdrop.classList.remove("open");
    els.modalBackdrop.hidden = true;
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
  }
  els.modalClose.addEventListener("click", closeModal);
  els.modalBackdrop.addEventListener("click", function (e) {
    if (e.target === els.modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeModal();
  });

  // ---------- Utils ----------
  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }
})();
