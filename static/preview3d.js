/* 3D preview: compact WebGL heightmap mesh with orbit/zoom/pan. */
"use strict";

window.Preview3D = (function () {
  var canvas = document.getElementById("pane3d");
  var gl = canvas.getContext("webgl", { antialias: true, alpha: false });

  var VS = [
    "attribute vec3 a_pos;",
    "attribute vec3 a_nrm;",
    "attribute float a_h;",
    "attribute float a_rock;",
    "attribute float a_wet;",
    "uniform mat4 u_mvp;",
    "uniform mat4 u_view;",
    "varying float v_h;",
    "varying float v_rock;",
    "varying float v_wet;",
    "varying vec3 v_n;",
    "void main() {",
    "  v_h = a_h;",
    "  v_rock = a_rock;",
    "  v_wet = a_wet;",
    "  v_n = mat3(u_view) * a_nrm;",
    "  gl_Position = u_mvp * vec4(a_pos, 1.0);",
    "}"
  ].join("\n");

  var FS = [
    "precision mediump float;",
    "varying float v_h;",
    "varying float v_rock;",
    "varying float v_wet;",
    "varying vec3 v_n;",
    "uniform float u_sea;",
    "uniform float u_lmax;",
    "vec3 ramp(float t) {",
    "  vec3 sand = vec3(0.788, 0.714, 0.549);",
    "  vec3 dune = vec3(0.604, 0.635, 0.424);",
    "  vec3 g1   = vec3(0.384, 0.533, 0.310);",
    "  vec3 g2   = vec3(0.318, 0.467, 0.278);",
    "  vec3 scr  = vec3(0.345, 0.439, 0.298);",
    "  vec3 r1   = vec3(0.431, 0.424, 0.365);",
    "  vec3 r2   = vec3(0.557, 0.537, 0.486);",
    "  if (t < 0.045) return mix(sand, dune, t / 0.045);",
    "  if (t < 0.120) return mix(dune, g1, (t - 0.045) / 0.075);",
    "  if (t < 0.380) return mix(g1, g2, (t - 0.120) / 0.260);",
    "  if (t < 0.600) return mix(g2, scr, (t - 0.380) / 0.220);",
    "  if (t < 0.800) return mix(scr, r1, (t - 0.600) / 0.200);",
    "  return mix(r1, r2, clamp((t - 0.800) / 0.200, 0.0, 1.0));",
    "}",
    "void main() {",
    "  vec3 base;",
    "  if (v_h < u_sea) {",
    "    float d = clamp((u_sea - v_h) / max(3.0 * u_sea, 1e-4), 0.0, 1.0);",
    "    d = pow(d, 0.7);",
    "    base = mix(vec3(0.102, 0.329, 0.518), vec3(0.031, 0.094, 0.227), d);",
    "  } else {",
    "    float t = clamp((v_h - u_sea) / max(u_lmax - u_sea, 1e-4), 0.0, 1.0);",
    "    base = ramp(t);",
    // bare rock on steep faces, so a massif reads as rock rather than as
    // a darker patch of grass
    "    base = mix(base, vec3(0.404, 0.396, 0.345), v_rock * 0.85);",
    // damp, darker ground in hollows and valley floors
    "    base *= vec3(1.0 - 0.34 * v_wet, 1.0 - 0.20 * v_wet,",
    "                  1.0 - 0.12 * v_wet);",
    "  }",
    "  vec3 n = normalize(v_n);",
    "  vec3 l = normalize(vec3(0.45, 0.8, 0.35));",
    // half-Lambert: a hard cosine term crushes the shadow side to black,
    // which on a compressed heightmap reads as blotches, not as relief
    "  float diff = dot(n, l) * 0.5 + 0.5;",
    "  gl_FragColor = vec4(base * (0.42 + 0.78 * diff), 1.0);",
    "}"
  ].join("\n");

  var WS = [
    "attribute vec3 a_pos;",
    "uniform mat4 u_mvp;",
    "void main() { gl_Position = u_mvp * vec4(a_pos, 1.0); }"
  ].join("\n");

  var WFS = [
    "precision mediump float;",
    "void main() { gl_FragColor = vec4(0.078, 0.286, 0.478, 0.72); }"
  ].join("\n");

  if (!gl) {
    return {
      draw: function () {},
      resize: function () {},
      render: function () {}
    };
  }

  function compile(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(s));
    }
    return s;
  }

  function program(vsSrc, fsSrc) {
    var p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, vsSrc));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fsSrc));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(p));
    }
    return p;
  }

  var progTerrain, progWater, loc;
  try {
    progTerrain = program(VS, FS);
    progWater = program(WS, WFS);
    loc = {
      a_pos: gl.getAttribLocation(progTerrain, "a_pos"),
      a_nrm: gl.getAttribLocation(progTerrain, "a_nrm"),
      a_h: gl.getAttribLocation(progTerrain, "a_h"),
      a_rock: gl.getAttribLocation(progTerrain, "a_rock"),
      a_wet: gl.getAttribLocation(progTerrain, "a_wet"),
      u_mvp: gl.getUniformLocation(progTerrain, "u_mvp"),
      u_view: gl.getUniformLocation(progTerrain, "u_view"),
      u_sea: gl.getUniformLocation(progTerrain, "u_sea"),
      u_lmax: gl.getUniformLocation(progTerrain, "u_lmax"),
      w_pos: gl.getAttribLocation(progWater, "a_pos"),
      w_mvp: gl.getUniformLocation(progWater, "u_mvp")
    };
  } catch (e) {
    progTerrain = null;
  }

  var vboPos = gl.createBuffer();
  var vboNrm = gl.createBuffer();
  var vboH = gl.createBuffer();
  var vboRock = gl.createBuffer();
  var vboWet = gl.createBuffer();
  var vboIdx = gl.createBuffer();
  var vboWater = gl.createBuffer();

  /* Separable box blur of a float plane, clamped at the edges. */
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

  var idxCount = 0;
  var sea = 0.06;
  var landMax = 1.0; // land color scale (max height), set in draw()
  var showWater = true; // water plane only when something is submerged
  var framed = false;   // auto-frame once, keep the user's camera after
  var framedW = 0, framedH = 0;
  var frameH = 0.5; // mid height for camera target (scaled units)

  var Z_EXAG = 0.35;
  var cam = {
    theta: -0.7,
    phi: 0.95,
    dist: 3.0,
    tx: 0,
    ty: 0,
    tz: 0,
    fov: 45 * Math.PI / 180
  };
  var last = null;

  /* ---------- matrices (column-major) ---------- */
  function mMul(a, b) {
    var o = new Array(16);
    for (var c = 0; c < 4; c++) {
      for (var r = 0; r < 4; r++) {
        o[c * 4 + r] =
          a[r] * b[c * 4] +
          a[4 + r] * b[c * 4 + 1] +
          a[8 + r] * b[c * 4 + 2] +
          a[12 + r] * b[c * 4 + 3];
      }
    }
    return o;
  }
  function mPersp(fovy, aspect, near, far) {
    var f = 1 / Math.tan(fovy / 2);
    var nf = 1 / (near - far);
    return [
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0
    ];
  }
  function mLookAt(eye, ctr, up) {
    var zx = eye[0] - ctr[0], zy = eye[1] - ctr[1], zz = eye[2] - ctr[2];
    var zl = Math.sqrt(zx * zx + zy * zy + zz * zz) || 1;
    zx /= zl; zy /= zl; zz /= zl;
    var xx = up[1] * zz - up[2] * zy;
    var xy = up[2] * zx - up[0] * zz;
    var xz = up[0] * zy - up[1] * zx;
    var xl = Math.sqrt(xx * xx + xy * xy + xz * xz) || 1;
    xx /= xl; xy /= xl; xz /= xl;
    var yx = zy * xz - zz * xy;
    var yy = zz * xx - zx * xz;
    var yz = zx * xy - zy * xx;
    return [
      xx, yx, zx, 0,
      xy, yy, zy, 0,
      xz, yz, zz, 0,
      -(xx * eye[0] + xy * eye[1] + xz * eye[2]),
      -(yx * eye[0] + yy * eye[1] + yz * eye[2]),
      -(zx * eye[0] + zy * eye[1] + zz * eye[2]),
      1
    ];
  }

  function resize() {
    var wrap = document.getElementById("pane3d-wrap");
    var dpr = window.devicePixelRatio || 1;
    var w = Math.max(1, Math.round(wrap.clientWidth * dpr));
    var h = Math.max(1, Math.round(wrap.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
  }

  function buildMesh(heights, w, h) {
    // decimate so the mesh stays <= 256 segments per side
    var step = Math.max(1, Math.ceil(Math.max(w, h) / 256));
    var gw = Math.floor((w - 1) / step) + 1;
    var gh = Math.floor((h - 1) / step) + 1;
    var n = gw * gh;
    var pos = new Float32Array(n * 3);
    var nrm = new Float32Array(n * 3);
    var hs = new Float32Array(n);
    var x, y, i;
    var hmin = 1e9, hmax = -1e9;
    for (y = 0; y < gh; y++) {
      for (x = 0; x < gw; x++) {
        var sx = Math.min(w - 1, x * step);
        var sy = Math.min(h - 1, y * step);
        var hv = heights[sy * w + sx];
        i = y * gw + x;
        pos[i * 3] = (gw > 1 ? x / (gw - 1) : 0) - 0.5;
        pos[i * 3 + 1] = hv * Z_EXAG;
        pos[i * 3 + 2] = (gh > 1 ? y / (gh - 1) : 0) - 0.5;
        hs[i] = hv;
        if (hv < hmin) hmin = hv;
        if (hv > hmax) hmax = hv;
      }
    }
    // normals and colors scale to p99.5 of the land heights (not the
    // single max), /0.85 so only genuinely high ground reaches snow
    var landVals = [];
    for (i = 0; i < n; i++) {
      if (hs[i] > sea) landVals.push(hs[i]);
    }
    landVals.sort(function (a, b) { return a - b; });
    var lmax = landVals.length
      ? landVals[Math.min(landVals.length - 1, Math.floor(landVals.length * 0.995))]
      : sea;
    var lrange = Math.max((lmax - sea) / 0.85, 1e-4);
    var hsn = new Float32Array(n);
    for (i = 0; i < n; i++) hsn[i] = (hs[i] - sea) / lrange;
    var cell = 1 / Math.max(gw - 1, 1);
    // Vertical scale of the drawn mesh: hsn*lrange is the raw height and
    // the vertex y is that times Z_EXAG, so the geometric normal is the
    // one the eye actually sees. Without it the shading is ~10x too steep
    // and most of the island falls into shadow.
    var zs = lrange * Z_EXAG;
    var gsx = w / 512, gsy = h / 512;
    var rock = new Float32Array(n);
    var wet = new Float32Array(n);
    for (y = 0; y < gh; y++) {
      for (x = 0; x < gw; x++) {
        var xl = x > 0 ? x - 1 : x, xr = x < gw - 1 ? x + 1 : x;
        var yd = y > 0 ? y - 1 : y, yu = y < gh - 1 ? y + 1 : y;
        var i0 = y * gw + x;
        var dhx = (hsn[i0 - x + xr] - hsn[i0 - x + xl])
          / (Math.max(xr - xl, 1) * cell) * zs;
        var dhy = (hsn[i0 + (yu - y) * gw] - hsn[i0 + (yd - y) * gw])
          / (Math.max(yu - yd, 1) * cell) * zs;
        var nx = -dhx, ny = 1.0, nz = -dhy;
        var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
        nrm[i0 * 3] = nx / nl;
        nrm[i0 * 3 + 1] = ny / nl;
        nrm[i0 * 3 + 2] = nz / nl;
        // steepness in normalized-height units per map pixel, matching the
        // 2D preview so both views agree on where rock is bare
        var sxp = (hsn[i0 - x + xr] - hsn[i0 - x + xl])
          / (Math.max(xr - xl, 1) * step) * gsx;
        var syp = (hsn[i0 + (yu - y) * gw] - hsn[i0 + (yd - y) * gw])
          / (Math.max(yu - yd, 1) * step) * gsy;
        var sl = Math.sqrt(sxp * sxp + syp * syp);
        var rk = (sl - 0.020) / 0.048;
        rock[i0] = rk < 0 ? 0 : (rk > 1 ? 1 : rk * rk * (3 - 2 * rk));
      }
    }
    // Local mean height: ground below it is a hollow or a valley floor.
    // The window is 2 *map* pixels wide (not 2 grid cells), so the shading
    // agrees with the 2D preview at any preview resolution.
    var rw = Math.max(1, Math.round(2 / step));
    var meanT = boxBlur(hsn, gw, gh, rw);
    var hollow = new Float32Array(n);
    for (i = 0; i < n; i++) {
      var hd = meanT[i] - hsn[i];
      hollow[i] = hd > 0 ? hd : 0;
    }
    // Join the deepest ground into damp ribbons rather than 1-pixel speckle.
    hollow = boxBlur(hollow, gw, gh, 1);
    for (i = 0; i < n; i++) {
      if (hs[i] <= sea) continue;
      var wt = hollow[i] * 200;
      wet[i] = wt > 1 ? 1 : wt;
    }
    var indices = new Uint16Array((gw - 1) * (gh - 1) * 6);
    i = 0;
    for (y = 0; y < gh - 1; y++) {
      for (x = 0; x < gw - 1; x++) {
        var a0 = y * gw + x, b0 = a0 + 1, c0 = a0 + gw, d0 = c0 + 1;
        indices[i++] = a0; indices[i++] = c0; indices[i++] = b0;
        indices[i++] = b0; indices[i++] = c0; indices[i++] = d0;
      }
    }
    frameH = ((hmin + hmax) / 2) * Z_EXAG;
    return {
      pos: pos, nrm: nrm, hs: hs, rock: rock, wet: wet, idx: indices,
      count: indices.length, hmin: hmin, hmax: hmax, lmax: lmax
    };
  }

  function autoFrame() {
    cam.dist = 0.95 / Math.sin(cam.fov / 2);
    cam.tx = 0;
    cam.ty = frameH;
    cam.tz = 0;
    cam.theta = -0.7;
    cam.phi = 0.95;
  }

  function render() {
    if (!progTerrain || idxCount === 0) return;
    resize();
    var w = canvas.width, h = canvas.height;
    gl.clearColor(0.027, 0.039, 0.063, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);

    var proj = mPersp(cam.fov, w / Math.max(h, 1), 0.01, 100);
    var eye = [
      cam.tx + cam.dist * Math.cos(cam.phi) * Math.sin(cam.theta),
      cam.ty + cam.dist * Math.sin(cam.phi),
      cam.tz + cam.dist * Math.cos(cam.phi) * Math.cos(cam.theta)
    ];
    var view = mLookAt(eye, [cam.tx, cam.ty, cam.tz], [0, 1, 0]);
    var mvp = mMul(proj, view);
    var f32 = new Float32Array(mvp);

    gl.useProgram(progTerrain);
    gl.bindBuffer(gl.ARRAY_BUFFER, vboPos);
    gl.enableVertexAttribArray(loc.a_pos);
    gl.vertexAttribPointer(loc.a_pos, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, vboNrm);
    gl.enableVertexAttribArray(loc.a_nrm);
    gl.vertexAttribPointer(loc.a_nrm, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, vboH);
    gl.enableVertexAttribArray(loc.a_h);
    gl.vertexAttribPointer(loc.a_h, 1, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, vboRock);
    gl.enableVertexAttribArray(loc.a_rock);
    gl.vertexAttribPointer(loc.a_rock, 1, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, vboWet);
    gl.enableVertexAttribArray(loc.a_wet);
    gl.vertexAttribPointer(loc.a_wet, 1, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, vboIdx);
    gl.uniformMatrix4fv(loc.u_mvp, false, f32);
    gl.uniformMatrix4fv(loc.u_view, false, new Float32Array(view));
    gl.uniform1f(loc.u_sea, sea);
    gl.uniform1f(loc.u_lmax, landMax);
    gl.drawElements(gl.TRIANGLES, idxCount, gl.UNSIGNED_SHORT, 0);

    // water plane at sea level (only when terrain actually dips below it)
    if (showWater) {
      var wy = sea * Z_EXAG;
      var S = 0.62;
      var wq = new Float32Array([
        -S, wy, -S, S, wy, -S, -S, wy, S,
        -S, wy, S, S, wy, -S, S, wy, S
      ]);
      gl.useProgram(progWater);
      gl.bindBuffer(gl.ARRAY_BUFFER, vboWater);
      gl.bufferData(gl.ARRAY_BUFFER, wq, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(loc.w_pos);
      gl.vertexAttribPointer(loc.w_pos, 3, gl.FLOAT, false, 0, 0);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.uniformMatrix4fv(loc.w_mvp, false, f32);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      gl.disable(gl.BLEND);
    }
  }

  /* ---------- input ---------- */
  canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  canvas.addEventListener("mousedown", function (e) {
    last = { x: e.clientX, y: e.clientY, btn: e.button };
  });
  window.addEventListener("mouseup", function () { last = null; });
  window.addEventListener("mousemove", function (e) {
    if (!last) return;
    var dx = e.clientX - last.x, dy = e.clientY - last.y;
    last.x = e.clientX;
    last.y = e.clientY;
    if (last.btn === 0) {
      cam.theta -= dx * 0.0075;
      cam.phi += dy * 0.0075;
      if (cam.phi < 0.05) cam.phi = 0.05;
      if (cam.phi > 1.52) cam.phi = 1.52;
    } else if (last.btn === 2) {
      var rx = Math.cos(cam.theta), rz = -Math.sin(cam.theta);
      var scale = cam.dist * 0.0016;
      cam.tx += rx * dx * scale;
      cam.tz += rz * dx * scale;
      cam.ty -= dy * scale;
    }
    render();
  });
  canvas.addEventListener("dblclick", function () {
    autoFrame();
    render();
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    cam.dist *= e.deltaY > 0 ? 1.1 : 0.9;
    if (cam.dist < 0.3) cam.dist = 0.3;
    if (cam.dist > 40) cam.dist = 40;
    render();
  }, { passive: false });

  window.addEventListener("resize", function () {
    resize();
    render();
  });

  return {
    draw: function (heights, w, h, seaLevel) {
      if (!progTerrain) return;
      sea = seaLevel;
      var mesh = buildMesh(heights, w, h);
      // color scale tops out at pale rock (p99.5 of land heights)
      landMax = Math.max(mesh.lmax, sea + 1e-4);
      showWater = mesh.hmin < sea;
      gl.bindBuffer(gl.ARRAY_BUFFER, vboPos);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.pos, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, vboNrm);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.nrm, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, vboH);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.hs, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, vboRock);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.rock, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, vboWet);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.wet, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, vboIdx);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.idx, gl.STATIC_DRAW);
      idxCount = mesh.count;
      // frame the camera only on first draw or resolution change so
      // regenerating terrain doesn't steal the user's view
      if (!framed || framedW !== w || framedH !== h) {
        autoFrame();
        framed = true;
        framedW = w;
        framedH = h;
      }
      resize();
      render();
    },
    resize: function () {
      resize();
      render();
    },
    render: render
  };
})();
