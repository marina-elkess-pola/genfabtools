// Lightweight geometry helpers for the parking generator (standalone, no React)

export function clonePoints(pts) {
    return (pts || []).map(p => ({ x: p.x, y: p.y }));
}

export function centroid(pts) {
    if (!pts || pts.length === 0) return { x: 0, y: 0 };
    const s = pts.reduce((a, p) => { a.x += p.x; a.y += p.y; return a; }, { x: 0, y: 0 });
    return { x: s.x / pts.length, y: s.y / pts.length };
}

export function rotatePoint(p, c, ang) {
    const s = Math.sin(ang), ccos = Math.cos(ang);
    const dx = p.x - c.x, dy = p.y - c.y;
    return { x: c.x + dx * ccos - dy * s, y: c.y + dx * s + dy * ccos };
}

export function rotatePolygon(pts, c, ang) {
    return pts.map(p => rotatePoint(p, c, ang));
}

export function bbox(pts) {
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

export function pointInPolygon(pt, poly) {
    // Ray casting algorithm, inclusive of edges
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i].x, yi = poly[i].y;
        const xj = poly[j].x, yj = poly[j].y;
        const intersect = ((yi > pt.y) !== (yj > pt.y)) &&
            (pt.x <= (xj - xi) * (pt.y - yi) / ((yj - yi) || 1e-9) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

export function polyContainsRect(rectPoly, boundary) {
    // Require all rectangle corners inside boundary
    return rectPoly.every(p => pointInPolygon(p, boundary));
}

export function rectFromCenterDir(center, dirT, dirN, w, d) {
    // Rectangle with width along T, depth along N
    const hx = (w / 2) * dirT.x; const hy = (w / 2) * dirT.y;
    const nx = (d / 2) * dirN.x; const ny = (d / 2) * dirN.y;
    return [
        { x: center.x - hx - nx, y: center.y - hy - ny },
        { x: center.x + hx - nx, y: center.y + hy - ny },
        { x: center.x + hx + nx, y: center.y + hy + ny },
        { x: center.x - hx + nx, y: center.y - hy + ny },
    ];
}

export function dot(a, b) { return a.x * b.x + a.y * b.y; }
export function norm(v) { const n = Math.hypot(v.x, v.y) || 1; return { x: v.x / n, y: v.y / n }; }

export function principalAxisAngle(pts) {
    // PCA-like closed form angle (atan2(2Cxy, Cxx - Cyy)/2)
    if (!pts || pts.length < 2) return 0;
    const c = centroid(pts);
    let Cxx = 0, Cyy = 0, Cxy = 0;
    for (const p of pts) {
        const dx = p.x - c.x, dy = p.y - c.y;
        Cxx += dx * dx; Cyy += dy * dy; Cxy += dx * dy;
    }
    return 0.5 * Math.atan2(2 * Cxy, (Cxx - Cyy));
}

export function projectionsExtent(pts, axis) {
    // Return min/max scalar projection along a unit axis
    let min = Infinity, max = -Infinity;
    for (const p of pts) {
        const k = p.x * axis.x + p.y * axis.y;
        if (k < min) min = k; if (k > max) max = k;
    }
    return { min, max };
}

export function hsl(i) {
    const hue = (i * 137.508) % 360; // golden angle
    return `hsl(${hue}, 42%, 42%)`;
}

// Compute an inward offset (parallel curve) polygon for a simple boundary at distance s (user units).
// This uses a straight offset per edge and intersects adjacent offsets. For concave corners, it may shrink
// slightly to avoid self-intersections. Intended for visual rings; not a full straight skeleton.
export function computeOffsetPolygon(boundary, s) {
    const pts = clonePoints(boundary || []);
    if (!pts || pts.length < 3 || s <= 0) return null;
    const offsetLines = [];
    for (let i = 0; i < pts.length; i++) {
        const a = pts[i]; const b = pts[(i + 1) % pts.length];
        const dx = b.x - a.x, dy = b.y - a.y;
        const len = Math.hypot(dx, dy);
        if (len < 1e-6) continue;
        // inward normal assuming CCW boundary
        const nx = -dy / len, ny = dx / len;
        // line points offset by s
        const a2 = { x: a.x + nx * s, y: a.y + ny * s };
        const b2 = { x: b.x + nx * s, y: b.y + ny * s };
        // store line in point-direction form
        offsetLines.push({ p: a2, d: { x: dx, y: dy } });
    }
    // intersect consecutive offset lines to get vertices
    const result = [];
    for (let i = 0; i < offsetLines.length; i++) {
        const L1 = offsetLines[i];
        const L2 = offsetLines[(i + 1) % offsetLines.length];
        const x1 = L1.p.x, y1 = L1.p.y, dx1 = L1.d.x, dy1 = L1.d.y;
        const x2 = L2.p.x, y2 = L2.p.y, dx2 = L2.d.x, dy2 = L2.d.y;
        const det = dx1 * (-dy2) - dy1 * (-dx2);
        let t = 0;
        if (Math.abs(det) < 1e-9) {
            // lines nearly parallel; pick midpoint for stability
            result.push({ x: (x1 + x2) / 2, y: (y1 + y2) / 2 });
            continue;
        }
        // Solve for intersection: L1: (x1,y1) + t*(dx1,dy1), L2: (x2,y2) + u*(dx2,dy2)
        // Using perpendicular form to avoid explicit u
        const A = [[dx1, -dx2], [dy1, -dy2]];
        const B = [x2 - x1, y2 - y1];
        // Solve 2x2 for t via Cramer
        const detA = A[0][0] * A[1][1] - A[0][1] * A[1][0];
        const detT = B[0] * A[1][1] - A[0][1] * B[1];
        t = detT / (detA || 1e-9);
        result.push({ x: x1 + t * dx1, y: y1 + t * dy1 });
    }
    // If any vertex fell outside original boundary (concave corner), shrink s slightly and retry once
    const anyOutside = result.some(v => !pointInPolygon(v, pts));
    if (anyOutside && s > 1e-3) return computeOffsetPolygon(boundary, s * 0.9);
    return result;
}
