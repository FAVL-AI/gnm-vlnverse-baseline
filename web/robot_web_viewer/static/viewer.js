/**
 * FleetSafe Three.js URDF Viewer — viewer.js
 *
 * Provides the FleetSafeViewer namespace with:
 *   - JointStateStream: WebSocket subscriber
 *   - RobotRenderer: Three.js 3D rendering (optional, requires three.min.js)
 *   - StickFigureRenderer: lightweight 2D canvas fallback
 *
 * Usage:
 *   const stream = new FleetSafeViewer.JointStateStream(
 *     'ws://localhost:8080/ws/joint_states',
 *     (state) => { // update your UI }
 *   );
 */
(function(global) {
  'use strict';

  // ── JointStateStream ────────────────────────────────────────────────────────

  /**
   * WebSocket subscriber for /ws/joint_states.
   * Auto-reconnects on disconnect.
   *
   * @param {string} url - WebSocket URL
   * @param {function} onUpdate - callback(state) where state = {names, positions, velocities, timestamp, source}
   * @param {object} opts - options: {reconnectMs: 2000}
   */
  function JointStateStream(url, onUpdate, opts) {
    opts = opts || {};
    this.url = url;
    this.onUpdate = onUpdate;
    this.reconnectMs = opts.reconnectMs || 2000;
    this._retries = 0;
    this._closed = false;
    this._connect();
  }

  JointStateStream.prototype._connect = function() {
    if (this._closed) return;
    var self = this;
    this._ws = new WebSocket(this.url);

    this._ws.onopen = function() {
      self._retries = 0;
      if (typeof self.onConnect === 'function') self.onConnect();
    };

    this._ws.onmessage = function(evt) {
      try {
        var state = JSON.parse(evt.data);
        self.onUpdate(state);
      } catch(e) {
        console.warn('[JointStateStream] parse error:', e);
      }
    };

    this._ws.onerror = function(err) {
      if (typeof self.onError === 'function') self.onError(err);
    };

    this._ws.onclose = function() {
      self._retries++;
      if (typeof self.onDisconnect === 'function') self.onDisconnect(self._retries);
      if (!self._closed) {
        setTimeout(function() { self._connect(); }, self.reconnectMs);
      }
    };
  };

  JointStateStream.prototype.close = function() {
    this._closed = true;
    if (this._ws) this._ws.close();
  };

  JointStateStream.prototype.send = function(msg) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
  };

  // ── StickFigureRenderer ─────────────────────────────────────────────────────

  /**
   * Lightweight 2D stick figure renderer on a canvas element.
   *
   * @param {HTMLCanvasElement} canvas
   * @param {object} opts - options
   */
  function StickFigureRenderer(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.scale = opts.scale || 140;
    this.cx = canvas.width / 2;
    this.cy = canvas.height * (opts.cyRatio || 0.42);
    this.bgColor = opts.bgColor || '#0d1117';
    this.jointColors = {
      leftLeg:  opts.leftLegColor  || '#f85149',
      rightLeg: opts.rightLegColor || '#3fb950',
      leftArm:  opts.leftArmColor  || '#e3b341',
      rightArm: opts.rightArmColor || '#79c0ff',
      torso:    opts.torsoColor    || '#58a6ff',
    };
  }

  StickFigureRenderer.prototype.render = function(positions) {
    var ctx = this.ctx;
    var W = this.canvas.width, H = this.canvas.height;
    var CX = this.cx, CY = this.cy;
    var S = this.scale;
    var pos = positions || new Array(18).fill(0);

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = this.bgColor;
    ctx.fillRect(0, 0, W, H);

    // Ground line
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, H * 0.88);
    ctx.lineTo(W, H * 0.88);
    ctx.stroke();

    // ── Torso ────────────────────────────────────────────────────────────────
    var torsoTop = CY - S * 0.5;
    ctx.strokeStyle = this.jointColors.torso;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.lineTo(CX, torsoTop);
    ctx.stroke();

    // ── Head ─────────────────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.arc(CX, torsoTop - 20, 20, 0, 2 * Math.PI);
    ctx.strokeStyle = this.jointColors.torso;
    ctx.lineWidth = 2;
    ctx.stroke();

    // ── Legs ─────────────────────────────────────────────────────────────────
    this._drawLeg(ctx, pos, 0, -1, S, CX, CY, this.jointColors.leftLeg);   // left
    this._drawLeg(ctx, pos, 1,  1, S, CX, CY, this.jointColors.rightLeg);  // right

    // ── Arms ─────────────────────────────────────────────────────────────────
    this._drawArm(ctx, pos, 0, -1, S, CX, torsoTop, this.jointColors.leftArm);
    this._drawArm(ctx, pos, 1,  1, S, CX, torsoTop, this.jointColors.rightArm);

    // ── Labels ────────────────────────────────────────────────────────────────
    ctx.fillStyle = '#8b949e';
    ctx.font = '11px monospace';
    ctx.fillText('H1 Humanoid — Sagittal Plane', 10, 18);
  };

  StickFigureRenderer.prototype._drawLeg = function(ctx, pos, side, sign, S, CX, CY, color) {
    var base = side === 0 ? 0 : 5;
    var hipPitch = pos[base + 2] || -0.4;
    var knee = pos[base + 3] || 0.8;
    var thigh = S * 0.42, shank = S * 0.42;

    var hx = CX + sign * S * 0.09, hy = CY;
    var kx = hx + thigh * Math.sin(hipPitch);
    var ky = hy + thigh * Math.cos(hipPitch);
    var kneeTotal = hipPitch + knee;
    var fx = kx + shank * Math.sin(kneeTotal);
    var fy = ky + shank * Math.cos(kneeTotal);

    ctx.strokeStyle = color;
    ctx.lineWidth = 5;
    ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(kx, ky); ctx.stroke();
    ctx.lineWidth = 4;
    ctx.strokeStyle = color + '99';
    ctx.beginPath(); ctx.moveTo(kx, ky); ctx.lineTo(fx, fy); ctx.stroke();
    // Foot
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(fx + sign * 22, fy); ctx.stroke();
  };

  StickFigureRenderer.prototype._drawArm = function(ctx, pos, side, sign, S, CX, shoulderY, color) {
    var base = 10 + side * 4;
    var pitch = pos[base] || 0;
    var elbow = pos[base + 2] || 0;
    var sx = CX + sign * S * 0.2, sy = shoulderY + 10;
    var upper = S * 0.27, lower = S * 0.24;
    var ex = sx + upper * Math.sin(pitch) * sign;
    var ey = sy + upper * Math.cos(pitch);
    var hx = ex + lower * Math.sin(pitch + elbow) * sign;
    var hy = ey + lower * Math.cos(pitch + elbow);

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.lineTo(hx, hy); ctx.stroke();
  };

  // ── RobotAPI ─────────────────────────────────────────────────────────────────

  /**
   * REST API client for fleet-safe endpoints.
   */
  var RobotAPI = {
    baseUrl: '',

    async getRobotInfo() {
      const r = await fetch(this.baseUrl + '/api/robot/info');
      return r.json();
    },

    async getSafetyStatus() {
      const r = await fetch(this.baseUrl + '/api/safety/status');
      return r.json();
    },

    async getFleetStatus() {
      const r = await fetch(this.baseUrl + '/api/fleet/status');
      return r.json();
    },
  };

  // ── Export ────────────────────────────────────────────────────────────────────
  global.FleetSafeViewer = {
    JointStateStream: JointStateStream,
    StickFigureRenderer: StickFigureRenderer,
    RobotAPI: RobotAPI,
    version: '0.1.0',
  };

})(window);
