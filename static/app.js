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
    previewBusy: false,   // a preview request is in flight
    previewPending: false, // config changed while busy: render again after
    statusTimer: null,
    selected: 0,
    heights: null,
    lastW: 0,
    lastH: 0,
    undoStack: [],     // config snapshots, oldest first
    redoStack: [],     // states left behind by undo, waiting to come back
    undoLast: null,    // JSON of the last recorded state
    undoSkipNext: false // ignore the snapshot produced by restoring a state
  };

  var UNDO_MAX = 50;

  /* ================= config <-> UI ================= */

  function applyToUI(cfg) {
    state.config = cfg;
    ensureIslandFields();
    ensureLandscapeFields();
    $("seed").value = cfg.seed;
    $("mode").value = cfg.mode;
    syncFullRes(cfg.width, cfg.height);
    $("sea-level").value = cfg.sea_level;
    $("sea-level-val").textContent = Number(cfg.sea_level).toFixed(3);
    $("land-height").value = cfg.landscape.land_height;
    $("land-height-val").textContent = Number(cfg.landscape.land_height).toFixed(3);
    $("land-peak").value = cfg.landscape.mountain_height;
    $("land-peak-val").textContent = Number(cfg.landscape.mountain_height).toFixed(2);
    $("land-cover").value = cfg.landscape.mountain_coverage;
    $("land-cover-val").textContent = Number(cfg.landscape.mountain_coverage).toFixed(2);
    $("land-msize").value = cfg.landscape.mountain_size;
    $("land-msize-val").textContent = Number(cfg.landscape.mountain_size).toFixed(2);
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
    cfg.seed = clampInt($("seed").value, 0, 2147483647,
      TOOL_DEFAULTS && TOOL_DEFAULTS.seed != null ? TOOL_DEFAULTS.seed : 0);
    cfg.mode = $("mode").value;
    var fr = readFullRes();
    cfg.width = fr.w;
    cfg.height = fr.h;
    cfg.sea_level = Number($("sea-level").value);
    ensureLandscapeFields();
    cfg.landscape.land_height = Number($("land-height").value);
    cfg.landscape.mountain_height = Number($("land-peak").value);
    cfg.landscape.mountain_coverage = Number($("land-cover").value);
    cfg.landscape.mountain_size = Number($("land-msize").value);
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

  /* Full-res dropdown: shortcuts for the exported map size, with a Custom
     entry that exposes free W/H fields (non-square allowed) so the tool is
     not tied to Unreal's 2^n+1 sizes. Previews never use it: they are
     capped at 1024 and rendered at their own size. */
  var FULL_RES_MAX = 4096;

  function clampSize(v) {
    return clampInt(v, 64, FULL_RES_MAX, 1024);
  }

  /* Reflect the config's size in the dropdown. A size that is not a preset
     (a non-square map, or an off-list value) switches the select to
     "Custom…" and fills the W/H fields instead of being replaced. */
  function syncFullRes(w, h) {
    w = clampSize(w);
    h = clampSize(h);
    var sel = $("full-res");
    var v = (w === h) ? String(w) : "";
    var preset = v ? sel.querySelector('option[value="' + v + '"]') : null;
    $("custom-w").value = w;
    $("custom-h").value = h;
    $("custom-size-row").style.display = preset ? "none" : "";
    sel.value = preset ? v : "__custom";
  }

  function readFullRes() {
    var sel = $("full-res");
    if (sel.value === "__custom") {
      return { w: clampSize($("custom-w").value), h: clampSize($("custom-h").value) };
    }
    var s = clampSize(sel.value);
    return { w: s, h: s };
  }

  /* Per-island seeds: every island owns one, so rerolling an island only
     reshapes that island. Kept in sync with core.noise.island_seed(). */
  function randomSeed() {
    return Math.floor(Math.random() * 4294967296) >>> 0;
  }

  function islandSeed(base, index) {
    return (Math.imul(base >>> 0, 73856093) ^ Math.imul(index, 19349663)) >>> 0;
  }

  /* The tool's default values live in ONE place: defaults.json at the
     project root. The backend loads it into DEFAULT_CONFIG, serves it
     through /api/defaults, and init() caches the response here — nothing
     in this file may hardcode a default of its own. */
  var TOOL_DEFAULTS = null;

  /* Central island template (defaults.json's first island), or null. */
  function centralIsland() {
    return (TOOL_DEFAULTS && TOOL_DEFAULTS.islands && TOOL_DEFAULTS.islands[0]) || null;
  }

  /* A single field of that template — used wherever a value is missing
     and must be filled with the tool's default rather than a local copy. */
  function defaultOf(key) {
    var isl = centralIsland();
    return isl ? isl[key] : undefined;
  }

  function centralLandscape() {
    return (TOOL_DEFAULTS && TOOL_DEFAULTS.landscape) || {};
  }

  function ensureIslandFields() {
    var islands = state.config.islands;
    for (var i = 0; i < islands.length; i++) {
      var isl = islands[i];
      if (typeof isl.seed !== "number" || !isFinite(isl.seed)) {
        isl.seed = islandSeed(state.config.seed, i); // pre-seed configs stay reproducible
      }
      isl.seed = isl.seed >>> 0;
      // The split seeds are materialized once so the card shows the real
      // values; until one is rerolled it stays equal to the island seed.
      if (typeof isl.shape_seed !== "number" || !isFinite(isl.shape_seed)) {
        isl.shape_seed = isl.seed;
      }
      isl.shape_seed = isl.shape_seed >>> 0;
      if (typeof isl.terrain_seed !== "number" || !isFinite(isl.terrain_seed)) {
        isl.terrain_seed = isl.seed;
      }
      isl.terrain_seed = isl.terrain_seed >>> 0;
      // Missing values come from the central defaults — only the seeds
      // above are ever random. Legacy configs predate these fields.
      ["land_height", "mountain_height", "mountain_coverage", "mountain_size",
       "shape_variety", "coast_slope"].forEach(function (k) {
        if (typeof isl[k] !== "number" || !isFinite(isl[k])) {
          var v = defaultOf(k);
          if (typeof v === "number") isl[k] = v;
        }
      });
      if (typeof isl.shape_variety === "number") {
        isl.shape_variety = Math.min(1, Math.max(0, isl.shape_variety));
      }
      if (typeof isl.coast_slope === "number") {
        isl.coast_slope = Math.min(1, Math.max(0, isl.coast_slope));
      }
    }
  }

  /* Landscape elevation model. Legacy saved configs predate the block, so
     fill it in from the central defaults rather than letting readUI write
     into undefined. */
  function ensureLandscapeFields() {
    var l = state.config.landscape;
    if (!l || typeof l !== "object") l = state.config.landscape = {};
    var d = centralLandscape();
    Object.keys(d).forEach(function (k) {
      if (typeof l[k] !== "number" || !isFinite(l[k])) l[k] = d[k];
    });
    return l;
  }

  function updateModeUI() {
    var isl = $("islands-panel");
    var islands = state.config.mode === "islands";
    isl.style.display = islands ? "" : "none";
    var land = $("landscape-panel");
    if (land) land.style.display = islands ? "none" : "";
    var seedField = $("global-seed-field");
    if (seedField) seedField.style.display = islands ? "none" : ""; // islands carry their own seeds
    var seaRow = $("sea-level-row");
    if (seaRow) seaRow.style.display = islands ? "" : "none";
    // Coast roughness only shapes island shorelines; landscape has no coast.
    var coastRow = $("coast-warp-row");
    if (coastRow) coastRow.style.display = islands ? "" : "none";
    // The same slider means fine relief on an island and lowland roll on a
    // landscape tile, so name it for what it does in the current mode.
    var dlabel = $("detail-amp-label");
    if (dlabel) {
      dlabel.textContent = islands ? "Terrain detail" : "Plain roll";
      dlabel.title = islands
        ? "Amplitude of fine noise detail"
        : "How much the lowland rolls up and down around the plain height";
    }
    var hint = $("stats-hint");
    if (hint) {
      hint.textContent = islands
        ? "\u2022 min / max / mean height and land % above sea level"
        : "\u2022 min / max / mean height of the tile";
    }
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

    /* Two seed rows per island: the outline (footprint + rotation) and the
       surface (plain, mountains, shore band) can be rerolled one at a time,
       so you can keep a coastline you like and reshuffle the terrain. */
    function seedRowEl(labelText, cls, value, title) {
      var row = document.createElement("div");
      row.className = "island-seed";
      var lab = document.createElement("label");
      lab.textContent = labelText + " ";
      lab.title = title;
      var inp = document.createElement("input");
      inp.type = "number";
      inp.className = cls;
      inp.min = "0";
      inp.max = "4294967295";
      inp.step = "1";
      inp.value = String(value >>> 0);
      lab.appendChild(inp);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "small " + cls + "-reroll";
      btn.textContent = "\u21bb";
      btn.title = "reroll " + labelText.toLowerCase() + " only";
      row.appendChild(lab);
      row.appendChild(btn);
      return { row: row, input: inp, reroll: btn };
    }
    var shapeSeedRow = seedRowEl("Shape seed", "isl-shape-seed", isl.shape_seed,
      "Outline seed — footprint lobes, bays, peninsulas and rotation. Lock it to keep the coast while the terrain changes");
    var terrSeedRow = seedRowEl("Terrain seed", "isl-terrain-seed", isl.terrain_seed,
      "Surface seed — plain relief, mountains and the shore band. Reroll it to reshape the land under the same outline");

    var sizeRow = sliderRow("Size", "isl-r", 0.02, 0.9, 0.005, isl.radius, Number(isl.radius).toFixed(3));
    var aspVal = isl.aspect == null ? defaultOf("aspect") : isl.aspect;
    var aspRow = sliderRow("Aspect", "isl-as", 0.3, 3, 0.01, aspVal, Number(aspVal).toFixed(2));
    var shapeVal = isl.shape_variety == null ? defaultOf("shape_variety") : isl.shape_variety;
    var shapeRow = sliderRow("Shape", "isl-shape", 0, 1, 0.01, shapeVal,
      Number(shapeVal).toFixed(2),
      "Footprint variety for this island only: 0 = circle, higher = seed-driven bays, peninsulas and lobes");
    var coastVal = isl.coast_slope == null ? defaultOf("coast_slope") : isl.coast_slope;
    var coastRow = sliderRow("Coast", "isl-coast", 0, 1, 0.01, coastVal,
      Number(coastVal).toFixed(2),
      "Shoreline for this island only: 0 = sharp drop at the waterline, 1 = long gentle slope into the sea");
    var rotRow = sliderRow("Rotation", "isl-a", 0, 360, 1, deg(isl.angle || 0), String(deg(isl.angle || 0)));

    var sub = document.createElement("div");
    sub.className = "island-sub";
    sub.textContent = "ELEVATION";
    var landRow = sliderRow("Land", "isl-land", 0.02, 0.5, 0.005, isl.land_height,
      Number(isl.land_height).toFixed(3),
      "Absolute height of this island's flat plain — keep it above sea level");
    var peakRow = sliderRow("Peaks", "isl-peak", 0, 0.6, 0.01, isl.mountain_height,
      Number(isl.mountain_height).toFixed(2),
      "How far the mountains rise above the plain");
    var covRow = sliderRow("Coverage", "isl-cov", 0, 1, 0.01, isl.mountain_coverage,
      Number(isl.mountain_coverage).toFixed(2),
      "How much of the island gets high ground (0 = flat atoll, 1 = mountains everywhere)");
    var sizeRow2 = sliderRow("Mount. size", "isl-msize", 0.5, 2.5, 0.05, isl.mountain_size,
      Number(isl.mountain_size).toFixed(2),
      "How broad each mountain massif is — small hills up to one big range");

    card.appendChild(head);
    card.appendChild(pos);
    card.appendChild(shapeSeedRow.row);
    card.appendChild(terrSeedRow.row);
    card.appendChild(sizeRow.row);
    card.appendChild(aspRow.row);
    card.appendChild(shapeRow.row);
    card.appendChild(coastRow.row);
    card.appendChild(rotRow.row);
    card.appendChild(sub);
    card.appendChild(landRow.row);
    card.appendChild(peakRow.row);
    card.appendChild(covRow.row);
    card.appendChild(sizeRow2.row);

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
    shapeRow.input.addEventListener("input", function () {
      state.config.islands[i].shape_variety = Number(shapeRow.input.value);
      shapeRow.output.textContent = Number(shapeRow.input.value).toFixed(2);
      Preview2D.setConfig(state.config);
      changed();
    });
    coastRow.input.addEventListener("input", function () {
      state.config.islands[i].coast_slope = Number(coastRow.input.value);
      coastRow.output.textContent = Number(coastRow.input.value).toFixed(2);
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
    function bindSeed(row, key) {
      row.input.addEventListener("change", function () {
        var v = clampInt(row.input.value, 0, 4294967295,
          state.config.islands[i][key] >>> 0);
        state.config.islands[i][key] = v;
        row.input.value = String(v);
        changed();
      });
      row.reroll.addEventListener("click", function () {
        state.config.islands[i][key] = randomSeed();
        row.input.value = String(state.config.islands[i][key]);
        changed();
        schedulePreview(true);
      });
    }
    bindSeed(shapeSeedRow, "shape_seed");
    bindSeed(terrSeedRow, "terrain_seed");
    function bindElevation(row, key, digits) {
      row.input.addEventListener("input", function () {
        var v = Number(row.input.value);
        state.config.islands[i][key] = v;
        row.output.textContent = digits === 3 ? v.toFixed(3) : v.toFixed(2);
        Preview2D.setConfig(state.config);
        changed();
      });
    }
    bindElevation(landRow, "land_height", 3);
    bindElevation(peakRow, "mountain_height", 2);
    bindElevation(covRow, "mountain_coverage", 2);
    bindElevation(sizeRow2, "mountain_size", 2);
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

  function sliderRow(label, cls, min, max, step, val, text, title) {
    var row = document.createElement("div");
    row.className = "row slider-row";
    var l = document.createElement("label");
    l.textContent = label;
    if (title) l.title = title;
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
      var av = isl.aspect == null ? defaultOf("aspect") : isl.aspect;
      aspEl.value = String(av);
      aspEl.nextElementSibling.textContent = Number(av).toFixed(2);
    }
    var shEl = card.getElementsByClassName("isl-shape")[0];
    if (shEl && document.activeElement !== shEl) {
      var sv = isl.shape_variety == null ? defaultOf("shape_variety") : isl.shape_variety;
      shEl.value = String(sv);
      shEl.nextElementSibling.textContent = Number(sv).toFixed(2);
    }
    var coEl = card.getElementsByClassName("isl-coast")[0];
    if (coEl && document.activeElement !== coEl) {
      var cov2 = isl.coast_slope == null ? 0.5 : isl.coast_slope;
      coEl.value = String(cov2);
      coEl.nextElementSibling.textContent = Number(cov2).toFixed(2);
    }
    var a = card.getElementsByClassName("isl-a")[0];
    var d = deg(isl.angle || 0);
    a.value = String(d);
    a.nextElementSibling.textContent = String(d);
    var ssd = card.getElementsByClassName("isl-shape-seed")[0];
    if (ssd && document.activeElement !== ssd) {
      ssd.value = String((isl.shape_seed != null ? isl.shape_seed : isl.seed) >>> 0);
    }
    var tsd = card.getElementsByClassName("isl-terrain-seed")[0];
    if (tsd && document.activeElement !== tsd) {
      tsd.value = String((isl.terrain_seed != null ? isl.terrain_seed : isl.seed) >>> 0);
    }
    var ld = card.getElementsByClassName("isl-land")[0];
    if (ld && document.activeElement !== ld) {
      ld.value = String(isl.land_height);
      ld.nextElementSibling.textContent = Number(isl.land_height).toFixed(3);
    }
    var pk = card.getElementsByClassName("isl-peak")[0];
    if (pk && document.activeElement !== pk) {
      pk.value = String(isl.mountain_height);
      pk.nextElementSibling.textContent = Number(isl.mountain_height).toFixed(2);
    }
    var cv = card.getElementsByClassName("isl-cov")[0];
    if (cv && document.activeElement !== cv) {
      cv.value = String(isl.mountain_coverage);
      cv.nextElementSibling.textContent = Number(isl.mountain_coverage).toFixed(2);
    }
    var ms = card.getElementsByClassName("isl-msize")[0];
    if (ms && document.activeElement !== ms) {
      ms.value = String(isl.mountain_size);
      ms.nextElementSibling.textContent = Number(isl.mountain_size).toFixed(2);
    }
  }

  /* A freshly added island copies the central default island (defaults.json
     via /api/defaults) and only draws new seeds — every slider starts at
     the tool's default, never at a random value. */
  function defaultIsland(cx, cy) {
    var seed = randomSeed();
    var isl = centralIsland()
      ? JSON.parse(JSON.stringify(centralIsland()))
      : {};
    isl.cx = cx;
    isl.cy = cy;
    isl.seed = seed;
    isl.shape_seed = seed;
    isl.terrain_seed = seed;
    isl.enabled = true;
    return isl;
  }

  /* ================= preview / generate ================= */

  function changed() {
    state.fullDirty = true;
    markExports();
    schedulePreview();
  }

  /* Undo works on whole configs. runPreview() is the one place where the
     DOM has just been read back into state.config, so that is where a change
     is recorded: one entry per rendered state, which coalesces a slider drag
     (a burst of `input` events) into a single undo step instead of one per
     pixel dragged. */
  function snapshotForUndo() {
    var snap = JSON.stringify(state.config);
    if (state.undoSkipNext) {
      state.undoSkipNext = false;
      state.undoLast = snap; // canonical state after applying an undo
      return;
    }
    if (state.undoLast === null) {
      state.undoLast = snap;
      return;
    }
    if (snap === state.undoLast) return;
    state.undoStack.push(state.undoLast);
    if (state.undoStack.length > UNDO_MAX) state.undoStack.shift();
    state.redoStack.length = 0; // a new change invalidates the forward path
    state.undoLast = snap;
    updateHistoryUI();
  }

  /* Shared by undo and redo: restore a snapshot and re-render it. */
  function restoreSnapshot(snap) {
    state.undoSkipNext = true;
    state.undoLast = snap;
    applyToUI(JSON.parse(snap));
    state.fullDirty = true; // the full-res render no longer matches
    markExports();
    schedulePreview(true);
  }

  function undo() {
    if (!state.undoStack.length) return;
    var prev = state.undoStack.pop();
    state.redoStack.push(state.undoLast); // keep the state we are leaving
    if (state.redoStack.length > UNDO_MAX) state.redoStack.shift();
    restoreSnapshot(prev);
    updateHistoryUI();
  }

  function redo() {
    if (!state.redoStack.length) return;
    var next = state.redoStack.pop();
    state.undoStack.push(state.undoLast);
    restoreSnapshot(next);
    updateHistoryUI();
  }

  function updateHistoryUI() {
    var u = $("undo");
    var r = $("redo");
    if (u) u.disabled = !state.undoStack.length;
    if (r) r.disabled = !state.redoStack.length;
  }

  /* Full res only affects the full generate, never the preview, so this
     does not schedule a preview (which would just re-render the same
     picture at the preview size). */
  function fullResChanged() {
    readUI();
    state.fullDirty = true;
    markExports();
  }

  function schedulePreview(immediate) {
    if (state.previewTimer) clearTimeout(state.previewTimer);
    if (immediate) {
      state.previewTimer = null;
      requestPreview();
    } else {
      state.previewTimer = setTimeout(requestPreview, 350);
    }
  }

  /* One preview at a time. While a render is in flight, further changes only
     mark the newest config as pending, so dragging a slider queues one
     follow-up instead of a row of 5-second jobs. */
  function requestPreview() {
    if (state.previewTimer) {
      clearTimeout(state.previewTimer);
      state.previewTimer = null;
    }
    if (state.previewBusy) {
      state.previewPending = true;
      return;
    }
    runPreview();
  }

  function runPreview() {
    readUI();
    snapshotForUndo();
    var seq = ++state.previewSeq;
    var size = parseInt($("preview-res").value, 10) || 512;
    var cfg = JSON.parse(JSON.stringify(state.config));
    state.previewBusy = true;
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
            Preview3D.draw(arr, job.width, job.height, previewSea());
            showStats(job);
          });
      })
      .catch(function (e) {
        if (seq !== state.previewSeq) return;
        $("stats-line").textContent = "preview error: " + e;
      })
      .then(function () {
        state.previewBusy = false;
        if (state.previewPending) {
          state.previewPending = false;
          requestPreview();
        }
      });
  }

  /* Landscape has no sea, whatever the (hidden) sea-level slider still says:
     previews must never paint water on an inland tile. */
  function previewSea() {
    return state.config.mode === "landscape" ? 0 : Number(state.config.sea_level);
  }

  function showStats(job) {
    var s = job.stats;
    if (!s) return;
    var line = "min " + s.min.toFixed(3) + " \u00b7 max " + s.max.toFixed(3) +
      " \u00b7 mean " + s.mean.toFixed(3);
    // No sea on an inland tile, so a land percentage would always read 100%.
    if (state.config.mode !== "landscape") {
      line += " \u00b7 land " + (s.land_frac * 100).toFixed(1) + "%";
    }
    $("stats-line").textContent = line;
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
    // Masks are companions to the same full-res render. Water needs a sea,
    // so it stays off in landscape mode.
    $("mask-slope").disabled = !on;
    $("mask-water").disabled = !(on && state.config.mode !== "landscape");
  }

  /* Masks are separate downloads at the heightmap's size, not a bundle. */
  function downloadMask(kind) {
    if (!state.fullId) return;
    var url = "/api/masks/" + state.fullId + "?kind=" + kind +
      "&steepness=" + encodeURIComponent($("mask-steepness").value);
    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("mask failed " + r.status);
        return r.blob();
      })
      .then(function (b) {
        var a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = "hmg_" + state.config.width + "x" + state.config.height +
          "_" + kind + ".png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      })
      .catch(function (e) {
        $("preview-ms").textContent = String(e);
      });
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
        var ext = {"png16": ".png", "raw16": ".raw", "exr": ".exr"}[fmt];
    var name = "hmg_" + state.config.width + "x" + state.config.height + ext;
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
            base.shape_variety = cfg.shape_variety != null ? cfg.shape_variety : base.shape_variety;
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
            if (cfg.landscape) {
              for (var k4 in cfg.landscape) {
                if (Object.prototype.hasOwnProperty.call(cfg.landscape, k4)) base.landscape[k4] = cfg.landscape[k4];
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
    $("mask-water").addEventListener("click", function () { downloadMask("water"); });
    $("mask-slope").addEventListener("click", function () { downloadMask("slope"); });
    bindSlider("mask-steepness", "mask-steepness-val", 2, function () {});
    $("save-cfg").addEventListener("click", saveConfig);
    $("undo").addEventListener("click", undo);
    $("redo").addEventListener("click", redo);
    // Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z and Ctrl+Y redo; text fields keep
    // their own native undo so typing in a number box is not hijacked
    // (range/checkbox inputs are covered).
    document.addEventListener("keydown", function (e) {
      if (!e.ctrlKey && !e.metaKey) return;
      var key = String(e.key || "").toLowerCase();
      var isRedo = key === "y" || (key === "z" && e.shiftKey);
      var isUndo = key === "z" && !e.shiftKey;
      if (!isRedo && !isUndo) return;
      var t = e.target;
      if (t && t.tagName === "INPUT" &&
          t.type !== "range" && t.type !== "checkbox" &&
          t.type !== "radio") return;
      e.preventDefault();
      if (isRedo) redo(); else undo();
    });
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
    $("full-res").addEventListener("change", function () {
      if (this.value === "__custom") {
        // start from the current size so the fields are never empty
        $("custom-w").value = state.config.width;
        $("custom-h").value = state.config.height;
        $("custom-size-row").style.display = "";
      } else {
        $("custom-size-row").style.display = "none";
      }
      fullResChanged();
    });
    $("custom-w").addEventListener("input", function () {
      if ($("wh-linked").checked) $("custom-h").value = $("custom-w").value;
      fullResChanged();
    });
    $("custom-h").addEventListener("input", function () {
      if ($("wh-linked").checked) $("custom-w").value = $("custom-h").value;
      fullResChanged();
    });
    // On blur/Enter, show the clamped value instead of leaving 99999 in a box.
    function normalizeCustomSize() {
      readUI();
      $("custom-w").value = state.config.width;
      $("custom-h").value = state.config.height;
    }
    $("custom-w").addEventListener("change", normalizeCustomSize);
    $("custom-h").addEventListener("change", normalizeCustomSize);
    bindSlider("sea-level", "sea-level-val", 3, function () { changed(); });
    bindSlider("land-height", "land-height-val", 3, function () { changed(); });
    bindSlider("land-peak", "land-peak-val", 2, function () { changed(); });
    bindSlider("land-cover", "land-cover-val", 2, function () { changed(); });
    bindSlider("land-msize", "land-msize-val", 2, function () { changed(); });
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
      for (var k = 0; k < islands.length; k++) {
        islands[k].seed = randomSeed();
        islands[k].shape_seed = randomSeed();
        islands[k].terrain_seed = randomSeed();
      }
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
        TOOL_DEFAULTS = JSON.parse(JSON.stringify(d.config)); // pristine cache of defaults.json
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
