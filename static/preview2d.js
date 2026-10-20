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

  function rampLand(t) {
    // green -> olive -> gray-brown -> white
    var stops = [
      [0.00, 0x3f, 0x7d, 0x44],
      [0.35, 0x6e, 0x7f, 0x4e],
      [0.65, 0x8a, 0x85, 0x78],
      [1.00, 0xf2, 0xf2, 0xf5]
    ];
    for (var i = 1; i < stops.length; i++) {
      if (t <= stops[i][0] || i === stops.length - 1) {
        var a = stops[i - 1], b = stops[i];
        var f = (t - a[0]) / (b[0] - a[0] + 1e-9);
        if (f < 0) f = 0; if (f > 1) f = 1;
        return [
          a[1] + (b[1] - a[1]) * f,
          a[2] + (b[2] - a[2]) * f,
          a[3] + (b[3] - a[3]) * f
        ];
      }
    }
    return [255, 255, 255];
  }

  function renderBase() {
    if (!heights) return;
    var sea = cfg ? cfg.sea_level : 0.06;
    // land colors span sea..landMax so low islands keep full contrast;
    // /0.65 caps at gray-brown (no snow) for gentle island heights
    var landMax = sea;
    for (var q = 0; q < heights.length; q++) {
      if (heights[q] > landMax) landMax = heights[q];
    }
    var landRange = Math.max((landMax - sea) / 0.65, 1e-4);
    function landT(hv) {
      var tv = (hv - sea) / landRange;
      return tv < 0 ? 0 : (tv > 1 ? 1 : tv);
    }
    off.width = iw;
    off.height = ih;
    var img = offctx.createImageData(iw, ih);
    var px = img.data;
    var i = 0;
    var invSea = 1 / Math.max(sea, 1e-4);
    for (var y = 0; y < ih; y++) {
      for (var x = 0; x < iw; x++, i++) {
        var h = heights[i];
        var r, g, b;
        if (h < sea) {
          // water: shallow near coast -> deep offshore
          var d = (sea - h) * invSea;
          if (d > 1) d = 1;
          r = 20 + (8 - 20) * d;
          g = 73 + (24 - 73) * d;
          b = 122 + (58 - 122) * d;
        } else {
          var t = landT(h);
          var c = rampLand(t);
          // hillshade from normalized differences (raw slopes are tiny
          // on compressed island heights, so shade relative to landRange)
          var hx1 = landT(heights[i + (x + 1 < iw ? 1 : 0)]);
          var hx0 = landT(heights[i - (x > 0 ? 1 : 0)]);
          var hy1 = landT(heights[i + (y + 1 < ih ? iw : 0)]);
          var hy0 = landT(heights[i - (y > 0 ? iw : 0)]);
          var sh = 1 + (hx0 - hx1) * 8 + (hy0 - hy1) * 8;
          if (sh < 0.55) sh = 0.55;
          if (sh > 1.3) sh = 1.3;
          r = c[0] * sh;
          g = c[1] * sh;
          b = c[2] * sh;
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
