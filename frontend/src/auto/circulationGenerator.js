/**
 * Circulation Generator for Surface Parking Layouts
 * 
 * Generates code-compliant circulation networks including:
 * - Perimeter drive lanes (two-way loop around the lot)
 * - Internal drive aisles (between stall rows)
 * - Cross-connectors (vertical links between horizontal aisles)
 * - Entry/exit access points
 * 
 * All dimensions are derived from the building code standards in parking_standards.json
 */

import { rectFromCenterDir, polyContainsRect, pointInPolygon, projectionsExtent, dot } from './geometry';
import { resolveCirculationParams } from './parkingStandards';

/**
 * Generate a complete circulation network for surface parking
 * 
 * @param {Object} options
 * @param {Array<{x,y}>} options.boundary - Lot boundary polygon points
 * @param {string} options.codeSet - Building code (e.g., 'IBC_2024')
 * @param {number} options.unitsPerMeter - Conversion factor
 * @param {number} options.stallWidth - Stall width in meters
 * @param {number} options.stallDepth - Stall depth in meters
 * @param {number} options.axisAngle - Primary axis angle in radians
 * @param {string} options.aisleType - 'one-way' | 'two-way'
 * @param {string} options.layoutPattern - 'loop' | 'grid' | 'linear'
 * @returns {Object} Circulation network with streets, aisles, connectors
 */
export function generateCirculationNetwork(options) {
    const {
        boundary,
        codeSet = 'GENERIC',
        unitsPerMeter = 1,
        stallWidth = 2.5,
        stallDepth = 5.0,
        axisAngle = 0,
        aisleType = 'two-way',
        layoutPattern = 'loop'
    } = options;

    if (!boundary || boundary.length < 3) {
        return { streets: [], aisles: [], connectors: [], access: [] };
    }

    // Get code-compliant dimensions
    const circ = resolveCirculationParams(codeSet, aisleType);
    const driveWidth = circ.driveWidth * unitsPerMeter;
    const fireLaneWidth = circ.fireLaneWidth * unitsPerMeter;
    
    // Stall dimensions in drawing units
    const W = stallWidth * unitsPerMeter;
    const D = stallDepth * unitsPerMeter;
    
    // Double-loaded aisle module pitch: aisle + 2 stall depths
    const modulePitch = driveWidth + 2 * D;

    // Direction vectors
    const t = { x: Math.cos(axisAngle), y: Math.sin(axisAngle) };  // tangent (along rows)
    const n = { x: -t.y, y: t.x };                                  // normal (across rows)

    // Boundary extents in t/n coordinate system
    const extT = projectionsExtent(boundary, t);
    const extN = projectionsExtent(boundary, n);

    // Inset from boundary edges for perimeter drive
    const perimeterInset = Math.min(driveWidth * 0.6, Math.max(1, (extT.max - extT.min) * 0.02));

    const result = {
        streets: [],      // Perimeter and major circulation
        aisles: [],       // Internal drive aisles
        connectors: [],   // T-junction connectors
        access: []        // Entry/exit zones
    };

    // === STEP 1: PERIMETER LOOP ===
    // Creates a rectangular perimeter drive around the lot
    const perimeterStreets = generatePerimeterLoop({
        boundary, t, n, extT, extN,
        driveWidth, perimeterInset, axisAngle
    });
    result.streets.push(...perimeterStreets);

    // Calculate the interior zone (inside perimeter streets)
    const interiorT = {
        min: extT.min + driveWidth + perimeterInset,
        max: extT.max - driveWidth - perimeterInset
    };
    const interiorN = {
        min: extN.min + driveWidth + perimeterInset,
        max: extN.max - driveWidth - perimeterInset
    };

    // === STEP 2: INTERNAL AISLES ===
    // Horizontal aisles running parallel to the main axis
    const aisles = generateInternalAisles({
        boundary, t, n,
        interiorT, interiorN,
        modulePitch, driveWidth, W, D,
        axisAngle, unitsPerMeter
    });
    result.aisles.push(...aisles);

    // === STEP 3: CROSS-CONNECTORS (VERTICAL) ===
    // Vertical connectors linking horizontal aisles for grid circulation
    if (layoutPattern === 'grid' || layoutPattern === 'loop') {
        const connectors = generateCrossConnectors({
            boundary, t, n,
            interiorT, interiorN,
            aisles,
            driveWidth, axisAngle, unitsPerMeter
        });
        result.connectors.push(...connectors);
    }

    // === STEP 4: ACCESS POINTS ===
    // Entry and exit zones at perimeter
    const accessPoints = generateAccessPoints({
        boundary, t, n,
        extT, extN,
        driveWidth, perimeterInset, axisAngle
    });
    result.access.push(...accessPoints);

    return result;
}

/**
 * Generate perimeter drive loop (4 sides)
 */
function generatePerimeterLoop({ boundary, t, n, extT, extN, driveWidth, perimeterInset, axisAngle }) {
    const streets = [];
    
    // Calculate perimeter street positions
    const leftT = extT.min + driveWidth / 2 + perimeterInset;
    const rightT = extT.max - driveWidth / 2 - perimeterInset;
    const bottomN = extN.min + driveWidth / 2 + perimeterInset;
    const topN = extN.max - driveWidth / 2 - perimeterInset;

    // Dimensions
    const horizontalLen = Math.max(0, (rightT - leftT));
    const verticalLen = Math.max(0, (topN - bottomN));

    if (horizontalLen <= 0 || verticalLen <= 0) return streets;

    // Left vertical street
    const leftCenter = { x: t.x * leftT + n.x * ((bottomN + topN) / 2), y: t.y * leftT + n.y * ((bottomN + topN) / 2) };
    const leftStreet = tryFitStreet(boundary, leftCenter, t, n, driveWidth, verticalLen, axisAngle + Math.PI / 2, 'perimeter-left');
    if (leftStreet) streets.push(leftStreet);

    // Right vertical street
    const rightCenter = { x: t.x * rightT + n.x * ((bottomN + topN) / 2), y: t.y * rightT + n.y * ((bottomN + topN) / 2) };
    const rightStreet = tryFitStreet(boundary, rightCenter, t, n, driveWidth, verticalLen, axisAngle + Math.PI / 2, 'perimeter-right');
    if (rightStreet) streets.push(rightStreet);

    // Bottom horizontal street
    const bottomCenter = { x: t.x * ((leftT + rightT) / 2) + n.x * bottomN, y: t.y * ((leftT + rightT) / 2) + n.y * bottomN };
    const bottomStreet = tryFitStreet(boundary, bottomCenter, t, n, horizontalLen, driveWidth, axisAngle, 'perimeter-bottom');
    if (bottomStreet) streets.push(bottomStreet);

    // Top horizontal street
    const topCenter = { x: t.x * ((leftT + rightT) / 2) + n.x * topN, y: t.y * ((leftT + rightT) / 2) + n.y * topN };
    const topStreet = tryFitStreet(boundary, topCenter, t, n, horizontalLen, driveWidth, axisAngle, 'perimeter-top');
    if (topStreet) streets.push(topStreet);

    return streets;
}

/**
 * Generate internal aisles between stall rows
 */
function generateInternalAisles({ boundary, t, n, interiorT, interiorN, modulePitch, driveWidth, W, D, axisAngle, unitsPerMeter }) {
    const aisles = [];
    
    // Calculate aisle positions: evenly spaced across the interior
    const interiorHeight = interiorN.max - interiorN.min;
    const numModules = Math.floor(interiorHeight / modulePitch);
    
    if (numModules < 1) return aisles;

    // Start from bottom and place aisles at center of each module
    const firstAisleN = interiorN.min + modulePitch / 2;
    const aisleLength = Math.max(0, interiorT.max - interiorT.min);

    if (aisleLength <= driveWidth) return aisles;

    for (let i = 0; i < numModules; i++) {
        const aisleN = firstAisleN + i * modulePitch;
        
        // Skip if outside interior bounds
        if (aisleN < interiorN.min || aisleN > interiorN.max) continue;

        const aisleCenterT = (interiorT.min + interiorT.max) / 2;
        const center = { x: t.x * aisleCenterT + n.x * aisleN, y: t.y * aisleCenterT + n.y * aisleN };

        const aisle = tryFitStreet(boundary, center, t, n, aisleLength, driveWidth, axisAngle, 'aisle');
        if (aisle) {
            aisle.moduleIndex = i;
            aisle.coordN = aisleN;
            aisles.push(aisle);
        }
    }

    return aisles;
}

/**
 * Generate cross-connectors (vertical streets linking horizontal aisles)
 */
function generateCrossConnectors({ boundary, t, n, interiorT, interiorN, aisles, driveWidth, axisAngle, unitsPerMeter }) {
    const connectors = [];
    
    if (aisles.length < 2) return connectors;

    // Calculate connector positions: place at 1/3 and 2/3 of interior width
    const interiorWidth = interiorT.max - interiorT.min;
    const connectorPositions = [
        interiorT.min + interiorWidth * 0.33,
        interiorT.min + interiorWidth * 0.67
    ];

    // Find the N-extent of all aisles
    const aisleNs = aisles.map(a => a.coordN || dot({ x: a.x, y: a.y }, n));
    const minAisleN = Math.min(...aisleNs);
    const maxAisleN = Math.max(...aisleNs);

    // Connector should span from first to last aisle
    const connectorLen = Math.max(0, maxAisleN - minAisleN + driveWidth);
    const connectorCenterN = (minAisleN + maxAisleN) / 2;

    for (const connT of connectorPositions) {
        const center = { x: t.x * connT + n.x * connectorCenterN, y: t.y * connT + n.y * connectorCenterN };
        
        const connector = tryFitStreet(boundary, center, t, n, driveWidth, connectorLen, axisAngle + Math.PI / 2, 'connector');
        if (connector) connectors.push(connector);
    }

    return connectors;
}

/**
 * Generate entry/exit access points
 */
function generateAccessPoints({ boundary, t, n, extT, extN, driveWidth, perimeterInset, axisAngle }) {
    const access = [];

    // Place one access point on the bottom edge
    const accessLen = Math.min(driveWidth * 3, (extT.max - extT.min) * 0.25);
    const accessN = extN.min + driveWidth / 2 + perimeterInset;
    const accessT = (extT.min + extT.max) / 2;
    
    const center = { x: t.x * accessT + n.x * accessN, y: t.y * accessT + n.y * accessN };
    const accessRect = tryFitStreet(boundary, center, t, n, accessLen, driveWidth * 0.8, axisAngle, 'access');
    if (accessRect) access.push(accessRect);

    return access;
}

/**
 * Helper: Try to fit a street rectangle within the boundary
 * @returns {Object|null} Street object or null if it doesn't fit
 */
function tryFitStreet(boundary, center, t, n, length, width, angle, type) {
    let fitLen = length;
    let fitWidth = width;
    let rect = rectFromCenterDir(center, t, n, fitLen, fitWidth);
    let tries = 0;

    // Iteratively shrink until it fits
    while (!polyContainsRect(rect, boundary) && tries < 10) {
        fitLen *= 0.9;
        rect = rectFromCenterDir(center, t, n, fitLen, fitWidth);
        tries++;
    }

    // Accept if fully inside or at least center is inside
    if (polyContainsRect(rect, boundary) || pointInPolygon(center, boundary)) {
        return {
            x: center.x,
            y: center.y,
            w: fitLen,
            h: fitWidth,
            angle: angle,
            type: type
        };
    }

    return null;
}

/**
 * Merge circulation into a unified streets array
 * Combines streets, aisles, and connectors with proper types
 */
export function mergeCirculationToStreets(circulationNetwork) {
    const { streets = [], aisles = [], connectors = [], access = [] } = circulationNetwork;
    
    const merged = [];
    
    // Add streets with 'street' type (already have types from generation)
    for (const s of streets) {
        merged.push({ ...s, type: s.type || 'street' });
    }
    
    // Add aisles with 'aisle' type
    for (const a of aisles) {
        merged.push({ ...a, type: 'aisle' });
    }
    
    // Add connectors with 'connector' type
    for (const c of connectors) {
        merged.push({ ...c, type: 'connector' });
    }
    
    // Add access with 'access' type
    for (const ac of access) {
        merged.push({ ...ac, type: 'access' });
    }

    return merged;
}

/**
 * Generate stalls along aisles
 */
export function generateStallsForAisles(options) {
    const {
        boundary,
        aisles,
        t, n,
        stallWidth,
        stallDepth,
        driveWidth,
        unitsPerMeter = 1
    } = options;

    const stalls = [];
    const W = stallWidth * unitsPerMeter;
    const D = stallDepth * unitsPerMeter;
    const aisleW = driveWidth * unitsPerMeter;

    for (const aisle of aisles) {
        if (aisle.type !== 'aisle') continue;

        const aisleCenter = { x: aisle.x, y: aisle.y };
        const aisleLen = aisle.w || 0;
        const aisleN = dot(aisleCenter, n);
        const aisleT = dot(aisleCenter, t);

        // Stall rows on both sides of aisle
        const rowOffset = (aisleW / 2) + (D / 2);
        const rowNs = [aisleN - rowOffset, aisleN + rowOffset];

        // Stall placement along aisle
        const halfLen = aisleLen / 2;
        const startT = aisleT - halfLen + W / 2;
        const endT = aisleT + halfLen - W / 2;

        for (const rowN of rowNs) {
            for (let kt = startT; kt <= endT; kt += W) {
                const c = { x: t.x * kt + n.x * rowN, y: t.y * kt + n.y * rowN };
                const rect = rectFromCenterDir(c, t, n, W, D);
                
                if (polyContainsRect(rect, boundary)) {
                    stalls.push({ x: c.x, y: c.y, hw: W / 2, hd: D / 2 });
                }
            }
        }
    }

    return stalls;
}
