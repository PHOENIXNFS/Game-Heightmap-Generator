/* App state, controls, API calls, island cards, preview orchestration. */
"use strict";

(function () {
  var $ = function (id) { return document.getElementById(id); };

  var state = {
    config: null,        // source of truth, mirrors the API shape
    previewId: null,
    fullId: null,
    fullDirty: true,     // config changed since last full generate
    previewSeq: 0,
    previewTimer: null,
    statusTimer: null,
    selected: 0,
    heights: null,
    lastW: 0,
    lastH: 0
  };

  /* ================= config <-> UI ================= */

  function applyToUI(cfg) {
    state.config = cfg;
    ensureIslandSeeds();
    $("seed").value = cfg.seed;
    $("mode").value = cfg.mode;
    $("map-w").value = cfg.width;
    $("map-h").value = cfg.height;
    $("sea-level").value = cfg.sea_level;
    $("sea-level-val").textContent = Number(cfg.sea_level).toFixed(3);
    $("noise-scale").value = cfg.noise.scale;
    $("noise-scale-val").textContent = Number(cfg.noise.scale).toFixed(1);
    $("detail-amp").value = cfg.noise.detail_amp;
    $("detail-amp-val").textContent = Number(cfg.noise.detail_amp).toFixed(2);
    $("coast-warp").value = cfg.noise.coast_warp;
    $("coast-warp-val").textContent = Number(cfg.noise.coast_warp).toFixed(2);
    $("noise-persistence").value = cfg.noise.persistence;
    $("noise-persistence-val").textContent = Number(cfg.noise.persistence).toFixed(2);
    $("noise-octaves").value = cfg.noise.octaves;
    $("noise-octaves-val").textContent = String(cfg.noise.octaves);
    $("smoothing-thermal").value = cfg.smoothing.thermal;
    $("smoothing-thermal-val").textContent = Number(cfg.smoothing.thermal).toFixed(2);
    $("smoothing-blur").value = cfg.smoothing.blur;
    $("smoothing-blur-val").textContent = Number(cfg.smoothing.blur).toFixed(2);
    $("erosion-enabled").checked = cfg.erosion.enabled;
    $("erosion-droplets").value = cfg.erosion.droplets;
    $("erosion-droplets-val").textContent = String(cfg.erosion.droplets);
    $("erosion-steps").value = cfg.erosion.max_steps;
    $("erosion-steps-val").textContent = String(cfg.erosion.max_steps);
    updateErosionUI();
    updateModeUI();
    renderIslandCards();
  }

  function readUI() {
    var cfg = state.config;
    cfg.seed = clampInt($("seed").value, 0, 2147483647, 1337);
    cfg.mode = $("mode").value;
    cfg.width = clampInt($("map-w").value, 64, 8192, 1024);
    cfg.height = clampInt($("map-h").value, 64, 8192, 1024);
    cfg.sea_level = Number($("sea-level").value);
    cfg.noise.scale = Number($("noise-scale").value);
    cfg.noise.detail_amp = Number($("detail-amp").value);
    cfg.noise.coast_warp = Number($("coast-warp").value);
    cfg.noise.persistence = Number($("noise-persistence").value);
    cfg.noise.octaves = clampInt($("noise-octaves").value, 1, 10, 6);
    cfg.smoothing.thermal = Number($("smoothing-thermal").value);
    cfg.smoothing.blur = Number($("smoothing-blur").value);
    cfg.erosion.enabled = $("erosion-enabled").checked;
    cfg.erosion.droplets = clampInt($("erosion-droplets").value, 0, 400000, 60000);
    cfg.erosion.max_steps = clampInt($("erosion-steps").value, 0, 120, 30);
    return cfg;
  }

  function clampInt(v, lo, hi, dflt) {
    var n = parseInt(v, 10);
    if (isNaN(n)) return dflt;
    return Math.min(hi, Math.max(lo, n));
  }

  /* Per-island seeds: every island owns one, so rerolling an island only
     reshapes that island. Kept in sync with core.noise.island_seed(). */
  function randomSeed() {
    return Math.floor(Math.random() * 4294967296) >>> 0;
  }

  function islandSeed(base, index) {
    return (Math.imul(base >>> 0, 73856093) ^ Math.imul(index, 19349663)) >>> 0;
  }

  function ensureIslandSeeds() {
    var islands = state.config.islands;
    for (var i = 0; i < islands.length; i++) {
      var s = islands[i].seed;
      if (typeof s !== "number" || !isFinite(s)) {
        s = islandSeed(state.config.seed, i); // pre-seed configs stay reproducible
      }
      islands[i].seed = s >>> 0;
    }
  }

  function updateModeUI() {
    var isl = $("islands-panel");
    var islands = state.config.mode === "islands";
    isl.style.display = islands ? "" : "none";
    var seedField = $("global-seed-field");
    if (seedField) seedField.style.display = islands ? "none" : ""; // islands carry their own seeds
    var seaRow = $("sea-level-row");
    if (seaRow) seaRow.style.display = islands ? "" : "none";
    if (window.Preview2D) Preview2D.setConfig(state.config);
  }

  function updateErosionUI() {
    var on = $("erosion-enabled").checked;
    var ctl = $("erosion-controls");
    ctl.style.opacity = on ? "1" : "0.4";
    var inputs = ctl.getElementsByTagName("input");
    for (var i = 0; i < inputs.length; i++) inputs[i].disabled = !on;
  }

  /* ================= island cards ================= */

  function deg(r) {
    var d = Math.round(r * 180 / Math.PI);
    return ((d % 360) + 360) % 360;
  }

  function renderIslandCards() {
    var list = $("island-list");
    list.innerHTML = "";
    var islands = state.config.islands;
    for (var i = 0; i < islands.length; i++) {
      list.appendChild(buildCard(i, islands[i]));
    }
    selectIsland(Math.min(state.selected, islands.length - 1));
  }

  function buildCard(i, isl) {
    var card = document.createElement("div");
    card.className = "island-card";
    card.dataset.i = String(i);

    var head = document.createElement("div");
    head.className = "island-head";
    var chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = !!isl.enabled;
    chk.title = "enabled";
    var name = document.createElement("span");
    name.className = "name";
    name.textContent = "Island " + (i + 1);
    var del = document.createElement("button");
    del.className = "danger isl-del";
    del.title = "remove island";
    del.textContent = "\u00d7";
    head.appendChild(chk);
    head.appendChild(name);
    head.appendChild(del);

    var pos = document.createElement("div");
    pos.className = "island-pos";
    pos.appendChild(posInput("X", "isl-x", isl.cx));
    pos.appendChild(posInput("Y", "isl-y", isl.cy));

    var seedRow = document.createElement("div");
    seedRow.className = "island-seed";
    var seedLabel = document.createElement("label");
    seedLabel.textContent = "Seed ";
    seedLabel.title = "Random seed for this island only — rerolling it leaves the other islands untouched";
    var seedInp = document.createElement("input");
    seedInp.type = "number";
    seedInp.className = "isl-seed";
    seedInp.min = "0";
    seedInp.max = "4294967295";
    seedInp.step = "1";
    seedInp.value = String(isl.seed >>> 0);
    seedLabel.appendChild(seedInp);
    var reroll = document.createElement("button");
    reroll.type = "button";
    reroll.className = "small isl-reroll";
    reroll.textContent = "\u21bb";
    reroll.title = "reroll this island's seed";
    seedRow.appendChild(seedLabel);
    seedRow.appendChild(reroll);

    var sizeRow = sliderRow("Size", "isl-r", 0.02, 0.9, 0.005, isl.radius, Number(isl.radius).toFixed(3));
    var aspVal = isl.aspect == null ? 1 : isl.aspect;
    var aspRow = sliderRow("Aspect", "isl-as", 0.3, 3, 0.01, aspVal, Number(aspVal).toFixed(2));
    var rotRow = sliderRow("Rotation", "isl-a", 0, 360, 1, deg(isl.angle || 0), String(deg(isl.angle || 0)));

    card.appendChild(head);
    card.appendChild(pos);
    card.appendChild(seedRow);
    card.appendChild(sizeRow.row);
    card.appendChild(aspRow.row);
    card.appendChild(rotRow.row);

    chk.addEventListener("change", function () {
      state.config.islands[i].enabled = chk.checked;
      changed();
    });
    del.addEventListener("click", function () {
      state.config.islands.splice(i, 1);
      if (state.config.islands.length === 0) {
        state.config.islands.push(defaultIsland(0.5, 0.5));
      }
      renderIslandCards();
      changed();
    });
    var xi = card.getElementsByClassName("isl-x")[0];
    var yi = card.getElementsByClassName("isl-y")[0];
    xi.addEventListener("input", function () {
      state.config.islands[i].cx = Number(xi.value) || 0;
      Preview2D.constrain(state.config.islands[i]);
      xi.value = Number(state.config.islands[i].cx).toFixed(2);
      Preview2D.setConfig(state.config);
      changed();
    });
    yi.addEventListener("input", function () {
      state.config.islands[i].cy = Number(yi.value) || 0;
      Preview2D.constrain(state.config.islands[i]);
      yi.value = Number(state.config.islands[i].cy).toFixed(2);
      Preview2D.setConfig(state.config);
      changed();
    });
    sizeRow.input.addEventListener("input", function () {
      state.config.islands[i].radius = Number(sizeRow.input.value);
      sizeRow.output.textContent = Number(sizeRow.input.value).toFixed(3);
      Preview2D.constrain(state.config.islands[i]);
      syncCard(i);
      Preview2D.setConfig(state.config);
      changed();
    });
    aspRow.input.addEventListener("input", function () {
      state.config.islands[i].aspect = Number(aspRow.input.value);
      aspRow.output.textContent = Number(aspRow.input.value).toFixed(2);
      Preview2D.constrain(state.config.islands[i]);
      syncCard(i);
      Preview2D.setConfig(state.config);
      changed();
    });
    rotRow.input.addEventListener("input", function () {
      state.config.islands[i].angle = Number(rotRow.input.value) * Math.PI / 180;
      rotRow.output.textContent = rotRow.input.value;
      Preview2D.constrain(state.config.islands[i]);
      syncCard(i);
      Preview2D.setConfig(state.config);
      changed();
    });
    seedInp.addEventListener("change", function () {
      var v = clampInt(seedInp.value, 0, 4294967295, state.config.islands[i].seed >>> 0);
      state.config.islands[i].seed = v;
      seedInp.value = String(v);
      changed();
    });
    reroll.addEventListener("click", function () {
      state.config.islands[i].seed = randomSeed();
      seedInp.value = String(state.config.islands[i].seed);
      changed();
      schedulePreview(true);
    });
    card.addEventListener("mousedown", function () {
      selectIsland(i);
    });
    return card;
  }

  function posInput(label, cls, val) {
    var l = document.createElement("label");
    l.textContent = label + " ";
    var inp = document.createElement("input");
    inp.type = "number";
    inp.className = cls;
    inp.step = "0.01";
    inp.value = Number(val).toFixed(2);
    l.appendChild(inp);
    return l;
  }

  function sliderRow(label, cls, min, max, step, val, text) {
    var row = document.createElement("div");
    row.className = "row slider-row";
    var l = document.createElement("label");
    l.textContent = label;
    var inp = document.createElement("input");
    inp.type = "range";
    inp.className = cls;
    inp.min = String(min);
    inp.max = String(max);
    inp.step = String(step);
    inp.value = String(val);
    var out = document.createElement("output");
    out.textContent = text;
    row.appendChild(l);
    row.appendChild(inp);
    row.appendChild(out);
    return { row: row, input: inp, output: out };
  }

  function selectIsland(i) {
    if (i < 0) return;
    state.selected = i;
    var cards = document.getElementsByClassName("island-card");
    for (var k = 0; k < cards.length; k++) {
      if (Number(cards[k].dataset.i) === i) {
        cards[k].classList.add("active");
      } else {
        cards[k].classList.remove("active");
      }
    }
  }

  function syncCard(i) {
    var card = document.querySelector('.island-card[data-i="' + i + '"]');
    if (!card) return;
    var isl = state.config.islands[i];
    var xi = card.getElementsByClassName("isl-x")[0];
    var yi = card.getElementsByClassName("isl-y")[0];
    if (document.activeElement !== xi) xi.value = Number(isl.cx).toFixed(2);
    if (document.activeElement !== yi) yi.value = Number(isl.cy).toFixed(2);
    var r = card.getElementsByClassName("isl-r")[0];
    r.value = String(isl.radius);
    r.nextElementSibling.textContent = Number(isl.radius).toFixed(3);
    var aspEl = card.getElementsByClassName("isl-as")[0];
    if (aspEl) {
      var av = isl.aspect == null ? 1 : isl.aspect;
      aspEl.value = String(av);
      aspEl.nextElementSibling.textContent = Number(av).toFixed(2);
    }
    var a = card.getElementsByClassName("isl-a")[0];
    var d = deg(isl.angle || 0);
    a.value = String(d);
    a.nextElementSibling.textContent = String(d);
    var sd = card.getElementsByClassName("isl-seed")[0];
    if (sd && document.activeElement !== sd) sd.value = String(isl.seed >>> 0);
  }

  function defaultIsland(cx, cy) {
    return {
      cx: cx,
      cy: cy,
      radius: 0.18,
      aspect: 1.0,
      angle: 0,
      seed: randomSeed(),
      enabled: true
    };
  }

  /* ================= preview / generate ================= */

  function changed() {
    state.fullDirty = true;
    markExports();
    schedulePreview();
  }

  function schedulePreview(immediate) {
    if (state.previewTimer) clearTimeout(state.previewTimer);
    if (immediate) {
      runPreview();
    } else {
      state.previewTimer = setTimeout(runPreview, 350);
    }
  }

  function runPreview() {
    if (state.previewTimer) {
      clearTimeout(state.previewTimer);
      state.previewTimer = null;
    }
    readUI();
    var seq = ++state.previewSeq;
    var size = parseInt($("preview-res").value, 10) || 512;
    var cfg = JSON.parse(JSON.stringify(state.config));
    $("preview-ms").textContent = "preview \u2026";
    fetch("/api/preview?size=" + size, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: cfg })
    })
      .then(function (r) { return r.json(); })
      .then(function (job) {
        if (seq !== state.previewSeq) return; // stale response
        if (job.status !== "done") {
          $("stats-line").textContent = "preview failed: " + (job.error || job.status);
          $("preview-ms").textContent = "";
          return;
        }
        state.previewId = job.id;
        return fetch("/api/heights/" + job.id)
          .then(function (r) { return r.arrayBuffer(); })
          .then(function (buf) {
            if (seq !== state.previewSeq) return;
            var arr = new Float32Array(buf);
            state.heights = arr;
            state.lastW = job.width;
            state.lastH = job.height;
            Preview2D.draw(arr, job.width, job.height, state.config);
            Preview3D.draw(arr, job.width, job.height, state.config.sea_level);
            showStats(job);
          });
      })
      .catch(function (e) {
        if (seq !== state.previewSeq) return;
        $("stats-line").textContent = "preview error: " + e;
      });
  }

  function showStats(job) {
    var s = job.stats;
    if (!s) return;
    $("stats-line").textContent =
      "min " + s.min.toFixed(3) + " \u00b7 max " + s.max.toFixed(3) +
      " \u00b7 mean " + s.mean.toFixed(3) +
      " \u00b7 land " + (s.land_frac * 100).toFixed(1) + "%";
    $("preview-ms").textContent =
      "preview " + job.width + "\u00d7" + job.height + " in " + job.ms + "ms";
  }

  function generateFull() {
    readUI();
    var cfg = JSON.parse(JSON.stringify(state.config));
    var btn = $("generate-full");
    btn.disabled = true;
    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: cfg })
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        state.fullId = res.id;
        pollStatus(res.id);
      })
      .catch(function (e) {
        btn.disabled = false;
        $("preview-ms").textContent = "generate error: " + e;
      });
  }

  function pollStatus(id) {
    if (state.statusTimer) clearTimeout(state.statusTimer);
    fetch("/api/status/" + id)
      .then(function (r) { return r.json(); })
      .then(function (st) {
        var btn = $("generate-full");
        if (st.status === "running") {
          btn.textContent = "Generating " + Math.round((st.progress || 0) * 100) + "%";
          state.statusTimer = setTimeout(function () { pollStatus(id); }, 350);
          return;
        }
        btn.disabled = false;
        btn.textContent = "Generate Full Res";
        if (st.status === "done") {
          state.fullDirty = false;
          markExports();
          $("preview-ms").textContent = "full generate " + st.ms + "ms";
        } else {
          $("stats-line").textContent = "generate failed: " + (st.error || st.status);
        }
      })
      .catch(function () {
        state.statusTimer = setTimeout(function () { pollStatus(id); }, 700);
      });
  }

  function markExports() {
    var on = !!state.fullId && !state.fullDirty;
    $("export-png16").disabled = !on;
    $("export-raw16").disabled = !on;
    $("export-exr").disabled = !on;
  }

  function exportAs(fmt) {
    if (!state.fullId) return;
    var url = "/api/export/" + state.fullId +
      "?format=" + fmt + "&sea_mode=remap&scale=1";
    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("export failed " + r.status);
        return r.blob();
      })
      .then(function (b) {
        var a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        var name = "hmg_" + state.config.width + "x" + state.config.height + "." + fmt;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      })
      .catch(function (e) {
        $("preview-ms").textContent = String(e);
      });
  }

  /* ================= save / load ================= */

  function saveConfig() {
    readUI();
    var blob = new Blob([JSON.stringify(state.config, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "heightmap-config.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
  }

  function loadConfig(file) {
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var cfg = JSON.parse(String(reader.result));
        fetch("/api/defaults")
          .then(function (r) { return r.json(); })
          .then(function (d) {
            var base = d.config;
            base.width = cfg.width || base.width;
            base.height = cfg.height || base.height;
            base.seed = cfg.seed != null ? cfg.seed : base.seed;
            base.sea_level = cfg.sea_level != null ? cfg.sea_level : base.sea_level;
            base.mode = cfg.mode || base.mode;
            if (cfg.noise) {
              for (var k in cfg.noise) {
                if (Object.prototype.hasOwnProperty.call(cfg.noise, k)) base.noise[k] = cfg.noise[k];
              }
            }
            if (cfg.erosion) {
              for (var k2 in cfg.erosion) {
                if (Object.prototype.hasOwnProperty.call(cfg.erosion, k2)) base.erosion[k2] = cfg.erosion[k2];
              }
            }
            if (cfg.smoothing) {
              for (var k3 in cfg.smoothing) {
                if (Object.prototype.hasOwnProperty.call(cfg.smoothing, k3)) base.smoothing[k3] = cfg.smoothing[k3];
              }
            }
            if (Array.isArray(cfg.islands) && cfg.islands.length) base.islands = cfg.islands;
            applyToUI(base);
            changed();
            schedulePreview(true);
          });
      } catch (e) {
        $("preview-ms").textContent = "load failed: " + e;
      }
    };
    reader.readAsText(file);
  }

  /* ================= wiring ================= */

  function bind() {
    // header
    $("seed").addEventListener("change", function () { changed(); });
    $("seed-random").addEventListener("click", function () {
      $("seed").value = String(Math.floor(Math.random() * 2147483647));
      changed();
      schedulePreview(true);
    });
    $("preview-res").addEventListener("change", function () { schedulePreview(true); });
    $("generate-full").addEventListener("click", generateFull);
    $("export-png16").addEventListener("click", function () { exportAs("png16"); });
    $("export-raw16").addEventListener("click", function () { exportAs("raw16"); });
    $("export-exr").addEventListener("click", function () { exportAs("exr"); });
    $("save-cfg").addEventListener("click", saveConfig);
    $("load-cfg").addEventListener("click", function () { $("load-cfg-file").click(); });
    $("load-cfg-file").addEventListener("change", function () {
      if (this.files && this.files[0]) loadConfig(this.files[0]);
      this.value = "";
    });

    // map
    $("mode").addEventListener("change", function () {
      readUI();
      updateModeUI();
      changed();
    });
    $("map-w").addEventListener("input", function () {
      if ($("wh-linked").checked) $("map-h").value = $("map-w").value;
      changed();
    });
    $("map-h").addEventListener("input", function () {
      if ($("wh-linked").checked) $("map-w").value = $("map-h").value;
      changed();
    });
    var presets = $("ue-presets").getElementsByTagName("button");
    for (var i = 0; i < presets.length; i++) {
      presets[i].addEventListener("click", function () {
        $("map-w").value = this.dataset.w;
        $("map-h").value = this.dataset.h;
        changed();
      });
    }
    bindSlider("sea-level", "sea-level-val", 3, function () { changed(); });
    bindSlider("noise-scale", "noise-scale-val", 1, function () { changed(); });
    bindSlider("detail-amp", "detail-amp-val", 2, function () { changed(); });
    bindSlider("coast-warp", "coast-warp-val", 2, function () { changed(); });
    bindSlider("noise-persistence", "noise-persistence-val", 2, function () { changed(); });
    bindSlider("noise-octaves", "noise-octaves-val", 0, function () { changed(); });
    bindSlider("smoothing-thermal", "smoothing-thermal-val", 2, function () { changed(); });
    bindSlider("smoothing-blur", "smoothing-blur-val", 2, function () { changed(); });

    $("noise-reset").addEventListener("click", function () {
      $("noise-scale").value = "2.5";
      $("noise-scale-val").textContent = "2.5";
      $("detail-amp").value = "0.4";
      $("detail-amp-val").textContent = "0.40";
      $("coast-warp").value = "0.35";
      $("coast-warp-val").textContent = "0.35";
      $("noise-persistence").value = "0.5";
      $("noise-persistence-val").textContent = "0.50";
      $("noise-octaves").value = "6";
      $("noise-octaves-val").textContent = "6";
      changed();
    });

    // erosion
    $("erosion-enabled").addEventListener("change", function () {
      updateErosionUI();
      changed();
    });
    bindSlider("erosion-droplets", "erosion-droplets-val", 0, function () { changed(); });
    bindSlider("erosion-steps", "erosion-steps-val", 0, function () { changed(); });

    // islands
    $("island-add").addEventListener("click", function () {
      var isl = defaultIsland(0.5, 0.5);
      state.config.islands.push(isl);
      renderIslandCards();
      selectIsland(state.config.islands.length - 1);
      changed();
    });
    $("island-reroll").addEventListener("click", function () {
      var islands = state.config.islands;
      for (var k = 0; k < islands.length; k++) islands[k].seed = randomSeed();
      renderIslandCards();
      changed();
      schedulePreview(true);
    });

    // preview handles
    Preview2D.setOnChange(function (idx, isl) {
      state.config.islands[idx].cx = isl.cx;
      state.config.islands[idx].cy = isl.cy;
      state.config.islands[idx].radius = isl.radius;
      state.config.islands[idx].angle = isl.angle;
      syncCard(idx);
      changed();
    });
    Preview2D.setOnAdd(function (ix, iy) {
      var isl = defaultIsland(ix, iy);
      Preview2D.constrain(isl);
      state.config.islands.push(isl);
      renderIslandCards();
      selectIsland(state.config.islands.length - 1);
      changed();
    });
    Preview2D.setOnSelect(function (idx) {
      selectIsland(idx);
    });

    // resize
    window.addEventListener("resize", function () {
      Preview2D.resize();
      Preview3D.resize();
    });
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () {
        Preview2D.resize();
        Preview3D.resize();
      });
      ro.observe(document.getElementById("pane2d-wrap"));
      ro.observe(document.getElementById("pane3d-wrap"));
    }
  }

  function bindSlider(id, outId, digits, cb) {
    var el = $(id);
    var out = $(outId);
    el.addEventListener("input", function () {
      var v = Number(el.value);
      out.textContent = digits === 0 ? String(Math.round(v)) : v.toFixed(digits);
      cb();
    });
  }

  /* ================= init ================= */

  function init() {
    fetch("/api/defaults")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        applyToUI(d.config);
        bind();
        markExports();
        schedulePreview(true);
      })
      .catch(function (e) {
        // server restarting / unreachable: keep retrying instead of
        // leaving a dead page behind
        var el = document.getElementById("stats-line");
        if (el) el.textContent = "waiting for server \u2026 (" + e + ")";
        setTimeout(init, 1500);
      });
  }
  init();
})();
