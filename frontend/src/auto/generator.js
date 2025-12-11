// Structured parking baseline generator (Stage 1+2)
// Deterministic, fast heuristics: grid → aisles → stalls → columns → validate → score.

import { clonePoints, principalAxisAngle, dot, projectionsExtent, rectFromCenterDir, polyContainsRect, pointInPolygon, hsl } from './geometry';
import { normalizeWithCodeStandards, resolveCirculationParams } from './parkingStandards';
import { generateCirculationNetwork, mergeCirculationToStreets, generateStallsForAisles } from './circulationGenerator';

// Choose an axis aligned to the dominant boundary edge orientation.
// Fallback to principal axis if edges are noisy or boundary is irregular.
function dominantEdgeAxisAngle(boundary) {
    if (!boundary || boundary.length < 2) return principalAxisAngle(boundary || []);
    let sum0 = 0, sum90 = 0;
    for (let i = 0; i < boundary.length; i++) {
        const a = boundary[i];
        const b = boundary[(i + 1) % boundary.length];
        const dx = (b.x - a.x); const dy = (b.y - a.y);
        const len = Math.hypot(dx, dy);
        if (len <= 1e-6) continue;
        const ang = Math.atan2(dy, dx);
        // Normalize to nearest of 0 or 90 degrees relative buckets
        const angMod = ((ang % (Math.PI)) + Math.PI) % Math.PI; // [0, pi)
        const dist0 = Math.min(Math.abs(angMod - 0), Math.abs(Math.PI - angMod));
        const dist90 = Math.abs(angMod - Math.PI / 2);
        // Weight by edge length
        const w0 = Math.max(0, 1 - Math.min(1, dist0 / (Math.PI / 8)));
        const w90 = Math.max(0, 1 - Math.min(1, dist90 / (Math.PI / 8)));
        sum0 += w0 * len;
        sum90 += w90 * len;
    }
    // If one orientation dominates, lock axis to it
    if (sum0 > sum90 * 1.2) return 0; // along X
    if (sum90 > sum0 * 1.2) return Math.PI / 2; // along Y
    return principalAxisAngle(boundary || []);
}

function resolveAisleWidthMeters(p) {
    // Use code-based standards if codeSet is provided
    if (p.codeSet) {
        const circ = resolveCirculationParams(p.codeSet, p.aisleType || 'two-way');
        return circ.driveWidth;
    }
    // Fallback to legacy logic
    const baseTwoWay = (typeof p.driveWidth === 'number' && p.driveWidth > 0) ? p.driveWidth : 6.0;
    const t = (p.aisleType || 'two-way');
    if (t === 'one-way') return 3.5;
    return baseTwoWay; // 'two-way' default
}

function resolveStreetWidthMeters(p) {
    // Use code-based standards if codeSet is provided
    if (p.codeSet) {
        const circ = resolveCirculationParams(p.codeSet, p.streetType || 'two-way');
        // Fire lanes and spines use fire lane width
        if (p.streetType === 'spine' || p.streetType === 'fire-lane') {
            return circ.fireLaneWidth;
        }
        return circ.driveWidth;
    }
    // Fallback to legacy logic
    const baseTwoWay = (typeof p.driveWidth === 'number' && p.driveWidth > 0) ? p.driveWidth : 6.0;
    const t = (p.streetType || 'two-way');
    if (t === 'one-way') return 3.5;
    if (t === 'spine') return Math.max(baseTwoWay, 7.0);
    return baseTwoWay; // 'two-way' default
}

// Small helper: deduplicate band/rect entries (x,y,w,h,angle) by rounded keys
function dedupeBands(arr) {
    if (!Array.isArray(arr) || arr.length === 0) return arr || [];
    const seen = new Set();
    const out = [];
    for (const b of arr) {
        if (!b) continue;
        const k = `${Math.round((b.x || 0) * 1000)}_${Math.round((b.y || 0) * 1000)}_${Math.round((b.w || 0) * 1000)}_${Math.round((b.h || 0) * 1000)}_${Math.round(((b.angle || 0)) * 1000)}`;
        if (!seen.has(k)) { seen.add(k); out.push(b); }
    }
    return out;
}

// Merge bands by geometry ignoring `type`. When duplicates are found, choose a
// type by priority so connectors remain visible: connector > aisle > street > access > ramp
function mergeBands(arr) {
    if (!Array.isArray(arr) || arr.length === 0) return arr || [];
    const out = [];
    const typePriority = { connector: 5, aisle: 4, street: 3, access: 2, ramp: 1 };
    // clustering merge: group bands that are close in position, similar angle, and similar size
    for (const b of arr) {
        if (!b) continue;
        let merged = false;
        for (const ex of out) {
            const dx = (b.x || 0) - (ex.x || 0);
            const dy = (b.y || 0) - (ex.y || 0);
            const dist = Math.hypot(dx, dy);
            const angDiff = Math.abs(((b.angle || 0) - (ex.angle || 0)) % (Math.PI));
            const angClose = Math.min(Math.abs(angDiff), Math.abs(Math.PI - angDiff));
            // threshold: centers within quarter of average length OR small absolute (2 units)
            const avgLen = Math.max(1, ((b.w || 0) + (ex.w || 0)) / 2);
            // more aggressive merge: allow larger center tolerance relative to length
            const centerThresh = Math.max(3, avgLen * 0.5);
            const sizeRatioW = Math.max(0.01, Math.min((b.w || 0) / (ex.w || 1), (ex.w || 1) / Math.max(0.01, (b.w || 0))));
            const sizeRatioH = Math.max(0.01, Math.min((b.h || 0) / (ex.h || 1), (ex.h || 1) / Math.max(0.01, (b.h || 0))));
            const sizeSimilar = sizeRatioW > 0.5 && sizeRatioH > 0.5;
            if (dist <= centerThresh && angClose < 0.2 && sizeSimilar) {
                // merge into ex: average center, expand w/h to max, pick higher-priority type
                ex.x = (ex.x + b.x) / 2;
                ex.y = (ex.y + b.y) / 2;
                ex.w = Math.max(ex.w || 0, b.w || 0);
                ex.h = Math.max(ex.h || 0, b.h || 0);
                const te = ex.type || 'street'; const tn = b.type || 'street';
                if ((typePriority[tn] || 0) > (typePriority[te] || 0)) ex.type = tn;
                merged = true; break;
            }
        }
        if (!merged) out.push(Object.assign({}, b));
    }
    try { console.info('[generator] mergeBands:', { in: arr.length, out: out.length }); } catch (e) { }
    return out;
}

/**
 * @typedef {Object} GenParams
 * @property {number} unitsPerMeter - user units per meter (required)
 * @property {number} stallWidth - meters
 * @property {number} stallDepth - meters
 * @property {number} driveWidth - meters (two-way)
 * @property {number[]} anglesDeg - candidate angles to test, relative to principal axis (e.g., [0, 15, -15])
 * @property {number[]} stallAngles - array of stall angles to try (e.g., [90, 60])
 * @property {number} clipAcceptance - fraction (0..1) of stall area required to accept (simplified as all-corners-inside here)
 * @property {number} columnSpacing - meters (square grid) default 7.5
 * @property {number} columnClearance - meters around aisles and stalls
 */

/**
 * @typedef {Object} Scheme
 * @property {Array<{x:number,y:number}>} points - boundary
 * @property {boolean} closed
 * @property {string} color
 * @property {Array<{x:number,y:number, hw:number, hd:number}>} stalls - rectangles (center x,y half widths hw,hd)
 * @property {Array<{x:number,y:number, w:number, h:number, angle:number}>} aisles - centerlines as thin rectangles for viz
 * @property {Array<{x:number,y:number, w:number, h:number, angle:number}>} streets - perimeter/entry circulation bands
 * @property {Array<{x:number,y:number, w:number, h:number, angle:number}>} access - access zones near entries
 * @property {Array<{x:number,y:number}>} columns - column centers
 * @property {Array<{x:number,y:number, w:number, h:number, angle:number}>} ramps - simple rectangles
 * @property {{stalls:number, aisles:number, columns:number, conflicts:number, score:number}} counts
 */

function metersToUnits(m, upm) { return m * (Number(upm) || 1); }

export function generateBaselineSchemes(boundaryPts, params) {
    const p = normalizeParams(params);
    const boundary = clonePoints(boundaryPts || []);
    if (!boundary || boundary.length < 3) return [];
    const upm = p.unitsPerMeter;
    const W = metersToUnits(p.stallWidth, upm);
    const D = metersToUnits(p.stallDepth, upm);
    const WD_AISLE = metersToUnits(resolveAisleWidthMeters(p), upm);
    const WD_STREET = metersToUnits(resolveStreetWidthMeters(p), upm);
    const PITCH = WD_AISLE + 2 * D; // double-loaded module pitch across normal
    const baseAng = (p.axisStrategy === 'edge-longest' || p.enforceOrthogonalLayout || p.avoidDeadEnds)
        ? dominantEdgeAxisAngle(boundary)
        : principalAxisAngle(boundary);
    const candidates = (p.anglesDeg || [0]).map(d => baseAng + (d * Math.PI / 180));

    const results = [];
    let idxColor = 0;

    // Try multiple normal-phase offsets to vary aisle placement across the site
    const phaseFractions = [0.0, 0.33, 0.5];
    for (const ang of candidates) {
        for (const stallAng of p.stallAngles) {
            for (const f of phaseFractions) {
                const res = layoutOnce(boundary, p, ang, stallAng * Math.PI / 180, f);
                if (res) { res.color = hsl(++idxColor); results.push(res); }
            }
        }
    }

    // rank by score desc
    results.sort((a, b) => (b.counts?.score || 0) - (a.counts?.score || 0));
    const top = results.slice(0, p.keepTop);
    try {
        top.forEach((r, idx) => {
            try { console.info('[generator] baseline result', idx, 'stalls=', (r.stalls || []).length, 'aisles=', (r.aisles || []).length, 'streets=', (r.streets || []).length, 'counts=', r.counts); } catch (e) { }
        });
    } catch (e) { }
    return top;
}

// Structural-first generator: columns define modules, then stalls/aisles fill modules
// Typical underground parking module pitch across rows: 2*stallDepth + driveWidth (double-loaded)
// Typical column spans along row direction: ~7.5m, 8.0m (approx 3 stall widths)
// We attempt several span presets and return top schemes by stall count and continuity
export function generateStructuralSchemes(boundaryPts, params) {
    const p = normalizeParams(params);
    const boundary = clonePoints(boundaryPts || []);
    if (!boundary || boundary.length < 3) return [];
    const upm = p.unitsPerMeter;
    const W = metersToUnits(p.stallWidth, upm);
    const D = metersToUnits(p.stallDepth, upm);
    const WD_AISLE = metersToUnits(resolveAisleWidthMeters(p), upm);
    const WD_STREET = metersToUnits(resolveStreetWidthMeters(p), upm);
    const pitchY = 2 * D + WD_AISLE; // double-loaded module height (normal direction)
    const axisAngle = (p.axisStrategy === 'edge-longest' || p.enforceOrthogonalLayout || p.avoidDeadEnds)
        ? dominantEdgeAxisAngle(boundary)
        : principalAxisAngle(boundary);
    const t = { x: Math.cos(axisAngle), y: Math.sin(axisAngle) };
    const n = { x: -t.y, y: t.x };
    const extT = projectionsExtent(boundary, t);
    const extN = projectionsExtent(boundary, n);
    const accessMode = p.accessPlacement || 'auto'; // 'auto' | 'min-edge' | 'max-edge' | 'center'
    // structural span presets (meters) along t direction. Allow explicit override from params
    // Choose span presets. If a target stall count is provided, explore a slightly wider range to better fit capacity.
    const defaultPresets = [7.0, 7.5, 8.0];
    const targetAwarePresets = [6.5, 7.0, 7.5, 8.0, 8.5];
    const spanPresetsM = Array.isArray(p.spanPresetsMeters) && p.spanPresetsMeters.length > 0
        ? p.spanPresetsMeters
        : (typeof p.columnSpacing === 'number' && p.columnSpacing > 0
            ? [p.columnSpacing]
            : (typeof p.targetStalls === 'number' && p.targetStalls > 0 ? targetAwarePresets : defaultPresets));
    const schemes = [];
    let colorIdx = 0;
    for (const spanM of spanPresetsM) {
        const span = metersToUnits(spanM, upm);
        // compute t positions for column lines (span multiples)
        // start grid at or before boundary extents so boundary is included in the grid framing
        const startT = Math.floor(extT.min / span) * span;
        const tLines = [];
        for (let tt = startT; tt <= extT.max + span; tt += span) tLines.push(tt);
        // compute n positions for row boundaries (pitch multiples)
        const startN = Math.floor(extN.min / pitchY) * pitchY;
        const nLines = [];
        for (let nn = startN; nn <= extN.max + pitchY; nn += pitchY) nLines.push(nn);
        if (tLines.length < 2 || nLines.length < 2) continue; // insufficient grid for modules
        // derive columns at intersections of tLines & nLines
        const columns = [];
        for (const tt of tLines) {
            for (const nn of nLines) {
                const c = { x: t.x * tt + n.x * nn, y: t.y * tt + n.y * nn };
                if (pointInPolygon(c, boundary)) columns.push(c);
            }
        }
        // generate modules (cells) between consecutive nLines; inside each cell create aisle & stalls
        const stalls = [];
        const aisles = [];
        for (let ri = 0; ri < nLines.length - 1; ri++) {
            const n0 = nLines[ri];
            const n1 = nLines[ri + 1];
            const cellHeight = n1 - n0;
            if (cellHeight < pitchY * 0.9) continue; // skip undersized band
            // aisle center at mid normal coordinate
            const aisleN = (n0 + n1) / 2;
            const aisleLen = (extT.max - extT.min);
            const aisleCenterT = (extT.min + extT.max) / 2;
            const aisleCenter = { x: t.x * aisleCenterT + n.x * aisleN, y: t.y * aisleCenterT + n.y * aisleN };
            let fitLen = aisleLen;
            let aisleRect = rectFromCenterDir(aisleCenter, t, n, fitLen, WD_AISLE);
            let triesFit = 0;
            while (!polyContainsRect(aisleRect, boundary) && triesFit < 8 && fitLen > WD_AISLE) {
                fitLen *= 0.9;
                aisleRect = rectFromCenterDir(aisleCenter, t, n, fitLen, WD_AISLE);
                triesFit++;
            }
            if (polyContainsRect(aisleRect, boundary)) {
                aisles.push({ x: aisleCenter.x, y: aisleCenter.y, w: fitLen, h: WD_AISLE, angle: axisAngle });
            }
            // stall row centers: back-to-back rows offset from aisle center by DR/2 + D/2
            const rowOffsets = [-(WD_AISLE / 2 + D / 2), (WD_AISLE / 2 + D / 2)];
            const halfLen = fitLen / 2;
            const effStartT = aisleCenterT - halfLen;
            const effEndT = aisleCenterT + halfLen;
            const startStallT = Math.ceil(effStartT / W) * W;
            for (const off of rowOffsets) {
                const rowN = aisleN + off;
                for (let tt = startStallT; tt <= effEndT - W / 2; tt += W) {
                    const c = { x: t.x * tt + n.x * rowN, y: t.y * tt + n.y * rowN };
                    const rect = rectFromCenterDir(c, t, n, W, D);
                    if (polyContainsRect(rect, boundary)) {
                        stalls.push({ x: c.x, y: c.y, hw: W / 2, hd: D / 2 });
                    }
                }
            }
        }
        // De-duplicate stalls that overlap due to perimeter-first complement adding rows near existing modules
        const dedupStalls = [];
        for (const s of stalls) {
            const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, W, D);
            let overlapsExisting = false;
            for (const kept of dedupStalls) {
                const kr = rectFromCenterDir({ x: kept.x, y: kept.y }, t, n, W, D);
                if (rectsOverlap(sr, kr)) { overlapsExisting = true; break; }
            }
            if (!overlapsExisting) dedupStalls.push(s);
        }
        // Work with de-duplicated set from here on
        const stallsDedupe = dedupStalls;
        // streets: perimeter bands along long axis near extT edges
        const streetW = WD_STREET;
        const streetLen = Math.abs(extN.max - extN.min);
        const streetTInset = metersToUnits(1.2, upm); // small inset
        const streetTPositions = [extT.min + streetW / 2 + streetTInset, extT.max - streetW / 2 - streetTInset];
        const streets = [];
        for (const tPos of streetTPositions) {
            if (tPos <= extT.min || tPos >= extT.max) continue;
            const c = { x: t.x * tPos + n.x * ((extN.min + extN.max) / 2), y: t.y * tPos + n.y * ((extN.min + extN.max) / 2) };
            const r = rectFromCenterDir(c, t, n, streetW, streetLen);
            // Accept street if fully contained or if its center lies inside boundary (allow partial streets)
            const contains = polyContainsRect(r, boundary) || pointInPolygon(c, boundary);
            // diagnostic log to help debug why streets may be rejected
            try {
                console.info('[generator] street candidate', { tPos, streetW, streetLen, center: c, contains });
            } catch (e) { }
            if (contains) streets.push({ x: c.x, y: c.y, w: streetW, h: streetLen, angle: axisAngle, type: 'street' });
        }
        // Perimeter ring: optionally generate perimeter street ring and perimeter stalls
        // Controlled by p.applyRingToGenerator to avoid always mutating baseline behavior
        if (p.applyRingToGenerator) {
            const offsetM = (typeof p.perimeterStreetOffsetMeters === 'number' ? p.perimeterStreetOffsetMeters : 1.0);
            const margin = metersToUnits(Math.max(0, offsetM), upm);
            const topN = extN.max - (WD_STREET + D / 2 + margin);
            const bottomN = extN.min + (WD_STREET + D / 2 + margin);
            const leftCenterT = extT.min + (WD_STREET + D / 2 + margin);
            const rightCenterT = extT.max - (WD_STREET + D / 2 + margin);
            // Optionally add perimeter stall rows if explicitly enabled
            if (p.enablePerimeterStalls) {
                // Horizontal (top and bottom) rows
                const alongTStart = extT.min + W / 2 + margin;
                const alongTEnd = extT.max - W / 2 - margin;
                for (let tt = alongTStart; tt <= alongTEnd; tt += W) {
                    const cb = { x: t.x * tt + n.x * bottomN, y: t.y * tt + n.y * bottomN };
                    const rb = rectFromCenterDir(cb, t, n, W, D);
                    if (polyContainsRect(rb, boundary)) stalls.push({ x: cb.x, y: cb.y, hw: W / 2, hd: D / 2 });
                    const ct = { x: t.x * tt + n.x * topN, y: t.y * tt + n.y * topN };
                    const rt = rectFromCenterDir(ct, t, n, W, D);
                    if (polyContainsRect(rt, boundary)) stalls.push({ x: ct.x, y: ct.y, hw: W / 2, hd: D / 2 });
                }
                // Vertical (left and right) rows
                const nAlongStart = extN.min + W / 2 + margin;
                const nAlongEnd = extN.max - W / 2 - margin;
                for (let nn = nAlongStart; nn <= nAlongEnd; nn += W) {
                    const cl = { x: t.x * leftCenterT + n.x * nn, y: t.y * leftCenterT + n.y * nn };
                    const rl = rectFromCenterDir(cl, n, t, W, D);
                    if (polyContainsRect(rl, boundary)) stalls.push({ x: cl.x, y: cl.y, hw: W / 2, hd: D / 2 });
                    const cr = { x: t.x * rightCenterT + n.x * nn, y: t.y * rightCenterT + n.y * nn };
                    const rr = rectFromCenterDir(cr, n, t, W, D);
                    if (polyContainsRect(rr, boundary)) stalls.push({ x: cr.x, y: cr.y, hw: W / 2, hd: D / 2 });
                }
            }
            // Add a perimeter street ring for clean circulation (fit-checked)
            const horizLen = Math.max(0, (extT.max - extT.min) - 2 * (WD_STREET + margin));
            const vertLen = Math.max(0, (extN.max - extN.min) - 2 * (WD_STREET + margin));
            if (horizLen > 0) {
                const topStreetC = { x: t.x * ((extT.min + extT.max) / 2) + n.x * topN, y: t.y * ((extT.min + extT.max) / 2) + n.y * topN };
                let topLen = horizLen;
                let topStreetR = rectFromCenterDir(topStreetC, t, n, topLen, WD_STREET);
                let triesTop = 0;
                while (!polyContainsRect(topStreetR, boundary) && triesTop < 8 && topLen > WD_STREET) {
                    topLen *= 0.9;
                    topStreetR = rectFromCenterDir(topStreetC, t, n, topLen, WD_STREET);
                    triesTop++;
                }
                if (polyContainsRect(topStreetR, boundary) || pointInPolygon(topStreetC, boundary)) streets.push({ x: topStreetC.x, y: topStreetC.y, w: topLen, h: WD_STREET, angle: axisAngle, type: 'street' });
                else try { console.info('[generator] top perimeter street failed contain check', { topLen, topStreetC }); } catch (e) { }

                const botStreetC = { x: t.x * ((extT.min + extT.max) / 2) + n.x * bottomN, y: t.y * ((extT.min + extT.max) / 2) + n.y * bottomN };
                let botLen = horizLen;
                let botStreetR = rectFromCenterDir(botStreetC, t, n, botLen, WD_STREET);
                let triesBot = 0;
                while (!polyContainsRect(botStreetR, boundary) && triesBot < 8 && botLen > WD_STREET) {
                    botLen *= 0.9;
                    botStreetR = rectFromCenterDir(botStreetC, t, n, botLen, WD_STREET);
                    triesBot++;
                }
                if (polyContainsRect(botStreetR, boundary) || pointInPolygon(botStreetC, boundary)) streets.push({ x: botStreetC.x, y: botStreetC.y, w: botLen, h: WD_STREET, angle: axisAngle, type: 'street' });
                else try { console.info('[generator] bottom perimeter street failed contain check', { botLen, botStreetC }); } catch (e) { }
            }
            if (vertLen > 0) {
                const leftStreetC = { x: t.x * leftCenterT + n.x * ((extN.min + extN.max) / 2), y: t.y * leftCenterT + n.y * ((extN.min + extN.max) / 2) };
                let leftH = vertLen;
                let leftStreetR = rectFromCenterDir(leftStreetC, n, t, leftH, WD_STREET);
                let triesL = 0;
                while (!polyContainsRect(leftStreetR, boundary) && triesL < 8 && leftH > WD_STREET) {
                    leftH *= 0.9;
                    leftStreetR = rectFromCenterDir(leftStreetC, n, t, leftH, WD_STREET);
                    triesL++;
                }
                if (polyContainsRect(leftStreetR, boundary) || pointInPolygon(leftStreetC, boundary)) streets.push({ x: leftStreetC.x, y: leftStreetC.y, w: leftH, h: WD_STREET, angle: axisAngle + Math.PI / 2, type: 'street' });
                else try { console.info('[generator] left perimeter street failed contain check', { leftH, leftStreetC }); } catch (e) { }

                const rightStreetC = { x: t.x * rightCenterT + n.x * ((extN.min + extN.max) / 2), y: t.y * rightCenterT + n.y * ((extN.min + extN.max) / 2) };
                let rightH = vertLen;
                let rightStreetR = rectFromCenterDir(rightStreetC, n, t, rightH, WD_STREET);
                let triesR = 0;
                while (!polyContainsRect(rightStreetR, boundary) && triesR < 8 && rightH > WD_STREET) {
                    rightH *= 0.9;
                    rightStreetR = rectFromCenterDir(rightStreetC, n, t, rightH, WD_STREET);
                    triesR++;
                }
                if (polyContainsRect(rightStreetR, boundary) || pointInPolygon(rightStreetC, boundary)) streets.push({ x: rightStreetC.x, y: rightStreetC.y, w: rightH, h: WD_STREET, angle: axisAngle + Math.PI / 2, type: 'street' });
                else try { console.info('[generator] right perimeter street failed contain check', { rightH, rightStreetC }); } catch (e) { }
            }
        }
        // Circulation spine: disabled in structural-only revert
        if (false && p.circulationMode === 'spine') {
            const midT = (extT.min + extT.max) / 2;
            const c = { x: t.x * midT + n.x * ((extN.min + extN.max) / 2), y: t.y * midT + n.y * ((extN.min + extN.max) / 2) };
            let r = rectFromCenterDir(c, t, n, streetW, streetLen);
            // If clipped, shrink length until fully inside
            let triesSp = 0; let spineLen = streetLen;
            while (!polyContainsRect(r, boundary) && triesSp < 6) {
                spineLen *= 0.9;
                r = rectFromCenterDir(c, t, n, streetW, spineLen);
                triesSp++;
            }
            if (polyContainsRect(r, boundary)) streets.push({ x: c.x, y: c.y, w: streetW, h: spineLen, angle: axisAngle, type: 'street' });
        }
        // cross connectors: disabled in structural-only revert
        // Strategy: if explicit spacing is provided, use it; otherwise place exactly `minConnectorCount` evenly across width.
        const connectorSpacingUnits = 0;
        const connectorCentersT = new Set();
        if (connectorSpacingUnits && connectorSpacingUnits > 0) {
            for (let tt = extT.min + connectorSpacingUnits / 2; tt <= extT.max - connectorSpacingUnits / 2; tt += connectorSpacingUnits) {
                connectorCentersT.add(tt);
            }
        } else {
            let minConn = Math.max(0, Number(p.minConnectorCount || 0));
            if ((p.circulationMode === 'loop' || p.circulationMode === 'grid' || p.avoidDeadEnds) && minConn < 2) minConn = 2;
            if (p.circulationMode === 'grid') minConn = Math.max(minConn, 3);
            for (let i = 1; i <= minConn; i++) {
                const frac = i / (minConn + 1);
                connectorCentersT.add(extT.min + (extT.max - extT.min) * frac);
            }
        }
        // Compute the vertical span needed to actually bridge all horizontal aisles
        const aisleNs = aisles
            .filter(a => Math.abs(a.h - WD_AISLE) <= WD_AISLE * 0.51)
            .map(a => dot({ x: a.x, y: a.y }, n));
        const hasAisles = aisleNs.length > 0;
        const minAisleN = hasAisles ? Math.min(...aisleNs) : extN.min;
        const maxAisleN = hasAisles ? Math.max(...aisleNs) : extN.max;
        const connSpanLen = Math.max(WD_STREET * 2.2, (maxAisleN - minAisleN) + WD_STREET * 0.8);
        const connSpanCenterN = (hasAisles ? (minAisleN + maxAisleN) / 2 : (extN.min + extN.max) / 2);

        // Place vertical bands at each chosen t coordinate, with robust fitting
        const connectorRects = [];
        for (const tPos of connectorCentersT) {
            const c = { x: t.x * tPos + n.x * connSpanCenterN, y: t.y * tPos + n.y * connSpanCenterN };
            let wConn = WD_STREET; let hConn = connSpanLen; let r = rectFromCenterDir(c, t, n, wConn, hConn); let triesC = 0;
            // Try shrinking width, then slight lateral shifts to find a fit
            while (!polyContainsRect(r, boundary) && triesC < 18) {
                if (wConn > WD_STREET * 0.6) {
                    wConn *= 0.85;
                } else {
                    // shift +/- small fractions of stall width to find an interior fit
                    const shift = (triesC % 2 === 0 ? +1 : -1) * Math.min(W * 0.5, WD_STREET);
                    const cShift = { x: t.x * (tPos + shift) + n.x * ((extN.min + extN.max) / 2), y: t.y * (tPos + shift) + n.y * ((extN.min + extN.max) / 2) };
                    r = rectFromCenterDir(cShift, t, n, wConn, hConn);
                    triesC++;
                    continue;
                }
                // try shrinking height if width and shifts weren't enough
                if (hConn > connSpanLen * 0.6) {
                    hConn *= 0.9;
                }
                r = rectFromCenterDir(c, t, n, wConn, hConn);
                triesC++;
            }
            // If still not fully inside, accept a conservative clipped connector centered within boundary
            if (!polyContainsRect(r, boundary)) {
                hConn = Math.max(WD_STREET * 2, connSpanLen * 0.6);
                wConn = Math.max(WD_STREET * 0.6, wConn);
                r = rectFromCenterDir(c, t, n, wConn, hConn);
            }
            // Accept connector band if it fits, or if its center/anchors are inside, or if forced for dev
            const centerInside = pointInPolygon(c, boundary);
            const rectInside = polyContainsRect(r, boundary);
            if (rectInside || centerInside || p.forceConnectors) {
                streets.push({ x: c.x, y: c.y, w: wConn, h: hConn, angle: (axisAngle || 0), type: 'connector' });
                try { console.info('[generator] baseline connector created', { tPos, center: c, wConn, hConn, rectInside, centerInside }); } catch (e) { }
            } else {
                try { console.info('[generator] baseline connector rejected', { tPos, center: c, wConn, hConn, rectInside, centerInside }); } catch (e) { }
            }
        }
        // Skip adding extra intersection squares to reduce visual clutter
        // End-cap connectors: disabled in structural-only revert
        // We add short drive-width bands at both ends of the aisle towards the nearest street T-position.
        // Populate `streetTPivots` from any streets already created so end-cap logic can reference real streets
        // store both t and n coordinates so connectors can align in both axes
        let streetTPivots = (streets || []).map(s => ({ t: dot({ x: s.x, y: s.y }, t), n: dot({ x: s.x, y: s.y }, n) }));
        let endCapsCount = 0;
        for (const a of aisles) {
            if (Math.abs(a.h - WD_AISLE) > WD_AISLE * 0.51) continue;
            const aCenterT = dot({ x: a.x, y: a.y }, t);
            const aCenterN = dot({ x: a.x, y: a.y }, n);
            const halfLen = a.w / 2;
            const endsT = [aCenterT - halfLen, aCenterT + halfLen];
            for (const eT of endsT) {
                // find nearest street pivot along t
                let nearestT = null; let bestDist = Number.POSITIVE_INFINITY;
                for (const sT of streetTPivots) {
                    const d = Math.abs(eT - sT);
                    if (d < bestDist) { bestDist = d; nearestT = sT; }
                }
                if (nearestT == null) continue;
                const connCenterT = (eT + nearestT) / 2;
                // Aim to fully bridge from aisle end to nearest street pivot
                let connLen = Math.max(WD_STREET * 1.2, Math.min(Math.abs(nearestT - eT), metersToUnits(25, upm)));
                const connCenter = { x: t.x * connCenterT + n.x * aCenterN, y: t.y * connCenterT + n.y * aCenterN };
                // Iteratively shrink until fully inside the boundary to avoid clipped bands
                let connRect = rectFromCenterDir(connCenter, t, n, connLen, WD_STREET);
                let triesEC = 0;
                while (!polyContainsRect(connRect, boundary) && triesEC < 6) {
                    connLen *= 0.8;
                    connRect = rectFromCenterDir(connCenter, t, n, connLen, WD_STREET);
                    triesEC++;
                }
                // If connectors are forced (dev) or connectors are enabled, try to emit a short connector
                if (p.forceConnectors || p.enableConnectors) {
                    // build a connector between aisle end and the nearest street pivot
                    const anchorA = { x: t.x * eT + n.x * aCenterN, y: t.y * eT + n.y * aCenterN };
                    // nearestT may be a pivot object (with t/n) or a plain number; normalize to world coord
                    let targetWorld;
                    if (nearestT && typeof nearestT === 'object' && nearestT.t != null) {
                        targetWorld = { x: t.x * nearestT.t + n.x * nearestT.n, y: t.y * nearestT.t + n.y * nearestT.n };
                    } else if (typeof nearestT === 'number') {
                        targetWorld = { x: t.x * nearestT + n.x * aCenterN, y: t.y * nearestT + n.y * aCenterN };
                    } else {
                        targetWorld = { x: t.x * aCenterT + n.x * aCenterN, y: t.y * aCenterT + n.y * aCenterN };
                    }
                    const dxC = targetWorld.x - anchorA.x; const dyC = targetWorld.y - anchorA.y; const distC = Math.hypot(dxC, dyC);
                    if (distC > 1e-6) {
                        const angC = Math.atan2(dyC, dxC);
                        const tC = { x: Math.cos(angC), y: Math.sin(angC) };
                        const nC = { x: -tC.y, y: tC.x };
                        const centerC = { x: (anchorA.x + targetWorld.x) / 2, y: (anchorA.y + targetWorld.y) / 2 };
                        let cLen = distC + Math.max(WD_STREET * 0.5, metersToUnits(1, upm));
                        let cRect = rectFromCenterDir(centerC, tC, nC, cLen, WD_STREET);
                        let triesC2 = 0;
                        while (!polyContainsRect(cRect, boundary) && triesC2 < 8 && cLen > metersToUnits(4, upm)) {
                            cLen *= 0.8; cRect = rectFromCenterDir(centerC, tC, nC, cLen, WD_STREET); triesC2++;
                        }
                        const centerInsideC = pointInPolygon(centerC, boundary);
                        const aInside = pointInPolygon(anchorA, boundary);
                        const bInside = pointInPolygon(targetWorld, boundary);
                        const rectInsideC = polyContainsRect(cRect, boundary);
                        if (rectInsideC || centerInsideC || aInside || bInside || p.forceConnectors) {
                            streets.push({ x: centerC.x, y: centerC.y, w: cLen, h: WD_STREET, angle: angC, type: 'connector' });
                            try { console.info('[generator] endcap connector created', { from: anchorA, to: targetWorld, center: centerC, len: cLen, reason: rectInsideC ? 'rect' : (centerInsideC ? 'center' : (aInside ? 'aInside' : (bInside ? 'bInside' : 'forced'))) }); } catch (e) { }
                        } else {
                            try { console.info('[generator] endcap connector rejected', { center: centerC, len: cLen, aInside, bInside, centerInsideC, rectInsideC }); } catch (e) { }
                        }
                    }
                }
            }
        }
        // access zones: flexible placement candidates, choose best by minimal stall removal
        const access = [];
        const accessLen = Math.min(metersToUnits(30, upm), (extT.max - extT.min) * 0.4);
        const accessW = WD_STREET * 0.8;
        const accessNCandidates = [extN.min + accessW / 2 + metersToUnits(0.5, upm), (extN.min + extN.max) / 2, extN.max - accessW / 2 - metersToUnits(0.5, upm)];
        const accessTCandidates = [extT.min + accessLen / 2 + metersToUnits(0.5, upm), (extT.min + extT.max) / 2, extT.max - accessLen / 2 - metersToUnits(0.5, upm)];
        let bestAccess = null, bestImpact = Number.POSITIVE_INFINITY;
        const placeCandidates = [];
        // Build candidate centers according to mode
        if (accessMode === 'min-edge') {
            placeCandidates.push({ tPos: accessTCandidates[0], nPos: accessNCandidates[0] });
        } else if (accessMode === 'max-edge') {
            placeCandidates.push({ tPos: accessTCandidates[2], nPos: accessNCandidates[2] });
        } else if (accessMode === 'center') {
            placeCandidates.push({ tPos: accessTCandidates[1], nPos: accessNCandidates[1] });
        } else {
            // auto: evaluate a small set along edges and center
            for (const nPos of accessNCandidates) {
                for (const tPos of accessTCandidates) {
                    placeCandidates.push({ tPos, nPos });
                }
            }
        }
        for (const cand of placeCandidates) {
            const c = { x: t.x * cand.tPos + n.x * cand.nPos, y: t.y * cand.tPos + n.y * cand.nPos };
            const r = rectFromCenterDir(c, t, n, accessLen, accessW);
            if (!polyContainsRect(r, boundary)) continue;
            // compute stall impact: number of stalls whose rect overlaps r
            let impact = 0;
            for (const s of stalls) {
                const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, W, D);
                const overlap = rectsOverlap(r, sr);
                if (overlap) impact++;
            }
            if (impact < bestImpact) { bestImpact = impact; bestAccess = { x: c.x, y: c.y, w: accessLen, h: accessW, angle: axisAngle }; }
        }
        if (bestAccess) {
            access.push(bestAccess);
            // Optional separate entry/exit: place a second access on opposite edge if requested
            if (p.separateEntryExit) {
                let oppBest = null; let oppImpact = Number.POSITIVE_INFINITY;
                const targetT = dot({ x: bestAccess.x, y: bestAccess.y }, t);
                const oppositeTPivot = (targetT < (extT.min + extT.max) / 2) ? accessTCandidates[2] : accessTCandidates[0];
                for (const nPos of accessNCandidates) {
                    const cOpp = { x: t.x * oppositeTPivot + n.x * nPos, y: t.y * oppositeTPivot + n.y * nPos };
                    const rOpp = rectFromCenterDir(cOpp, t, n, accessLen, accessW);
                    if (!polyContainsRect(rOpp, boundary)) continue;
                    let impactOpp = 0;
                    for (const s of stalls) {
                        const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, W, D);
                        if (rectsOverlap(rOpp, sr)) impactOpp++;
                    }
                    if (impactOpp < oppImpact) { oppImpact = impactOpp; oppBest = { x: cOpp.x, y: cOpp.y, w: accessLen, h: accessW, angle: axisAngle }; }
                }
                if (oppBest) access.push(oppBest);
            }
            // Ensure a drive-width connector band at the same normal coordinate as access
            const connCenterT = (extT.min + extT.max) / 2;
            // project the access center onto the normal axis to get its N-coordinate
            const connCenterN = dot({ x: bestAccess.x, y: bestAccess.y }, n);
            const connCenter = { x: t.x * connCenterT + n.x * connCenterN, y: t.y * connCenterT + n.y * connCenterN };
            // Iteratively shrink length until the connector fits within the lot polygon
            let connLen = (extT.max - extT.min);
            let connRect = rectFromCenterDir(connCenter, t, n, connLen, WD_STREET);
            const minLen = Math.max(WD_STREET * 1.2, metersToUnits(8, upm));
            const minLenStreet = Math.max(WD_STREET * 1.2, metersToUnits(8, upm));
            let tries = 0;
            while (!polyContainsRect(connRect, boundary) && connLen > minLenStreet && tries < 12) {
                connLen *= 0.8; // shrink by 20%
                connRect = rectFromCenterDir(connCenter, t, n, connLen, WD_STREET);
                tries++;
            }
            if (polyContainsRect(connRect, boundary) || pointInPolygon(connCenter, boundary)) streets.push({ x: connCenter.x, y: connCenter.y, w: connLen, h: WD_STREET, angle: axisAngle, type: 'street' });
        }
        // ramp: choose ramp centers by evaluating candidates (aisle-ends, street centers, and center), snap to aisle ends
        const riseAccessM = Math.max(0, Number(p.groundEntryHeightMeters || 0));
        const accessSlope = Math.max(0.01, Number(p.accessRampMaxSlopePercent || 12) / 100);
        const computedAccessLenM = riseAccessM > 0 ? (riseAccessM / accessSlope) : 10;
        const rampLen = metersToUnits(computedAccessLenM, upm);
        const rampW = WD_STREET;
        const minRampLen = metersToUnits(8, upm);
        const rampCandidates = [];
        const midT = (extT.min + extT.max) / 2;
        // candidates at each aisle end (prefer these)
        for (const a of aisles) {
            const aCenterT = dot({ x: a.x, y: a.y }, t);
            const halfLen = a.w / 2;
            const endsT = [aCenterT - halfLen, aCenterT + halfLen];
            const aCenterN = dot({ x: a.x, y: a.y }, n);
            for (const eT of endsT) rampCandidates.push({ tPos: eT, nPos: aCenterN, type: 'aisleEnd' });
        }
        // candidates at street centers (if any)
        for (const s of streets) {
            const sT = dot({ x: s.x, y: s.y }, t);
            const sN = dot({ x: s.x, y: s.y }, n);
            rampCandidates.push({ tPos: sT, nPos: sN, type: 'streetCenter' });
        }
        // fallback candidates along edges and center
        rampCandidates.push({ tPos: extT.min + rampLen / 2 + metersToUnits(0.5, upm), nPos: (extN.min + extN.max) / 2, type: 'edge-min' });
        rampCandidates.push({ tPos: extT.max - rampLen / 2 - metersToUnits(0.5, upm), nPos: (extN.min + extN.max) / 2, type: 'edge-max' });
        rampCandidates.push({ tPos: midT, nPos: (extN.min + extN.max) / 2, type: 'center' });

        let bestRamp = null; let bestScore = Number.POSITIVE_INFINITY;
        for (const cand of rampCandidates) {
            const rc = { x: t.x * cand.tPos + n.x * cand.nPos, y: t.y * cand.tPos + n.y * cand.nPos };
            let rLen = rampLen; let rRect = rectFromCenterDir(rc, t, n, rLen, rampW);
            let triesR = 0;
            while (!polyContainsRect(rRect, boundary) && rLen > minRampLen && triesR < 10) {
                rLen *= 0.85; rRect = rectFromCenterDir(rc, t, n, rLen, rampW); triesR++;
            }
            // allow partial fit if center is inside
            const fits = polyContainsRect(rRect, boundary) || pointInPolygon(rc, boundary);
            if (!fits) continue;
            // approach band toward interior: determine sign based on candidate T relative to midT
            const interiorSign = (cand.tPos >= midT) ? -1 : +1;
            const approachLen = Math.max(metersToUnits(8, upm), WD_STREET * 1.0);
            const approachCenterT = cand.tPos + interiorSign * (rLen / 2 + approachLen / 2);
            const approachCenter = { x: t.x * approachCenterT + n.x * cand.nPos, y: t.y * approachCenterT + n.y * cand.nPos };
            const approachRect = rectFromCenterDir(approachCenter, t, n, approachLen, rampW);
            // compute stall impact (overlaps with rampRect or approachRect)
            let impact = 0;
            for (const s of stalls) {
                const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, W, D);
                if (rectsOverlap(sr, rRect) || rectsOverlap(sr, approachRect)) impact++;
            }
            // connectivity bonus/penalty: prefer aisleEnd or streetCenter candidates and those near an aisle
            let penalty = 0;
            if (cand.type !== 'aisleEnd' && cand.type !== 'streetCenter') penalty += 3; // mild penalty for generic edges
            // measure distance to nearest aisle center along T axis
            let nearestAisleDist = Number.POSITIVE_INFINITY;
            for (const a of aisles) {
                const aT = dot({ x: a.x, y: a.y }, t);
                nearestAisleDist = Math.min(nearestAisleDist, Math.abs(cand.tPos - aT));
            }
            if (nearestAisleDist > metersToUnits(6, upm)) penalty += 2; // if far from aisles add penalty
            const score = impact + penalty;
            if (score < bestScore) { bestScore = score; bestRamp = { center: rc, w: rLen, h: rampW, angle: axisAngle, approachRect, tPos: cand.tPos, nPos: cand.nPos }; }
        }
        const ramps = bestRamp ? [{ x: bestRamp.center.x, y: bestRamp.center.y, w: bestRamp.w, h: bestRamp.h, angle: bestRamp.angle }] : [];
        const rampApproachRects = bestRamp && polyContainsRect(bestRamp.approachRect, boundary) ? [bestRamp.approachRect] : (bestRamp ? [bestRamp.approachRect] : []);
        // If we placed a ramp, create a connector street from ramp t position to nearest street pivot or to nearest aisle end
        if (bestRamp) {
            const rampT = bestRamp.tPos; const rampN = bestRamp.nPos;
            // choose target as nearest street pivot else nearest aisle end; keep its T and N coords
            let targetT = null; let targetN = null; let bestDist = Number.POSITIVE_INFINITY;
            for (const sp of streetTPivots) { const d = Math.abs(sp.t - rampT); if (d < bestDist) { bestDist = d; targetT = sp.t; targetN = sp.n; } }
            if (targetT == null) {
                for (const a of aisles) { const aT = dot({ x: a.x, y: a.y }, t); const aN = dot({ x: a.x, y: a.y }, n); const d = Math.abs(aT - rampT); if (d < bestDist) { bestDist = d; targetT = aT; targetN = aN; } }
            }
            if (targetT == null) { targetT = midT; targetN = (extN.min + extN.max) / 2; }
            // connector center between ramp and target, average N so connector meets both
            // Build connector rectangle between ramp center and target anchor (world coords) so it spans both
            const anchor1 = { x: bestRamp.center.x, y: bestRamp.center.y };
            const anchor2 = { x: t.x * targetT + n.x * targetN, y: t.y * targetT + n.y * targetN };
            const dx = anchor2.x - anchor1.x; const dy = anchor2.y - anchor1.y;
            const dist = Math.hypot(dx, dy);
            if (dist > 1e-6) {
                const angleConn = Math.atan2(dy, dx);
                const t2 = { x: Math.cos(angleConn), y: Math.sin(angleConn) };
                const n2 = { x: -t2.y, y: t2.x };
                const centerWorld = { x: (anchor1.x + anchor2.x) / 2, y: (anchor1.y + anchor2.y) / 2 };
                // extend slightly beyond anchors to ensure clean butt joints
                let connLen = dist + Math.max(WD_STREET * 0.8, metersToUnits(2, upm));
                let connRect = rectFromCenterDir(centerWorld, t2, n2, connLen, WD_STREET);
                let triesConn = 0;
                while (!polyContainsRect(connRect, boundary) && triesConn < 12 && connLen > metersToUnits(6, upm)) {
                    connLen *= 0.85; connRect = rectFromCenterDir(centerWorld, t2, n2, connLen, WD_STREET); triesConn++;
                }
                // Accept connector if fully inside, center inside, OR either anchor endpoint is inside.
                const anchor1Inside = pointInPolygon(anchor1, boundary);
                const anchor2Inside = pointInPolygon(anchor2, boundary);
                const centerInside = pointInPolygon(centerWorld, boundary);
                const fullyInside = polyContainsRect(connRect, boundary);
                if (fullyInside || centerInside || anchor1Inside || anchor2Inside) {
                    streets.push({ x: centerWorld.x, y: centerWorld.y, w: connLen, h: WD_STREET, angle: angleConn, type: 'connector' });
                    try { console.info('[generator] connector created', { ramp: anchor1, target: anchor2, center: centerWorld, len: connLen, angle: angleConn, reason: fullyInside ? 'rect' : (centerInside ? 'center' : (anchor1Inside ? 'anchor1' : 'anchor2')) }); } catch (e) { }
                } else {
                    try { console.info('[generator] connector rejected (clipped)', { center: centerWorld, len: connLen, anchor1Inside, anchor2Inside, centerInside, fullyInside }); } catch (e) { }
                    if (p.forceConnectors) {
                        try { console.info('[generator] connector forced (dev)', { center: centerWorld, len: connLen }); } catch (e) { }
                        streets.push({ x: centerWorld.x, y: centerWorld.y, w: connLen, h: WD_STREET, angle: angleConn, type: 'connector' });
                    }
                }
            }
        }
        // Remove stalls that overlap access/aisles/streets to prevent visual/logic overlap
        // Prevent overlap with access, aisles, cross-connector streets, and ramps (but keep perimeter street adjacency)
        // Inflate clearing bands slightly to robustly keep stalls out of circulation
        const inflateRect = (rect, inflateT, inflateN) => {
            const rx0 = Math.min(...rect.map(p => p.x));
            const rx1 = Math.max(...rect.map(p => p.x));
            const ry0 = Math.min(...rect.map(p => p.y));
            const ry1 = Math.max(...rect.map(p => p.y));
            const cx = (rx0 + rx1) / 2;
            const cy = (ry0 + ry1) / 2;
            const w = (rx1 - rx0) + inflateT * 2;
            const h = (ry1 - ry0) + inflateN * 2;
            return rectFromCenterDir({ x: cx, y: cy }, { x: 1, y: 0 }, { x: 0, y: 1 }, w, h);
        };
        // Reduce clearing inflation to avoid over-filtering stalls in tight surface lots
        const inflateT = metersToUnits(0.25, upm);
        const inflateN = metersToUnits(0.25, upm);
        const bands = [
            ...aisles.map(a => inflateRect(rectFromCenterDir({ x: a.x, y: a.y }, t, n, a.w, a.h), inflateT, inflateN)),
            ...access.map(ac => inflateRect(rectFromCenterDir({ x: ac.x, y: ac.y }, t, n, ac.w, ac.h), inflateT, inflateN)),
            ...streets
                .filter(s => s.w <= WD_STREET * 1.05) // treat connector-like streets as clearing bands
                .map(s => inflateRect(rectFromCenterDir({ x: s.x, y: s.y }, t, n, s.w, s.h), inflateT, inflateN))
            ,
            ...ramps.map(rp => inflateRect(rectFromCenterDir({ x: rp.x, y: rp.y }, t, n, rp.w, rp.h), inflateT, inflateN))
            ,
            ...rampApproachRects.map(r => inflateRect(r, inflateT, inflateN))
        ];
        // Also avoid user obstacles (cores/mechanical rooms)
        const obstacles = Array.isArray(p.obstacles) ? p.obstacles : [];
        const obstacleRectsTN = obstacles.map(o => {
            // convert world-oriented rect to axis-aligned in t/n basis using its bbox in that basis
            const halfW = (o.w || 0) / 2, halfH = (o.h || 0) / 2; const ang = o.angle || 0;
            const cc = Math.cos(ang), ss = Math.sin(ang);
            const cornersWorld = [
                { x: o.x + (-halfW * cc - -halfH * ss), y: o.y + (-halfW * ss + -halfH * cc) },
                { x: o.x + (halfW * cc - -halfH * ss), y: o.y + (halfW * ss + -halfH * cc) },
                { x: o.x + (halfW * cc - halfH * ss), y: o.y + (halfW * ss + halfH * cc) },
                { x: o.x + (-halfW * cc - halfH * ss), y: o.y + (-halfW * ss + halfH * cc) },
            ];
            // project to t/n, then build rect from min/max extents
            const projTN = cornersWorld.map(pw => ({ tx: dot({ x: pw.x, y: pw.y }, t), ny: dot({ x: pw.x, y: pw.y }, n) }));
            const minT = Math.min(...projTN.map(p => p.tx)), maxT = Math.max(...projTN.map(p => p.tx));
            const minN = Math.min(...projTN.map(p => p.ny)), maxN = Math.max(...projTN.map(p => p.ny));
            const cT = (minT + maxT) / 2, cN = (minN + maxN) / 2;
            const cWorld = { x: t.x * cT + n.x * cN, y: t.y * cT + n.y * cN };
            return rectFromCenterDir(cWorld, t, n, (maxT - minT), (maxN - minN));
        });
        const filteredStalls = stallsDedupe.filter(s => {
            const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, W, D);
            for (const b of bands) { if (rectsOverlap(sr, b)) return false; }
            for (const ob of obstacleRectsTN) { if (rectsOverlap(sr, ob)) return false; }
            return true;
        });
        // Filter out columns that sit inside access or connector bands
        const clearingForColumns = [
            ...access.map(ac => inflateRect(rectFromCenterDir({ x: ac.x, y: ac.y }, t, n, ac.w, ac.h), inflateT, inflateN)),
            ...streets
                .filter(s => s.w <= WD_STREET * 1.05)
                .map(s => inflateRect(rectFromCenterDir({ x: s.x, y: s.y }, t, n, s.w, s.h), inflateT, inflateN)),
            ...ramps.map(rp => inflateRect(rectFromCenterDir({ x: rp.x, y: rp.y }, t, n, rp.w, rp.h), inflateT, inflateN)),
            ...rampApproachRects.map(r => inflateRect(r, inflateT, inflateN)),
            ...obstacleRectsTN.map(r => inflateRect(r, inflateT, inflateN))
        ];
        let filteredColumns = columns.filter(c => {
            // reject if column center lies within any clearing band
            for (const b of clearingForColumns) {
                const bx0 = Math.min(...b.map(p => p.x)), bx1 = Math.max(...b.map(p => p.x));
                const by0 = Math.min(...b.map(p => p.y)), by1 = Math.max(...b.map(p => p.y));
                if (c.x >= bx0 && c.x <= bx1 && c.y >= by0 && c.y <= by1) return false;
            }
            return true;
        });
        // Surface lots don't have structural columns; drop them entirely when in surface mode.
        const isSurface = !!(p?.parkingType === 'surface' || p?.type === 'surface' || p?.surfaceParking === true);
        if (isSurface) {
            try { console.info('[generator] surface mode: suppressing columns'); } catch (e) { }
            filteredColumns = [];
        }
        // conflicts: columns inside stalls (should be zero ideally)
        let conflicts = 0;
        for (const c of filteredColumns) {
            for (const s of filteredStalls) {
                if (Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, t)) <= (W / 2) && Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, n)) <= (D / 2)) { conflicts++; break; }
            }
        }
        // Unify circulation: promote aisles into streets with type 'aisle'
        const unifiedStreets = dedupeBands([
            ...streets,
            ...aisles.map(a => ({ x: a.x, y: a.y, w: a.w, h: a.h, angle: a.angle || axisAngle, type: 'aisle' }))
        ]);
        // Debug: report vertical vs horizontal street counts for Y-axis visibility validation
        try {
            const horizCount = unifiedStreets.filter(st => st && Math.abs((st.angle || 0) - axisAngle) < 0.1 && st.type === 'street').length;
            const vertCount = unifiedStreets.filter(st => st && Math.abs((st.angle || 0) - (axisAngle + Math.PI / 2)) < 0.1 && st.type === 'street').length;
            console.info('[generator] streets summary', { horizCount, vertCount, total: unifiedStreets.length });
        } catch (e) { }
        const connectorsCount = unifiedStreets.filter(st => st && st.type === 'connector').length;
        // Total street length to discourage excessive fragmentation
        const totalStreetLen = unifiedStreets.reduce((acc, st) => acc + (st ? st.w : 0), 0);
        const counts = { stalls: filteredStalls.length, aisles: unifiedStreets.filter(s => s.type === 'aisle').length, columns: filteredColumns.length, connectors: connectorsCount, conflicts, score: 0 };
        // Priority-aware score: adjust weights according to `p.designPriority`.
        const w = priorityWeights(p.designPriority);
        // Limit connector influence to avoid skewed designs
        const connectorsScore = Math.min(connectorsCount, 6) * ((w.connectors || 0) * 1.0);
        // Small penalty on excessive street length to keep designs tidy
        const streetLenPenalty = Math.max(0, totalStreetLen - metersToUnits(60, upm)) * 0.02;
        counts.score = (counts.stalls * (1.0 * w.stalls))
            - (conflicts * (200 * w.conflicts))
            + (counts.aisles * (0.3 * w.aisles))
            + (filteredColumns.length * (0.1 * w.columns))
            + connectorsScore
            - streetLenPenalty;
        // Dead-end penalty when requested (expected two end caps per aisle)
        const expectedEnds = aisles.length * 2;
        const deadEnds = Math.max(0, expectedEnds - endCapsCount);
        if (p.avoidDeadEnds) {
            counts.score -= deadEnds * 10;
        }
        // Mild symmetry/consistency preference: penalize high aisle angle variance
        const aisleAngles = aisles.map(a => a.angle || axisAngle);
        const meanAng = aisleAngles.length ? (aisleAngles.reduce((s, v) => s + v, 0) / aisleAngles.length) : axisAngle;
        const varAng = aisleAngles.length ? (aisleAngles.reduce((s, v) => s + Math.pow(v - meanAng, 2), 0) / aisleAngles.length) : 0;
        counts.score -= varAng * 0.5;
        // Aisles are represented within streets as type 'aisle'; return empty aisles for UI to rely on streets layer
        schemes.push({ points: boundary, closed: true, color: hsl(++colorIdx), stalls: filteredStalls, aisles: [], streets: unifiedStreets, access, columns: filteredColumns, ramps, counts });
    }
    // rank and limit
    // If a target stall count exists, prioritize closeness to the target, then fallback to score
    if (typeof p.targetStalls === 'number' && p.targetStalls > 0) {
        const tgt = p.targetStalls;
        schemes.sort((a, b) => {
            const da = Math.abs((a.counts?.stalls || 0) - tgt);
            const db = Math.abs((b.counts?.stalls || 0) - tgt);
            if (da !== db) return da - db;
            return (b.counts?.score || 0) - (a.counts?.score || 0);
        });
    } else {
        schemes.sort((a, b) => (b.counts?.score || 0) - (a.counts?.score || 0));
    }
    const topSchemes = schemes.slice(0, p.keepTop);
    try {
        topSchemes.forEach((s, i) => {
            try { console.info('[generator] structural result', i, 'stalls=', (s.stalls || []).length, 'aisles=', (s.aisles || []).length, 'streets=', (s.streets || []).length, 'counts=', s.counts); } catch (e) { }
        });
    } catch (e) { }
    return topSchemes;
}

function normalizeParams(params) {
    // First, apply code-based standards if a codeSet is provided
    const codeNormalized = params?.codeSet
        ? normalizeWithCodeStandards(params)
        : params;

    const defaults = {
        unitsPerMeter: 1,
        stallWidth: 2.6,
        stallDepth: 5.0,
        driveWidth: 6.0,
        aisleType: 'two-way',
        streetType: 'two-way',
        anglesDeg: [0, 12, -12, 24, -24],
        stallAngles: [90, 60],
        clipAcceptance: 0.25,
        columnSpacing: 7.5,
        columnClearance: 0.3,
        // Columns control
        enableColumns: true,
        keepTop: 3,
        // Street layout knobs
        minVerticalStreetCount: 2,
        // Ramp sizing defaults
        groundEntryHeightMeters: 0,
        levelHeightMeters: 3.5,
        accessRampMaxSlopePercent: 12,
        internalRampMaxSlopePercent: 12,
        // Dev-only flag: when true, create connectors even if clipped
        forceConnectors: false,
    };
    // Merge: defaults < code-based < user-provided
    const p = { ...defaults, ...(codeNormalized || {}) };
    // If any surface flag is present, disable columns by default.
    const isSurface = !!(p?.parkingType === 'surface' || p?.type === 'surface' || p?.surfaceParking === true);
    if (isSurface) p.enableColumns = false;
    // Enforce orthogonal bays when requested: keep aisles aligned to principal axis and stalls perpendicular.
    // Respect explicit user-provided angles if present; only override when typical defaults are in effect.
    if (p.enforceOrthogonalLayout) {
        const userProvidedAngles = Array.isArray(params?.anglesDeg) && params.anglesDeg.length > 0;
        const userProvidedStallAngles = Array.isArray(params?.stallAngles) && params.stallAngles.length > 0;
        if (!userProvidedAngles) p.anglesDeg = [0];
        if (!userProvidedStallAngles) p.stallAngles = [90];
    }
    return p;
}

// Map `designPriority` to weighting factors across simple metrics.
function priorityWeights(priority) {
    const p = (priority || '').toLowerCase();
    switch (p) {
        case 'capacity':
            return { stalls: 1.2, conflicts: 1.0, aisles: 0.9, columns: 0.8 };
        case 'comfort':
            return { stalls: 0.9, conflicts: 1.5, aisles: 1.1, columns: 0.8 };
        case 'flow':
            return { stalls: 1.0, conflicts: 1.2, aisles: 1.2, columns: 0.8, connectors: 1.3 };
        case 'accessibility':
            return { stalls: 0.95, conflicts: 1.6, aisles: 1.1, columns: 0.8 };
        case 'cost':
            return { stalls: 1.0, conflicts: 1.1, aisles: 0.9, columns: 0.6 };
        case 'future-ready':
        case 'future':
            return { stalls: 1.05, conflicts: 1.3, aisles: 1.0, columns: 0.9 };
        default:
            return { stalls: 1.0, conflicts: 1.0, aisles: 1.0, columns: 1.0 };
    }
}


// Axis-aligned rectangle overlap test (same basis as rectFromCenterDir t/n)
function rectsOverlap(a, b) {
    const ax0 = Math.min(...a.map(p => p.x)), ax1 = Math.max(...a.map(p => p.x));
    const ay0 = Math.min(...a.map(p => p.y)), ay1 = Math.max(...a.map(p => p.y));
    const bx0 = Math.min(...b.map(p => p.x)), bx1 = Math.max(...b.map(p => p.x));
    const by0 = Math.min(...b.map(p => p.y)), by1 = Math.max(...b.map(p => p.y));
    return ax0 <= bx1 && ax1 >= bx0 && ay0 <= by1 && ay1 >= by0;
}

/**
 * Generate a single parking layout using the new clean circulation generator.
 * This replaces the previous complex, fragmented street generation logic.
 */
function layoutOnce(boundary, p, axisAngle, stallAngle, phaseFrac = 0) {
    const upm = p.unitsPerMeter;
    const W = metersToUnits(p.stallWidth, upm);
    const D = metersToUnits(p.stallDepth, upm);
    const driveWidthM = resolveAisleWidthMeters(p);
    const WD_AISLE = metersToUnits(driveWidthM, upm);
    const WD_STREET = metersToUnits(resolveStreetWidthMeters(p), upm);

    // Direction vectors
    const t = { x: Math.cos(axisAngle), y: Math.sin(axisAngle) };
    const n = { x: -t.y, y: t.x };
    const extN = projectionsExtent(boundary, n);
    const extT = projectionsExtent(boundary, t);

    // === USE NEW CLEAN CIRCULATION GENERATOR ===
    const circulationNetwork = generateCirculationNetwork({
        boundary,
        codeSet: p.codeSet || 'GENERIC',
        unitsPerMeter: upm,
        stallWidth: p.stallWidth,
        stallDepth: p.stallDepth,
        axisAngle,
        aisleType: p.aisleType || 'two-way',
        layoutPattern: p.circulationMode || 'loop'
    });

    // Merge all circulation into unified streets array
    const streets = mergeCirculationToStreets(circulationNetwork);

    // Generate stalls along the aisles
    const rawStalls = generateStallsForAisles({
        boundary,
        aisles: streets.filter(s => s.type === 'aisle'),
        t, n,
        stallWidth: p.stallWidth,
        stallDepth: p.stallDepth,
        driveWidth: driveWidthM,
        unitsPerMeter: upm
    });

    // Access zones from the circulation network
    const access = circulationNetwork.access || [];

    // === RAMPS (for structured parking) ===
    const ramps = [];
    const riseAccessM = Math.max(0, Number(p.groundEntryHeightMeters || 0));
    if (riseAccessM > 0) {
        const accessSlope = Math.max(0.01, Number(p.accessRampMaxSlopePercent || 12) / 100);
        const rampLenMeters = Math.max(10, riseAccessM / accessSlope);
        const rampLen = metersToUnits(rampLenMeters, upm);
        const rampW = WD_STREET;
        const rampN = (extN.min + extN.max) / 2;
        const rampCenter = { 
            x: t.x * (extT.min + rampLen / 2 + metersToUnits(0.5, upm)) + n.x * rampN, 
            y: t.y * (extT.min + rampLen / 2 + metersToUnits(0.5, upm)) + n.y * rampN 
        };
        const rampRect = rectFromCenterDir(rampCenter, t, n, rampLen, rampW);
        if (polyContainsRect(rampRect, boundary)) {
            ramps.push({ x: rampCenter.x, y: rampCenter.y, w: rampLen, h: rampW, angle: axisAngle, type: 'ramp' });
        }
    }

    // === FILTER STALLS OVERLAPPING CIRCULATION ===
    const circulationRects = streets
        .filter(st => st && st.type !== 'street') // Don't filter stalls near perimeter streets
        .map(st => {
            const isHoriz = Math.abs((st.angle || 0) - axisAngle) < 0.1;
            return rectFromCenterDir({ x: st.x, y: st.y }, t, n, isHoriz ? st.w : st.h, isHoriz ? st.h : st.w);
        });
    const rampRects = ramps.map(rp => rectFromCenterDir({ x: rp.x, y: rp.y }, t, n, rp.w, rp.h));
    const accessRects = access.map(ac => rectFromCenterDir({ x: ac.x, y: ac.y }, t, n, ac.w, ac.h));
    const blockerRects = [...circulationRects, ...rampRects, ...accessRects];

    const filteredStalls = rawStalls.filter(s => {
        const sr = rectFromCenterDir({ x: s.x, y: s.y }, t, n, (s.hw || 0) * 2, (s.hd || 0) * 2);
        for (const br of blockerRects) {
            if (rectsOverlap(sr, br)) return false;
        }
        return true;
    });

    // === COLUMNS (for structured parking only) ===
    const cols = [];
    const isSurfaceLot = !!(p?.parkingType === 'surface' || p?.type === 'surface' || p?.surfaceParking === true);
    
    if (!isSurfaceLot && p.enableColumns !== false) {
        const clearance = metersToUnits(p.columnClearance || 0.3, upm);
        const C = metersToUnits(p.columnSpacing || 7.5, upm);
        const startNc = Math.ceil(extN.min / C) * C;
        const startTc = Math.ceil(extT.min / C) * C;
        
        for (let kn = startNc; kn <= extN.max; kn += C) {
            for (let kt = startTc; kt <= extT.max; kt += C) {
                const c = { x: t.x * kt + n.x * kn, y: t.y * kt + n.y * kn };
                if (!pointInPolygon(c, boundary)) continue;
                
                // Avoid placing columns inside streets or stalls
                let nearStreet = false;
                for (const st of streets) {
                    const stN = dot({ x: st.x, y: st.y }, n);
                    const stT = dot({ x: st.x, y: st.y }, t);
                    const isHoriz = Math.abs((st.angle || 0) - axisAngle) < 0.1;
                    if (isHoriz) {
                        if (Math.abs(kn - stN) <= ((st.h || WD_AISLE) / 2 + clearance)) { nearStreet = true; break; }
                    } else {
                        if (Math.abs(kt - stT) <= ((st.w || WD_STREET) / 2 + clearance)) { nearStreet = true; break; }
                    }
                }
                if (nearStreet) continue;
                
                let inStall = false;
                for (const s of filteredStalls) {
                    if (Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, t)) <= (W / 2 + clearance) &&
                        Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, n)) <= (D / 2 + clearance)) { 
                        inStall = true; break; 
                    }
                }
                if (!inStall) cols.push(c);
            }
        }
    }

    // === COUNTS & SCORING ===
    let conflicts = 0;
    for (const c of cols) {
        for (const s of filteredStalls) {
            if (Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, t)) <= (W / 2) &&
                Math.abs(dot({ x: c.x - s.x, y: c.y - s.y }, n)) <= (D / 2)) { 
                conflicts++; break; 
            }
        }
    }

    const aisleCount = streets.filter(s => s.type === 'aisle').length;
    const connectorCount = streets.filter(s => s.type === 'connector').length;
    const perimeterCount = streets.filter(s => s.type && s.type.startsWith('perimeter')).length;

    const counts = {
        stalls: filteredStalls.length,
        aisles: aisleCount,
        streets: perimeterCount,
        columns: cols.length,
        connectors: connectorCount,
        conflicts,
        score: 0
    };

    const w = priorityWeights(p.designPriority);
    counts.score = (counts.stalls * (1.0 * w.stalls))
        - (conflicts * (50 * w.conflicts))
        + (aisleCount * (0.2 * w.aisles))
        + (cols.length * (0.05 * w.columns))
        + (connectorCount * (0.12 * (w.connectors || 1)));

    return {
        points: boundary,
        closed: true,
        color: '#475569',
        stalls: filteredStalls,
        aisles: [], // Aisles are now in streets array with type 'aisle'
        streets,
        access,
        columns: cols,
        ramps,
        counts
    };
}

// Re-export parking standards functions for UI access
export { getAvailableParkingCodes, getParkingStandards, resolveCirculationParams, resolveStallParams, getRecommendedAngles } from './parkingStandards';
