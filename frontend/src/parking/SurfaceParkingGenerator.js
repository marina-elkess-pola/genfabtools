/**
 * SurfaceParkingGenerator - TestFit-style surface parking layout algorithm
 * 
 * Generates optimized parking layouts using:
 * - Parallel line-sweep fill for parking modules
 * - Circulation spine connecting entries
 * - Double-loaded and single-loaded aisle configurations
 * - ADA/EV/Compact stall placement
 * 
 * All units in feet (converted internally as needed)
 */

// ============================================================================
// GEOMETRY UTILITIES
// ============================================================================

/**
 * Calculate polygon area using shoelace formula
 */
function polygonArea(vertices) {
    let area = 0;
    const n = vertices.length;
    for (let i = 0; i < n; i++) {
        const j = (i + 1) % n;
        area += vertices[i].x * vertices[j].y;
        area -= vertices[j].x * vertices[i].y;
    }
    return Math.abs(area / 2);
}

/**
 * Calculate polygon centroid
 */
function polygonCentroid(vertices) {
    let cx = 0, cy = 0;
    const n = vertices.length;
    for (let i = 0; i < n; i++) {
        cx += vertices[i].x;
        cy += vertices[i].y;
    }
    return { x: cx / n, y: cy / n };
}

/**
 * Get bounding box of polygon
 */
function getBoundingBox(vertices) {
    const xs = vertices.map(v => v.x);
    const ys = vertices.map(v => v.y);
    return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys),
        width: Math.max(...xs) - Math.min(...xs),
        height: Math.max(...ys) - Math.min(...ys)
    };
}

/**
 * Offset polygon inward (simple approach for convex/near-convex polygons)
 */
function offsetPolygonInward(vertices, distance) {
    const centroid = polygonCentroid(vertices);
    return vertices.map(v => {
        const dx = v.x - centroid.x;
        const dy = v.y - centroid.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) return { ...v };
        const scale = Math.max(0, (len - distance) / len);
        return {
            x: centroid.x + dx * scale,
            y: centroid.y + dy * scale
        };
    });
}

/**
 * Check if point is inside polygon (ray casting)
 */
function pointInPolygon(point, polygon) {
    let inside = false;
    const n = polygon.length;
    for (let i = 0, j = n - 1; i < n; j = i++) {
        const xi = polygon[i].x, yi = polygon[i].y;
        const xj = polygon[j].x, yj = polygon[j].y;
        if (((yi > point.y) !== (yj > point.y)) &&
            (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi)) {
            inside = !inside;
        }
    }
    return inside;
}

/**
 * Check if rectangle is fully inside polygon
 */
function rectangleInPolygon(rect, polygon) {
    // rect = { x, y, width, height, angle }
    const corners = getRectangleCorners(rect);
    return corners.every(c => pointInPolygon(c, polygon));
}

/**
 * Get corners of a rotated rectangle
 */
function getRectangleCorners(rect) {
    const { x, y, width, height, angle = 0 } = rect;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const hw = width / 2;
    const hh = height / 2;

    const corners = [
        { dx: -hw, dy: -hh },
        { dx: hw, dy: -hh },
        { dx: hw, dy: hh },
        { dx: -hw, dy: hh }
    ];

    return corners.map(c => ({
        x: x + c.dx * cos - c.dy * sin,
        y: y + c.dx * sin + c.dy * cos
    }));
}

/**
 * Calculate principal axis of polygon using PCA-like approach
 */
function getPrincipalAxis(vertices) {
    const bbox = getBoundingBox(vertices);
    // Simple heuristic: use the longer axis of bounding box
    if (bbox.width >= bbox.height) {
        return 0; // Horizontal
    } else {
        return Math.PI / 2; // Vertical
    }
}

/**
 * Clip line segment to polygon bounds (simplified)
 */
function clipLineToPolygon(p1, p2, polygon) {
    const bbox = getBoundingBox(polygon);
    // Simple clip to bounding box first
    // For production, use proper polygon clipping

    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    if (len === 0) return null;

    // Find entry and exit points along the line
    let tMin = 0, tMax = 1;

    // Check if endpoints are inside
    const p1Inside = pointInPolygon(p1, polygon);
    const p2Inside = pointInPolygon(p2, polygon);

    if (p1Inside && p2Inside) {
        return { start: p1, end: p2 };
    }

    if (!p1Inside && !p2Inside) {
        // Both outside - check if line crosses polygon
        // Simplified: return null for now
        return null;
    }

    // One inside, one outside - find intersection
    // Simplified binary search
    const steps = 20;
    let inside = p1Inside ? p1 : p2;
    let outside = p1Inside ? p2 : p1;

    for (let i = 0; i < steps; i++) {
        const mid = {
            x: (inside.x + outside.x) / 2,
            y: (inside.y + outside.y) / 2
        };
        if (pointInPolygon(mid, polygon)) {
            inside = mid;
        } else {
            outside = mid;
        }
    }

    if (p1Inside) {
        return { start: p1, end: inside };
    } else {
        return { start: inside, end: p2 };
    }
}

// ============================================================================
// PARKING MODULE GENERATION
// ============================================================================

/**
 * Calculate module depth based on parking angle
 */
function calculateModuleDepth(config) {
    const { stallDepth, aisleWidth, doubleLoaded = true } = config;
    if (doubleLoaded) {
        return stallDepth * 2 + aisleWidth; // Stalls on both sides
    } else {
        return stallDepth + aisleWidth; // Stalls on one side only
    }
}

/**
 * Calculate stall pitch along aisle based on angle
 */
function calculateStallPitch(stallWidth, angleDeg) {
    if (angleDeg === 90) {
        return stallWidth;
    }
    const angleRad = (angleDeg * Math.PI) / 180;
    return stallWidth / Math.sin(angleRad);
}

/**
 * Generate stalls along an aisle segment
 */
function generateStallsAlongAisle(aisleStart, aisleEnd, config, side = 'both') {
    const {
        stallWidth,
        stallDepth,
        parkingAngle = 90,
        endcapClearance = 2,
        aisleWidth
    } = config;

    const stalls = [];

    // Aisle direction
    const dx = aisleEnd.x - aisleStart.x;
    const dy = aisleEnd.y - aisleStart.y;
    const aisleLength = Math.sqrt(dx * dx + dy * dy);
    if (aisleLength < endcapClearance * 2) return stalls;

    const aisleAngle = Math.atan2(dy, dx);
    const unitX = dx / aisleLength;
    const unitY = dy / aisleLength;

    // Perpendicular direction (for stall offset)
    const perpX = -unitY;
    const perpY = unitX;

    // Stall pitch along aisle
    const pitch = calculateStallPitch(stallWidth, parkingAngle);

    // Usable length
    const usableLength = aisleLength - endcapClearance * 2;
    const numStalls = Math.floor(usableLength / pitch);

    // Stall angle (relative to aisle)
    const stallAngleRad = (parkingAngle * Math.PI) / 180;

    // Generate stalls on requested sides
    const sides = side === 'both' ? ['left', 'right'] : [side];

    for (const s of sides) {
        const sideSign = s === 'left' ? 1 : -1;

        for (let i = 0; i < numStalls; i++) {
            // Position along aisle
            const t = endcapClearance + (i + 0.5) * pitch;
            const baseX = aisleStart.x + unitX * t;
            const baseY = aisleStart.y + unitY * t;

            // Offset perpendicular to aisle (center of stall)
            const offsetDist = aisleWidth / 2 + stallDepth / 2;
            const stallCenterX = baseX + perpX * offsetDist * sideSign;
            const stallCenterY = baseY + perpY * offsetDist * sideSign;

            // Stall rotation
            let stallRotation = aisleAngle + Math.PI / 2; // Perpendicular to aisle
            if (parkingAngle !== 90) {
                stallRotation = aisleAngle + stallAngleRad * sideSign;
            }

            stalls.push({
                x: stallCenterX,
                y: stallCenterY,
                width: stallWidth,
                height: stallDepth,
                angle: stallRotation,
                type: 'standard',
                aisleIndex: null // Will be set later
            });
        }
    }

    return stalls;
}

// ============================================================================
// MAIN LAYOUT GENERATOR
// ============================================================================

/**
 * Generate a complete surface parking layout
 * 
 * @param {Object} options
 * @param {Array} options.boundary - Site boundary polygon [{x, y}, ...]
 * @param {Array} options.obstacles - Building footprints to avoid
 * @param {Object} options.setbacks - { front, rear, side } in feet
 * @param {Object} options.config - Parking configuration
 * @returns {Object} Layout with stalls, aisles, circulation
 */
export function generateSurfaceParkingLayout(options) {
    const {
        boundary,
        obstacles = [],
        setbacks = { front: 10, rear: 10, side: 10 },
        config = {}
    } = options;

    // Default configuration (US standard dimensions in feet)
    const parkingConfig = {
        stallWidth: config.stallWidth || 9,           // 9 ft standard
        stallDepth: config.stallDepth || 18,          // 18 ft standard
        compactWidth: config.compactWidth || 8,       // 8 ft compact
        compactDepth: config.compactDepth || 16,      // 16 ft compact
        aisleWidth: config.aisleWidth || 24,          // 24 ft two-way
        parkingAngle: config.parkingAngle || 90,      // 90° perpendicular
        perimeterBuffer: config.perimeterBuffer || 3, // 3 ft from edge
        endcapClearance: config.endcapClearance || 2, // 2 ft at ends

        // Stall mix percentages
        standardPct: config.standardPct ?? 85,
        compactPct: config.compactPct ?? 10,
        adaPct: config.adaPct ?? 3,
        evPct: config.evPct ?? 2,

        // Feature flags
        hasLandscaping: config.hasLandscaping !== false,
        landscapeInterval: config.landscapeInterval || 15,
        hasEndIslands: config.endIslands !== false,
        hasFireLane: config.fireLane !== false,
        hasEntryExit: config.hasEntryExit !== false,

        doubleLoaded: true, // Double-loaded aisles
        ...config
    };

    // Step 1: Calculate allowed area (inside setbacks)
    const bbox = getBoundingBox(boundary);
    const buildableArea = {
        minX: bbox.minX + setbacks.side,
        maxX: bbox.maxX - setbacks.side,
        minY: bbox.minY + setbacks.front,
        maxY: bbox.maxY - setbacks.rear,
        width: bbox.width - setbacks.side * 2,
        height: bbox.height - setbacks.front - setbacks.rear
    };

    // Step 2: Define parking field (simplified: use rectangular buildable area)
    const field = [
        { x: buildableArea.minX, y: buildableArea.minY },
        { x: buildableArea.maxX, y: buildableArea.minY },
        { x: buildableArea.maxX, y: buildableArea.maxY },
        { x: buildableArea.minX, y: buildableArea.maxY }
    ];

    // Step 3: Determine primary parking orientation
    const primaryAxis = getPrincipalAxis(boundary);
    const isHorizontalAisles = buildableArea.width >= buildableArea.height;

    // Step 4: Calculate circulation loop dimensions
    const loopInset = parkingConfig.perimeterBuffer;
    const loopWidth = parkingConfig.aisleWidth;

    // Parking bay area (inside circulation loop)
    const bayArea = {
        minX: buildableArea.minX + loopInset + loopWidth,
        maxX: buildableArea.maxX - loopInset - loopWidth,
        minY: buildableArea.minY + loopInset + loopWidth,
        maxY: buildableArea.maxY - loopInset - loopWidth,
        width: buildableArea.width - (loopInset + loopWidth) * 2,
        height: buildableArea.height - (loopInset + loopWidth) * 2
    };

    // Step 5: Generate parking modules using line-sweep
    const moduleDepth = calculateModuleDepth(parkingConfig);
    const stalls = [];
    const aisles = [];

    // Determine aisle direction and count
    const aisleDirection = isHorizontalAisles ? 'horizontal' : 'vertical';
    let numModules, aisleSpacing;

    if (aisleDirection === 'horizontal') {
        // Aisles run left-right, modules stack vertically
        numModules = Math.floor(bayArea.height / moduleDepth);
        aisleSpacing = moduleDepth;
    } else {
        // Aisles run top-bottom, modules stack horizontally
        numModules = Math.floor(bayArea.width / moduleDepth);
        aisleSpacing = moduleDepth;
    }

    // Step 6: Generate aisles and stalls for each module
    for (let m = 0; m < numModules; m++) {
        let aisleStart, aisleEnd, aisleY, aisleX;

        if (aisleDirection === 'horizontal') {
            // Horizontal aisle at vertical position
            aisleY = bayArea.minY + m * moduleDepth + parkingConfig.stallDepth + parkingConfig.aisleWidth / 2;
            aisleStart = { x: bayArea.minX, y: aisleY };
            aisleEnd = { x: bayArea.maxX, y: aisleY };
        } else {
            // Vertical aisle at horizontal position
            aisleX = bayArea.minX + m * moduleDepth + parkingConfig.stallDepth + parkingConfig.aisleWidth / 2;
            aisleStart = { x: aisleX, y: bayArea.minY };
            aisleEnd = { x: aisleX, y: bayArea.maxY };
        }

        // Add aisle
        aisles.push({
            start: aisleStart,
            end: aisleEnd,
            width: parkingConfig.aisleWidth,
            index: m,
            direction: aisleDirection
        });

        // Generate stalls along this aisle
        const aisleStalls = generateStallsAlongAisle(
            aisleStart,
            aisleEnd,
            parkingConfig,
            'both'
        );

        // Filter stalls that fit within bay area
        const validStalls = aisleStalls.filter(stall => {
            const rect = {
                x: stall.x,
                y: stall.y,
                width: stall.width,
                height: stall.height,
                angle: stall.angle
            };
            const corners = getRectangleCorners(rect);
            return corners.every(c =>
                c.x >= bayArea.minX && c.x <= bayArea.maxX &&
                c.y >= bayArea.minY && c.y <= bayArea.maxY
            );
        });

        validStalls.forEach(s => {
            s.aisleIndex = m;
            stalls.push(s);
        });
    }

    // Step 7: Apply stall types (ADA, EV, Compact, Standard)
    const totalStalls = stalls.length;
    const adaCount = Math.max(1, Math.ceil(totalStalls * parkingConfig.adaPct / 100));
    const evCount = Math.ceil(totalStalls * parkingConfig.evPct / 100);
    const compactCount = Math.ceil(totalStalls * parkingConfig.compactPct / 100);

    // Assign types - ADA near entrance (bottom of site), then EV, then Compact
    stalls.sort((a, b) => b.y - a.y); // Sort by Y descending (near entrance = high Y)

    let typeIndex = 0;
    stalls.forEach((stall, idx) => {
        if (idx < adaCount) {
            stall.type = 'ada';
            stall.width = 12; // ADA stall wider
        } else if (idx < adaCount + evCount) {
            stall.type = 'ev';
        } else if (idx < adaCount + evCount + compactCount) {
            stall.type = 'compact';
            stall.width = parkingConfig.compactWidth;
            stall.height = parkingConfig.compactDepth;
        } else {
            stall.type = 'standard';
        }
    });

    // Step 8: Apply landscape islands if enabled
    if (parkingConfig.hasLandscaping || parkingConfig.hasEndIslands) {
        const interval = parkingConfig.landscapeInterval;
        stalls.forEach((stall, idx) => {
            // End islands (first and last stall of each aisle side)
            const isEndIsland = parkingConfig.hasEndIslands &&
                (idx % interval === 0 || idx % interval === interval - 1);

            // Landscape islands at intervals
            const isLandscapeIsland = parkingConfig.hasLandscaping &&
                idx > 0 && idx % interval === 0;

            if (isEndIsland || isLandscapeIsland) {
                stall.type = 'landscape';
            }
        });
    }

    // Step 9: Generate circulation loop
    const circulationLoop = {
        outer: {
            minX: buildableArea.minX + loopInset,
            maxX: buildableArea.maxX - loopInset,
            minY: buildableArea.minY + loopInset,
            maxY: buildableArea.maxY - loopInset
        },
        width: loopWidth,
        segments: [
            // Top
            {
                start: { x: buildableArea.minX + loopInset, y: buildableArea.minY + loopInset + loopWidth / 2 },
                end: { x: buildableArea.maxX - loopInset, y: buildableArea.minY + loopInset + loopWidth / 2 },
                direction: 'right'
            },
            // Right
            {
                start: { x: buildableArea.maxX - loopInset - loopWidth / 2, y: buildableArea.minY + loopInset },
                end: { x: buildableArea.maxX - loopInset - loopWidth / 2, y: buildableArea.maxY - loopInset },
                direction: 'down'
            },
            // Bottom
            {
                start: { x: buildableArea.maxX - loopInset, y: buildableArea.maxY - loopInset - loopWidth / 2 },
                end: { x: buildableArea.minX + loopInset, y: buildableArea.maxY - loopInset - loopWidth / 2 },
                direction: 'left'
            },
            // Left
            {
                start: { x: buildableArea.minX + loopInset + loopWidth / 2, y: buildableArea.maxY - loopInset },
                end: { x: buildableArea.minX + loopInset + loopWidth / 2, y: buildableArea.minY + loopInset },
                direction: 'up'
            }
        ]
    };

    // Step 10: Entry/Exit points
    const entryExitPoints = [];
    if (parkingConfig.hasEntryExit) {
        // Place entry and exit on bottom edge (main access road assumed at bottom)
        entryExitPoints.push({
            type: 'entry',
            x: buildableArea.minX + buildableArea.width * 0.25,
            y: buildableArea.maxY,
            width: 28,
            depth: loopWidth + 8
        });
        entryExitPoints.push({
            type: 'exit',
            x: buildableArea.minX + buildableArea.width * 0.75,
            y: buildableArea.maxY,
            width: 28,
            depth: loopWidth + 8
        });
    }

    // Calculate counts
    const counts = {
        standard: stalls.filter(s => s.type === 'standard').length,
        compact: stalls.filter(s => s.type === 'compact').length,
        ada: stalls.filter(s => s.type === 'ada').length,
        ev: stalls.filter(s => s.type === 'ev').length,
        landscape: stalls.filter(s => s.type === 'landscape').length,
        total: stalls.filter(s => s.type !== 'landscape').length
    };

    return {
        stalls,
        aisles,
        circulationLoop,
        entryExitPoints,
        bayArea,
        buildableArea,
        config: parkingConfig,
        counts,
        // Scoring metrics
        metrics: {
            stallCount: counts.total,
            aisleCount: aisles.length,
            efficiency: counts.total / (bayArea.width * bayArea.height) * (parkingConfig.stallWidth * parkingConfig.stallDepth),
            coverageRatio: (counts.total * parkingConfig.stallWidth * parkingConfig.stallDepth) / (buildableArea.width * buildableArea.height)
        }
    };
}

/**
 * Convert layout to render-ready format for 2D canvas
 */
export function layoutToCanvas2D(layout, scale = 1) {
    const { stalls, aisles, circulationLoop, entryExitPoints, config } = layout;

    return {
        // Stall rectangles ready for canvas drawing
        stallRects: stalls.map(s => ({
            x: s.x * scale,
            y: s.y * scale,
            width: s.width * scale,
            height: s.height * scale,
            angle: s.angle,
            type: s.type,
            color: getStallColor(s.type)
        })),

        // Aisle rectangles
        aisleRects: aisles.map(a => {
            const dx = a.end.x - a.start.x;
            const dy = a.end.y - a.start.y;
            const length = Math.sqrt(dx * dx + dy * dy);
            const angle = Math.atan2(dy, dx);
            const cx = (a.start.x + a.end.x) / 2;
            const cy = (a.start.y + a.end.y) / 2;

            return {
                x: cx * scale,
                y: cy * scale,
                width: length * scale,
                height: a.width * scale,
                angle: angle,
                color: 'rgba(31, 41, 55, 0.8)'
            };
        }),

        // Circulation loop segments
        loopSegments: circulationLoop.segments.map(seg => ({
            start: { x: seg.start.x * scale, y: seg.start.y * scale },
            end: { x: seg.end.x * scale, y: seg.end.y * scale },
            width: circulationLoop.width * scale,
            direction: seg.direction,
            color: 'rgba(75, 85, 99, 0.9)'
        })),

        // Entry/Exit
        entryExit: entryExitPoints.map(e => ({
            x: e.x * scale,
            y: e.y * scale,
            width: e.width * scale,
            depth: e.depth * scale,
            type: e.type,
            color: e.type === 'entry' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'
        }))
    };
}

/**
 * Get color for stall type
 */
function getStallColor(type) {
    const colors = {
        standard: '#fbbf24',  // Yellow
        compact: '#a855f7',   // Purple
        ada: '#3b82f6',       // Blue
        ev: '#22c55e',        // Green
        landscape: '#22c55e', // Green (island)
    };
    return colors[type] || colors.standard;
}

/**
 * Convert layout to Three.js ready format
 */
export function layoutToThreeJS(layout, centerX, centerY) {
    const { stalls, aisles, circulationLoop, entryExitPoints, bayArea, buildableArea, config } = layout;

    return {
        // Stalls with 3D positions
        stalls: stalls.map(s => ({
            // Convert to 3D coordinates (X stays, Y becomes -Z)
            x: s.x - centerX,
            z: centerY - s.y,
            width: s.width,
            depth: s.height,
            angle: s.angle,
            type: s.type,
            color: getStallColorHex(s.type)
        })),

        // Aisles
        aisles: aisles.map(a => {
            const cx = (a.start.x + a.end.x) / 2 - centerX;
            const cz = centerY - (a.start.y + a.end.y) / 2;
            const dx = a.end.x - a.start.x;
            const dy = a.end.y - a.start.y;
            const length = Math.sqrt(dx * dx + dy * dy);

            return {
                x: cx,
                z: cz,
                width: length,
                depth: a.width,
                angle: Math.atan2(dy, dx),
                color: 0x1f2937
            };
        }),

        // Circulation loop
        loop: {
            outer: {
                x: (circulationLoop.outer.minX + circulationLoop.outer.maxX) / 2 - centerX,
                z: centerY - (circulationLoop.outer.minY + circulationLoop.outer.maxY) / 2,
                width: circulationLoop.outer.maxX - circulationLoop.outer.minX,
                depth: circulationLoop.outer.maxY - circulationLoop.outer.minY
            },
            width: circulationLoop.width,
            color: 0x4b5563
        },

        // Entry/Exit
        entryExit: entryExitPoints.map(e => ({
            x: e.x - centerX,
            z: centerY - e.y,
            width: e.width,
            depth: e.depth,
            type: e.type,
            color: e.type === 'entry' ? 0x22c55e : 0xef4444
        })),

        // Bay area (for stall placement reference)
        bayArea: {
            x: (bayArea.minX + bayArea.maxX) / 2 - centerX,
            z: centerY - (bayArea.minY + bayArea.maxY) / 2,
            width: bayArea.width,
            depth: bayArea.height
        },

        // Asphalt base
        asphalt: {
            x: (buildableArea.minX + buildableArea.maxX) / 2 - centerX,
            z: centerY - (buildableArea.minY + buildableArea.maxY) / 2,
            width: buildableArea.width,
            depth: buildableArea.height,
            color: 0x374151
        }
    };
}

/**
 * Get hex color for Three.js materials
 */
function getStallColorHex(type) {
    const colors = {
        standard: 0xfbbf24,
        compact: 0xa855f7,
        ada: 0x3b82f6,
        ev: 0x22c55e,
        landscape: 0x22c55e
    };
    return colors[type] || colors.standard;
}

// Default export for full module import
// Note: Functions are already exported individually with 'export function' declarations
export default {
    generateSurfaceParkingLayout,
    layoutToCanvas2D,
    layoutToThreeJS
};
