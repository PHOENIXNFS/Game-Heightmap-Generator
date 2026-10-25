/* 2D heightmap preview: base render + island handles (move/resize/rotate). */
"use strict";

window.Preview2D = (function () {
  var base = document.getElementById("pane2d");
  var overlay = document.getElementById("pane2d-overlay");
  var bctx = base.getContext("2d");
  var octx = overlay.getContext("2d");
  var off = document.createElement("canvas");
  var offctx = off.getContext("2d");

  var heights = null;
  var iw = 0, ih = 0;          // image size in heightmap pixels
  var cfg = null;              // current config
  var view = { scale: 1, ox: 0, oy: 0, dpr: 1 };
  var drag = null;             // { mode, index, startX, startY, orig }
  var onChange = null;         // function (index, partialIsland)
  var onAdd = null;            // function (imgX, imgY)
  var onSelect = null;         // function (index)

  // Colour ramp by normalized height: beach -> grass -> upland scrub ->
  // rock. Bare rock is mostly delivered by slope (see renderBase), so the
  // ramp alone stays green on the lowland instead of turning grey.
  var STOPS = [
    [0.000, 0xc9, 0xb6, 0x8c],   // sand at the waterline
    [0.045, 0x9a, 0xa2, 0x6c],   // dune grass
    [0.120, 0x62, 0x88, 0x4f],   // plain
    [0.380, 0x51, 0x77, 0x47],   // deeper lowland
    [0.600, 0x58, 0x70, 0x4c],   // upland scrub
    [0.800, 0x6e, 0x6c, 0x5d],   // weathered rock
    [1.000, 0x8e, 0x89, 0x7c]    // bare high rock
  ];
  var RC = [0, 0, 0];

  function rampLand(t) {
    for (var i = 1; i < STOPS.length; i++) {
      if (t <= STOPS[i][0] || i === STOPS.length - 1) {
        var a = STOPS[i - 1], b = STOPS[i];
        var f = (t - a[0]) / (b[0] - a[0] + 1e-9);
        if (f < 0) f = 0; if (f > 1) f = 1;
        RC[0] = a[1] + (b[1] - a[1]) * f;
        RC[1] = a[2] + (b[2] - a[2]) * f;
        RC[2] = a[3] + (b[3] - a[3]) * f;
        return RC;
      }
    }
    RC[0] = RC[1] = RC[2] = 255;
    return RC;
  }

  /* Separable box blur of a float plane, clamped at the edges. Used to find
   * ground that sits below its neighbourhood (hollows, valley floors). */
  function boxBlur(src, w, h, r) {
    var tmp = new Float32Array(w * h);
    var out = new Float32Array(w * h);
    var cum = new Float64Array(Math.max(w, h) + 1);
    var x, y, i;
    for (y = 0; y < h; y++) {
      var row = y * w;
      cum[0] = 0;
      for (x = 0; x < w; x++) cum[x + 1] = cum[x] + src[row + x];
      for (x = 0; x < w; x++) {
        var x0 = x - r < 0 ? 0 : x - r;
        var x1 = x + r + 1 > w ? w : x + r + 1;
        tmp[row + x] = (cum[x1] - cum[x0]) / (x1 - x0);
      }
    }
    for (x = 0; x < w; x++) {
      cum[0] = 0;
      for (y = 0; y < h; y++) cum[y + 1] = cum[y] + tmp[y * w + x];
      for (y = 0; y < h; y++) {
        var y0 = y - r < 0 ? 0 : y - r;
        var y1 = y + r + 1 > h ? h : y + r + 1;
        out[y * w + x] = (cum[y1] - cum[y0]) / (y1 - y0);
      }
    }
    return out;
  }

  function renderBase() {
    if (!heights) return;
    // Landscape is inland: no sea line, so nothing is ever painted as water.
    var sea = cfg ? (cfg.mode === "landscape" ? 0 : cfg.sea_level) : 0.06;
    // Land colors span sea..p99.5 of the land heights, divided by 0.85 so
    // only genuinely high ground reaches pale rock/snow. Using a
    // percentile instead of the max keeps one spike from washing the
    // whole island out to white.
    var landVals = [];
    for (var q = 0; q < heights.length; q += 4) {
      if (heights[q] > sea) landVals.push(heights[q]);
    }
    landVals.sort(function (a, b) { return a - b; });
    var hi = landVals.length
      ? landVals[Math.min(landVals.length - 1, Math.floor(landVals.length * 0.995))]
      : sea;
    var landRange = Math.max((hi - sea) / 0.85, 1e-4);
    off.width = iw;
    off.height = ih;
    var img = offctx.createImageData(iw, ih);
    var px = img.data;
    var i = 0;
    // Normalized terrain plane, so neighbours, slope and hollows are all
    // measured in the same units as the colour ramp.
    var n = iw * ih;
    var tn = new Float32Array(n);
    for (var q = 0; q < n; q++) {
      var tv0 = (heights[q] - sea) / landRange;
      tn[q] = tv0 < 0 ? 0 : (tv0 > 1 ? 1 : tv0);
    }
    // Local mean: terrain below it is a hollow or a valley floor.
    // A narrow window (~2 px at 512) is what isolates *valleys* from the
    // broad rolling hollows of the plain; a wide one just blurs the island.
    // The radius scales with preview resolution so a 256 and a 1024 preview
    // shade the same physical ground.
    var hr = Math.max(1, Math.round(2 * iw / 512));
    var meanT = boxBlur(tn, iw, ih, hr);
    var hollow = new Float32Array(n);
    for (var q2 = 0; q2 < n; q2++) {
      var hd = meanT[q2] - tn[q2];
      hollow[q2] = hd > 0 ? hd : 0;
    }
    // Join the deepest ground into continuous damp ribbons instead of
    // single-pixel speckle, then normalize to 0..1.
    hollow = boxBlur(hollow, iw, ih, Math.max(1, Math.round(hr / 2)));
    for (var q3 = 0; q3 < n; q3++) {
      var hv = hollow[q3] * 200;
      hollow[q3] = hv > 1 ? 1 : hv;
    }
    // Slope/hollow thresholds are in pixels of the *preview*; rescale so a
    // 256 preview and a 1024 preview shade the same island area.
    var gs = iw / 512;
    // Slope in ramp units per 512-pixel width, plus this map's own p99 so
    // bare rock follows the terrain instead of an island-tuned constant:
    // compact island peaks and broad landscape ranges differ ~10x in
    // absolute slope, and both should read as rock where they are steep.
    var slope = new Float32Array(n);
    var slSample = [];
    for (var ys = 0; ys < ih; ys++) {
      for (var xs = 0; xs < iw; xs++) {
        var is = ys * iw + xs;
        var sxm = xs > 0 ? is - 1 : is;
        var sxp2 = xs + 1 < iw ? is + 1 : is;
        var sym = ys > 0 ? is - iw : is;
        var syp2 = ys + 1 < ih ? is + iw : is;
        var sxv = (tn[sxp2] - tn[sxm]) * 0.5 * gs;
        var syv = (tn[syp2] - tn[sym]) * 0.5 * gs;
        var sv = Math.sqrt(sxv * sxv + syv * syv);
        slope[is] = sv;
        if (heights[is] >= sea && is % 5 === 0) slSample.push(sv);
      }
    }
    slSample.sort(function (a, b) { return a - b; });
    var slRef = slSample.length
      ? slSample[Math.min(slSample.length - 1, Math.floor(slSample.length * 0.99))]
      : 0.1;
    if (slRef < 1e-5) slRef = 1e-5;
    // Fractions of that reference: at the island reference (0.1) this is the
    // old fixed ramp, 0.020 .. 0.068. Kept in step with preview3d.js.
    var rockLo = 0.20 * slRef;
    var rockHi = 0.68 * slRef;
    // water depth ramps over 3x sea level, so shallow shelves stay
    // subtle instead of ringing every coast in bright cyan
    var invSea = 1 / Math.max(3 * sea, 1e-4);
    for (var y = 0; y < ih; y++) {
      for (var x = 0; x < iw; x++, i++) {
        var h = heights[i];
        var r, g, b;
        if (h < sea) {
          // water: shallow near coast -> deep offshore
          var d = (sea - h) * invSea;
          if (d > 1) d = 1;
          if (d < 0) d = 0;
          d = Math.pow(d, 0.7);
          r = 26 + (8 - 26) * d;
          g = 84 + (24 - 84) * d;
          b = 132 + (58 - 132) * d;
        } else {
          var t = tn[i];
          var c = rampLand(t);
          var xm = x > 0 ? i - 1 : i;
          var xp = x + 1 < iw ? i + 1 : i;
          var ym = y > 0 ? i - iw : i;
          var yp = y + 1 < ih ? i + iw : i;
          // slope of the height field (ramp units per pixel)
          var sx = (tn[xp] - tn[xm]) * 0.5 * gs;
          var sy = (tn[yp] - tn[ym]) * 0.5 * gs;
          // Hillshade: half-Lambert from the north-west. A hard Lambert
          // term crushes the shadow side to black on these compressed
          // heights, which reads as blotches rather than relief.
          var sl = slope[i];
          var lam = (0.62 - 0.52 * sx - 0.52 * sy) / Math.sqrt(sl * sl + 1);
          var sh = 0.56 + 0.78 * (lam < 0 ? 0 : lam);
          // Bare rock on steep ground: the threshold scales with this map's
          // own steepness, so broad landscape ranges and compact island
          // peaks both show bare rock on their flanks.
          var rock = (sl - rockLo) / (rockHi - rockLo);
          if (rock < 0) rock = 0; if (rock > 1) rock = 1;
          rock = rock * rock * (3 - 2 * rock);
          r = c[0]; g = c[1]; b = c[2];
          if (rock > 0) {
            r += (0x77 - r) * rock;
            g += (0x72 - g) * rock;
            b += (0x66 - b) * rock;
          }
          // Hollows and valley floors stay damper and darker, which is what
          // stops the plain reading as one flat sheet of green.
          var wet = hollow[i];
          if (wet > 0) {
            r *= 1 - 0.34 * wet;
            g *= 1 - 0.20 * wet;
            b *= 1 - 0.12 * wet;
          }
          // Aspect: north-facing slopes are cooler, south-facing drier.
          var asp = (tn[yp] - tn[ym]) * 22 * gs;
          if (asp < -1) asp = -1; if (asp > 1) asp = 1;
          r *= 1 + 0.055 * asp;
          g *= 1 + 0.012 * asp;
          b *= 1 - 0.050 * asp;
          r *= sh; g *= sh; b *= sh;
        }
        px[i * 4] = r;
        px[i * 4 + 1] = g;
        px[i * 4 + 2] = b;
        px[i * 4 + 3] = 255;
      }
    }
    offctx.putImageData(img, 0, 0);
    blit();
  }

  function fit() {
    var wrap = document.getElementById("pane2d-wrap");
    var cw = wrap.clientWidth, ch = wrap.clientHeight;
    view.dpr = window.devicePixelRatio || 1;
    base.width = Math.max(1, Math.round(cw * view.dpr));
    base.height = Math.max(1, Math.round(ch * view.dpr));
    overlay.width = base.width;
    overlay.height = base.height;
    if (iw > 0 && ih > 0) {
      var s = Math.min(cw / iw, ch / ih);
      view.scale = s;
      view.ox = (cw - iw * s) / 2;
      view.oy = (ch - ih * s) / 2;
    }
    blit();
    drawOverlay();
  }

  function blit() {
    if (!heights) return;
    bctx.setTransform(1, 0, 0, 1, 0, 0);
    bctx.clearRect(0, 0, base.width, base.height);
    bctx.imageSmoothingEnabled = true;
    var s = view.scale * view.dpr;
    bctx.drawImage(off, view.ox * view.dpr, view.oy * view.dpr, iw * s, ih * s);
  }

  // display (CSS px) -> image px
  function toImg(cx, cy) {
    return [(cx - view.ox) / view.scale, (cy - view.oy) / view.scale];
  }
  // image px -> display px
  function toDisp(ix, iy) {
    return [ix * view.scale + view.ox, iy * view.scale + view.oy];
  }

  function islandGeom(k) {
    var isl = cfg.islands[k];
    var minDim = Math.min(iw, ih);
    var cx = isl.cx * iw, cy = isl.cy * ih;
    var r = isl.radius * minDim;
    var a = isl.angle || 0;
    var asp = isl.aspect == null ? 1 : isl.aspect;
    return { cx: cx, cy: cy, r: r, a: a, asp: asp };
  }

  function drawOverlay() {
    octx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
    octx.clearRect(0, 0, overlay.width / view.dpr, overlay.height / view.dpr);
    if (!cfg || cfg.mode !== "islands") return;
    for (var k = 0; k < cfg.islands.length; k++) {
      var g = islandGeom(k);
      var p0 = toDisp(g.cx, g.cy);
      var active = cfg.islands[k].enabled;
      octx.globalAlpha = active ? 1 : 0.35;

      // planform ellipse (aspect + rotation)
      var rx = g.r * g.asp * view.scale;
      var ry = g.r / g.asp * view.scale;
      octx.beginPath();
      octx.ellipse(p0[0], p0[1], Math.max(rx, 1), Math.max(ry, 1), g.a, 0, Math.PI * 2);
      octx.strokeStyle = "#6aa2ff";
      octx.lineWidth = 1.2;
      octx.stroke();

      // resize handle (local +x rim, rotated by angle)
      var hx = g.cx + g.r * g.asp * Math.cos(g.a);
      var hy = g.cy + g.r * g.asp * Math.sin(g.a);
      var hp = toDisp(hx, hy);
      octx.beginPath();
      octx.arc(hp[0], hp[1], 5, 0, Math.PI * 2);
      octx.fillStyle = "#3b82f6";
      octx.fill();

      // rotation handle (local -y, beyond the rim)
      var ox2 = g.cx + (g.r / g.asp) * 1.18 * Math.sin(g.a);
      var oy2 = g.cy - (g.r / g.asp) * 1.18 * Math.cos(g.a);
      var op = toDisp(ox2, oy2);
      octx.beginPath();
      octx.arc(op[0], op[1], 5, 0, Math.PI * 2);
      octx.fillStyle = "#f59e0b";
      octx.fill();

      // center label badge: number matching the sidebar card
      octx.beginPath();
      octx.arc(p0[0], p0[1], 9, 0, Math.PI * 2);
      octx.fillStyle = "rgba(13, 17, 23, 0.75)";
      octx.fill();
      octx.strokeStyle = "#9cc0ff";
      octx.lineWidth = 1;
      octx.stroke();
      octx.fillStyle = "#9cc0ff";
      octx.font = "bold 11px 'Segoe UI', sans-serif";
      octx.textAlign = "center";
      octx.textBaseline = "middle";
      octx.fillText(String(k + 1), p0[0], p0[1] + 0.5);
      octx.globalAlpha = 1;
    }
  }

  function hitTest(dx, dy) {
    if (!cfg || cfg.mode !== "islands") return null;
    var TOL = 10;
    for (var k = cfg.islands.length - 1; k >= 0; k--) {
      var g = islandGeom(k);
      var p0 = toDisp(g.cx, g.cy);
      // world -> island-local (rotate by -angle)
      var ca = Math.cos(g.a), sa = Math.sin(g.a);
      var px = dx - p0[0], py = dy - p0[1];
      var u = px * ca + py * sa;
      var v = -px * sa + py * ca;
      var rx = Math.max(g.r * g.asp * view.scale, 1);
      var ry = Math.max(g.r / g.asp * view.scale, 1);
      var hxp = toDisp(g.cx + g.r * g.asp * Math.cos(g.a), g.cy + g.r * g.asp * Math.sin(g.a));
      var oxp = toDisp(
        g.cx + (g.r / g.asp) * 1.18 * Math.sin(g.a),
        g.cy - (g.r / g.asp) * 1.18 * Math.cos(g.a)
      );
      if (Math.abs(dx - oxp[0]) < TOL && Math.abs(dy - oxp[1]) < TOL) {
        return { mode: "rotate", index: k, geom: g };
      }
      if (Math.abs(dx - hxp[0]) < TOL && Math.abs(dy - hxp[1]) < TOL) {
        return { mode: "resize", index: k, geom: g };
      }
      var e = (u * u) / (rx * rx) + (v * v) / (ry * ry);
      if (e <= 1) {
        // center grab wins close in, otherwise select inside the ellipse
        var distC = Math.sqrt(u * u + v * v);
        var near = Math.min(rx, ry);
        if (distC < Math.max(TOL, near * 0.18)) {
          return { mode: "move", index: k, geom: g };
        }
        return { mode: "select", index: k, geom: g };
      }
    }
    return null;
  }

  overlay.addEventListener("mousedown", function (e) {
    if (!cfg) return;
    var rect = overlay.getBoundingClientRect();
    var dx = e.clientX - rect.left, dy = e.clientY - rect.top;
    var hit = hitTest(dx, dy);
    if (!hit) return;
    if (hit.mode === "select") {
      if (onSelect) onSelect(hit.index);
      return;
    }
    var isl = cfg.islands[hit.index];
    drag = {
      mode: hit.mode,
      index: hit.index,
      img: toImg(dx, dy),
      geom: hit.geom,
      cx0: isl.cx,
      cy0: isl.cy
    };
    if (onSelect) onSelect(hit.index);
    e.preventDefault();
  });

  window.addEventListener("mousemove", function (e) {
    if (!drag || !cfg) return;
    var rect = overlay.getBoundingClientRect();
    var img = toImg(e.clientX - rect.left, e.clientY - rect.top);
    var isl = cfg.islands[drag.index];
    var g = drag.geom;
    if (drag.mode === "move") {
      var dx = (img[0] - drag.img[0]) / iw;
      var dy = (img[1] - drag.img[1]) / ih;
      isl.cx = drag.cx0 + dx;
      isl.cy = drag.cy0 + dy;
    } else if (drag.mode === "resize") {
      var rx0 = img[0] - g.cx, ry0 = img[1] - g.cy;
      var u0 = rx0 * Math.cos(g.a) + ry0 * Math.sin(g.a);
      var v0 = -rx0 * Math.sin(g.a) + ry0 * Math.cos(g.a);
      var elx = u0 / g.asp, ely = v0 * g.asp;
      var dist = Math.sqrt(elx * elx + ely * ely);
      isl.radius = clamp(dist / Math.min(iw, ih), 0.02, 1.5);
    } else if (drag.mode === "rotate") {
      var vx = img[0] - g.cx, vy = img[1] - g.cy;
      if (Math.abs(vx) + Math.abs(vy) > 1) {
        isl.angle = Math.atan2(vx, -vy);
      }
    }
    constrain(isl);
    drawOverlay();
    if (onChange) onChange(drag.index, isl);
  });

  window.addEventListener("mouseup", function () {
    drag = null;
  });

  overlay.addEventListener("dblclick", function (e) {
    if (!cfg || cfg.mode !== "islands") return;
    var rect = overlay.getBoundingClientRect();
    var img = toImg(e.clientX - rect.left, e.clientY - rect.top);
    if (img[0] < 0 || img[1] < 0 || img[0] >= iw || img[1] >= ih) return;
    if (onAdd) onAdd(img[0] / iw, img[1] / ih);
  });

  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }

  // keep the island's rotated-ellipse footprint fully inside the map
  function constrain(isl) {
    if (!iw || !ih || !isl) return isl;
    var minDim = Math.min(iw, ih);
    var asp = isl.aspect == null ? 1 : isl.aspect;
    var rx = isl.radius * asp * minDim / iw;
    var ry = (isl.radius / asp) * minDim / ih;
    var a = isl.angle || 0;
    var ca = Math.cos(a), sa = Math.sin(a);
    var ex = Math.sqrt(rx * rx * ca * ca + ry * ry * sa * sa);
    var ey = Math.sqrt(rx * rx * sa * sa + ry * ry * ca * ca);
    isl.cx = clamp(isl.cx, Math.min(ex, 0.5), Math.max(1 - ex, 0.5));
    isl.cy = clamp(isl.cy, Math.min(ey, 0.5), Math.max(1 - ey, 0.5));
    return isl;
  }

  return {
    draw: function (arr, w, h, config) {
      heights = arr;
      iw = w;
      ih = h;
      cfg = config;
      fit();
      renderBase();
      drawOverlay();
    },
    setConfig: function (config) {
      cfg = config;
      drawOverlay();
    },
    resize: function () {
      fit();
    },
    setOnChange: function (fn) { onChange = fn; },
    setOnAdd: function (fn) { onAdd = fn; },
    setOnSelect: function (fn) { onSelect = fn; },
    constrain: constrain
  };
})();
