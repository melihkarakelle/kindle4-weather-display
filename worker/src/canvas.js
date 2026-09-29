// Tiny 8-bit grayscale canvas with the handful of Pillow-style primitives the
// Kindle layouts use. Text comes from the pre-rendered bitmap atlas
// (tools/make_atlas.py), so no font rasterising happens at runtime.
import atlas from "./atlas.json";

export const W = 600;
export const H = 800;

// Decode a glyph's base64 packed bitmap once and keep it on the glyph object.
function glyphBytes(g) {
  if (!g._bytes) {
    const bin = atob(g.bits || "");
    const b = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    g._bytes = b;
  }
  return g._bytes;
}

export class Canvas {
  constructor(width = W, height = H) {
    this.w = width;
    this.h = height;
    this.px = new Uint8Array(width * height).fill(255);
  }

  set(x, y, v = 0) {
    x |= 0;
    y |= 0;
    if (x >= 0 && y >= 0 && x < this.w && y < this.h) this.px[y * this.w + x] = v;
  }

  // Pillow rectangle: both corners inclusive.
  rect(x0, y0, x1, y1, { fill = null, outline = null, width = 1 } = {}) {
    if (fill !== null) {
      for (let y = Math.round(y0); y <= Math.round(y1); y++)
        for (let x = Math.round(x0); x <= Math.round(x1); x++) this.set(x, y, fill);
    }
    if (outline !== null) {
      for (let i = 0; i < width; i++) {
        this.rect(x0 + i, y0 + i, x1 - i, y0 + i, { fill: outline });
        this.rect(x0 + i, y1 - i, x1 - i, y1 - i, { fill: outline });
        this.rect(x0 + i, y0 + i, x0 + i, y1 - i, { fill: outline });
        this.rect(x1 - i, y0 + i, x1 - i, y1 - i, { fill: outline });
      }
    }
  }

  // Straight line with a square brush (layouts only use axis-aligned lines).
  line(x0, y0, x1, y1, width = 1, v = 0) {
    const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
    const half = Math.floor((width - 1) / 2);
    for (let i = 0; i <= steps; i++) {
      const x = Math.round(x0 + ((x1 - x0) * i) / steps);
      const y = Math.round(y0 + ((y1 - y0) * i) / steps);
      for (let dy = -half; dy < width - half; dy++)
        for (let dx = -half; dx < width - half; dx++) this.set(x + dx, y + dy, v);
    }
  }

  // Filled ellipse inside the box (x0,y0)-(x1,y1).
  ellipse(x0, y0, x1, y1, v = 0) {
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const rx = (x1 - x0) / 2, ry = (y1 - y0) / 2;
    if (rx <= 0 || ry <= 0) return;
    for (let y = Math.floor(y0); y <= Math.ceil(y1); y++)
      for (let x = Math.floor(x0); x <= Math.ceil(x1); x++) {
        const nx = (x - cx) / rx, ny = (y - cy) / ry;
        if (nx * nx + ny * ny <= 1) this.set(x, y, v);
      }
  }

  // Filled polygon (even-odd scanline).
  polygon(points, v = 0) {
    const ys = points.map((p) => p[1]);
    const minY = Math.floor(Math.min(...ys)), maxY = Math.ceil(Math.max(...ys));
    for (let y = minY; y <= maxY; y++) {
      const xs = [];
      for (let i = 0; i < points.length; i++) {
        const [ax, ay] = points[i];
        const [bx, by] = points[(i + 1) % points.length];
        if ((ay <= y && by > y) || (by <= y && ay > y)) xs.push(ax + ((y - ay) * (bx - ax)) / (by - ay));
      }
      xs.sort((a, b) => a - b);
      for (let i = 0; i + 1 < xs.length; i += 2)
        for (let x = Math.ceil(xs[i]); x <= Math.floor(xs[i + 1]); x++) this.set(x, y, v);
    }
  }

  // ---- text ----

  font(key) {
    const f = atlas.fonts[key];
    if (!f) throw new Error(`font ${key} not in atlas — rebuild with tools/make_atlas.py`);
    return f;
  }

  // Advance width, like Pillow's getlength().
  textWidth(text, key) {
    const f = this.font(key);
    let w = 0;
    for (const ch of text) w += f.glyphs[ch] ? f.glyphs[ch].adv : 0;
    return w;
  }

  /**
   * Draw text with a Pillow anchor: first letter l/m/r (horizontal),
   * second letter a (ascender) or m (middle of ascender/descender).
   */
  text(x, y, text, key, anchor = "la", v = 0) {
    const f = this.font(key);
    const width = this.textWidth(text, key);
    let pen = anchor[0] === "m" ? x - width / 2 : anchor[0] === "r" ? x - width : x;
    // Glyph offsets in the atlas are relative to the ascender line.
    const top = anchor[1] === "m" ? y - (f.ascent + f.descent) / 2 : y;

    for (const ch of text) {
      const g = f.glyphs[ch];
      if (!g) continue; // not in the atlas (e.g. emoji): skip
      this.blit(g, Math.round(pen + g.left), Math.round(top + g.top), v);
      pen += g.adv;
    }
  }

  // Copy one glyph bitmap with its top-left at (gx, gy).
  blit(g, gx, gy, v = 0) {
    if (!g.w || !g.h) return;
    const b = glyphBytes(g), stride = (g.w + 7) >> 3;
    for (let r = 0; r < g.h; r++)
      for (let c = 0; c < g.w; c++)
        if (b[r * stride + (c >> 3)] & (0x80 >> (c & 7))) this.set(gx + c, gy + r, v);
  }

  // Centre a single icon glyph's ink box on (cx, cy) — matches the old draw_icon().
  icon(cx, cy, ch, key, v = 0) {
    const g = this.font(key).glyphs[ch];
    if (g) this.blit(g, Math.round(cx - g.w / 2), Math.round(cy - g.h / 2), v);
  }

  // Trim text with an ellipsis until it fits in maxWidth.
  fit(text, key, maxWidth) {
    if (this.textWidth(text, key) <= maxWidth) return text;
    let t = text;
    while (t.length > 4 && this.textWidth(t + "…", key) > maxWidth) t = t.slice(0, -1);
    return t.trimEnd() + "…";
  }

  sep(y, margin = 20, thickness = 2) {
    this.line(margin, y, this.w - margin, y, thickness);
  }
}
