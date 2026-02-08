// New surface parking design module (clean API)
// Provides architecturally aligned layout independent from legacy generators.

import { rectFromCenterDir, polyContainsRect, pointInPolygon, projectionsExtent, dot } from '../auto/geometry';

export function generateParkingLayout(options) {
    const {
        boundary,
        axisAngle = 0,
        unitsPerMeter = 1,
        stallWidth = 2.6,
        stallDepth = 5.0,
        perimeterWidth = 6.0,
        aisleWidth = 3.6,
        maxAisles = 3,
        aisleDirection = 'two-way',        // 'two-way' | 'one-way'
        connectorDirection = 'two-way',    // 'two-way' | 'one-way'
        includeStalls = false              // streets-only by default for current focus
    } = options || {};

    if (!Array.isArray(boundary) || boundary.length < 3) {
        return { streets: [], aisles: [], connectors: [], stalls: [], access: [] };
    }

    const finalAngle = boundary.length === 4 ? 0 : axisAngle;
    const t = { x: Math.cos(finalAngle), y: Math.sin(finalAngle) };
    const n = { x: -t.y, y: t.x };
    const extT = projectionsExtent(boundary, t);
    const extN = projectionsExtent(boundary, n);

    const W = stallWidth * unitsPerMeter;
    const D = stallDepth * unitsPerMeter;
    const perW = perimeterWidth * unitsPerMeter;
    const aisleW = aisleWidth * unitsPerMeter;

    const inset = Math.max(perW * 0.6, ((extT.max - extT.min) + (extN.max - extN.min)) * 0.01);
    const leftT = extT.min + inset;
    const rightT = extT.max - inset;
    const bottomN = extN.min + inset;
    const topN = extN.max - inset;
    const horizLen = Math.max(0, rightT - leftT);
    const vertLen = Math.max(0, topN - bottomN);

    const streets = [];
    if (horizLen > 0 && vertLen > 0) {
        const centerN = (bottomN + topN) / 2;
        const centerT = (leftT + rightT) / 2;
        streets.push(rectToStreet(boundary, { x: t.x * leftT + n.x * centerN, y: t.y * leftT + n.y * centerN }, vertLen, perW, finalAngle + Math.PI / 2, 'perimeter', { direction: 'two-way', oneWay: false, dir: { x: n.x, y: n.y } }));
        streets.push(rectToStreet(boundary, { x: t.x * rightT + n.x * centerN, y: t.y * rightT + n.y * centerN }, vertLen, perW, finalAngle + Math.PI / 2, 'perimeter', { direction: 'two-way', oneWay: false, dir: { x: n.x, y: n.y } }));
        streets.push(rectToStreet(boundary, { x: t.x * centerT + n.x * bottomN, y: t.y * centerT + n.y * bottomN }, horizLen, perW, finalAngle, 'perimeter', { direction: 'two-way', oneWay: false, dir: { x: t.x, y: t.y } }));
        streets.push(rectToStreet(boundary, { x: t.x * centerT + n.x * topN, y: t.y * centerT + n.y * topN }, horizLen, perW, finalAngle, 'perimeter', { direction: 'two-way', oneWay: false, dir: { x: t.x, y: t.y } }));
    }

    const interiorT = { min: leftT + perW, max: rightT - perW };
    const interiorN = { min: bottomN + perW, max: topN - perW };
    const interiorHeight = Math.max(0, interiorN.max - interiorN.min);
    const interiorWidth = Math.max(0, interiorT.max - interiorT.min);
    const parkingModule = D + aisleW + D;

    const aisles = [];
    const maxModules = Math.floor(interiorHeight / parkingModule);
    const numModules = Math.max(1, Math.min(maxAisles, maxModules));
    if (numModules >= 1 && interiorWidth > 0) {
        const startN = interiorN.min + D + aisleW / 2;
        for (let i = 0; i < numModules; i++) {
            const aisleN = startN + i * parkingModule;
            const center = { x: t.x * ((interiorT.min + interiorT.max) / 2) + n.x * aisleN, y: t.y * ((interiorT.min + interiorT.max) / 2) + n.y * aisleN };
            const isOneWay = (aisleDirection === 'one-way');
            const aisle = rectToStreet(boundary, center, interiorWidth, aisleW, finalAngle, 'aisle', { direction: isOneWay ? 'one-way' : 'two-way', oneWay: isOneWay, dir: { x: t.x, y: t.y } });
            if (aisle) aisles.push(aisle);
        }
    }

    const connectors = [];
    if (aisles.length > 0) {
        const thirds = [interiorT.min + interiorWidth * (1 / 3), interiorT.min + interiorWidth * (2 / 3)];
        const centerN = (interiorN.min + interiorN.max) / 2;
        for (const connT of thirds) {
            const center = { x: t.x * connT + n.x * centerN, y: t.y * connT + n.y * centerN };
            const connOneWay = (connectorDirection === 'one-way');
            // Determine intersection type by counting aisle crossings at this T position
            const crosses = aisles.filter(a => {
                const aCenterT = dot({ x: a.x, y: a.y }, t);
                const halfLen = a.w / 2;
                return (connT >= aCenterT - halfLen && connT <= aCenterT + halfLen);
            }).length;
            const junctionType = (crosses >= 2) ? '+' : 'T';
            const conn = rectToStreet(boundary, center, interiorHeight, aisleW, finalAngle + Math.PI / 2, 'connector', { direction: connOneWay ? 'one-way' : 'two-way', oneWay: connOneWay, dir: { x: n.x, y: n.y }, junction: junctionType });
            if (conn) connectors.push(conn);
        }
        // End-cap connectors: snap aisle ends to nearest perimeter street center for clean T-junctions
        const perimeterTPivots = (streets || [])
            .filter(s => s && s.type === 'perimeter')
            .map(s => dot({ x: s.x, y: s.y }, t));
        for (const a of aisles) {
            const aT = dot({ x: a.x, y: a.y }, t);
            const aN = dot({ x: a.x, y: a.y }, n);
            const halfLen = a.w / 2;
            const endsT = [aT - halfLen, aT + halfLen];
            for (const eT of endsT) {
                // choose nearest perimeter T pivot; fallback to centerline
                let targetT = (interiorT.min + interiorT.max) / 2;
                let best = Number.POSITIVE_INFINITY;
                for (const pt of perimeterTPivots) {
                    const d = Math.abs(eT - pt);
                    if (d < best) { best = d; targetT = pt; }
                }
                const connCenterT = (eT + targetT) / 2;
                const connCenter = { x: t.x * connCenterT + n.x * aN, y: t.y * connCenterT + n.y * aN };
                const connLen = Math.max(aisleW * 1.2, Math.abs(targetT - eT));
                const endConn = rectToStreet(boundary, connCenter, connLen, aisleW, finalAngle, 'connector', { direction: 'two-way', oneWay: false, dir: { x: t.x, y: t.y }, junction: 'T' });
                if (endConn) connectors.push(endConn);
            }
        }
    }

    // Build street polygons first so stall generation can avoid overlaps up-front
    const streetRects = [...streets, ...aisles, ...connectors]
        .filter(Boolean)
        .map(st => {
            const ang = st.angle || finalAngle;
            const tSt = { x: Math.cos(ang), y: Math.sin(ang) };
            const nSt = { x: -tSt.y, y: tSt.x };
            return rectFromCenterDir({ x: st.x, y: st.y }, tSt, nSt, st.w, st.h);
        });

    // Place a centered access band at the bottom connecting into the perimeter
    const access = [];
    {
        const accessT = (leftT + rightT) / 2;
        const neededReach = Math.max(0, (bottomN - extN.min) + perW * 0.7);
        const accessLen = Math.max(perW * 2.2, neededReach);
        const accessW = perW * 0.8;
        const accessCenterN = extN.min + accessLen / 2;
        const accCenter = { x: t.x * accessT + n.x * accessCenterN, y: t.y * accessT + n.y * accessCenterN };
        const acc = rectToStreet(boundary, accCenter, accessLen, accessW, finalAngle + Math.PI / 2, 'access', { direction: 'two-way', oneWay: false });
        if (acc) access.push(acc);
    }

    // Optionally generate stalls; default off while focusing on streets
    const stalls = includeStalls
        ? generateStallsForAisles({ boundary, aisles, stallWidth, stallDepth, unitsPerMeter, streetRects })
        : [];

    // Helpers for precise polygon overlap (convex)
    function bbox(poly) {
        return {
            minx: Math.min(...poly.map(p => p.x)),
            maxx: Math.max(...poly.map(p => p.x)),
            miny: Math.min(...poly.map(p => p.y)),
            maxy: Math.max(...poly.map(p => p.y))
        };
    }
    function bboxesOverlap(a, b) {
        return a.minx <= b.maxx && a.maxx >= b.minx && a.miny <= b.maxy && a.maxy >= b.miny;
    }
    function segInt(a, b, c, d) {
        function orient(p, q, r) { return Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)); }
        const o1 = orient(a, b, c), o2 = orient(a, b, d), o3 = orient(c, d, a), o4 = orient(c, d, b);
        if (o1 === 0 && onSeg(a, c, b)) return true;
        if (o2 === 0 && onSeg(a, d, b)) return true;
        if (o3 === 0 && onSeg(c, a, d)) return true;
        if (o4 === 0 && onSeg(c, b, d)) return true;
        return (o1 !== o2 && o3 !== o4);
    }
    function onSeg(p, q, r) { return Math.min(p.x, r.x) <= q.x && q.x <= Math.max(p.x, r.x) && Math.min(p.y, r.y) <= q.y && q.y <= Math.max(p.y, r.y); }
    function polysOverlap(pa, pb) {
        const ba = bbox(pa), bb = bbox(pb);
        if (!bboxesOverlap(ba, bb)) return false;
        // Vertex-in-polygon tests
        if (pa.some(pt => pointInPolygon(pt, pb))) return true;
        if (pb.some(pt => pointInPolygon(pt, pa))) return true;
        // Edge intersections
        for (let i = 0; i < pa.length; i++) {
            const a1 = pa[i], a2 = pa[(i + 1) % pa.length];
            for (let j = 0; j < pb.length; j++) {
                const b1 = pb[j], b2 = pb[(j + 1) % pb.length];
                if (segInt(a1, a2, b1, b2)) return true;
            }
        }
        return false;
    }

    const filteredStalls = includeStalls
        ? stalls.filter(s => {
            const sr = rectFromCenterDir({ x: s.x, y: s.y }, { x: 1, y: 0 }, { x: 0, y: 1 }, (s.hw || 0) * 2, (s.hd || 0) * 2);
            for (const st of streetRects) {
                if (polysOverlap(sr, st)) return false;
            }
            return true;
        })
        : [];

    return { streets: streets.filter(Boolean), aisles, connectors, stalls: filteredStalls, access };
}

export function generateStallsForAisles(options) {
    const { boundary, aisles = [], stallWidth = 2.6, stallDepth = 5.0, unitsPerMeter = 1, streetRects = [] } = options || {};
    const W = stallWidth * unitsPerMeter;
    const D = stallDepth * unitsPerMeter;
    const stalls = [];
    for (const aisle of aisles) {
        if (!aisle || aisle.type !== 'aisle') continue;
        const tAisle = { x: Math.cos(aisle.angle), y: Math.sin(aisle.angle) };
        const nAisle = { x: -tAisle.y, y: tAisle.x };
        const offset = aisle.h / 2 + D / 2;
        const baseT = dot({ x: aisle.x, y: aisle.y }, tAisle);
        const halfLen = aisle.w / 2;
        const sides = [dot({ x: aisle.x, y: aisle.y }, nAisle) + offset, dot({ x: aisle.x, y: aisle.y }, nAisle) - offset];
        for (const sideN of sides) {
            for (let tp = baseT - halfLen + W / 2; tp < baseT + halfLen - W / 2; tp += W) {
                const center = { x: tAisle.x * tp + nAisle.x * sideN, y: tAisle.y * tp + nAisle.y * sideN };
                const rect = rectFromCenterDir(center, tAisle, nAisle, W, D);
                if (!polyContainsRect(rect, boundary)) continue;
                // Pre-filter: avoid placing a stall if it overlaps any street/connector polygon
                let overlapsLane = false;
                for (const sr of streetRects) {
                    if (polysOverlapRect(sr, rect)) { overlapsLane = true; break; }
                }
                if (!overlapsLane) stalls.push({ x: center.x, y: center.y, hw: W / 2, hd: D / 2 });
            }
        }
    }
    return stalls;
}

// Lightweight polygon-rectangle overlap using AABB prefilter + edge intersections
function polysOverlapRect(poly, rect) {
    const ax0 = Math.min(...rect.map(p => p.x)), ax1 = Math.max(...rect.map(p => p.x));
    const ay0 = Math.min(...rect.map(p => p.y)), ay1 = Math.max(...rect.map(p => p.y));
    const bx0 = Math.min(...poly.map(p => p.x)), bx1 = Math.max(...poly.map(p => p.x));
    const by0 = Math.min(...poly.map(p => p.y)), by1 = Math.max(...poly.map(p => p.y));
    const aabb = ax0 <= bx1 && ax1 >= bx0 && ay0 <= by1 && ay1 >= by0;
    if (!aabb) return false;
    // point-in-polygon checks
    if (rect.some(pt => pointInPolygon(pt, poly))) return true;
    if (poly.some(pt => pointInPolygon(pt, rect))) return true;
    // segment intersection checks
    const segInt = (p1, p2, q1, q2) => {
        const orient = (p, q, r) => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
        const onSeg = (p, q, r) => Math.min(p.x, r.x) <= q.x && q.x <= Math.max(p.x, r.x) && Math.min(p.y, r.y) <= q.y && q.y <= Math.max(p.y, r.y);
        const o1 = orient(p1, p2, q1), o2 = orient(p1, p2, q2), o3 = orient(q1, q2, p1), o4 = orient(q1, q2, p2);
        if (o1 === 0 && onSeg(p1, q1, p2)) return true;
        if (o2 === 0 && onSeg(p1, q2, p2)) return true;
        if (o3 === 0 && onSeg(q1, p1, q2)) return true;
        if (o4 === 0 && onSeg(q1, p2, q2)) return true;
        return (o1 !== o2 && o3 !== o4);
    };
    for (let i = 0; i < rect.length; i++) {
        const a1 = rect[i], a2 = rect[(i + 1) % rect.length];
        for (let j = 0; j < poly.length; j++) {
            const b1 = poly[j], b2 = poly[(j + 1) % poly.length];
            if (segInt(a1, a2, b1, b2)) return true;
        }
    }
    return false;
}

function rectToStreet(boundary, center, length, width, angle, type, extra = {}) {
    const t = { x: Math.cos(angle), y: Math.sin(angle) };
    const n = { x: -t.y, y: t.x };
    let rect = rectFromCenterDir(center, t, n, length, width);
    let tries = 0;
    while (!polyContainsRect(rect, boundary) && tries < 8) {
        length *= 0.92;
        rect = rectFromCenterDir(center, t, n, length, width);
        tries++;
    }
    if (polyContainsRect(rect, boundary) || pointInPolygon(center, boundary)) {
        return { x: center.x, y: center.y, w: length, h: width, angle, type, ...extra };
    }
    return null;
}