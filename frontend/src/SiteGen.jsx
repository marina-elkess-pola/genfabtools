import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import SiteGen3DViewer from './SiteGen3DViewer';
import polygonClipping from 'polygon-clipping';
import pointInPolygon from 'robust-point-in-polygon';
// DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
import { getV2Flags, isV2Enabled } from './api2';

/**
 * SiteGen - Real Estate Feasibility Engine
 * 
 * Automated site planning tool that generates optimized building massing
 * and parking layouts given site constraints.
 */

// ============================================================================
// POLYGON GEOMETRY UTILITIES (for irregular parking lot shapes)
// ============================================================================

/**
 * Convert our {x, y} polygon format to polygon-clipping format [[x, y], ...]
 */
const toClipperFormat = (polygon) => {
    if (!polygon || polygon.length < 3) return null;
    return [polygon.map(p => [p.x, p.y])];
};

/**
 * Convert polygon-clipping format back to our {x, y} format
 */
const fromClipperFormat = (clipperResult) => {
    if (!clipperResult || clipperResult.length === 0) return [];
    // Take the first polygon (outer ring) from the first multi-polygon
    const firstPoly = clipperResult[0];
    if (!firstPoly || firstPoly.length === 0) return [];
    return firstPoly[0].map(([x, y]) => ({ x, y }));
};

/**
 * Offset (inset or expand) a polygon by a given distance
 * Positive offset = inset (shrink), Negative offset = expand
 * Uses edge-based offsetting that handles concave corners correctly
 */
const offsetPolygon = (polygon, offset) => {
    if (!polygon || polygon.length < 3 || offset === 0) return polygon;

    const n = polygon.length;

    // Determine winding order (positive = clockwise, negative = counter-clockwise)
    let signedArea = 0;
    for (let i = 0; i < n; i++) {
        const curr = polygon[i];
        const next = polygon[(i + 1) % n];
        signedArea += (next.x - curr.x) * (next.y + curr.y);
    }
    // For inset: positive offset should shrink the polygon
    // windingSign determines which direction is "inward"
    const windingSign = signedArea > 0 ? 1 : -1;

    // Create offset edges (each edge moved inward by offset distance)
    const offsetEdges = [];
    for (let i = 0; i < n; i++) {
        const curr = polygon[i];
        const next = polygon[(i + 1) % n];

        // Edge vector
        const dx = next.x - curr.x;
        const dy = next.y - curr.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;

        // Perpendicular normal (inward direction based on winding)
        const nx = windingSign * dy / len;
        const ny = windingSign * -dx / len;

        // Offset both endpoints of this edge
        offsetEdges.push({
            x1: curr.x + nx * offset,
            y1: curr.y + ny * offset,
            x2: next.x + nx * offset,
            y2: next.y + ny * offset
        });
    }

    // Find intersections of consecutive offset edges to get new vertices
    const result = [];
    for (let i = 0; i < n; i++) {
        const edge1 = offsetEdges[i];
        const edge2 = offsetEdges[(i + 1) % n];

        // Line intersection: find where edge1 and edge2 meet
        const x1 = edge1.x1, y1 = edge1.y1, x2 = edge1.x2, y2 = edge1.y2;
        const x3 = edge2.x1, y3 = edge2.y1, x4 = edge2.x2, y4 = edge2.y2;

        const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);

        if (Math.abs(denom) < 0.0001) {
            // Lines are parallel, use the endpoint
            result.push({ x: edge1.x2, y: edge1.y2 });
        } else {
            // Calculate intersection point
            const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
            const ix = x1 + t * (x2 - x1);
            const iy = y1 + t * (y2 - y1);
            result.push({ x: ix, y: iy });
        }
    }

    return result;
};

/**
 * Check if a point is inside a polygon
 * Returns: -1 = inside, 0 = on boundary, 1 = outside
 */
const isPointInPolygon = (point, polygon) => {
    if (!polygon || polygon.length < 3) return false;
    const pts = polygon.map(p => [p.x, p.y]);
    const result = pointInPolygon(pts, [point.x, point.y]);
    return result <= 0; // -1 (inside) or 0 (on boundary) = true
};

/**
 * Check if a rectangle is fully inside a polygon
 */
const isRectInPolygon = (x, y, w, h, polygon) => {
    // Check all four corners
    const corners = [
        { x: x, y: y },
        { x: x + w, y: y },
        { x: x + w, y: y + h },
        { x: x, y: y + h }
    ];
    return corners.every(corner => isPointInPolygon(corner, polygon));
};

/**
 * Check if a rectangle is at least partially inside a polygon (for partial stalls)
 */
const isRectPartiallyInPolygon = (x, y, w, h, polygon) => {
    const corners = [
        { x: x, y: y },
        { x: x + w, y: y },
        { x: x + w, y: y + h },
        { x: x, y: y + h }
    ];
    return corners.some(corner => isPointInPolygon(corner, polygon));
};

/**
 * Calculate the area of a polygon using the shoelace formula
 */
const polygonArea = (polygon) => {
    if (!polygon || polygon.length < 3) return 0;
    let area = 0;
    const n = polygon.length;
    for (let i = 0; i < n; i++) {
        const curr = polygon[i];
        const next = polygon[(i + 1) % n];
        area += curr.x * next.y - next.x * curr.y;
    }
    return Math.abs(area) / 2;
};

/**
 * Get the centroid of a polygon
 */
const polygonCentroid = (polygon) => {
    if (!polygon || polygon.length < 3) return { x: 0, y: 0 };
    let cx = 0, cy = 0;
    const n = polygon.length;
    for (let i = 0; i < n; i++) {
        cx += polygon[i].x;
        cy += polygon[i].y;
    }
    return { x: cx / n, y: cy / n };
};

/**
 * Get bounding box of a polygon
 */
const polygonBounds = (polygon) => {
    if (!polygon || polygon.length === 0) return { minX: 0, maxX: 0, minY: 0, maxY: 0, width: 0, height: 0 };
    const xs = polygon.map(p => p.x);
    const ys = polygon.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    return { minX, maxX, minY, maxY, width: maxX - minX, height: maxY - minY };
};

/**
 * Find the longest edge of a polygon (for optimal stall orientation)
 */
const findLongestEdge = (polygon) => {
    if (!polygon || polygon.length < 2) return { angle: 0, length: 0, midpoint: { x: 0, y: 0 } };

    let longest = { length: 0, angle: 0, midpoint: { x: 0, y: 0 }, start: null, end: null };
    const n = polygon.length;

    for (let i = 0; i < n; i++) {
        const p1 = polygon[i];
        const p2 = polygon[(i + 1) % n];
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const length = Math.sqrt(dx * dx + dy * dy);

        if (length > longest.length) {
            longest = {
                length,
                angle: Math.atan2(dy, dx),
                midpoint: { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 },
                start: p1,
                end: p2
            };
        }
    }

    return longest;
};

/**
 * Find rectangular sub-regions in an irregular polygon where cross-aisles can be placed.
 * Scans the polygon to find continuous rectangular areas that are wide enough for a spine.
 * 
 * @param {Array} polygon - Array of {x, y} points
 * @param {number} minWidth - Minimum width for a rectangular region (e.g., 200ft)
 * @param {number} spineWidth - Width of the cross-aisle spine (e.g., 24ft)
 * @returns {Array} - Array of {x, minY, maxY} positions where spines can be placed
 */
const findRectangularSubRegions = (polygon, minWidth = 200, spineWidth = 24) => {
    if (!polygon || polygon.length < 3) return [];

    const bounds = polygonBounds(polygon);
    const scanStep = 5; // Scan every 5 feet
    const spines = [];

    // Scan horizontally to find vertical strips
    for (let x = bounds.minX + spineWidth; x < bounds.maxX - spineWidth; x += scanStep) {
        // Check if this X position has enough continuous vertical extent
        let minYInside = null;
        let maxYInside = null;
        let gapDetected = false;

        for (let y = bounds.minY; y <= bounds.maxY; y += scanStep) {
            const testPoint = { x, y };
            const isInside = isPointInPolygon(testPoint, polygon);

            if (isInside) {
                if (minYInside === null) {
                    minYInside = y;
                }
                if (gapDetected) {
                    // Gap in the polygon - reset (L/U shape detected)
                    minYInside = y;
                    gapDetected = false;
                }
                maxYInside = y;
            } else if (minYInside !== null && maxYInside !== null) {
                gapDetected = true;
            }
        }

        if (minYInside !== null && maxYInside !== null) {
            const verticalExtent = maxYInside - minYInside;

            // Only consider positions that have significant vertical extent
            // and are far enough from other spines
            if (verticalExtent >= 50) {
                // Check horizontal extent at this X (is there enough width on both sides?)
                const leftBoundary = findPolygonEdgeAtY((minYInside + maxYInside) / 2, polygon, 'left');
                const rightBoundary = findPolygonEdgeAtY((minYInside + maxYInside) / 2, polygon, 'right');

                const leftWidth = x - leftBoundary;
                const rightWidth = rightBoundary - x;

                // Only add spine if there's significant parking area on both sides
                if (leftWidth >= 50 && rightWidth >= 50 && (leftWidth + rightWidth) >= minWidth) {
                    // Check if we already have a spine nearby
                    const tooClose = spines.some(s => Math.abs(s.x - x) < minWidth / 2);
                    if (!tooClose) {
                        spines.push({
                            x: x,
                            minY: minYInside,
                            maxY: maxYInside,
                            leftWidth,
                            rightWidth
                        });
                    }
                }
            }
        }
    }

    return spines;
};

/**
 * Find polygon edge at a given Y coordinate
 * @param {number} y - Y coordinate to scan
 * @param {Array} polygon - Array of {x, y} points
 * @param {string} side - 'left' or 'right'
 * @returns {number} - X coordinate of edge
 */
const findPolygonEdgeAtY = (y, polygon, side = 'left') => {
    const bounds = polygonBounds(polygon);
    const scanStep = 2;

    if (side === 'left') {
        for (let x = bounds.minX; x <= bounds.maxX; x += scanStep) {
            if (isPointInPolygon({ x, y }, polygon)) {
                return x;
            }
        }
        return bounds.minX;
    } else {
        for (let x = bounds.maxX; x >= bounds.minX; x -= scanStep) {
            if (isPointInPolygon({ x, y }, polygon)) {
                return x;
            }
        }
        return bounds.maxX;
    }
};

/**
 * Build junction points from connected aisles.
 * Points that are within snapDistance of each other are considered connected.
 * @param {Array} aisles - Array of {id, points: [{x,y},...]}
 * @param {number} snapDistance - Distance threshold for junction detection (in feet)
 * @returns {Array} - Array of {id, x, y, connections: [{aisleId, pointIndex},...]}
 */
const buildAisleJunctions = (aisles, snapDistance = 10) => {
    if (!aisles || aisles.length === 0) return [];

    const junctions = [];
    const usedPoints = new Set(); // Track which points have been assigned to junctions
    let junctionId = 0;

    // Collect all aisle points with their references
    const allPoints = [];
    aisles.forEach(aisle => {
        aisle.points.forEach((point, pointIndex) => {
            allPoints.push({
                x: point.x,
                y: point.y,
                aisleId: aisle.id,
                pointIndex,
                key: `${aisle.id}-${pointIndex}`
            });
        });
    });

    // Find clusters of nearby points
    allPoints.forEach((point, idx) => {
        if (usedPoints.has(point.key)) return;

        // Find all points within snap distance
        const cluster = [point];
        usedPoints.add(point.key);

        allPoints.forEach((otherPoint, otherIdx) => {
            if (idx === otherIdx || usedPoints.has(otherPoint.key)) return;

            const dx = point.x - otherPoint.x;
            const dy = point.y - otherPoint.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist <= snapDistance) {
                cluster.push(otherPoint);
                usedPoints.add(otherPoint.key);
            }
        });

        // Only create junction if multiple points are connected
        if (cluster.length > 1) {
            // Average position for the junction
            const avgX = cluster.reduce((sum, p) => sum + p.x, 0) / cluster.length;
            const avgY = cluster.reduce((sum, p) => sum + p.y, 0) / cluster.length;

            junctions.push({
                id: junctionId++,
                x: avgX,
                y: avgY,
                connections: cluster.map(p => ({
                    aisleId: p.aisleId,
                    pointIndex: p.pointIndex
                }))
            });
        }
    });

    return junctions;
};

/**
 * Find which aisle point or junction is at a given position
 * @param {number} x - X coordinate
 * @param {number} y - Y coordinate  
 * @param {Array} aisles - Array of aisles
 * @param {Array} junctions - Array of junctions
 * @param {number} hitRadius - Detection radius in feet
 * @returns {Object|null} - {type: 'junction', junctionId} or {type: 'point', aisleId, pointIndex}
 */
const findAislePointAtPosition = (x, y, aisles, junctions, hitRadius = 8) => {
    // Check junctions first (they have priority)
    for (const junction of junctions) {
        const dx = x - junction.x;
        const dy = y - junction.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist <= hitRadius) {
            return { type: 'junction', junctionId: junction.id };
        }
    }

    // Check individual aisle points (excluding those in junctions)
    const junctionPoints = new Set();
    junctions.forEach(j => {
        j.connections.forEach(c => {
            junctionPoints.add(`${c.aisleId}-${c.pointIndex}`);
        });
    });

    for (const aisle of aisles) {
        for (let i = 0; i < aisle.points.length; i++) {
            const key = `${aisle.id}-${i}`;
            if (junctionPoints.has(key)) continue;

            const point = aisle.points[i];
            const dx = x - point.x;
            const dy = y - point.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist <= hitRadius) {
                return { type: 'point', aisleId: aisle.id, pointIndex: i };
            }
        }
    }

    return null;
};

/**
 * Find the closest point on any aisle segment (for adding new points)
 * @param {number} x - X coordinate
 * @param {number} y - Y coordinate
 * @param {Array} aisles - Array of aisles
 * @param {number} maxDistance - Maximum distance to consider (in feet)
 * @returns {Object|null} - {aisleId, segmentIndex, x, y, distance} or null
 */
const findClosestAisleSegment = (x, y, aisles, maxDistance = 15) => {
    let closest = null;
    let minDist = maxDistance;

    for (const aisle of aisles) {
        if (!aisle.points || aisle.points.length < 2) continue;

        for (let i = 0; i < aisle.points.length - 1; i++) {
            const p1 = aisle.points[i];
            const p2 = aisle.points[i + 1];

            // Calculate closest point on segment
            const dx = p2.x - p1.x;
            const dy = p2.y - p1.y;
            const lengthSq = dx * dx + dy * dy;

            if (lengthSq === 0) continue;

            let t = ((x - p1.x) * dx + (y - p1.y) * dy) / lengthSq;
            t = Math.max(0.1, Math.min(0.9, t)); // Keep away from endpoints

            const nearestX = p1.x + t * dx;
            const nearestY = p1.y + t * dy;
            const dist = Math.sqrt((x - nearestX) * (x - nearestX) + (y - nearestY) * (y - nearestY));

            if (dist < minDist) {
                minDist = dist;
                closest = {
                    aisleId: aisle.id,
                    segmentIndex: i,
                    x: nearestX,
                    y: nearestY,
                    distance: dist
                };
            }
        }
    }

    return closest;
};

// ============================================================================
// CUSTOM AISLE COLLISION DETECTION
// For calculating stall exclusions when custom aisles are drawn
// ============================================================================

/**
 * Calculate distance from a point to a line segment
 * @param {number} px - Point X
 * @param {number} py - Point Y
 * @param {number} x1 - Segment start X
 * @param {number} y1 - Segment start Y
 * @param {number} x2 - Segment end X
 * @param {number} y2 - Segment end Y
 * @returns {number} - Distance from point to segment
 */
const pointToSegmentDistance = (px, py, x1, y1, x2, y2) => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;

    if (lengthSq === 0) {
        // Segment is a point
        return Math.sqrt((px - x1) * (px - x1) + (py - y1) * (py - y1));
    }

    // Project point onto line, clamped to segment
    let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
    t = Math.max(0, Math.min(1, t));

    const nearestX = x1 + t * dx;
    const nearestY = y1 + t * dy;

    return Math.sqrt((px - nearestX) * (px - nearestX) + (py - nearestY) * (py - nearestY));
};

/**
 * Check if a rectangle (stall) collides with any custom aisle
 * @param {number} stallX - Stall left X coordinate
 * @param {number} stallY - Stall top Y coordinate
 * @param {number} stallW - Stall width
 * @param {number} stallH - Stall height (depth)
 * @param {Array} aisles - Array of {id, points: [{x,y},...]}
 * @param {number} aisleWidth - Width of aisles in feet
 * @returns {boolean} - True if stall collides with any aisle
 */
const stallCollidesWithAisles = (stallX, stallY, stallW, stallH, aisles, aisleWidth) => {
    if (!aisles || aisles.length === 0) return false;

    // Get stall center and corners
    const centerX = stallX + stallW / 2;
    const centerY = stallY + stallH / 2;
    const corners = [
        { x: stallX, y: stallY },
        { x: stallX + stallW, y: stallY },
        { x: stallX + stallW, y: stallY + stallH },
        { x: stallX, y: stallY + stallH }
    ];

    const halfAisleWidth = aisleWidth / 2;

    for (const aisle of aisles) {
        if (!aisle.points || aisle.points.length < 2) continue;

        // Check each segment of the aisle
        for (let i = 0; i < aisle.points.length - 1; i++) {
            const p1 = aisle.points[i];
            const p2 = aisle.points[i + 1];

            // Check if stall center is within aisle width of the segment
            const centerDist = pointToSegmentDistance(centerX, centerY, p1.x, p1.y, p2.x, p2.y);
            if (centerDist < halfAisleWidth + Math.min(stallW, stallH) / 2) {
                return true;
            }

            // Check if any corner is within aisle width
            for (const corner of corners) {
                const cornerDist = pointToSegmentDistance(corner.x, corner.y, p1.x, p1.y, p2.x, p2.y);
                if (cornerDist < halfAisleWidth) {
                    return true;
                }
            }
        }
    }

    return false;
};

/**
 * Generate stalls along a custom aisle path
 * Places stalls perpendicular to each segment on both sides
 * @param {Object} aisle - {id, points: [{x,y},...]}
 * @param {number} stallWidth - Width of each stall
 * @param {number} stallDepth - Depth of each stall
 * @param {number} aisleWidth - Width of the drive aisle
 * @param {Object} bounds - {minX, minY, maxX, maxY} parking area bounds
 * @returns {Array} - Array of stall objects {x, y, w, h, angle, side}
 */
const generateStallsAlongAisle = (aisle, stallWidth, stallDepth, aisleWidth, bounds) => {
    if (!aisle.points || aisle.points.length < 2) return [];

    const stalls = [];
    const halfAisle = aisleWidth / 2;

    for (let i = 0; i < aisle.points.length - 1; i++) {
        const p1 = aisle.points[i];
        const p2 = aisle.points[i + 1];

        // Calculate segment direction and perpendicular
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const segmentLength = Math.sqrt(dx * dx + dy * dy);
        if (segmentLength < stallWidth) continue;

        // Unit vectors
        const ux = dx / segmentLength; // Along segment
        const uy = dy / segmentLength;
        const nx = -uy; // Perpendicular (normal)
        const ny = ux;

        // Calculate angle for stall rotation
        const angle = Math.atan2(dy, dx) * 180 / Math.PI;

        // Number of stalls that fit along this segment
        const numStalls = Math.floor(segmentLength / stallWidth);
        const startOffset = (segmentLength - numStalls * stallWidth) / 2;

        for (let j = 0; j < numStalls; j++) {
            const t = startOffset + j * stallWidth + stallWidth / 2;
            const cx = p1.x + ux * t; // Center along segment
            const cy = p1.y + uy * t;

            // Left side stall
            const leftX = cx + nx * (halfAisle + stallDepth / 2);
            const leftY = cy + ny * (halfAisle + stallDepth / 2);
            if (leftX >= bounds.minX && leftX <= bounds.maxX &&
                leftY >= bounds.minY && leftY <= bounds.maxY) {
                stalls.push({
                    x: leftX - stallWidth / 2,
                    y: leftY - stallDepth / 2,
                    w: stallWidth,
                    h: stallDepth,
                    angle: angle + 90,
                    side: 'left',
                    centerX: leftX,
                    centerY: leftY
                });
            }

            // Right side stall
            const rightX = cx - nx * (halfAisle + stallDepth / 2);
            const rightY = cy - ny * (halfAisle + stallDepth / 2);
            if (rightX >= bounds.minX && rightX <= bounds.maxX &&
                rightY >= bounds.minY && rightY <= bounds.maxY) {
                stalls.push({
                    x: rightX - stallWidth / 2,
                    y: rightY - stallDepth / 2,
                    w: stallWidth,
                    h: stallDepth,
                    angle: angle - 90,
                    side: 'right',
                    centerX: rightX,
                    centerY: rightY
                });
            }
        }
    }

    return stalls;
};

/**
 * Check if a point is inside a polygon (for bounds validation)
 */
const isPointInParkingBounds = (x, y, bounds) => {
    if (!bounds) return true;
    return x >= bounds.minX && x <= bounds.maxX && y >= bounds.minY && y <= bounds.maxY;
};

// ============================================================================
// ADA ACCESSIBLE PARKING REQUIREMENTS
// Per ADA Standards for Accessible Design (2010) and IBC
// ============================================================================

/**
 * Calculate required number of accessible parking spaces per ADA Table 208.2
 * @param {number} totalSpaces - Total parking spaces in lot
 * @returns {object} - { total: required ADA spaces, vanAccessible: required van spaces }
 */
const calculateAdaRequired = (totalSpaces) => {
    let adaRequired = 0;

    if (totalSpaces <= 0) {
        adaRequired = 0;
    } else if (totalSpaces <= 25) {
        adaRequired = 1;
    } else if (totalSpaces <= 50) {
        adaRequired = 2;
    } else if (totalSpaces <= 75) {
        adaRequired = 3;
    } else if (totalSpaces <= 100) {
        adaRequired = 4;
    } else if (totalSpaces <= 150) {
        adaRequired = 5;
    } else if (totalSpaces <= 200) {
        adaRequired = 6;
    } else if (totalSpaces <= 300) {
        adaRequired = 7;
    } else if (totalSpaces <= 400) {
        adaRequired = 8;
    } else if (totalSpaces <= 500) {
        adaRequired = 9;
    } else if (totalSpaces <= 1000) {
        // 2% of total
        adaRequired = Math.ceil(totalSpaces * 0.02);
    } else {
        // 20 + 1 for each 100 over 1000
        adaRequired = 20 + Math.ceil((totalSpaces - 1000) / 100);
    }

    // Van accessible: at least 1 for every 6 accessible (or fraction thereof)
    // Minimum 1 van accessible space
    const vanAccessible = Math.max(1, Math.ceil(adaRequired / 6));

    return {
        total: adaRequired,
        vanAccessible,
        standard: adaRequired - vanAccessible
    };
};

// ============================================================================
// ANGLED PARKING GEOMETRY - Supports 45°, 60°, and 90° parking
// Based on ITE Parking Generation Manual and MUTCD standards
// ============================================================================

/**
 * Get parking stall geometry for a given angle
 * Returns the projected dimensions and optimal aisle width
 * 
 * Standard stall: 9' x 18' (width x depth)
 * 
 * For angled parking, we need:
 * - Projected width (spacing along the aisle) = width/sin(angle) 
 * - Projected depth (perpendicular to aisle) = depth*cos(angle) + width*sin(angle)
 * - Aisle width depends on one-way vs two-way and parking angle
 */
const getAngledParkingGeometry = (angle, stallWidth = 9, stallDepth = 18, driveType = 'twoWay') => {
    const angleRad = (angle * Math.PI) / 180;
    const sin = Math.sin(angleRad);
    const cos = Math.cos(angleRad);

    // ITE Parking Generation Manual standard dimensions
    // Module width = stall width / sin(angle) - spacing along the aisle
    const stallModuleWidth = angle === 90 ? stallWidth : stallWidth / sin;

    // Stall depth projection (perpendicular to aisle) per ITE:
    // This is measured from the aisle edge to the wall/curb
    // Formula: (L × sin(θ)) + (W × cos(θ)) where L=stall length, W=stall width
    // This accounts for the full stall including the angled orientation
    const stallDepthProjection = angle === 90 ? stallDepth : (stallDepth * sin) + (stallWidth * cos);

    // Optimal aisle widths by angle and drive type (per ITE/MUTCD standards)
    const aisleWidths = {
        45: { oneWay: 12, twoWay: 18, hybrid: 14 },
        60: { oneWay: 15, twoWay: 20, hybrid: 16 },
        90: { oneWay: 24, twoWay: 24, hybrid: 20 },
    };

    const angleAisles = aisleWidths[angle] || aisleWidths[90];
    const recommendedAisleWidth = angleAisles[driveType] || angleAisles.twoWay;

    // Module depth = two stall rows + one aisle (for double-loaded)
    const moduleDepth = stallDepthProjection * 2 + recommendedAisleWidth;

    return {
        angle,
        angleRad,
        stallWidth,
        stallDepth,
        stallModuleWidth,
        stallDepthProjection,
        recommendedAisleWidth,
        moduleDepth,
        sin,
        cos,
        // For drawing: the stall parallelogram corners
        getStallCorners: (x, y, isTopRow = true) => {
            // The stall is drawn as a parallelogram
            // Front width along aisle = stallModuleWidth  
            // The back edge is offset by how much the stall "leans"
            // Lean = stallWidth × cos(θ) - this is the horizontal component of the stall width
            const lean = stallWidth * cos;

            if (angle === 90) {
                // Perpendicular parking - simple rectangle (no lean)
                // Both rows draw DOWN from rowY
                return [
                    { x: x, y: y },
                    { x: x + stallWidth, y: y },
                    { x: x + stallWidth, y: y + stallDepth },
                    { x: x, y: y + stallDepth },
                ];
            }

            // Angled parking - parallelogram
            // BOTH rows draw DOWN from rowY (front at y, back at y + depthProjection)
            // The difference is the LEAN DIRECTION:
            // - Top row: back edge shifts LEFT (creates \ pattern) 
            // - Bottom row: back edge shifts RIGHT (creates / pattern)
            // This creates proper herringbone/chevron pattern:
            //   ╲╲╲╲╲╲  ← Top row
            //   ══════  ← Aisle  
            //   ╱╱╱╱╱╱  ← Bottom row
            if (isTopRow) {
                // Top row: back edge shifts LEFT by lean (negative X direction)
                return [
                    { x: x, y: y },                                            // Front-left
                    { x: x + stallModuleWidth, y: y },                         // Front-right
                    { x: x + stallModuleWidth - lean, y: y + stallDepthProjection },  // Back-right (shifted LEFT)
                    { x: x - lean, y: y + stallDepthProjection },              // Back-left (shifted LEFT)
                ];
            } else {
                // Bottom row: back edge shifts RIGHT by lean (positive X direction)
                return [
                    { x: x, y: y },                                            // Front-left
                    { x: x + stallModuleWidth, y: y },                         // Front-right
                    { x: x + stallModuleWidth + lean, y: y + stallDepthProjection },  // Back-right (shifted RIGHT)
                    { x: x + lean, y: y + stallDepthProjection },              // Back-left (shifted RIGHT)
                ];
            }
        }
    };
};

/**
 * Check if an angled stall fits inside a polygon
 * Uses the parallelogram corners for accurate boundary checking
 */
const isAngledStallInPolygon = (stallCorners, polygon) => {
    if (!polygon || polygon.length < 3 || !stallCorners || stallCorners.length < 4) return false;

    // Check if all corners are inside the polygon
    return stallCorners.every(corner => isPointInPolygon(corner, polygon));
};

/**
 * Calculate the center point of an angled stall for placement validation
 */
const getAngledStallCenter = (stallCorners) => {
    if (!stallCorners || stallCorners.length < 4) return { x: 0, y: 0 };
    const sumX = stallCorners.reduce((sum, c) => sum + c.x, 0);
    const sumY = stallCorners.reduce((sum, c) => sum + c.y, 0);
    return { x: sumX / 4, y: sumY / 4 };
};

// ============================================================================
// BUILDING TYPE TEMPLATES
// ============================================================================

const BUILDING_TYPES = {
    multifamily: {
        name: 'Multi-Family',
        icon: '🏢',
        subtypes: {
            garden: { name: 'Garden Apartments', floors: 3, unitSize: 850, efficiency: 0.85, parkingRatio: 1.5, floorHeight: 10 },
            midrise: { name: 'Mid-Rise (4-6 floors)', floors: 5, unitSize: 900, efficiency: 0.82, parkingRatio: 1.25, floorHeight: 10 },
            highrise: { name: 'High-Rise (7+ floors)', floors: 12, unitSize: 950, efficiency: 0.78, parkingRatio: 1.0, floorHeight: 10 },
            affordable: { name: 'Affordable Housing', floors: 4, unitSize: 750, efficiency: 0.85, parkingRatio: 0.75, floorHeight: 10 },
            senior: { name: 'Senior Living', floors: 4, unitSize: 650, efficiency: 0.80, parkingRatio: 0.5, floorHeight: 10 },
            student: { name: 'Student Housing', floors: 5, unitSize: 400, efficiency: 0.80, parkingRatio: 0.5, floorHeight: 10 },
        },
        unitLabel: 'Units',
        metrics: ['units', 'bedrooms', 'parking']
    },
    singlefamily: {
        name: 'Single-Family',
        icon: '🏠',
        subtypes: {
            detached: { name: 'Detached Homes', lotSize: 5000, unitSize: 2200, floors: 2, parkingRatio: 2.0, floorHeight: 10 },
            attached: { name: 'Townhomes', lotSize: 2000, unitSize: 1800, floors: 3, parkingRatio: 2.0, floorHeight: 10 },
            duplex: { name: 'Duplex', lotSize: 3500, unitSize: 1400, floors: 2, parkingRatio: 2.0, floorHeight: 10 },
            cottage: { name: 'Cottage Court', lotSize: 2500, unitSize: 1000, floors: 1, parkingRatio: 1.5, floorHeight: 10 },
            adu: { name: 'ADU / Accessory Units', lotSize: 1500, unitSize: 600, floors: 1, parkingRatio: 1.0, floorHeight: 10 },
        },
        unitLabel: 'Lots',
        metrics: ['lots', 'units', 'parking']
    },
    industrial: {
        name: 'Industrial',
        icon: '🏭',
        subtypes: {
            warehouse: { name: 'Warehouse', clearHeight: 32, coverage: 0.55, dockRatio: 1, parkingRatio: 0.5, floorHeight: 36 },
            lightindustrial: { name: 'Light Industrial', clearHeight: 24, coverage: 0.50, dockRatio: 0.5, parkingRatio: 1.0, floorHeight: 28 },
            manufacturing: { name: 'Manufacturing', clearHeight: 28, coverage: 0.45, dockRatio: 2, parkingRatio: 1.5, floorHeight: 32 },
            flexspace: { name: 'Flex Space', clearHeight: 20, coverage: 0.50, dockRatio: 0.25, parkingRatio: 2.0, floorHeight: 24 },
            coldStorage: { name: 'Cold Storage', clearHeight: 40, coverage: 0.50, dockRatio: 3, parkingRatio: 0.3, floorHeight: 44 },
        },
        unitLabel: 'SF',
        metrics: ['sf', 'docks', 'parking']
    },
    hotel: {
        name: 'Hotel',
        icon: '🏨',
        subtypes: {
            budget: { name: 'Budget / Economy', roomSize: 280, efficiency: 0.70, parkingRatio: 0.8, floorHeight: 10, floors: 4 },
            select: { name: 'Select Service', roomSize: 350, efficiency: 0.68, parkingRatio: 1.0, floorHeight: 10, floors: 5 },
            fullservice: { name: 'Full Service', roomSize: 450, efficiency: 0.62, parkingRatio: 1.2, floorHeight: 11, floors: 8 },
            luxury: { name: 'Luxury', roomSize: 600, efficiency: 0.55, parkingRatio: 1.5, floorHeight: 12, floors: 10 },
            extended: { name: 'Extended Stay', roomSize: 400, efficiency: 0.72, parkingRatio: 1.0, floorHeight: 10, floors: 5 },
            resort: { name: 'Resort', roomSize: 550, efficiency: 0.50, parkingRatio: 1.5, floorHeight: 11, floors: 6 },
        },
        unitLabel: 'Rooms',
        metrics: ['rooms', 'keys', 'parking']
    },
    retail: {
        name: 'Retail',
        icon: '🛒',
        subtypes: {
            neighborhood: { name: 'Neighborhood Center', avgTenant: 3000, coverage: 0.25, parkingRatio: 4.0, floorHeight: 16, floors: 1 },
            community: { name: 'Community Center', avgTenant: 8000, coverage: 0.30, parkingRatio: 4.5, floorHeight: 18, floors: 1 },
            power: { name: 'Power Center', avgTenant: 25000, coverage: 0.30, parkingRatio: 5.0, floorHeight: 24, floors: 1 },
            lifestyle: { name: 'Lifestyle Center', avgTenant: 5000, coverage: 0.35, parkingRatio: 4.0, floorHeight: 16, floors: 2 },
            strip: { name: 'Strip Mall', avgTenant: 1500, coverage: 0.25, parkingRatio: 4.0, floorHeight: 14, floors: 1 },
            grocery: { name: 'Grocery Anchored', avgTenant: 45000, coverage: 0.28, parkingRatio: 5.0, floorHeight: 20, floors: 1 },
        },
        unitLabel: 'SF',
        metrics: ['sf', 'tenants', 'parking']
    },
    datacenter: {
        name: 'Data Center',
        icon: '🖥️',
        subtypes: {
            hyperscale: { name: 'Hyperscale', powerDensity: 150, coverage: 0.40, parkingRatio: 0.1, floorHeight: 16, floors: 2 },
            colocation: { name: 'Colocation', powerDensity: 100, coverage: 0.45, parkingRatio: 0.2, floorHeight: 14, floors: 3 },
            enterprise: { name: 'Enterprise', powerDensity: 80, coverage: 0.40, parkingRatio: 0.3, floorHeight: 14, floors: 2 },
            edge: { name: 'Edge / Micro', powerDensity: 50, coverage: 0.50, parkingRatio: 0.2, floorHeight: 12, floors: 1 },
        },
        unitLabel: 'MW',
        metrics: ['mw', 'sf', 'parking']
    },
    parking: {
        name: 'Parking',
        icon: '🅿️',
        subtypes: {
            surface: { name: 'Surface Lot', stallsPerAcre: 120, coverage: 0.90, floors: 1, floorHeight: 0 },
            structured: { name: 'Parking Structure', stallsPerSF: 0.003, coverage: 0.85, floors: 5, floorHeight: 11 },
            underground: { name: 'Underground', stallsPerSF: 0.0028, coverage: 0.90, floors: 2, floorHeight: 11 },
            automated: { name: 'Automated / Robotic', stallsPerSF: 0.005, coverage: 0.80, floors: 8, floorHeight: 8 },
            mixeduse: { name: 'Mixed-Use Podium', stallsPerSF: 0.003, coverage: 0.85, floors: 3, floorHeight: 11 },
        },
        unitLabel: 'Stalls',
        metrics: ['stalls', 'levels', 'sf']
    },
};

// ============================================================================
// MASSING TYPOLOGIES - Visual building configurations
// ============================================================================

const MASSING_TYPOLOGIES = {
    multifamily: {
        podium: {
            name: 'Podium',
            description: 'Units over retail/parking base',
            icon: '🏗️',
            config: { podiumFloors: 2, residentialFloors: 4, totalFloors: 6, floorHeight: 10, podiumHeight: 15, towerWidthPct: 70, towerDepthPct: 70 },
            preview: { hasBase: true, baseColor: '#6b7280', towerColor: '#8b5cf6', baseRatio: 0.25 }
        },
        wrap: {
            name: 'Wrap',
            description: 'Units wrap around parking garage',
            icon: '🔲',
            config: { floors: 5, floorHeight: 10, garageFloors: 4, garageHeight: 11, wrapThicknessPct: 20 },
            preview: { hasCore: true, coreColor: '#6b7280', wrapColor: '#8b5cf6', coreRatio: 0.4 }
        },
        townhomes: {
            name: 'Townhomes',
            description: '3-story attached row houses',
            icon: '🏘️',
            config: { floors: 3, floorHeight: 10, unitWidth: 24, unitDepth: 50 },
            preview: { isRows: true, rowColor: '#8b5cf6', gapRatio: 0.3 }
        },
        garden: {
            name: 'Garden',
            description: 'Surface parking with 3-story buildings',
            icon: '🌳',
            config: { floors: 3, floorHeight: 10, buildingCount: 4 },
            preview: { isScattered: true, buildingColor: '#8b5cf6', parkingColor: '#fbbf24' }
        },
        tower: {
            name: 'Tower',
            description: 'High-rise (10+) over podium',
            icon: '🏙️',
            config: { towerFloors: 20, podiumFloors: 3, floorHeight: 10, podiumHeight: 12, towerWidthPct: 35, towerDepthPct: 35 },
            preview: { hasTower: true, podiumColor: '#6b7280', towerColor: '#8b5cf6', towerRatio: 0.5 }
        },
        gurban: {
            name: 'Gurban',
            description: 'Garden-urban with surface parking',
            icon: '🏛️',
            config: { floors: 4, floorHeight: 10 },
            preview: { isLShape: true, buildingColor: '#8b5cf6', parkingColor: '#fbbf24' }
        },
    },
    singlefamily: {
        subdivision: { name: 'Subdivision', description: 'Traditional lot layout', icon: '🏡', config: { floors: 2, floorHeight: 10 } },
        cluster: { name: 'Cluster', description: 'Clustered with common green', icon: '🌲', config: { floors: 2, floorHeight: 10 } },
        courtyard: { name: 'Courtyard', description: 'Units around shared court', icon: '⬜', config: { floors: 2, floorHeight: 10 } },
    },
    industrial: {
        bigbox: { name: 'Big Box', description: 'Single large warehouse', icon: '📦', config: { floors: 1, clearHeight: 36, floorHeight: 40 } },
        multibuilding: { name: 'Multi-Building', description: 'Multiple warehouse buildings', icon: '🏢', config: { floors: 1, clearHeight: 32, floorHeight: 36 } },
        crossdock: { name: 'Cross-Dock', description: 'Through-loading facility', icon: '🔀', config: { floors: 1, clearHeight: 32, floorHeight: 36, dockHeight: 20 } },
        podium: { name: 'Podium', description: 'Warehouse over podium base', icon: '🏗️', config: { podiumFloors: 1, warehouseFloors: 1, clearHeight: 32, podiumHeight: 14 }, preview: { hasBase: true, baseColor: '#6b7280', towerColor: '#f59e0b', baseRatio: 0.3 } },
    },
    hotel: {
        courtyard: { name: 'Courtyard', description: 'U-shape around courtyard', icon: '🏨', config: { floors: 5, floorHeight: 11 } },
        tower: { name: 'Tower', description: 'Vertical tower hotel', icon: '🏙️', config: { towerFloors: 12, podiumFloors: 2, floorHeight: 11, podiumHeight: 14 } },
        linear: { name: 'Linear', description: 'Linear bar building', icon: '▬', config: { floors: 6, floorHeight: 11 } },
    },
    retail: {
        lshaped: { name: 'L-Shaped', description: 'L-shaped strip center', icon: '⌐', config: { floors: 1, floorHeight: 18 } },
        ushaped: { name: 'U-Shaped', description: 'U-shaped with anchor', icon: '⊓', config: { floors: 1, floorHeight: 20, anchorHeight: 28 } },
        inline: { name: 'Inline', description: 'Straight inline strip', icon: '▬', config: { floors: 1, floorHeight: 16 } },
        podium: { name: 'Podium', description: 'Retail over podium parking', icon: '🏗️', config: { podiumFloors: 2, retailFloors: 1, floorHeight: 18, podiumHeight: 11 }, preview: { hasBase: true, baseColor: '#6b7280', towerColor: '#ec4899', baseRatio: 0.4 } },
    },
    datacenter: {
        campus: { name: 'Campus', description: 'Multi-building campus', icon: '🖥️', config: { floors: 2, floorHeight: 16 } },
        single: { name: 'Single Hall', description: 'Single data hall', icon: '📡', config: { floors: 2, floorHeight: 18 } },
        podium: { name: 'Podium', description: 'Data center over podium base', icon: '🏗️', config: { podiumFloors: 1, dataFloors: 2, floorHeight: 16, podiumHeight: 14 }, preview: { hasBase: true, baseColor: '#6b7280', towerColor: '#06b6d4', baseRatio: 0.25 } },
    },
    parking: {
        surface: {
            name: 'Surface',
            description: 'Testfit-style surface lot with dynamic fill',
            icon: '🅿️',
            config: {
                floors: 0,
                floorHeight: 0,
                // === STALL DIMENSIONS (US Standards) ===
                stallWidth: 9,           // 9' standard (8.5' compact, 11' ADA)
                stallDepth: 18,          // 18' standard (16' compact)
                compactWidth: 8.5,       // Compact stall width
                compactDepth: 16,        // Compact stall depth
                // === DRIVE AISLE ===
                aisleWidth: 24,          // 24' two-way, 12-18' one-way
                parkingAngle: 90,        // 90°, 60°, or 45°
                driveType: 'twoWay',     // 'oneWay' or 'twoWay'
                // === STALL MIX (Testfit-style) ===
                standardPct: 85,         // Standard stalls %
                compactPct: 10,          // Compact stalls %
                adaPct: 3,               // ADA accessible % (legacy - use hasAda instead)
                evPct: 2,                // EV charging %
                hasAda: true,            // Enable ADA accessible stalls (per code requirements)
                adaExtra: 0,             // Additional ADA stalls beyond code minimum (for medical, senior, etc.)
                adaPosition: 0,          // Starting stall index for ADA cluster (0 = start, -1 = end, or specific index)
                // === LANDSCAPING ===
                hasLandscaping: false,   // DEFAULT OFF - cleaner view
                landscapeInterval: 25,   // End cap every N stalls (if enabled)
                endIslands: false,       // DEFAULT OFF - end islands at row ends
                // === CIRCULATION ===
                hasEntryExit: true,      // Show entry/exit points
                entryExitType: 'standard', // 'standard', 'channelized', 'fullAccess'
                hasGateBooth: true,      // Show ticket/gate booths
                hasCrosswalk: true,      // Show pedestrian crosswalk
                hasCrossAisle: true,     // Cross-aisle spine for larger lots
                fireLane: true,          // Fire lane around perimeter
                perimeterWidth: 24,      // Fire lane/perimeter drive width
                // === DISPLAY OPTIONS ===
                showLightPoles: true,    // Show light poles in 3D view
                showStallNumbers: true,  // Show stall numbering (A-001 format)
            }
        },
        structured: { name: 'Structured', description: 'Parking structure', icon: '🏗️', config: { floors: 5, floorHeight: 11 } },
        podium: { name: 'Podium', description: 'Parking with amenity podium', icon: '🏛️', config: { podiumFloors: 1, parkingFloors: 4, floorHeight: 11, podiumHeight: 16 }, preview: { hasBase: true, baseColor: '#22c55e', towerColor: '#6b7280', baseRatio: 0.2 } },
    },
};

// ============================================================================
// UNIT MIX TEMPLATES - Testfit-style unit type configuration
// ============================================================================

const DEFAULT_UNIT_MIX = {
    multifamily: [
        { id: 'studio', name: 'Studio', targetPct: 10, sf: 500, bedrooms: 0, bathrooms: 1, rentPSF: 3.50, color: '#22c55e' },
        { id: '1br', name: '1 Bedroom', targetPct: 35, sf: 700, bedrooms: 1, bathrooms: 1, rentPSF: 3.25, color: '#3b82f6' },
        { id: '1br_den', name: '1 BR + Den', targetPct: 15, sf: 850, bedrooms: 1, bathrooms: 1, rentPSF: 3.15, color: '#6366f1' },
        { id: '2br', name: '2 Bedroom', targetPct: 25, sf: 1000, bedrooms: 2, bathrooms: 2, rentPSF: 3.00, color: '#8b5cf6' },
        { id: '2br_den', name: '2 BR + Den', targetPct: 10, sf: 1150, bedrooms: 2, bathrooms: 2, rentPSF: 2.90, color: '#a855f7' },
        { id: '3br', name: '3 Bedroom', targetPct: 5, sf: 1350, bedrooms: 3, bathrooms: 2, rentPSF: 2.75, color: '#d946ef' },
    ],
    hotel: [
        { id: 'king', name: 'Standard King', targetPct: 40, sf: 325, beds: 1, rentPerNight: 159, color: '#3b82f6' },
        { id: 'double_queen', name: 'Double Queen', targetPct: 35, sf: 375, beds: 2, rentPerNight: 179, color: '#6366f1' },
        { id: 'junior_suite', name: 'Junior Suite', targetPct: 15, sf: 475, beds: 1, rentPerNight: 229, color: '#8b5cf6' },
        { id: 'suite', name: 'Suite', targetPct: 8, sf: 650, beds: 1, rentPerNight: 349, color: '#a855f7' },
        { id: 'penthouse', name: 'Penthouse Suite', targetPct: 2, sf: 1200, beds: 2, rentPerNight: 599, color: '#d946ef' },
    ],
    office: [
        { id: 'open', name: 'Open Office', targetPct: 55, sfPerPerson: 150, color: '#3b82f6' },
        { id: 'private', name: 'Private Office', targetPct: 15, sfPerPerson: 200, color: '#6366f1' },
        { id: 'conference', name: 'Conference Room', targetPct: 10, sfPerPerson: 25, capacity: 12, color: '#8b5cf6' },
        { id: 'huddle', name: 'Huddle Room', targetPct: 8, sfPerPerson: 30, capacity: 4, color: '#a855f7' },
        { id: 'amenity', name: 'Amenity Space', targetPct: 12, sfPerPerson: 50, color: '#22c55e' },
    ],
    singlefamily: [
        { id: 'small', name: 'Small (2BR)', targetPct: 20, sf: 1400, bedrooms: 2, bathrooms: 2, price: 350000, color: '#22c55e' },
        { id: 'medium', name: 'Medium (3BR)', targetPct: 45, sf: 1800, bedrooms: 3, bathrooms: 2.5, price: 450000, color: '#3b82f6' },
        { id: 'large', name: 'Large (4BR)', targetPct: 25, sf: 2400, bedrooms: 4, bathrooms: 3, price: 575000, color: '#8b5cf6' },
        { id: 'xlarge', name: 'XL (5BR)', targetPct: 10, sf: 3200, bedrooms: 5, bathrooms: 4, price: 750000, color: '#d946ef' },
    ],
    industrial: [
        { id: 'warehouse', name: 'Warehouse', targetPct: 70, clearHeight: 32, rentPSF: 0.85, color: '#6b7280' },
        { id: 'office', name: 'Office/Admin', targetPct: 15, clearHeight: 10, rentPSF: 1.50, color: '#3b82f6' },
        { id: 'mezzanine', name: 'Mezzanine', targetPct: 10, clearHeight: 12, rentPSF: 1.25, color: '#8b5cf6' },
        { id: 'dock', name: 'Dock High', targetPct: 5, clearHeight: 10, rentPSF: 0.95, color: '#22c55e' },
    ],
    retail: [
        { id: 'anchor', name: 'Anchor Tenant', targetPct: 40, sf: 45000, rentPSF: 12, color: '#ef4444' },
        { id: 'junior_anchor', name: 'Junior Anchor', targetPct: 20, sf: 15000, rentPSF: 18, color: '#f97316' },
        { id: 'inline', name: 'Inline Retail', targetPct: 25, sf: 3000, rentPSF: 28, color: '#3b82f6' },
        { id: 'small_shop', name: 'Small Shop', targetPct: 10, sf: 1200, rentPSF: 35, color: '#8b5cf6' },
        { id: 'pad', name: 'Outparcel/Pad', targetPct: 5, sf: 4000, rentPSF: 40, color: '#22c55e' },
    ],
};

const ZONING_PRESETS = {
    R1: { name: 'R-1 Low Density', far: 0.5, height: 35, coverage: 0.4, parkingRatio: 2.0 },
    R2: { name: 'R-2 Medium Density', far: 1.0, height: 45, coverage: 0.5, parkingRatio: 1.5 },
    R3: { name: 'R-3 High Density', far: 2.0, height: 65, coverage: 0.6, parkingRatio: 1.25 },
    R4: { name: 'R-4 Urban', far: 3.0, height: 85, coverage: 0.7, parkingRatio: 1.0 },
    MX: { name: 'Mixed Use', far: 2.5, height: 75, coverage: 0.65, parkingRatio: 1.0 },
    C1: { name: 'Commercial', far: 2.0, height: 55, coverage: 0.6, parkingRatio: 3.0 },
};

const SETBACK_PRESETS = {
    urban: { front: 0, side: 0, rear: 10, name: 'Urban (0/0/10)' },
    suburban: { front: 20, side: 10, rear: 15, name: 'Suburban (20/10/15)' },
    rural: { front: 30, side: 15, rear: 20, name: 'Rural (30/15/20)' },
    custom: { front: 10, side: 5, rear: 10, name: 'Custom' },
};

// ============================================================================
// VEHICLE TYPES - Standard dimensions for swept path analysis
// ============================================================================

const VEHICLE_TYPES = {
    passengerCar: {
        name: 'Passenger Car',
        icon: '🚗',
        length: 17,           // 17 ft (AASHTO P design vehicle)
        width: 6.5,           // 6.5 ft
        wheelbase: 10.8,      // 10.8 ft
        frontOverhang: 3,     // 3 ft
        rearOverhang: 3.2,    // 3.2 ft
        minTurningRadius: 18, // 18 ft (outside front wheel)
        color: '#3b82f6',     // Blue
    },
    suv: {
        name: 'SUV / Pickup',
        icon: '🚙',
        length: 19,           // 19 ft
        width: 7,             // 7 ft
        wheelbase: 12,        // 12 ft
        frontOverhang: 3.5,   // 3.5 ft
        rearOverhang: 3.5,    // 3.5 ft
        minTurningRadius: 22, // 22 ft
        color: '#22c55e',     // Green
    },
    deliveryTruck: {
        name: 'Delivery Truck (SU-30)',
        icon: '🚚',
        length: 30,           // 30 ft (AASHTO SU-30)
        width: 8,             // 8 ft
        wheelbase: 20,        // 20 ft
        frontOverhang: 4,     // 4 ft
        rearOverhang: 6,      // 6 ft
        minTurningRadius: 42, // 42 ft
        color: '#f59e0b',     // Orange
    },
    fireTruck: {
        name: 'Fire Truck',
        icon: '🚒',
        length: 35,           // 35 ft
        width: 8.5,           // 8.5 ft
        wheelbase: 20,        // 20 ft
        frontOverhang: 6,     // 6 ft
        rearOverhang: 9,      // 9 ft
        minTurningRadius: 25, // 25 ft (inside)
        color: '#ef4444',     // Red
    },
    ambulance: {
        name: 'Ambulance',
        icon: '🚑',
        length: 22,           // 22 ft
        width: 7.5,           // 7.5 ft
        wheelbase: 14,        // 14 ft
        frontOverhang: 3.5,   // 3.5 ft
        rearOverhang: 4.5,    // 4.5 ft
        minTurningRadius: 28, // 28 ft
        color: '#ffffff',     // White
    },
    bus: {
        name: 'Bus (BUS-40)',
        icon: '🚌',
        length: 40,           // 40 ft (AASHTO BUS)
        width: 8.5,           // 8.5 ft
        wheelbase: 25,        // 25 ft
        frontOverhang: 6,     // 6 ft
        rearOverhang: 9,      // 9 ft
        minTurningRadius: 42, // 42 ft
        color: '#8b5cf6',     // Purple
    },
    semiTrailer: {
        name: 'Semi-Trailer (WB-40)',
        icon: '🚛',
        length: 45,           // 45 ft overall
        width: 8.5,           // 8.5 ft
        wheelbase: 40,        // 40 ft (kingpin to rear axle)
        frontOverhang: 3,     // 3 ft
        rearOverhang: 2,      // 2 ft
        minTurningRadius: 40, // 40 ft (inside)
        color: '#6b7280',     // Gray
    },
};

// ============================================================================
// MASSING PREVIEW COMPONENT - Isometric 3D visualization
// ============================================================================

function MassingPreview({ massing }) {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !massing?.preview) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        // Clear
        ctx.fillStyle = '#0a0a1a';
        ctx.fillRect(0, 0, w, h);

        // Isometric projection helpers
        const isoX = (x, y) => w / 2 + (x - y) * 0.866;
        const isoY = (x, y, z) => h * 0.75 + (x + y) * 0.5 - z;

        // Draw isometric box with color
        const drawBox = (x, y, z, bw, bd, bh, color, outlineColor = '#000') => {
            // Top face
            ctx.beginPath();
            ctx.moveTo(isoX(x, y), isoY(x, y, z + bh));
            ctx.lineTo(isoX(x + bw, y), isoY(x + bw, y, z + bh));
            ctx.lineTo(isoX(x + bw, y + bd), isoY(x + bw, y + bd, z + bh));
            ctx.lineTo(isoX(x, y + bd), isoY(x, y + bd, z + bh));
            ctx.closePath();
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = outlineColor;
            ctx.lineWidth = 1;
            ctx.stroke();

            // Right face
            ctx.beginPath();
            ctx.moveTo(isoX(x + bw, y), isoY(x + bw, y, z));
            ctx.lineTo(isoX(x + bw, y), isoY(x + bw, y, z + bh));
            ctx.lineTo(isoX(x + bw, y + bd), isoY(x + bw, y + bd, z + bh));
            ctx.lineTo(isoX(x + bw, y + bd), isoY(x + bw, y + bd, z));
            ctx.closePath();
            ctx.fillStyle = shadeColor(color, -20);
            ctx.fill();
            ctx.stroke();

            // Left face
            ctx.beginPath();
            ctx.moveTo(isoX(x, y + bd), isoY(x, y + bd, z));
            ctx.lineTo(isoX(x, y + bd), isoY(x, y + bd, z + bh));
            ctx.lineTo(isoX(x + bw, y + bd), isoY(x + bw, y + bd, z + bh));
            ctx.lineTo(isoX(x + bw, y + bd), isoY(x + bw, y + bd, z));
            ctx.closePath();
            ctx.fillStyle = shadeColor(color, -40);
            ctx.fill();
            ctx.stroke();
        };

        const shadeColor = (color, percent) => {
            const num = parseInt(color.replace('#', ''), 16);
            const amt = Math.round(2.55 * percent);
            const R = Math.min(255, Math.max(0, (num >> 16) + amt));
            const G = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amt));
            const B = Math.min(255, Math.max(0, (num & 0x0000FF) + amt));
            return '#' + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
        };

        const p = massing.preview;

        // Base size for drawings
        const baseW = 40, baseD = 30;

        if (p.hasBase) {
            // Podium: base + tower
            drawBox(-baseW / 2, -baseD / 2, 0, baseW, baseD, 10, p.baseColor || '#6b7280');
            const towerW = baseW * 0.7, towerD = baseD * 0.7;
            drawBox(-towerW / 2, -towerD / 2, 10, towerW, towerD, 25, p.towerColor || '#8b5cf6');
        } else if (p.hasCore) {
            // Wrap: core garage + wrap building
            const coreW = baseW * 0.5, coreD = baseD * 0.5;
            drawBox(-coreW / 2, -coreD / 2, 0, coreW, coreD, 20, p.coreColor || '#6b7280');
            // Wrap on three sides
            drawBox(-baseW / 2, -baseD / 2, 0, baseW * 0.2, baseD, 25, p.wrapColor || '#8b5cf6');
            drawBox(baseW / 2 - baseW * 0.2, -baseD / 2, 0, baseW * 0.2, baseD, 25, p.wrapColor || '#8b5cf6');
            drawBox(-baseW / 2, baseD / 2 - baseD * 0.25, 0, baseW, baseD * 0.25, 25, p.wrapColor || '#8b5cf6');
        } else if (p.hasTower) {
            // Tower: podium + tall tower
            drawBox(-baseW / 2, -baseD / 2, 0, baseW, baseD, 12, p.podiumColor || '#6b7280');
            const towerW = baseW * 0.4, towerD = baseD * 0.4;
            drawBox(-towerW / 2, -towerD / 2, 12, towerW, towerD, 40, p.towerColor || '#8b5cf6');
        } else if (p.isRows) {
            // Townhomes: multiple row buildings
            for (let i = 0; i < 3; i++) {
                drawBox(-baseW / 2, -baseD / 2 + i * 14, 0, baseW, 8, 15, p.rowColor || '#8b5cf6');
            }
        } else if (p.isScattered) {
            // Garden: scattered buildings with parking
            drawBox(-baseW / 2, -baseD / 2, 0, baseW, baseD, 2, p.parkingColor || '#fbbf24'); // parking
            drawBox(-baseW / 2 + 5, -baseD / 2 + 5, 2, 12, 10, 15, p.buildingColor || '#8b5cf6');
            drawBox(baseW / 2 - 17, -baseD / 2 + 5, 2, 12, 10, 15, p.buildingColor || '#8b5cf6');
            drawBox(-baseW / 2 + 5, baseD / 2 - 15, 2, 12, 10, 15, p.buildingColor || '#8b5cf6');
            drawBox(baseW / 2 - 17, baseD / 2 - 15, 2, 12, 10, 15, p.buildingColor || '#8b5cf6');
        } else if (p.isLShape) {
            // Gurban: L-shaped building
            drawBox(-baseW / 2, -baseD / 2, 0, baseW * 0.6, baseD, 2, p.parkingColor || '#fbbf24');
            drawBox(-baseW / 2, -baseD / 2, 2, baseW * 0.3, baseD, 20, p.buildingColor || '#8b5cf6');
            drawBox(-baseW / 2, -baseD / 2, 2, baseW, baseD * 0.35, 20, p.buildingColor || '#8b5cf6');
        } else {
            // Default: simple box
            drawBox(-baseW / 2, -baseD / 2, 0, baseW, baseD, 20, '#8b5cf6');
        }

    }, [massing]);

    return (
        <canvas
            ref={canvasRef}
            width={200}
            height={96}
            className="w-full h-full"
        />
    );
}

export default function SiteGen() {
    // Canvas state
    const canvasRef = useRef(null);
    const canvasContainerRef = useRef(null);
    const viewer3DRef = useRef(null);
    const [zoom3DLevel, setZoom3DLevel] = useState(100); // 3D view zoom percentage
    const [canvasSize, setCanvasSize] = useState({ width: 1400, height: 900 });
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const templateBuildings2DRef = useRef([]); // For 2D template building click detection
    const [templateBuildingsList, setTemplateBuildingsList] = useState([]); // For UI rendering
    const [boundary, setBoundary] = useState([]);
    const [isDrawing, setIsDrawing] = useState(false);
    const [drawMode, setDrawMode] = useState('boundary'); // 'boundary' | 'exclusion'
    const [exclusions, setExclusions] = useState([]);
    const [currentExclusion, setCurrentExclusion] = useState([]);

    // Undo/Redo history
    const [undoStack, setUndoStack] = useState([]);
    const [redoStack, setRedoStack] = useState([]);
    const isUndoRedoAction = useRef(false); // Flag to prevent saving during undo/redo

    // Boundary editing state
    const [isEditingBoundary, setIsEditingBoundary] = useState(false);
    const [draggingBoundaryVertex, setDraggingBoundaryVertex] = useState(null); // index of vertex being dragged
    const [draggingBoundaryEdge, setDraggingBoundaryEdge] = useState(null); // index of edge being dragged
    const [edgeDragStart, setEdgeDragStart] = useState(null); // { mouseX, mouseY, vertices: [{x,y}, {x,y}] }
    const [hoveredBoundaryVertex, setHoveredBoundaryVertex] = useState(null); // for visual feedback
    const [hoveredBoundaryEdge, setHoveredBoundaryEdge] = useState(null); // for edge hover visual feedback

    // Precision editing state (Rhino-like controls)
    const [coordDisplay2D, setCoordDisplay2D] = useState(null); // { x, y, screenX, screenY } for overlay
    const [editingVertex2D, setEditingVertex2D] = useState(null); // { index, x, y } for precise input dialog
    const vertexDragStart2DRef = useRef(null); // Starting position for ortho mode

    // Template building drag state for 2D
    const [draggingTemplateBuilding2D, setDraggingTemplateBuilding2D] = useState(null); // index of template building being dragged
    const [dragOffset2D, setDragOffset2D] = useState({ x: 0, y: 0 }); // offset from building center to mouse on drag start

    // Snapping settings (Testfit-style)
    const [snapEnabled, setSnapEnabled] = useState(true);
    const [snapToGrid, setSnapToGrid] = useState(true);
    const [snapToObjects, setSnapToObjects] = useState(true);
    const [snapToAngles, setSnapToAngles] = useState(true);
    const [orthoMode, setOrthoMode] = useState(false); // 90° only snapping (like CAD ortho)
    const [gridSize, setGridSize] = useState(10); // 10ft grid

    // Floating panels
    const [buildingsPanelCollapsed, setBuildingsPanelCollapsed] = useState(false);

    // Edit mode (Testfit-style modes)
    const [editMode, setEditMode] = useState('draw'); // 'select' | 'draw' | 'pan' - default to draw

    // Building Type
    const [buildingType, setBuildingType] = useState('multifamily');
    const [buildingSubtype, setBuildingSubtype] = useState('midrise');
    const [massingType, setMassingType] = useState('podium');

    // Editable massing parameters - allows user to customize after selecting massing type
    const [massingParams, setMassingParams] = useState({});
    const [showParamsPanel, setShowParamsPanel] = useState(true);

    // Individual building overrides - allows each building in multi-building layouts to have different heights
    // Format: { buildingIndex: { floors: 5 }, ... } or { buildingIndex: { clearHeight: 40 }, ... }
    const [individualBuildingParams, setIndividualBuildingParams] = useState({});

    // Template building positions - allows moving template buildings in multi-building layouts
    // Format: { buildingIndex: { x: 100, z: 200 }, ... }
    const [templateBuildingPositions, setTemplateBuildingPositions] = useState({});
    const [selectedTemplateBuilding, setSelectedTemplateBuilding] = useState(null);

    // Amenity positions - allows moving amenities (pools, gardens, courtyards) in layouts
    // Format: { amenityId: { x: 100, z: 200 }, ... } where amenityId is like 'pool', 'garden', 'courtyard'
    const [amenityPositions, setAmenityPositions] = useState({});
    const [selectedAmenity, setSelectedAmenity] = useState(null);
    const [draggingAmenity, setDraggingAmenity] = useState(null);
    const [amenityDragOffset, setAmenityDragOffset] = useState({ x: 0, y: 0 });
    const amenities2DRef = useRef([]);

    // === VEHICLE TRACKING / SWEPT PATH ANALYSIS ===
    // Vehicles placed on the site for circulation testing
    // Format: [{ id, type, x, y, rotation, trail: [{x, y, rotation}] }, ...]
    const [vehicles, setVehicles] = useState([]);
    const [selectedVehicle, setSelectedVehicle] = useState(null); // vehicle id
    const [draggingVehicle, setDraggingVehicle] = useState(null); // vehicle id being dragged
    const [vehicleDragOffset, setVehicleDragOffset] = useState({ x: 0, y: 0 });
    const [showVehiclePanel, setShowVehiclePanel] = useState(false); // Toggle vehicle tool panel
    const [vehicleTrailsVisible, setVehicleTrailsVisible] = useState(true); // Show movement trails
    const [vehicleTurningRadiusVisible, setVehicleTurningRadiusVisible] = useState(true); // Show turning radius
    const [vehicleAutoDrive, setVehicleAutoDrive] = useState(false); // Auto-drive animation
    const [vehicleSpeed, setVehicleSpeed] = useState(2); // Speed: 1-5 (feet per frame)
    const [vehiclePathProgress, setVehiclePathProgress] = useState(0); // Progress along circulation path (0-1)

    // === ADA PLACEMENT MODE ===
    const [isPlacingAda, setIsPlacingAda] = useState(false); // Click-to-place ADA cluster mode
    const [adaHoverIndex, setAdaHoverIndex] = useState(null); // Hover preview for ADA stall index
    const [adaHoverRow, setAdaHoverRow] = useState(null); // Hover preview for ADA row
    const parkingLayoutRef = useRef(null); // Store all row geometries for click detection

    // === CROSS-AISLE SPINE PLACEMENT ===
    const [crossAisleMode, setCrossAisleMode] = useState('auto'); // 'auto', 'manual', 'force', 'draw'
    const [manualSpines, setManualSpines] = useState([]); // [{x: number, fromY: number, toY: number}]
    const [isPlacingSpine, setIsPlacingSpine] = useState(false); // Click-to-place spine mode
    const [spineHoverX, setSpineHoverX] = useState(null); // Hover preview X position

    // === CUSTOM DRIVE AISLE DRAWING ===
    const [drawnAisles, setDrawnAisles] = useState([]); // [{points: [{x,y},...], id: number}]
    const [isDrawingAisle, setIsDrawingAisle] = useState(false); // Currently drawing an aisle
    const [currentAislePoints, setCurrentAislePoints] = useState([]); // Points of aisle being drawn
    const [aisleHoverPoint, setAisleHoverPoint] = useState(null); // Hover preview point

    // === AISLE EDITING MODE ===
    const [isEditingAisles, setIsEditingAisles] = useState(false); // Edit mode for aisles
    const [hoveredAislePoint, setHoveredAislePoint] = useState(null); // {aisleId, pointIndex} or {junctionId} for junctions
    const [draggingAislePoint, setDraggingAislePoint] = useState(null); // {aisleId, pointIndex} or {junctionId}
    const [aisleJunctions, setAisleJunctions] = useState([]); // [{id, x, y, connections: [{aisleId, pointIndex},...]}]
    const [aisleEditHistory, setAisleEditHistory] = useState([]); // Undo history stack
    const [aisleBackup, setAisleBackup] = useState(null); // Backup before editing started (for cancel)
    const [aisleContextMenu, setAisleContextMenu] = useState(null); // {x, y, screenX, screenY, type, data}

    const vehicles2DRef = useRef([]); // For click detection
    const nextVehicleId = useRef(1);
    const vehicleAnimationRef = useRef(null); // Animation frame ref

    // Add a vehicle to the site
    const addVehicle = useCallback((type) => {
        const vehicleSpec = VEHICLE_TYPES[type];
        if (!vehicleSpec) return;

        // Place vehicle in the center of the lot boundary (not canvas)
        let centerX, centerY;
        if (boundary && boundary.length >= 3) {
            const minX = Math.min(...boundary.map(p => p.x));
            const maxX = Math.max(...boundary.map(p => p.x));
            const minY = Math.min(...boundary.map(p => p.y));
            const maxY = Math.max(...boundary.map(p => p.y));
            centerX = (minX + maxX) / 2;
            centerY = (minY + maxY) / 2;
        } else {
            // Fallback to canvas center
            centerX = canvasSize.width / 2 / SCALE;
            centerY = canvasSize.height / 2 / SCALE;
        }

        const newVehicle = {
            id: nextVehicleId.current++,
            type: type,
            x: centerX,
            y: centerY,
            rotation: 0, // degrees, 0 = pointing right (east)
            trail: [], // Movement history: [{x, y, rotation}, ...]
        };

        setVehicles(prev => [...prev, newVehicle]);
        setSelectedVehicle(newVehicle.id);
    }, [canvasSize, boundary]);

    // Remove selected vehicle
    const removeVehicle = useCallback((vehicleId) => {
        setVehicles(prev => prev.filter(v => v.id !== vehicleId));
        if (selectedVehicle === vehicleId) {
            setSelectedVehicle(null);
        }
    }, [selectedVehicle]);

    // Clear all vehicle trails
    const clearAllTrails = useCallback(() => {
        setVehicles(prev => prev.map(v => ({ ...v, trail: [] })));
    }, []);

    // Rotate selected vehicle
    const rotateVehicle = useCallback((vehicleId, deltaAngle) => {
        setVehicles(prev => prev.map(v => {
            if (v.id === vehicleId) {
                return { ...v, rotation: (v.rotation + deltaAngle) % 360 };
            }
            return v;
        }));
    }, []);

    // Move vehicle forward/backward (in direction it's facing)
    const moveVehicle = useCallback((vehicleId, distance) => {
        setVehicles(prev => prev.map(v => {
            if (v.id === vehicleId) {
                const rotRad = (v.rotation * Math.PI) / 180;
                const dx = Math.cos(rotRad) * distance;
                const dy = Math.sin(rotRad) * distance;
                // Add current position to trail before moving
                const newTrail = [...v.trail, { x: v.x, y: v.y, rotation: v.rotation }];
                // Limit trail length to prevent memory issues
                if (newTrail.length > 500) newTrail.shift();
                return {
                    ...v,
                    x: v.x + dx,
                    y: v.y + dy,
                    trail: newTrail
                };
            }
            return v;
        }));
    }, []);

    // Steer vehicle (turn while moving)
    const steerVehicle = useCallback((vehicleId, steerAngle, distance) => {
        setVehicles(prev => prev.map(v => {
            if (v.id === vehicleId) {
                const spec = VEHICLE_TYPES[v.type];
                // Calculate turn radius based on steer angle
                // Ackermann steering: R = wheelbase / tan(steerAngle)
                const steerRad = (steerAngle * Math.PI) / 180;
                let turnRadius = Infinity;
                if (Math.abs(steerRad) > 0.01) {
                    turnRadius = spec.wheelbase / Math.tan(Math.abs(steerRad));
                    // Clamp to minimum turning radius
                    turnRadius = Math.max(turnRadius, spec.minTurningRadius);
                }

                // Calculate arc movement
                const rotRad = (v.rotation * Math.PI) / 180;
                let newX, newY, newRotation;

                if (turnRadius === Infinity || turnRadius > 1000) {
                    // Straight movement
                    newX = v.x + Math.cos(rotRad) * distance;
                    newY = v.y + Math.sin(rotRad) * distance;
                    newRotation = v.rotation;
                } else {
                    // Arc movement
                    const arcAngle = distance / turnRadius; // radians
                    const turnDir = steerAngle > 0 ? 1 : -1;

                    // Center of turn circle
                    const cx = v.x - turnDir * Math.sin(rotRad) * turnRadius;
                    const cy = v.y + turnDir * Math.cos(rotRad) * turnRadius;

                    // New position on arc
                    const newAngle = rotRad + turnDir * arcAngle;
                    newX = cx + turnDir * Math.sin(newAngle) * turnRadius;
                    newY = cy - turnDir * Math.cos(newAngle) * turnRadius;
                    newRotation = (v.rotation + turnDir * arcAngle * 180 / Math.PI) % 360;
                }

                // Add current position to trail
                const newTrail = [...v.trail, { x: v.x, y: v.y, rotation: v.rotation }];
                if (newTrail.length > 500) newTrail.shift();

                return {
                    ...v,
                    x: newX,
                    y: newY,
                    rotation: newRotation,
                    trail: newTrail
                };
            }
            return v;
        }));
    }, []);

    // Keyboard controls for vehicle
    useEffect(() => {
        if (!selectedVehicle || !showVehiclePanel) return;

        const handleKeyDown = (e) => {
            // Only handle if vehicle panel is open and we have a selected vehicle
            if (!showVehiclePanel || !selectedVehicle) return;

            const speed = vehicleSpeed;
            const turnAngle = 5; // degrees per key press

            switch (e.key) {
                case 'ArrowUp':
                case 'w':
                case 'W':
                    e.preventDefault();
                    moveVehicle(selectedVehicle, speed);
                    break;
                case 'ArrowDown':
                case 's':
                case 'S':
                    e.preventDefault();
                    moveVehicle(selectedVehicle, -speed);
                    break;
                case 'ArrowLeft':
                case 'a':
                case 'A':
                    e.preventDefault();
                    // Turn left while moving slightly forward
                    steerVehicle(selectedVehicle, -25, speed * 0.5);
                    break;
                case 'ArrowRight':
                case 'd':
                case 'D':
                    e.preventDefault();
                    // Turn right while moving slightly forward
                    steerVehicle(selectedVehicle, 25, speed * 0.5);
                    break;
                case 'q':
                case 'Q':
                    e.preventDefault();
                    rotateVehicle(selectedVehicle, -5);
                    break;
                case 'e':
                case 'E':
                    e.preventDefault();
                    rotateVehicle(selectedVehicle, 5);
                    break;
                case ' ':
                    e.preventDefault();
                    setVehicleAutoDrive(prev => !prev);
                    break;
                case 'c':
                case 'C':
                    e.preventDefault();
                    clearAllTrails();
                    break;
                default:
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedVehicle, showVehiclePanel, vehicleSpeed, moveVehicle, steerVehicle, rotateVehicle, clearAllTrails]);

    // Place vehicle at entry point
    const placeVehicleAtEntry = useCallback((vehicleId) => {
        // Find the entry point based on current parking layout
        // Entry is at the bottom center of the lot, rotated to face into the lot
        setVehicles(prev => prev.map(v => {
            if (v.id === vehicleId) {
                // Get boundary - use the state variable
                if (!boundary || boundary.length < 3) return v;

                // Find bottom-most point
                let bottomY = -Infinity;
                let bottomX = 0;
                boundary.forEach(p => {
                    if (p.y > bottomY) {
                        bottomY = p.y;
                        bottomX = p.x;
                    }
                });

                // Calculate center X
                const minX = Math.min(...boundary.map(p => p.x));
                const maxX = Math.max(...boundary.map(p => p.x));
                const centerX = (minX + maxX) / 2;

                return {
                    ...v,
                    x: centerX,
                    y: bottomY + 20, // Just outside the lot
                    rotation: -90, // Facing up (into the lot)
                    trail: []
                };
            }
            return v;
        }));
    }, [boundary]);
    // Reset individual building params and positions when massing type changes
    useEffect(() => {
        setIndividualBuildingParams({});
        setTemplateBuildingPositions({});
        setSelectedTemplateBuilding(null);
        setAmenityPositions({});
        setSelectedAmenity(null);
        setDraggingAmenity(null);
        setAmenityDragOffset({ x: 0, y: 0 });
    }, [massingType, buildingType]);

    // Free-form building placement
    const [customBuildings, setCustomBuildings] = useState([]);
    const [selectedBuildingId, setSelectedBuildingId] = useState(null); // Smart selection
    const [isDrawingShape, setIsDrawingShape] = useState(false); // Shift+click drawing mode
    const [newBuildingConfig, setNewBuildingConfig] = useState({
        width: 60,
        depth: 80,
        floors: 4,
        floorHeight: 10,
        color: 'multifamily'
    });
    // Polygon drawing state
    const [drawingPolygon, setDrawingPolygon] = useState([]); // Points being drawn
    const [polygonBuildingConfig, setPolygonBuildingConfig] = useState({
        floors: 4,
        floorHeight: 10,
        color: 'multifamily'
    });

    // Zoning constraints
    const [zoningPreset, setZoningPreset] = useState('R2');
    const [far, setFar] = useState(1.0);
    const [heightLimit, setHeightLimit] = useState(45);
    const [lotCoverage, setLotCoverage] = useState(0.5);
    const [parkingRatio, setParkingRatio] = useState(1.5);

    // Setbacks
    const [setbackPreset, setSetbackPreset] = useState('suburban');
    const [setbacks, setSetbacks] = useState({ front: 20, side: 10, rear: 15 });

    // Unit Mix (Testfit-style)
    const [unitMix, setUnitMix] = useState(() => {
        // Initialize with default mix for multifamily
        return JSON.parse(JSON.stringify(DEFAULT_UNIT_MIX.multifamily || []));
    });
    const [showUnitMixPanel, setShowUnitMixPanel] = useState(false);

    // Update unit mix when building type changes
    useEffect(() => {
        const defaultMix = DEFAULT_UNIT_MIX[buildingType];
        if (defaultMix) {
            setUnitMix(JSON.parse(JSON.stringify(defaultMix)));
        } else {
            setUnitMix([]);
        }
    }, [buildingType]);

    // Get current building config
    const currentBuildingType = BUILDING_TYPES[buildingType];
    const currentSubtype = currentBuildingType?.subtypes[buildingSubtype] || Object.values(currentBuildingType?.subtypes || {})[0];
    const currentMassings = MASSING_TYPOLOGIES[buildingType] || {};
    const currentMassing = currentMassings[massingType] || Object.values(currentMassings)[0];

    // Effective massing config = user edited params merged with defaults
    const effectiveMassingConfig = {
        ...(currentMassing?.config || {}),
        ...massingParams
    };

    // === SHARED PARKING LAYOUT CALCULATION ===
    // Calculate once, used by both 2D and 3D views for consistency (like Rhino viewports)
    // Supports both rectangular and irregular polygon boundaries
    const parkingLayout = useMemo(() => {
        // Note: massingType is 'surface' for surface parking (not 'surfaceParking')
        if (massingType !== 'surface' || buildingType !== 'parking' || !boundary || boundary.length < 3) {
            return null;
        }

        // === POLYGON-BASED LAYOUT ===
        // Works with any polygon shape, not just rectangles

        // Get boundary bounds (for fallback and reference)
        const bounds = polygonBounds(boundary);
        const { minX, maxX, minY, maxY, width: siteW, height: siteD } = bounds;

        // Get config values
        const stallWidth = effectiveMassingConfig.stallWidth || 9;
        const stallDepth = effectiveMassingConfig.stallDepth || 18;
        const aisleWidth = effectiveMassingConfig.aisleWidth || 24;
        const driveType = effectiveMassingConfig.driveType || 'twoWay';
        const parkingAngle = effectiveMassingConfig.parkingAngle || 90;

        // === ANGLED PARKING GEOMETRY ===
        // Get angle-specific dimensions for 45°, 60°, or 90° parking
        const angledGeometry = getAngledParkingGeometry(parkingAngle, stallWidth, stallDepth, driveType);
        const {
            stallModuleWidth,      // Width each stall takes along the aisle
            stallDepthProjection,  // Depth perpendicular to aisle
            recommendedAisleWidth, // Optimal aisle width for this angle
            getStallCorners        // Function to get parallelogram corners
        } = angledGeometry;

        // Layout calculations - use angle-adjusted dimensions
        const loopWidth = aisleWidth; // Perimeter loop width stays the same
        const loopInset = 2;
        // Use recommended aisle width for angled parking, or configured width for 90°
        const effectiveAisleWidth = parkingAngle === 90
            ? (driveType === 'hybrid' ? 20 : aisleWidth)
            : recommendedAisleWidth;

        // === POLYGON INSETS ===
        // Create actual polygon shapes instead of bounding boxes

        // 1. Setback polygon (boundary inset by setback distance)
        const avgSetback = (setbacks.front + setbacks.side + setbacks.rear) / 3;
        const setbackPolygon = offsetPolygon(boundary, avgSetback);

        // 2. Loop outer polygon (setback + loop inset)
        const loopOuterPolygon = offsetPolygon(boundary, avgSetback + loopInset);

        // 3. Loop inner polygon (creates the perimeter loop ring)
        const loopInnerPolygon = offsetPolygon(boundary, avgSetback + loopInset + loopWidth);

        // 4. Interior parking polygon (where stalls go)
        const interiorPolygon = loopInnerPolygon;

        // Get interior bounds for module calculations
        const interiorBounds = polygonBounds(interiorPolygon);

        // Buildable area bounds (for backward compatibility)
        const setbackX = minX + setbacks.side;
        const setbackY = minY + setbacks.front;
        const buildableW = siteW - setbacks.side * 2;
        const buildableD = siteD - setbacks.front - setbacks.rear;

        // Interior dimensions from polygon bounds
        const loopInnerX = interiorBounds.minX;
        const loopInnerY = interiorBounds.minY;
        const loopInnerW = interiorBounds.width;
        const loopInnerH = interiorBounds.height;

        // Module calculations (double-loaded = 2 stall rows + 1 aisle)
        // For angled parking, use projected depths instead of actual depths
        const effectiveStallDepth = parkingAngle === 90 ? stallDepth : stallDepthProjection;
        const effectiveStallModuleWidth = parkingAngle === 90 ? stallWidth : stallModuleWidth;

        const moduleDepth = effectiveStallDepth * 2 + effectiveAisleWidth;
        const numModules = Math.floor(loopInnerH / moduleDepth);
        const stallsPerRow = Math.floor(loopInnerW / effectiveStallModuleWidth);

        // Remaining space for end row
        const moduleGridDepth = numModules * moduleDepth;
        const remainingD = loopInnerH - moduleGridDepth;
        const endRowFits = remainingD >= effectiveStallDepth + 2;

        // Perimeter loop bounds (for backward compatibility)
        const loopOuterBounds = polygonBounds(loopOuterPolygon);
        const loopOX = loopOuterBounds.minX;
        const loopOY = loopOuterBounds.minY;
        const loopTotalW = loopOuterBounds.width;
        const loopTotalD = loopOuterBounds.height;

        // Detect if lot is irregular (not a simple rectangle)
        const isIrregular = boundary.length > 4 || (() => {
            if (boundary.length !== 4) return true;
            // Check if angles are approximately 90 degrees
            for (let i = 0; i < 4; i++) {
                const prev = boundary[(i + 3) % 4];
                const curr = boundary[i];
                const next = boundary[(i + 1) % 4];
                const dx1 = curr.x - prev.x, dy1 = curr.y - prev.y;
                const dx2 = next.x - curr.x, dy2 = next.y - curr.y;
                const dot = dx1 * dx2 + dy1 * dy2;
                const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);
                const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
                const cosAngle = Math.abs(dot / (len1 * len2 + 0.001));
                if (cosAngle > 0.1) return true; // Not perpendicular
            }
            return false;
        })();

        // Find optimal stall orientation (align to longest edge)
        const longestEdge = findLongestEdge(interiorPolygon);

        // Calculate actual stall count by checking which stalls fit inside the polygon
        // This is more accurate for irregular shapes
        let validStallCount = 0;
        const stallPositions = [];

        // Helper to validate stall position for irregular shapes
        // Must pass ALL checks: center in inner, center in outer, corners in inner
        // Now supports angled stalls by checking parallelogram corners
        const isStallValid = (x, y, w, h, facingUp = true) => {
            if (parkingAngle !== 90) {
                // For angled parking, get the actual stall corners (parallelogram)
                const stallCorners = getStallCorners(x, y, facingUp);
                const center = getAngledStallCenter(stallCorners);

                // Center must be inside interior polygon
                if (!isPointInPolygon(center, interiorPolygon)) return false;

                // All corners must be inside interior polygon
                if (!isAngledStallInPolygon(stallCorners, interiorPolygon)) return false;

                return true;
            }

            // 90° parking - use rectangle check
            if (!isIrregular) {
                return isRectInPolygon(x, y, w, h, interiorPolygon);
            }
            // For irregular shapes, use stricter validation
            const centerX = x + w / 2;
            const centerY = y + h / 2;
            const centerPoint = { x: centerX, y: centerY };

            // Center must be inside inner polygon
            const centerInInner = isPointInPolygon(centerPoint, loopInnerPolygon);
            if (!centerInInner) return false;

            // Center must be inside outer polygon (handles offset issues at reflex corners)
            const centerInOuter = loopOuterPolygon ? isPointInPolygon(centerPoint, loopOuterPolygon) : true;
            if (!centerInOuter) return false;

            // All corners must be inside inner polygon
            const cornersInInner = isRectInPolygon(x, y, w, h, loopInnerPolygon);
            if (!cornersInInner) return false;

            return true;
        };

        // Generate stall positions and check against interior polygon
        // Use effective dimensions based on parking angle
        for (let m = 0; m < numModules; m++) {
            const moduleStartY = loopInnerY + m * moduleDepth;

            // Top row of stalls in module (vehicles nose up/away from aisle)
            for (let s = 0; s < stallsPerRow; s++) {
                const stallX = loopInnerX + s * effectiveStallModuleWidth;
                const stallY = moduleStartY + effectiveStallDepth; // Front edge at aisle

                if (isStallValid(stallX, stallY, effectiveStallModuleWidth, effectiveStallDepth, true)) {
                    validStallCount++;
                    stallPositions.push({
                        x: stallX,
                        y: stallY,
                        row: 'top',
                        module: m,
                        index: s,
                        facingUp: true,
                        corners: parkingAngle !== 90 ? getStallCorners(stallX, stallY, true) : null
                    });
                }
            }

            // Bottom row of stalls in module (vehicles nose down/away from aisle)
            for (let s = 0; s < stallsPerRow; s++) {
                const stallX = loopInnerX + s * effectiveStallModuleWidth;
                const stallY = moduleStartY + effectiveStallDepth + effectiveAisleWidth; // Front edge at aisle

                if (isStallValid(stallX, stallY, effectiveStallModuleWidth, effectiveStallDepth, false)) {
                    validStallCount++;
                    stallPositions.push({
                        x: stallX,
                        y: stallY,
                        row: 'bottom',
                        module: m,
                        index: s,
                        facingUp: false,
                        corners: parkingAngle !== 90 ? getStallCorners(stallX, stallY, false) : null
                    });
                }
            }
        }

        // End row stalls (if space) - single row facing up
        if (endRowFits) {
            const endRowY = loopInnerY + moduleGridDepth + effectiveStallDepth;
            for (let s = 0; s < stallsPerRow; s++) {
                const stallX = loopInnerX + s * effectiveStallModuleWidth;
                if (isStallValid(stallX, endRowY, effectiveStallModuleWidth, effectiveStallDepth, true)) {
                    validStallCount++;
                    stallPositions.push({
                        x: stallX,
                        y: endRowY,
                        row: 'end',
                        module: -1,
                        index: s,
                        facingUp: true,
                        corners: parkingAngle !== 90 ? getStallCorners(stallX, endRowY, true) : null
                    });
                }
            }
        }

        // Final stall counts (use valid count for irregular, original for rectangular)
        const totalStalls = isIrregular || parkingAngle !== 90
            ? validStallCount
            : (stallsPerRow * 2 * numModules) + (endRowFits ? stallsPerRow : 0);
        const totalDoubleLoadedStalls = stallsPerRow * 2 * numModules;
        const endRowStalls = endRowFits ? stallsPerRow : 0;

        return {
            // Site/buildable area (bounds-based, for backward compatibility)
            siteW, siteD, minX, maxX, minY, maxY,
            setbackX, setbackY, buildableW, buildableD,

            // Configuration
            stallWidth, stallDepth, aisleWidth, driveType, effectiveAisleWidth,
            loopWidth, loopInset,

            // Perimeter loop (bounds-based for backward compatibility)
            loopOX, loopOY, loopTotalW, loopTotalD,

            // Interior area (bounds-based for backward compatibility)
            loopInnerX, loopInnerY, loopInnerW, loopInnerH,

            // Module layout
            moduleDepth, numModules, stallsPerRow,
            moduleGridDepth, remainingD, endRowFits,

            // Stall counts
            totalDoubleLoadedStalls, endRowStalls, totalStalls,

            // === Polygon-based geometry ===
            // These are the actual polygon shapes for rendering
            isIrregular,
            setbackPolygon,
            loopOuterPolygon,
            loopInnerPolygon,
            interiorPolygon,
            longestEdge,
            stallPositions, // Pre-calculated valid stall positions with corners for angled parking
            interiorBounds,
            loopOuterBounds,

            // === Angled parking geometry ===
            parkingAngle,
            angledGeometry, // Full geometry object with helper functions
            effectiveStallModuleWidth, // Width along aisle
            effectiveStallDepth, // Depth perpendicular to aisle
        };
    }, [boundary, setbacks, massingType, buildingType, effectiveMassingConfig]);

    // Results
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [results, setResults] = useState(null);
    const [activeConfig, setActiveConfig] = useState(0);

    // Scale for canvas
    const SCALE = 2; // 2 pixels per foot

    // View mode: 2D plan or 3D isometric
    const [viewMode, setViewMode] = useState('3d'); // '2d' | '3d'

    // 2D Canvas zoom and pan
    const [canvasZoom, setCanvasZoom] = useState(1);
    const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });
    const [isPanning, setIsPanning] = useState(false);
    const panStartRef = useRef({ x: 0, y: 0 });
    const panInitialRef = useRef({ x: 0, y: 0 });

    // Close aisle context menu when clicking outside
    useEffect(() => {
        if (!aisleContextMenu) return;

        const handleClickOutside = () => {
            setAisleContextMenu(null);
        };

        // Delay adding listener to avoid immediate close
        const timer = setTimeout(() => {
            document.addEventListener('click', handleClickOutside);
        }, 0);

        return () => {
            clearTimeout(timer);
            document.removeEventListener('click', handleClickOutside);
        };
    }, [aisleContextMenu]);

    // ResizeObserver to track canvas container size
    useEffect(() => {
        const container = canvasContainerRef.current;
        if (!container) return;

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                if (width > 0 && height > 0) {
                    setCanvasSize({ width: Math.floor(width), height: Math.floor(height) });
                }
            }
        });

        resizeObserver.observe(container);
        return () => resizeObserver.disconnect();
    }, []);

    // Initialize massing params when massing type changes
    useEffect(() => {
        if (currentMassing?.config) {
            setMassingParams({ ...currentMassing.config });
        }
    }, [massingType, buildingType]);

    // Apply preset when changed
    useEffect(() => {
        const preset = ZONING_PRESETS[zoningPreset];
        if (preset) {
            setFar(preset.far);
            setHeightLimit(preset.height);
            setLotCoverage(preset.coverage);
            setParkingRatio(preset.parkingRatio);
        }
    }, [zoningPreset]);

    useEffect(() => {
        const preset = SETBACK_PRESETS[setbackPreset];
        if (preset && setbackPreset !== 'custom') {
            setSetbacks({ front: preset.front, side: preset.side, rear: preset.rear });
        }
    }, [setbackPreset]);

    // ========================================================================
    // UNDO/REDO SYSTEM
    // ========================================================================

    // Create a snapshot of current state
    const createSnapshot = useCallback(() => {
        return {
            boundary: JSON.parse(JSON.stringify(boundary)),
            customBuildings: JSON.parse(JSON.stringify(customBuildings)),
            exclusions: JSON.parse(JSON.stringify(exclusions)),
        };
    }, [boundary, customBuildings, exclusions]);

    // Restore state from snapshot
    const restoreSnapshot = useCallback((snapshot) => {
        isUndoRedoAction.current = true;
        setBoundary(snapshot.boundary);
        setCustomBuildings(snapshot.customBuildings);
        setExclusions(snapshot.exclusions);
        // Reset the flag after state updates
        setTimeout(() => { isUndoRedoAction.current = false; }, 50);
    }, []);

    // Save current state to undo stack (called before changes)
    const saveToHistory = useCallback(() => {
        if (isUndoRedoAction.current) return;
        const snapshot = createSnapshot();
        setUndoStack(prev => {
            const newStack = [...prev, snapshot];
            // Limit stack size to prevent memory issues
            if (newStack.length > 50) newStack.shift();
            return newStack;
        });
        // Clear redo stack when new action is performed
        setRedoStack([]);
    }, [createSnapshot]);

    // Undo action
    const handleUndo = useCallback(() => {
        if (undoStack.length === 0) return;

        // Save current state to redo stack before undoing
        const currentSnapshot = createSnapshot();
        setRedoStack(prev => [...prev, currentSnapshot]);

        // Pop from undo stack and restore
        const previousSnapshot = undoStack[undoStack.length - 1];
        setUndoStack(prev => prev.slice(0, -1));
        restoreSnapshot(previousSnapshot);
    }, [undoStack, createSnapshot, restoreSnapshot]);

    // Redo action
    const handleRedo = useCallback(() => {
        if (redoStack.length === 0) return;

        // Save current state to undo stack before redoing
        const currentSnapshot = createSnapshot();
        setUndoStack(prev => [...prev, currentSnapshot]);

        // Pop from redo stack and restore
        const nextSnapshot = redoStack[redoStack.length - 1];
        setRedoStack(prev => prev.slice(0, -1));
        restoreSnapshot(nextSnapshot);
    }, [redoStack, createSnapshot, restoreSnapshot]);

    // Track changes to save to history (debounced for dragging)
    const saveTimeoutRef = useRef(null);
    const lastSnapshotRef = useRef(null);

    useEffect(() => {
        if (isUndoRedoAction.current || isDrawing) return;

        const currentState = JSON.stringify({ boundary, customBuildings, exclusions });

        // Only save if state actually changed
        if (lastSnapshotRef.current === currentState) return;

        // Debounce saves during rapid changes (like dragging)
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);

        saveTimeoutRef.current = setTimeout(() => {
            if (lastSnapshotRef.current && lastSnapshotRef.current !== currentState) {
                // State changed, save the previous state
                const prevState = JSON.parse(lastSnapshotRef.current);
                setUndoStack(prev => {
                    const newStack = [...prev, prevState];
                    if (newStack.length > 50) newStack.shift();
                    return newStack;
                });
                setRedoStack([]); // Clear redo on new action
            }
            lastSnapshotRef.current = currentState;
        }, 500); // 500ms debounce

        // Initialize on first render
        if (!lastSnapshotRef.current) {
            lastSnapshotRef.current = currentState;
        }

        return () => {
            if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        };
    }, [boundary, customBuildings, exclusions, isDrawing]);

    // Keyboard handlers for smart edit mode
    useEffect(() => {
        const handleKeyDown = (e) => {
            // Skip if typing in an input field
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            // === PARKING MODE KEYBOARD SHORTCUTS ===
            if (buildingType === 'parking' && massingType === 'surface' && boundary.length >= 3 && !isDrawing) {
                // D: Toggle draw mode
                if (e.key === 'd' || e.key === 'D') {
                    e.preventDefault();
                    setIsDrawingAisle(prev => !prev);
                    setIsPlacingSpine(false);
                    setIsEditingAisles(false);
                    setIsPlacingAda(false);
                    if (isDrawingAisle) {
                        setCurrentAislePoints([]);
                        setAisleHoverPoint(null);
                    }
                    return;
                }
                // E: Toggle edit mode (if aisles exist)
                if ((e.key === 'e' || e.key === 'E') && drawnAisles.length > 0) {
                    e.preventDefault();
                    if (!isEditingAisles) {
                        setAisleBackup(JSON.parse(JSON.stringify(drawnAisles)));
                        // Exit boundary edit when entering aisle edit
                        setIsEditingBoundary(false);
                    }
                    setIsEditingAisles(prev => !prev);
                    setIsDrawingAisle(false);
                    setIsPlacingSpine(false);
                    if (isEditingAisles) {
                        setAisleBackup(null);
                        setAisleEditHistory([]);
                    }
                    return;
                }
                // S: Toggle spine placement (if cross-aisle enabled and no custom aisles)
                if ((e.key === 's' || e.key === 'S') && crossAisleMode !== 'none' && drawnAisles.length === 0) {
                    e.preventDefault();
                    setIsPlacingSpine(prev => !prev);
                    setIsDrawingAisle(false);
                    setIsEditingAisles(false);
                    setIsPlacingAda(false);
                    return;
                }
                // R: Reset to auto layout
                if ((e.key === 'r' || e.key === 'R') && (drawnAisles.length > 0 || manualSpines.length > 0)) {
                    e.preventDefault();
                    setDrawnAisles([]);
                    setManualSpines([]);
                    setIsEditingAisles(false);
                    setIsDrawingAisle(false);
                    setAisleBackup(null);
                    setAisleEditHistory([]);
                    return;
                }
            }

            // Ctrl+Z: undo last aisle edit (check FIRST before general undo)
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey && isEditingAisles && aisleEditHistory.length > 0) {
                e.preventDefault();
                const lastState = aisleEditHistory[aisleEditHistory.length - 1];
                setDrawnAisles(lastState);
                setAisleEditHistory(prev => prev.slice(0, -1));
                return;
            }
            // Undo: Ctrl+Z (general - for boundary/buildings)
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                handleUndo();
                return;
            }
            // Redo: Ctrl+Y or Ctrl+Shift+Z
            if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
                e.preventDefault();
                handleRedo();
                return;
            }
            // Delete or Backspace: remove selected building OR undo last aisle point
            if ((e.key === 'Delete' || e.key === 'Backspace') && selectedBuildingId) {
                e.preventDefault();
                setCustomBuildings(prev => prev.filter(b => b.id !== selectedBuildingId));
                setSelectedBuildingId(null);
            }
            // Backspace while drawing aisle: undo last point
            if (e.key === 'Backspace' && isDrawingAisle && currentAislePoints.length > 0) {
                e.preventDefault();
                setCurrentAislePoints(prev => prev.slice(0, -1));
                return;
            }
            // Enter while drawing aisle: finish drawing (if at least 2 points)
            if (e.key === 'Enter' && isDrawingAisle && currentAislePoints.length >= 2) {
                e.preventDefault();
                setDrawnAisles(prev => [...prev, {
                    points: [...currentAislePoints],
                    id: Date.now()
                }]);
                setCurrentAislePoints([]);
                setIsDrawingAisle(false);
                setAisleHoverPoint(null);
                return;
            }
            // Escape: deselect or cancel drawing
            if (e.key === 'Escape') {
                e.preventDefault();
                // Close context menu first
                if (aisleContextMenu) {
                    setAisleContextMenu(null);
                    return;
                }
                // Cancel aisle editing - restore backup
                if (isEditingAisles) {
                    if (aisleBackup !== null) {
                        setDrawnAisles(aisleBackup);
                    }
                    setIsEditingAisles(false);
                    setHoveredAislePoint(null);
                    setDraggingAislePoint(null);
                    setAisleEditHistory([]);
                    setAisleBackup(null);
                    return;
                }
                // Cancel aisle drawing first
                if (isDrawingAisle) {
                    setIsDrawingAisle(false);
                    setCurrentAislePoints([]);
                    setAisleHoverPoint(null);
                    return;
                }
                // Cancel spine placement
                if (isPlacingSpine) {
                    setIsPlacingSpine(false);
                    setSpineHoverX(null);
                    return;
                }
                // Cancel ADA placement
                if (isPlacingAda) {
                    setIsPlacingAda(false);
                    setAdaHoverIndex(null);
                    setAdaHoverRow(null);
                    return;
                }
                if (isDrawingShape) {
                    setIsDrawingShape(false);
                    setDrawingPolygon([]);
                } else {
                    setSelectedBuildingId(null);
                }
            }
            // Enter: finish editing aisles
            if (e.key === 'Enter' && isEditingAisles) {
                e.preventDefault();
                setIsEditingAisles(false);
                setHoveredAislePoint(null);
                setDraggingAislePoint(null);
                setAisleEditHistory([]);
                setAisleBackup(null);
                return;
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedBuildingId, isDrawingShape, handleUndo, handleRedo, isDrawingAisle, isPlacingSpine, isPlacingAda, currentAislePoints, isEditingAisles, aisleEditHistory, aisleBackup]);

    // Handler to add a custom building at clicked position
    const handleAddBuilding = useCallback((x, z) => {
        const newBuilding = {
            id: Date.now(),
            x: x - newBuildingConfig.width / 2, // Center on click
            z: z - newBuildingConfig.depth / 2,
            width: newBuildingConfig.width,
            depth: newBuildingConfig.depth,
            floors: newBuildingConfig.floors,
            floorHeight: newBuildingConfig.floorHeight,
            color: newBuildingConfig.color,
        };
        setCustomBuildings(prev => [...prev, newBuilding]);
    }, [newBuildingConfig]);

    // Handler to delete a custom building
    const handleDeleteBuilding = useCallback((buildingId) => {
        setCustomBuildings(prev => prev.filter(b => b.id !== buildingId));
        if (selectedBuildingId === buildingId) setSelectedBuildingId(null);
    }, [selectedBuildingId]);

    // Handler to select a building (shows handles)
    const handleSelectBuilding = useCallback((buildingId) => {
        setSelectedBuildingId(buildingId);
        // Deselect template building when selecting custom
        if (buildingId !== null) {
            setSelectedTemplateBuilding(null);
        }
    }, []);

    // Handler to move a building
    const handleMoveBuilding = useCallback((buildingId, newX, newZ) => {
        setCustomBuildings(prev => prev.map(b => {
            if (b.id !== buildingId) return b;
            if (b.type === 'polygon' && b.polygon) {
                // Move polygon: offset all vertices
                const dx = newX - (b.polygon.reduce((s, p) => s + p.x, 0) / b.polygon.length);
                const dz = newZ - (b.polygon.reduce((s, p) => s + p.z, 0) / b.polygon.length);
                return { ...b, polygon: b.polygon.map(p => ({ x: p.x + dx, z: p.z + dz })) };
            }
            // Box building: update x, z
            return { ...b, x: newX - (b.width || 60) / 2, z: newZ - (b.depth || 80) / 2 };
        }));
    }, []);

    // Handler to select a template building
    const handleSelectTemplateBuilding = useCallback((buildingIndex) => {
        setSelectedTemplateBuilding(buildingIndex);
        // Deselect custom building when selecting template
        if (buildingIndex !== null) {
            setSelectedBuildingId(null);
        }
    }, []);

    // Handler to move a template building
    const handleMoveTemplateBuilding = useCallback((buildingIndex, newX, newZ) => {
        setTemplateBuildingPositions(prev => ({
            ...prev,
            [buildingIndex]: { x: newX, z: newZ }
        }));
    }, []);

    // Clear all custom buildings
    const handleClearAllBuildings = useCallback(() => {
        setCustomBuildings([]);
    }, []);

    // Handler to add polygon point during drawing
    const handleAddPolygonPoint = useCallback((x, z) => {
        setDrawingPolygon(prev => [...prev, { x, z }]);
    }, []);

    // Handler to finish polygon drawing and create building
    const handleFinishPolygon = useCallback(() => {
        if (drawingPolygon.length >= 3) {
            const newBuilding = {
                id: Date.now(),
                type: 'polygon', // Mark as polygon building
                polygon: drawingPolygon,
                floors: polygonBuildingConfig.floors,
                floorHeight: polygonBuildingConfig.floorHeight,
                color: polygonBuildingConfig.color,
            };
            setCustomBuildings(prev => [...prev, newBuilding]);
        }
        setDrawingPolygon([]);
        setIsDrawingShape(false);
    }, [drawingPolygon, polygonBuildingConfig]);

    // Handler to cancel polygon drawing
    const handleCancelPolygon = useCallback(() => {
        setDrawingPolygon([]);
        setIsDrawingShape(false);
    }, []);

    // Start drawing mode (Shift+click)
    const handleStartDrawing = useCallback(() => {
        setIsDrawingShape(true);
        setDrawingPolygon([]);
        setSelectedBuildingId(null);
    }, []);

    // ========================================================================
    // BOUNDARY EDITING HANDLERS
    // ========================================================================

    // Update a boundary vertex position
    const handleUpdateBoundaryVertex = useCallback((index, newX, newY) => {
        setBoundary(prev => {
            const updated = [...prev];
            updated[index] = { x: newX, y: newY };
            return updated;
        });
    }, []);

    // Add a new vertex on an edge (between index and index+1)
    const handleAddBoundaryVertex = useCallback((afterIndex, x, y) => {
        setBoundary(prev => {
            const updated = [...prev];
            updated.splice(afterIndex + 1, 0, { x, y });
            return updated;
        });
    }, []);

    // Delete a boundary vertex (need at least 3)
    const handleDeleteBoundaryVertex = useCallback((index) => {
        setBoundary(prev => {
            if (prev.length <= 3) return prev; // Minimum 3 vertices
            return prev.filter((_, i) => i !== index);
        });
    }, []);

    // Handler to update a vertex of a polygon building
    const handleUpdateVertex = useCallback((buildingId, vertexIndex, newX, newZ) => {
        setCustomBuildings(prev => prev.map(bldg => {
            if (bldg.id === buildingId && bldg.type === 'polygon' && bldg.polygon) {
                const newPolygon = [...bldg.polygon];
                newPolygon[vertexIndex] = { x: newX, z: newZ };
                return { ...bldg, polygon: newPolygon };
            }
            return bldg;
        }));
    }, []);

    // ========================================================================
    // ISOMETRIC 3D RENDERING HELPERS
    // ========================================================================

    const shadeColor = (color, percent) => {
        const num = parseInt(color.replace('#', ''), 16);
        const amt = Math.round(2.55 * percent);
        const R = Math.min(255, Math.max(0, (num >> 16) + amt));
        const G = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amt));
        const B = Math.min(255, Math.max(0, (num & 0x0000FF) + amt));
        return '#' + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
    };

    // Helper to check if a point is inside a polygon (ray casting algorithm)
    const pointInPolygon = useCallback((point, polygon) => {
        if (!polygon || polygon.length < 3) return false;

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
    }, []);

    // Helper to check if a rectangle is fully inside a polygon
    // Checks all 4 corners of the rectangle
    const rectInPolygon = useCallback((x, y, w, h, polygon) => {
        if (!polygon || polygon.length < 3) return true; // No polygon = assume inside

        // Check all 4 corners
        const corners = [
            { x: x, y: y },           // Top-left
            { x: x + w, y: y },       // Top-right
            { x: x + w, y: y + h },   // Bottom-right
            { x: x, y: y + h }        // Bottom-left
        ];

        return corners.every(corner => pointInPolygon(corner, polygon));
    }, [pointInPolygon]);

    // Helper to check if a rectangle overlaps with any exclusion zone
    // Returns true if the rectangle overlaps with ANY exclusion polygon
    const rectOverlapsExclusions = useCallback((x, y, w, h, exclusionList) => {
        if (!exclusionList || exclusionList.length === 0) return false;

        // Check all 4 corners of the rectangle
        const corners = [
            { x: x, y: y },           // Top-left
            { x: x + w, y: y },       // Top-right
            { x: x + w, y: y + h },   // Bottom-right
            { x: x, y: y + h }        // Bottom-left
        ];
        const center = { x: x + w / 2, y: y + h / 2 };

        for (const exclusion of exclusionList) {
            if (!exclusion || exclusion.length < 3) continue;

            // Check if any corner or center is inside the exclusion
            if (corners.some(corner => pointInPolygon(corner, exclusion))) {
                return true;
            }
            if (pointInPolygon(center, exclusion)) {
                return true;
            }

            // Also check if any exclusion vertex is inside the rectangle
            for (const pt of exclusion) {
                if (pt.x >= x && pt.x <= x + w && pt.y >= y && pt.y <= y + h) {
                    return true;
                }
            }
        }
        return false;
    }, [pointInPolygon]);

    // Helper to get the valid X range (min, max) at a given Y within a polygon
    // Uses ray casting to find intersection points with polygon edges
    const getXRangeAtY = useCallback((y, polygon) => {
        if (!polygon || polygon.length < 3) return null;

        const intersections = [];
        const n = polygon.length;

        for (let i = 0; i < n; i++) {
            const p1 = polygon[i];
            const p2 = polygon[(i + 1) % n];

            // Check if this edge crosses the Y value
            if ((p1.y <= y && p2.y > y) || (p2.y <= y && p1.y > y)) {
                // Calculate X intersection
                const t = (y - p1.y) / (p2.y - p1.y);
                const x = p1.x + t * (p2.x - p1.x);
                intersections.push(x);
            }
        }

        if (intersections.length < 2) return null;

        // Sort intersections and return min/max
        intersections.sort((a, b) => a - b);
        return { minX: intersections[0], maxX: intersections[intersections.length - 1] };
    }, []);

    // Helper to inset a polygon by a fixed distance (for setback visualization)
    // Uses a uniform offset - works well for convex and simple concave polygons
    const insetPolygon = useCallback((polygon, offset) => {
        if (!polygon || polygon.length < 3) return polygon;

        // First, determine winding order (clockwise or counter-clockwise)
        // Using shoelace formula for signed area
        let signedArea = 0;
        for (let i = 0; i < polygon.length; i++) {
            const curr = polygon[i];
            const next = polygon[(i + 1) % polygon.length];
            signedArea += (next.x - curr.x) * (next.y + curr.y);
        }
        // In screen coords (Y down): signedArea > 0 means clockwise
        // To SHRINK (inset), we need to move vertices INWARD
        // Flip the sign: clockwise polygons need positive offset direction
        const windingSign = signedArea > 0 ? 1 : -1;

        const result = [];
        const n = polygon.length;

        for (let i = 0; i < n; i++) {
            const prev = polygon[(i - 1 + n) % n];
            const curr = polygon[i];
            const next = polygon[(i + 1) % n];

            // Calculate edge vectors
            const dx1 = curr.x - prev.x;
            const dy1 = curr.y - prev.y;
            const dx2 = next.x - curr.x;
            const dy2 = next.y - curr.y;

            // Normalize and get perpendicular (inward pointing with winding adjustment)
            const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1) || 1;
            const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 1;

            // Perpendicular normals (adjusted for winding order)
            const nx1 = windingSign * dy1 / len1;
            const ny1 = windingSign * -dx1 / len1;
            const nx2 = windingSign * dy2 / len2;
            const ny2 = windingSign * -dx2 / len2;

            // Average the normals for the vertex offset direction
            let nx = (nx1 + nx2) / 2;
            let ny = (ny1 + ny2) / 2;
            const nlen = Math.sqrt(nx * nx + ny * ny) || 1;
            nx /= nlen;
            ny /= nlen;

            // Calculate offset distance (adjust for corner angle)
            const dot = nx1 * nx2 + ny1 * ny2;
            const cornerFactor = 1 / Math.max(0.5, Math.sqrt((1 + dot) / 2));
            const adjustedOffset = offset * Math.min(cornerFactor, 2);

            result.push({
                x: curr.x + nx * adjustedOffset,
                y: curr.y + ny * adjustedOffset
            });
        }

        return result;
    }, []);

    // Helper to inset a polygon with DIFFERENT setbacks per edge orientation
    // front = bottom edges (facing street), rear = top edges, side = left/right edges
    // Uses same algorithm as insetPolygon but with variable offset per edge
    const insetPolygonWithSetbacks = useCallback((polygon, frontSetback, sideSetback, rearSetback) => {
        if (!polygon || polygon.length < 3) return polygon;

        // Determine winding order (same as insetPolygon)
        let signedArea = 0;
        for (let i = 0; i < polygon.length; i++) {
            const curr = polygon[i];
            const next = polygon[(i + 1) % polygon.length];
            signedArea += (next.x - curr.x) * (next.y + curr.y);
        }
        // Same winding sign as the working insetPolygon
        const windingSign = signedArea > 0 ? -1 : 1;

        const n = polygon.length;
        const result = [];

        for (let i = 0; i < n; i++) {
            const prev = polygon[(i - 1 + n) % n];
            const curr = polygon[i];
            const next = polygon[(i + 1) % n];

            // Calculate edge vectors (same as insetPolygon)
            const dx1 = curr.x - prev.x;  // Edge from prev to curr
            const dy1 = curr.y - prev.y;
            const dx2 = next.x - curr.x;  // Edge from curr to next
            const dy2 = next.y - curr.y;

            const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1) || 1;
            const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 1;

            // Perpendicular normals (same formula as working insetPolygon)
            const nx1 = windingSign * dy1 / len1;
            const ny1 = windingSign * -dx1 / len1;
            const nx2 = windingSign * dy2 / len2;
            const ny2 = windingSign * -dx2 / len2;

            // Determine setback for each edge based on edge direction
            // Edge 1 (prev->curr): classify by direction
            let offset1;
            const edx1 = dx1 / len1;
            const edy1 = dy1 / len1;
            if (Math.abs(edx1) > Math.abs(edy1)) {
                // Horizontal edge
                offset1 = edy1 > 0 ? frontSetback : rearSetback; // Going down = front, up = rear
            } else {
                // Vertical edge
                offset1 = sideSetback;
            }

            // Edge 2 (curr->next): classify by direction
            let offset2;
            const edx2 = dx2 / len2;
            const edy2 = dy2 / len2;
            if (Math.abs(edx2) > Math.abs(edy2)) {
                // Horizontal edge
                offset2 = edy2 > 0 ? frontSetback : rearSetback;
            } else {
                // Vertical edge
                offset2 = sideSetback;
            }

            // Average the normals for the vertex offset direction (same as insetPolygon)
            let nx = (nx1 + nx2) / 2;
            let ny = (ny1 + ny2) / 2;
            const nlen = Math.sqrt(nx * nx + ny * ny) || 1;
            nx /= nlen;
            ny /= nlen;

            // Use average of the two edge setbacks for this corner
            const offset = (offset1 + offset2) / 2;

            // Adjust for corner angle (same as insetPolygon)
            const dot = nx1 * nx2 + ny1 * ny2;
            const cornerFactor = 1 / Math.max(0.5, Math.sqrt((1 + dot) / 2));
            const adjustedOffset = offset * Math.min(cornerFactor, 2);

            result.push({
                x: curr.x + nx * adjustedOffset,
                y: curr.y + ny * adjustedOffset
            });
        }

        return result;
    }, []);

    // ========================================================================
    // SNAPPING SYSTEM (Testfit-style)
    // ========================================================================

    // Snap a point to grid
    const snapToGridPoint = useCallback((x, y) => {
        if (!snapEnabled || !snapToGrid) return { x, y };
        return {
            x: Math.round(x / gridSize) * gridSize,
            y: Math.round(y / gridSize) * gridSize
        };
    }, [snapEnabled, snapToGrid, gridSize]);

    // Snap to nearest object vertex or edge
    const snapToObjectsPoint = useCallback((x, y, excludeIndices = []) => {
        if (!snapEnabled || !snapToObjects) return { x, y, snapped: false };

        const SNAP_THRESHOLD = 15; // pixels threshold for snapping
        let closestDist = SNAP_THRESHOLD;
        let snappedPoint = { x, y, snapped: false };

        // Check boundary vertices
        boundary.forEach((pt, i) => {
            if (excludeIndices.includes(i)) return;
            const dist = Math.sqrt((x - pt.x) ** 2 + (y - pt.y) ** 2);
            if (dist < closestDist) {
                closestDist = dist;
                snappedPoint = { x: pt.x, y: pt.y, snapped: true, type: 'vertex' };
            }
        });

        // Check custom building vertices
        customBuildings.forEach(bldg => {
            if (bldg.type === 'polygon' && bldg.polygon) {
                bldg.polygon.forEach(pt => {
                    const dist = Math.sqrt((x - pt.x) ** 2 + (y - pt.z) ** 2);
                    if (dist < closestDist) {
                        closestDist = dist;
                        snappedPoint = { x: pt.x, y: pt.z, snapped: true, type: 'building' };
                    }
                });
            } else if (bldg.x !== undefined) {
                // Box building corners
                const corners = [
                    { x: bldg.x, y: bldg.z },
                    { x: bldg.x + bldg.width, y: bldg.z },
                    { x: bldg.x + bldg.width, y: bldg.z + bldg.depth },
                    { x: bldg.x, y: bldg.z + bldg.depth }
                ];
                corners.forEach(pt => {
                    const dist = Math.sqrt((x - pt.x) ** 2 + (y - pt.y) ** 2);
                    if (dist < closestDist) {
                        closestDist = dist;
                        snappedPoint = { x: pt.x, y: pt.y, snapped: true, type: 'building' };
                    }
                });
            }
        });

        return snappedPoint;
    }, [snapEnabled, snapToObjects, boundary, customBuildings]);

    // Snap to common angles (0, 45, 90, 135, 180...) or ortho (90° only) relative to a reference point
    const snapToAngle = useCallback((x, y, refX, refY) => {
        if (!snapEnabled || !snapToAngles) return { x, y };

        const dx = x - refX;
        const dy = y - refY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 5) return { x, y }; // Too close, no angle snap

        const angle = Math.atan2(dy, dx);
        // Ortho mode: only 90° increments (0°, 90°, 180°, 270°)
        // Normal mode: 45° increments
        const SNAP_ANGLES = orthoMode
            ? [0, Math.PI / 2, Math.PI, -Math.PI / 2] // 90° only
            : [0, Math.PI / 4, Math.PI / 2, 3 * Math.PI / 4, Math.PI, -3 * Math.PI / 4, -Math.PI / 2, -Math.PI / 4];
        const ANGLE_THRESHOLD = orthoMode ? Math.PI / 6 : Math.PI / 18; // 30° for ortho, 10° for normal

        for (const snapAngle of SNAP_ANGLES) {
            if (Math.abs(angle - snapAngle) < ANGLE_THRESHOLD) {
                return {
                    x: refX + dist * Math.cos(snapAngle),
                    y: refY + dist * Math.sin(snapAngle),
                    snapped: true,
                    angle: snapAngle
                };
            }
        }

        return { x, y };
    }, [snapEnabled, snapToAngles, orthoMode]);

    // Combined snap function - tries all snap types in priority order
    const applySnapping = useCallback((x, y, refPoint = null, excludeIndices = []) => {
        let result = { x, y };

        // First try object snapping (highest priority)
        const objSnap = snapToObjectsPoint(x, y, excludeIndices);
        if (objSnap.snapped) {
            return objSnap;
        }

        // Then try angle snapping if we have a reference point
        if (refPoint) {
            const angleSnap = snapToAngle(x, y, refPoint.x, refPoint.y);
            if (angleSnap.snapped) {
                result = angleSnap;
            }
        }

        // Finally apply grid snapping
        result = snapToGridPoint(result.x, result.y);

        return result;
    }, [snapToGridPoint, snapToObjectsPoint, snapToAngle]);

    // Track changes to individual building params to trigger canvas redraw
    const [paramChangeCounter, setParamChangeCounter] = useState(0);
    useEffect(() => {
        setParamChangeCounter(c => c + 1);
    }, [individualBuildingParams, templateBuildingPositions]);

    // Draw canvas
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        // Clear with reset transform
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = '#f8fafc'; // Light background matching website
        ctx.fillRect(0, 0, w, h);

        // Apply zoom and pan transform
        ctx.setTransform(canvasZoom, 0, 0, canvasZoom, canvasPan.x, canvasPan.y);

        // Grid - only show when snapToGrid is enabled
        if (snapToGrid) {
            const gridSpacing = gridSize * SCALE;
            ctx.strokeStyle = '#e2e8f0';
            ctx.lineWidth = 1 / canvasZoom;
            for (let x = -Math.ceil(canvasPan.x / canvasZoom / gridSpacing) * gridSpacing; x < (w - canvasPan.x) / canvasZoom; x += gridSpacing) {
                ctx.beginPath();
                ctx.moveTo(x, -canvasPan.y / canvasZoom);
                ctx.lineTo(x, (h - canvasPan.y) / canvasZoom);
                ctx.stroke();
            }
            for (let y = -Math.ceil(canvasPan.y / canvasZoom / gridSpacing) * gridSpacing; y < (h - canvasPan.y) / canvasZoom; y += gridSpacing) {
                ctx.beginPath();
                ctx.moveTo(-canvasPan.x / canvasZoom, y);
                ctx.lineTo((w - canvasPan.x) / canvasZoom, y);
                ctx.stroke();
            }

            // Draw major grid lines (every 5 grid cells) for better visibility
            if (gridSize <= 20) {
                ctx.strokeStyle = '#cbd5e1';
                ctx.lineWidth = 1 / canvasZoom;
                const majorSpacing = gridSpacing * 5;
                for (let x = -Math.ceil(canvasPan.x / canvasZoom / majorSpacing) * majorSpacing; x < (w - canvasPan.x) / canvasZoom; x += majorSpacing) {
                    ctx.beginPath();
                    ctx.moveTo(x, -canvasPan.y / canvasZoom);
                    ctx.lineTo(x, (h - canvasPan.y) / canvasZoom);
                    ctx.stroke();
                }
                for (let y = -Math.ceil(canvasPan.y / canvasZoom / majorSpacing) * majorSpacing; y < (h - canvasPan.y) / canvasZoom; y += majorSpacing) {
                    ctx.beginPath();
                    ctx.moveTo(-canvasPan.x / canvasZoom, y);
                    ctx.lineTo((w - canvasPan.x) / canvasZoom, y);
                    ctx.stroke();
                }
            }
        }

        // ====================================================================
        // 2D MODE: Traditional plan view
        // ====================================================================
        if (viewMode === '2d') {
            // Draw boundary
            if (boundary.length > 0) {
                ctx.beginPath();
                ctx.moveTo(boundary[0].x * SCALE, boundary[0].y * SCALE);
                for (let i = 1; i < boundary.length; i++) {
                    ctx.lineTo(boundary[i].x * SCALE, boundary[i].y * SCALE);
                }
                if (!isDrawing) ctx.closePath();
                ctx.fillStyle = 'rgba(100, 200, 100, 0.2)';
                ctx.fill();
                ctx.strokeStyle = isEditingBoundary ? '#22d3ee' : '#4ade80'; // Cyan when editing
                ctx.lineWidth = isEditingBoundary ? 3 : 2;
                ctx.stroke();

                // Highlight hovered edge when editing
                if (isEditingBoundary && hoveredBoundaryEdge !== null && !isDrawing) {
                    const p1 = boundary[hoveredBoundaryEdge];
                    const p2 = boundary[(hoveredBoundaryEdge + 1) % boundary.length];
                    ctx.beginPath();
                    ctx.moveTo(p1.x * SCALE, p1.y * SCALE);
                    ctx.lineTo(p2.x * SCALE, p2.y * SCALE);
                    ctx.strokeStyle = '#f97316'; // Orange highlight
                    ctx.lineWidth = 5;
                    ctx.stroke();
                }

                // Draw vertices - larger when editing
                boundary.forEach((pt, i) => {
                    const isHovered = isEditingBoundary && hoveredBoundaryVertex === i;
                    const radius = isEditingBoundary ? (isHovered ? 10 : 7) : 5;

                    ctx.beginPath();
                    ctx.arc(pt.x * SCALE, pt.y * SCALE, radius, 0, Math.PI * 2);

                    if (isEditingBoundary) {
                        // Edit mode: white with cyan outline
                        ctx.fillStyle = isHovered ? '#22d3ee' : '#ffffff';
                        ctx.fill();
                        ctx.strokeStyle = '#0891b2';
                        ctx.lineWidth = 2;
                        ctx.stroke();
                    } else {
                        ctx.fillStyle = i === 0 ? '#22c55e' : '#4ade80';
                        ctx.fill();
                    }
                });

                // Show edge midpoints when editing (for adding new vertices)
                if (isEditingBoundary && !isDrawing) {
                    for (let i = 0; i < boundary.length; i++) {
                        const p1 = boundary[i];
                        const p2 = boundary[(i + 1) % boundary.length];
                        const midX = (p1.x + p2.x) / 2 * SCALE;
                        const midY = (p1.y + p2.y) / 2 * SCALE;

                        ctx.beginPath();
                        ctx.arc(midX, midY, 4, 0, Math.PI * 2);
                        ctx.fillStyle = '#94a3b8';
                        ctx.fill();
                        ctx.strokeStyle = '#475569';
                        ctx.lineWidth = 1;
                        ctx.stroke();
                    }
                }
            }

            // Draw exclusions
            exclusions.forEach((ex) => {
                ctx.beginPath();
                ctx.moveTo(ex[0].x * SCALE, ex[0].y * SCALE);
                for (let i = 1; i < ex.length; i++) {
                    ctx.lineTo(ex[i].x * SCALE, ex[i].y * SCALE);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(239, 68, 68, 0.3)';
                ctx.fill();
                ctx.strokeStyle = '#ef4444';
                ctx.lineWidth = 2;
                ctx.stroke();
            });

            // Current exclusion being drawn
            if (currentExclusion.length > 0) {
                ctx.beginPath();
                ctx.moveTo(currentExclusion[0].x * SCALE, currentExclusion[0].y * SCALE);
                for (let i = 1; i < currentExclusion.length; i++) {
                    ctx.lineTo(currentExclusion[i].x * SCALE, currentExclusion[i].y * SCALE);
                }
                ctx.strokeStyle = '#f87171';
                ctx.lineWidth = 2;
                ctx.stroke();
            }

            // Calculate massing footprints for 2D (same as 3D)
            if (boundary.length >= 3 && !isDrawing) {
                const minX = Math.min(...boundary.map(p => p.x));
                const maxX = Math.max(...boundary.map(p => p.x));
                const minY = Math.min(...boundary.map(p => p.y));
                const maxY = Math.max(...boundary.map(p => p.y));
                const siteW = maxX - minX;
                const siteD = maxY - minY;

                // Draw buildable area as inset polygon (follows boundary shape)
                // Uses average setback for now - per-edge setbacks need debugging
                // Skip for parking - parking has its own visual boundaries (perimeter curb)
                const avgSetback = (setbacks.front + setbacks.side + setbacks.rear) / 3;
                const insetBoundary = insetPolygon(boundary, avgSetback);

                if (insetBoundary && insetBoundary.length >= 3 && buildingType !== 'parking') {
                    ctx.beginPath();
                    ctx.moveTo(insetBoundary[0].x * SCALE, insetBoundary[0].y * SCALE);
                    for (let i = 1; i < insetBoundary.length; i++) {
                        ctx.lineTo(insetBoundary[i].x * SCALE, insetBoundary[i].y * SCALE);
                    }
                    ctx.closePath();
                    ctx.fillStyle = 'rgba(59, 130, 246, 0.15)';
                    ctx.fill();
                    ctx.strokeStyle = '#3b82f6';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([5, 5]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // For massing calculations, derive from the INSET BOUNDARY polygon
                // This properly handles irregular shapes with per-edge setbacks
                let setbackX, setbackY, buildableW, buildableD;
                if (insetBoundary && insetBoundary.length >= 3) {
                    // Use bounding box of the inset polygon
                    const insetMinX = Math.min(...insetBoundary.map(p => p.x));
                    const insetMaxX = Math.max(...insetBoundary.map(p => p.x));
                    const insetMinY = Math.min(...insetBoundary.map(p => p.y));
                    const insetMaxY = Math.max(...insetBoundary.map(p => p.y));

                    // Safety check: inset bounds must be INSIDE original bounds
                    // If inset polygon is somehow larger, use constrained values
                    setbackX = Math.max(insetMinX, minX);
                    setbackY = Math.max(insetMinY, minY);
                    const constrainedMaxX = Math.min(insetMaxX, maxX);
                    const constrainedMaxY = Math.min(insetMaxY, maxY);
                    buildableW = Math.max(0, constrainedMaxX - setbackX);
                    buildableD = Math.max(0, constrainedMaxY - setbackY);
                } else {
                    // Fallback to rectangular calculation
                    setbackX = minX + setbacks.side;
                    setbackY = minY + setbacks.front;
                    buildableW = Math.max(0, siteW - setbacks.side * 2);
                    buildableD = Math.max(0, siteD - setbacks.front - setbacks.rear);
                }

                // Skip massing if buildable area is too small
                if (buildableW <= 0 || buildableD <= 0) {
                    // Draw "setbacks too large" indicator
                    ctx.save();
                    ctx.fillStyle = '#ef4444';
                    ctx.font = 'bold 14px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    const centerX = (minX + siteW / 2) * SCALE;
                    const centerY = (minY + siteD / 2) * SCALE;
                    ctx.fillText('Setbacks exceed site dimensions', centerX, centerY);
                    ctx.restore();
                } else {

                    // Draw massing footprints based on building type and massing type
                    const floorH = currentSubtype?.floorHeight || 10;
                    const massType = massingType;

                    // Building type specific colors
                    const typeColors = {
                        multifamily: { main: 'rgba(139, 92, 246, 0.4)', stroke: '#8b5cf6' },      // Purple
                        singlefamily: { main: 'rgba(34, 197, 94, 0.4)', stroke: '#22c55e' },      // Green
                        industrial: { main: 'rgba(234, 179, 8, 0.4)', stroke: '#eab308' },        // Yellow
                        hotel: { main: 'rgba(236, 72, 153, 0.4)', stroke: '#ec4899' },            // Pink
                        retail: { main: 'rgba(249, 115, 22, 0.4)', stroke: '#f97316' },           // Orange
                        datacenter: { main: 'rgba(14, 165, 233, 0.4)', stroke: '#0ea5e9' },       // Sky blue
                        parking: { main: 'rgba(156, 163, 175, 0.4)', stroke: '#9ca3af' },         // Gray
                    };

                    // === SITE BOUNDARY CLIPPING ===
                    // Clip to the ORIGINAL site boundary polygon
                    // This ensures NO massing ever extends outside the site boundary
                    // Individual setbacks are applied within the parking layout calculations
                    ctx.save();
                    if (boundary && boundary.length >= 3) {
                        ctx.beginPath();
                        ctx.moveTo(boundary[0].x * SCALE, boundary[0].y * SCALE);
                        for (let i = 1; i < boundary.length; i++) {
                            ctx.lineTo(boundary[i].x * SCALE, boundary[i].y * SCALE);
                        }
                        ctx.closePath();
                        ctx.clip();
                    }

                    const colors = typeColors[buildingType] || typeColors.multifamily;
                    const buildColor = colors.main;
                    const buildStroke = colors.stroke;
                    const parkingColor = 'rgba(250, 204, 21, 0.4)';
                    const podiumColor = 'rgba(107, 114, 128, 0.4)';

                    // Track template buildings for click detection
                    const templateBuildings2D = [];

                    const drawRect = (x, y, w, h, color, strokeColor, isTemplateBuilding = false, templateIndex = null) => {
                        // Apply template building position offset if available
                        let finalX = x;
                        let finalY = y;
                        if (isTemplateBuilding && templateIndex !== null && templateBuildingPositions[templateIndex]) {
                            const offset = templateBuildingPositions[templateIndex];
                            // The stored position is the new center, so offset to corner
                            finalX = offset.x - w / 2;
                            finalY = offset.z - h / 2;
                        }

                        // Store for click detection (using current position)
                        if (isTemplateBuilding && templateIndex !== null) {
                            templateBuildings2D.push({
                                index: templateIndex,
                                x: finalX,
                                y: finalY,
                                w: w,
                                h: h,
                                origX: x,
                                origY: y
                            });
                        }

                        ctx.beginPath();
                        ctx.rect(finalX * SCALE, finalY * SCALE, w * SCALE, h * SCALE);
                        ctx.fillStyle = color;
                        ctx.fill();

                        // Always draw dark edge outline for better mass visibility
                        ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
                        ctx.lineWidth = 1;
                        ctx.stroke();

                        // Highlight if selected (additional highlight stroke)
                        if (isTemplateBuilding && templateIndex === selectedTemplateBuilding) {
                            ctx.strokeStyle = '#ff6600';
                            ctx.lineWidth = 4;
                            ctx.stroke();
                        } else if (strokeColor) {
                            ctx.strokeStyle = strokeColor;
                            ctx.lineWidth = 2;
                            ctx.stroke();
                        }

                        // Show parameter labels on template buildings
                        if (isTemplateBuilding && templateIndex !== null) {
                            const centerX = (finalX + w / 2) * SCALE;
                            const centerY = (finalY + h / 2) * SCALE;

                            // Get individual parameters (or fall back to base values)
                            const params = individualBuildingParams[templateIndex];
                            const baseFloors = effectiveMassingConfig.floors || currentSubtype?.floors || 3;
                            const baseClearHeight = effectiveMassingConfig.clearHeight || 36;
                            const baseFloorHeight = effectiveMassingConfig.floorHeight || 18;
                            let label = '';

                            // Get startLevel if set
                            const startLevel = params?.startLevel ?? 0;
                            const startLevelPrefix = startLevel > 0 ? `L${startLevel}→` : '';

                            if (buildingType === 'industrial') {
                                const height = params?.clearHeight ?? baseClearHeight;
                                label = `${startLevelPrefix}${height}'`;
                            } else if (buildingType === 'retail') {
                                const height = params?.floorHeight ?? baseFloorHeight;
                                label = `${startLevelPrefix}${height}'`;
                            } else if (['multifamily', 'hotel', 'singlefamily', 'datacenter', 'parking'].includes(buildingType)) {
                                const floors = params?.floors ?? baseFloors;
                                label = `${startLevelPrefix}${floors}F`;
                            }

                            if (label) {
                                ctx.save();
                                ctx.font = 'bold 14px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';

                                // Draw background for label
                                const metrics = ctx.measureText(label);
                                const padding = 4;
                                ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
                                ctx.fillRect(
                                    centerX - metrics.width / 2 - padding,
                                    centerY - 7 - padding,
                                    metrics.width + padding * 2,
                                    14 + padding * 2
                                );

                                // Draw label text
                                ctx.fillStyle = templateIndex === selectedTemplateBuilding ? '#ff6600' : '#ffffff';
                                ctx.fillText(label, centerX, centerY);
                                ctx.restore();
                            }

                            // Always show building number for reference
                            ctx.save();
                            ctx.font = '10px sans-serif';
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'top';
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
                            ctx.fillText(`#${templateIndex + 1}`, centerX, (finalY + 2) * SCALE);
                            ctx.restore();
                        }
                    };

                    // Track amenities for click detection
                    const amenities2D = [];

                    // Draw amenity (pool, garden, courtyard) with position offset support
                    const drawAmenity = (amenityId, x, y, w, h, type = 'pool') => {
                        // Apply amenity position offset if available
                        let finalX = x;
                        let finalY = y;
                        if (amenityPositions[amenityId]) {
                            const offset = amenityPositions[amenityId];
                            finalX = offset.x - w / 2;
                            finalY = offset.z - h / 2;
                        }

                        // Store for click detection
                        amenities2D.push({
                            id: amenityId,
                            x: finalX,
                            y: finalY,
                            w: w,
                            h: h,
                            origX: x,
                            origY: y,
                            type: type
                        });

                        ctx.beginPath();
                        if (type === 'circle') {
                            // Draw circle (for cluster green)
                            const radius = Math.min(w, h) / 2;
                            ctx.arc((finalX + w / 2) * SCALE, (finalY + h / 2) * SCALE, radius * SCALE, 0, Math.PI * 2);
                        } else {
                            ctx.rect(finalX * SCALE, finalY * SCALE, w * SCALE, h * SCALE);
                        }

                        // Color based on type
                        if (type === 'pool' || type === 'circle-pool') {
                            ctx.fillStyle = 'rgba(14, 165, 233, 0.3)';
                            ctx.strokeStyle = selectedAmenity === amenityId ? '#ff6600' : '#0ea5e9';
                        } else {
                            // Garden/green
                            ctx.fillStyle = 'rgba(34, 197, 94, 0.2)';
                            ctx.strokeStyle = selectedAmenity === amenityId ? '#ff6600' : '#22c55e';
                        }
                        ctx.fill();
                        ctx.lineWidth = selectedAmenity === amenityId ? 3 : 1;
                        ctx.stroke();

                        // Show amenity label
                        ctx.save();
                        ctx.font = '10px sans-serif';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillStyle = selectedAmenity === amenityId ? '#ff6600' : 'rgba(255, 255, 255, 0.7)';
                        const labelText = type === 'pool' || type === 'circle-pool' ? '🏊' : '🌳';
                        ctx.fillText(labelText, (finalX + w / 2) * SCALE, (finalY + h / 2) * SCALE);
                        ctx.restore();
                    };

                    if (massType === 'podium') {
                        // Podium: Full base + smaller tower footprint (matching 3D viewer)
                        const towerWidthPct = effectiveMassingConfig.towerWidthPct || 70;
                        const towerDepthPct = effectiveMassingConfig.towerDepthPct || 70;
                        const towerW = buildableW * (towerWidthPct / 100);
                        const towerD = buildableD * (towerDepthPct / 100);
                        const towerOffX = (buildableW - towerW) / 2;
                        const towerOffY = (buildableD - towerD) / 2;
                        // Podium footprint (template building 0) - uses lotCoverage only on width like 3D
                        drawRect(setbackX, setbackY, buildableW * lotCoverage, buildableD, podiumColor, '#6b7280', true, 0);
                        // Tower footprint (template building 1) - uses towerWidthPct/towerDepthPct like 3D
                        drawRect(setbackX + towerOffX, setbackY + towerOffY, towerW * lotCoverage, towerD, buildColor, '#8b5cf6', true, 1);

                    } else if (massType === 'wrap') {
                        // Wrap: Parking core with residential wrapping
                        const coreW = buildableW * 0.4;
                        const coreD = buildableD * 0.5;
                        const coreX = setbackX + (buildableW - coreW) / 2;
                        const coreY = setbackY + (buildableD - coreD) / 2;
                        const wrapThickness = buildableW * 0.2;
                        // Core (selectable as building 3)
                        drawRect(coreX, coreY, coreW, coreD, podiumColor, '#6b7280', true, 3);
                        // Wrap - left (selectable as building 0)
                        drawRect(setbackX, setbackY, wrapThickness, buildableD, buildColor, '#8b5cf6', true, 0);
                        // Wrap - right (selectable as building 1)
                        drawRect(setbackX + buildableW - wrapThickness, setbackY, wrapThickness, buildableD, buildColor, '#8b5cf6', true, 1);
                        // Wrap - back (selectable as building 2)
                        drawRect(setbackX + wrapThickness, setbackY + buildableD * 0.75, buildableW - wrapThickness * 2, buildableD * 0.25, buildColor, '#8b5cf6', true, 2);

                    } else if (massType === 'tower') {
                        // Tower: Large podium + tall narrow tower (matching 3D viewer)
                        const towerWidthPct = effectiveMassingConfig.towerWidthPct || 35;
                        const towerDepthPct = effectiveMassingConfig.towerDepthPct || 35;
                        const towerW = buildableW * (towerWidthPct / 100);
                        const towerD = buildableD * (towerDepthPct / 100);
                        const towerOffX = (buildableW - towerW) / 2;
                        const towerOffY = (buildableD - towerD) / 2;
                        // Podium (selectable as building 0) - 80% footprint like 3D
                        drawRect(setbackX, setbackY, buildableW * 0.8, buildableD * 0.8, podiumColor, '#6b7280', true, 0);
                        // Tower (selectable as building 1) - uses towerWidthPct/towerDepthPct
                        drawRect(setbackX + towerOffX, setbackY + towerOffY, towerW, towerD, buildColor, '#8b5cf6', true, 1);

                    } else if (massType === 'townhomes') {
                        // Townhomes: Multiple parallel rows (matching 3D viewer)
                        const unitW = effectiveMassingConfig.unitWidth || 24;
                        const unitD = effectiveMassingConfig.unitDepth || 50;
                        const rowSpacing = 30;
                        const rows = Math.floor(buildableD / (unitD + rowSpacing));
                        const unitsPerRow = Math.floor(buildableW / unitW);
                        const rowWidth = Math.min(buildableW * 0.9, unitsPerRow * unitW);
                        for (let r = 0; r < Math.min(rows, 4); r++) {
                            const rowY = setbackY + r * (unitD + rowSpacing) + 10;
                            drawRect(setbackX + 10, rowY, rowWidth, unitD * 0.8, buildColor, buildStroke, true, r);
                        }

                    } else if (massType === 'garden') {
                        // Garden: Surface parking + scattered buildings
                        drawRect(setbackX, setbackY, buildableW, buildableD, parkingColor, '#eab308');
                        const bldgW = buildableW * 0.25;
                        const bldgD = buildableD * 0.25;
                        const gap = 15;
                        drawRect(setbackX + gap, setbackY + gap, bldgW, bldgD, buildColor, buildStroke, true, 0);
                        drawRect(setbackX + buildableW - bldgW - gap, setbackY + gap, bldgW, bldgD, buildColor, buildStroke, true, 1);
                        drawRect(setbackX + gap, setbackY + buildableD - bldgD - gap, bldgW, bldgD, buildColor, buildStroke, true, 2);
                        drawRect(setbackX + buildableW - bldgW - gap, setbackY + buildableD - bldgD - gap, bldgW, bldgD, buildColor, buildStroke, true, 3);

                    } else if (massType === 'gurban') {
                        // Gurban: L-shaped building with surface parking
                        const armW = buildableW * 0.3;
                        const armD = buildableD * 0.35;
                        // Surface parking
                        drawRect(setbackX + armW, setbackY + armD, buildableW - armW, buildableD - armD, parkingColor, '#eab308');
                        // L-shape vertical arm (selectable as building 0)
                        drawRect(setbackX, setbackY, armW, buildableD, buildColor, buildStroke, true, 0);
                        // L-shape horizontal arm (selectable as building 1)
                        drawRect(setbackX + armW, setbackY, buildableW - armW, armD, buildColor, buildStroke, true, 1);

                        // ================================================================
                        // SINGLE-FAMILY BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'singlefamily' && massType === 'subdivision') {
                        // Subdivision: Traditional lot grid
                        const lotW = 60;
                        const lotD = 100;
                        const cols = Math.floor(buildableW / lotW);
                        const rows = Math.floor(buildableD / lotD);
                        let bldgIdx = 0;
                        for (let r = 0; r < rows; r++) {
                            for (let c = 0; c < cols; c++) {
                                const lotX = setbackX + c * lotW + 5;
                                const lotY = setbackY + r * lotD + 5;
                                // Draw lot
                                ctx.beginPath();
                                ctx.rect(lotX * SCALE, lotY * SCALE, (lotW - 10) * SCALE, (lotD - 10) * SCALE);
                                ctx.strokeStyle = '#22c55e55';
                                ctx.lineWidth = 1;
                                ctx.stroke();
                                // Draw house
                                drawRect(lotX + 10, lotY + 20, lotW - 30, lotD * 0.4, buildColor, buildStroke, true, bldgIdx);
                                bldgIdx++;
                            }
                        }
                    } else if (buildingType === 'singlefamily' && massType === 'cluster') {
                        // Cluster: Grouped around common green
                        const centerX = setbackX + buildableW / 2;
                        const centerY = setbackY + buildableD / 2;
                        const radius = Math.min(buildableW, buildableD) * 0.35;
                        // Central green (movable amenity)
                        const greenRadius = radius * 0.5;
                        drawAmenity('cluster-green', centerX - greenRadius, centerY - greenRadius, greenRadius * 2, greenRadius * 2, 'circle');
                        // Houses around
                        for (let i = 0; i < 8; i++) {
                            const angle = (i / 8) * Math.PI * 2;
                            const hx = centerX + Math.cos(angle) * radius - 15;
                            const hy = centerY + Math.sin(angle) * radius - 15;
                            drawRect(hx, hy, 30, 30, buildColor, buildStroke, true, i);
                        }
                    } else if (buildingType === 'singlefamily') {
                        // Courtyard or default: Units around shared court (matching 3D indexing)
                        // Courtyard green (movable amenity)
                        drawAmenity('courtyard-green', setbackX + 20, setbackY + 20, buildableW - 40, buildableD - 40, 'garden');
                        const houseW = 35;
                        const houseD = 40;
                        let bldgIdx = 0;
                        // Alternating top/bottom like 3D viewer
                        for (let i = 0; i < 3; i++) {
                            // Top row house
                            drawRect(setbackX + 30 + i * (houseW + 15), setbackY + 25, houseW, houseD, buildColor, buildStroke, true, bldgIdx);
                            bldgIdx++;
                            // Bottom row house
                            drawRect(setbackX + 30 + i * (houseW + 15), setbackY + buildableD - houseD - 25, houseW, houseD, buildColor, buildStroke, true, bldgIdx);
                            bldgIdx++;
                        }

                        // ================================================================
                        // INDUSTRIAL BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'industrial' && massType === 'bigbox') {
                        // Big Box: Single large warehouse (selectable as building 0)
                        drawRect(setbackX + 10, setbackY + 10, buildableW - 20, buildableD - 20, buildColor, buildStroke, true, 0);
                        // Dock doors on one side
                        for (let i = 0; i < 5; i++) {
                            const dockX = setbackX + 20 + i * ((buildableW - 40) / 5);
                            ctx.beginPath();
                            ctx.rect(dockX * SCALE, (setbackY + buildableD - 15) * SCALE, 15 * SCALE, 10 * SCALE);
                            ctx.fillStyle = '#6b7280';
                            ctx.fill();
                            ctx.strokeStyle = '#4b5563';
                            ctx.stroke();
                        }
                    } else if (buildingType === 'industrial' && massType === 'multibuilding') {
                        // Multi-Building: Multiple warehouses
                        const bldgW = (buildableW - 30) / 2;
                        const bldgD = (buildableD - 30) / 2;
                        drawRect(setbackX + 10, setbackY + 10, bldgW, bldgD, buildColor, buildStroke, true, 0);
                        drawRect(setbackX + bldgW + 20, setbackY + 10, bldgW, bldgD, buildColor, buildStroke, true, 1);
                        drawRect(setbackX + 10, setbackY + bldgD + 20, bldgW, bldgD, buildColor, buildStroke, true, 2);
                        drawRect(setbackX + bldgW + 20, setbackY + bldgD + 20, bldgW, bldgD, buildColor, buildStroke, true, 3);
                    } else if (buildingType === 'industrial' && massType === 'podium') {
                        // Podium: Warehouse over podium base
                        // Podium base (template building 0)
                        drawRect(setbackX, setbackY, buildableW, buildableD, podiumColor, '#6b7280', true, 0);
                        // Warehouse above (template building 1)
                        const warehouseInset = 15;
                        drawRect(setbackX + warehouseInset, setbackY + warehouseInset, buildableW - warehouseInset * 2, buildableD - warehouseInset * 2, buildColor, buildStroke, true, 1);
                    } else if (buildingType === 'industrial') {
                        // Cross-Dock: Through-loading facility
                        const dockWidth = buildableW * 0.15;
                        // Main warehouse (selectable as building 0)
                        drawRect(setbackX + dockWidth, setbackY + 10, buildableW - dockWidth * 2, buildableD - 20, buildColor, buildStroke, true, 0);
                        // Dock areas (not selectable)
                        drawRect(setbackX, setbackY + 10, dockWidth, buildableD - 20, podiumColor, '#6b7280');
                        drawRect(setbackX + buildableW - dockWidth, setbackY + 10, dockWidth, buildableD - 20, podiumColor, '#6b7280');

                        // ================================================================
                        // HOTEL BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'hotel' && massType === 'courtyard') {
                        // U-shape around courtyard (matching 3D viewer)
                        const armThick = buildableW * 0.25;
                        // Left wing (selectable as building 0)
                        drawRect(setbackX, setbackY, armThick, buildableD, buildColor, buildStroke, true, 0);
                        // Right wing (selectable as building 1)
                        drawRect(setbackX + buildableW - armThick, setbackY, armThick, buildableD, buildColor, buildStroke, true, 1);
                        // Back connector (selectable as building 2) - uses same width calculation as 3D
                        drawRect(setbackX + armThick, setbackY, buildableW - armThick * 2, buildableD * 0.3, buildColor, buildStroke, true, 2);
                        // Courtyard pool (movable amenity)
                        const courtW = buildableW - armThick * 2 - 20;
                        const courtD = buildableD * 0.5 - 20;
                        drawAmenity('hotel-pool', setbackX + armThick + 10, setbackY + buildableD * 0.35, courtW, courtD, 'pool');
                    } else if (buildingType === 'hotel' && massType === 'tower') {
                        // Vertical tower hotel
                        const towerW = buildableW * 0.5;
                        const towerD = buildableD * 0.5;
                        // Podium (selectable as building 0)
                        drawRect(setbackX, setbackY, buildableW * 0.8, buildableD * 0.4, podiumColor, '#6b7280', true, 0);
                        // Tower (selectable as building 1)
                        drawRect(setbackX + (buildableW - towerW) / 2, setbackY + 10, towerW, towerD, buildColor, buildStroke, true, 1);
                    } else if (buildingType === 'hotel') {
                        // Linear: Bar building (selectable as building 0)
                        drawRect(setbackX + 10, setbackY + buildableD * 0.3, buildableW - 20, buildableD * 0.4, buildColor, buildStroke, true, 0);
                        // Pool area in front (movable amenity)
                        drawAmenity('hotel-pool', setbackX + buildableW * 0.3, setbackY + buildableD * 0.75, buildableW * 0.4, buildableD * 0.15, 'pool');

                        // ================================================================
                        // RETAIL BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'retail' && massType === 'lshaped') {
                        // L-Shaped strip center
                        drawRect(setbackX, setbackY, buildableW, buildableD, parkingColor, '#eab308');
                        // Vertical strip (selectable as building 0)
                        drawRect(setbackX, setbackY, buildableW * 0.2, buildableD, buildColor, buildStroke, true, 0);
                        // Horizontal strip (selectable as building 1)
                        drawRect(setbackX, setbackY + buildableD - buildableD * 0.25, buildableW, buildableD * 0.25, buildColor, buildStroke, true, 1);
                    } else if (buildingType === 'retail' && massType === 'ushaped') {
                        // U-Shaped with anchor
                        drawRect(setbackX, setbackY, buildableW, buildableD, parkingColor, '#eab308');
                        // Left wing (selectable as building 0)
                        drawRect(setbackX, setbackY, buildableW * 0.2, buildableD, buildColor, buildStroke, true, 0);
                        // Right wing (selectable as building 1)
                        drawRect(setbackX + buildableW * 0.8, setbackY, buildableW * 0.2, buildableD, buildColor, buildStroke, true, 1);
                        // Anchor store at back (selectable as building 2)
                        drawRect(setbackX + buildableW * 0.2, setbackY, buildableW * 0.6, buildableD * 0.35, buildColor, buildStroke, true, 2);
                    } else if (buildingType === 'retail' && massType === 'podium') {
                        // Retail Podium: Retail over parking podium
                        // Podium base (template building 0)
                        drawRect(setbackX, setbackY, buildableW, buildableD, podiumColor, '#6b7280', true, 0);
                        // Retail above (template building 1)
                        const retailInset = 10;
                        drawRect(setbackX + retailInset, setbackY + retailInset, buildableW - retailInset * 2, buildableD - retailInset * 2, buildColor, buildStroke, true, 1);
                    } else if (buildingType === 'retail') {
                        // Inline strip (selectable as building 0) - default retail massing
                        drawRect(setbackX, setbackY, buildableW, buildableD, parkingColor, '#eab308');
                        drawRect(setbackX + 10, setbackY + buildableD * 0.7, buildableW - 20, buildableD * 0.25, buildColor, buildStroke, true, 0);

                        // ================================================================
                        // DATACENTER BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'datacenter' && massType === 'campus') {
                        // Multi-building campus
                        const bldgW = (buildableW - 40) / 2;
                        const bldgD = (buildableD - 40) / 2;
                        drawRect(setbackX + 10, setbackY + 10, bldgW, bldgD, buildColor, buildStroke, true, 0);
                        drawRect(setbackX + bldgW + 30, setbackY + 10, bldgW, bldgD, buildColor, buildStroke, true, 1);
                        drawRect(setbackX + 10, setbackY + bldgD + 30, bldgW, bldgD, buildColor, buildStroke, true, 2);
                        drawRect(setbackX + bldgW + 30, setbackY + bldgD + 30, bldgW, bldgD, buildColor, buildStroke, true, 3);
                    } else if (buildingType === 'datacenter' && massType === 'podium') {
                        // Datacenter Podium: Data center over podium base
                        // Podium base (template building 0)
                        drawRect(setbackX, setbackY, buildableW, buildableD, podiumColor, '#6b7280', true, 0);
                        // Data hall above (template building 1)
                        const dcInset = 15;
                        drawRect(setbackX + dcInset, setbackY + dcInset, buildableW - dcInset * 2, buildableD - dcInset * 2, buildColor, buildStroke, true, 1);
                        // Cooling units on podium
                        for (let i = 0; i < 3; i++) {
                            const coolX = setbackX + buildableW - 30;
                            const coolY = setbackY + 25 + i * (buildableD - 50) / 2;
                            ctx.beginPath();
                            ctx.rect(coolX * SCALE, coolY * SCALE, 15 * SCALE, 12 * SCALE);
                            ctx.fillStyle = '#4b5563';
                            ctx.fill();
                        }
                    } else if (buildingType === 'datacenter') {
                        // Single Hall (selectable as building 0) - default datacenter massing
                        drawRect(setbackX + 15, setbackY + 15, buildableW - 30, buildableD - 30, buildColor, buildStroke, true, 0);
                        // Cooling units
                        for (let i = 0; i < 4; i++) {
                            const coolX = setbackX + buildableW - 35;
                            const coolY = setbackY + 30 + i * (buildableD - 60) / 3;
                            ctx.beginPath();
                            ctx.rect(coolX * SCALE, coolY * SCALE, 20 * SCALE, 15 * SCALE);
                            ctx.fillStyle = '#4b5563';
                            ctx.fill();
                        }

                        // ================================================================
                        // PARKING BUILDING TYPE MASSINGS
                        // ================================================================
                    } else if (buildingType === 'parking' && massType === 'surface') {
                        // ================================================================
                        // TESTFIT-STYLE SURFACE PARKING LAYOUT
                        // Uses shared parkingLayout for exact sync with 3D view
                        // Like Rhino: both views show the same geometry from different angles
                        // ================================================================

                        // Skip parking-specific rendering if no parking layout calculated
                        // But still allow custom aisles to be drawn (they don't depend on parkingLayout)
                        const hasParkingLayout = !!parkingLayout;

                        if (hasParkingLayout) {
                            // === USE SHARED LAYOUT (synced with 3D view) ===
                            const {
                                stallWidth, stallDepth, aisleWidth, driveType, effectiveAisleWidth,
                                loopWidth, loopInset,
                                setbackX: layoutSetbackX, setbackY: layoutSetbackY,
                                buildableW: layoutBuildableW, buildableD: layoutBuildableD,
                                loopOX, loopOY, loopTotalW, loopTotalD,
                                loopInnerX, loopInnerY, loopInnerW, loopInnerH,
                                moduleDepth, numModules, stallsPerRow,
                                moduleGridDepth, remainingD, endRowFits,
                                totalStalls,
                                // Polygon-based geometry for irregular shapes
                                isIrregular,
                                loopOuterPolygon,
                                loopInnerPolygon,
                                interiorPolygon,
                                stallPositions,
                                // Angled parking geometry
                                parkingAngle: layoutParkingAngle,
                                angledGeometry,
                                effectiveStallModuleWidth,
                                effectiveStallDepth
                            } = parkingLayout;

                            // Helper function to draw a polygon path
                            const drawPolygonPath = (polygon, close = true) => {
                                if (!polygon || polygon.length < 3) return;
                                ctx.beginPath();
                                ctx.moveTo(polygon[0].x * SCALE, polygon[0].y * SCALE);
                                for (let i = 1; i < polygon.length; i++) {
                                    ctx.lineTo(polygon[i].x * SCALE, polygon[i].y * SCALE);
                                }
                                if (close) ctx.closePath();
                            };

                            // Additional visual options from config
                            const compactWidth = effectiveMassingConfig.compactWidth || 8.5;
                            const compactDepth = effectiveMassingConfig.compactDepth || 16;
                            const parkingAngle = effectiveMassingConfig.parkingAngle || 90;
                            // SIMPLIFIED: Default to NO landscape islands and NO end islands for cleaner view
                            // User must explicitly enable these features
                            const hasLandscaping = effectiveMassingConfig.hasLandscaping === true;
                            const landscapeInterval = effectiveMassingConfig.landscapeInterval || 12; // SYNCED with 3D view
                            const endIslands = effectiveMassingConfig.endIslands === true; // Default OFF
                            const hasEntryExit = effectiveMassingConfig.hasEntryExit !== false;
                            const entryExitType = effectiveMassingConfig.entryExitType || 'standard';
                            const fireLane = effectiveMassingConfig.fireLane !== false;
                            const perimeterWidth = effectiveMassingConfig.perimeterWidth || 24;
                            const hasGateBooth = effectiveMassingConfig.hasGateBooth !== false;
                            const hasCrosswalk = effectiveMassingConfig.hasCrosswalk !== false;
                            const hasAda = effectiveMassingConfig.hasAda !== false;
                            const adaExtra = effectiveMassingConfig.adaExtra || 0; // Additional ADA beyond code minimum
                            const adaPosition = effectiveMassingConfig.adaPosition || 0; // ADA cluster starting position (stall index)
                            const adaRow = effectiveMassingConfig.adaRow || 0; // ADA cluster row index (0 = first row)
                            const hasCrossAisle = effectiveMassingConfig.hasCrossAisle === true; // SYNCED with 3D - requires explicit true
                            const showStallNumbers = effectiveMassingConfig.showStallNumbers !== false; // SYNCED with 3D
                            const showLightPoles = effectiveMassingConfig.showLightPoles !== false; // SYNCED with 3D

                            // Stall mix percentages
                            const standardPct = effectiveMassingConfig.standardPct || 85;
                            const compactPct = effectiveMassingConfig.compactPct || 10;
                            const adaPct = effectiveMassingConfig.adaPct || 3; // Legacy - overridden if hasAda is true
                            const evPct = effectiveMassingConfig.evPct || 2;

                            // === COLOR PALETTE (Testfit-style) ===
                            const colors = {
                                asphalt: 'rgba(55, 65, 81, 0.6)',      // Dark gray pavement
                                aisle: '#4b5563',                       // Same as perimeter loop (OPAQUE)
                                loop: '#4b5563',                        // Perimeter loop drive (OPAQUE - no layering artifacts)
                                fireLane: 'rgba(239, 68, 68, 0.08)',   // Light red fire lane
                                fireLaneStroke: '#ef4444',              // Red border
                                standard: '#fbbf24',                    // Yellow - standard
                                compact: '#a855f7',                     // Purple - compact
                                ada: '#3b82f6',                         // Blue - ADA
                                ev: '#22c55e',                          // Green - EV
                                landscape: 'rgba(34, 197, 94, 0.5)',   // Green islands
                                tree: '#166534',                        // Dark green trees
                                entry: '#22c55e',                       // Green entry
                                exit: '#ef4444',                        // Red exit
                                arrow: '#ffffff',                       // Solid white arrows
                            };

                            // Use standard stall values for layout (shared from parkingLayout)
                            // For angled parking, use projected dimensions from angledGeometry
                            const effStallWidth = effectiveStallModuleWidth || stallWidth;
                            const effStallDepth = effectiveStallDepth || stallDepth;
                            const optAisleWidth = effectiveAisleWidth;
                            const isAngledParking = layoutParkingAngle && layoutParkingAngle !== 90;

                            // Helper function to draw a parallelogram stall for angled parking
                            const drawAngledStall = (corners, fillColor, strokeColor) => {
                                if (!corners || corners.length < 4) return;
                                ctx.beginPath();
                                ctx.moveTo(corners[0].x * SCALE, corners[0].y * SCALE);
                                for (let i = 1; i < corners.length; i++) {
                                    ctx.lineTo(corners[i].x * SCALE, corners[i].y * SCALE);
                                }
                                ctx.closePath();
                                ctx.fillStyle = fillColor;
                                ctx.fill();
                                ctx.strokeStyle = strokeColor;
                                ctx.lineWidth = 2;
                                ctx.stroke();
                            };

                            // Get the stall corners generator from angledGeometry
                            const getStallCorners = angledGeometry?.getStallCorners || null;

                            // === IRREGULAR SHAPE SUPPORT ===
                            // Create parking boundary polygon by insetting the site boundary
                            // Uses the working insetPolygon with average setback + loop offset
                            const avgSetbackForParking = (setbacks.front + setbacks.side + setbacks.rear) / 3;
                            const parkingLoopOffset = loopInset + loopWidth;
                            const parkingBoundary = insetPolygon(boundary, avgSetbackForParking + parkingLoopOffset);

                            // Check if lot is irregular (more than 4 vertices or non-rectangular)
                            const isIrregularLot = boundary.length > 4 || (() => {
                                if (boundary.length !== 4) return true;
                                // Check if angles are approximately 90 degrees
                                for (let i = 0; i < 4; i++) {
                                    const prev = boundary[(i + 3) % 4];
                                    const curr = boundary[i];
                                    const next = boundary[(i + 1) % 4];
                                    const dx1 = curr.x - prev.x, dy1 = curr.y - prev.y;
                                    const dx2 = next.x - curr.x, dy2 = next.y - curr.y;
                                    const dot = dx1 * dx2 + dy1 * dy2;
                                    const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);
                                    const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
                                    const cosAngle = Math.abs(dot / (len1 * len2 + 0.001));
                                    if (cosAngle > 0.1) return true; // Not perpendicular
                                }
                                return false;
                            })();

                            // Interior parking area - inside the perimeter loop
                            // Perimeter stalls (facing outward) will be drawn on the OUTSIDE of the loop
                            // Check if area is too small (from shared layout)
                            const parkingAreaTooSmall = numModules === 0 || stallsPerRow === 0;

                            if (parkingAreaTooSmall) {
                                // Draw just the base asphalt
                                ctx.beginPath();
                                ctx.rect(layoutSetbackX * SCALE, layoutSetbackY * SCALE, layoutBuildableW * SCALE, layoutBuildableD * SCALE);
                                ctx.fillStyle = 'rgba(55, 65, 81, 0.6)';
                                ctx.fill();

                                // Show "Area Too Small" message
                                ctx.save();
                                ctx.fillStyle = '#ffffff';
                                ctx.font = 'bold 14px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                const centerX = (layoutSetbackX + layoutBuildableW / 2) * SCALE;
                                const centerY = (layoutSetbackY + layoutBuildableD / 2) * SCALE;
                                ctx.fillText('Area Too Small for Parking', centerX, centerY);
                                ctx.font = '12px sans-serif';
                                ctx.fillText(`Need 60'×60' min, have ${Math.round(loopInnerW)}'×${Math.round(loopInnerH)}'`, centerX, centerY + 20);
                                ctx.restore();
                            }

                            // Only draw parking layout if area is large enough
                            if (!parkingAreaTooSmall) {

                                // === USE SHARED PARKING LAYOUT (synced with 3D view) ===
                                // All layout values come from parkingLayout for exact sync

                                // Map shared values to local names for existing code
                                const interiorX = loopInnerX;
                                const interiorY = loopInnerY;
                                const interiorW = loopInnerW;
                                const interiorH = loopInnerH;

                                // Use shared module calculations
                                const interiorStallsPerRow = stallsPerRow;
                                const interiorModules = numModules;
                                const interiorModuleGridDepth = moduleGridDepth;
                                const interiorRemainingD = remainingD;
                                const interiorEndRowFits = endRowFits;

                                // Stall counts from shared layout
                                const interiorDoubleLoadedStalls = stallsPerRow * 2 * numModules;
                                const interiorEndRowStalls = endRowFits ? stallsPerRow : 0;
                                const expectedTotalStalls = totalStalls;

                                // Debug logging removed for production

                                // Position interior bay
                                const bayX = interiorX;
                                const bayY = interiorY;
                                const bayW = stallsPerRow * effStallWidth;
                                const bayD = moduleGridDepth;

                                // Cross-aisle for very wide lots (> 200ft) - SYNCED with 3D view logic
                                // Now supports 3 modes:
                                // - 'auto': Auto-detect based on lot width and shape (original behavior)
                                // - 'manual': Only use manually placed spines
                                // - 'force': Force cross-aisle even for irregular shapes
                                let useCrossAisle = false;
                                let autoSpinePositions = []; // For auto-detected spines in irregular shapes

                                if (crossAisleMode === 'auto') {
                                    // Original logic: width > 200ft AND rectangular
                                    useCrossAisle = hasCrossAisle && layoutBuildableW > 200 && !isIrregular;
                                } else if (crossAisleMode === 'force') {
                                    // Force mode: Enable cross-aisle even for irregular shapes
                                    useCrossAisle = hasCrossAisle && layoutBuildableW > 200;
                                    // For irregular shapes in force mode, auto-detect rectangular sub-regions
                                    if (isIrregular && loopInnerPolygon && loopInnerPolygon.length >= 3) {
                                        autoSpinePositions = findRectangularSubRegions(loopInnerPolygon, 150, effectiveAisleWidth);
                                    }
                                }
                                // 'manual' mode: useCrossAisle stays false, only manualSpines are rendered

                                const spineWidth = (useCrossAisle || manualSpines.length > 0) ? effectiveAisleWidth : 0;

                                // === DRAW BASE ASPHALT ===
                                // For irregular shapes, use the actual boundary polygon
                                // For rectangular, use the bounding box
                                ctx.fillStyle = colors.asphalt;
                                if (isIrregular && loopOuterPolygon && loopOuterPolygon.length >= 3) {
                                    // Draw the asphalt following the boundary shape
                                    drawPolygonPath(loopOuterPolygon);
                                    ctx.fill();
                                } else {
                                    // Rectangular fallback
                                    ctx.beginPath();
                                    ctx.rect(layoutSetbackX * SCALE, layoutSetbackY * SCALE, layoutBuildableW * SCALE, layoutBuildableD * SCALE);
                                    ctx.fill();
                                }

                                // === DRAW PERIMETER CIRCULATION LOOP ===
                                // For irregular shapes: use polygon path
                                // For rectangular: use rounded rectangles
                                const cornerRadius = Math.min(20, loopWidth); // 20ft radius or loop width, whichever is smaller

                                // Perimeter loop outer rectangle (from shared layout)
                                const loopOuter = {
                                    x: loopOX,
                                    y: loopOY,
                                    w: loopTotalW,
                                    h: loopTotalD
                                };

                                // Draw perimeter loop with rounded corners for smooth vehicle turning
                                ctx.fillStyle = colors.loop;

                                // Helper function to draw rounded rectangle path
                                const drawRoundedRectPath = (x, y, w, h, r) => {
                                    ctx.beginPath();
                                    ctx.moveTo((x + r) * SCALE, y * SCALE);
                                    // Top edge
                                    ctx.lineTo((x + w - r) * SCALE, y * SCALE);
                                    // Top-right corner
                                    ctx.arcTo((x + w) * SCALE, y * SCALE, (x + w) * SCALE, (y + r) * SCALE, r * SCALE);
                                    // Right edge
                                    ctx.lineTo((x + w) * SCALE, (y + h - r) * SCALE);
                                    // Bottom-right corner
                                    ctx.arcTo((x + w) * SCALE, (y + h) * SCALE, (x + w - r) * SCALE, (y + h) * SCALE, r * SCALE);
                                    // Bottom edge
                                    ctx.lineTo((x + r) * SCALE, (y + h) * SCALE);
                                    // Bottom-left corner
                                    ctx.arcTo(x * SCALE, (y + h) * SCALE, x * SCALE, (y + h - r) * SCALE, r * SCALE);
                                    // Left edge
                                    ctx.lineTo(x * SCALE, (y + r) * SCALE);
                                    // Top-left corner
                                    ctx.arcTo(x * SCALE, y * SCALE, (x + r) * SCALE, y * SCALE, r * SCALE);
                                    ctx.closePath();
                                };

                                // Draw perimeter loop (the driving ring around parking bays)
                                // Only draw auto-generated loop if no custom aisles exist
                                if (drawnAisles.length === 0) {
                                    ctx.fillStyle = colors.loop;

                                    if (isIrregular && loopOuterPolygon && loopInnerPolygon) {
                                        // === IRREGULAR SHAPE: Use polygon paths ===
                                        // Draw outer polygon
                                        drawPolygonPath(loopOuterPolygon);
                                        ctx.fill();

                                        // Cut out inner polygon (create the loop ring)
                                        ctx.save();
                                        ctx.globalCompositeOperation = 'destination-out';
                                        drawPolygonPath(loopInnerPolygon);
                                        ctx.fill();
                                        ctx.restore();

                                        // Redraw with proper composite to get correct loop color
                                        ctx.fillStyle = colors.loop;
                                        ctx.beginPath();
                                        // Draw outer path
                                        ctx.moveTo(loopOuterPolygon[0].x * SCALE, loopOuterPolygon[0].y * SCALE);
                                        for (let i = 1; i < loopOuterPolygon.length; i++) {
                                            ctx.lineTo(loopOuterPolygon[i].x * SCALE, loopOuterPolygon[i].y * SCALE);
                                        }
                                        ctx.closePath();
                                        // Draw inner path (reverse direction for hole)
                                        ctx.moveTo(loopInnerPolygon[0].x * SCALE, loopInnerPolygon[0].y * SCALE);
                                        for (let i = loopInnerPolygon.length - 1; i >= 0; i--) {
                                            ctx.lineTo(loopInnerPolygon[i].x * SCALE, loopInnerPolygon[i].y * SCALE);
                                        }
                                        ctx.closePath();
                                        ctx.fill('evenodd');
                                    } else {
                                        // === RECTANGULAR SHAPE: Use rounded rectangles ===
                                        const innerR = Math.max(cornerRadius - loopWidth, 2);

                                        // Draw outer rounded rectangle
                                        drawRoundedRectPath(loopOuter.x, loopOuter.y, loopOuter.w, loopOuter.h, cornerRadius);
                                        ctx.fill();

                                        // Cut out inner area (create the loop shape)
                                        ctx.save();
                                        ctx.globalCompositeOperation = 'destination-out';
                                        drawRoundedRectPath(
                                            loopOuter.x + loopWidth,
                                            loopOuter.y + loopWidth,
                                            loopOuter.w - loopWidth * 2,
                                            loopOuter.h - loopWidth * 2,
                                            innerR
                                        );
                                        ctx.fill();
                                        ctx.restore();

                                        // Redraw the loop with proper fill (after cutting)
                                        ctx.fillStyle = colors.loop;
                                        drawRoundedRectPath(loopOuter.x, loopOuter.y, loopOuter.w, loopOuter.h, cornerRadius);
                                        // Use fill with evenodd to create the ring shape
                                        ctx.save();
                                        drawRoundedRectPath(
                                            loopOuter.x + loopWidth,
                                            loopOuter.y + loopWidth,
                                            loopOuter.w - loopWidth * 2,
                                            loopOuter.h - loopWidth * 2,
                                            innerR
                                        );
                                        ctx.clip('evenodd');
                                        ctx.fillRect(loopOuter.x * SCALE, loopOuter.y * SCALE, loopOuter.w * SCALE, loopOuter.h * SCALE);
                                        ctx.restore();
                                    }
                                } // End of drawnAisles.length === 0 check for perimeter loop

                                // === DRAW FIRE LANE MARKING (if enabled) ===
                                // Fire lane marking goes on the perimeter circulation loop only
                                // Real fire lanes are marked with curb paint and "NO PARKING FIRE LANE" text
                                // Only show if no custom aisles (they replace the auto-generated loop)
                                if (fireLane && drawnAisles.length === 0) {
                                    ctx.save();
                                    ctx.strokeStyle = colors.fireLaneStroke;
                                    ctx.lineWidth = 3;

                                    if (isIrregular && loopOuterPolygon && loopInnerPolygon) {
                                        // Draw polygon outlines for fire lane
                                        drawPolygonPath(loopOuterPolygon);
                                        ctx.stroke();
                                        drawPolygonPath(loopInnerPolygon);
                                        ctx.stroke();
                                    } else {
                                        // Draw with rounded corners (synced with 3D rectangular approach)
                                        drawRoundedRectPath(loopOuter.x, loopOuter.y, loopOuter.w, loopOuter.h, cornerRadius);
                                        ctx.stroke();

                                        const innerLoopX = loopOuter.x + loopWidth;
                                        const innerLoopY = loopOuter.y + loopWidth;
                                        const innerLoopW = loopOuter.w - loopWidth * 2;
                                        const innerLoopH = loopOuter.h - loopWidth * 2;
                                        const innerR2 = Math.max(cornerRadius - loopWidth, 2);
                                        drawRoundedRectPath(innerLoopX, innerLoopY, innerLoopW, innerLoopH, innerR2);
                                        ctx.stroke();
                                    }

                                    ctx.restore();

                                    // "NO PARKING FIRE LANE" text centered in each segment
                                    ctx.save();
                                    ctx.fillStyle = colors.fireLaneStroke;
                                    ctx.font = 'bold 7px sans-serif';
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';

                                    // Use polygon centroid for irregular shapes, otherwise use loopOuter bounds
                                    const loopCenterX = isIrregular && loopOuterPolygon
                                        ? polygonCentroid(loopOuterPolygon).x
                                        : loopOuter.x + loopOuter.w / 2;
                                    const loopTopY = isIrregular && loopOuterPolygon
                                        ? polygonBounds(loopOuterPolygon).minY + loopWidth / 2
                                        : loopOuter.y + loopWidth / 2;
                                    const loopBottomY = isIrregular && loopOuterPolygon
                                        ? polygonBounds(loopOuterPolygon).maxY - loopWidth / 2
                                        : loopOuter.y + loopOuter.h - loopWidth / 2;

                                    // Top segment
                                    ctx.fillText('🚒 NO PARKING - FIRE LANE 🚒', loopCenterX * SCALE, loopTopY * SCALE);
                                    // Bottom segment
                                    ctx.fillText('🚒 NO PARKING - FIRE LANE 🚒', loopCenterX * SCALE, loopBottomY * SCALE);
                                    ctx.restore();
                                }

                                // === SAVE ENTRY/EXIT PARAMETERS FOR DRAWING OUTSIDE CLIP ===
                                // Entry/exit needs to extend beyond the site boundary into the street
                                // Parameters are saved here and drawn after ctx.restore() for the boundary clip
                                let entryExitParams = null;
                                if (hasEntryExit) {
                                    // Entry/Exit Configuration
                                    const laneWidth = 12;           // Single lane width (ft)
                                    const throatDepth = 45;         // Increased depth for all features
                                    const flareWidth = 4;           // Reduced flare for cleaner look
                                    const turnRadius = 12;          // Inside turn radius
                                    const queueSpaces = 2;          // Number of cars that can queue
                                    const dividerWidth = 3;         // Narrower median

                                    // Find the best edge for entry/exit (prefer bottom/south edge)
                                    // For irregular shapes, find the southernmost horizontal edge
                                    let entryEdgeMidX, entryEdgeMidY;
                                    let entryEdgeAngle = Math.PI / 2; // Facing down (outward from bottom edge)
                                    let entryEdgeLength;

                                    if (isIrregular && loopOuterPolygon && loopOuterPolygon.length >= 3) {
                                        // Find the southernmost (highest Y) horizontal edge
                                        let bestEdge = null;
                                        let maxY = -Infinity;

                                        for (let i = 0; i < loopOuterPolygon.length; i++) {
                                            const p1 = loopOuterPolygon[i];
                                            const p2 = loopOuterPolygon[(i + 1) % loopOuterPolygon.length];
                                            const midY = (p1.y + p2.y) / 2;
                                            const edgeLen = Math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2);

                                            // Check if this edge is roughly horizontal and long enough
                                            const dx = Math.abs(p2.x - p1.x);
                                            const dy = Math.abs(p2.y - p1.y);
                                            const isHorizontal = dx > dy * 2;

                                            if (isHorizontal && edgeLen >= laneWidth * 2 + 10 && midY > maxY) {
                                                maxY = midY;
                                                bestEdge = { p1, p2, midX: (p1.x + p2.x) / 2, midY, edgeLen };
                                            }
                                        }

                                        if (bestEdge) {
                                            entryEdgeMidX = bestEdge.midX;
                                            entryEdgeMidY = bestEdge.midY;
                                            entryEdgeLength = bestEdge.edgeLen;
                                        } else {
                                            // Fallback to polygon bounds
                                            const bounds = {
                                                minX: Math.min(...loopOuterPolygon.map(p => p.x)),
                                                maxX: Math.max(...loopOuterPolygon.map(p => p.x)),
                                                maxY: Math.max(...loopOuterPolygon.map(p => p.y))
                                            };
                                            entryEdgeMidX = (bounds.minX + bounds.maxX) / 2;
                                            entryEdgeMidY = bounds.maxY;
                                            entryEdgeLength = bounds.maxX - bounds.minX;
                                        }
                                    } else {
                                        // Regular rectangle - use loopOuter bounds
                                        entryEdgeMidX = loopOuter.x + loopOuter.w / 2;
                                        entryEdgeMidY = loopOuter.y + loopOuter.h;
                                        entryEdgeLength = loopOuter.w;
                                    }

                                    // Position entry/exit centered on the bottom edge
                                    // Entry/exit connects at the edge and extends OUTWARD (perpendicular to edge)
                                    const centerX = entryEdgeMidX;
                                    const centerY = entryEdgeMidY;
                                    const outwardAngle = entryEdgeAngle;

                                    // Entry lane local positions (used by all types)
                                    // For right-hand traffic (US/ITE standard):
                                    // - Entry should be on driver's RIGHT when entering from street
                                    // - Exit should be on driver's RIGHT when exiting to street
                                    // In plan view (looking down): Entry = RIGHT side, Exit = LEFT side
                                    // After rotation transform: positive X = RIGHT visually, negative X = LEFT visually
                                    const entryLaneLocalX = dividerWidth / 2; // RIGHT side (positive X)
                                    const exitLaneLocalX = -dividerWidth / 2 - laneWidth; // LEFT side (negative X)

                                    // Save all parameters for drawing after clip is removed
                                    entryExitParams = {
                                        entryExitType,
                                        centerX,
                                        centerY,
                                        outwardAngle,
                                        laneWidth,
                                        throatDepth,
                                        flareWidth,
                                        dividerWidth,
                                        loopWidth,
                                        entryLaneLocalX,
                                        exitLaneLocalX,
                                        hasGateBooth,
                                        hasCrosswalk,
                                        colors,
                                        SCALE
                                    };
                                }

                                // === DRAW PARKING BAY INTERIOR ===
                                // Use polygon for irregular shapes, rectangle for regular
                                ctx.fillStyle = colors.asphalt;
                                if (isIrregular && interiorPolygon && interiorPolygon.length >= 3) {
                                    drawPolygonPath(interiorPolygon);
                                    ctx.fill();
                                } else {
                                    ctx.beginPath();
                                    ctx.rect(interiorX * SCALE, interiorY * SCALE, interiorW * SCALE, interiorH * SCALE);
                                    ctx.fill();
                                }

                                // === SINGLE PARKING SECTION (no cross-aisle for simplicity) ===
                                // Cross-aisle only makes sense for very wide lots (>200ft)
                                let parkingSections = [
                                    { x: bayX, w: bayW, stallsPerRow: interiorStallsPerRow, side: 'full', spineX: null }
                                ];

                                // Spine position (center of bay, only used if cross-aisle is enabled)
                                const spineX = bayX + bayW / 2;

                                // === STALL COUNTERS ===
                                let counts = { standard: 0, compact: 0, ada: 0, adaVan: 0, ev: 0, total: 0 };
                                let stallIndex = 0;
                                let stallsRemovedByAisles = 0; // Track stalls skipped due to custom aisle collision

                                // Calculate total stalls across all sections (double-loaded modules)
                                const totalStallsPerModule = parkingSections.reduce((sum, sec) => sum + sec.stallsPerRow * 2, 0);
                                const totalDoubleLoadedStalls = totalStallsPerModule * interiorModules;

                                // Add end row stalls if there's remaining depth
                                const endRowStallCount = interiorEndRowFits ? interiorStallsPerRow : 0;
                                const totalPossibleStalls = totalDoubleLoadedStalls + endRowStallCount;

                                // Calculate stall type counts
                                // ADA: Use code-based calculation if hasAda is enabled, plus any additional (adaExtra)
                                const adaCodeRequirements = hasAda ? calculateAdaRequired(totalPossibleStalls) : { total: 0, vanAccessible: 0, standard: 0 };
                                // Add extra ADA stalls (for medical facilities, senior housing, etc.)
                                const totalAdaStalls = adaCodeRequirements.total + adaExtra;
                                // Recalculate van accessible for total (1 per 6, minimum 1 if any ADA)
                                const totalVanAccessible = totalAdaStalls > 0 ? Math.max(1, Math.ceil(totalAdaStalls / 6)) : 0;
                                const adaStalls = totalAdaStalls;
                                const adaVanStalls = totalVanAccessible;
                                const adaStandardStalls = totalAdaStalls - totalVanAccessible;
                                const evStalls = Math.ceil(totalPossibleStalls * evPct / 100);
                                const compactStalls = Math.ceil(totalPossibleStalls * compactPct / 100);

                                // === STORE PARKING LAYOUT FOR ADA PLACEMENT ===
                                // Store all row geometries so click handler can detect any row
                                const allRows = [];
                                for (let m = 0; m < interiorModules; m++) {
                                    const moduleY = bayY + m * moduleDepth;
                                    // Top row of module
                                    allRows.push({
                                        rowIndex: m * 2,
                                        y: moduleY,
                                        height: effStallDepth
                                    });
                                    // Bottom row of module
                                    allRows.push({
                                        rowIndex: m * 2 + 1,
                                        y: moduleY + effStallDepth + optAisleWidth,
                                        height: effStallDepth
                                    });
                                }

                                // Add end row if it fits (single-loaded row at the end)
                                if (interiorEndRowFits) {
                                    const endRowY = bayY + bayD;
                                    allRows.push({
                                        rowIndex: interiorModules * 2, // Next index after all double-loaded rows
                                        y: endRowY,
                                        height: effStallDepth
                                    });
                                }

                                parkingLayoutRef.current = {
                                    rows: allRows,
                                    sectionX: bayX,
                                    stallWidth: effStallWidth,
                                    stallsPerRow: interiorStallsPerRow,
                                    adaStalls,
                                    adaVanStalls,
                                    adaClusterSize: adaStalls + 1, // +1 for access aisle
                                    SCALE,
                                    moduleDepth,
                                    optAisleWidth,
                                    // Add perimeter loop bounds for aisle snapping
                                    loopOuter: {
                                        x: loopOX,
                                        y: loopOY,
                                        w: loopTotalW,
                                        h: loopTotalD
                                    },
                                    loopWidth: loopWidth,
                                    aisleWidth: effectiveAisleWidth,
                                    // Cross-aisle info for Capture & Edit
                                    useCrossAisle: useCrossAisle,
                                    spineX: spineX,
                                    autoSpinePositions: autoSpinePositions,
                                    isIrregular: isIrregular
                                };

                                // === DRAW PARKING MODULES (for each section) ===
                                for (let m = 0; m < interiorModules; m++) {
                                    const moduleY = bayY + m * moduleDepth;
                                    const aisleY = moduleY + effStallDepth;

                                    // For irregular shapes, polygon clipping is done in the X-scan below
                                    // No need for center-point pre-check - it fails for L/U shaped polygons

                                    // Use shared layout values for aisle bounds (synced with 3D)
                                    let aisleSegments = [{ startX: interiorX, endX: interiorX + interiorW }];

                                    // For irregular shapes, clip aisle to polygon at this Y position
                                    // Need to detect DISCONTINUOUS segments (gaps in L/U shapes)
                                    // IMPORTANT: For double-loaded parking, aisle only valid where BOTH
                                    // top row AND bottom row stalls would be inside the polygon
                                    if (isIrregular && loopInnerPolygon && loopInnerPolygon.length >= 3) {
                                        // Y positions for stall rows above and below the aisle
                                        const topRowCenterY = moduleY + effStallDepth / 2;  // Top stall row center
                                        const bottomRowCenterY = aisleY + optAisleWidth + effStallDepth / 2;  // Bottom stall row center

                                        // Scan to find all valid X segments (handling gaps)
                                        const segments = [];
                                        let segmentStart = null;
                                        let lastValid = false;

                                        for (let testX = interiorX; testX <= interiorX + interiorW; testX += 2) {
                                            // Check if BOTH top and bottom stall rows are inside polygon at this X
                                            const topPoint = { x: testX, y: topRowCenterY };
                                            const bottomPoint = { x: testX, y: bottomRowCenterY };

                                            const topInInner = isPointInPolygon(topPoint, loopInnerPolygon);
                                            const topInOuter = loopOuterPolygon ? isPointInPolygon(topPoint, loopOuterPolygon) : true;
                                            const bottomInInner = isPointInPolygon(bottomPoint, loopInnerPolygon);
                                            const bottomInOuter = loopOuterPolygon ? isPointInPolygon(bottomPoint, loopOuterPolygon) : true;

                                            // Aisle only valid where BOTH rows would have stalls
                                            const isValid = topInInner && topInOuter && bottomInInner && bottomInOuter;

                                            if (isValid && !lastValid) {
                                                // Starting a new segment
                                                segmentStart = testX;
                                            } else if (!isValid && lastValid && segmentStart !== null) {
                                                // Ending a segment
                                                segments.push({ startX: segmentStart, endX: testX - 2 });
                                                segmentStart = null;
                                            }
                                            lastValid = isValid;
                                        }

                                        // Close final segment if still open
                                        if (lastValid && segmentStart !== null) {
                                            segments.push({ startX: segmentStart, endX: interiorX + interiorW });
                                        }

                                        if (segments.length === 0) {
                                            // No valid segments at this Y, skip this module
                                            continue;
                                        }

                                        aisleSegments = segments;

                                        // Draw each aisle segment separately (handles L/U shape gaps)
                                        // Always draw internal aisles - they're auto-positioned based on stall layout
                                        aisleSegments.forEach(segment => {
                                            const segmentWidth = segment.endX - segment.startX;
                                            if (segmentWidth <= 0) return;

                                            ctx.beginPath();
                                            ctx.rect(segment.startX * SCALE, aisleY * SCALE, segmentWidth * SCALE, optAisleWidth * SCALE);
                                            ctx.fillStyle = colors.loop;
                                            ctx.fill();
                                        });
                                    }

                                    // Use first segment for backward compatibility with existing code
                                    const aisleInnerStartX = aisleSegments[0]?.startX || interiorX;
                                    const aisleInnerEndX = aisleSegments[aisleSegments.length - 1]?.endX || (interiorX + interiorW);

                                    if (useCrossAisle) {
                                        // Cross-aisle disabled for irregular shapes
                                    } else if (!isIrregular) {
                                        // FULL AISLE for regular shapes
                                        // Always draw internal aisles - they're auto-positioned based on stall layout
                                        const aisleInnerWidth = aisleInnerEndX - aisleInnerStartX;
                                        ctx.beginPath();
                                        ctx.rect(aisleInnerStartX * SCALE, aisleY * SCALE, aisleInnerWidth * SCALE, optAisleWidth * SCALE);
                                        ctx.fillStyle = colors.loop;
                                        ctx.fill();

                                        // Note: Junction treatments removed - crosswalks provide sufficient marking
                                    } else {
                                        // IRREGULAR SHAPES: draw aisle only
                                        // Always draw internal aisles - they're auto-positioned based on stall layout
                                        const aisleInnerWidth = aisleInnerEndX - aisleInnerStartX;
                                        ctx.beginPath();
                                        ctx.rect(aisleInnerStartX * SCALE, aisleY * SCALE, aisleInnerWidth * SCALE, optAisleWidth * SCALE);
                                        ctx.fillStyle = colors.loop;
                                        ctx.fill();
                                    }

                                    // Note: T-intersection fillets removed to prevent layering artifacts
                                    // The simple rectangle aisles provide clean visual connections

                                    // Draw aisles for each section (stalls only, aisle already drawn above)
                                    parkingSections.forEach((section, secIndex) => {

                                        // Internal aisle arrows and center line
                                        const intAisleY = (aisleY + optAisleWidth / 2) * SCALE;

                                        if (driveType === 'twoWay') {
                                            // Two-way internal aisle: center divider line only (dashed)
                                            // Use clipped aisle bounds for irregular shapes
                                            ctx.save();
                                            ctx.strokeStyle = 'rgba(255,255,255,0.4)';
                                            ctx.lineWidth = 1;
                                            ctx.setLineDash([6, 4]);
                                            ctx.beginPath();
                                            ctx.moveTo((aisleInnerStartX + 10) * SCALE, intAisleY);
                                            ctx.lineTo((aisleInnerEndX - 10) * SCALE, intAisleY);
                                            ctx.stroke();
                                            ctx.setLineDash([]);
                                            ctx.restore();
                                        } else {
                                            // Hybrid one-way: internal aisles ALTERNATE per module row
                                            // AND are OPPOSITE for left vs right sections of cross-aisle
                                            // This creates proper circulation with counter-clockwise perimeter:
                                            // - Left perimeter goes UP (↑)
                                            // - Right perimeter goes DOWN (↓)
                                            // - Left section aisles: even rows → (toward spine), odd rows ← (toward perimeter)
                                            // - Right section aisles: even rows ← (toward spine), odd rows → (toward perimeter)
                                            ctx.save();
                                            ctx.fillStyle = '#ffffff'; // White arrows for visibility
                                            ctx.font = 'bold 16px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';

                                            // Determine direction based on module index AND section side
                                            let direction;
                                            if (section.side === 'left' || section.side === 'full') {
                                                // Left section or full width: even rows go right, odd rows go left
                                                direction = m % 2 === 0 ? '→' : '←';
                                            } else {
                                                // Right section: OPPOSITE - even rows go left (toward spine), odd rows go right
                                                direction = m % 2 === 0 ? '←' : '→';
                                            }

                                            // Calculate arrows based on MUTCD spacing (60 ft)
                                            // Use clipped aisle bounds for irregular shapes
                                            const aisleLength = aisleInnerEndX - aisleInnerStartX;
                                            const numAisleArrows = Math.max(1, Math.floor(aisleLength / 60));
                                            const aisleArrowSpacing = aisleLength / (numAisleArrows + 1);

                                            for (let i = 1; i <= numAisleArrows; i++) {
                                                const arrowX = aisleInnerStartX + i * aisleArrowSpacing;
                                                ctx.fillText(direction, arrowX * SCALE, intAisleY);
                                            }
                                            ctx.restore();
                                        }

                                        // === DRAW STALLS FOR THIS SECTION ===
                                        // MAXIMIZED LAYOUT: All positions are stalls except optional landscape islands
                                        // End islands are now drawn as small wheel stops at aisle ends, NOT in stall positions

                                        // === ADA POSITION CALCULATION ===
                                        // Determine where ADA stalls should be placed in the first row
                                        // adaPosition: 0 = start (left), -1 = end (right), >0 = custom stall index
                                        const adaClusterSize = adaStalls + 1; // +1 for access aisle
                                        let adaStartIndex, adaEndIndex, adaAccessAisleIndex;
                                        if (adaPosition === -1) {
                                            // End of row (right side) - ADA at end, access aisle before them
                                            adaAccessAisleIndex = section.stallsPerRow - adaClusterSize;
                                            adaStartIndex = adaAccessAisleIndex + 1;
                                            adaEndIndex = section.stallsPerRow - 1;
                                        } else if (adaPosition > 0) {
                                            // Custom position - ADA stalls start at adaPosition, access aisle after
                                            // Clamp to valid range to prevent overflow
                                            const maxStartIndex = section.stallsPerRow - adaClusterSize;
                                            const clampedPosition = Math.min(adaPosition, maxStartIndex);
                                            adaStartIndex = clampedPosition;
                                            adaEndIndex = adaStartIndex + adaStalls - 1;
                                            adaAccessAisleIndex = adaEndIndex + 1;
                                        } else {
                                            // Start of row (left side) - ADA at start, access aisle after them
                                            adaStartIndex = 0;
                                            adaEndIndex = adaStalls - 1;
                                            adaAccessAisleIndex = adaStalls;
                                        }

                                        const drawStallRow = (rowY, isTopRow, rowIndex) => {
                                            // Bounds check: Skip if row would be outside the INTERIOR parking area
                                            // Using shared layout values for exact sync with 3D view
                                            if (rowY < interiorY || rowY + effStallDepth > interiorY + interiorH) {
                                                return; // Skip this row - it would overlap with perimeter
                                            }

                                            // Row letter for stall numbering (A, B, C, D... from rowIndex)
                                            const rowLetter = String.fromCharCode(65 + rowIndex);

                                            // Calculate lean for angled parking bounds checking
                                            const lean = isAngledParking && angledGeometry
                                                ? angledGeometry.stallWidth * angledGeometry.cos
                                                : 0;

                                            for (let s = 0; s < section.stallsPerRow; s++) {
                                                // For angled parking, offset first stall to account for lean
                                                // Top rows lean LEFT: start with +lean offset so back-left corner stays in bounds
                                                // Bottom rows lean RIGHT: no start offset needed, but check right edge
                                                const leanOffset = isAngledParking && isTopRow ? lean : 0;
                                                const stallX = section.x + leanOffset + s * effStallWidth;

                                                // Bounds check: For rectangular use bounding box, for irregular use polygon
                                                if (isIrregular && loopInnerPolygon && loopInnerPolygon.length >= 3) {
                                                    // Check if stall center is inside the interior polygon
                                                    // Use center point check to avoid false positives at reflex corners
                                                    const stallCenterX = stallX + effStallWidth / 2;
                                                    const stallCenterY = rowY + effStallDepth / 2;
                                                    const centerPoint = { x: stallCenterX, y: stallCenterY };

                                                    // Must be inside BOTH inner and outer polygons
                                                    const centerInInner = isPointInPolygon(centerPoint, loopInnerPolygon);
                                                    const centerInOuter = loopOuterPolygon ? isPointInPolygon(centerPoint, loopOuterPolygon) : true;

                                                    // For angled parking, check parallelogram corners; for rectangular, check rectangle
                                                    let cornersInBounds = true;
                                                    if (isAngledParking && getStallCorners) {
                                                        const stallCorners = getStallCorners(stallX, rowY, isTopRow);
                                                        cornersInBounds = stallCorners.every(corner =>
                                                            isPointInPolygon(corner, loopInnerPolygon)
                                                        );
                                                    } else {
                                                        cornersInBounds = isRectInPolygon(stallX, rowY, effStallWidth, effStallDepth, loopInnerPolygon);
                                                    }

                                                    if (!centerInInner || !centerInOuter || !cornersInBounds) {
                                                        continue; // Skip stall - outside polygon boundary
                                                    }
                                                } else {
                                                    // Rectangular bounds check - account for angled stall parallelogram corners
                                                    if (isAngledParking && getStallCorners) {
                                                        const stallCorners = getStallCorners(stallX, rowY, isTopRow);
                                                        // Check all 4 parallelogram corners are within interior bounds
                                                        const allCornersInBounds = stallCorners.every(corner =>
                                                            corner.x >= interiorX &&
                                                            corner.x <= interiorX + interiorW &&
                                                            corner.y >= interiorY &&
                                                            corner.y <= interiorY + interiorH
                                                        );
                                                        if (!allCornersInBounds) {
                                                            continue; // Skip this stall - parallelogram extends outside interior
                                                        }
                                                    } else {
                                                        // Standard rectangular bounds check
                                                        if (stallX < interiorX || stallX + effStallWidth > interiorX + interiorW) {
                                                            continue; // Skip this stall - would overlap with perimeter
                                                        }
                                                    }
                                                }

                                                // === EXCLUSION ZONE CHECK ===
                                                // Skip stalls that overlap with any exclusion zone
                                                if (rectOverlapsExclusions(stallX, rowY, effStallWidth, effStallDepth, exclusions)) {
                                                    continue; // Skip stall - overlaps exclusion zone
                                                }

                                                // === CUSTOM AISLE COLLISION CHECK ===
                                                // Skip stalls that overlap with any custom drawn aisle
                                                if (drawnAisles.length > 0 && stallCollidesWithAisles(stallX, rowY, effStallWidth, effStallDepth, drawnAisles, optAisleWidth)) {
                                                    stallsRemovedByAisles++;
                                                    continue; // Skip stall - overlaps custom aisle
                                                }

                                                // Check for landscape island (every N stalls, in middle only - NOT at edges)
                                                // Landscape islands take stall positions but are optional and infrequent
                                                const isLandscape = hasLandscaping && s > 0 && s < section.stallsPerRow - 1 && s % landscapeInterval === 0;

                                                // === ADA ACCESS AISLE SKIP LOGIC ===
                                                // The stall position for the access aisle is calculated based on adaPosition
                                                // Access aisle is 5-8' wide, stall is 9' - skip 1 stall position
                                                // Only applies to the ADA row (rowIndex === adaRow) where ADA stalls are placed
                                                const isAccessAislePosition = hasAda && adaStalls > 0 && rowIndex === adaRow && s === adaAccessAisleIndex;

                                                if (isAccessAislePosition) {
                                                    // === DRAW ADA ACCESS AISLE AT THIS POSITION ===
                                                    // Per ADA 502.3 - Shared Access Aisles
                                                    const accessAisleWidth = adaVanStalls > 0 ? 8 : 5; // Van=8', Standard=5'
                                                    // For angled parking, use base stall depth (18'), not projected depth
                                                    const accessAisleDepth = isAngledParking && angledGeometry
                                                        ? angledGeometry.stallDepth  // 18' base depth
                                                        : effStallDepth;

                                                    // Draw access aisle with diagonal stripes (blue hatching)
                                                    ctx.save();
                                                    ctx.beginPath();
                                                    ctx.rect(stallX * SCALE, rowY * SCALE, accessAisleWidth * SCALE, accessAisleDepth * SCALE);
                                                    ctx.fillStyle = 'rgba(59, 130, 246, 0.3)';
                                                    ctx.fill();
                                                    ctx.strokeStyle = '#3b82f6';
                                                    ctx.lineWidth = 2;
                                                    ctx.stroke();

                                                    // Diagonal hatching per ADA (45° stripes)
                                                    ctx.strokeStyle = '#3b82f6';
                                                    ctx.lineWidth = 1.5;
                                                    ctx.setLineDash([]);
                                                    for (let h = 0; h < accessAisleDepth + accessAisleWidth; h += 3) {
                                                        ctx.beginPath();
                                                        const startX = stallX;
                                                        const startY = rowY + Math.min(h, accessAisleDepth);
                                                        const endX = stallX + Math.min(h, accessAisleWidth);
                                                        const endY = rowY + Math.max(0, h - accessAisleWidth);
                                                        ctx.moveTo(startX * SCALE, startY * SCALE);
                                                        ctx.lineTo(endX * SCALE, endY * SCALE);
                                                        ctx.stroke();
                                                    }

                                                    // "VAN" label if any van accessible stalls exist
                                                    if (adaVanStalls > 0) {
                                                        ctx.fillStyle = '#1d4ed8';
                                                        ctx.font = 'bold 6px sans-serif';
                                                        ctx.textAlign = 'center';
                                                        ctx.textBaseline = 'middle';
                                                        ctx.fillText('VAN', (stallX + accessAisleWidth / 2) * SCALE, (rowY + accessAisleDepth / 2) * SCALE);
                                                    }
                                                    ctx.restore();

                                                    continue; // Skip stall drawing at this position
                                                }

                                                if (isLandscape) {
                                                    // Landscape island with tree
                                                    ctx.beginPath();
                                                    ctx.rect(stallX * SCALE, rowY * SCALE, effStallWidth * SCALE, effStallDepth * SCALE);
                                                    ctx.fillStyle = colors.landscape;
                                                    ctx.fill();
                                                    ctx.strokeStyle = '#22c55e';
                                                    ctx.lineWidth = 1;
                                                    ctx.stroke();
                                                    // Tree
                                                    ctx.beginPath();
                                                    ctx.arc((stallX + effStallWidth / 2) * SCALE, (rowY + effStallDepth / 2) * SCALE, 3 * SCALE, 0, Math.PI * 2);
                                                    ctx.fillStyle = colors.tree;
                                                    ctx.fill();
                                                } else {
                                                    // PARKING STALL - maximize count
                                                    // Determine stall type based on position in row and stall mix
                                                    let stallColor = colors.standard;
                                                    let stallLabel = '';
                                                    let stallType = 'standard';

                                                    // === ADA STALLS: Position-based assignment ===
                                                    // ADA stalls are placed at adaStartIndex to adaEndIndex in the selected row (adaRow)
                                                    // Van accessible stalls come first within the ADA cluster
                                                    const isAdaPosition = hasAda && rowIndex === adaRow && s >= adaStartIndex && s <= adaEndIndex;
                                                    const adaIndexInCluster = isAdaPosition ? (adaPosition === -1 ? s - adaStartIndex : s) : -1;
                                                    const isVanPosition = isAdaPosition && adaIndexInCluster < adaVanStalls;

                                                    if (isVanPosition) {
                                                        // Van accessible ADA stall
                                                        stallColor = colors.ada;
                                                        stallLabel = '♿';
                                                        stallType = 'adaVan';
                                                        counts.adaVan++;
                                                        counts.ada++;
                                                    } else if (isAdaPosition) {
                                                        // Standard ADA stall
                                                        stallColor = colors.ada;
                                                        stallLabel = '♿';
                                                        stallType = 'ada';
                                                        counts.ada++;
                                                    } else if (stallIndex < adaStalls + evStalls) {
                                                        stallColor = colors.ev;
                                                        stallLabel = '⚡';
                                                        stallType = 'ev';
                                                        counts.ev++;
                                                    } else if (stallIndex < adaStalls + evStalls + compactStalls) {
                                                        stallColor = colors.compact;
                                                        stallLabel = 'C';
                                                        stallType = 'compact';
                                                        counts.compact++;
                                                    } else {
                                                        counts.standard++;
                                                    }
                                                    counts.total++;
                                                    stallIndex++;

                                                    // Determine actual stall dimensions (ADA stalls are wider)
                                                    const isAda = stallType === 'ada' || stallType === 'adaVan';
                                                    const isVanAda = stallType === 'adaVan';
                                                    const actualStallWidth = isAda ? 11 : effStallWidth; // ADA = 11' (8' stall + 3' partial access aisle, shared)

                                                    // === ANGLED PARKING SUPPORT ===
                                                    // For angled parking (45°, 60°), draw parallelogram stalls
                                                    // EXCEPTION: ADA stalls are always 90° perpendicular per ADA 502.2
                                                    if (isAngledParking && getStallCorners && !isAda) {
                                                        // For angled parking, draw stalls as parallelograms
                                                        // Proper double-loaded herringbone layout:
                                                        // - Top row: stalls face UP (nose away from aisle) - facingUp=true
                                                        // - Bottom row: stalls face DOWN (nose away from aisle) - facingUp=false
                                                        // This creates opposing `\` and `/` patterns that interlock properly
                                                        const stallCorners = getStallCorners(stallX, rowY, isTopRow);

                                                        drawAngledStall(stallCorners, stallColor, '#ffffff');

                                                        // Calculate center for labels
                                                        const centerX = stallCorners.reduce((sum, c) => sum + c.x, 0) / 4;
                                                        const centerY = stallCorners.reduce((sum, c) => sum + c.y, 0) / 4;

                                                        // Label for special stalls (EV, Compact) - placed at CENTER
                                                        if (stallLabel) {
                                                            ctx.save();
                                                            ctx.font = 'bold 12px sans-serif';
                                                            ctx.textAlign = 'center';
                                                            ctx.textBaseline = 'middle';
                                                            ctx.fillStyle = '#ffffff';
                                                            ctx.fillText(stallLabel, centerX * SCALE, centerY * SCALE);
                                                            ctx.restore();
                                                        }

                                                        // Stall numbering for angled - placed at REAR (near wheel stop)
                                                        // Per parking standards, numbers are painted near the wheel stop
                                                        if (showStallNumbers) {
                                                            const stallNumber = String(s + 1).padStart(3, '0');
                                                            const stallNumLabel = `${rowLetter}-${stallNumber}`;

                                                            // Calculate rear center of stall (back edge midpoint)
                                                            // Back corners are indices 2 and 3 in the parallelogram
                                                            const backCenterX = (stallCorners[2].x + stallCorners[3].x) / 2;
                                                            const backCenterY = (stallCorners[2].y + stallCorners[3].y) / 2;
                                                            // Offset slightly toward center for readability
                                                            const rearX = (backCenterX + centerX) / 2;
                                                            const rearY = (backCenterY + centerY) / 2;

                                                            ctx.save();
                                                            ctx.font = 'bold 5px sans-serif';
                                                            ctx.textAlign = 'center';
                                                            ctx.textBaseline = 'middle';
                                                            ctx.fillStyle = '#374151';
                                                            ctx.fillText(stallNumLabel, rearX * SCALE, rearY * SCALE);
                                                            ctx.restore();
                                                        }
                                                    } else {
                                                        // 90° PERPENDICULAR PARKING - Draw rectangle
                                                        // (Also used for ADA stalls in angled parking per ADA 502.2)

                                                        // For ADA stalls in angled parking, use BASE stall dimensions (9'x18')
                                                        // not the projected angled dimensions
                                                        const adaStallWidth = isAda && isAngledParking && angledGeometry
                                                            ? angledGeometry.stallWidth  // 9' base width
                                                            : effStallWidth;
                                                        const adaStallDepth = isAda && isAngledParking && angledGeometry
                                                            ? angledGeometry.stallDepth  // 18' base depth
                                                            : effStallDepth;

                                                        ctx.beginPath();
                                                        ctx.rect(stallX * SCALE, rowY * SCALE, adaStallWidth * SCALE, adaStallDepth * SCALE);
                                                        ctx.fillStyle = stallColor; // SOLID fill
                                                        ctx.fill();
                                                        ctx.strokeStyle = '#ffffff'; // White border for contrast
                                                        ctx.lineWidth = 2;
                                                        ctx.stroke();

                                                        // Label for special stalls (ADA, EV, Compact) at CENTER
                                                        if (stallLabel) {
                                                            ctx.save();
                                                            ctx.font = 'bold 12px sans-serif';
                                                            ctx.textAlign = 'center';
                                                            ctx.textBaseline = 'middle';
                                                            ctx.fillStyle = '#ffffff';
                                                            ctx.fillText(stallLabel, (stallX + adaStallWidth / 2) * SCALE, (rowY + adaStallDepth / 2) * SCALE);
                                                            ctx.restore();

                                                            // === ADA VERTICAL SIGN INDICATOR (per ADA/MUTCD) ===
                                                            if (isAda) {
                                                                // Draw sign post symbol at front of stall
                                                                ctx.save();
                                                                const signX = stallX + adaStallWidth / 2;
                                                                const signY = isTopRow ? rowY + adaStallDepth - 2 : rowY + 2;

                                                                // Sign post
                                                                ctx.strokeStyle = '#6b7280';
                                                                ctx.lineWidth = 2;
                                                                ctx.beginPath();
                                                                ctx.moveTo(signX * SCALE, signY * SCALE);
                                                                ctx.lineTo(signX * SCALE, (signY + (isTopRow ? -4 : 4)) * SCALE);
                                                                ctx.stroke();

                                                                // Sign head
                                                                ctx.fillStyle = '#3b82f6';
                                                                ctx.beginPath();
                                                                ctx.rect((signX - 1.5) * SCALE, (signY + (isTopRow ? -6 : 4)) * SCALE, 3 * SCALE, 2 * SCALE);
                                                                ctx.fill();
                                                                ctx.restore();
                                                            }
                                                        }

                                                        // === STALL NUMBERING (SYNCED WITH 3D) - 90° only ===
                                                        // Format: A-001 for row A stall 1, B-001 for row B, etc.
                                                        // Per parking standards (MUTCD/ITE):
                                                        // - Numbers painted in rear quarter of stall, but IN FRONT of wheel stop
                                                        // - Wheel stop is at ~2ft from rear edge, numbers at ~5-6ft from rear
                                                        if (showStallNumbers) {
                                                            const stallNumber = String(s + 1).padStart(3, '0');
                                                            const stallNumLabel = `${rowLetter}-${stallNumber}`;

                                                            ctx.save();
                                                            ctx.font = 'bold 5px sans-serif';
                                                            ctx.textAlign = 'center';
                                                            ctx.textBaseline = 'middle';
                                                            ctx.fillStyle = '#374151'; // Dark gray text

                                                            // Position in rear quarter but in front of wheel stop
                                                            // Wheel stop is at inset=2, so place number at ~25% from rear
                                                            // Top row: rear is at top, so 25% from top
                                                            // Bottom row: rear is at bottom, so 25% from bottom
                                                            const rearOffset = adaStallDepth * 0.25; // ~4.5ft from rear for 18ft stall
                                                            const numberY = isTopRow
                                                                ? rowY + rearOffset
                                                                : rowY + adaStallDepth - rearOffset;
                                                            ctx.fillText(stallNumLabel, (stallX + adaStallWidth / 2) * SCALE, numberY * SCALE);
                                                            ctx.restore();
                                                        }
                                                    } // End of 90° perpendicular parking block
                                                }
                                            }
                                        };

                                        // Top row of stalls
                                        drawStallRow(moduleY, true, m * 2); // Row A, C, E, etc.
                                        // Bottom row of stalls
                                        drawStallRow(moduleY + effStallDepth + optAisleWidth, false, m * 2 + 1); // Row B, D, F, etc.

                                        // === ADA PLACEMENT HOVER PREVIEW ===
                                        // When user is placing ADA and hovering, show preview highlight on the hovered row
                                        const topRowGlobalIndex = m * 2;
                                        const bottomRowGlobalIndex = m * 2 + 1;
                                        const showPreviewOnTop = isPlacingAda && adaHoverIndex !== null && adaHoverRow === topRowGlobalIndex;
                                        const showPreviewOnBottom = isPlacingAda && adaHoverIndex !== null && adaHoverRow === bottomRowGlobalIndex;

                                        if (showPreviewOnTop || showPreviewOnBottom) {
                                            const previewClusterSize = adaStalls + 1; // +1 for access aisle
                                            const previewStartIndex = adaHoverIndex;

                                            ctx.save();
                                            // Draw highlight box around proposed ADA cluster
                                            const highlightX = section.x + previewStartIndex * effStallWidth;
                                            const highlightWidth = previewClusterSize * effStallWidth;
                                            const highlightY = showPreviewOnTop ? moduleY : moduleY + effStallDepth + optAisleWidth;
                                            const highlightHeight = effStallDepth;

                                            // Pulsing blue overlay
                                            ctx.fillStyle = 'rgba(59, 130, 246, 0.3)';
                                            ctx.fillRect(
                                                highlightX * SCALE,
                                                highlightY * SCALE,
                                                highlightWidth * SCALE,
                                                highlightHeight * SCALE
                                            );

                                            // Bold blue border
                                            ctx.strokeStyle = '#3b82f6';
                                            ctx.lineWidth = 3;
                                            ctx.setLineDash([5, 3]);
                                            ctx.strokeRect(
                                                highlightX * SCALE,
                                                highlightY * SCALE,
                                                highlightWidth * SCALE,
                                                highlightHeight * SCALE
                                            );
                                            ctx.setLineDash([]);

                                            // Label showing ADA count and row
                                            ctx.fillStyle = '#1d4ed8';
                                            ctx.font = 'bold 14px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';
                                            const rowLetter = String.fromCharCode(65 + adaHoverRow);
                                            ctx.fillText(
                                                `♿ ${adaStalls} ADA + Aisle (Row ${rowLetter})`,
                                                (highlightX + highlightWidth / 2) * SCALE,
                                                (highlightY + highlightHeight / 2) * SCALE
                                            );
                                            ctx.restore();
                                        }

                                        // === WHEEL STOPS FOR ALL STALLS (synced with 3D view) ===
                                        // Wheel stops prevent vehicle overhang into walkways
                                        // Typically 5' long, 6" wide concrete or rubber stops
                                        // IMPORTANT: In double-loaded parking:
                                        // - Top row vehicles NOSE UP (away from aisle) - stop at TOP of stall
                                        // - Bottom row vehicles NOSE DOWN (away from aisle) - stop at BOTTOM of stall
                                        const wheelStopLength = 5; // Matches 3D (5ft)
                                        const wheelStopWidth = 0.5;
                                        const wheelStopInset = 2; // Inset from rear edge (matches 3D)
                                        ctx.save();
                                        ctx.fillStyle = '#9ca3af'; // Gray concrete (matches 3D)
                                        ctx.strokeStyle = '#6b7280';
                                        ctx.lineWidth = 0.5;

                                        // Get lean for angled parking
                                        const wheelStopLean = isAngledParking && angledGeometry
                                            ? angledGeometry.stallWidth * angledGeometry.cos
                                            : 0;

                                        // Draw wheel stops for EVERY stall in each row
                                        [moduleY, moduleY + effStallDepth + optAisleWidth].forEach((rowY, localRowIndex) => {
                                            // Only draw if this row would be inside boundary
                                            if (rowY < interiorY || rowY + effStallDepth > interiorY + interiorH) return;

                                            const isTopRow = localRowIndex === 0;
                                            const globalRowIndex = m * 2 + localRowIndex; // Actual row index across all modules

                                            // Draw wheel stop for each stall in the row
                                            for (let ws = 0; ws < section.stallsPerRow; ws++) {
                                                // Skip ADA access aisle position (reserved for access aisle, not a stall)
                                                if (hasAda && adaStalls > 0 && globalRowIndex === adaRow && ws === adaAccessAisleIndex) {
                                                    continue;
                                                }

                                                // Check if this stall is an ADA stall (ADA stalls are always 90° even in angled parking)
                                                const isAdaStall = hasAda && globalRowIndex === adaRow && ws >= adaStartIndex && ws <= adaEndIndex;

                                                // Apply lean offset only for non-ADA stalls in angled parking
                                                const useAngledGeometry = isAngledParking && !isAdaStall;
                                                const stallLeanOffset = useAngledGeometry && isTopRow ? wheelStopLean : 0;
                                                const stallX = section.x + stallLeanOffset + ws * effStallWidth;

                                                // For irregular shapes, check polygon bounds
                                                if (isIrregular && interiorPolygon && interiorPolygon.length >= 3) {
                                                    if (useAngledGeometry && getStallCorners) {
                                                        const stallCorners = getStallCorners(stallX, rowY, isTopRow);
                                                        const allCornersIn = stallCorners.every(c => isPointInPolygon(c, interiorPolygon));
                                                        if (!allCornersIn) continue;
                                                    } else if (!isRectInPolygon(stallX, rowY, effStallWidth, effStallDepth, interiorPolygon)) {
                                                        continue; // Skip stall - outside polygon
                                                    }
                                                } else {
                                                    // Rectangular bounds check
                                                    if (useAngledGeometry && getStallCorners) {
                                                        const stallCorners = getStallCorners(stallX, rowY, isTopRow);
                                                        const allCornersInBounds = stallCorners.every(corner =>
                                                            corner.x >= interiorX &&
                                                            corner.x <= interiorX + interiorW
                                                        );
                                                        if (!allCornersInBounds) continue;
                                                    } else if (stallX < interiorX || stallX + effStallWidth > interiorX + interiorW) {
                                                        continue;
                                                    }
                                                }

                                                // Calculate wheel stop position - must be centered on the BACK EDGE of the stall
                                                let stopX, stopY;
                                                if (useAngledGeometry && getStallCorners) {
                                                    // For angled parking (non-ADA), get actual parallelogram corners
                                                    const stallCorners = getStallCorners(stallX, rowY, isTopRow);
                                                    // Back corners are indices 2 and 3
                                                    const backLeft = stallCorners[3];
                                                    const backRight = stallCorners[2];
                                                    const backCenterX = (backLeft.x + backRight.x) / 2;
                                                    const backCenterY = (backLeft.y + backRight.y) / 2;
                                                    // Center the wheel stop on the back edge, inset slightly
                                                    stopX = backCenterX - wheelStopLength / 2;
                                                    stopY = backCenterY - wheelStopInset - wheelStopWidth / 2;
                                                } else {
                                                    // For 90° parking (or ADA stalls), back edge is directly behind front edge
                                                    // ADA stalls use base depth (18') not projected depth
                                                    const stallDepthToUse = isAdaStall && isAngledParking && angledGeometry
                                                        ? angledGeometry.stallDepth
                                                        : effStallDepth;
                                                    stopX = stallX + (effStallWidth - wheelStopLength) / 2;
                                                    // Top row: rear at top, Bottom row: rear at bottom
                                                    stopY = isTopRow
                                                        ? rowY + wheelStopInset
                                                        : rowY + stallDepthToUse - wheelStopInset - wheelStopWidth;
                                                }

                                                ctx.beginPath();
                                                ctx.rect(stopX * SCALE, stopY * SCALE, wheelStopLength * SCALE, wheelStopWidth * SCALE);
                                                ctx.fill();
                                                ctx.stroke();
                                            }
                                        });
                                        ctx.restore();

                                        // === END ISLANDS (optional landscape islands at row ends) ===
                                        // Professional design with raised curbs, mulch, and trees
                                        if (endIslands) {
                                            ctx.save();
                                            // Draw end islands (landscape areas at row ends)
                                            [moduleY, moduleY + effStallDepth + optAisleWidth].forEach((rowY, rowIndex) => {
                                                // Only draw if this row would be inside boundary
                                                if (rowY < interiorY || rowY + effStallDepth > interiorY + interiorH) return;

                                                const drawEndIsland = (islandX) => {
                                                    const islandY = rowY;
                                                    const islandW = effStallWidth;
                                                    const islandH = effStallDepth;
                                                    const curbWidth = 0.5;
                                                    const treeRadius = 2.5;

                                                    // Raised curb border (concrete)
                                                    ctx.beginPath();
                                                    ctx.rect(islandX * SCALE, islandY * SCALE, islandW * SCALE, islandH * SCALE);
                                                    ctx.fillStyle = '#d1d5db'; // Concrete curb
                                                    ctx.fill();

                                                    // Mulch/ground cover (inner area)
                                                    ctx.beginPath();
                                                    ctx.rect(
                                                        (islandX + curbWidth) * SCALE,
                                                        (islandY + curbWidth) * SCALE,
                                                        (islandW - curbWidth * 2) * SCALE,
                                                        (islandH - curbWidth * 2) * SCALE
                                                    );
                                                    ctx.fillStyle = '#854d0e'; // Brown mulch
                                                    ctx.fill();

                                                    // Grass patch in center
                                                    const grassPadding = 1.5;
                                                    ctx.beginPath();
                                                    ctx.rect(
                                                        (islandX + grassPadding) * SCALE,
                                                        (islandY + grassPadding) * SCALE,
                                                        (islandW - grassPadding * 2) * SCALE,
                                                        (islandH - grassPadding * 2) * SCALE
                                                    );
                                                    ctx.fillStyle = colors.landscape;
                                                    ctx.fill();

                                                    // Tree shadow (offset circle)
                                                    ctx.beginPath();
                                                    ctx.arc(
                                                        (islandX + islandW / 2 + 0.5) * SCALE,
                                                        (islandY + islandH / 2 + 0.5) * SCALE,
                                                        treeRadius * SCALE,
                                                        0, Math.PI * 2
                                                    );
                                                    ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
                                                    ctx.fill();

                                                    // Tree canopy (dark green)
                                                    ctx.beginPath();
                                                    ctx.arc(
                                                        (islandX + islandW / 2) * SCALE,
                                                        (islandY + islandH / 2) * SCALE,
                                                        treeRadius * SCALE,
                                                        0, Math.PI * 2
                                                    );
                                                    ctx.fillStyle = colors.tree;
                                                    ctx.fill();
                                                    ctx.strokeStyle = '#14532d';
                                                    ctx.lineWidth = 1;
                                                    ctx.stroke();

                                                    // Tree highlight (lighter center)
                                                    ctx.beginPath();
                                                    ctx.arc(
                                                        (islandX + islandW / 2 - 0.5) * SCALE,
                                                        (islandY + islandH / 2 - 0.5) * SCALE,
                                                        (treeRadius * 0.4) * SCALE,
                                                        0, Math.PI * 2
                                                    );
                                                    ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
                                                    ctx.fill();
                                                };

                                                // Left end island (at first stall position)
                                                const leftIslandX = section.x;
                                                if (leftIslandX >= interiorX) {
                                                    drawEndIsland(leftIslandX);
                                                }

                                                // Right end island (at last stall position)
                                                const rightIslandX = section.x + (section.stallsPerRow - 1) * effStallWidth;
                                                if (rightIslandX + effStallWidth <= interiorX + interiorW) {
                                                    drawEndIsland(rightIslandX);
                                                }
                                            });
                                            ctx.restore();
                                        }
                                    });
                                }

                                // === REMAINING SPACE: Single-loaded parking (end row) ===
                                // Draw end row if there's enough remaining depth after modules (in INTERIOR area)
                                if (interiorEndRowFits) {
                                    // Position: immediately after all double-loaded modules
                                    const endRowY = bayY + bayD;

                                    // For irregular shapes, check if end row Y is inside polygon
                                    // Scan to find valid X range at this Y position
                                    let drawEndRow = true;
                                    let endRowStartX = interiorX;
                                    let endRowEndX = interiorX + interiorW;

                                    if (isIrregular && loopInnerPolygon && loopInnerPolygon.length >= 3) {
                                        const testY = endRowY + effStallDepth / 2;
                                        let minXFound = null;
                                        let maxXFound = null;

                                        for (let testX = interiorX; testX <= interiorX + interiorW; testX += 2) {
                                            const testPoint = { x: testX, y: testY };
                                            const inInner = isPointInPolygon(testPoint, loopInnerPolygon);
                                            const inOuter = loopOuterPolygon ? isPointInPolygon(testPoint, loopOuterPolygon) : true;
                                            if (inInner && inOuter) {
                                                if (minXFound === null) minXFound = testX;
                                                maxXFound = testX;
                                            }
                                        }

                                        if (minXFound === null || maxXFound === null) {
                                            drawEndRow = false;
                                        } else {
                                            endRowStartX = minXFound;
                                            endRowEndX = maxXFound;
                                        }
                                    }

                                    if (drawEndRow) {
                                        parkingSections.forEach(section => {
                                            for (let s = 0; s < section.stallsPerRow; s++) {
                                                const stallX = section.x + s * effStallWidth;

                                                // Bounds check for irregular shapes using polygon
                                                if (isIrregular && loopInnerPolygon && loopInnerPolygon.length >= 3) {
                                                    const inInner = isRectInPolygon(stallX, endRowY, effStallWidth, effStallDepth, loopInnerPolygon);
                                                    const inOuter = loopOuterPolygon ? isRectInPolygon(stallX, endRowY, effStallWidth, effStallDepth, loopOuterPolygon) : true;
                                                    if (!inInner || !inOuter) {
                                                        continue; // Skip stall - outside polygon boundary
                                                    }
                                                } else {
                                                    // Bounds check: Skip if stall would be outside INTERIOR horizontal bounds
                                                    // Using shared layout values for sync with 3D
                                                    if (stallX < interiorX || stallX + effStallWidth > interiorX + interiorW) {
                                                        continue;
                                                    }
                                                }

                                                // === EXCLUSION ZONE CHECK ===
                                                // Skip stalls that overlap with any exclusion zone
                                                if (rectOverlapsExclusions(stallX, endRowY, effStallWidth, effStallDepth, exclusions)) {
                                                    continue; // Skip stall - overlaps exclusion zone
                                                }

                                                // Skip landscape islands in this row too
                                                const isLandscape = hasLandscaping && s > 0 && s < section.stallsPerRow - 1 && s % landscapeInterval === 0;
                                                if (isLandscape) continue;

                                                // End row index for ADA placement
                                                const endRowIndex = interiorModules * 2;

                                                // Use stallIndex to assign types based on configured percentages
                                                let stallColor = colors.standard;
                                                let stallLabel = '';
                                                let stallType = 'standard';

                                                // === ADA STALLS: Position-based assignment for end row ===
                                                // Check if ADA cluster is placed on this end row
                                                const isAdaPosition = hasAda && adaRow === endRowIndex && s >= adaStartIndex && s <= adaEndIndex;
                                                const adaIndexInCluster = isAdaPosition ? (adaPosition === -1 ? s - adaStartIndex : s - adaStartIndex) : -1;
                                                const isVanPosition = isAdaPosition && adaIndexInCluster < adaVanStalls;

                                                // Check for access aisle position on end row
                                                const isAccessAislePosition = hasAda && adaStalls > 0 && adaRow === endRowIndex && s === adaAccessAisleIndex;

                                                if (isAccessAislePosition) {
                                                    // Draw access aisle for end row (similar to main rows)
                                                    const accessAisleWidth = adaVanStalls > 0 ? 8 : 5;
                                                    const accessAisleDepth = isAngledParking && angledGeometry ? angledGeometry.stallDepth : effStallDepth;

                                                    ctx.save();
                                                    ctx.beginPath();
                                                    ctx.rect(stallX * SCALE, endRowY * SCALE, accessAisleWidth * SCALE, accessAisleDepth * SCALE);
                                                    ctx.fillStyle = 'rgba(59, 130, 246, 0.3)';
                                                    ctx.fill();
                                                    ctx.strokeStyle = '#3b82f6';
                                                    ctx.lineWidth = 2;
                                                    ctx.stroke();

                                                    // Diagonal hatching
                                                    ctx.strokeStyle = '#3b82f6';
                                                    ctx.lineWidth = 1.5;
                                                    for (let h = 0; h < accessAisleDepth + accessAisleWidth; h += 3) {
                                                        ctx.beginPath();
                                                        const startX = stallX;
                                                        const startY = endRowY + Math.min(h, accessAisleDepth);
                                                        const endX = stallX + Math.min(h, accessAisleWidth);
                                                        const endY = endRowY + Math.max(0, h - accessAisleWidth);
                                                        ctx.moveTo(startX * SCALE, startY * SCALE);
                                                        ctx.lineTo(endX * SCALE, endY * SCALE);
                                                        ctx.stroke();
                                                    }
                                                    ctx.restore();
                                                    continue; // Skip stall drawing at this position
                                                }

                                                if (isVanPosition) {
                                                    stallColor = colors.ada;
                                                    stallLabel = '♿';
                                                    stallType = 'adaVan';
                                                    counts.adaVan++;
                                                    counts.ada++;
                                                } else if (isAdaPosition) {
                                                    stallColor = colors.ada;
                                                    stallLabel = '♿';
                                                    stallType = 'ada';
                                                    counts.ada++;
                                                } else if (stallIndex < adaStalls + evStalls) {
                                                    stallColor = colors.ev;
                                                    stallLabel = '⚡';
                                                    counts.ev++;
                                                } else if (stallIndex < adaStalls + evStalls + compactStalls) {
                                                    stallColor = colors.compact;
                                                    stallLabel = 'C';
                                                    counts.compact++;
                                                } else {
                                                    counts.standard++;
                                                }
                                                counts.total++;
                                                stallIndex++;

                                                // ADA stall determination
                                                const isAda = stallType === 'ada' || stallType === 'adaVan';
                                                const isVanAda = stallType === 'adaVan';

                                                // === ANGLED PARKING SUPPORT FOR END ROW ===
                                                // EXCEPTION: ADA stalls are always 90° perpendicular per ADA 502.2
                                                if (isAngledParking && getStallCorners && !isAda) {
                                                    // End row uses same angled stall drawing as other rows
                                                    const stallCorners = getStallCorners(stallX, endRowY, false);
                                                    drawAngledStall(stallCorners, stallColor, '#ffffff');

                                                    // Calculate center for labels
                                                    const centerX = stallCorners.reduce((sum, c) => sum + c.x, 0) / 4;
                                                    const centerY = stallCorners.reduce((sum, c) => sum + c.y, 0) / 4;

                                                    // Type label at CENTER (EV, Compact)
                                                    if (stallLabel) {
                                                        ctx.save();
                                                        ctx.font = 'bold 12px sans-serif';
                                                        ctx.textAlign = 'center';
                                                        ctx.textBaseline = 'middle';
                                                        ctx.fillStyle = '#ffffff';
                                                        ctx.fillText(stallLabel, centerX * SCALE, centerY * SCALE);
                                                        ctx.restore();
                                                    }

                                                    // === STALL NUMBERING FOR END ROW - at REAR (near wheel stop) ===
                                                    if (showStallNumbers) {
                                                        const endRowLetter = String.fromCharCode(65 + interiorModules * 2);
                                                        const stallNumber = String(s + 1).padStart(3, '0');
                                                        const stallNumLabel = `${endRowLetter}-${stallNumber}`;

                                                        // Back edge midpoint
                                                        const backCenterX = (stallCorners[2].x + stallCorners[3].x) / 2;
                                                        const backCenterY = (stallCorners[2].y + stallCorners[3].y) / 2;
                                                        const rearX = (backCenterX + centerX) / 2;
                                                        const rearY = (backCenterY + centerY) / 2;

                                                        ctx.save();
                                                        ctx.font = 'bold 5px sans-serif';
                                                        ctx.textAlign = 'center';
                                                        ctx.textBaseline = 'middle';
                                                        ctx.fillStyle = '#374151';
                                                        ctx.fillText(stallNumLabel, rearX * SCALE, rearY * SCALE);
                                                        ctx.restore();
                                                    }
                                                } else {
                                                    // 90° perpendicular parking - draw rectangle
                                                    ctx.beginPath();
                                                    ctx.rect(stallX * SCALE, endRowY * SCALE, effStallWidth * SCALE, effStallDepth * SCALE);
                                                    ctx.fillStyle = stallColor;
                                                    ctx.fill();
                                                    ctx.strokeStyle = '#ffffff';
                                                    ctx.lineWidth = 2;
                                                    ctx.stroke();

                                                    // Type label at CENTER (ADA, EV, Compact)
                                                    if (stallLabel) {
                                                        ctx.save();
                                                        ctx.font = 'bold 12px sans-serif';
                                                        ctx.textAlign = 'center';
                                                        ctx.textBaseline = 'middle';
                                                        ctx.fillStyle = '#ffffff';
                                                        ctx.fillText(stallLabel, (stallX + effStallWidth / 2) * SCALE, (endRowY + effStallDepth / 2) * SCALE);
                                                        ctx.restore();
                                                    }

                                                    // === STALL NUMBERING FOR END ROW - at rear quarter, in front of wheel stop ===
                                                    if (showStallNumbers) {
                                                        const endRowLetter = String.fromCharCode(65 + interiorModules * 2);
                                                        const stallNumber = String(s + 1).padStart(3, '0');
                                                        const stallNumLabel = `${endRowLetter}-${stallNumber}`;

                                                        ctx.save();
                                                        ctx.font = 'bold 5px sans-serif';
                                                        ctx.textAlign = 'center';
                                                        ctx.textBaseline = 'middle';
                                                        ctx.fillStyle = '#374151';
                                                        // End row is bottom row, so rear is at bottom
                                                        // Position at 25% from rear edge (in front of wheel stop)
                                                        const rearOffset = effStallDepth * 0.25;
                                                        ctx.fillText(stallNumLabel, (stallX + effStallWidth / 2) * SCALE, (endRowY + effStallDepth - rearOffset) * SCALE);
                                                        ctx.restore();
                                                    }
                                                }
                                            }

                                            // === ADA PLACEMENT HOVER PREVIEW FOR END ROW ===
                                            const endRowGlobalIndex = interiorModules * 2;
                                            if (isPlacingAda && adaHoverIndex !== null && adaHoverRow === endRowGlobalIndex) {
                                                const previewClusterSize = adaStalls + 1;
                                                const previewStartIndex = adaHoverIndex;

                                                ctx.save();
                                                const highlightX = section.x + previewStartIndex * effStallWidth;
                                                const highlightWidth = previewClusterSize * effStallWidth;
                                                const highlightY = endRowY;
                                                const highlightHeight = effStallDepth;

                                                ctx.fillStyle = 'rgba(59, 130, 246, 0.3)';
                                                ctx.fillRect(highlightX * SCALE, highlightY * SCALE, highlightWidth * SCALE, highlightHeight * SCALE);

                                                ctx.strokeStyle = '#3b82f6';
                                                ctx.lineWidth = 3;
                                                ctx.setLineDash([5, 3]);
                                                ctx.strokeRect(highlightX * SCALE, highlightY * SCALE, highlightWidth * SCALE, highlightHeight * SCALE);
                                                ctx.setLineDash([]);

                                                ctx.fillStyle = '#1d4ed8';
                                                ctx.font = 'bold 14px sans-serif';
                                                ctx.textAlign = 'center';
                                                ctx.textBaseline = 'middle';
                                                const rowLetter = String.fromCharCode(65 + endRowGlobalIndex);
                                                ctx.fillText(
                                                    `♿ ${adaStalls} ADA + Aisle (Row ${rowLetter})`,
                                                    (highlightX + highlightWidth / 2) * SCALE,
                                                    (highlightY + highlightHeight / 2) * SCALE
                                                );
                                                ctx.restore();
                                            }

                                            // === WHEEL STOPS FOR END ROW (synced with 3D view) ===
                                            // Draw wheel stops for each stall in the end row
                                            const endWheelStopLength = 5;
                                            const endWheelStopWidth = 0.5;
                                            const endWheelStopInset = 2;
                                            // endRowGlobalIndex already declared above for hover preview

                                            ctx.save();
                                            ctx.fillStyle = '#9ca3af';
                                            ctx.strokeStyle = '#6b7280';
                                            ctx.lineWidth = 0.5;

                                            for (let ws = 0; ws < section.stallsPerRow; ws++) {
                                                // Skip ADA access aisle position on end row
                                                if (hasAda && adaStalls > 0 && adaRow === endRowGlobalIndex && ws === adaAccessAisleIndex) {
                                                    continue;
                                                }

                                                // Check if this stall is ADA on end row
                                                const isAdaStall = hasAda && adaRow === endRowGlobalIndex && ws >= adaStartIndex && ws <= adaEndIndex;

                                                // End row uses 90° geometry for all stalls (it's single-loaded, facing the aisle)
                                                // But we still need to handle ADA stall width correctly
                                                const stallX = section.x + ws * effStallWidth;

                                                // Polygon check for irregular shapes
                                                if (isIrregular && interiorPolygon && interiorPolygon.length >= 3) {
                                                    if (!isRectInPolygon(stallX, endRowY, effStallWidth, effStallDepth, interiorPolygon)) {
                                                        continue;
                                                    }
                                                } else {
                                                    if (stallX < interiorX || stallX + effStallWidth > interiorX + interiorW) continue;
                                                }

                                                const stopX = stallX + (effStallWidth - endWheelStopLength) / 2;
                                                // End row faces the aisle (top), so wheel stop at rear (bottom)
                                                const stopY = endRowY + effStallDepth - endWheelStopInset - endWheelStopWidth;
                                                ctx.beginPath();
                                                ctx.rect(stopX * SCALE, stopY * SCALE, endWheelStopLength * SCALE, endWheelStopWidth * SCALE);
                                                ctx.fill();
                                                ctx.stroke();
                                            }
                                            ctx.restore();
                                        });
                                    } // End of if (drawEndRow)
                                }

                                // End islands removed - internal aisles now connect directly to perimeter loop
                                // for proper traffic circulation flow

                                // ============================================================
                                // === PERIMETER CURBS (synced with 3D view) ===
                                // Draw raised curbs around the outer edge of the fire lane
                                // These define the lot boundary visually
                                // For irregular shapes: follow polygon edges
                                // For rectangular: use rounded corners
                                // ============================================================
                                ctx.save();
                                const curbWidth2D = 0.5; // 6 inches
                                ctx.strokeStyle = '#d1d5db'; // Light gray concrete
                                ctx.lineWidth = curbWidth2D * 2 * SCALE;

                                if (isIrregular && loopOuterPolygon && loopOuterPolygon.length >= 3) {
                                    // IRREGULAR: Draw curb along polygon edges
                                    drawPolygonPath(loopOuterPolygon);
                                    ctx.stroke();
                                } else {
                                    // RECTANGULAR: Draw curb with rounded corners
                                    const curbRadius = cornerRadius + curbWidth2D;
                                    drawRoundedRectPath(
                                        loopOuter.x - curbWidth2D,
                                        loopOuter.y - curbWidth2D,
                                        loopOuter.w + curbWidth2D * 2,
                                        loopOuter.h + curbWidth2D * 2,
                                        curbRadius
                                    );
                                    ctx.stroke();
                                }
                                ctx.restore();

                                // ============================================================
                                // === LIGHT POLES (synced with 3D view) ===
                                // Draw light poles at corners and along perimeter
                                // Controlled by showLightPoles config option
                                // ============================================================
                                if (showLightPoles) {
                                    ctx.save();
                                    const poleRadius2D = 1.5; // Visual size for 2D
                                    const fixtureSize2D = 3;

                                    const drawLightPole2D = (x, y, rotation = 0) => {
                                        // Pole base (circle)
                                        ctx.beginPath();
                                        ctx.arc(x * SCALE, y * SCALE, poleRadius2D * SCALE, 0, Math.PI * 2);
                                        ctx.fillStyle = '#4b5563'; // Dark gray metal
                                        ctx.fill();
                                        ctx.strokeStyle = '#374151';
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Fixture arm (line extending from pole)
                                        ctx.beginPath();
                                        const armEndX = x + Math.cos(rotation) * fixtureSize2D;
                                        const armEndY = y + Math.sin(rotation) * fixtureSize2D;
                                        ctx.moveTo(x * SCALE, y * SCALE);
                                        ctx.lineTo(armEndX * SCALE, armEndY * SCALE);
                                        ctx.strokeStyle = '#4b5563';
                                        ctx.lineWidth = 2;
                                        ctx.stroke();

                                        // Light fixture (small rectangle at end)
                                        ctx.beginPath();
                                        ctx.arc(armEndX * SCALE, armEndY * SCALE, 1.5 * SCALE, 0, Math.PI * 2);
                                        ctx.fillStyle = '#fef3c7'; // Warm white
                                        ctx.fill();
                                        ctx.strokeStyle = '#fcd34d';
                                        ctx.lineWidth = 1;
                                        ctx.stroke();
                                    };

                                    const poleOffset = 3; // 3ft outside the loop curb
                                    const poleSpacing = 80;

                                    if (isIrregular && loopOuterPolygon && loopOuterPolygon.length >= 3) {
                                        // IRREGULAR POLYGON: Place poles at vertices and along edges
                                        // Use winding direction to determine outward (opposite of inward)
                                        let signedArea = 0;
                                        for (let i = 0; i < loopOuterPolygon.length; i++) {
                                            const curr = loopOuterPolygon[i];
                                            const next = loopOuterPolygon[(i + 1) % loopOuterPolygon.length];
                                            signedArea += (next.x - curr.x) * (next.y + curr.y);
                                        }
                                        const windingSign = signedArea > 0 ? 1 : -1;

                                        for (let i = 0; i < loopOuterPolygon.length; i++) {
                                            const prev = loopOuterPolygon[(i - 1 + loopOuterPolygon.length) % loopOuterPolygon.length];
                                            const p1 = loopOuterPolygon[i];
                                            const p2 = loopOuterPolygon[(i + 1) % loopOuterPolygon.length];

                                            // Edge vectors for bisector calculation
                                            const dx1 = p1.x - prev.x;
                                            const dy1 = p1.y - prev.y;
                                            const dx2 = p2.x - p1.x;
                                            const dy2 = p2.y - p1.y;
                                            const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1) || 1;
                                            const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 1;

                                            // Outward normals using winding (opposite of inward)
                                            const n1x = -windingSign * dy1 / len1;
                                            const n1y = windingSign * dx1 / len1;
                                            const n2x = -windingSign * dy2 / len2;
                                            const n2y = windingSign * dx2 / len2;

                                            // Bisector (average of outward normals)
                                            let bx = (n1x + n2x) / 2;
                                            let by = (n1y + n2y) / 2;
                                            const bLen = Math.sqrt(bx * bx + by * by) || 1;
                                            bx /= bLen;
                                            by /= bLen;

                                            // Corner pole (placed OUTSIDE the loop, in landscaping strip)
                                            const cornerX = p1.x + bx * poleOffset;
                                            const cornerY = p1.y + by * poleOffset;
                                            const cornerAngle = Math.atan2(-by, -bx); // Fixture points inward
                                            drawLightPole2D(cornerX, cornerY, cornerAngle);

                                            // Edge poles (every ~80ft along edge)
                                            const edgeLen = Math.sqrt(dx2 * dx2 + dy2 * dy2);
                                            const numEdgePoles = Math.max(0, Math.floor(edgeLen / poleSpacing) - 1);
                                            if (numEdgePoles > 0) {
                                                const ux = dx2 / edgeLen;
                                                const uy = dy2 / edgeLen;
                                                // Outward perpendicular for this edge
                                                const outX = -windingSign * uy;
                                                const outY = windingSign * ux;
                                                for (let j = 1; j <= numEdgePoles; j++) {
                                                    const t = j * edgeLen / (numEdgePoles + 1);
                                                    const edgeX = p1.x + ux * t;
                                                    const edgeY = p1.y + uy * t;
                                                    const px = edgeX + outX * poleOffset;
                                                    const py = edgeY + outY * poleOffset;
                                                    const poleAngle = Math.atan2(-outY, -outX); // Point inward
                                                    drawLightPole2D(px, py, poleAngle);
                                                }
                                            }
                                        }
                                    } else {
                                        // RECTANGULAR: Original rectangle-based pole placement
                                        // Corner poles (at corners of the perimeter loop)
                                        drawLightPole2D(loopOuter.x - poleOffset, loopOuter.y - poleOffset, Math.PI / 4);
                                        drawLightPole2D(loopOuter.x + loopOuter.w + poleOffset, loopOuter.y - poleOffset, Math.PI * 3 / 4);
                                        drawLightPole2D(loopOuter.x - poleOffset, loopOuter.y + loopOuter.h + poleOffset, -Math.PI / 4);
                                        drawLightPole2D(loopOuter.x + loopOuter.w + poleOffset, loopOuter.y + loopOuter.h + poleOffset, -Math.PI * 3 / 4);

                                        // Edge poles (every ~80ft along perimeter loop)
                                        const topBottomPoleCount = Math.max(0, Math.floor(loopOuter.w / poleSpacing) - 1);
                                        const sidesPoleCount = Math.max(0, Math.floor(loopOuter.h / poleSpacing) - 1);

                                        // Top edge poles
                                        for (let i = 1; i <= topBottomPoleCount; i++) {
                                            const poleX = loopOuter.x + i * loopOuter.w / (topBottomPoleCount + 1);
                                            drawLightPole2D(poleX, loopOuter.y - poleOffset, Math.PI / 2);
                                        }
                                        // Bottom edge poles
                                        for (let i = 1; i <= topBottomPoleCount; i++) {
                                            const poleX = loopOuter.x + i * loopOuter.w / (topBottomPoleCount + 1);
                                            drawLightPole2D(poleX, loopOuter.y + loopOuter.h + poleOffset, -Math.PI / 2);
                                        }
                                        // Left edge poles
                                        for (let i = 1; i <= sidesPoleCount; i++) {
                                            const poleZ = loopOuter.y + i * loopOuter.h / (sidesPoleCount + 1);
                                            drawLightPole2D(loopOuter.x - poleOffset, poleZ, 0);
                                        }
                                        // Right edge poles
                                        for (let i = 1; i <= sidesPoleCount; i++) {
                                            const poleZ = loopOuter.y + i * loopOuter.h / (sidesPoleCount + 1);
                                            drawLightPole2D(loopOuter.x + loopOuter.w + poleOffset, poleZ, Math.PI);
                                        }
                                    }
                                    ctx.restore();
                                }

                                // Note: Drive aisle crosswalks removed for feasibility stage
                                // Crosswalks are added during design development when building location is known
                                // and ADA-compliant pedestrian routes are planned

                                // === TESTFIT-STYLE SUMMARY PANEL ===
                                const panelX = setbackX + buildableW + 10;
                                const panelY = setbackY;
                                const panelW = 90;
                                const panelH = 100;

                                // Only draw panel if there's room
                                if (panelX + panelW < boundary.reduce((max, p) => Math.max(max, p.x), 0) + 50) {
                                    ctx.beginPath();
                                    ctx.roundRect(panelX * SCALE, panelY * SCALE, panelW * SCALE, panelH * SCALE, 4 * SCALE);
                                    ctx.fillStyle = 'rgba(17, 24, 39, 0.9)';
                                    ctx.fill();
                                    ctx.strokeStyle = '#374151';
                                    ctx.stroke();

                                    ctx.save();
                                    ctx.textAlign = 'left';

                                    // Title
                                    ctx.font = 'bold 10px sans-serif';
                                    ctx.fillStyle = '#f3f4f6';
                                    ctx.fillText('PARKING SUMMARY', (panelX + 5) * SCALE, (panelY + 12) * SCALE);

                                    // Total
                                    ctx.font = 'bold 14px sans-serif';
                                    ctx.fillStyle = '#fbbf24';
                                    ctx.fillText(`${counts.total} STALLS`, (panelX + 5) * SCALE, (panelY + 28) * SCALE);

                                    // Breakdown
                                    ctx.font = '9px sans-serif';
                                    let lineY = 42;

                                    ctx.fillStyle = colors.standard;
                                    ctx.fillText(`● Standard: ${counts.standard}`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);
                                    lineY += 12;

                                    ctx.fillStyle = colors.compact;
                                    ctx.fillText(`● Compact: ${counts.compact}`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);
                                    lineY += 12;

                                    ctx.fillStyle = colors.ada;
                                    const adaCodeMin = adaCodeRequirements.total;
                                    const adaExtraLabel = adaExtra > 0 ? ` (+${adaExtra})` : '';
                                    ctx.fillText(`● ADA: ${counts.ada}${adaExtraLabel}${counts.adaVan > 0 ? ` (${counts.adaVan} Van)` : ''}`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);
                                    lineY += 12;

                                    ctx.fillStyle = colors.ev;
                                    ctx.fillText(`● EV: ${counts.ev}`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);
                                    lineY += 12;

                                    // Show stalls removed by custom aisles
                                    if (stallsRemovedByAisles > 0) {
                                        ctx.fillStyle = '#f97316'; // Orange
                                        ctx.fillText(`● Aisle -${stallsRemovedByAisles}`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);
                                        lineY += 12;
                                    }

                                    // Dimensions
                                    ctx.fillStyle = '#9ca3af';
                                    ctx.font = '8px sans-serif';
                                    ctx.fillText(`${stallWidth}'×${stallDepth}' @ ${parkingAngle}°`, (panelX + 5) * SCALE, (panelY + lineY) * SCALE);

                                    ctx.restore();
                                }

                                // === DRAW ENTRY/EXIT ===
                                // Entry/exit extends outward from the site boundary into the street
                                // IMPORTANT: We restore the clip to allow drawing outside the boundary
                                if (entryExitParams) {
                                    // Temporarily remove boundary clip to draw entry/exit outside
                                    ctx.restore(); // Remove boundary clip
                                    ctx.save(); // Save clean state for entry/exit drawing

                                    const {
                                        entryExitType: eeType,
                                        centerX,
                                        centerY,
                                        outwardAngle,
                                        laneWidth,
                                        throatDepth,
                                        flareWidth,
                                        dividerWidth,
                                        loopWidth: eeLoopWidth,
                                        entryLaneLocalX,
                                        exitLaneLocalX,
                                        hasGateBooth: eeGateBooth,
                                        hasCrosswalk: eeCrosswalk,
                                        colors: eeColors,
                                        SCALE: eeSCALE
                                    } = entryExitParams;

                                    // ========================================
                                    // STANDARD ENTRY/EXIT (Per ITE/MUTCD)
                                    // 12ft lanes, throat depth per code, center divider
                                    // ========================================
                                    if (eeType === 'standard' || eeType === 'perpendicular') {
                                        ctx.save();
                                        ctx.translate(centerX * eeSCALE, centerY * eeSCALE);
                                        // CRITICAL: outwardAngle is the direction pointing AWAY from lot
                                        // We want the throat to extend in this direction
                                        // The throat is drawn in +Y local coords, so rotate to align +Y with outward
                                        // outwardAngle - PI/2 rotates so +Y points in outwardAngle direction
                                        ctx.rotate(outwardAngle - Math.PI / 2);

                                        // Entry throat
                                        ctx.beginPath();
                                        ctx.moveTo(entryLaneLocalX * eeSCALE, 0);
                                        ctx.lineTo((entryLaneLocalX + laneWidth) * eeSCALE, 0);
                                        ctx.lineTo((entryLaneLocalX + laneWidth + flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((entryLaneLocalX - flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
                                        ctx.fill();
                                        ctx.strokeStyle = eeColors.entry;
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Entry arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.7)';
                                        ctx.font = 'bold 10px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▲', (entryLaneLocalX + laneWidth / 2) * eeSCALE, (throatDepth - 8) * eeSCALE);
                                        ctx.restore();

                                        // Entry label
                                        ctx.save();
                                        ctx.fillStyle = eeColors.entry;
                                        ctx.font = 'bold 8px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('ENTRY', (entryLaneLocalX + laneWidth / 2) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.restore();

                                        // Exit throat
                                        ctx.beginPath();
                                        ctx.moveTo(exitLaneLocalX * eeSCALE, 0);
                                        ctx.lineTo((exitLaneLocalX + laneWidth) * eeSCALE, 0);
                                        ctx.lineTo((exitLaneLocalX + laneWidth + flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((exitLaneLocalX - flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)';
                                        ctx.fill();
                                        ctx.strokeStyle = eeColors.exit;
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Exit arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.7)';
                                        ctx.font = 'bold 10px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▼', (exitLaneLocalX + laneWidth / 2) * eeSCALE, (throatDepth - 8) * eeSCALE);
                                        ctx.restore();

                                        // Exit label
                                        ctx.save();
                                        ctx.fillStyle = eeColors.exit;
                                        ctx.font = 'bold 8px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('EXIT', (exitLaneLocalX + laneWidth / 2) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.restore();

                                        // Center divider
                                        ctx.beginPath();
                                        ctx.moveTo(0, 0);
                                        ctx.lineTo(0, throatDepth * eeSCALE);
                                        ctx.strokeStyle = '#166534';
                                        ctx.lineWidth = dividerWidth * eeSCALE;
                                        ctx.stroke();

                                        // Crosswalk
                                        if (eeCrosswalk) {
                                            const crosswalkLocalY = 3;
                                            const crosswalkHeight = 6;
                                            const stripeWidth = 2;
                                            const stripeGap = 2;
                                            ctx.save();
                                            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                                            const entryStripes = Math.floor(laneWidth / (stripeWidth + stripeGap));
                                            for (let s = 0; s < entryStripes; s++) {
                                                const stripeX = entryLaneLocalX + s * (stripeWidth + stripeGap) + 1;
                                                ctx.fillRect(stripeX * eeSCALE, crosswalkLocalY * eeSCALE, stripeWidth * eeSCALE, crosswalkHeight * eeSCALE);
                                            }
                                            const exitStripes = Math.floor(laneWidth / (stripeWidth + stripeGap));
                                            for (let s = 0; s < exitStripes; s++) {
                                                const stripeX = exitLaneLocalX + s * (stripeWidth + stripeGap) + 1;
                                                ctx.fillRect(stripeX * eeSCALE, crosswalkLocalY * eeSCALE, stripeWidth * eeSCALE, crosswalkHeight * eeSCALE);
                                            }
                                            ctx.restore();
                                        }

                                        // Gate booth
                                        if (eeGateBooth) {
                                            const boothWidth = 6;
                                            const boothDepth = 8;
                                            const boothLocalY = 15;
                                            // TICKET booth (entry side) - Yellow
                                            const entryBoothX = entryLaneLocalX + laneWidth + 2;
                                            ctx.beginPath();
                                            ctx.rect(entryBoothX * eeSCALE, boothLocalY * eeSCALE, boothWidth * eeSCALE, boothDepth * eeSCALE);
                                            ctx.fillStyle = '#fbbf24';
                                            ctx.fill();
                                            ctx.strokeStyle = '#d97706';
                                            ctx.lineWidth = 1;
                                            ctx.stroke();
                                            // TICKET label (matches 3D)
                                            ctx.save();
                                            ctx.fillStyle = '#000000';
                                            ctx.font = 'bold 5px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';
                                            ctx.fillText('TICKET', (entryBoothX + boothWidth / 2) * eeSCALE, (boothLocalY + boothDepth / 2) * eeSCALE);
                                            ctx.restore();
                                            const gateArmLocalY = boothLocalY + boothDepth / 2;
                                            ctx.beginPath();
                                            ctx.moveTo((entryLaneLocalX + laneWidth - 1) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.lineTo((entryLaneLocalX + 2) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.strokeStyle = '#dc2626';
                                            ctx.lineWidth = 2;
                                            ctx.stroke();
                                            // PAY booth (exit side) - Green
                                            const exitBoothX = exitLaneLocalX - boothWidth - 2;
                                            ctx.beginPath();
                                            ctx.rect(exitBoothX * eeSCALE, boothLocalY * eeSCALE, boothWidth * eeSCALE, boothDepth * eeSCALE);
                                            ctx.fillStyle = '#34d399';
                                            ctx.fill();
                                            ctx.strokeStyle = '#059669';
                                            ctx.lineWidth = 1;
                                            ctx.stroke();
                                            // PAY label (matches 3D)
                                            ctx.save();
                                            ctx.fillStyle = '#000000';
                                            ctx.font = 'bold 5px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';
                                            ctx.fillText('PAY', (exitBoothX + boothWidth / 2) * eeSCALE, (boothLocalY + boothDepth / 2) * eeSCALE);
                                            ctx.restore();
                                            ctx.beginPath();
                                            ctx.moveTo((exitLaneLocalX + 1) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.lineTo((exitLaneLocalX + laneWidth - 2) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.strokeStyle = '#dc2626';
                                            ctx.lineWidth = 2;
                                            ctx.stroke();
                                        }

                                        // Street edge indicator
                                        ctx.save();
                                        ctx.strokeStyle = '#4b5563';
                                        ctx.lineWidth = 2;
                                        ctx.beginPath();
                                        ctx.moveTo((exitLaneLocalX - flareWidth / 2 - 3) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((entryLaneLocalX + laneWidth + flareWidth / 2 + 3) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.stroke();
                                        ctx.restore();

                                        // Connection to circulation loop
                                        ctx.beginPath();
                                        ctx.rect(exitLaneLocalX * eeSCALE, -eeLoopWidth * eeSCALE, laneWidth * eeSCALE, eeLoopWidth * eeSCALE);
                                        ctx.fillStyle = eeColors.loop;
                                        ctx.fill();
                                        ctx.beginPath();
                                        ctx.rect(entryLaneLocalX * eeSCALE, -eeLoopWidth * eeSCALE, laneWidth * eeSCALE, eeLoopWidth * eeSCALE);
                                        ctx.fillStyle = eeColors.loop;
                                        ctx.fill();

                                        ctx.restore();
                                    }
                                    // ========================================
                                    // CHANNELIZED ENTRY/EXIT (Per ITE Parking Generation)
                                    // Raised median island separating entry/exit lanes
                                    // ========================================
                                    else if (eeType === 'channelized' || eeType === 'parallel') {
                                        // Channelized entry: Two separate lanes with raised island between
                                        // Per ITE: 12ft lanes, 6ft minimum raised median, 30ft throat depth
                                        const islandWidth = 8; // Raised median island width (6-10ft per code)
                                        const islandLength = throatDepth - 5; // Island doesn't extend to street edge

                                        ctx.save();
                                        ctx.translate(centerX * eeSCALE, centerY * eeSCALE);
                                        ctx.rotate(outwardAngle - Math.PI / 2);

                                        // Entry lane (right side for right-hand traffic)
                                        ctx.beginPath();
                                        ctx.moveTo((islandWidth / 2) * eeSCALE, 0);
                                        ctx.lineTo((islandWidth / 2 + laneWidth) * eeSCALE, 0);
                                        ctx.lineTo((islandWidth / 2 + laneWidth + flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((islandWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
                                        ctx.fill();
                                        ctx.strokeStyle = eeColors.entry;
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Entry arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.7)';
                                        ctx.font = 'bold 10px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▲', (islandWidth / 2 + laneWidth / 2) * eeSCALE, (throatDepth - 8) * eeSCALE);
                                        ctx.restore();

                                        // Entry label
                                        ctx.save();
                                        ctx.fillStyle = eeColors.entry;
                                        ctx.font = 'bold 8px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('ENTRY', (islandWidth / 2 + laneWidth / 2) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.restore();

                                        // Exit lane (left side for right-hand traffic)
                                        ctx.beginPath();
                                        ctx.moveTo((-islandWidth / 2) * eeSCALE, 0);
                                        ctx.lineTo((-islandWidth / 2 - laneWidth) * eeSCALE, 0);
                                        ctx.lineTo((-islandWidth / 2 - laneWidth - flareWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((-islandWidth / 2) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.15)';
                                        ctx.fill();
                                        ctx.strokeStyle = eeColors.exit;
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Exit arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.7)';
                                        ctx.font = 'bold 10px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▼', (-islandWidth / 2 - laneWidth / 2) * eeSCALE, (throatDepth - 8) * eeSCALE);
                                        ctx.restore();

                                        // Exit label
                                        ctx.save();
                                        ctx.fillStyle = eeColors.exit;
                                        ctx.font = 'bold 8px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('EXIT', (-islandWidth / 2 - laneWidth / 2) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.restore();

                                        // Raised median island (channelization)
                                        ctx.beginPath();
                                        // Tapered nose at street side
                                        ctx.moveTo(0, 0);
                                        ctx.lineTo((islandWidth / 2) * eeSCALE, 3 * eeSCALE);
                                        ctx.lineTo((islandWidth / 2) * eeSCALE, islandLength * eeSCALE);
                                        ctx.lineTo((-islandWidth / 2) * eeSCALE, islandLength * eeSCALE);
                                        ctx.lineTo((-islandWidth / 2) * eeSCALE, 3 * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.4)';
                                        ctx.fill();
                                        ctx.strokeStyle = '#166534';
                                        ctx.lineWidth = 2;
                                        ctx.stroke();

                                        // Island hatching (indicates raised curb)
                                        ctx.save();
                                        ctx.strokeStyle = '#166534';
                                        ctx.lineWidth = 0.5;
                                        for (let y = 5; y < islandLength - 2; y += 4) {
                                            ctx.beginPath();
                                            ctx.moveTo((-islandWidth / 2 + 1) * eeSCALE, y * eeSCALE);
                                            ctx.lineTo((islandWidth / 2 - 1) * eeSCALE, y * eeSCALE);
                                            ctx.stroke();
                                        }
                                        ctx.restore();

                                        // Crosswalk
                                        if (eeCrosswalk) {
                                            const crosswalkLocalY = 3;
                                            const crosswalkHeight = 6;
                                            const stripeWidth = 2;
                                            const stripeGap = 2;
                                            ctx.save();
                                            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                                            // Entry lane stripes
                                            const entryStripes = Math.floor(laneWidth / (stripeWidth + stripeGap));
                                            for (let s = 0; s < entryStripes; s++) {
                                                const stripeX = islandWidth / 2 + s * (stripeWidth + stripeGap) + 1;
                                                ctx.fillRect(stripeX * eeSCALE, crosswalkLocalY * eeSCALE, stripeWidth * eeSCALE, crosswalkHeight * eeSCALE);
                                            }
                                            // Exit lane stripes
                                            const exitStripes = Math.floor(laneWidth / (stripeWidth + stripeGap));
                                            for (let s = 0; s < exitStripes; s++) {
                                                const stripeX = -islandWidth / 2 - laneWidth + s * (stripeWidth + stripeGap) + 1;
                                                ctx.fillRect(stripeX * eeSCALE, crosswalkLocalY * eeSCALE, stripeWidth * eeSCALE, crosswalkHeight * eeSCALE);
                                            }
                                            ctx.restore();
                                        }

                                        // Gate booth
                                        if (eeGateBooth) {
                                            const boothWidth = 6;
                                            const boothDepth = 8;
                                            const boothLocalY = 15;
                                            // TICKET booth (entry side) - Yellow
                                            const entryBoothX = islandWidth / 2 + laneWidth + 2;
                                            ctx.beginPath();
                                            ctx.rect(entryBoothX * eeSCALE, boothLocalY * eeSCALE, boothWidth * eeSCALE, boothDepth * eeSCALE);
                                            ctx.fillStyle = '#fbbf24';
                                            ctx.fill();
                                            ctx.strokeStyle = '#d97706';
                                            ctx.lineWidth = 1;
                                            ctx.stroke();
                                            // TICKET label (matches 3D)
                                            ctx.save();
                                            ctx.fillStyle = '#000000';
                                            ctx.font = 'bold 5px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';
                                            ctx.fillText('TICKET', (entryBoothX + boothWidth / 2) * eeSCALE, (boothLocalY + boothDepth / 2) * eeSCALE);
                                            ctx.restore();
                                            // Entry gate arm
                                            const gateArmLocalY = boothLocalY + boothDepth / 2;
                                            ctx.beginPath();
                                            ctx.moveTo((islandWidth / 2 + laneWidth - 1) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.lineTo((islandWidth / 2 + 2) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.strokeStyle = '#dc2626';
                                            ctx.lineWidth = 2;
                                            ctx.stroke();
                                            // PAY booth (exit side) - Green
                                            const exitBoothX = -islandWidth / 2 - laneWidth - boothWidth - 2;
                                            ctx.beginPath();
                                            ctx.rect(exitBoothX * eeSCALE, boothLocalY * eeSCALE, boothWidth * eeSCALE, boothDepth * eeSCALE);
                                            ctx.fillStyle = '#34d399';
                                            ctx.fill();
                                            ctx.strokeStyle = '#059669';
                                            ctx.lineWidth = 1;
                                            ctx.stroke();
                                            // PAY label (matches 3D)
                                            ctx.save();
                                            ctx.fillStyle = '#000000';
                                            ctx.font = 'bold 5px sans-serif';
                                            ctx.textAlign = 'center';
                                            ctx.textBaseline = 'middle';
                                            ctx.fillText('PAY', (exitBoothX + boothWidth / 2) * eeSCALE, (boothLocalY + boothDepth / 2) * eeSCALE);
                                            ctx.restore();
                                            // Exit gate arm
                                            ctx.beginPath();
                                            ctx.moveTo((-islandWidth / 2 - 1) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.lineTo((-islandWidth / 2 - laneWidth + 2) * eeSCALE, gateArmLocalY * eeSCALE);
                                            ctx.strokeStyle = '#dc2626';
                                            ctx.lineWidth = 2;
                                            ctx.stroke();
                                        }

                                        // Street edge indicator
                                        ctx.save();
                                        ctx.strokeStyle = '#4b5563';
                                        ctx.lineWidth = 2;
                                        ctx.beginPath();
                                        ctx.moveTo((-islandWidth / 2 - laneWidth - flareWidth / 2 - 5) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((islandWidth / 2 + laneWidth + flareWidth / 2 + 5) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.stroke();
                                        ctx.restore();

                                        // Connection to circulation loop
                                        ctx.beginPath();
                                        ctx.rect((-islandWidth / 2 - laneWidth) * eeSCALE, -eeLoopWidth * eeSCALE, laneWidth * eeSCALE, eeLoopWidth * eeSCALE);
                                        ctx.fillStyle = eeColors.loop;
                                        ctx.fill();
                                        ctx.beginPath();
                                        ctx.rect((islandWidth / 2) * eeSCALE, -eeLoopWidth * eeSCALE, laneWidth * eeSCALE, eeLoopWidth * eeSCALE);
                                        ctx.fillStyle = eeColors.loop;
                                        ctx.fill();

                                        ctx.restore();
                                    }
                                    // ========================================
                                    // FULL ACCESS ENTRY/EXIT (Wide Curb Cut)
                                    // Single wide opening, all movements allowed
                                    // ========================================
                                    else if (eeType === 'fullAccess' || eeType === 'angled') {
                                        // Full access: Wide single opening without channelization
                                        // Per local codes: typically 24-36ft wide, minimal throat
                                        const fullWidth = laneWidth * 2 + 4; // Two lanes plus clearance
                                        const curbRadius = 8; // Curb return radius

                                        ctx.save();
                                        ctx.translate(centerX * eeSCALE, centerY * eeSCALE);
                                        ctx.rotate(outwardAngle - Math.PI / 2);

                                        // Main driveway opening
                                        ctx.beginPath();
                                        ctx.moveTo((-fullWidth / 2) * eeSCALE, 0);
                                        ctx.lineTo((fullWidth / 2) * eeSCALE, 0);
                                        // Flared at street with curb returns
                                        ctx.lineTo((fullWidth / 2 + curbRadius) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((-fullWidth / 2 - curbRadius) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.closePath();
                                        ctx.fillStyle = 'rgba(156, 163, 175, 0.2)';
                                        ctx.fill();
                                        ctx.strokeStyle = '#6b7280';
                                        ctx.lineWidth = 1;
                                        ctx.stroke();

                                        // Center line (dashed, advisory)
                                        ctx.save();
                                        ctx.setLineDash([4, 4]);
                                        ctx.strokeStyle = '#fbbf24';
                                        ctx.lineWidth = 1;
                                        ctx.beginPath();
                                        ctx.moveTo(0, 2 * eeSCALE);
                                        ctx.lineTo(0, (throatDepth - 2) * eeSCALE);
                                        ctx.stroke();
                                        ctx.setLineDash([]);
                                        ctx.restore();

                                        // Entry side indicator (right for right-hand traffic)
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.3)';
                                        ctx.beginPath();
                                        ctx.rect(2 * eeSCALE, 2 * eeSCALE, (fullWidth / 2 - 4) * eeSCALE, (throatDepth - 4) * eeSCALE);
                                        ctx.fill();
                                        ctx.restore();

                                        // Exit side indicator (left for right-hand traffic)
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.3)';
                                        ctx.beginPath();
                                        ctx.rect((-fullWidth / 2 + 2) * eeSCALE, 2 * eeSCALE, (fullWidth / 2 - 4) * eeSCALE, (throatDepth - 4) * eeSCALE);
                                        ctx.fill();
                                        ctx.restore();

                                        // Entry arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(34, 197, 94, 0.8)';
                                        ctx.font = 'bold 12px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▲', (fullWidth / 4) * eeSCALE, (throatDepth / 2) * eeSCALE);
                                        ctx.restore();

                                        // Exit arrow
                                        ctx.save();
                                        ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
                                        ctx.font = 'bold 12px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillText('▼', (-fullWidth / 4) * eeSCALE, (throatDepth / 2) * eeSCALE);
                                        ctx.restore();

                                        // Labels
                                        ctx.save();
                                        ctx.font = 'bold 8px sans-serif';
                                        ctx.textAlign = 'center';
                                        ctx.textBaseline = 'middle';
                                        ctx.fillStyle = eeColors.entry;
                                        ctx.fillText('ENTRY', (fullWidth / 4) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.fillStyle = eeColors.exit;
                                        ctx.fillText('EXIT', (-fullWidth / 4) * eeSCALE, (throatDepth + 6) * eeSCALE);
                                        ctx.restore();

                                        // Crosswalk (full width)
                                        if (eeCrosswalk) {
                                            const crosswalkLocalY = 3;
                                            const crosswalkHeight = 6;
                                            const stripeWidth = 2;
                                            const stripeGap = 2;
                                            ctx.save();
                                            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                                            const numStripes = Math.floor(fullWidth / (stripeWidth + stripeGap));
                                            for (let s = 0; s < numStripes; s++) {
                                                const stripeX = -fullWidth / 2 + s * (stripeWidth + stripeGap) + 1;
                                                ctx.fillRect(stripeX * eeSCALE, crosswalkLocalY * eeSCALE, stripeWidth * eeSCALE, crosswalkHeight * eeSCALE);
                                            }
                                            ctx.restore();
                                        }

                                        // Street edge indicator
                                        ctx.save();
                                        ctx.strokeStyle = '#4b5563';
                                        ctx.lineWidth = 2;
                                        ctx.beginPath();
                                        ctx.moveTo((-fullWidth / 2 - curbRadius - 5) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.lineTo((fullWidth / 2 + curbRadius + 5) * eeSCALE, throatDepth * eeSCALE);
                                        ctx.stroke();
                                        ctx.restore();

                                        // Connection to circulation loop (full width)
                                        ctx.beginPath();
                                        ctx.rect((-fullWidth / 2) * eeSCALE, -eeLoopWidth * eeSCALE, fullWidth * eeSCALE, eeLoopWidth * eeSCALE);
                                        ctx.fillStyle = eeColors.loop;
                                        ctx.fill();

                                        ctx.restore();
                                    }

                                    // Restore from entry/exit drawing and re-apply boundary clip
                                    ctx.restore(); // Restore from entry/exit save
                                    ctx.save(); // New save for remaining operations
                                    if (boundary && boundary.length >= 3) {
                                        ctx.beginPath();
                                        ctx.moveTo(boundary[0].x * SCALE, boundary[0].y * SCALE);
                                        for (let i = 1; i < boundary.length; i++) {
                                            ctx.lineTo(boundary[i].x * SCALE, boundary[i].y * SCALE);
                                        }
                                        ctx.closePath();
                                        ctx.clip();
                                    }
                                }

                                // === DRAW CIRCULATION ARROWS (MUTCD-compliant spacing) ===
                                // Per MUTCD: Directional arrows every 50-100 ft in parking lots
                                ctx.save();
                                ctx.fillStyle = '#ffffff'; // White arrows
                                ctx.font = 'bold 16px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';

                                const arrowOffset = loopWidth / 2;
                                const ARROW_SPACING_FT = 60; // 60 ft between arrows (MUTCD standard range: 50-100 ft)
                                const laneOffsetFt = loopWidth / 4; // Offset for two-way lanes

                                // Compute polygon winding direction (same as offsetPolygon uses)
                                const getWindingSign = (poly) => {
                                    if (!poly || poly.length < 3) return 1;
                                    let signedArea = 0;
                                    for (let i = 0; i < poly.length; i++) {
                                        const curr = poly[i];
                                        const next = poly[(i + 1) % poly.length];
                                        signedArea += (next.x - curr.x) * (next.y + curr.y);
                                    }
                                    return signedArea > 0 ? 1 : -1;
                                };

                                // Helper to draw arrows along polygon edge - supports one-way and two-way
                                // Uses winding direction to determine correct inward perpendicular
                                const drawArrowsAlongPolygonEdge = (polygon, inwardOffset, isTwoWay) => {
                                    if (!polygon || polygon.length < 3) return;
                                    const windingSign = getWindingSign(polygon);

                                    for (let i = 0; i < polygon.length; i++) {
                                        const p1 = polygon[i];
                                        const p2 = polygon[(i + 1) % polygon.length];
                                        const dx = p2.x - p1.x;
                                        const dy = p2.y - p1.y;
                                        const edgeLen = Math.sqrt(dx * dx + dy * dy);
                                        if (edgeLen < 20) continue; // Skip short edges

                                        // Unit vectors along edge
                                        const ux = dx / edgeLen;
                                        const uy = dy / edgeLen;

                                        // Inward perpendicular based on winding (same as offsetPolygon)
                                        const nx = windingSign * uy;
                                        const ny = windingSign * -ux;

                                        // Number of arrows on this edge
                                        const numArrows = Math.max(1, Math.floor(edgeLen / ARROW_SPACING_FT));
                                        const spacing = edgeLen / (numArrows + 1);
                                        const angle = Math.atan2(dy, dx);

                                        for (let a = 1; a <= numArrows; a++) {
                                            // Position along edge, then offset inward using perpendicular
                                            const t = a * spacing;
                                            const edgeX = p1.x + ux * t;
                                            const edgeY = p1.y + uy * t;
                                            const baseX = edgeX + nx * inwardOffset;
                                            const baseY = edgeY + ny * inwardOffset;

                                            if (isTwoWay) {
                                                // Two-way: draw two arrows offset from centerline
                                                // Outer lane arrow (further from center)
                                                const ax1 = baseX - nx * laneOffsetFt;
                                                const ay1 = baseY - ny * laneOffsetFt;
                                                ctx.save();
                                                ctx.translate(ax1 * SCALE, ay1 * SCALE);
                                                ctx.rotate(angle);
                                                ctx.fillText('→', 0, 0);
                                                ctx.restore();

                                                // Inner lane arrow (closer to center)
                                                const ax2 = baseX + nx * laneOffsetFt;
                                                const ay2 = baseY + ny * laneOffsetFt;
                                                ctx.save();
                                                ctx.translate(ax2 * SCALE, ay2 * SCALE);
                                                ctx.rotate(angle + Math.PI); // Opposite direction
                                                ctx.fillText('→', 0, 0);
                                                ctx.restore();
                                            } else {
                                                // One-way: single arrow at centerline
                                                ctx.save();
                                                ctx.translate(baseX * SCALE, baseY * SCALE);
                                                ctx.rotate(angle);
                                                ctx.fillText('→', 0, 0);
                                                ctx.restore();
                                            }
                                        }
                                    }
                                };

                                // Helper to draw centerline along polygon edges (no corner intersections)
                                const drawCenterlineAlongPolygon = (polygon, inwardOffset) => {
                                    if (!polygon || polygon.length < 3) return;
                                    const windingSign = getWindingSign(polygon);

                                    // Draw each edge as a separate dashed line (no corner connections)
                                    for (let i = 0; i < polygon.length; i++) {
                                        const p1 = polygon[i];
                                        const p2 = polygon[(i + 1) % polygon.length];
                                        const dx = p2.x - p1.x;
                                        const dy = p2.y - p1.y;
                                        const edgeLen = Math.sqrt(dx * dx + dy * dy);
                                        if (edgeLen < 20) continue; // Skip short edges

                                        const ux = dx / edgeLen;
                                        const uy = dy / edgeLen;

                                        // Inward perpendicular based on winding
                                        const nx = windingSign * uy;
                                        const ny = windingSign * -ux;

                                        // Offset start and end points inward, with margin from corners
                                        const margin = 10;
                                        const x1 = (p1.x + ux * margin + nx * inwardOffset) * SCALE;
                                        const y1 = (p1.y + uy * margin + ny * inwardOffset) * SCALE;
                                        const x2 = (p2.x - ux * margin + nx * inwardOffset) * SCALE;
                                        const y2 = (p2.y - uy * margin + ny * inwardOffset) * SCALE;

                                        ctx.beginPath();
                                        ctx.moveTo(x1, y1);
                                        ctx.lineTo(x2, y2);
                                        ctx.stroke();
                                    }
                                };

                                if (isIrregular && loopOuterPolygon && loopOuterPolygon.length >= 3) {
                                    // IRREGULAR POLYGON: Draw arrows along polygon edges
                                    drawArrowsAlongPolygonEdge(loopOuterPolygon, arrowOffset, driveType === 'twoWay');

                                    // Center dashed line for two-way
                                    if (driveType === 'twoWay') {
                                        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
                                        ctx.lineWidth = 1;
                                        ctx.setLineDash([8, 6]);
                                        drawCenterlineAlongPolygon(loopOuterPolygon, arrowOffset);
                                        ctx.setLineDash([]);
                                    }
                                } else {
                                    // RECTANGULAR: Use shared layout values for sync with 3D
                                    // Calculate number of arrows based on actual street length
                                    const topBottomLength = loopOuter.w - 2 * loopWidth; // Exclude corners
                                    const leftRightLength = loopOuter.h - 2 * loopWidth;

                                    const numArrowsHorizontal = Math.max(1, Math.floor(topBottomLength / ARROW_SPACING_FT));
                                    const numArrowsVertical = Math.max(1, Math.floor(leftRightLength / ARROW_SPACING_FT));

                                    const topStartX = loopOuter.x + loopWidth;
                                    const topSpacing = topBottomLength / (numArrowsHorizontal + 1);
                                    const sideStartY = loopOuter.y + loopWidth;
                                    const sideSpacing = leftRightLength / (numArrowsVertical + 1);

                                    if (driveType === 'twoWay') {
                                        // TWO-WAY: Bidirectional arrows on each segment
                                        for (let i = 1; i <= numArrowsHorizontal; i++) {
                                            const arrowX = topStartX + i * topSpacing;
                                            ctx.fillText('←', arrowX * SCALE, (loopOuter.y + arrowOffset - 5) * SCALE);
                                            ctx.fillText('→', arrowX * SCALE, (loopOuter.y + arrowOffset + 5) * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsHorizontal; i++) {
                                            const arrowX = topStartX + i * topSpacing;
                                            ctx.fillText('→', arrowX * SCALE, (loopOuter.y + loopOuter.h - arrowOffset - 5) * SCALE);
                                            ctx.fillText('←', arrowX * SCALE, (loopOuter.y + loopOuter.h - arrowOffset + 5) * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsVertical; i++) {
                                            const arrowY = sideStartY + i * sideSpacing;
                                            ctx.fillText('↑', (loopOuter.x + loopOuter.w - arrowOffset - 5) * SCALE, arrowY * SCALE);
                                            ctx.fillText('↓', (loopOuter.x + loopOuter.w - arrowOffset + 5) * SCALE, arrowY * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsVertical; i++) {
                                            const arrowY = sideStartY + i * sideSpacing;
                                            ctx.fillText('↓', (loopOuter.x + arrowOffset - 5) * SCALE, arrowY * SCALE);
                                            ctx.fillText('↑', (loopOuter.x + arrowOffset + 5) * SCALE, arrowY * SCALE);
                                        }
                                    } else {
                                        // ONE-WAY / HYBRID: Counter-clockwise circulation
                                        for (let i = 1; i <= numArrowsHorizontal; i++) {
                                            const arrowX = topStartX + i * topSpacing;
                                            const arrowY = loopOuter.y + arrowOffset;
                                            ctx.fillText('→', arrowX * SCALE, arrowY * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsVertical; i++) {
                                            const arrowX = loopOuter.x + loopOuter.w - arrowOffset;
                                            const arrowY = sideStartY + i * sideSpacing;
                                            ctx.fillText('↓', arrowX * SCALE, arrowY * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsHorizontal; i++) {
                                            const arrowX = topStartX + i * topSpacing;
                                            const arrowY = loopOuter.y + loopOuter.h - arrowOffset;
                                            ctx.fillText('←', arrowX * SCALE, arrowY * SCALE);
                                        }
                                        for (let i = 1; i <= numArrowsVertical; i++) {
                                            const arrowX = loopOuter.x + arrowOffset;
                                            const arrowY = sideStartY + i * sideSpacing;
                                            ctx.fillText('↑', arrowX * SCALE, arrowY * SCALE);
                                        }
                                    }

                                    // Center dashed line for two-way perimeter streets
                                    if (driveType === 'twoWay') {
                                        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
                                        ctx.lineWidth = 1;
                                        ctx.setLineDash([8, 6]);

                                        ctx.beginPath();
                                        ctx.moveTo((loopOuter.x + 10) * SCALE, (loopOuter.y + arrowOffset) * SCALE);
                                        ctx.lineTo((loopOuter.x + loopOuter.w - 10) * SCALE, (loopOuter.y + arrowOffset) * SCALE);
                                        ctx.stroke();

                                        ctx.beginPath();
                                        ctx.moveTo((loopOuter.x + 10) * SCALE, (loopOuter.y + loopOuter.h - arrowOffset) * SCALE);
                                        ctx.lineTo((loopOuter.x + loopOuter.w - 10) * SCALE, (loopOuter.y + loopOuter.h - arrowOffset) * SCALE);
                                        ctx.stroke();

                                        ctx.beginPath();
                                        ctx.moveTo((loopOuter.x + arrowOffset) * SCALE, (loopOuter.y + loopWidth + 10) * SCALE);
                                        ctx.lineTo((loopOuter.x + arrowOffset) * SCALE, (loopOuter.y + loopOuter.h - loopWidth - 10) * SCALE);
                                        ctx.stroke();

                                        ctx.beginPath();
                                        ctx.moveTo((loopOuter.x + loopOuter.w - arrowOffset) * SCALE, (loopOuter.y + loopWidth + 10) * SCALE);
                                        ctx.lineTo((loopOuter.x + loopOuter.w - arrowOffset) * SCALE, (loopOuter.y + loopOuter.h - loopWidth - 10) * SCALE);
                                        ctx.stroke();

                                        ctx.setLineDash([]);
                                    }
                                }
                                ctx.restore();

                                // === CROSS-AISLE SPINE (drawn on top of stalls, connected to perimeter) ===
                                // Helper function to draw a single spine
                                const drawSpine = (spineXPos, spineTopY, spineBottomY, isPreview = false) => {
                                    const spineFullHeight = spineBottomY - spineTopY;
                                    if (spineFullHeight <= 0) return;

                                    // Draw spine as simple rectangle
                                    ctx.beginPath();
                                    ctx.rect(spineXPos * SCALE, spineTopY * SCALE, effectiveAisleWidth * SCALE, spineFullHeight * SCALE);
                                    ctx.fillStyle = isPreview ? 'rgba(59, 130, 246, 0.5)' : colors.loop;
                                    ctx.fill();

                                    if (isPreview) {
                                        ctx.strokeStyle = '#3b82f6';
                                        ctx.lineWidth = 2;
                                        ctx.setLineDash([5, 5]);
                                        ctx.stroke();
                                        ctx.setLineDash([]);
                                    }

                                    // Spine directional arrows
                                    ctx.save();
                                    ctx.fillStyle = isPreview ? 'rgba(255, 255, 255, 0.7)' : '#ffffff';
                                    ctx.font = 'bold 16px sans-serif';
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';

                                    // Calculate number of arrows based on spine length
                                    const numSpineArrows = Math.max(1, Math.floor(spineFullHeight / ARROW_SPACING_FT));
                                    const spineArrowSpacing = spineFullHeight / (numSpineArrows + 1);

                                    // Always two-way for cross-aisle
                                    for (let i = 1; i <= numSpineArrows; i++) {
                                        const arrowY = spineTopY + i * spineArrowSpacing;
                                        ctx.fillText('↓', (spineXPos + effectiveAisleWidth * 0.25) * SCALE, arrowY * SCALE);
                                        ctx.fillText('↑', (spineXPos + effectiveAisleWidth * 0.75) * SCALE, arrowY * SCALE);
                                    }
                                    ctx.restore();

                                    // Center dashed line for two-way traffic
                                    if (!isPreview) {
                                        ctx.save();
                                        ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
                                        ctx.lineWidth = 1;
                                        ctx.setLineDash([8, 6]);
                                        ctx.beginPath();
                                        const spineCenterX = (spineXPos + effectiveAisleWidth / 2) * SCALE;
                                        ctx.moveTo(spineCenterX, (spineTopY + 10) * SCALE);
                                        ctx.lineTo(spineCenterX, (spineBottomY - 10) * SCALE);
                                        ctx.stroke();
                                        ctx.setLineDash([]);
                                        ctx.restore();
                                    }
                                };

                                // Standard perimeter bounds for spines
                                const spineTopY = loopOuter.y + loopWidth;
                                const spineBottomY = loopOuter.y + loopOuter.h - loopWidth;

                                // Only draw auto-generated spines if no custom aisles exist
                                if (drawnAisles.length === 0) {
                                    // 1. Draw standard center spine (for rectangular lots in auto/force mode)
                                    if (useCrossAisle && !isIrregular) {
                                        drawSpine(spineX, spineTopY, spineBottomY);
                                    }

                                    // 2. Draw auto-detected spines for irregular shapes in force mode
                                    if (crossAisleMode === 'force' && isIrregular && hasCrossAisle) {
                                        if (autoSpinePositions.length > 0) {
                                            // Use auto-detected positions
                                            autoSpinePositions.forEach(spine => {
                                                drawSpine(spine.x - effectiveAisleWidth / 2, spine.minY, spine.maxY);
                                            });
                                        } else {
                                            // Fallback: draw center spine using bounding box center
                                            // This ensures force mode always shows something for irregular shapes
                                            const centerSpineX = bayX + bayW / 2 - effectiveAisleWidth / 2;
                                            drawSpine(centerSpineX, spineTopY, spineBottomY);
                                        }
                                    }

                                    // 3. Draw manually placed spines
                                    if (manualSpines.length > 0) {
                                        manualSpines.forEach(spine => {
                                            drawSpine(spine.x - effectiveAisleWidth / 2, spineTopY, spineBottomY);
                                        });
                                    }

                                    // 4. Draw spine hover preview
                                    if (isPlacingSpine && spineHoverX !== null) {
                                        drawSpine(spineHoverX - effectiveAisleWidth / 2, spineTopY, spineBottomY, true);
                                    }
                                } // End of drawnAisles.length === 0 check for spines

                            } // End of if (!parkingAreaTooSmall)

                        } // End of if (hasParkingLayout)

                        // === DRAW CUSTOM DRIVE AISLES ===
                        // Always draw custom aisles regardless of parking area size or parkingLayout availability
                        // First, restore context to remove any clipping that might hide aisles
                        ctx.restore();
                        ctx.save();

                        // Helper function to draw a drive aisle path with width
                        const drawAislePath = (points, isPreview = false) => {
                            if (!points || points.length < 2) return;

                            // Validate all points have valid coordinates
                            const validPoints = points.filter(p =>
                                p && typeof p.x === 'number' && typeof p.y === 'number' &&
                                !isNaN(p.x) && !isNaN(p.y) && isFinite(p.x) && isFinite(p.y)
                            );
                            if (validPoints.length < 2) return;

                            // Use aisle width from config or default 24ft
                            // Note: effectiveAisleWidth is only available inside hasParkingLayout block
                            const aisleWidth = effectiveMassingConfig?.aisleWidth || 24;

                            ctx.save();

                            // Draw the path as a thick line (representing the aisle width)
                            ctx.beginPath();
                            ctx.moveTo(validPoints[0].x * SCALE, validPoints[0].y * SCALE);
                            for (let i = 1; i < validPoints.length; i++) {
                                ctx.lineTo(validPoints[i].x * SCALE, validPoints[i].y * SCALE);
                            }

                            ctx.lineWidth = aisleWidth * SCALE;
                            ctx.lineCap = 'round';
                            ctx.lineJoin = 'round';
                            ctx.strokeStyle = isPreview ? 'rgba(59, 130, 246, 0.5)' : (colors?.loop || '#4b5563');
                            ctx.stroke();

                            // Draw center dashed line
                            ctx.beginPath();
                            ctx.moveTo(validPoints[0].x * SCALE, validPoints[0].y * SCALE);
                            for (let i = 1; i < validPoints.length; i++) {
                                ctx.lineTo(validPoints[i].x * SCALE, validPoints[i].y * SCALE);
                            }
                            ctx.lineWidth = 2;
                            ctx.setLineDash([8, 6]);
                            ctx.strokeStyle = isPreview ? 'rgba(255, 255, 255, 0.7)' : 'rgba(255, 255, 255, 0.5)';
                            ctx.stroke();
                            ctx.setLineDash([]);

                            // Draw direction arrows along the path
                            if (!isPreview) {
                                ctx.fillStyle = '#ffffff';
                                ctx.font = 'bold 14px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';

                                for (let i = 0; i < validPoints.length - 1; i++) {
                                    const p1 = validPoints[i];
                                    const p2 = validPoints[i + 1];
                                    const midX = (p1.x + p2.x) / 2;
                                    const midY = (p1.y + p2.y) / 2;
                                    const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

                                    // Draw arrow at midpoint
                                    ctx.save();
                                    ctx.translate(midX * SCALE, midY * SCALE);
                                    ctx.rotate(angle);
                                    ctx.fillText('→', 0, 0);
                                    ctx.restore();
                                }
                            }

                            // Draw vertex circles
                            validPoints.forEach((pt, idx) => {
                                ctx.beginPath();
                                ctx.arc(pt.x * SCALE, pt.y * SCALE, isPreview ? 6 : 4, 0, Math.PI * 2);
                                ctx.fillStyle = idx === 0 ? '#22c55e' : (idx === validPoints.length - 1 ? '#ef4444' : '#3b82f6');
                                ctx.fill();
                                ctx.strokeStyle = '#ffffff';
                                ctx.lineWidth = 2;
                                ctx.stroke();
                            });

                            ctx.restore();
                        };

                        // 5. Draw saved custom aisles
                        if (drawnAisles.length > 0) {
                            drawnAisles.forEach((aisle) => {
                                drawAislePath(aisle.points);
                            });

                            // === DRAW EDIT HANDLES WHEN IN EDITING MODE ===
                            if (isEditingAisles) {
                                // Build junctions for visual display
                                const junctions = buildAisleJunctions(drawnAisles, 10);
                                const junctionPointKeys = new Set();
                                junctions.forEach(j => {
                                    j.connections.forEach(c => {
                                        junctionPointKeys.add(`${c.aisleId}-${c.pointIndex}`);
                                    });
                                });

                                // Draw junction handles (yellow squares - shared points)
                                junctions.forEach(junction => {
                                    const isHovered = hoveredAislePoint?.type === 'junction' &&
                                        hoveredAislePoint.junctionId === junction.id;
                                    const isDragging = draggingAislePoint?.type === 'junction' &&
                                        draggingAislePoint.junctionId === junction.id;

                                    ctx.save();
                                    ctx.beginPath();
                                    const handleSize = (isHovered || isDragging) ? 16 : 14;
                                    ctx.rect(
                                        junction.x * SCALE - handleSize / 2,
                                        junction.y * SCALE - handleSize / 2,
                                        handleSize, handleSize
                                    );
                                    ctx.fillStyle = isDragging ? '#f59e0b' : (isHovered ? '#fbbf24' : '#eab308');
                                    ctx.fill();
                                    ctx.strokeStyle = '#ffffff';
                                    ctx.lineWidth = 2;
                                    ctx.stroke();

                                    // Draw connection count badge
                                    ctx.fillStyle = '#000000';
                                    ctx.font = 'bold 10px sans-serif';
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';
                                    ctx.fillText(junction.connections.length.toString(), junction.x * SCALE, junction.y * SCALE);
                                    ctx.restore();
                                });

                                // Draw individual point handles (circles - non-junction points)
                                drawnAisles.forEach(aisle => {
                                    aisle.points.forEach((pt, idx) => {
                                        const pointKey = `${aisle.id}-${idx}`;
                                        if (junctionPointKeys.has(pointKey)) return; // Skip junction points

                                        const isHovered = hoveredAislePoint?.type === 'point' &&
                                            hoveredAislePoint.aisleId === aisle.id &&
                                            hoveredAislePoint.pointIndex === idx;
                                        const isDragging = draggingAislePoint?.type === 'point' &&
                                            draggingAislePoint.aisleId === aisle.id &&
                                            draggingAislePoint.pointIndex === idx;

                                        ctx.save();
                                        ctx.beginPath();
                                        const radius = (isHovered || isDragging) ? 12 : 10;
                                        ctx.arc(pt.x * SCALE, pt.y * SCALE, radius, 0, Math.PI * 2);

                                        // Color based on position and state
                                        let fillColor;
                                        if (isDragging) {
                                            fillColor = '#f97316'; // Orange when dragging
                                        } else if (isHovered) {
                                            fillColor = '#fb923c'; // Light orange when hovered
                                        } else if (idx === 0) {
                                            fillColor = '#22c55e'; // Green for start
                                        } else if (idx === aisle.points.length - 1) {
                                            fillColor = '#ef4444'; // Red for end
                                        } else {
                                            fillColor = '#3b82f6'; // Blue for middle
                                        }

                                        ctx.fillStyle = fillColor;
                                        ctx.fill();
                                        ctx.strokeStyle = '#ffffff';
                                        ctx.lineWidth = 2;
                                        ctx.stroke();
                                        ctx.restore();
                                    });
                                });
                            }
                        }

                        // 6. Draw current aisle being drawn (with hover preview)
                        if (currentAislePoints.length > 0) {
                            // Draw the current path
                            const previewPoints = aisleHoverPoint
                                ? [...currentAislePoints, aisleHoverPoint]
                                : currentAislePoints;
                            drawAislePath(previewPoints, true);
                        }

                        // 7. Draw snap indicator when hovering near existing aisle point
                        if (aisleHoverPoint && aisleHoverPoint.snapped) {
                            ctx.save();
                            // Draw a larger ring to indicate snap point
                            ctx.beginPath();
                            ctx.arc(aisleHoverPoint.x * SCALE, aisleHoverPoint.y * SCALE, 15, 0, Math.PI * 2);
                            ctx.strokeStyle = '#22c55e';
                            ctx.lineWidth = 3;
                            ctx.setLineDash([4, 4]);
                            ctx.stroke();
                            ctx.setLineDash([]);

                            // Draw inner filled circle
                            ctx.beginPath();
                            ctx.arc(aisleHoverPoint.x * SCALE, aisleHoverPoint.y * SCALE, 8, 0, Math.PI * 2);
                            ctx.fillStyle = '#22c55e';
                            ctx.fill();
                            ctx.strokeStyle = '#ffffff';
                            ctx.lineWidth = 2;
                            ctx.stroke();
                            ctx.restore();
                        }

                        // === DRAW VEHICLES (Swept Path Analysis) ===
                        // Always draw vehicles regardless of parking area size
                        // Clear previous vehicle hit boxes
                        vehicles2DRef.current = [];

                        if (vehicles.length > 0) {
                            vehicles.forEach(vehicle => {
                                const spec = VEHICLE_TYPES[vehicle.type];
                                if (!spec) return;

                                const vx = vehicle.x * SCALE;
                                const vy = vehicle.y * SCALE;
                                const vLength = spec.length * SCALE;
                                const vWidth = spec.width * SCALE;
                                const rotRad = (vehicle.rotation * Math.PI) / 180;

                                // Draw swept path with ghost vehicle outlines
                                if (vehicleTrailsVisible && vehicle.trail.length > 0) {
                                    ctx.save();

                                    // Draw ghost vehicles at intervals along the trail
                                    const ghostInterval = Math.max(1, Math.floor(vehicle.trail.length / 30));

                                    for (let i = 0; i < vehicle.trail.length; i += ghostInterval) {
                                        const tp = vehicle.trail[i];
                                        const ghostX = tp.x * SCALE;
                                        const ghostY = tp.y * SCALE;
                                        const ghostRotRad = (tp.rotation * Math.PI) / 180;
                                        const progress = i / vehicle.trail.length;
                                        const opacity = 0.15 + progress * 0.25;

                                        ctx.save();
                                        ctx.translate(ghostX, ghostY);
                                        ctx.rotate(ghostRotRad);
                                        ctx.globalAlpha = opacity;
                                        ctx.beginPath();
                                        ctx.rect(-vLength / 2, -vWidth / 2, vLength, vWidth);
                                        ctx.fillStyle = spec.color;
                                        ctx.fill();
                                        ctx.strokeStyle = spec.color;
                                        ctx.lineWidth = 1;
                                        ctx.stroke();
                                        ctx.restore();
                                    }

                                    // Swept path envelope lines
                                    ctx.globalAlpha = 0.3;
                                    ctx.strokeStyle = spec.color;
                                    ctx.lineWidth = 1;
                                    ctx.setLineDash([4, 4]);

                                    // Left side
                                    ctx.beginPath();
                                    for (let i = 0; i < vehicle.trail.length; i++) {
                                        const tp = vehicle.trail[i];
                                        const ghostRotRad = (tp.rotation * Math.PI) / 180;
                                        const offsetX = -Math.sin(ghostRotRad) * (spec.width / 2);
                                        const offsetY = Math.cos(ghostRotRad) * (spec.width / 2);
                                        const edgeX = tp.x * SCALE + offsetX * SCALE;
                                        const edgeY = tp.y * SCALE + offsetY * SCALE;
                                        if (i === 0) ctx.moveTo(edgeX, edgeY);
                                        else ctx.lineTo(edgeX, edgeY);
                                    }
                                    const currOffsetX = -Math.sin(rotRad) * (spec.width / 2);
                                    const currOffsetY = Math.cos(rotRad) * (spec.width / 2);
                                    ctx.lineTo(vx + currOffsetX * SCALE, vy + currOffsetY * SCALE);
                                    ctx.stroke();

                                    // Right side
                                    ctx.beginPath();
                                    for (let i = 0; i < vehicle.trail.length; i++) {
                                        const tp = vehicle.trail[i];
                                        const ghostRotRad = (tp.rotation * Math.PI) / 180;
                                        const offsetX = Math.sin(ghostRotRad) * (spec.width / 2);
                                        const offsetY = -Math.cos(ghostRotRad) * (spec.width / 2);
                                        const edgeX = tp.x * SCALE + offsetX * SCALE;
                                        const edgeY = tp.y * SCALE + offsetY * SCALE;
                                        if (i === 0) ctx.moveTo(edgeX, edgeY);
                                        else ctx.lineTo(edgeX, edgeY);
                                    }
                                    ctx.lineTo(vx - currOffsetX * SCALE, vy - currOffsetY * SCALE);
                                    ctx.stroke();

                                    // Center line
                                    ctx.globalAlpha = 0.6;
                                    ctx.lineWidth = 2;
                                    ctx.setLineDash([]);
                                    ctx.beginPath();
                                    ctx.moveTo(vehicle.trail[0].x * SCALE, vehicle.trail[0].y * SCALE);
                                    for (let i = 1; i < vehicle.trail.length; i++) {
                                        ctx.lineTo(vehicle.trail[i].x * SCALE, vehicle.trail[i].y * SCALE);
                                    }
                                    ctx.lineTo(vx, vy);
                                    ctx.stroke();

                                    ctx.restore();
                                }

                                // Turning radius indicator
                                if (vehicleTurningRadiusVisible && selectedVehicle === vehicle.id) {
                                    ctx.save();
                                    ctx.strokeStyle = spec.color;
                                    ctx.lineWidth = 1;
                                    ctx.setLineDash([4, 4]);
                                    ctx.globalAlpha = 0.4;
                                    ctx.beginPath();
                                    ctx.arc(vx, vy, spec.minTurningRadius * SCALE, 0, Math.PI * 2);
                                    ctx.stroke();
                                    ctx.setLineDash([]);
                                    ctx.restore();
                                }

                                // Draw vehicle body
                                ctx.save();
                                ctx.translate(vx, vy);
                                ctx.rotate(rotRad);

                                ctx.beginPath();
                                ctx.rect(-vLength / 2, -vWidth / 2, vLength, vWidth);
                                ctx.fillStyle = selectedVehicle === vehicle.id ? spec.color : spec.color + 'cc';
                                ctx.fill();
                                ctx.strokeStyle = selectedVehicle === vehicle.id ? '#ffffff' : '#000000';
                                ctx.lineWidth = selectedVehicle === vehicle.id ? 3 : 1;
                                ctx.stroke();

                                // Front indicator
                                ctx.beginPath();
                                ctx.moveTo(vLength / 2, -vWidth / 4);
                                ctx.lineTo(vLength / 2 + 4, 0);
                                ctx.lineTo(vLength / 2, vWidth / 4);
                                ctx.closePath();
                                ctx.fillStyle = '#ffffff';
                                ctx.fill();

                                // Wheels
                                const wheelLength = 3 * SCALE;
                                const wheelWidth = 1.5 * SCALE;
                                const wheelOffsetX = spec.wheelbase / 2 * SCALE - vLength / 2 + spec.frontOverhang * SCALE;
                                ctx.fillStyle = '#1f2937';
                                ctx.fillRect(wheelOffsetX + spec.wheelbase * SCALE / 2 - wheelLength / 2, -vWidth / 2 - wheelWidth / 2, wheelLength, wheelWidth);
                                ctx.fillRect(wheelOffsetX + spec.wheelbase * SCALE / 2 - wheelLength / 2, vWidth / 2 - wheelWidth / 2, wheelLength, wheelWidth);
                                ctx.fillRect(wheelOffsetX - wheelLength / 2, -vWidth / 2 - wheelWidth / 2, wheelLength, wheelWidth);
                                ctx.fillRect(wheelOffsetX - wheelLength / 2, vWidth / 2 - wheelWidth / 2, wheelLength, wheelWidth);

                                // Vehicle icon
                                ctx.rotate(-rotRad);
                                ctx.fillStyle = '#ffffff';
                                ctx.font = 'bold 10px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                ctx.fillText(spec.icon, 0, 0);

                                ctx.restore();

                                // Store hit box
                                vehicles2DRef.current.push({
                                    id: vehicle.id,
                                    x: vehicle.x,
                                    y: vehicle.y,
                                    width: spec.length,
                                    height: spec.width,
                                    rotation: vehicle.rotation,
                                });
                            });
                        }

                        // === DRAW EXCLUSION ZONES ON TOP OF PARKING ===
                        // Draw exclusions after parking so they are visible
                        if (exclusions && exclusions.length > 0) {
                            exclusions.forEach((ex) => {
                                if (!ex || ex.length < 3) return;
                                ctx.beginPath();
                                ctx.moveTo(ex[0].x * SCALE, ex[0].y * SCALE);
                                for (let i = 1; i < ex.length; i++) {
                                    ctx.lineTo(ex[i].x * SCALE, ex[i].y * SCALE);
                                }
                                ctx.closePath();
                                ctx.fillStyle = 'rgba(239, 68, 68, 0.4)';
                                ctx.fill();
                                ctx.strokeStyle = '#dc2626';
                                ctx.lineWidth = 3;
                                ctx.stroke();

                                // Add "EXCLUSION" label
                                const centerX = ex.reduce((sum, p) => sum + p.x, 0) / ex.length;
                                const centerY = ex.reduce((sum, p) => sum + p.y, 0) / ex.length;
                                ctx.save();
                                ctx.font = 'bold 10px sans-serif';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                ctx.fillStyle = '#dc2626';
                                ctx.fillText('⛔ EXCLUSION', centerX * SCALE, centerY * SCALE);
                                ctx.restore();
                            });
                        }

                        // === END OF SURFACE PARKING ===

                    } else if (buildingType === 'parking' && massType === 'podium') {
                        // Parking Podium: Parking structure with amenity podium
                        // Amenity podium base (template building 0)
                        drawRect(setbackX, setbackY, buildableW, buildableD * 0.25, 'rgba(34, 197, 94, 0.4)', '#22c55e', true, 0);
                        // Parking structure above (template building 1)
                        drawRect(setbackX + 10, setbackY + buildableD * 0.25 + 5, buildableW - 20, buildableD * 0.7, podiumColor, '#6b7280', true, 1);
                        // Ramp indicator
                        ctx.beginPath();
                        ctx.moveTo((setbackX + 20) * SCALE, (setbackY + buildableD * 0.6) * SCALE);
                        ctx.lineTo((setbackX + 40) * SCALE, (setbackY + buildableD * 0.6 - 15) * SCALE);
                        ctx.lineTo((setbackX + 40) * SCALE, (setbackY + buildableD * 0.6 + 15) * SCALE);
                        ctx.closePath();
                        ctx.fillStyle = '#4b5563';
                        ctx.fill();
                    } else if (buildingType === 'parking') {
                        // Structured parking (selectable as building 0) - default parking massing
                        drawRect(setbackX + 10, setbackY + 10, buildableW - 20, buildableD - 20, podiumColor, '#6b7280', true, 0);
                        // Ramp indicator
                        ctx.beginPath();
                        ctx.moveTo((setbackX + 20) * SCALE, (setbackY + buildableD / 2) * SCALE);
                        ctx.lineTo((setbackX + 40) * SCALE, (setbackY + buildableD / 2 - 20) * SCALE);
                        ctx.lineTo((setbackX + 40) * SCALE, (setbackY + buildableD / 2 + 20) * SCALE);
                        ctx.closePath();
                        ctx.fillStyle = '#4b5563';
                        ctx.fill();

                    } else {
                        // Default: Simple rectangular building (selectable as building 0)
                        const bldgW = buildableW * Math.sqrt(lotCoverage);
                        const bldgD = buildableD * Math.sqrt(lotCoverage);
                        const offX = (buildableW - bldgW) / 2;
                        const offY = (buildableD - bldgD) / 2;
                        drawRect(setbackX + offX, setbackY + offY, bldgW, bldgD, buildColor, buildStroke, true, 0);
                    }

                    // Show massing type label (in screen coordinates, not affected by pan/zoom)
                    ctx.save();
                    ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset to screen coordinates
                    ctx.font = 'bold 14px sans-serif';
                    ctx.textAlign = 'left';
                    ctx.textBaseline = 'bottom';
                    // Draw with background for readability
                    const massingLabel = currentMassing ? `${currentMassing.icon || 'P'} ${currentMassing.name || 'Surface'}` : 'P Surface';
                    const labelMetrics = ctx.measureText(massingLabel);
                    // White background with border for readability
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
                    ctx.fillRect(10, h - 35, labelMetrics.width + 16, 28);
                    ctx.strokeStyle = 'rgba(100, 116, 139, 0.3)';
                    ctx.lineWidth = 1;
                    ctx.strokeRect(10, h - 35, labelMetrics.width + 16, 28);
                    ctx.fillStyle = '#1e293b';
                    ctx.fillText(massingLabel, 18, h - 14);
                    ctx.restore();

                    // Store template buildings for click detection and UI rendering
                    templateBuildings2DRef.current = templateBuildings2D;
                    // Store amenities for click detection
                    amenities2DRef.current = amenities2D;
                    // Update state when buildings change (for UI rendering)
                    const buildingsChanged = templateBuildings2D.length !== templateBuildingsList.length ||
                        templateBuildings2D.some((b, i) => {
                            const existing = templateBuildingsList[i];
                            return !existing || b.x !== existing.x || b.y !== existing.y;
                        });
                    if (buildingsChanged) {
                        setTemplateBuildingsList([...templateBuildings2D]);
                    }

                    // === END IRREGULAR SHAPE CLIPPING ===
                    // Restore canvas state to remove clipping
                    ctx.restore();

                    // === REDRAW BOUNDARY ON TOP OF MASSING ===
                    // This ensures the site boundary is always visible and interactive
                    if (boundary.length >= 3) {
                        // Draw boundary polygon outline
                        ctx.beginPath();
                        ctx.moveTo(boundary[0].x * SCALE, boundary[0].y * SCALE);
                        for (let i = 1; i < boundary.length; i++) {
                            ctx.lineTo(boundary[i].x * SCALE, boundary[i].y * SCALE);
                        }
                        ctx.closePath();
                        ctx.strokeStyle = isEditingBoundary ? '#22d3ee' : '#4ade80';
                        ctx.lineWidth = isEditingBoundary ? 3 : 2;
                        ctx.stroke();

                        // Highlight hovered edge when editing
                        if (isEditingBoundary && hoveredBoundaryEdge !== null) {
                            const p1 = boundary[hoveredBoundaryEdge];
                            const p2 = boundary[(hoveredBoundaryEdge + 1) % boundary.length];
                            ctx.beginPath();
                            ctx.moveTo(p1.x * SCALE, p1.y * SCALE);
                            ctx.lineTo(p2.x * SCALE, p2.y * SCALE);
                            ctx.strokeStyle = '#f97316';
                            ctx.lineWidth = 5;
                            ctx.stroke();
                        }

                        // Draw vertices on top
                        boundary.forEach((pt, i) => {
                            const isHovered = isEditingBoundary && hoveredBoundaryVertex === i;
                            const radius = isEditingBoundary ? (isHovered ? 10 : 7) : 5;

                            ctx.beginPath();
                            ctx.arc(pt.x * SCALE, pt.y * SCALE, radius, 0, Math.PI * 2);

                            if (isEditingBoundary) {
                                ctx.fillStyle = isHovered ? '#22d3ee' : '#ffffff';
                                ctx.fill();
                                ctx.strokeStyle = '#0891b2';
                                ctx.lineWidth = 2;
                                ctx.stroke();
                            } else {
                                ctx.fillStyle = i === 0 ? '#22c55e' : '#4ade80';
                                ctx.fill();
                                ctx.strokeStyle = '#166534';
                                ctx.lineWidth = 1;
                                ctx.stroke();
                            }
                        });

                        // Show edge midpoints when editing
                        if (isEditingBoundary) {
                            for (let i = 0; i < boundary.length; i++) {
                                const p1 = boundary[i];
                                const p2 = boundary[(i + 1) % boundary.length];
                                const midX = (p1.x + p2.x) / 2 * SCALE;
                                const midY = (p1.y + p2.y) / 2 * SCALE;

                                ctx.beginPath();
                                ctx.arc(midX, midY, 4, 0, Math.PI * 2);
                                ctx.fillStyle = '#94a3b8';
                                ctx.fill();
                            }
                        }
                    }

                    // === FIXED MASSING TYPE LABEL (outside clip region) ===
                    // Show current massing type at bottom-left of canvas
                    if (buildingType === 'parking' && massType === 'surface') {
                        ctx.save();
                        ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset to identity (screen coords)
                        ctx.font = 'bold 14px sans-serif';
                        ctx.textAlign = 'left';
                        ctx.textBaseline = 'middle';
                        const surfaceLabel = '🅿️ Surface';
                        const surfaceLabelMetrics = ctx.measureText(surfaceLabel);
                        // White background with green border
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
                        ctx.fillRect(12, h - 75, surfaceLabelMetrics.width + 20, 28);
                        ctx.strokeStyle = '#22c55e';
                        ctx.lineWidth = 2;
                        ctx.strokeRect(12, h - 75, surfaceLabelMetrics.width + 20, 28);
                        ctx.fillStyle = '#1e293b';
                        ctx.fillText(surfaceLabel, 22, h - 61);
                        ctx.restore();
                    }

                } // End of else block (buildable area is valid)
            }
        }

        // ====================================================================
        // 3D MODE: Isometric visualization
        // ====================================================================
        if (viewMode === '3d' && boundary.length >= 3 && !isDrawing) {
            // Calculate building dimensions based on massing type (using user-editable params)
            const massingConfig = effectiveMassingConfig;
            const floorH = massingConfig.floorHeight || currentSubtype?.floorHeight || 10;
            const configFloors = massingConfig.floors || massingConfig.totalFloors || massingConfig.towerFloors || currentSubtype?.floors || 4;
            const floors = Math.min(configFloors, Math.floor(heightLimit / floorH));
            const totalHeight = floors * floorH;
            const coverage = lotCoverage;

            // Calculate site bounds
            const minX = Math.min(...boundary.map(p => p.x));
            const maxX = Math.max(...boundary.map(p => p.x));
            const minY = Math.min(...boundary.map(p => p.y));
            const maxY = Math.max(...boundary.map(p => p.y));
            const siteW = maxX - minX;
            const siteD = maxY - minY;

            // Isometric projection - center on canvas
            // Adjust scale based on expected building heights for the massing type
            const maxExpectedHeight = massingConfig.towerFloors
                ? (massingConfig.towerFloors * (massingConfig.floorHeight || 10) + (massingConfig.podiumHeight || 36))
                : (configFloors * floorH);
            const baseIsoScale = Math.min(w / (siteW * 1.8), h / (siteD * 1.5 + maxExpectedHeight * 0.8)) * 0.75;
            const isoScale = baseIsoScale;
            const heightScale = isoScale * 0.6; // Height exaggeration for visibility
            const centerX = w / 2;
            const centerY = h * 0.55 + maxExpectedHeight * heightScale * 0.3; // Push down to make room for tall buildings

            const isoX = (x, y) => centerX + ((x - minX - siteW / 2) - (y - minY - siteD / 2)) * 0.866 * isoScale;
            const isoY = (x, y, z = 0) => centerY + ((x - minX - siteW / 2) + (y - minY - siteD / 2)) * 0.5 * isoScale - z * heightScale;

            // Draw isometric ground plane (site boundary)
            ctx.beginPath();
            ctx.moveTo(isoX(boundary[0].x, boundary[0].y), isoY(boundary[0].x, boundary[0].y, 0));
            for (let i = 1; i < boundary.length; i++) {
                ctx.lineTo(isoX(boundary[i].x, boundary[i].y), isoY(boundary[i].x, boundary[i].y, 0));
            }
            ctx.closePath();
            ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
            ctx.fill();
            ctx.strokeStyle = '#22c55e';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Draw 3D isometric box helper with edge highlighting
            const drawIsoBox = (bx, by, bz, bw, bd, bh, topColor, sideColor) => {
                const corners = {
                    ftl: [bx, by, bz + bh],
                    ftr: [bx + bw, by, bz + bh],
                    fbl: [bx, by, bz],
                    fbr: [bx + bw, by, bz],
                    btl: [bx, by + bd, bz + bh],
                    btr: [bx + bw, by + bd, bz + bh],
                    bbl: [bx, by + bd, bz],
                    bbr: [bx + bw, by + bd, bz],
                };

                // Top face
                ctx.beginPath();
                ctx.moveTo(isoX(...corners.ftl), isoY(...corners.ftl));
                ctx.lineTo(isoX(...corners.ftr), isoY(...corners.ftr));
                ctx.lineTo(isoX(...corners.btr), isoY(...corners.btr));
                ctx.lineTo(isoX(...corners.btl), isoY(...corners.btl));
                ctx.closePath();
                ctx.fillStyle = topColor;
                ctx.fill();
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // Right face
                ctx.beginPath();
                ctx.moveTo(isoX(...corners.ftr), isoY(...corners.ftr));
                ctx.lineTo(isoX(...corners.fbr), isoY(...corners.fbr));
                ctx.lineTo(isoX(...corners.bbr), isoY(...corners.bbr));
                ctx.lineTo(isoX(...corners.btr), isoY(...corners.btr));
                ctx.closePath();
                ctx.fillStyle = sideColor;
                ctx.fill();
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // Left face (front)
                ctx.beginPath();
                ctx.moveTo(isoX(...corners.btl), isoY(...corners.btl));
                ctx.lineTo(isoX(...corners.bbl), isoY(...corners.bbl));
                ctx.lineTo(isoX(...corners.bbr), isoY(...corners.bbr));
                ctx.lineTo(isoX(...corners.btr), isoY(...corners.btr));
                ctx.closePath();
                ctx.fillStyle = shadeColor(sideColor, -15);
                ctx.fill();
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
                ctx.lineWidth = 1.5;
                ctx.stroke();
            };

            // Draw buildable area outline using inset polygon (follows boundary shape)
            // Uses average setback for now - per-edge setbacks need debugging
            const avgSetbackIso = (setbacks.front + setbacks.side + setbacks.rear) / 3;
            const insetBoundaryIso = insetPolygon(boundary, avgSetbackIso);

            // Get buildable area bounds from the INSET BOUNDARY polygon
            // This properly handles irregular shapes with per-edge setbacks
            let setbackX, setbackY, buildableW, buildableD;
            if (insetBoundaryIso && insetBoundaryIso.length >= 3) {
                // Use bounding box of the inset polygon
                const insetMinX = Math.min(...insetBoundaryIso.map(p => p.x));
                const insetMaxX = Math.max(...insetBoundaryIso.map(p => p.x));
                const insetMinY = Math.min(...insetBoundaryIso.map(p => p.y));
                const insetMaxY = Math.max(...insetBoundaryIso.map(p => p.y));

                // Safety check: inset bounds must be INSIDE original bounds
                // If inset polygon is somehow larger, use constrained values
                setbackX = Math.max(insetMinX, minX);
                setbackY = Math.max(insetMinY, minY);
                const constrainedMaxX = Math.min(insetMaxX, maxX);
                const constrainedMaxY = Math.min(insetMaxY, maxY);
                buildableW = Math.max(0, constrainedMaxX - setbackX);
                buildableD = Math.max(0, constrainedMaxY - setbackY);
            } else {
                // Fallback to rectangular calculation
                setbackX = minX + setbacks.side;
                setbackY = minY + setbacks.front;
                buildableW = Math.max(0, siteW - setbacks.side * 2);
                buildableD = Math.max(0, siteD - setbacks.front - setbacks.rear);
            }

            if (insetBoundaryIso && insetBoundaryIso.length >= 3) {
                ctx.beginPath();
                ctx.moveTo(isoX(insetBoundaryIso[0].x, insetBoundaryIso[0].y), isoY(insetBoundaryIso[0].x, insetBoundaryIso[0].y, 0));
                for (let i = 1; i < insetBoundaryIso.length; i++) {
                    ctx.lineTo(isoX(insetBoundaryIso[i].x, insetBoundaryIso[i].y), isoY(insetBoundaryIso[i].x, insetBoundaryIso[i].y, 0));
                }
                ctx.closePath();
                ctx.setLineDash([5, 5]);
                ctx.strokeStyle = '#3b82f6';
                ctx.lineWidth = 1;
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Building type specific colors for 3D
            const typeColors3D = {
                multifamily: '#8b5cf6',      // Purple
                singlefamily: '#22c55e',      // Green
                industrial: '#eab308',        // Yellow
                hotel: '#ec4899',             // Pink
                retail: '#f97316',            // Orange
                datacenter: '#0ea5e9',        // Sky blue
                parking: '#9ca3af',           // Gray
            };

            // Draw massing based on type
            const massType = massingType;
            const buildColor = typeColors3D[buildingType] || '#8b5cf6';
            const parkingColor = '#fbbf24';
            const podiumColor = '#6b7280';

            if (massType === 'podium') {
                // Podium: Full base + smaller tower using massing config
                const podiumFloors = massingConfig.podiumFloors || 2;
                const residentialFloors = massingConfig.residentialFloors || 4;
                const podiumH = massingConfig.podiumHeight || (podiumFloors * floorH);
                const towerH = residentialFloors * floorH;
                const towerW = buildableW * 0.7;
                const towerD = buildableD * 0.7;
                const towerOffX = (buildableW - towerW) / 2;
                const towerOffY = (buildableD - towerD) / 2;

                // Draw podium
                drawIsoBox(setbackX, setbackY, 0, buildableW * coverage, buildableD, podiumH, podiumColor, shadeColor(podiumColor, -20));
                // Draw tower
                drawIsoBox(setbackX + towerOffX, setbackY + towerOffY, podiumH, towerW * coverage, towerD, towerH, buildColor, shadeColor(buildColor, -20));

            } else if (massType === 'wrap') {
                // Wrap: Parking core with residential wrapping using massing config
                const wrapFloors = massingConfig.floors || 5;
                const garageFloors = massingConfig.garageFloors || 4;
                const garageH = garageFloors * (massingConfig.garageHeight || 11);
                const wrapH = wrapFloors * floorH;
                const coreW = buildableW * 0.4;
                const coreD = buildableD * 0.5;
                const coreX = setbackX + (buildableW - coreW) / 2;
                const coreY = setbackY + (buildableD - coreD) / 2;
                const wrapThickness = buildableW * 0.2;

                // Draw parking core
                drawIsoBox(coreX, coreY, 0, coreW, coreD, garageH, podiumColor, shadeColor(podiumColor, -20));
                // Draw wrap - left
                drawIsoBox(setbackX, setbackY, 0, wrapThickness, buildableD, wrapH, buildColor, shadeColor(buildColor, -20));
                // Draw wrap - right
                drawIsoBox(setbackX + buildableW - wrapThickness, setbackY, 0, wrapThickness, buildableD, wrapH, buildColor, shadeColor(buildColor, -20));
                // Draw wrap - back
                drawIsoBox(setbackX + wrapThickness, setbackY + buildableD * 0.75, 0, buildableW - wrapThickness * 2, buildableD * 0.25, wrapH, buildColor, shadeColor(buildColor, -20));

            } else if (massType === 'tower') {
                // Tower: Large podium + tall narrow tower using massing config
                const towerFloors = massingConfig.towerFloors || 20;
                const podiumFloors = massingConfig.podiumFloors || 3;
                const podiumH = massingConfig.podiumHeight || (podiumFloors * 12);
                const towerH = towerFloors * floorH;
                const towerW = buildableW * 0.35;
                const towerD = buildableD * 0.35;
                const towerOffX = (buildableW - towerW) / 2;
                const towerOffY = (buildableD - towerD) / 2;

                // Draw podium
                drawIsoBox(setbackX, setbackY, 0, buildableW * 0.8, buildableD * 0.8, podiumH, podiumColor, shadeColor(podiumColor, -20));
                // Draw tower
                drawIsoBox(setbackX + towerOffX, setbackY + towerOffY, podiumH, towerW, towerD, towerH, buildColor, shadeColor(buildColor, -20));

            } else if (massType === 'townhomes') {
                // Townhomes: Multiple parallel rows using massing config
                const thFloors = massingConfig.floors || 3;
                const unitW = massingConfig.unitWidth || 24;
                const unitD = massingConfig.unitDepth || 50;
                const rowSpacing = 30;
                const rowH = thFloors * floorH;
                const rows = Math.floor(buildableD / (unitD + rowSpacing));
                const unitsPerRow = Math.floor(buildableW / unitW);

                for (let r = 0; r < Math.min(rows, 4); r++) {
                    const rowY = setbackY + r * (unitD + rowSpacing) + 10;
                    const rowWidth = Math.min(buildableW * 0.9, unitsPerRow * unitW);
                    drawIsoBox(setbackX + 10, rowY, 0, rowWidth, unitD * 0.8, rowH, buildColor, shadeColor(buildColor, -20));
                }

            } else if (massType === 'garden') {
                // Garden: Scattered buildings with surface parking using massing config
                const gardenFloors = massingConfig.floors || 3;
                const bldgH = gardenFloors * floorH;
                // Draw surface parking
                drawIsoBox(setbackX, setbackY, 0, buildableW, buildableD, 2, parkingColor, shadeColor(parkingColor, -20));

                // Draw 4 scattered buildings
                const bldgW = buildableW * 0.25;
                const bldgD = buildableD * 0.25;
                const gap = 15;

                drawIsoBox(setbackX + gap, setbackY + gap, 2, bldgW, bldgD, bldgH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + buildableW - bldgW - gap, setbackY + gap, 2, bldgW, bldgD, bldgH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + gap, setbackY + buildableD - bldgD - gap, 2, bldgW, bldgD, bldgH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + buildableW - bldgW - gap, setbackY + buildableD - bldgD - gap, 2, bldgW, bldgD, bldgH, buildColor, shadeColor(buildColor, -20));

            } else if (massType === 'gurban') {
                // Gurban: L-shaped building with surface parking using massing config
                const gurbanFloors = massingConfig.floors || 4;
                const bldgH = gurbanFloors * floorH;
                const armW = buildableW * 0.3;
                const armD = buildableD * 0.35;

                // Draw surface parking
                drawIsoBox(setbackX + armW, setbackY + armD, 0, buildableW - armW, buildableD - armD, 2, parkingColor, shadeColor(parkingColor, -20));

                // Draw L-shape vertical arm
                drawIsoBox(setbackX, setbackY, 2, armW, buildableD, bldgH, buildColor, shadeColor(buildColor, -20));
                // Draw L-shape horizontal arm
                drawIsoBox(setbackX + armW, setbackY, 2, buildableW - armW, armD, bldgH, buildColor, shadeColor(buildColor, -20));

                // ================================================================
                // SINGLE-FAMILY 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'singlefamily' && massType === 'subdivision') {
                // Subdivision: Grid of houses using massing config
                const sfFloors = massingConfig.floors || 2;
                const houseH = sfFloors * floorH;
                const lotW = 60;
                const lotD = 100;
                const cols = Math.floor(buildableW / lotW);
                const rows = Math.floor(buildableD / lotD);
                for (let r = 0; r < rows; r++) {
                    for (let c = 0; c < cols; c++) {
                        const lotX = setbackX + c * lotW + 15;
                        const lotY = setbackY + r * lotD + 25;
                        drawIsoBox(lotX, lotY, 0, lotW - 30, lotD * 0.4, houseH, buildColor, shadeColor(buildColor, -20));
                    }
                }
            } else if (buildingType === 'singlefamily' && massType === 'cluster') {
                // Cluster: Houses around central green using massing config
                const sfFloors = massingConfig.floors || 2;
                const houseH = sfFloors * floorH;
                const centerX = setbackX + buildableW / 2;
                const centerY = setbackY + buildableD / 2;
                const radius = Math.min(buildableW, buildableD) * 0.35;
                for (let i = 0; i < 8; i++) {
                    const angle = (i / 8) * Math.PI * 2;
                    const hx = centerX + Math.cos(angle) * radius - 15;
                    const hy = centerY + Math.sin(angle) * radius - 15;
                    drawIsoBox(hx, hy, 0, 30, 30, houseH, buildColor, shadeColor(buildColor, -20));
                }
            } else if (buildingType === 'singlefamily') {
                // Courtyard homes using massing config
                const sfFloors = massingConfig.floors || 2;
                const houseH = sfFloors * floorH;
                const houseW = 35;
                const houseD = 40;
                for (let i = 0; i < 3; i++) {
                    drawIsoBox(setbackX + 30 + i * (houseW + 15), setbackY + 25, 0, houseW, houseD, houseH, buildColor, shadeColor(buildColor, -20));
                    drawIsoBox(setbackX + 30 + i * (houseW + 15), setbackY + buildableD - houseD - 25, 0, houseW, houseD, houseH, buildColor, shadeColor(buildColor, -20));
                }

                // ================================================================
                // INDUSTRIAL 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'industrial' && massType === 'bigbox') {
                // Big Box warehouse using massing config
                const warehouseH = massingConfig.clearHeight || massingConfig.floorHeight || currentSubtype?.clearHeight || 36;
                drawIsoBox(setbackX + 10, setbackY + 10, 0, buildableW - 20, buildableD - 20, warehouseH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'industrial' && massType === 'multibuilding') {
                // Multiple warehouses using massing config
                const warehouseH = massingConfig.clearHeight || massingConfig.floorHeight || currentSubtype?.clearHeight || 32;
                const bldgW = (buildableW - 30) / 2;
                const bldgD = (buildableD - 30) / 2;
                drawIsoBox(setbackX + 10, setbackY + 10, 0, bldgW, bldgD, warehouseH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + bldgW + 20, setbackY + 10, 0, bldgW, bldgD, warehouseH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + 10, setbackY + bldgD + 20, 0, bldgW, bldgD, warehouseH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + bldgW + 20, setbackY + bldgD + 20, 0, bldgW, bldgD, warehouseH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'industrial') {
                // Cross-dock using massing config
                const warehouseH = massingConfig.clearHeight || massingConfig.floorHeight || currentSubtype?.clearHeight || 32;
                const dockH = massingConfig.dockHeight || warehouseH * 0.6;
                const dockWidth = buildableW * 0.15;
                drawIsoBox(setbackX + dockWidth, setbackY + 10, 0, buildableW - dockWidth * 2, buildableD - 20, warehouseH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX, setbackY + 10, 0, dockWidth, buildableD - 20, dockH, podiumColor, shadeColor(podiumColor, -20));
                drawIsoBox(setbackX + buildableW - dockWidth, setbackY + 10, 0, dockWidth, buildableD - 20, dockH, podiumColor, shadeColor(podiumColor, -20));

                // ================================================================
                // HOTEL 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'hotel' && massType === 'courtyard') {
                // U-shape hotel using massing config
                const hotelFloors = massingConfig.floors || 5;
                const hotelH = hotelFloors * floorH;
                const armThick = buildableW * 0.25;
                drawIsoBox(setbackX, setbackY, 0, armThick, buildableD, hotelH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + buildableW - armThick, setbackY, 0, armThick, buildableD, hotelH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + armThick, setbackY, 0, buildableW - armThick * 2, buildableD * 0.3, hotelH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'hotel' && massType === 'tower') {
                // Tower hotel using massing config
                const towerFloors = massingConfig.towerFloors || 12;
                const podiumFloors = massingConfig.podiumFloors || 2;
                const podiumH = massingConfig.podiumHeight || (podiumFloors * 14);
                const towerH = towerFloors * floorH;
                const towerW = buildableW * 0.5;
                const towerD = buildableD * 0.5;
                drawIsoBox(setbackX, setbackY, 0, buildableW * 0.8, buildableD * 0.4, podiumH, podiumColor, shadeColor(podiumColor, -20));
                drawIsoBox(setbackX + (buildableW - towerW) / 2, setbackY + 10, podiumH, towerW, towerD, towerH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'hotel') {
                // Linear hotel using massing config
                const hotelFloors = massingConfig.floors || 6;
                const hotelH = hotelFloors * floorH;
                drawIsoBox(setbackX + 10, setbackY + buildableD * 0.3, 0, buildableW - 20, buildableD * 0.4, hotelH, buildColor, shadeColor(buildColor, -20));

                // ================================================================
                // RETAIL 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'retail' && massType === 'lshaped') {
                // L-shaped retail using massing config
                const retailH = massingConfig.floorHeight || 18;
                drawIsoBox(setbackX, setbackY, 0, buildableW, buildableD, 2, parkingColor, shadeColor(parkingColor, -20));
                drawIsoBox(setbackX, setbackY, 2, buildableW * 0.2, buildableD, retailH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX, setbackY + buildableD - buildableD * 0.25, 2, buildableW, buildableD * 0.25, retailH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'retail' && massType === 'ushaped') {
                // U-shaped retail using massing config
                const retailH = massingConfig.floorHeight || 20;
                const anchorH = massingConfig.anchorHeight || 28;
                drawIsoBox(setbackX, setbackY, 0, buildableW, buildableD, 2, parkingColor, shadeColor(parkingColor, -20));
                drawIsoBox(setbackX, setbackY, 2, buildableW * 0.2, buildableD, retailH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + buildableW * 0.8, setbackY, 2, buildableW * 0.2, buildableD, retailH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + buildableW * 0.2, setbackY, 2, buildableW * 0.6, buildableD * 0.35, anchorH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'retail') {
                // Inline retail using massing config
                const retailH = massingConfig.floorHeight || 16;
                drawIsoBox(setbackX, setbackY, 0, buildableW, buildableD, 2, parkingColor, shadeColor(parkingColor, -20));
                drawIsoBox(setbackX + 10, setbackY + buildableD * 0.7, 2, buildableW - 20, buildableD * 0.25, retailH, buildColor, shadeColor(buildColor, -20));

                // ================================================================
                // DATACENTER 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'datacenter' && massType === 'campus') {
                // Multi-building data center campus using massing config
                const dcFloors = massingConfig.floors || 2;
                const dcH = dcFloors * (massingConfig.floorHeight || 16);
                const bldgW = (buildableW - 40) / 2;
                const bldgD = (buildableD - 40) / 2;
                drawIsoBox(setbackX + 10, setbackY + 10, 0, bldgW, bldgD, dcH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + bldgW + 30, setbackY + 10, 0, bldgW, bldgD, dcH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + 10, setbackY + bldgD + 30, 0, bldgW, bldgD, dcH, buildColor, shadeColor(buildColor, -20));
                drawIsoBox(setbackX + bldgW + 30, setbackY + bldgD + 30, 0, bldgW, bldgD, dcH, buildColor, shadeColor(buildColor, -20));
            } else if (buildingType === 'datacenter') {
                // Single data hall using massing config
                const dcFloors = massingConfig.floors || 2;
                const dcH = dcFloors * (massingConfig.floorHeight || 18);
                drawIsoBox(setbackX + 15, setbackY + 15, 0, buildableW - 30, buildableD - 30, dcH, buildColor, shadeColor(buildColor, -20));

                // ================================================================
                // PARKING 3D MASSINGS
                // ================================================================
            } else if (buildingType === 'parking' && massType === 'surface') {
                // ================================================================
                // SURFACE PARKING 3D - Simple flat representation
                // ================================================================

                const effStallWidth = massingConfig.stallWidth || 9;
                const effStallDepth = massingConfig.stallDepth || 18;
                const aisleWidth = massingConfig.aisleWidth || 24;
                const loopWidth = aisleWidth;
                const loopInset = 2;

                // Colors - YELLOW for standard (most stalls)
                const asphaltColor = '#374151';
                const loopColor = '#4b5563';
                const yellowStall = '#fbbf24';  // Standard - MOST stalls
                const purpleStall = '#a855f7';  // Compact
                const blueStall = '#3b82f6';    // ADA
                const greenStall = '#22c55e';   // EV (only a few)

                // Draw flat asphalt base
                drawIsoBox(setbackX, setbackY, 0, buildableW, buildableD, 0.5, asphaltColor, shadeColor(asphaltColor, -10));

                // Loop boundaries
                const loopOuterX = setbackX + loopInset;
                const loopOuterY = setbackY + loopInset;
                const loopOuterW = buildableW - loopInset * 2;
                const loopOuterH = buildableD - loopInset * 2;

                const loopInnerX = loopOuterX + loopWidth;
                const loopInnerY = loopOuterY + loopWidth;
                const loopInnerW = Math.max(0, loopOuterW - loopWidth * 2);
                const loopInnerH = Math.max(0, loopOuterH - loopWidth * 2);

                // Draw perimeter loop (only if no custom aisles)
                if (drawnAisles.length === 0) {
                    drawIsoBox(loopOuterX, loopOuterY, 0.5, loopOuterW, loopWidth, 0.15, loopColor, shadeColor(loopColor, -10));
                    drawIsoBox(loopOuterX, loopOuterY + loopOuterH - loopWidth, 0.5, loopOuterW, loopWidth, 0.15, loopColor, shadeColor(loopColor, -10));
                    drawIsoBox(loopOuterX, loopOuterY + loopWidth, 0.5, loopWidth, loopOuterH - loopWidth * 2, 0.15, loopColor, shadeColor(loopColor, -10));
                    drawIsoBox(loopOuterX + loopOuterW - loopWidth, loopOuterY + loopWidth, 0.5, loopWidth, loopOuterH - loopWidth * 2, 0.15, loopColor, shadeColor(loopColor, -10));
                }

                // Interior parking
                const interiorX = loopInnerX;
                const interiorY = loopInnerY;
                const interiorW = loopInnerW;
                const interiorH = loopInnerH;

                const moduleDepth = effStallDepth * 2 + aisleWidth;
                const stallsPerRow = Math.floor(interiorW / effStallWidth);
                const numModules = Math.floor(interiorH / moduleDepth);

                // Stall mix: 85% standard, 10% compact, 3% ADA, 2% EV
                const totalStalls = Math.max(1, stallsPerRow * 2 * numModules);
                const adaCount = Math.max(2, Math.ceil(totalStalls * 0.03));
                const evCount = Math.max(2, Math.ceil(totalStalls * 0.02));

                // Helper to determine stall color based on index
                // SIMPLIFIED: First few ADA, last few EV, rest YELLOW
                const getStallColor = (index, total) => {
                    if (index < 2) return blueStall;         // First 2 = ADA (blue)
                    if (index >= total - 2) return greenStall; // Last 2 = EV (green)
                    if (index === 5 || index === 15 || index === 25) return purpleStall; // A few compact
                    return yellowStall;                       // Everything else = YELLOW
                };

                let stallCounter = 0;

                if (stallsPerRow > 0 && numModules > 0) {
                    for (let m = 0; m < numModules; m++) {
                        const moduleY = interiorY + m * moduleDepth;

                        // Top row
                        for (let s = 0; s < stallsPerRow; s++) {
                            const stallX = interiorX + s * effStallWidth;
                            const color = getStallColor(stallCounter, totalStalls);
                            stallCounter++;
                            drawIsoBox(stallX + 0.2, moduleY + 0.2, 0.5, effStallWidth - 0.4, effStallDepth - 0.4, 0.12, color, shadeColor(color, -15));
                        }

                        // Center aisle
                        drawIsoBox(interiorX, moduleY + effStallDepth, 0.5, interiorW, aisleWidth, 0.1, loopColor, shadeColor(loopColor, -10));

                        // Bottom row
                        const bottomRowY = moduleY + effStallDepth + aisleWidth;
                        for (let s = 0; s < stallsPerRow; s++) {
                            const stallX = interiorX + s * effStallWidth;
                            const color = getStallColor(stallCounter, totalStalls);
                            stallCounter++;
                            drawIsoBox(stallX + 0.2, bottomRowY + 0.2, 0.5, effStallWidth - 0.4, effStallDepth - 0.4, 0.12, color, shadeColor(color, -15));
                        }
                    }
                }

                // Entry/Exit - small lanes at bottom center
                const laneW = 12;
                const laneD = 20;
                const divW = 2;
                const eeBaseX = setbackX + buildableW / 2 - laneW - divW / 2;
                const eeBaseY = setbackY + buildableD;

                // Entry (green), Divider (yellow), Exit (red)
                drawIsoBox(eeBaseX, eeBaseY, 0.5, laneW, laneD, 0.15, '#22c55e', shadeColor('#22c55e', -15));
                drawIsoBox(eeBaseX + laneW, eeBaseY, 0.5, divW, laneD, 0.4, '#fbbf24', shadeColor('#fbbf24', -15));
                drawIsoBox(eeBaseX + laneW + divW, eeBaseY, 0.5, laneW, laneD, 0.15, '#ef4444', shadeColor('#ef4444', -15));

            } else if (buildingType === 'parking') {
                // Structured parking using massing config
                const parkingFloors = massingConfig.floors || 5;
                const parkingFloorH = massingConfig.floorHeight || 11;
                const parkingH = parkingFloors * parkingFloorH;
                drawIsoBox(setbackX + 10, setbackY + 10, 0, buildableW - 20, buildableD - 20, parkingH, podiumColor, shadeColor(podiumColor, -20));

            } else {
                // Default: Simple rectangular building
                const bldgW = buildableW * Math.sqrt(coverage);
                const bldgD = buildableD * Math.sqrt(coverage);
                const offX = (buildableW - bldgW) / 2;
                const offY = (buildableD - bldgD) / 2;

                drawIsoBox(setbackX + offX, setbackY + offY, 0, bldgW, bldgD, totalHeight, buildColor, shadeColor(buildColor, -20));
            }

            // Draw floor count label with massing-aware details
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 14px sans-serif';
            ctx.textAlign = 'center';

            // Generate floor label based on massing type
            let floorLabel = `${floors}F`;
            let heightLabel = `${totalHeight}ft`;

            if (massingConfig.towerFloors && massingConfig.podiumFloors) {
                floorLabel = `${massingConfig.towerFloors}F + ${massingConfig.podiumFloors}F`;
                const towerH = massingConfig.towerFloors * floorH;
                const podiumH = massingConfig.podiumHeight || massingConfig.podiumFloors * 12;
                heightLabel = `${towerH + podiumH}ft`;
            } else if (massingConfig.residentialFloors && massingConfig.podiumFloors) {
                floorLabel = `${massingConfig.residentialFloors}F + ${massingConfig.podiumFloors}F`;
                const resH = massingConfig.residentialFloors * floorH;
                const podiumH = massingConfig.podiumHeight || 15;
                heightLabel = `${resH + podiumH}ft`;
            } else if (massingConfig.clearHeight) {
                floorLabel = `CLR`;
                heightLabel = `${massingConfig.clearHeight}ft`;
            } else if (buildingType === 'parking' && massType === 'surface') {
                floorLabel = `—`;
                heightLabel = `Surface`;
            }

            ctx.fillText(floorLabel, w - 50, 30);
            ctx.font = '11px sans-serif';
            ctx.fillStyle = '#9ca3af';
            ctx.fillText(heightLabel, w - 50, 46);

        } else if (viewMode === '3d' && (boundary.length < 3 || isDrawing)) {
            // 3D mode but still drawing - show 2D for drawing
            if (boundary.length > 0) {
                ctx.beginPath();
                ctx.moveTo(boundary[0].x * SCALE, boundary[0].y * SCALE);
                for (let i = 1; i < boundary.length; i++) {
                    ctx.lineTo(boundary[i].x * SCALE, boundary[i].y * SCALE);
                }
                if (!isDrawing) ctx.closePath();
                ctx.fillStyle = 'rgba(100, 200, 100, 0.2)';
                ctx.fill();
                ctx.strokeStyle = '#4ade80';
                ctx.lineWidth = 2;
                ctx.stroke();

                boundary.forEach((pt, i) => {
                    ctx.beginPath();
                    ctx.arc(pt.x * SCALE, pt.y * SCALE, 5, 0, Math.PI * 2);
                    ctx.fillStyle = i === 0 ? '#22c55e' : '#4ade80';
                    ctx.fill();
                });
            }

            // Show hint
            ctx.fillStyle = '#6b7280';
            ctx.font = '14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Draw a site boundary to see 3D massing', w / 2, h - 20);
        }

    }, [boundary, isDrawing, exclusions, currentExclusion, results, activeConfig, SCALE, viewMode, buildingType, massingType, currentSubtype, currentMassing, effectiveMassingConfig, massingParams, lotCoverage, heightLimit, setbacks, isEditingBoundary, hoveredBoundaryVertex, hoveredBoundaryEdge, insetPolygon, insetPolygonWithSetbacks, gridSize, snapToGrid, templateBuildingPositions, selectedTemplateBuilding, paramChangeCounter, canvasZoom, canvasPan, canvasSize, pointInPolygon, rectInPolygon, rectOverlapsExclusions, drawnAisles, currentAislePoints, isDrawingAisle, aisleHoverPoint, isEditingAisles, hoveredAislePoint, draggingAislePoint]);

    // Helper to find which vertex or edge is near a point
    const findNearbyBoundaryElement = useCallback((x, y) => {
        const VERTEX_RADIUS = 8; // pixels
        const EDGE_DISTANCE = 6; // pixels

        // Check vertices first
        for (let i = 0; i < boundary.length; i++) {
            const pt = boundary[i];
            const screenX = pt.x * SCALE;
            const screenY = pt.y * SCALE;
            const dist = Math.sqrt((x - screenX) ** 2 + (y - screenY) ** 2);
            if (dist < VERTEX_RADIUS) {
                return { type: 'vertex', index: i };
            }
        }

        // Check edges (for adding new points)
        for (let i = 0; i < boundary.length; i++) {
            const p1 = boundary[i];
            const p2 = boundary[(i + 1) % boundary.length];
            // Point to line segment distance
            const x1 = p1.x * SCALE, y1 = p1.y * SCALE;
            const x2 = p2.x * SCALE, y2 = p2.y * SCALE;
            const A = x - x1, B = y - y1, C = x2 - x1, D = y2 - y1;
            const dot = A * C + B * D;
            const lenSq = C * C + D * D;
            let param = lenSq !== 0 ? dot / lenSq : -1;

            if (param >= 0.1 && param <= 0.9) { // Not too close to vertices
                const xx = x1 + param * C;
                const yy = y1 + param * D;
                const dist = Math.sqrt((x - xx) ** 2 + (y - yy) ** 2);
                if (dist < EDGE_DISTANCE) {
                    return { type: 'edge', index: i, x: xx / SCALE, y: yy / SCALE };
                }
            }
        }

        return null;
    }, [boundary, SCALE]);

    // Helper to find template building at a point (for 2D click detection)
    const findTemplateBuildingAt = useCallback((mouseX, mouseY) => {
        const x = mouseX / SCALE;
        const y = mouseY / SCALE;
        const buildings = templateBuildings2DRef.current || [];
        // Check in reverse order (top buildings first)
        for (let i = buildings.length - 1; i >= 0; i--) {
            const bldg = buildings[i];
            if (x >= bldg.x && x <= bldg.x + bldg.w &&
                y >= bldg.y && y <= bldg.y + bldg.h) {
                return bldg.index;
            }
        }
        return null;
    }, [SCALE]);

    // Helper to find amenity at a point (for 2D click detection)
    const findAmenityAt = useCallback((mouseX, mouseY) => {
        const x = mouseX / SCALE;
        const y = mouseY / SCALE;
        const amenities = amenities2DRef.current || [];
        // Check in reverse order (top amenities first)
        for (let i = amenities.length - 1; i >= 0; i--) {
            const a = amenities[i];
            if (x >= a.x && x <= a.x + a.w &&
                y >= a.y && y <= a.y + a.h) {
                return a;
            }
        }
        return null;
    }, [SCALE]);

    // Helper to find vehicle at a point (for swept path analysis click detection)
    const findVehicleAt = useCallback((x, y) => {
        const vehicleHitBoxes = vehicles2DRef.current || [];
        // Check in reverse order (top vehicles first)
        for (let i = vehicleHitBoxes.length - 1; i >= 0; i--) {
            const v = vehicleHitBoxes[i];
            // Simple rectangular hit test (could be improved with rotation-aware detection)
            const halfW = v.width / 2;
            const halfH = v.height / 2;
            const dx = x - v.x;
            const dy = y - v.y;
            // Rotate point back to vehicle's local space
            const rotRad = (-v.rotation * Math.PI) / 180;
            const localX = dx * Math.cos(rotRad) - dy * Math.sin(rotRad);
            const localY = dx * Math.sin(rotRad) + dy * Math.cos(rotRad);

            if (Math.abs(localX) <= halfW && Math.abs(localY) <= halfH) {
                // Return the full vehicle data
                const vehicleData = vehicles.find(veh => veh.id === v.id);
                return vehicleData || null;
            }
        }
        return null;
    }, [vehicles]);

    // Handle moving amenity (pool, garden, courtyard)
    const handleMoveAmenity = useCallback((amenityId, x, y) => {
        setAmenityPositions(prev => ({
            ...prev,
            [amenityId]: { x, z: y } // Store center position (z for 3D compatibility)
        }));
    }, []);

    // Convert screen coordinates to canvas coordinates (accounting for zoom and pan)
    const screenToCanvas = useCallback((screenX, screenY) => {
        return {
            x: (screenX - canvasPan.x) / canvasZoom,
            y: (screenY - canvasPan.y) / canvasZoom
        };
    }, [canvasZoom, canvasPan]);

    // Canvas mouse handlers for boundary editing and template building selection
    const handleCanvasMouseDown = useCallback((e) => {
        const canvas = canvasRef.current;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // === AISLE EDITING MODE - Start dragging point ===
        if (isEditingAisles && drawnAisles.length > 0 && e.button === 0 && !isDrawingAisle) {
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const clickX = canvasCoords.x / SCALE;
            const clickY = canvasCoords.y / SCALE;

            // Build junctions from current aisles
            const junctions = buildAisleJunctions(drawnAisles, 15);

            // Hit radius in feet - use a minimum of 8ft for easy clicking
            const hitRadiusFeet = Math.max(8, 20 / (SCALE * canvasZoom));

            // Find if we're clicking on a point or junction
            const hitPoint = findAislePointAtPosition(clickX, clickY, drawnAisles, junctions, hitRadiusFeet);

            if (hitPoint) {
                // Save current state to undo history before starting drag
                setAisleEditHistory(prev => [...prev, JSON.parse(JSON.stringify(drawnAisles))]);

                // Store junction connections and original position for reliable dragging
                if (hitPoint.type === 'junction') {
                    const junction = junctions.find(j => j.id === hitPoint.junctionId);
                    if (junction) {
                        hitPoint.connections = [...junction.connections];
                        hitPoint.originalX = junction.x;
                        hitPoint.originalY = junction.y;
                    }
                }

                setDraggingAislePoint(hitPoint);
                e.preventDefault();
                return;
            }
        }

        // Middle mouse button, shift+left click, OR pan mode left click = start panning
        if (e.button === 1 || (e.button === 0 && e.shiftKey) || (e.button === 0 && editMode === 'pan')) {
            setIsPanning(true);
            panStartRef.current = { x: e.clientX, y: e.clientY };
            panInitialRef.current = { x: canvasPan.x, y: canvasPan.y };
            e.preventDefault();
            return;
        }

        // Convert screen to canvas coordinates for zoom-aware operations
        const canvasCoords = screenToCanvas(mouseX, mouseY);
        const canvasX = canvasCoords.x;
        const canvasY = canvasCoords.y;

        // Check for template building click in 2D mode
        if (viewMode === '2d' && !isDrawing && !isEditingBoundary) {
            const templateIdx = findTemplateBuildingAt(canvasX * canvasZoom, canvasY * canvasZoom);
            if (templateIdx !== null) {
                handleSelectTemplateBuilding(templateIdx);
                setSelectedAmenity(null); // Deselect any amenity
                setSelectedVehicle(null); // Deselect any vehicle
                setDraggingTemplateBuilding2D(templateIdx);

                // Calculate offset from building center to mouse
                const buildings = templateBuildings2DRef.current || [];
                const building = buildings.find(b => b.index === templateIdx);
                if (building) {
                    const centerX = building.x + building.w / 2;
                    const centerY = building.y + building.h / 2;
                    const clickX = canvasX / SCALE;
                    const clickY = canvasY / SCALE;
                    setDragOffset2D({ x: clickX - centerX, y: clickY - centerY });
                }

                e.preventDefault();
                return;
            }

            // Check for amenity click
            const amenity = findAmenityAt(canvasX * canvasZoom, canvasY * canvasZoom);
            if (amenity) {
                setSelectedAmenity(amenity.id);
                setSelectedTemplateBuilding(null); // Deselect any building
                setSelectedVehicle(null); // Deselect any vehicle
                setDraggingAmenity(amenity.id);

                // Calculate offset from amenity center to mouse
                const centerX = amenity.x + amenity.w / 2;
                const centerY = amenity.y + amenity.h / 2;
                const clickX = canvasX / SCALE;
                const clickY = canvasY / SCALE;
                setAmenityDragOffset({ x: clickX - centerX, y: clickY - centerY });

                e.preventDefault();
                return;
            }

            // Check for vehicle click (swept path analysis)
            const clickedVehicle = findVehicleAt(canvasX / SCALE, canvasY / SCALE);
            if (clickedVehicle) {
                setSelectedVehicle(clickedVehicle.id);
                setSelectedTemplateBuilding(null);
                setSelectedAmenity(null);
                setDraggingVehicle(clickedVehicle.id);

                // Calculate offset from vehicle center to mouse
                const clickX = canvasX / SCALE;
                const clickY = canvasY / SCALE;
                setVehicleDragOffset({ x: clickX - clickedVehicle.x, y: clickY - clickedVehicle.y });

                e.preventDefault();
                return;
            }
        }

        if (!isEditingBoundary || isDrawing) return;

        // canvasX, canvasY are in unzoomed canvas space (from screenToCanvas)
        // findNearbyBoundaryElement expects coords in SCALE space (same as drawing)
        const element = findNearbyBoundaryElement(canvasX, canvasY);

        if (element?.type === 'vertex') {
            // Right-click to delete vertex
            if (e.button === 2) {
                e.preventDefault();
                handleDeleteBoundaryVertex(element.index);
            } else {
                // Left-click to start dragging - store starting position for ortho mode
                const pt = boundary[element.index];
                vertexDragStart2DRef.current = { x: pt.x, y: pt.y };
                setDraggingBoundaryVertex(element.index);
            }
        } else if (element?.type === 'edge' && e.button === 0) {
            // Left-click on edge to start dragging the edge (move both vertices)
            const p1 = boundary[element.index];
            const p2 = boundary[(element.index + 1) % boundary.length];
            setDraggingBoundaryEdge(element.index);
            setEdgeDragStart({
                mouseX: canvasX / SCALE,  // Store in site units (same as boundary coordinates)
                mouseY: canvasY / SCALE,
                vertices: [{ x: p1.x, y: p1.y }, { x: p2.x, y: p2.y }]
            });
        } else if (element?.type === 'edge' && e.button === 2) {
            // Right-click on edge to add vertex
            e.preventDefault();
            handleAddBoundaryVertex(element.index, Math.round(element.x), Math.round(element.y));
        }
    }, [isEditingBoundary, isDrawing, findNearbyBoundaryElement, handleDeleteBoundaryVertex, handleAddBoundaryVertex, viewMode, findTemplateBuildingAt, handleSelectTemplateBuilding, findAmenityAt, findVehicleAt, canvasPan, canvasZoom, screenToCanvas, boundary, SCALE, editMode, isEditingAisles, drawnAisles, isDrawingAisle]);

    const handleCanvasMouseMove = useCallback((e) => {
        const canvas = canvasRef.current;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // === ADA PLACEMENT MODE HOVER ===
        if (isPlacingAda && parkingLayoutRef.current) {
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const hoverX = canvasCoords.x / SCALE;
            const hoverY = canvasCoords.y / SCALE;

            const layout = parkingLayoutRef.current;

            // Find which row is being hovered (check all rows)
            let hoveredRow = null;
            for (const row of layout.rows) {
                if (hoverY >= row.y && hoverY <= row.y + row.height) {
                    hoveredRow = row;
                    break;
                }
            }

            if (hoveredRow) {
                const relativeX = hoverX - layout.sectionX;
                const stallIndex = Math.floor(relativeX / layout.stallWidth);
                const maxStartIndex = layout.stallsPerRow - layout.adaClusterSize;

                if (stallIndex >= 0 && stallIndex <= maxStartIndex) {
                    setAdaHoverIndex(stallIndex);
                    setAdaHoverRow(hoveredRow.rowIndex);
                    canvas.style.cursor = 'pointer';
                } else {
                    setAdaHoverIndex(null);
                    setAdaHoverRow(null);
                    canvas.style.cursor = 'not-allowed';
                }
            } else {
                setAdaHoverIndex(null);
                setAdaHoverRow(null);
                canvas.style.cursor = 'crosshair';
            }
            return;
        }

        // === AISLE EDITING MODE HOVER ===
        if (isEditingAisles && drawnAisles.length > 0 && !isDrawingAisle) {
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const hoverX = canvasCoords.x / SCALE;
            const hoverY = canvasCoords.y / SCALE;

            // Build junctions from current aisles
            const junctions = buildAisleJunctions(drawnAisles, 15);

            // Hit radius in feet - use a minimum of 8ft for easy clicking
            const hitRadiusFeet = Math.max(8, 20 / (SCALE * canvasZoom));

            // Find if we're hovering over a point or junction
            const hitPoint = findAislePointAtPosition(hoverX, hoverY, drawnAisles, junctions, hitRadiusFeet);

            if (hitPoint) {
                setHoveredAislePoint(hitPoint);
                canvas.style.cursor = 'grab';
            } else {
                setHoveredAislePoint(null);
                canvas.style.cursor = draggingAislePoint ? 'grabbing' : 'default';
            }

            // If dragging, update the point position
            if (draggingAislePoint) {
                // Apply grid snapping
                const snapped = snapToGridPoint(hoverX, hoverY);
                let newX = snapped.x;
                let newY = snapped.y;

                // Apply perimeter snapping
                const layout = parkingLayoutRef.current;
                const snapDistance = 20;
                if (layout && layout.loopOuter) {
                    const loop = layout.loopOuter;
                    const loopW = layout.loopWidth || 24;
                    const topEdgeY = loop.y + loopW / 2;
                    const bottomEdgeY = loop.y + loop.h - loopW / 2;
                    const leftEdgeX = loop.x + loopW / 2;
                    const rightEdgeX = loop.x + loop.w - loopW / 2;

                    if (Math.abs(newY - topEdgeY) < snapDistance && newX >= loop.x && newX <= loop.x + loop.w) {
                        newY = topEdgeY;
                    } else if (Math.abs(newY - bottomEdgeY) < snapDistance && newX >= loop.x && newX <= loop.x + loop.w) {
                        newY = bottomEdgeY;
                    }
                    if (Math.abs(newX - leftEdgeX) < snapDistance && newY >= loop.y && newY <= loop.y + loop.h) {
                        newX = leftEdgeX;
                    } else if (Math.abs(newX - rightEdgeX) < snapDistance && newY >= loop.y && newY <= loop.y + loop.h) {
                        newX = rightEdgeX;
                    }
                }

                // Validate newX and newY before applying
                if (!isFinite(newX) || !isFinite(newY) || isNaN(newX) || isNaN(newY)) {
                    console.warn('Invalid drag coordinates, skipping update:', { newX, newY });
                    return;
                }

                if (draggingAislePoint.type === 'junction') {
                    // Move all connected points together using stored connections
                    // The connections were captured at drag start and don't change
                    if (draggingAislePoint.connections && draggingAislePoint.connections.length > 0) {
                        setDrawnAisles(prev => {
                            const updated = prev.map(aisle => {
                                // Check if this aisle has any points in the junction
                                const connectedPoints = draggingAislePoint.connections
                                    .filter(conn => conn.aisleId === aisle.id)
                                    .map(conn => conn.pointIndex);

                                if (connectedPoints.length === 0) return aisle;

                                // Update the connected points
                                return {
                                    ...aisle,
                                    points: aisle.points.map((p, idx) =>
                                        connectedPoints.includes(idx) ? { x: newX, y: newY } : p
                                    )
                                };
                            });
                            return updated;
                        });
                    }
                } else {
                    // Move single point
                    setDrawnAisles(prev => prev.map(aisle =>
                        aisle.id === draggingAislePoint.aisleId
                            ? {
                                ...aisle,
                                points: aisle.points.map((p, idx) =>
                                    idx === draggingAislePoint.pointIndex ? { x: newX, y: newY } : p
                                )
                            }
                            : aisle
                    ));
                }
                canvas.style.cursor = 'grabbing';
            }
            return;
        }

        // === SPINE PLACEMENT MODE HOVER ===
        if (isPlacingSpine && parkingLayoutRef.current) {
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const hoverX = canvasCoords.x / SCALE;

            const layout = parkingLayoutRef.current;

            // Validate hover is within parking area
            const minX = layout.sectionX;
            const maxX = layout.sectionX + layout.stallsPerRow * layout.stallWidth;

            if (hoverX >= minX && hoverX <= maxX) {
                setSpineHoverX(hoverX);
                canvas.style.cursor = 'crosshair';
            } else {
                setSpineHoverX(null);
                canvas.style.cursor = 'not-allowed';
            }
            return;
        }

        // === DRAW AISLE MODE HOVER ===
        if (isDrawingAisle) {
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            let hoverX = canvasCoords.x / SCALE;
            let hoverY = canvasCoords.y / SCALE;

            // Apply grid snapping for preview
            const snapped = snapToGridPoint(hoverX, hoverY);
            hoverX = snapped.x;
            hoverY = snapped.y;

            // === SNAP TO EXISTING AISLE POINTS (for creating junctions) ===
            const aisleSnapDistance = 15;
            let snappedToAisle = false;

            if (drawnAisles.length > 0) {
                let closestDist = aisleSnapDistance;
                let closestPoint = null;

                drawnAisles.forEach(aisle => {
                    aisle.points.forEach(pt => {
                        const dist = Math.sqrt((hoverX - pt.x) ** 2 + (hoverY - pt.y) ** 2);
                        if (dist < closestDist) {
                            closestDist = dist;
                            closestPoint = pt;
                        }
                    });
                });

                // Also check current aisle points
                if (currentAislePoints.length > 0) {
                    currentAislePoints.forEach(pt => {
                        const dist = Math.sqrt((hoverX - pt.x) ** 2 + (hoverY - pt.y) ** 2);
                        if (dist < closestDist) {
                            closestDist = dist;
                            closestPoint = pt;
                        }
                    });
                }

                if (closestPoint) {
                    hoverX = closestPoint.x;
                    hoverY = closestPoint.y;
                    snappedToAisle = true;
                }
            }

            // === SNAP TO PERIMETER LOOP EDGES (same as click handler) ===
            const layout = parkingLayoutRef.current;
            const snapDistance = 20;

            if (layout && layout.loopOuter && !snappedToAisle) {
                const loop = layout.loopOuter;
                const loopW = layout.loopWidth || 24;

                const topEdgeY = loop.y + loopW / 2;
                const bottomEdgeY = loop.y + loop.h - loopW / 2;
                const leftEdgeX = loop.x + loopW / 2;
                const rightEdgeX = loop.x + loop.w - loopW / 2;

                // Snap to edges
                if (Math.abs(hoverY - topEdgeY) < snapDistance && hoverX >= loop.x && hoverX <= loop.x + loop.w) {
                    hoverY = topEdgeY;
                } else if (Math.abs(hoverY - bottomEdgeY) < snapDistance && hoverX >= loop.x && hoverX <= loop.x + loop.w) {
                    hoverY = bottomEdgeY;
                }
                if (Math.abs(hoverX - leftEdgeX) < snapDistance && hoverY >= loop.y && hoverY <= loop.y + loop.h) {
                    hoverX = leftEdgeX;
                } else if (Math.abs(hoverX - rightEdgeX) < snapDistance && hoverY >= loop.y && hoverY <= loop.y + loop.h) {
                    hoverX = rightEdgeX;
                }
            }

            // === ORTHO MODE for hover preview ===
            if (currentAislePoints.length > 0 && !snappedToAisle) {
                const lastPoint = currentAislePoints[currentAislePoints.length - 1];
                const dx = Math.abs(hoverX - lastPoint.x);
                const dy = Math.abs(hoverY - lastPoint.y);

                if (dx > dy) {
                    hoverY = lastPoint.y;
                } else {
                    hoverX = lastPoint.x;
                }
            }

            setAisleHoverPoint({ x: hoverX, y: hoverY, snapped: snappedToAisle });
            canvas.style.cursor = snappedToAisle ? 'pointer' : 'crosshair';
            return;
        }

        // Handle canvas panning
        if (isPanning) {
            const dx = e.clientX - panStartRef.current.x;
            const dy = e.clientY - panStartRef.current.y;
            setCanvasPan({
                x: panInitialRef.current.x + dx,
                y: panInitialRef.current.y + dy
            });
            canvas.style.cursor = 'grabbing';
            return;
        }

        // Convert screen coordinates to canvas coordinates (accounting for zoom/pan)
        const canvasCoords = screenToCanvas(mouseX, mouseY);
        const canvasMouseX = canvasCoords.x;
        const canvasMouseY = canvasCoords.y;

        // Handle template building dragging in 2D
        if (draggingTemplateBuilding2D !== null) {
            // Convert mouse to site coordinates and subtract offset
            let newX = Math.round(canvasMouseX / SCALE) - dragOffset2D.x;
            let newY = Math.round(canvasMouseY / SCALE) - dragOffset2D.y;

            // Apply grid snapping to the center position
            const snapped = snapToGridPoint(newX, newY);
            newX = Math.round(snapped.x);
            newY = Math.round(snapped.y);

            // Calculate boundary constraints
            if (boundary.length >= 3) {
                const minX = Math.min(...boundary.map(p => p.x));
                const maxX = Math.max(...boundary.map(p => p.x));
                const minY = Math.min(...boundary.map(p => p.y));
                const maxY = Math.max(...boundary.map(p => p.y));

                // Constrain to boundary with 20ft margin
                const margin = 20;
                newX = Math.max(minX + margin, Math.min(maxX - margin, newX));
                newY = Math.max(minY + margin, Math.min(maxY - margin, newY));
            }

            // Store as z for consistency with 3D (y becomes z in 3D coordinate system)
            handleMoveTemplateBuilding(draggingTemplateBuilding2D, newX, newY);
            canvas.style.cursor = 'move';
            return;
        }

        // Handle amenity dragging in 2D
        if (draggingAmenity !== null) {
            // Convert mouse to site coordinates and subtract offset
            let newX = Math.round(canvasMouseX / SCALE) - amenityDragOffset.x;
            let newY = Math.round(canvasMouseY / SCALE) - amenityDragOffset.y;

            // Apply grid snapping to the center position
            const snapped = snapToGridPoint(newX, newY);
            newX = Math.round(snapped.x);
            newY = Math.round(snapped.y);

            // Calculate boundary constraints
            if (boundary.length >= 3) {
                const minX = Math.min(...boundary.map(p => p.x));
                const maxX = Math.max(...boundary.map(p => p.x));
                const minY = Math.min(...boundary.map(p => p.y));
                const maxY = Math.max(...boundary.map(p => p.y));

                // Constrain to boundary with 10ft margin (smaller for amenities)
                const margin = 10;
                newX = Math.max(minX + margin, Math.min(maxX - margin, newX));
                newY = Math.max(minY + margin, Math.min(maxY - margin, newY));
            }

            handleMoveAmenity(draggingAmenity, newX, newY);
            canvas.style.cursor = 'move';
            return;
        }

        // Handle vehicle dragging in 2D (swept path analysis)
        if (draggingVehicle !== null) {
            // Convert mouse to site coordinates and subtract offset
            let newX = canvasMouseX / SCALE - vehicleDragOffset.x;
            let newY = canvasMouseY / SCALE - vehicleDragOffset.y;

            // Update vehicle position and add to trail
            setVehicles(prev => prev.map(v => {
                if (v.id === draggingVehicle) {
                    // Add current position to trail (limit trail length to prevent memory issues)
                    const newTrail = [...v.trail];
                    const lastPoint = newTrail[newTrail.length - 1];

                    // Calculate movement direction and auto-rotate vehicle to face that direction
                    const dx = newX - v.x;
                    const dy = newY - v.y;
                    const moveDistance = Math.hypot(dx, dy);

                    // Only update rotation if moved enough (> 1 ft) to avoid jitter
                    let newRotation = v.rotation;
                    if (moveDistance > 1) {
                        // Calculate angle from movement direction (atan2 gives radians, convert to degrees)
                        // 0° = facing right (east), 90° = facing down (south)
                        newRotation = Math.atan2(dy, dx) * (180 / Math.PI);
                    }

                    // Only add to trail if moved significantly (> 2 ft)
                    if (!lastPoint || Math.hypot(newX - lastPoint.x, newY - lastPoint.y) > 2) {
                        newTrail.push({ x: v.x, y: v.y, rotation: v.rotation });
                        // Limit trail to last 500 points
                        if (newTrail.length > 500) {
                            newTrail.shift();
                        }
                    }

                    return { ...v, x: newX, y: newY, rotation: newRotation, trail: newTrail };
                }
                return v;
            }));
            canvas.style.cursor = 'move';
            return;
        }

        // Check for hover over template buildings in 2D
        if (viewMode === '2d' && !isDrawing && !isEditingBoundary) {
            const templateIdx = findTemplateBuildingAt(mouseX, mouseY);
            const amenity = findAmenityAt(mouseX, mouseY);
            if (templateIdx !== null || amenity !== null) {
                canvas.style.cursor = 'move';
            } else {
                canvas.style.cursor = 'crosshair';
            }
        }

        if (isEditingBoundary && draggingBoundaryVertex !== null) {
            // Dragging a vertex - move directly to mouse position
            let newX = Math.round(canvasMouseX / SCALE);
            let newY = Math.round(canvasMouseY / SCALE);

            // Apply ortho mode (Shift key or orthoMode toggle) - constrain to major axis
            if ((orthoMode || e.shiftKey) && vertexDragStart2DRef.current) {
                const deltaX = Math.abs(newX - vertexDragStart2DRef.current.x);
                const deltaY = Math.abs(newY - vertexDragStart2DRef.current.y);
                if (deltaX > deltaY) {
                    // Constrain to X axis (horizontal)
                    newY = vertexDragStart2DRef.current.y;
                } else {
                    // Constrain to Y axis (vertical)
                    newX = vertexDragStart2DRef.current.x;
                }
            }

            // Apply grid snapping only (consistent with edge dragging)
            if (snapToGrid) {
                const snapped = snapToGridPoint(newX, newY);
                newX = Math.round(snapped.x);
                newY = Math.round(snapped.y);
            }

            // Update coordinate display overlay
            setCoordDisplay2D({
                x: newX,
                y: newY,
                screenX: mouseX + 15,
                screenY: mouseY - 30,
                ortho: orthoMode || e.shiftKey
            });

            handleUpdateBoundaryVertex(draggingBoundaryVertex, newX, newY);
        } else if (isEditingBoundary && draggingBoundaryEdge !== null && edgeDragStart) {
            // Dragging an edge - move both vertices by the same delta
            const currentMouseX = canvasMouseX / SCALE;
            const currentMouseY = canvasMouseY / SCALE;
            const deltaX = currentMouseX - edgeDragStart.mouseX;
            const deltaY = currentMouseY - edgeDragStart.mouseY;

            // Calculate new positions for both vertices
            let newX1 = Math.round(edgeDragStart.vertices[0].x + deltaX);
            let newY1 = Math.round(edgeDragStart.vertices[0].y + deltaY);
            let newX2 = Math.round(edgeDragStart.vertices[1].x + deltaX);
            let newY2 = Math.round(edgeDragStart.vertices[1].y + deltaY);

            // Apply grid snapping to the first vertex (the edge will snap as a unit)
            if (snapToGrid) {
                const snapped1 = snapToGridPoint(newX1, newY1);
                const snapDeltaX = snapped1.x - newX1;
                const snapDeltaY = snapped1.y - newY1;
                newX1 = Math.round(snapped1.x);
                newY1 = Math.round(snapped1.y);
                newX2 = Math.round(newX2 + snapDeltaX);
                newY2 = Math.round(newY2 + snapDeltaY);
            }

            // Update both vertices
            const idx1 = draggingBoundaryEdge;
            const idx2 = (draggingBoundaryEdge + 1) % boundary.length;
            handleUpdateBoundaryVertex(idx1, newX1, newY1);
            handleUpdateBoundaryVertex(idx2, newX2, newY2);
        } else if (isEditingBoundary && !isDrawing) {
            // Hover detection - use canvas coordinates (from screenToCanvas)
            const element = findNearbyBoundaryElement(canvasMouseX, canvasMouseY);
            if (element?.type === 'vertex') {
                setHoveredBoundaryVertex(element.index);
                setHoveredBoundaryEdge(null);
                canvas.style.cursor = 'move';
            } else if (element?.type === 'edge') {
                setHoveredBoundaryVertex(null);
                setHoveredBoundaryEdge(element.index);
                canvas.style.cursor = 'ew-resize'; // Edge drag cursor
            } else {
                setHoveredBoundaryVertex(null);
                setHoveredBoundaryEdge(null);
                canvas.style.cursor = 'default';
            }
        }
    }, [isEditingBoundary, isDrawing, draggingBoundaryVertex, draggingBoundaryEdge, edgeDragStart, SCALE, findNearbyBoundaryElement, handleUpdateBoundaryVertex, boundary, applySnapping, draggingTemplateBuilding2D, dragOffset2D, snapToGridPoint, handleMoveTemplateBuilding, viewMode, findTemplateBuildingAt, draggingAmenity, amenityDragOffset, handleMoveAmenity, findAmenityAt, draggingVehicle, vehicleDragOffset, isPanning, screenToCanvas, snapToGrid, isPlacingAda, isPlacingSpine, isEditingAisles, drawnAisles, draggingAislePoint, canvasZoom, isDrawingAisle]);

    const handleCanvasMouseUp = useCallback(() => {
        setDraggingBoundaryVertex(null);
        setDraggingBoundaryEdge(null);
        setEdgeDragStart(null);
        setDraggingTemplateBuilding2D(null);
        setDragOffset2D({ x: 0, y: 0 });
        setDraggingAmenity(null);
        setAmenityDragOffset({ x: 0, y: 0 });
        setDraggingVehicle(null);
        setVehicleDragOffset({ x: 0, y: 0 });
        setIsPanning(false);
        // Clear aisle point dragging
        setDraggingAislePoint(null);
        // Clear precision editing state
        vertexDragStart2DRef.current = null;
        setCoordDisplay2D(null);
    }, []);

    // Double-click to open precise vertex input dialog OR finish aisle drawing
    const handleCanvasDoubleClick = useCallback((e) => {
        // === FINISH AISLE DRAWING ON DOUBLE-CLICK ===
        if (isDrawingAisle && currentAislePoints.length >= 2) {
            // Save the current aisle
            setDrawnAisles(prev => [...prev, {
                points: [...currentAislePoints],
                id: Date.now()
            }]);
            setCurrentAislePoints([]);
            setIsDrawingAisle(false);
            setAisleHoverPoint(null);
            return;
        }

        if (!isEditingBoundary || isDrawing) return;

        const canvas = canvasRef.current;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const canvasCoords = screenToCanvas(mouseX, mouseY);

        const element = findNearbyBoundaryElement(canvasCoords.x, canvasCoords.y);
        if (element?.type === 'vertex') {
            const pt = boundary[element.index];
            setEditingVertex2D({
                index: element.index,
                x: pt.x,
                y: pt.y
            });
        }
    }, [isEditingBoundary, isDrawing, screenToCanvas, findNearbyBoundaryElement, boundary, isDrawingAisle, currentAislePoints]);

    // Canvas wheel handler for zoom
    const handleCanvasWheel = useCallback((e) => {
        e.preventDefault();
        const canvas = canvasRef.current;
        if (!canvas) return;

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Calculate zoom factor
        const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
        const newZoom = Math.max(0.25, Math.min(4, canvasZoom * zoomFactor));

        // Adjust pan to zoom toward mouse position
        const zoomRatio = newZoom / canvasZoom;
        const newPanX = mouseX - (mouseX - canvasPan.x) * zoomRatio;
        const newPanY = mouseY - (mouseY - canvasPan.y) * zoomRatio;

        setCanvasZoom(newZoom);
        setCanvasPan({ x: newPanX, y: newPanY });
    }, [canvasZoom, canvasPan]);

    // Reset zoom to fit
    const handleResetZoom = useCallback(() => {
        setCanvasZoom(1);
        setCanvasPan({ x: 0, y: 0 });
    }, []);

    // Add wheel event listener with passive: false to allow preventDefault
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        canvas.addEventListener('wheel', handleCanvasWheel, { passive: false });
        return () => canvas.removeEventListener('wheel', handleCanvasWheel);
    }, [handleCanvasWheel]);

    // Canvas click handler
    const handleCanvasClick = useCallback((e) => {
        // === DRAW AISLE MODE ===
        // If in draw aisle mode, add points to the current aisle path
        if (isDrawingAisle) {
            const canvas = canvasRef.current;
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            let clickX = canvasCoords.x / SCALE;
            let clickY = canvasCoords.y / SCALE;

            // Apply grid snapping first
            const snapped = snapToGridPoint(clickX, clickY);
            clickX = snapped.x;
            clickY = snapped.y;

            // === SNAP TO EXISTING AISLE POINTS (for creating junctions) ===
            // This allows new streets to connect to existing streets
            const aisleSnapDistance = 15; // Snap within 15ft of existing aisle points
            let snappedToAisle = false;

            if (drawnAisles.length > 0) {
                let closestDist = aisleSnapDistance;
                let closestPoint = null;

                // Check all points of all existing aisles
                drawnAisles.forEach(aisle => {
                    aisle.points.forEach(pt => {
                        const dist = Math.sqrt((clickX - pt.x) ** 2 + (clickY - pt.y) ** 2);
                        if (dist < closestDist) {
                            closestDist = dist;
                            closestPoint = pt;
                        }
                    });
                });

                // Also check points of current aisle being drawn (for closing loops)
                if (currentAislePoints.length > 0) {
                    currentAislePoints.forEach(pt => {
                        const dist = Math.sqrt((clickX - pt.x) ** 2 + (clickY - pt.y) ** 2);
                        if (dist < closestDist) {
                            closestDist = dist;
                            closestPoint = pt;
                        }
                    });
                }

                if (closestPoint) {
                    clickX = closestPoint.x;
                    clickY = closestPoint.y;
                    snappedToAisle = true;
                }
            }

            // === SNAP TO PERIMETER LOOP EDGES ===
            // If near a perimeter edge, snap to the center of that edge (drive lane)
            const layout = parkingLayoutRef.current;
            const snapDistance = 20; // Snap within 20ft of perimeter

            if (layout && layout.loopOuter) {
                const loop = layout.loopOuter;
                const loopW = layout.loopWidth || 24;

                // Calculate the center of each perimeter edge (where vehicles drive)
                const topEdgeY = loop.y + loopW / 2;
                const bottomEdgeY = loop.y + loop.h - loopW / 2;
                const leftEdgeX = loop.x + loopW / 2;
                const rightEdgeX = loop.x + loop.w - loopW / 2;

                // Check proximity to each edge and snap
                // Top edge
                if (Math.abs(clickY - topEdgeY) < snapDistance && clickX >= loop.x && clickX <= loop.x + loop.w) {
                    clickY = topEdgeY;
                }
                // Bottom edge
                else if (Math.abs(clickY - bottomEdgeY) < snapDistance && clickX >= loop.x && clickX <= loop.x + loop.w) {
                    clickY = bottomEdgeY;
                }
                // Left edge
                if (Math.abs(clickX - leftEdgeX) < snapDistance && clickY >= loop.y && clickY <= loop.y + loop.h) {
                    clickX = leftEdgeX;
                }
                // Right edge
                else if (Math.abs(clickX - rightEdgeX) < snapDistance && clickY >= loop.y && clickY <= loop.y + loop.h) {
                    clickX = rightEdgeX;
                }
            }

            // === ORTHO MODE: Snap to horizontal or vertical from previous point ===
            // This ensures drive aisles are always orthogonal (like real parking lots)
            // Skip ortho if we snapped to an existing aisle point (junction takes priority)
            if (currentAislePoints.length > 0 && !snappedToAisle) {
                const lastPoint = currentAislePoints[currentAislePoints.length - 1];
                const dx = Math.abs(clickX - lastPoint.x);
                const dy = Math.abs(clickY - lastPoint.y);

                // Snap to the axis with the larger delta
                if (dx > dy) {
                    // Horizontal line - keep X, snap Y to previous
                    clickY = lastPoint.y;
                } else {
                    // Vertical line - keep Y, snap X to previous
                    clickX = lastPoint.x;
                }
            }

            // Add point to current aisle
            setCurrentAislePoints(prev => [...prev, { x: clickX, y: clickY }]);
            return;
        }

        // === SPINE PLACEMENT MODE ===
        // If in spine placement mode, add a manual cross-aisle spine at click position
        if (isPlacingSpine && parkingLayoutRef.current) {
            const canvas = canvasRef.current;
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const clickX = canvasCoords.x / SCALE;

            const layout = parkingLayoutRef.current;

            // Calculate vertical extent for the spine
            // Spine spans from first row to last row
            if (layout.rows && layout.rows.length > 0) {
                const minY = Math.min(...layout.rows.map(r => r.y));
                const maxY = Math.max(...layout.rows.map(r => r.y + r.height));

                // Validate click is within parking area
                const minX = layout.sectionX;
                const maxX = layout.sectionX + layout.stallsPerRow * layout.stallWidth;

                if (clickX >= minX && clickX <= maxX) {
                    // Add new spine at this X position
                    setManualSpines(prev => [...prev, {
                        x: clickX,
                        minY: minY,
                        maxY: maxY,
                        id: Date.now()
                    }]);
                    setIsPlacingSpine(false);
                    setSpineHoverX(null);
                    return;
                }
            }

            // Click outside valid area - exit placement mode
            setIsPlacingSpine(false);
            setSpineHoverX(null);
            return;
        }

        // === ADA PLACEMENT MODE ===
        // If in ADA placement mode, calculate row and stall index from click position
        if (isPlacingAda && parkingLayoutRef.current) {
            const canvas = canvasRef.current;
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            const canvasCoords = screenToCanvas(mouseX, mouseY);
            const clickX = canvasCoords.x / SCALE;
            const clickY = canvasCoords.y / SCALE;

            const layout = parkingLayoutRef.current;

            // Find which row was clicked (check all rows)
            let clickedRow = null;
            for (const row of layout.rows) {
                if (clickY >= row.y && clickY <= row.y + row.height) {
                    clickedRow = row;
                    break;
                }
            }

            if (clickedRow) {
                // Calculate which stall index was clicked
                const relativeX = clickX - layout.sectionX;
                const stallIndex = Math.floor(relativeX / layout.stallWidth);

                // Validate the index is within valid range
                // ADA cluster needs (adaClusterSize) positions, so max start is (stallsPerRow - adaClusterSize)
                const maxStartIndex = layout.stallsPerRow - layout.adaClusterSize;
                if (stallIndex >= 0 && stallIndex <= maxStartIndex) {
                    // Set the ADA position to this stall index AND row
                    setMassingParams(prev => ({
                        ...prev,
                        adaPosition: stallIndex,
                        adaRow: clickedRow.rowIndex
                    }));
                    setIsPlacingAda(false);
                    setAdaHoverIndex(null);
                    setAdaHoverRow(null);
                    return;
                }
            }

            // Click outside valid area - exit placement mode
            setIsPlacingAda(false);
            setAdaHoverIndex(null);
            setAdaHoverRow(null);
            return;
        }

        // Don't handle clicks when editing boundary (handled by mousedown)
        if (isEditingBoundary && !isDrawing) return;

        // If we were dragging a template building or amenity, don't process click
        if (draggingTemplateBuilding2D !== null || draggingAmenity !== null) return;

        // If we were panning, don't process click
        if (isPanning) return;

        // Pan mode - don't add points
        if (editMode === 'pan') return;

        // Select mode - only allow selection, not drawing (when boundary exists)
        if (editMode === 'select' && boundary.length >= 3 && !isDrawing) return;

        const canvas = canvasRef.current;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Convert screen coordinates to canvas coordinates (accounting for zoom/pan)
        const canvasCoords = screenToCanvas(mouseX, mouseY);
        let x = Math.round(canvasCoords.x / SCALE);
        let y = Math.round(canvasCoords.y / SCALE);

        // Check for template building or amenity click in 2D mode (for selection)
        // Only check for selection when NOT actively drawing (boundary or exclusion)
        if (viewMode === '2d' && !isDrawing && boundary.length >= 3 && drawMode === 'boundary' && currentExclusion.length === 0) {
            const templateIdx = findTemplateBuildingAt(mouseX, mouseY);
            const amenity = findAmenityAt(mouseX, mouseY);
            if (templateIdx !== null || amenity !== null) {
                // Already handled in mousedown
                return;
            }
            // If clicked on empty space, just deselect but DON'T return - allow starting new boundary
            handleSelectTemplateBuilding(null);
            setSelectedAmenity(null);
        }

        // Apply snapping for drawing
        if (drawMode === 'boundary' && isDrawing && boundary.length > 0) {
            const lastPoint = boundary[boundary.length - 1];
            const snapped = applySnapping(x, y, lastPoint);
            x = Math.round(snapped.x);
            y = Math.round(snapped.y);
        } else if (drawMode === 'exclusion' && currentExclusion.length > 0) {
            const lastPoint = currentExclusion[currentExclusion.length - 1];
            const snapped = applySnapping(x, y, lastPoint);
            x = Math.round(snapped.x);
            y = Math.round(snapped.y);
        } else {
            const snapped = snapToGridPoint(x, y);
            x = Math.round(snapped.x);
            y = Math.round(snapped.y);
        }

        if (drawMode === 'boundary') {
            if (!isDrawing) {
                setBoundary([{ x, y }]);
                setIsDrawing(true);
            } else {
                // Check if clicking near first point to close
                const first = boundary[0];
                const dist = Math.sqrt((x - first.x) ** 2 + (y - first.y) ** 2);
                if (dist < 10 && boundary.length >= 3) {
                    setIsDrawing(false);
                } else {
                    setBoundary([...boundary, { x, y }]);
                }
            }
        } else if (drawMode === 'exclusion') {
            if (currentExclusion.length === 0) {
                setCurrentExclusion([{ x, y }]);
            } else {
                const first = currentExclusion[0];
                const dist = Math.sqrt((x - first.x) ** 2 + (y - first.y) ** 2);
                if (dist < 10 && currentExclusion.length >= 3) {
                    setExclusions([...exclusions, currentExclusion]);
                    setCurrentExclusion([]);
                } else {
                    setCurrentExclusion([...currentExclusion, { x, y }]);
                }
            }
        }
    }, [boundary, isDrawing, drawMode, currentExclusion, exclusions, SCALE, isEditingBoundary, applySnapping, snapToGridPoint, viewMode, findTemplateBuildingAt, handleSelectTemplateBuilding, draggingTemplateBuilding2D, draggingAmenity, findAmenityAt, editMode, isPanning, screenToCanvas, isPlacingAda, setMassingParams, isPlacingSpine, setManualSpines, setSpineHoverX, isDrawingAisle]);

    // Generate feasibility
    const handleGenerate = useCallback(async () => {
        if (boundary.length < 3) {
            return;
        }

        setLoading(true);
        setError(null);

        try {
            // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
            const v2Flags = getV2Flags();
            const requestBody = {
                site: {
                    boundary: boundary,
                    exclusions: exclusions.map(ex => ({ polygon: ex })),
                },
                constraints: {
                    far: far,
                    height_limit: heightLimit,
                    lot_coverage: lotCoverage,
                    parking_ratio: parkingRatio,
                    setbacks: setbacks,
                },
                building_type: {
                    type: buildingType,
                    subtype: buildingSubtype,
                    config: currentSubtype,
                },
                options: {
                    parking_angles: [90],
                    building_positions: ['centered'],
                    optimize_for: 'units',
                },
                // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
                ...v2Flags,
            };

            try {
                const res = await fetch('/api/sitegen/feasibility', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify(requestBody),
                });

                if (!res.ok) {
                    // Silently ignore API errors - feasibility API not critical for parking visualization
                    console.debug('Feasibility API unavailable');
                    return;
                }

                const data = await res.json();
                setResults(data);
                setActiveConfig(0);
            } catch {
                // Silently ignore network errors
                console.debug('Feasibility API unreachable');
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [boundary, exclusions, far, heightLimit, lotCoverage, parkingRatio, setbacks, buildingType, buildingSubtype, currentSubtype]);

    // Auto-regenerate when constraints change (if we have a valid boundary)
    useEffect(() => {
        if (boundary.length >= 3 && !isDrawing) {
            handleGenerate();
        }
    }, [far, heightLimit, lotCoverage, parkingRatio, setbacks, buildingType, buildingSubtype, handleGenerate, isDrawing]);

    // Clear
    const handleClear = () => {
        setBoundary([]);
        setIsDrawing(false);
        setExclusions([]);
        setCurrentExclusion([]);
        setResults(null);
        setError(null);
    };

    // Quick demo boundary - Use 5 points so it always uses polygon rendering
    // This ensures consistent appearance whether editing or not
    const handleDemo = () => {
        // Create a simple rectangle with 5 points (adds midpoint on bottom edge)
        // This triggers polygon-based rendering which is more accurate
        setBoundary([
            { x: 50, y: 50 },
            { x: 250, y: 50 },
            { x: 250, y: 200 },
            { x: 150, y: 200 },  // Midpoint on bottom edge
            { x: 50, y: 200 },
        ]);
        setIsDrawing(false);
        setExclusions([]);
    };

    // Calculate site area
    const siteArea = boundary.length >= 3 ? (() => {
        let area = 0;
        for (let i = 0; i < boundary.length; i++) {
            const j = (i + 1) % boundary.length;
            area += boundary[i].x * boundary[j].y;
            area -= boundary[j].x * boundary[i].y;
        }
        return Math.abs(area / 2);
    })() : 0;

    return (
        <div className="h-full w-full overflow-hidden bg-slate-50 text-slate-900 flex flex-col">
            {/* Header */}
            <div className="flex-shrink-0 bg-white border-b border-slate-200 px-4 py-2 shadow-sm">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center shadow">
                            <span className="text-base">🏗️</span>
                        </div>
                        <div>
                            <h1 className="text-lg font-bold text-slate-900">SiteGen</h1>
                        </div>
                    </div>
                    <div className="flex gap-2 items-center">
                        {/* 2D/3D Toggle */}
                        <div className="flex bg-slate-100 rounded-lg overflow-hidden border border-slate-200">
                            <button
                                onClick={() => setViewMode('2d')}
                                className={`px-3 py-1.5 text-xs font-medium transition-all ${viewMode === '2d'
                                    ? 'bg-white text-slate-900 shadow-md'
                                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200'
                                    }`}
                            >
                                <span className="flex items-center gap-1">📐 2D</span>
                            </button>
                            <button
                                onClick={() => setViewMode('3d')}
                                className={`px-3 py-1.5 text-xs font-medium transition-all ${viewMode === '3d'
                                    ? 'bg-white text-slate-900 shadow-md'
                                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200'
                                    }`}
                            >
                                <span className="flex items-center gap-1">🎲 3D</span>
                            </button>
                        </div>
                        <button
                            onClick={handleDemo}
                            className="px-3 py-1.5 bg-white hover:bg-slate-50 rounded-lg text-xs border border-slate-200 transition-all text-slate-700 hover:text-slate-900"
                        >
                            📍 Demo
                        </button>
                        <button
                            onClick={handleClear}
                            className="px-3 py-1.5 bg-white hover:bg-red-50 rounded-lg text-xs border border-slate-200 transition-all text-slate-700 hover:text-red-600 hover:border-red-300"
                        >
                            🗑️ Clear
                        </button>
                        <button
                            onClick={handleGenerate}
                            disabled={loading || boundary.length < 3}
                            className="px-4 py-1.5 bg-white hover:bg-slate-50 text-slate-900 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed rounded-lg text-xs font-medium shadow-sm transition-all"
                        >
                            {loading ? '⏳...' : '✨ Generate'}
                        </button>
                    </div>
                </div>
            </div>

            <div className="flex-1 flex overflow-hidden">
                {/* Sidebar - Collapsible */}
                <div className={`sitegen-sidebar flex-shrink-0 bg-white overflow-y-auto border-r border-slate-200 transition-all duration-300 ${sidebarCollapsed ? 'w-0 p-0 overflow-hidden' : 'w-64 p-2'}`}>

                    {/* Building Type Selection */}
                    <div className="mb-4">
                        <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-2">
                            <span className="text-slate-500">▸</span> Building Type
                        </label>
                        <div className="grid grid-cols-4 gap-1 mb-2">
                            {Object.entries(BUILDING_TYPES).map(([key, bt]) => (
                                <button
                                    key={key}
                                    onClick={() => {
                                        setBuildingType(key);
                                        const firstSubtype = Object.keys(bt.subtypes)[0];
                                        setBuildingSubtype(firstSubtype);
                                        // Reset massing to first available for this type
                                        const typeMassings = MASSING_TYPOLOGIES[key];
                                        if (typeMassings) {
                                            setMassingType(Object.keys(typeMassings)[0]);
                                        }
                                        // Update parking ratio from subtype
                                        const subConfig = bt.subtypes[firstSubtype];
                                        if (subConfig.parkingRatio !== undefined) {
                                            setParkingRatio(subConfig.parkingRatio);
                                        }
                                    }}
                                    className={`p-2 rounded-lg text-center transition-all ${buildingType === key
                                        ? 'bg-teal-100 text-teal-800 ring-2 ring-teal-400 shadow-sm'
                                        : 'bg-slate-50 hover:bg-slate-100 border border-slate-200/50 hover:border-slate-300'}`}
                                    title={bt.name}
                                >
                                    <div className="text-xl mb-0.5">{bt.icon}</div>
                                    <div className="text-[9px] font-medium truncate text-slate-600">{bt.name.split('-')[0]}</div>
                                </button>
                            ))}
                        </div>

                        {/* Subtype dropdown */}
                        <select
                            value={buildingSubtype}
                            onChange={e => {
                                setBuildingSubtype(e.target.value);
                                const subConfig = currentBuildingType?.subtypes[e.target.value];
                                if (subConfig?.parkingRatio !== undefined) {
                                    setParkingRatio(subConfig.parkingRatio);
                                }
                            }}
                            className="w-full bg-slate-100 rounded px-3 py-2 text-sm"
                        >
                            {Object.entries(currentBuildingType?.subtypes || {}).map(([key, st]) => (
                                <option key={key} value={key}>{st.name}</option>
                            ))}
                        </select>

                        {/* Subtype details */}
                        {currentSubtype && (
                            <div className="mt-1.5 p-2 bg-slate-100/50 rounded-lg border border-slate-300 text-[10px] text-slate-500 space-y-0.5">
                                {currentSubtype.unitSize && <div className="flex justify-between"><span className="text-slate-500">Unit Size</span><span className="text-slate-600">{currentSubtype.unitSize} SF</span></div>}
                                {currentSubtype.roomSize && <div className="flex justify-between"><span className="text-slate-500">Room Size</span><span className="text-slate-600">{currentSubtype.roomSize} SF</span></div>}
                                {currentSubtype.lotSize && <div className="flex justify-between"><span className="text-slate-500">Lot Size</span><span className="text-slate-600">{currentSubtype.lotSize} SF</span></div>}
                                {currentSubtype.floors && <div className="flex justify-between"><span className="text-slate-500">Typical Floors</span><span className="text-slate-600">{currentSubtype.floors}</span></div>}
                                {currentSubtype.efficiency && <div className="flex justify-between"><span className="text-slate-500">Efficiency</span><span className="text-green-400">{(currentSubtype.efficiency * 100).toFixed(0)}%</span></div>}
                                {currentSubtype.clearHeight && <div className="flex justify-between"><span className="text-slate-500">Clear Height</span><span className="text-slate-600">{currentSubtype.clearHeight} ft</span></div>}
                                {currentSubtype.powerDensity && <div className="flex justify-between"><span className="text-slate-500">Power Density</span><span className="text-yellow-400">{currentSubtype.powerDensity} W/SF</span></div>}
                            </div>
                        )}
                    </div>

                    {/* Massing Typology Selection */}
                    {Object.keys(currentMassings).length > 0 && (
                        <div className="mb-4">
                            <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-2">
                                <span className="text-teal-600">▸</span> Massing
                                <span className="ml-auto px-1.5 py-0.5 bg-teal-500/20 text-teal-600 text-[8px] rounded-full font-medium">NEW</span>
                            </label>
                            <div className="grid grid-cols-3 gap-1.5 mb-2">
                                {Object.entries(currentMassings).map(([key, massing]) => (
                                    <button
                                        key={key}
                                        onClick={() => setMassingType(key)}
                                        className={`p-2 rounded-lg text-center transition-all ${massingType === key
                                            ? 'bg-teal-100 text-teal-800 ring-2 ring-teal-400 shadow-sm'
                                            : 'bg-slate-50 hover:bg-slate-100 border border-slate-200/50 hover:border-teal-500/50'
                                            }`}
                                        title={massing.description}
                                    >
                                        <div className="text-lg mb-0.5">{massing.icon}</div>
                                        <div className="text-[9px] font-medium truncate text-slate-600">{massing.name}</div>
                                    </button>
                                ))}
                            </div>

                            {/* Massing preview card */}
                            {currentMassing && (
                                <div className="p-2 bg-slate-100 rounded-lg border border-slate-200/50">
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <div className="w-7 h-7 bg-teal-500/20 rounded flex items-center justify-center">
                                            <span className="text-lg">{currentMassing.icon}</span>
                                        </div>
                                        <div className="flex-1">
                                            <div className="font-semibold text-slate-900 text-xs">{currentMassing.name}</div>
                                            <div className="text-[10px] text-slate-500 truncate">{currentMassing.description}</div>
                                        </div>
                                    </div>
                                    {/* Mini 3D isometric preview */}
                                    <div className="relative w-full h-16 bg-slate-100 rounded overflow-hidden border border-slate-300">
                                        <MassingPreview massing={currentMassing} />
                                    </div>
                                </div>
                            )}

                            {/* ============================================== */}
                            {/* EDITABLE MASSING PARAMETERS PANEL */}
                            {/* ============================================== */}
                            {currentMassing && Object.keys(massingParams).length > 0 && (
                                <div className="mt-2 p-2 bg-slate-100 rounded-lg border border-slate-200/50">
                                    <div
                                        className="flex items-center justify-between cursor-pointer group"
                                        onClick={() => setShowParamsPanel(!showParamsPanel)}
                                    >
                                        <h4 className="text-xs font-medium text-slate-600 flex items-center gap-1.5">
                                            <span className="text-sm">⚙️</span>
                                            <span>Parameters</span>
                                        </h4>
                                        <button className={`w-5 h-5 rounded flex items-center justify-center transition-all text-[10px] ${showParamsPanel ? 'bg-teal-500/20 text-teal-600' : 'bg-slate-100 text-slate-500 group-hover:bg-slate-200'}`}>
                                            {showParamsPanel ? '▼' : '▶'}
                                        </button>
                                    </div>

                                    {showParamsPanel && (
                                        <div className="space-y-3 mt-3 pt-3 border-t border-slate-200/50">
                                            {/* Dynamic parameter inputs based on massing config */}

                                            {/* Floor-related params */}
                                            {massingParams.floors !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Floors</span>
                                                        <span className="text-teal-600">{massingParams.floors}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="1"
                                                        max="30"
                                                        value={massingParams.floors}
                                                        onChange={e => setMassingParams({ ...massingParams, floors: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.towerFloors !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Tower Floors</span>
                                                        <span className="text-teal-600">{massingParams.towerFloors}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="5"
                                                        max="50"
                                                        value={massingParams.towerFloors}
                                                        onChange={e => setMassingParams({ ...massingParams, towerFloors: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.podiumFloors !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Podium Floors</span>
                                                        <span className="text-teal-600">{massingParams.podiumFloors}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="1"
                                                        max="6"
                                                        value={massingParams.podiumFloors}
                                                        onChange={e => setMassingParams({ ...massingParams, podiumFloors: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.residentialFloors !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Residential Floors</span>
                                                        <span className="text-teal-600">{massingParams.residentialFloors}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="2"
                                                        max="20"
                                                        value={massingParams.residentialFloors}
                                                        onChange={e => setMassingParams({ ...massingParams, residentialFloors: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.garageFloors !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Garage Levels</span>
                                                        <span className="text-teal-600">{massingParams.garageFloors}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="1"
                                                        max="8"
                                                        value={massingParams.garageFloors}
                                                        onChange={e => setMassingParams({ ...massingParams, garageFloors: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {/* Height params */}
                                            {massingParams.floorHeight !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Floor Height</span>
                                                        <span className="text-teal-600">{massingParams.floorHeight} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="8"
                                                        max="16"
                                                        value={massingParams.floorHeight}
                                                        onChange={e => setMassingParams({ ...massingParams, floorHeight: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.podiumHeight !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Podium Height</span>
                                                        <span className="text-teal-600">{massingParams.podiumHeight} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="10"
                                                        max="30"
                                                        value={massingParams.podiumHeight}
                                                        onChange={e => setMassingParams({ ...massingParams, podiumHeight: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.clearHeight !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Clear Height</span>
                                                        <span className="text-teal-600">{massingParams.clearHeight} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="20"
                                                        max="50"
                                                        value={massingParams.clearHeight}
                                                        onChange={e => setMassingParams({ ...massingParams, clearHeight: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.garageHeight !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Garage Floor Height</span>
                                                        <span className="text-teal-600">{massingParams.garageHeight} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="9"
                                                        max="14"
                                                        value={massingParams.garageHeight}
                                                        onChange={e => setMassingParams({ ...massingParams, garageHeight: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {/* Dimensional params */}
                                            {massingParams.unitWidth !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Unit Width</span>
                                                        <span className="text-teal-600">{massingParams.unitWidth} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="18"
                                                        max="36"
                                                        value={massingParams.unitWidth}
                                                        onChange={e => setMassingParams({ ...massingParams, unitWidth: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.unitDepth !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Unit Depth</span>
                                                        <span className="text-teal-600">{massingParams.unitDepth} ft</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="30"
                                                        max="80"
                                                        value={massingParams.unitDepth}
                                                        onChange={e => setMassingParams({ ...massingParams, unitDepth: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {massingParams.buildingCount !== undefined && (
                                                <div>
                                                    <label className="text-xs text-slate-500 flex justify-between">
                                                        <span>Building Count</span>
                                                        <span className="text-teal-600">{massingParams.buildingCount}</span>
                                                    </label>
                                                    <input
                                                        type="range"
                                                        min="2"
                                                        max="8"
                                                        value={massingParams.buildingCount}
                                                        onChange={e => setMassingParams({ ...massingParams, buildingCount: parseInt(e.target.value) })}
                                                        className="w-full accent-teal-500"
                                                    />
                                                </div>
                                            )}

                                            {/* ===== SURFACE PARKING PARAMETERS (US STANDARDS) ===== */}
                                            {massingParams.stallWidth !== undefined && (
                                                <div className="pt-2 border-t border-slate-200">
                                                    <div className="text-xs text-yellow-400 font-medium mb-2">🅿️ US Parking Standards</div>

                                                    {/* Stall Dimensions */}
                                                    <div className="grid grid-cols-2 gap-2 mb-2">
                                                        <div>
                                                            <label className="text-xs text-slate-500">Stall Width</label>
                                                            <div className="flex items-center gap-1">
                                                                <input
                                                                    type="number"
                                                                    min="8"
                                                                    max="10"
                                                                    step="0.5"
                                                                    value={massingParams.stallWidth}
                                                                    onChange={e => setMassingParams({ ...massingParams, stallWidth: parseFloat(e.target.value) })}
                                                                    className="w-full bg-slate-100 rounded px-2 py-1 text-xs"
                                                                />
                                                                <span className="text-xs text-slate-500">ft</span>
                                                            </div>
                                                        </div>
                                                        <div>
                                                            <label className="text-xs text-slate-500">Stall Depth</label>
                                                            <div className="flex items-center gap-1">
                                                                <input
                                                                    type="number"
                                                                    min="16"
                                                                    max="20"
                                                                    step="0.5"
                                                                    value={massingParams.stallDepth}
                                                                    onChange={e => setMassingParams({ ...massingParams, stallDepth: parseFloat(e.target.value) })}
                                                                    className="w-full bg-slate-100 rounded px-2 py-1 text-xs"
                                                                />
                                                                <span className="text-xs text-slate-500">ft</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {/* Aisle Width */}
                                                    <div className="mb-2">
                                                        <label className="text-xs text-slate-500 flex justify-between">
                                                            <span>Drive Aisle Width</span>
                                                            <span className="text-yellow-400">{massingParams.aisleWidth} ft</span>
                                                        </label>
                                                        <input
                                                            type="range"
                                                            min="12"
                                                            max="26"
                                                            value={massingParams.aisleWidth}
                                                            onChange={e => setMassingParams({ ...massingParams, aisleWidth: parseInt(e.target.value) })}
                                                            className="w-full accent-yellow-500"
                                                        />
                                                        <div className="text-xs text-slate-500">24' two-way | 12-18' one-way</div>
                                                    </div>

                                                    {/* Parking Angle */}
                                                    <div className="mb-2">
                                                        <label className="text-xs text-slate-500">Parking Angle</label>
                                                        <div className="flex gap-1 mt-1">
                                                            {[45, 60, 90].map(angle => (
                                                                <button
                                                                    key={angle}
                                                                    onClick={() => {
                                                                        const newAisle = angle === 90 ? 24 : angle === 60 ? 18 : 13;
                                                                        setMassingParams({
                                                                            ...massingParams,
                                                                            parkingAngle: angle,
                                                                            aisleWidth: newAisle
                                                                        });
                                                                    }}
                                                                    className={`flex-1 px-2 py-1 rounded text-xs ${massingParams.parkingAngle === angle
                                                                        ? 'bg-yellow-100 text-yellow-800'
                                                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                                        }`}
                                                                >
                                                                    {angle}°
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>

                                                    {/* Drive Type (One-way vs Two-way) */}
                                                    <div className="mb-2">
                                                        <label className="text-xs text-slate-500">Circulation</label>
                                                        <div className="flex gap-1 mt-1">
                                                            <button
                                                                onClick={() => setMassingParams({
                                                                    ...massingParams,
                                                                    driveType: 'twoWay',
                                                                    aisleWidth: 24
                                                                })}
                                                                className={`flex-1 px-2 py-1 rounded text-xs ${massingParams.driveType === 'twoWay'
                                                                    ? 'bg-blue-100 text-blue-800'
                                                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                                    }`}
                                                            >
                                                                ↔ Two-Way
                                                            </button>
                                                            <button
                                                                onClick={() => setMassingParams({
                                                                    ...massingParams,
                                                                    driveType: 'oneWay',
                                                                    aisleWidth: 14
                                                                })}
                                                                className={`flex-1 px-2 py-1 rounded text-xs ${massingParams.driveType === 'oneWay'
                                                                    ? 'bg-blue-100 text-blue-800'
                                                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                                    }`}
                                                            >
                                                                → One-Way
                                                            </button>
                                                        </div>
                                                    </div>

                                                    {/* Landscaping */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Landscape Islands</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasLandscaping: !massingParams.hasLandscaping
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasLandscaping
                                                                ? 'bg-green-100 text-green-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.hasLandscaping ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {massingParams.hasLandscaping && (
                                                        <div className="mb-2">
                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span>Island Interval</span>
                                                                <span className="text-green-400">Every {massingParams.landscapeInterval} stalls</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="8"
                                                                max="25"
                                                                value={massingParams.landscapeInterval}
                                                                onChange={e => setMassingParams({ ...massingParams, landscapeInterval: parseInt(e.target.value) })}
                                                                className="w-full accent-green-500"
                                                            />
                                                        </div>
                                                    )}

                                                    {/* End Islands Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">End Islands</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                endIslands: !massingParams.endIslands
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.endIslands
                                                                ? 'bg-green-100 text-green-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.endIslands ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Fire Lane Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Fire Lane</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                fireLane: !massingParams.fireLane
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.fireLane
                                                                ? 'bg-red-100 text-red-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.fireLane ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Entry/Exit Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Entry/Exit</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasEntryExit: !massingParams.hasEntryExit
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasEntryExit
                                                                ? 'bg-orange-100 text-orange-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.hasEntryExit ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Entry/Exit Type Selector - Per ITE Parking Generation Standards */}
                                                    {massingParams.hasEntryExit && (
                                                        <div className="flex items-center justify-between mb-2">
                                                            <label className="text-xs text-slate-500">Entry Type</label>
                                                            <div className="flex gap-1">
                                                                {[
                                                                    { id: 'standard', label: 'STD', title: 'Standard Driveway (12ft lanes, throat depth per code)' },
                                                                    { id: 'channelized', label: 'CHN', title: 'Channelized Entry (raised median island, per ITE)' },
                                                                    { id: 'fullAccess', label: 'FULL', title: 'Full Access (wide curb cut, all movements)' }
                                                                ].map(type => (
                                                                    <button
                                                                        key={type.id}
                                                                        onClick={() => setMassingParams({
                                                                            ...massingParams,
                                                                            entryExitType: type.id
                                                                        })}
                                                                        className={`px-1.5 py-0.5 rounded text-[10px] ${(massingParams.entryExitType || 'standard') === type.id
                                                                            ? 'bg-blue-500 text-white'
                                                                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                                                                            }`}
                                                                        title={type.title}
                                                                    >
                                                                        {type.label}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* Gate Booth Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Gate Booth</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasGateBooth: !massingParams.hasGateBooth
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasGateBooth !== false
                                                                ? 'bg-amber-100 text-amber-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.hasGateBooth !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* ADA Accessible Stalls Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">ADA Stalls</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasAda: !massingParams.hasAda
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasAda !== false
                                                                ? 'bg-blue-100 text-blue-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                            title="ADA accessible parking per code requirements"
                                                        >
                                                            {massingParams.hasAda !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* ADA Extra Slider - Only show when ADA is enabled */}
                                                    {massingParams.hasAda !== false && (
                                                        <div className="mb-2 pl-2 border-l-2 border-blue-200">
                                                            {/* Auto-calculated ADA count based on total stalls */}
                                                            {parkingLayout && parkingLayout.totalStalls > 0 && (() => {
                                                                const adaCalc = calculateAdaRequired(parkingLayout.totalStalls);
                                                                const totalAda = adaCalc.total + (massingParams.adaExtra || 0);
                                                                const vanCount = Math.max(1, Math.ceil(totalAda / 6));
                                                                return (
                                                                    <div className="mb-2 p-2 bg-blue-50 rounded text-xs">
                                                                        <div className="flex justify-between">
                                                                            <span className="text-slate-600">Total Stalls:</span>
                                                                            <span className="font-medium">{parkingLayout.totalStalls}</span>
                                                                        </div>
                                                                        <div className="flex justify-between">
                                                                            <span className="text-slate-600">Code Min (Table 208.2):</span>
                                                                            <span className="font-medium text-blue-600">{adaCalc.total}</span>
                                                                        </div>
                                                                        {(massingParams.adaExtra || 0) > 0 && (
                                                                            <div className="flex justify-between">
                                                                                <span className="text-slate-600">Extra:</span>
                                                                                <span className="font-medium text-green-600">+{massingParams.adaExtra}</span>
                                                                            </div>
                                                                        )}
                                                                        <div className="flex justify-between border-t border-blue-200 mt-1 pt-1">
                                                                            <span className="font-medium text-slate-700">Total ADA:</span>
                                                                            <span className="font-bold text-blue-700">{totalAda} ({vanCount} Van)</span>
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })()}

                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span>Extra ADA</span>
                                                                <span className="text-blue-400">+{massingParams.adaExtra || 0}</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="0"
                                                                max="10"
                                                                value={massingParams.adaExtra || 0}
                                                                onChange={e => setMassingParams({ ...massingParams, adaExtra: parseInt(e.target.value) })}
                                                                className="w-full accent-blue-500 h-1"
                                                                title="Additional ADA stalls beyond code minimum (for medical, senior housing, etc.)"
                                                            />
                                                            <div className="text-xs text-slate-400 mt-0.5">Code min + extra for special uses</div>

                                                            {/* ADA Position Control */}
                                                            <div className="flex items-center justify-between mt-2">
                                                                <label className="text-xs text-slate-500">Position</label>
                                                                <div className="flex items-center gap-1">
                                                                    <select
                                                                        value={massingParams.adaPosition || 0}
                                                                        onChange={e => setMassingParams({ ...massingParams, adaPosition: parseInt(e.target.value) })}
                                                                        className="text-xs px-1 py-0.5 rounded border border-slate-300 bg-white"
                                                                        title="Position ADA cluster along the row"
                                                                    >
                                                                        <option value="0">Start</option>
                                                                        <option value="-1">End</option>
                                                                        {massingParams.adaPosition > 0 && (
                                                                            <option value={massingParams.adaPosition}>@Stall {massingParams.adaPosition}</option>
                                                                        )}
                                                                    </select>
                                                                    <button
                                                                        onClick={() => setIsPlacingAda(!isPlacingAda)}
                                                                        className={`px-2 py-0.5 rounded text-xs ${isPlacingAda
                                                                            ? 'bg-blue-500 text-white animate-pulse'
                                                                            : 'bg-slate-100 text-slate-600 hover:bg-blue-100'
                                                                            }`}
                                                                        title="Click on any row in parking layout to place ADA cluster"
                                                                    >
                                                                        {isPlacingAda ? '📍 Click...' : '📍'}
                                                                    </button>
                                                                </div>
                                                            </div>

                                                            {/* Show current ADA row when not at default */}
                                                            {(massingParams.adaRow > 0 || massingParams.adaPosition > 0) && (
                                                                <div className="text-xs text-blue-500 mt-1">
                                                                    Row {String.fromCharCode(65 + (massingParams.adaRow || 0))}, Stall {massingParams.adaPosition || 0}
                                                                </div>
                                                            )}

                                                            {isPlacingAda && (
                                                                <div className="text-xs text-blue-500 mt-1 animate-pulse">
                                                                    Click on any row to place ADA cluster
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}

                                                    {/* Crosswalk Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Crosswalk</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasCrosswalk: !massingParams.hasCrosswalk
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasCrosswalk !== false
                                                                ? 'bg-yellow-100 text-yellow-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.hasCrosswalk !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Cross-Aisle Spine Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Cross-Aisle</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                hasCrossAisle: !massingParams.hasCrossAisle
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.hasCrossAisle !== false
                                                                ? 'bg-blue-100 text-blue-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.hasCrossAisle !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Cross-Aisle Extended Options - Only show when enabled */}
                                                    {massingParams.hasCrossAisle !== false && (
                                                        <div className="mb-2 pl-2 border-l-2 border-blue-200">
                                                            {/* Mode Selection */}
                                                            <div className="mb-2">
                                                                <label className="text-xs text-slate-500 block mb-1">Mode</label>
                                                                <div className="flex gap-1 flex-wrap">
                                                                    <button
                                                                        onClick={() => setCrossAisleMode('auto')}
                                                                        className={`flex-1 px-2 py-1 rounded text-xs ${crossAisleMode === 'auto'
                                                                            ? 'bg-blue-500 text-white'
                                                                            : 'bg-slate-100 text-slate-600 hover:bg-blue-100'
                                                                            }`}
                                                                        title="Auto-detect: Only for rectangular lots >200ft wide"
                                                                    >
                                                                        Auto
                                                                    </button>
                                                                    <button
                                                                        onClick={() => setCrossAisleMode('force')}
                                                                        className={`flex-1 px-2 py-1 rounded text-xs ${crossAisleMode === 'force'
                                                                            ? 'bg-green-500 text-white'
                                                                            : 'bg-slate-100 text-slate-600 hover:bg-green-100'
                                                                            }`}
                                                                        title="Force: Enable for any shape, auto-detect rectangular sub-regions"
                                                                    >
                                                                        Force
                                                                    </button>
                                                                    <button
                                                                        onClick={() => setCrossAisleMode('manual')}
                                                                        className={`flex-1 px-2 py-1 rounded text-xs ${crossAisleMode === 'manual'
                                                                            ? 'bg-purple-500 text-white'
                                                                            : 'bg-slate-100 text-slate-600 hover:bg-purple-100'
                                                                            }`}
                                                                        title="Manual: Click to place vertical spines"
                                                                    >
                                                                        Manual
                                                                    </button>
                                                                </div>
                                                            </div>

                                                            {/* Mode Description */}
                                                            <div className="text-xs text-slate-400 mb-2">
                                                                {crossAisleMode === 'auto' && 'Spines appear for rectangular lots >200ft wide'}
                                                                {crossAisleMode === 'force' && 'Forces spines for any shape (auto-detects regions)'}
                                                                {crossAisleMode === 'manual' && 'Click to place vertical spines anywhere'}
                                                            </div>

                                                            {/* Manual Placement Controls */}
                                                            {crossAisleMode === 'manual' && (
                                                                <div className="mb-2">
                                                                    <div className="flex items-center justify-between gap-2">
                                                                        <button
                                                                            onClick={() => {
                                                                                setIsPlacingSpine(!isPlacingSpine);
                                                                                setIsPlacingAda(false); // Cancel ADA placement if active
                                                                            }}
                                                                            className={`flex-1 px-2 py-1 rounded text-xs ${isPlacingSpine
                                                                                ? 'bg-purple-500 text-white animate-pulse'
                                                                                : 'bg-purple-100 text-purple-700 hover:bg-purple-200'
                                                                                }`}
                                                                            title="Click on parking area to place a vertical cross-aisle"
                                                                        >
                                                                            {isPlacingSpine ? '📍 Click to Place...' : '➕ Add Spine'}
                                                                        </button>
                                                                        {manualSpines.length > 0 && (
                                                                            <button
                                                                                onClick={() => setManualSpines([])}
                                                                                className="px-2 py-1 rounded text-xs bg-red-100 text-red-600 hover:bg-red-200"
                                                                                title="Remove all manually placed spines"
                                                                            >
                                                                                🗑️ All
                                                                            </button>
                                                                        )}
                                                                    </div>

                                                                    {/* List of manual spines with individual delete */}
                                                                    {manualSpines.length > 0 && (() => {
                                                                        // Sort spines by X position (left to right) for display
                                                                        const sortedSpines = [...manualSpines]
                                                                            .map((spine, originalIdx) => ({ ...spine, originalIdx }))
                                                                            .sort((a, b) => a.x - b.x);

                                                                        return (
                                                                            <div className="mt-2 space-y-1">
                                                                                {sortedSpines.map((spine, sortedIdx) => {
                                                                                    // Use letters A, B, C... from left to right
                                                                                    const letter = String.fromCharCode(65 + sortedIdx);
                                                                                    return (
                                                                                        <div key={spine.id || spine.originalIdx} className="flex items-center justify-between bg-purple-50 rounded px-2 py-1">
                                                                                            <span className="text-xs text-purple-700">
                                                                                                Drive Aisle {letter}
                                                                                            </span>
                                                                                            <button
                                                                                                onClick={() => setManualSpines(prev => prev.filter((_, i) => i !== spine.originalIdx))}
                                                                                                className="text-red-500 hover:text-red-700 text-xs px-1"
                                                                                                title={`Remove Drive Aisle ${letter}`}
                                                                                            >
                                                                                                ✕
                                                                                            </button>
                                                                                        </div>
                                                                                    );
                                                                                })}
                                                                            </div>
                                                                        );
                                                                    })()}

                                                                    {isPlacingSpine && (
                                                                        <div className="text-xs text-purple-500 mt-1 animate-pulse">
                                                                            Click on parking area to add spine
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}

                                                    {/* === CUSTOM AISLES STATUS (Editing via canvas toolbar) === */}
                                                    <div className="mb-2 p-2 bg-slate-50 rounded-lg">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-xs font-medium text-slate-600">Circulation Layout</span>
                                                            {drawnAisles.length > 0 ? (
                                                                <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">Custom</span>
                                                            ) : (
                                                                <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">Auto</span>
                                                            )}
                                                        </div>
                                                        {drawnAisles.length > 0 ? (
                                                            <div className="text-xs text-slate-500">
                                                                {drawnAisles.length} custom path{drawnAisles.length !== 1 ? 's' : ''}
                                                                {manualSpines.length > 0 && ` + ${manualSpines.length} spine${manualSpines.length !== 1 ? 's' : ''}`}
                                                            </div>
                                                        ) : manualSpines.length > 0 ? (
                                                            <div className="text-xs text-slate-500">
                                                                {manualSpines.length} manual spine{manualSpines.length !== 1 ? 's' : ''}
                                                            </div>
                                                        ) : (
                                                            <div className="text-xs text-slate-500">
                                                                Auto-generated layout
                                                            </div>
                                                        )}
                                                        <div className="mt-1.5 pt-1.5 border-t border-slate-200 text-[10px] text-slate-400">
                                                            Use canvas toolbar below to edit<br />
                                                            <span className="font-medium">D</span>=Draw <span className="font-medium">E</span>=Edit <span className="font-medium">S</span>=Spine <span className="font-medium">R</span>=Reset
                                                        </div>
                                                    </div>

                                                    {/* Light Poles Toggle (3D) */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Light Poles</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                showLightPoles: !massingParams.showLightPoles
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.showLightPoles !== false
                                                                ? 'bg-orange-100 text-orange-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.showLightPoles !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* Stall Numbers Toggle */}
                                                    <div className="flex items-center justify-between mb-2">
                                                        <label className="text-xs text-slate-500">Stall #s</label>
                                                        <button
                                                            onClick={() => setMassingParams({
                                                                ...massingParams,
                                                                showStallNumbers: !massingParams.showStallNumbers
                                                            })}
                                                            className={`px-2 py-0.5 rounded text-xs ${massingParams.showStallNumbers !== false
                                                                ? 'bg-purple-100 text-purple-800'
                                                                : 'bg-slate-100 text-slate-500'
                                                                }`}
                                                        >
                                                            {massingParams.showStallNumbers !== false ? 'ON' : 'OFF'}
                                                        </button>
                                                    </div>

                                                    {/* === STALL MIX (Testfit-style) === */}
                                                    <div className="pt-2 border-t border-slate-300 mt-2">
                                                        <div className="text-xs text-teal-600 font-medium mb-2">Stall Mix</div>

                                                        {/* Standard % */}
                                                        <div className="mb-1">
                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span className="flex items-center gap-1">
                                                                    <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                                                                    Standard
                                                                </span>
                                                                <span className="text-yellow-400">{massingParams.standardPct}%</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="50"
                                                                max="100"
                                                                value={massingParams.standardPct}
                                                                onChange={e => {
                                                                    const newStd = parseInt(e.target.value);
                                                                    const remaining = 100 - newStd;
                                                                    setMassingParams({
                                                                        ...massingParams,
                                                                        standardPct: newStd,
                                                                        compactPct: Math.round(remaining * 0.6),
                                                                        adaPct: Math.round(remaining * 0.25),
                                                                        evPct: Math.round(remaining * 0.15)
                                                                    });
                                                                }}
                                                                className="w-full accent-yellow-500 h-1"
                                                            />
                                                        </div>

                                                        {/* Compact % */}
                                                        <div className="mb-1">
                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span className="flex items-center gap-1">
                                                                    <span className="w-2 h-2 rounded-full bg-teal-500"></span>
                                                                    Compact
                                                                </span>
                                                                <span className="text-teal-600">{massingParams.compactPct}%</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="0"
                                                                max="30"
                                                                value={massingParams.compactPct}
                                                                onChange={e => setMassingParams({ ...massingParams, compactPct: parseInt(e.target.value) })}
                                                                className="w-full accent-teal-500 h-1"
                                                            />
                                                        </div>

                                                        {/* ADA % */}
                                                        <div className="mb-1">
                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span className="flex items-center gap-1">
                                                                    <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                                                                    ADA ♿
                                                                </span>
                                                                <span className="text-blue-400">{massingParams.adaPct}%</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="2"
                                                                max="10"
                                                                value={massingParams.adaPct}
                                                                onChange={e => setMassingParams({ ...massingParams, adaPct: parseInt(e.target.value) })}
                                                                className="w-full accent-blue-500 h-1"
                                                            />
                                                        </div>

                                                        {/* EV % */}
                                                        <div className="mb-1">
                                                            <label className="text-xs text-slate-500 flex justify-between">
                                                                <span className="flex items-center gap-1">
                                                                    <span className="w-2 h-2 rounded-full bg-green-500"></span>
                                                                    EV ⚡
                                                                </span>
                                                                <span className="text-green-400">{massingParams.evPct}%</span>
                                                            </label>
                                                            <input
                                                                type="range"
                                                                min="0"
                                                                max="20"
                                                                value={massingParams.evPct}
                                                                onChange={e => setMassingParams({ ...massingParams, evPct: parseInt(e.target.value) })}
                                                                className="w-full accent-green-500 h-1"
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Reset button */}
                                            <button
                                                onClick={() => setMassingParams({ ...currentMassing.config })}
                                                className="w-full mt-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded text-xs text-slate-600 transition-colors"
                                            >
                                                ↺ Reset to Defaults
                                            </button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Site Info */}
                    <div className="mb-3 p-2.5 bg-slate-100 rounded-lg border border-slate-200/50">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5">
                                <span className="text-sm">📍</span>
                                <span className="text-xs text-slate-500">Site Area</span>
                            </div>
                            <div className="text-lg font-bold text-slate-900">{siteArea.toLocaleString()} <span className="text-[10px] text-slate-500 font-normal">SF</span></div>
                        </div>
                        <div className="text-[10px] text-slate-500 text-right">≈ {(siteArea / 43560).toFixed(2)} acres</div>
                    </div>

                    {/* Zoning */}
                    <div className="mb-3">
                        <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                            <span className="text-teal-600">▸</span> Zoning
                        </label>
                        <select
                            value={zoningPreset}
                            onChange={e => {
                                const key = e.target.value;
                                const preset = ZONING_PRESETS[key];
                                setZoningPreset(key);
                                if (preset) {
                                    setFar(preset.far);
                                    setHeightLimit(preset.height);
                                    setLotCoverage(preset.coverage);
                                    setParkingRatio(preset.parkingRatio);
                                }
                            }}
                            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all cursor-pointer"
                        >
                            {Object.entries(ZONING_PRESETS).map(([key, val]) => (
                                <option key={key} value={key}>{val.name}</option>
                            ))}
                        </select>
                    </div>

                    {/* FAR */}
                    <div className="mb-2">
                        <label className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>FAR</span>
                            <span className="text-teal-600 font-medium">{far}</span>
                        </label>
                        <input
                            type="range"
                            min="0.5"
                            max="10"
                            step="0.1"
                            value={far}
                            onChange={e => setFar(parseFloat(e.target.value) || 0)}
                            className="w-full accent-teal-500 h-1.5"
                        />
                    </div>

                    {/* Height */}
                    <div className="mb-2">
                        <label className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>Height</span>
                            <span className="text-teal-600 font-medium">{heightLimit} ft</span>
                        </label>
                        <input
                            type="range"
                            min="20"
                            max="500"
                            step="5"
                            value={heightLimit}
                            onChange={e => setHeightLimit(parseInt(e.target.value) || 0)}
                            className="w-full accent-teal-500 h-1.5"
                        />
                    </div>

                    {/* Lot Coverage */}
                    <div className="mb-2">
                        <label className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>Coverage</span>
                            <span className="text-teal-600 font-medium">{(lotCoverage * 100).toFixed(0)}%</span>
                        </label>
                        <input
                            type="range"
                            min="0.1"
                            max="1"
                            step="0.05"
                            value={lotCoverage}
                            onChange={e => setLotCoverage(parseFloat(e.target.value))}
                            className="w-full accent-teal-500 h-1.5"
                        />
                    </div>

                    {/* Parking Ratio */}
                    <div className="mb-3">
                        <label className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>🚗 Parking</span>
                            <span className="text-yellow-400 font-medium">{parkingRatio}/unit</span>
                        </label>
                        <input
                            type="range"
                            min="0"
                            max="3"
                            step="0.25"
                            value={parkingRatio}
                            onChange={e => setParkingRatio(parseFloat(e.target.value) || 0)}
                            className="w-full accent-yellow-500 h-1.5"
                        />
                    </div>

                    {/* Setbacks */}
                    <div className="mb-3">
                        <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 mb-1.5">
                            <span className="text-teal-600">▸</span> Setbacks
                        </label>
                        <select
                            value={setbackPreset}
                            onChange={e => setSetbackPreset(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all cursor-pointer mb-2"
                        >
                            {Object.entries(SETBACK_PRESETS).map(([key, val]) => (
                                <option key={key} value={key}>{val.name}</option>
                            ))}
                        </select>
                        <div className="grid grid-cols-3 gap-1.5">
                            <div>
                                <label className="text-[10px] text-slate-500 mb-0.5 block">Front</label>
                                <input
                                    type="number"
                                    value={setbacks.front}
                                    onChange={e => { setSetbacks({ ...setbacks, front: parseInt(e.target.value) || 0 }); setSetbackPreset('custom'); }}
                                    className="w-full bg-slate-50 border border-slate-200 rounded px-1.5 py-1 text-xs text-center focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 mb-0.5 block">Side</label>
                                <input
                                    type="number"
                                    value={setbacks.side}
                                    onChange={e => { setSetbacks({ ...setbacks, side: parseInt(e.target.value) || 0 }); setSetbackPreset('custom'); }}
                                    className="w-full bg-slate-50 border border-slate-200 rounded px-1.5 py-1 text-xs text-center focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                                />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 mb-0.5 block">Rear</label>
                                <input
                                    type="number"
                                    value={setbacks.rear}
                                    onChange={e => { setSetbacks({ ...setbacks, rear: parseInt(e.target.value) || 0 }); setSetbackPreset('custom'); }}
                                    className="w-full bg-slate-50 border border-slate-200 rounded px-1.5 py-1 text-xs text-center focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                                />
                            </div>
                        </div>
                    </div>

                    {/* Unit Mix Panel (Testfit-style) */}
                    {unitMix.length > 0 && (
                        <div className="mb-3">
                            <button
                                onClick={() => setShowUnitMixPanel(!showUnitMixPanel)}
                                className="w-full flex items-center justify-between px-2.5 py-2 bg-gradient-to-r from-slate-800 to-slate-800/80 hover:from-slate-700 hover:to-slate-700/80 rounded-lg text-xs font-medium transition-all border border-slate-200/50"
                            >
                                <span className="flex items-center gap-1.5">
                                    <span>📊</span>
                                    <span>{buildingType === 'hotel' ? 'Rooms' : buildingType === 'retail' ? 'Tenants' : 'Unit Mix'}</span>
                                </span>
                                <span className="text-slate-500 text-[10px]">{showUnitMixPanel ? '▼' : '▶'}</span>
                            </button>

                            {showUnitMixPanel && (
                                <div className="mt-1.5 p-2 bg-white rounded border border-slate-200">
                                    <div className="space-y-3">
                                        {unitMix.map((unit, idx) => (
                                            <div key={unit.id} className="pb-3 border-b border-slate-200 last:border-0 last:pb-0">
                                                <div className="flex items-center justify-between mb-2">
                                                    <div className="flex items-center gap-2">
                                                        <div
                                                            className="w-3 h-3 rounded-full"
                                                            style={{ backgroundColor: unit.color }}
                                                        />
                                                        <span className="text-sm font-medium text-slate-700">{unit.name}</span>
                                                    </div>
                                                    <span className="text-sm font-bold text-teal-600">{unit.targetPct}%</span>
                                                </div>

                                                {/* Target Percentage Slider */}
                                                <div className="mb-2">
                                                    <input
                                                        type="range"
                                                        min="0"
                                                        max="100"
                                                        value={unit.targetPct}
                                                        onChange={e => {
                                                            const newMix = [...unitMix];
                                                            newMix[idx].targetPct = parseInt(e.target.value);
                                                            setUnitMix(newMix);
                                                        }}
                                                        className="w-full accent-teal-500 h-1"
                                                    />
                                                </div>

                                                {/* Unit Details */}
                                                <div className="grid grid-cols-2 gap-2 text-xs">
                                                    {/* SF */}
                                                    {unit.sf !== undefined && (
                                                        <div>
                                                            <label className="text-slate-500">SF</label>
                                                            <input
                                                                type="number"
                                                                value={unit.sf}
                                                                onChange={e => {
                                                                    const newMix = [...unitMix];
                                                                    newMix[idx].sf = parseInt(e.target.value) || 0;
                                                                    setUnitMix(newMix);
                                                                }}
                                                                className="w-full bg-slate-100 rounded px-2 py-1"
                                                            />
                                                        </div>
                                                    )}
                                                    {/* Bedrooms (multifamily/singlefamily) */}
                                                    {unit.bedrooms !== undefined && (
                                                        <div>
                                                            <label className="text-slate-500">Beds</label>
                                                            <input
                                                                type="number"
                                                                value={unit.bedrooms}
                                                                onChange={e => {
                                                                    const newMix = [...unitMix];
                                                                    newMix[idx].bedrooms = parseInt(e.target.value) || 0;
                                                                    setUnitMix(newMix);
                                                                }}
                                                                className="w-full bg-slate-100 rounded px-2 py-1"
                                                            />
                                                        </div>
                                                    )}
                                                    {/* Rent PSF (multifamily) */}
                                                    {unit.rentPSF !== undefined && (
                                                        <div>
                                                            <label className="text-slate-500">Rent/SF</label>
                                                            <input
                                                                type="number"
                                                                step="0.05"
                                                                value={unit.rentPSF}
                                                                onChange={e => {
                                                                    const newMix = [...unitMix];
                                                                    newMix[idx].rentPSF = parseFloat(e.target.value) || 0;
                                                                    setUnitMix(newMix);
                                                                }}
                                                                className="w-full bg-slate-100 rounded px-2 py-1"
                                                            />
                                                        </div>
                                                    )}
                                                    {/* Rent per Night (hotel) */}
                                                    {unit.rentPerNight !== undefined && (
                                                        <div>
                                                            <label className="text-slate-500">$/Night</label>
                                                            <input
                                                                type="number"
                                                                value={unit.rentPerNight}
                                                                onChange={e => {
                                                                    const newMix = [...unitMix];
                                                                    newMix[idx].rentPerNight = parseInt(e.target.value) || 0;
                                                                    setUnitMix(newMix);
                                                                }}
                                                                className="w-full bg-slate-100 rounded px-2 py-1"
                                                            />
                                                        </div>
                                                    )}
                                                    {/* Price (singlefamily) */}
                                                    {unit.price !== undefined && (
                                                        <div>
                                                            <label className="text-slate-500">Price</label>
                                                            <input
                                                                type="number"
                                                                step="10000"
                                                                value={unit.price}
                                                                onChange={e => {
                                                                    const newMix = [...unitMix];
                                                                    newMix[idx].price = parseInt(e.target.value) || 0;
                                                                    setUnitMix(newMix);
                                                                }}
                                                                className="w-full bg-slate-100 rounded px-2 py-1"
                                                            />
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ))}

                                        {/* Total check */}
                                        <div className="pt-2 border-t border-slate-300">
                                            <div className="flex justify-between text-sm">
                                                <span className="text-slate-500">Total Mix:</span>
                                                <span className={`font-bold ${unitMix.reduce((sum, u) => sum + u.targetPct, 0) === 100 ? 'text-green-400' : 'text-yellow-400'}`}>
                                                    {unitMix.reduce((sum, u) => sum + u.targetPct, 0)}%
                                                </span>
                                            </div>
                                            {unitMix.reduce((sum, u) => sum + u.targetPct, 0) !== 100 && (
                                                <p className="text-xs text-yellow-400 mt-1">⚠️ Mix should total 100%</p>
                                            )}
                                        </div>

                                        {/* Reset button */}
                                        <button
                                            onClick={() => {
                                                const defaultMix = DEFAULT_UNIT_MIX[buildingType];
                                                if (defaultMix) setUnitMix(JSON.parse(JSON.stringify(defaultMix)));
                                            }}
                                            className="w-full mt-3 px-3 py-2 bg-slate-100 hover:bg-slate-200 rounded-lg text-xs text-slate-600 transition-all border border-slate-300/50 hover:border-slate-500"
                                        >
                                            ↺ Reset to Defaults
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Results Summary */}
                    {results && results.summary && (
                        <div className="mt-5 p-4 bg-gradient-to-br from-green-900/30 to-slate-900 rounded-xl border border-green-500/30 shadow-lg">
                            <h3 className="font-bold text-green-400 mb-3 flex items-center gap-2 text-sm">
                                <span className="text-lg">{currentBuildingType?.icon}</span>
                                <span>{currentBuildingType?.name} Results</span>
                                <span className="ml-auto text-green-500">✓</span>
                            </h3>
                            <div className="space-y-2 text-sm">
                                {/* Dynamic primary metric based on building type */}
                                {buildingType === 'multifamily' && (
                                    <div className="flex justify-between items-center p-2 bg-slate-50/50 rounded-lg">
                                        <span className="text-slate-500">Units:</span>
                                        <span className="font-bold text-xl text-green-400">{results.summary.max_units}</span>
                                    </div>
                                )}
                                {buildingType === 'singlefamily' && (
                                    <div className="flex justify-between items-center p-2 bg-slate-50/50 rounded-lg">
                                        <span className="text-slate-500">Lots:</span>
                                        <span className="font-bold text-xl text-green-400">{Math.floor(siteArea / (currentSubtype?.lotSize || 5000))}</span>
                                    </div>
                                )}
                                {buildingType === 'hotel' && (
                                    <div className="flex justify-between items-center p-2 bg-slate-50/50 rounded-lg">
                                        <span className="text-slate-500">Rooms:</span>
                                        <span className="font-bold text-xl text-green-400">
                                            {Math.floor(results.summary.building_sf * (currentSubtype?.efficiency || 0.65) / (currentSubtype?.roomSize || 350))}
                                        </span>
                                    </div>
                                )}
                                {buildingType === 'industrial' && (
                                    <div className="flex justify-between items-center p-2 bg-slate-50/50 rounded-lg">
                                        <span className="text-slate-500">Warehouse SF:</span>
                                        <span className="font-bold text-xl text-green-400">{results.summary.building_sf?.toLocaleString()}</span>
                                    </div>
                                )}
                                {buildingType === 'retail' && (
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">Leasable SF:</span>
                                        <span className="font-medium text-lg text-green-400">{results.summary.building_sf?.toLocaleString()}</span>
                                    </div>
                                )}
                                {buildingType === 'datacenter' && (
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">IT Load (MW):</span>
                                        <span className="font-medium text-lg text-green-400">
                                            {((results.summary.building_sf * (currentSubtype?.powerDensity || 100)) / 1000000).toFixed(1)}
                                        </span>
                                    </div>
                                )}
                                {buildingType === 'parking' && (
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">Parking Stalls:</span>
                                        <span className="font-medium text-lg text-green-400">
                                            {currentSubtype?.stallsPerAcre
                                                ? Math.floor(siteArea / 43560 * currentSubtype.stallsPerAcre)
                                                : Math.floor(results.summary.building_sf * (currentSubtype?.stallsPerSF || 0.003))
                                            }
                                        </span>
                                    </div>
                                )}

                                <div className="border-t border-slate-200 my-2 pt-2"></div>

                                <div className="flex justify-between">
                                    <span className="text-slate-500">Building SF:</span>
                                    <span className="font-medium">{results.summary.building_sf?.toLocaleString()}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Floors:</span>
                                    <span className="font-medium">{results.summary.floors}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Parking Required:</span>
                                    <span className="font-medium">{Math.ceil(results.summary.max_units * parkingRatio)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Efficiency:</span>
                                    <span className="font-medium">{(results.summary.efficiency * 100).toFixed(1)}%</span>
                                </div>

                                {/* Unit Mix Breakdown */}
                                {unitMix.length > 0 && results.summary.max_units > 0 && (buildingType === 'multifamily' || buildingType === 'singlefamily') && (
                                    <>
                                        <div className="border-t border-slate-200 my-2 pt-2">
                                            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Unit Breakdown</span>
                                        </div>
                                        {unitMix.map(unit => {
                                            const unitCount = Math.round(results.summary.max_units * (unit.targetPct / 100));
                                            const totalRent = unit.rentPSF ? (unitCount * unit.sf * unit.rentPSF) : (unitCount * (unit.price || 0));
                                            return (
                                                <div key={unit.id} className="flex justify-between items-center">
                                                    <span className="flex items-center gap-1.5 text-slate-500">
                                                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: unit.color }}></span>
                                                        {unit.name}
                                                    </span>
                                                    <span className="font-medium">{unitCount}</span>
                                                </div>
                                            );
                                        })}
                                        <div className="flex justify-between text-xs mt-1">
                                            <span className="text-slate-500">Avg Unit Size:</span>
                                            <span className="text-slate-500">
                                                {Math.round(unitMix.reduce((sum, u) => sum + u.sf * (u.targetPct / 100), 0))} SF
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-xs">
                                            <span className="text-slate-500">Total Bedrooms:</span>
                                            <span className="text-slate-500">
                                                {Math.round(unitMix.reduce((sum, u) => {
                                                    const count = results.summary.max_units * (u.targetPct / 100);
                                                    return sum + count * (u.bedrooms || 0);
                                                }, 0))}
                                            </span>
                                        </div>
                                        {buildingType === 'multifamily' && unitMix[0]?.rentPSF && (
                                            <div className="flex justify-between text-xs font-medium text-green-400 mt-1">
                                                <span>Monthly Rent:</span>
                                                <span>
                                                    ${Math.round(unitMix.reduce((sum, u) => {
                                                        const count = results.summary.max_units * (u.targetPct / 100);
                                                        return sum + count * u.sf * u.rentPSF;
                                                    }, 0)).toLocaleString()}
                                                </span>
                                            </div>
                                        )}
                                    </>
                                )}

                                {/* Room Mix Breakdown (Hotel) */}
                                {unitMix.length > 0 && buildingType === 'hotel' && (
                                    <>
                                        <div className="border-t border-slate-200 my-2 pt-2">
                                            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Room Breakdown</span>
                                        </div>
                                        {(() => {
                                            const totalRooms = Math.floor(results.summary.building_sf * (currentSubtype?.efficiency || 0.65) / (currentSubtype?.roomSize || 350));
                                            return unitMix.map(room => {
                                                const roomCount = Math.round(totalRooms * (room.targetPct / 100));
                                                return (
                                                    <div key={room.id} className="flex justify-between items-center">
                                                        <span className="flex items-center gap-1.5 text-slate-500">
                                                            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: room.color }}></span>
                                                            {room.name}
                                                        </span>
                                                        <span className="font-medium">{roomCount}</span>
                                                    </div>
                                                );
                                            });
                                        })()}
                                        {(() => {
                                            const totalRooms = Math.floor(results.summary.building_sf * (currentSubtype?.efficiency || 0.65) / (currentSubtype?.roomSize || 350));
                                            const avgRate = unitMix.reduce((sum, r) => sum + r.rentPerNight * (r.targetPct / 100), 0);
                                            return (
                                                <div className="flex justify-between text-xs font-medium text-green-400 mt-1">
                                                    <span>RevPAR Potential:</span>
                                                    <span>${Math.round(avgRate * 0.7).toLocaleString()}/night</span>
                                                </div>
                                            );
                                        })()}
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Canvas / 3D Viewer */}
                <div className="flex-1 flex flex-col overflow-hidden min-w-0 relative">
                    {/* Sidebar Toggle Button */}
                    <button
                        onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                        className="absolute top-2 left-2 z-30 w-8 h-8 bg-white/90 backdrop-blur border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 flex items-center justify-center text-slate-600 hover:text-slate-900 transition-all"
                        title={sidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
                    >
                        {sidebarCollapsed ? '☰' : '✕'}
                    </button>

                    {error && (
                        <div className="absolute top-4 left-4 right-4 z-20 p-2 bg-red-100 border border-red-300 rounded-lg text-red-700 text-xs flex items-center gap-2">
                            <span className="text-red-500">⚠️</span>
                            <span>{error}</span>
                        </div>
                    )}

                    {/* Show 2D Canvas for drawing or when in 2D mode */}
                    {(viewMode === '2d' || boundary.length < 3 || isDrawing) && (
                        <div ref={canvasContainerRef} className="absolute inset-0 overflow-hidden">
                            <canvas
                                ref={canvasRef}
                                width={canvasSize.width}
                                height={canvasSize.height}
                                onClick={(e) => {
                                    // Close context menu on any click
                                    if (aisleContextMenu) {
                                        setAisleContextMenu(null);
                                        return;
                                    }
                                    handleCanvasClick(e);
                                }}
                                onMouseDown={handleCanvasMouseDown}
                                onMouseMove={handleCanvasMouseMove}
                                onMouseUp={handleCanvasMouseUp}
                                onMouseLeave={handleCanvasMouseUp}
                                onDoubleClick={handleCanvasDoubleClick}
                                onContextMenu={(e) => {
                                    e.preventDefault();
                                    // Handle right-click in aisle editing mode
                                    if (isEditingAisles && drawnAisles.length > 0) {
                                        const canvas = canvasRef.current;
                                        const rect = canvas.getBoundingClientRect();
                                        const mouseX = e.clientX - rect.left;
                                        const mouseY = e.clientY - rect.top;
                                        const canvasCoords = screenToCanvas(mouseX, mouseY);
                                        const clickX = canvasCoords.x / SCALE;
                                        const clickY = canvasCoords.y / SCALE;

                                        // Build junctions
                                        const junctions = buildAisleJunctions(drawnAisles, 15);
                                        const hitRadiusFeet = Math.max(8, 20 / (SCALE * canvasZoom));

                                        // Find if we're clicking on a point
                                        const hitPoint = findAislePointAtPosition(clickX, clickY, drawnAisles, junctions, hitRadiusFeet);

                                        if (hitPoint) {
                                            // Right-click on existing point - show delete menu
                                            setAisleContextMenu({
                                                screenX: e.clientX,
                                                screenY: e.clientY,
                                                x: clickX,
                                                y: clickY,
                                                type: 'delete',
                                                hitPoint,
                                                junctions
                                            });
                                        } else {
                                            // Right-click on empty space - check if near a segment to add point
                                            const closestSegment = findClosestAisleSegment(clickX, clickY, drawnAisles, 20);
                                            if (closestSegment) {
                                                setAisleContextMenu({
                                                    screenX: e.clientX,
                                                    screenY: e.clientY,
                                                    x: closestSegment.x,
                                                    y: closestSegment.y,
                                                    type: 'add',
                                                    segment: closestSegment
                                                });
                                            }
                                        }
                                    }
                                }}
                                className={`bg-slate-100 ${isPanning ? 'cursor-grabbing' : editMode === 'pan' ? 'cursor-grab' : editMode === 'select' ? 'cursor-default' : isEditingBoundary ? 'cursor-default' : 'cursor-crosshair'}`}
                                style={{ width: canvasSize.width, height: canvasSize.height }}
                            />

                            {/* Coordinate display overlay (Rhino-like) */}
                            {coordDisplay2D && (
                                <div
                                    className="absolute pointer-events-none z-50"
                                    style={{
                                        left: coordDisplay2D.screenX,
                                        top: coordDisplay2D.screenY,
                                        transform: 'translate(0, -100%)'
                                    }}
                                >
                                    <div className={`px-2 py-1 rounded text-xs font-mono shadow-lg ${coordDisplay2D.ortho
                                        ? 'bg-cyan-600 text-white'
                                        : 'bg-gray-900 text-white'
                                        }`}>
                                        <span className="text-cyan-300">X:</span> {coordDisplay2D.x}′
                                        <span className="mx-1">|</span>
                                        <span className="text-green-300">Y:</span> {coordDisplay2D.y}′
                                        {coordDisplay2D.ortho && (
                                            <span className="ml-2 text-yellow-300">[ORTHO]</span>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Aisle Edit Context Menu */}
                            {aisleContextMenu && (
                                <div
                                    className="fixed z-[100] bg-white rounded-lg shadow-xl border border-gray-200 py-1 min-w-[160px]"
                                    style={{
                                        left: aisleContextMenu.screenX,
                                        top: aisleContextMenu.screenY,
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    {aisleContextMenu.type === 'add' ? (
                                        <button
                                            className="w-full px-4 py-2 text-left text-sm hover:bg-blue-50 flex items-center gap-2"
                                            onClick={() => {
                                                // Add point to segment
                                                const { aisleId, segmentIndex, x, y } = aisleContextMenu.segment;
                                                setAisleEditHistory(prev => [...prev, JSON.parse(JSON.stringify(drawnAisles))]);
                                                setDrawnAisles(prev => prev.map(aisle => {
                                                    if (aisle.id !== aisleId) return aisle;
                                                    const newPoints = [...aisle.points];
                                                    newPoints.splice(segmentIndex + 1, 0, { x, y });
                                                    return { ...aisle, points: newPoints };
                                                }));
                                                setAisleContextMenu(null);
                                            }}
                                        >
                                            <span className="text-green-500">⊕</span>
                                            Add Point Here
                                        </button>
                                    ) : (
                                        <button
                                            className="w-full px-4 py-2 text-left text-sm hover:bg-red-50 flex items-center gap-2 text-red-600"
                                            onClick={() => {
                                                const { hitPoint, junctions } = aisleContextMenu;
                                                setAisleEditHistory(prev => [...prev, JSON.parse(JSON.stringify(drawnAisles))]);

                                                if (hitPoint.type === 'junction') {
                                                    const junction = junctions.find(j => j.id === hitPoint.junctionId);
                                                    if (junction) {
                                                        setDrawnAisles(prev => {
                                                            let updated = [...prev];
                                                            // Sort connections by pointIndex descending to avoid index shift issues
                                                            const sortedConns = [...junction.connections].sort((a, b) => b.pointIndex - a.pointIndex);
                                                            sortedConns.forEach(conn => {
                                                                const aisleIdx = updated.findIndex(a => a.id === conn.aisleId);
                                                                if (aisleIdx >= 0) {
                                                                    const newPoints = updated[aisleIdx].points.filter((_, idx) => idx !== conn.pointIndex);
                                                                    if (newPoints.length < 2) {
                                                                        updated = updated.filter(a => a.id !== conn.aisleId);
                                                                    } else {
                                                                        updated[aisleIdx] = { ...updated[aisleIdx], points: newPoints };
                                                                    }
                                                                }
                                                            });
                                                            return updated;
                                                        });
                                                    }
                                                } else {
                                                    setDrawnAisles(prev => {
                                                        return prev.map(aisle => {
                                                            if (aisle.id !== hitPoint.aisleId) return aisle;
                                                            const newPoints = aisle.points.filter((_, idx) => idx !== hitPoint.pointIndex);
                                                            return { ...aisle, points: newPoints };
                                                        }).filter(aisle => aisle.points.length >= 2);
                                                    });
                                                }
                                                setHoveredAislePoint(null);
                                                setAisleContextMenu(null);
                                            }}
                                        >
                                            <span>✕</span>
                                            Delete Point
                                        </button>
                                    )}
                                </div>
                            )}

                            {/* Precision input dialog (2D) */}
                            {editingVertex2D && (
                                <div className="absolute inset-0 flex items-center justify-center bg-black/30 z-50">
                                    <div className="bg-white rounded-lg shadow-xl p-4 min-w-[280px]">
                                        <h3 className="text-sm font-semibold text-gray-700 mb-3">
                                            Edit Vertex {editingVertex2D.index + 1} Position
                                        </h3>
                                        <div className="flex gap-3 mb-4">
                                            <div>
                                                <label className="block text-xs text-gray-500 mb-1">X (feet)</label>
                                                <input
                                                    type="number"
                                                    className="w-24 px-2 py-1 border rounded text-sm font-mono"
                                                    defaultValue={editingVertex2D.x}
                                                    id="vertex-x-input-2d"
                                                    autoFocus
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') {
                                                            const xInput = document.getElementById('vertex-x-input-2d');
                                                            const yInput = document.getElementById('vertex-y-input-2d');
                                                            if (xInput && yInput) {
                                                                handleUpdateBoundaryVertex(
                                                                    editingVertex2D.index,
                                                                    parseInt(xInput.value, 10) || 0,
                                                                    parseInt(yInput.value, 10) || 0
                                                                );
                                                            }
                                                            setEditingVertex2D(null);
                                                        } else if (e.key === 'Escape') {
                                                            setEditingVertex2D(null);
                                                        }
                                                    }}
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs text-gray-500 mb-1">Y (feet)</label>
                                                <input
                                                    type="number"
                                                    className="w-24 px-2 py-1 border rounded text-sm font-mono"
                                                    defaultValue={editingVertex2D.y}
                                                    id="vertex-y-input-2d"
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Enter') {
                                                            const xInput = document.getElementById('vertex-x-input-2d');
                                                            const yInput = document.getElementById('vertex-y-input-2d');
                                                            if (xInput && yInput) {
                                                                handleUpdateBoundaryVertex(
                                                                    editingVertex2D.index,
                                                                    parseInt(xInput.value, 10) || 0,
                                                                    parseInt(yInput.value, 10) || 0
                                                                );
                                                            }
                                                            setEditingVertex2D(null);
                                                        } else if (e.key === 'Escape') {
                                                            setEditingVertex2D(null);
                                                        }
                                                    }}
                                                />
                                            </div>
                                        </div>
                                        <div className="flex gap-2 justify-end">
                                            <button
                                                className="px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded"
                                                onClick={() => setEditingVertex2D(null)}
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                className="px-3 py-1 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-700"
                                                onClick={() => {
                                                    const xInput = document.getElementById('vertex-x-input-2d');
                                                    const yInput = document.getElementById('vertex-y-input-2d');
                                                    if (xInput && yInput) {
                                                        handleUpdateBoundaryVertex(
                                                            editingVertex2D.index,
                                                            parseInt(xInput.value, 10) || 0,
                                                            parseInt(yInput.value, 10) || 0
                                                        );
                                                    }
                                                    setEditingVertex2D(null);
                                                }}
                                            >
                                                Apply
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Floating Buildings Panel (2D) - Collapsible */}
                            {viewMode === '2d' && boundary.length >= 3 && !isDrawing && templateBuildingsList.length > 0 && (
                                <div className={`absolute bottom-12 right-2 bg-white/95 backdrop-blur border border-slate-200 rounded-lg shadow-lg transition-all duration-200 ${buildingsPanelCollapsed ? 'w-auto' : 'w-56'}`}>
                                    {/* Header with collapse toggle */}
                                    <div
                                        className="flex items-center justify-between px-2 py-1.5 cursor-pointer hover:bg-slate-50 rounded-t-lg border-b border-slate-100"
                                        onClick={() => setBuildingsPanelCollapsed(!buildingsPanelCollapsed)}
                                    >
                                        <h4 className="text-[10px] font-bold text-slate-700 flex items-center gap-1">
                                            <span>🏢</span> {buildingsPanelCollapsed ? templateBuildingsList.length : `Buildings (${templateBuildingsList.length})`}
                                        </h4>
                                        <span className="text-slate-400 text-xs">{buildingsPanelCollapsed ? '◀' : '▼'}</span>
                                    </div>

                                    {/* Collapsible content */}
                                    {!buildingsPanelCollapsed && (
                                        <div className="p-2 max-h-40 overflow-y-auto">
                                            {/* Apply to All - compact row */}
                                            {['multifamily', 'hotel', 'singlefamily', 'datacenter', 'parking'].includes(buildingType) && (
                                                <div className="flex items-center gap-1 mb-2 pb-2 border-b border-slate-100">
                                                    <span className="text-[10px] text-slate-500">All:</span>
                                                    <input
                                                        type="number"
                                                        min={buildingType === 'singlefamily' ? 1 : buildingType === 'datacenter' ? 1 : 2}
                                                        max={buildingType === 'singlefamily' ? 3 : buildingType === 'datacenter' ? 4 : buildingType === 'hotel' ? 30 : 10}
                                                        value={effectiveMassingConfig.floors || currentSubtype?.floors || 3}
                                                        onChange={e => {
                                                            const newFloors = parseInt(e.target.value) || 3;
                                                            const newParams = {};
                                                            templateBuildingsList.forEach((_, idx) => {
                                                                newParams[idx] = { floors: newFloors };
                                                            });
                                                            setIndividualBuildingParams(newParams);
                                                            setMassingParams(prev => ({ ...prev, floors: newFloors }));
                                                        }}
                                                        className="w-12 bg-slate-100 rounded px-1 py-0.5 text-xs text-center"
                                                    />
                                                    <span className="text-[10px] text-slate-400">floors</span>
                                                </div>
                                            )}
                                            {/* Apply to All - Clear Height (industrial) */}
                                            {buildingType === 'industrial' && (
                                                <div className="flex items-center gap-1 mb-2 pb-2 border-b border-slate-100">
                                                    <span className="text-[10px] text-slate-500">All:</span>
                                                    <input
                                                        type="number"
                                                        min="20"
                                                        max="60"
                                                        step="4"
                                                        value={effectiveMassingConfig.clearHeight || 36}
                                                        onChange={e => {
                                                            const newHeight = parseInt(e.target.value) || 36;
                                                            const newParams = {};
                                                            templateBuildingsList.forEach((_, idx) => {
                                                                newParams[idx] = { clearHeight: newHeight };
                                                            });
                                                            setIndividualBuildingParams(newParams);
                                                            setMassingParams(prev => ({ ...prev, clearHeight: newHeight }));
                                                        }}
                                                        className="w-12 bg-slate-100 rounded px-1 py-0.5 text-xs text-center"
                                                    />
                                                    <span className="text-[10px] text-slate-400">ft</span>
                                                </div>
                                            )}
                                            {/* Apply to All - Floor Height (retail) */}
                                            {buildingType === 'retail' && (
                                                <div className="flex items-center gap-1 mb-2 pb-2 border-b border-slate-100">
                                                    <span className="text-[10px] text-slate-500">All:</span>
                                                    <input
                                                        type="number"
                                                        min="14"
                                                        max="30"
                                                        step="2"
                                                        value={effectiveMassingConfig.floorHeight || 18}
                                                        onChange={e => {
                                                            const newHeight = parseInt(e.target.value) || 18;
                                                            const newParams = {};
                                                            templateBuildingsList.forEach((_, idx) => {
                                                                newParams[idx] = { floorHeight: newHeight };
                                                            });
                                                            setIndividualBuildingParams(newParams);
                                                            setMassingParams(prev => ({ ...prev, floorHeight: newHeight }));
                                                        }}
                                                        className="w-12 bg-slate-100 rounded px-1 py-0.5 text-xs text-center"
                                                    />
                                                    <span className="text-[10px] text-slate-400">ft</span>
                                                </div>
                                            )}

                                            {/* Compact Buildings List */}
                                            <div className="space-y-1">
                                                {templateBuildingsList.map((building, idx) => {
                                                    const isSelected = selectedTemplateBuilding === idx;
                                                    const currentFloors = individualBuildingParams[idx]?.floors ?? (effectiveMassingConfig.floors || currentSubtype?.floors || 3);
                                                    const currentHeight = individualBuildingParams[idx]?.clearHeight ?? (effectiveMassingConfig.clearHeight || 36);
                                                    const currentFloorHeight = individualBuildingParams[idx]?.floorHeight ?? (effectiveMassingConfig.floorHeight || 18);
                                                    const currentStartLevel = individualBuildingParams[idx]?.startLevel ?? 0;

                                                    const useFloors = ['multifamily', 'hotel', 'singlefamily', 'datacenter', 'parking'].includes(buildingType);
                                                    const useClearHeight = buildingType === 'industrial';
                                                    const useFloorHeight = buildingType === 'retail';

                                                    const getFloorLimits = () => {
                                                        switch (buildingType) {
                                                            case 'singlefamily': return { min: 1, max: 3 };
                                                            case 'datacenter': return { min: 1, max: 4 };
                                                            case 'parking': return { min: 2, max: 10 };
                                                            case 'hotel': return { min: 2, max: 30 };
                                                            default: return { min: 2, max: 10 };
                                                        }
                                                    };
                                                    const floorLimits = getFloorLimits();

                                                    return (
                                                        <div
                                                            key={idx}
                                                            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${isSelected
                                                                ? 'bg-orange-50 border border-orange-300'
                                                                : 'bg-slate-50 hover:bg-slate-100 border border-transparent'
                                                                }`}
                                                            onClick={() => handleSelectTemplateBuilding(idx)}
                                                        >
                                                            {/* Building number */}
                                                            <div className={`w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center ${isSelected ? 'bg-orange-100 text-orange-700' : 'bg-slate-200 text-slate-500'}`}>
                                                                {idx + 1}
                                                            </div>

                                                            {/* Start Level */}
                                                            <div className="flex items-center gap-0.5">
                                                                <span className="text-[9px] text-slate-400">L</span>
                                                                <button onClick={(e) => { e.stopPropagation(); if (currentStartLevel > 0) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), startLevel: currentStartLevel - 1 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">−</button>
                                                                <span className="w-4 text-center text-[10px] font-medium">{currentStartLevel}</span>
                                                                <button onClick={(e) => { e.stopPropagation(); if (currentStartLevel < 20) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), startLevel: currentStartLevel + 1 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">+</button>
                                                            </div>

                                                            {/* Floors/Height controls */}
                                                            {useFloors && (
                                                                <div className="flex items-center gap-0.5 ml-auto">
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentFloors > floorLimits.min) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), floors: currentFloors - 1 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-orange-100 rounded text-[10px]">−</button>
                                                                    <span className={`w-5 text-center text-[10px] font-bold ${isSelected ? 'text-orange-600' : ''}`}>{currentFloors}F</span>
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentFloors < floorLimits.max) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), floors: currentFloors + 1 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-orange-100 rounded text-[10px]">+</button>
                                                                </div>
                                                            )}
                                                            {useClearHeight && (
                                                                <div className="flex items-center gap-0.5 ml-auto">
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentHeight > 20) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), clearHeight: currentHeight - 4 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">−</button>
                                                                    <span className={`w-6 text-center text-[10px] font-bold ${isSelected ? 'text-orange-600' : ''}`}>{currentHeight}&apos;</span>
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentHeight < 60) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), clearHeight: currentHeight + 4 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">+</button>
                                                                </div>
                                                            )}
                                                            {useFloorHeight && (
                                                                <div className="flex items-center gap-0.5 ml-auto">
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentFloorHeight > 14) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), floorHeight: currentFloorHeight - 2 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">−</button>
                                                                    <span className={`w-6 text-center text-[10px] font-bold ${isSelected ? 'text-orange-600' : ''}`}>{currentFloorHeight}&apos;</span>
                                                                    <button onClick={(e) => { e.stopPropagation(); if (currentFloorHeight < 30) setIndividualBuildingParams(prev => ({ ...prev, [idx]: { ...(prev[idx] || {}), floorHeight: currentFloorHeight + 2 } })); }} className="w-4 h-4 bg-slate-100 hover:bg-slate-200 rounded text-[10px]">+</button>
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* 3D viewer - always mounted when boundary is valid to preserve camera state, hidden when in 2D mode */}
                    {boundary.length >= 3 && !isDrawing && (
                        <div
                            className="absolute inset-0 overflow-hidden bg-slate-100"
                            style={{ display: viewMode === '3d' ? 'block' : 'none' }}
                        >
                            <SiteGen3DViewer
                                ref={viewer3DRef}
                                boundary={boundary}
                                exclusions={exclusions}
                                buildingType={buildingType}
                                massingType={massingType}
                                massingConfig={effectiveMassingConfig}
                                parkingLayout={parkingLayout}
                                setbacks={setbacks}
                                lotCoverage={lotCoverage}
                                heightLimit={heightLimit}
                                onParamChange={(key, value) => setMassingParams(prev => ({ ...prev, [key]: Math.round(value) }))}
                                individualBuildingParams={individualBuildingParams}
                                onIndividualBuildingParamChange={(buildingIndex, key, value) => {
                                    setIndividualBuildingParams(prev => ({
                                        ...prev,
                                        [buildingIndex]: {
                                            ...(prev[buildingIndex] || {}),
                                            [key]: Math.round(value)
                                        }
                                    }));
                                }}
                                templateBuildingPositions={templateBuildingPositions}
                                selectedTemplateBuilding={selectedTemplateBuilding}
                                onSelectTemplateBuilding={handleSelectTemplateBuilding}
                                onMoveTemplateBuilding={handleMoveTemplateBuilding}
                                amenityPositions={amenityPositions}
                                selectedAmenity={selectedAmenity}
                                onSelectAmenity={setSelectedAmenity}
                                onMoveAmenity={handleMoveAmenity}
                                customBuildings={customBuildings}
                                selectedBuildingId={selectedBuildingId}
                                isDrawingShape={isDrawingShape}
                                newBuildingConfig={newBuildingConfig}
                                polygonBuildingConfig={polygonBuildingConfig}
                                onAddBuilding={handleAddBuilding}
                                onDeleteBuilding={handleDeleteBuilding}
                                onSelectBuilding={handleSelectBuilding}
                                onMoveBuilding={handleMoveBuilding}
                                drawingPolygon={drawingPolygon}
                                onAddPolygonPoint={handleAddPolygonPoint}
                                onFinishPolygon={handleFinishPolygon}
                                onStartDrawing={handleStartDrawing}
                                onUpdateVertex={handleUpdateVertex}
                                isEditingBoundary={isEditingBoundary}
                                onUpdateBoundaryVertex={handleUpdateBoundaryVertex}
                                onAddBoundaryVertex={handleAddBoundaryVertex}
                                onDeleteBoundaryVertex={handleDeleteBoundaryVertex}
                                snapEnabled={snapEnabled}
                                snapToGrid={snapToGrid}
                                gridSize={gridSize}
                                onZoomChange={setZoom3DLevel}
                                vehicles={vehicles}
                                selectedVehicle={selectedVehicle}
                                vehicleTrailsVisible={vehicleTrailsVisible}
                                vehicleTurningRadiusVisible={vehicleTurningRadiusVisible}
                                showVehiclePanel={showVehiclePanel}
                                vehicleSpeed={vehicleSpeed}
                                onSelectVehicle={setSelectedVehicle}
                                onShowVehiclePanel={() => setShowVehiclePanel(true)}
                                onMoveVehicle={moveVehicle}
                                onSteerVehicle={steerVehicle}
                                onRotateVehicle={rotateVehicle}
                                onClearAllTrails={clearAllTrails}
                            />
                        </div>
                    )}

                    {/* === FLOATING PARKING CANVAS TOOLBAR (Rhino-style) === */}
                    {/* Placed outside both 2D and 3D containers so it appears in both views */}
                    {buildingType === 'parking' && massingType === 'surface' && boundary.length >= 3 && !isDrawing && (
                        <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-40">
                            <div className="bg-white/95 backdrop-blur-sm rounded-xl shadow-lg border border-slate-200 px-3 py-2 flex items-center gap-2">
                                {/* Mode indicator */}
                                <div className="flex items-center gap-1.5 pr-3 border-r border-slate-200">
                                    <span className="text-xs text-slate-500">Mode:</span>
                                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${isDrawingAisle ? 'bg-orange-100 text-orange-700' :
                                        isEditingAisles ? 'bg-purple-100 text-purple-700' :
                                            isPlacingSpine ? 'bg-indigo-100 text-indigo-700' :
                                                'bg-slate-100 text-slate-600'
                                        }`}>
                                        {isDrawingAisle ? '✏️ Draw' :
                                            isEditingAisles ? '✎ Edit' :
                                                isPlacingSpine ? '📍 Spine' :
                                                    '👆 Select'}
                                    </span>
                                </div>

                                {/* Capture Layout (only if no custom aisles) */}
                                {drawnAisles.length === 0 && parkingLayoutRef.current && !isDrawingAisle && !isEditingAisles && (
                                    <button
                                        onClick={() => {
                                            const layout = parkingLayoutRef.current;
                                            if (!layout || !layout.loopOuter) return;
                                            const newAisles = [];
                                            const loop = layout.loopOuter;
                                            const loopW = layout.loopWidth || 24;

                                            // Calculate interior bounds (inside the perimeter loop)
                                            const innerX = loop.x + loopW;
                                            const innerY = loop.y + loopW;
                                            const innerW = loop.w - loopW * 2;
                                            const innerH = loop.h - loopW * 2;

                                            // Create perimeter loop as 4 connected aisles (center lines)
                                            // Top edge
                                            newAisles.push({
                                                id: Date.now(), points: [
                                                    { x: loop.x + loopW / 2, y: loop.y + loopW / 2 },
                                                    { x: loop.x + loop.w - loopW / 2, y: loop.y + loopW / 2 }
                                                ]
                                            });
                                            // Right edge
                                            newAisles.push({
                                                id: Date.now() + 1, points: [
                                                    { x: loop.x + loop.w - loopW / 2, y: loop.y + loopW / 2 },
                                                    { x: loop.x + loop.w - loopW / 2, y: loop.y + loop.h - loopW / 2 }
                                                ]
                                            });
                                            // Bottom edge
                                            newAisles.push({
                                                id: Date.now() + 2, points: [
                                                    { x: loop.x + loop.w - loopW / 2, y: loop.y + loop.h - loopW / 2 },
                                                    { x: loop.x + loopW / 2, y: loop.y + loop.h - loopW / 2 }
                                                ]
                                            });
                                            // Left edge
                                            newAisles.push({
                                                id: Date.now() + 3, points: [
                                                    { x: loop.x + loopW / 2, y: loop.y + loop.h - loopW / 2 },
                                                    { x: loop.x + loopW / 2, y: loop.y + loopW / 2 }
                                                ]
                                            });

                                            // Add spines ONLY if they're visible in the auto layout
                                            // Manual spines always get captured
                                            if (manualSpines.length > 0) {
                                                manualSpines.forEach((spine, i) => newAisles.push({
                                                    id: Date.now() + 10 + i,
                                                    points: [
                                                        { x: spine.x, y: innerY },
                                                        { x: spine.x, y: innerY + innerH }
                                                    ]
                                                }));
                                            } else if (layout.useCrossAisle && !layout.isIrregular) {
                                                // Only add center spine if auto layout shows it
                                                // Use the actual spineX from the layout for accuracy
                                                const spineCenterX = layout.spineX || (innerX + innerW / 2);
                                                newAisles.push({
                                                    id: Date.now() + 100,
                                                    points: [
                                                        { x: spineCenterX, y: innerY },
                                                        { x: spineCenterX, y: innerY + innerH }
                                                    ]
                                                });
                                            } else if (layout.useCrossAisle && layout.isIrregular && layout.autoSpinePositions?.length > 0) {
                                                // For irregular shapes with auto-detected spines
                                                layout.autoSpinePositions.forEach((spine, i) => newAisles.push({
                                                    id: Date.now() + 20 + i,
                                                    points: [
                                                        { x: spine.x, y: spine.minY },
                                                        { x: spine.x, y: spine.maxY }
                                                    ]
                                                }));
                                            }
                                            // If useCrossAisle is false and no manual spines, don't add any spine

                                            setDrawnAisles(newAisles);
                                            setAisleBackup(JSON.parse(JSON.stringify(newAisles)));
                                            setAisleEditHistory([]);
                                            setIsEditingAisles(true);
                                            // Exit boundary edit when entering aisle edit
                                            setIsEditingBoundary(false);
                                        }}
                                        className="px-3 py-1.5 rounded-lg text-xs bg-cyan-500 text-white hover:bg-cyan-600 transition-colors flex items-center gap-1.5"
                                        title="Convert layout to editable (then drag points)"
                                    >
                                        <span>📋</span> Capture & Edit
                                    </button>
                                )}

                                {/* Draw new aisle */}
                                <button
                                    onClick={() => {
                                        setIsDrawingAisle(!isDrawingAisle);
                                        setIsPlacingSpine(false);
                                        setIsPlacingAda(false);
                                        setIsEditingAisles(false);
                                        if (isDrawingAisle) {
                                            setCurrentAislePoints([]);
                                            setAisleHoverPoint(null);
                                        }
                                    }}
                                    className={`px-3 py-1.5 rounded-lg text-xs transition-colors flex items-center gap-1.5 ${isDrawingAisle
                                        ? 'bg-orange-500 text-white ring-2 ring-orange-300'
                                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                        }`}
                                    title="Draw custom aisle path (D)"
                                >
                                    <span>✏️</span> Draw
                                </button>

                                {/* Edit existing */}
                                {drawnAisles.length > 0 && (
                                    <button
                                        onClick={() => {
                                            if (!isEditingAisles) {
                                                setAisleBackup(JSON.parse(JSON.stringify(drawnAisles)));
                                                // Exit boundary edit when entering aisle edit
                                                setIsEditingBoundary(false);
                                            }
                                            setIsEditingAisles(!isEditingAisles);
                                            setIsDrawingAisle(false);
                                            setIsPlacingSpine(false);
                                            if (isEditingAisles) {
                                                setAisleBackup(null);
                                                setAisleEditHistory([]);
                                            }
                                        }}
                                        className={`px-3 py-1.5 rounded-lg text-xs transition-colors flex items-center gap-1.5 ${isEditingAisles
                                            ? 'bg-purple-500 text-white ring-2 ring-purple-300'
                                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                            }`}
                                        title="Edit aisle points (E)"
                                    >
                                        <span>✎</span> {isEditingAisles ? 'Done' : 'Edit'}
                                    </button>
                                )}

                                {/* Add Spine */}
                                {crossAisleMode !== 'none' && drawnAisles.length === 0 && (
                                    <button
                                        onClick={() => {
                                            setIsPlacingSpine(!isPlacingSpine);
                                            setIsDrawingAisle(false);
                                            setIsEditingAisles(false);
                                            setIsPlacingAda(false);
                                        }}
                                        className={`px-3 py-1.5 rounded-lg text-xs transition-colors flex items-center gap-1.5 ${isPlacingSpine
                                            ? 'bg-indigo-500 text-white ring-2 ring-indigo-300'
                                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                            }`}
                                        title="Add cross-aisle spine (S)"
                                    >
                                        <span>📍</span> Spine
                                    </button>
                                )}

                                {/* Divider */}
                                {(drawnAisles.length > 0 || manualSpines.length > 0) && (
                                    <div className="w-px h-6 bg-slate-200 mx-1"></div>
                                )}

                                {/* Reset */}
                                {(drawnAisles.length > 0 || manualSpines.length > 0) && (
                                    <button
                                        onClick={() => {
                                            setDrawnAisles([]);
                                            setManualSpines([]);
                                            setIsEditingAisles(false);
                                            setIsDrawingAisle(false);
                                            setAisleBackup(null);
                                            setAisleEditHistory([]);
                                        }}
                                        className="px-3 py-1.5 rounded-lg text-xs bg-red-50 text-red-600 hover:bg-red-100 transition-colors flex items-center gap-1.5"
                                        title="Reset to auto layout (R)"
                                    >
                                        <span>↺</span> Reset
                                    </button>
                                )}

                                {/* Keyboard hints */}
                                <div className="pl-3 border-l border-slate-200 text-[10px] text-slate-400 hidden md:block">
                                    {isDrawingAisle && 'Click: add point | Enter: finish | Esc: cancel'}
                                    {isEditingAisles && 'Drag: move | Right-click: delete | Ctrl+Z: undo'}
                                    {isPlacingSpine && 'Click: place spine'}
                                    {!isDrawingAisle && !isEditingAisles && !isPlacingSpine && 'D: draw | E: edit | S: spine'}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Vehicle Tracking Panel (Swept Path Analysis) - shown in both 2D and 3D */}
                    {showVehiclePanel && buildingType === 'parking' && massingType === 'surface' && (
                        <div className="absolute top-4 right-4 z-40 bg-white/95 backdrop-blur rounded-lg shadow-xl border border-slate-200 w-72 max-h-[calc(100vh-120px)] flex flex-col">
                            <div className="p-3 border-b border-slate-200 flex justify-between items-center flex-shrink-0">
                                <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                                    🚗 Vehicle Tracking
                                </h3>
                                <button
                                    onClick={() => setShowVehiclePanel(false)}
                                    className="text-slate-400 hover:text-slate-600"
                                >
                                    ✕
                                </button>
                            </div>

                            {/* Scrollable content area */}
                            <div className="overflow-y-auto flex-1">

                                {/* Add Vehicle Section */}
                                <div className="p-3 border-b border-slate-100">
                                    <p className="text-xs text-slate-500 mb-2">Add vehicle to test circulation:</p>
                                    <div className="grid grid-cols-2 gap-1">
                                        {Object.entries(VEHICLE_TYPES).map(([key, spec]) => (
                                            <button
                                                key={key}
                                                onClick={() => addVehicle(key)}
                                                className="px-2 py-1.5 text-xs rounded bg-slate-100 hover:bg-slate-200 text-slate-700 flex items-center gap-1"
                                                title={`${spec.name}\n${spec.length}' × ${spec.width}'\nTurn radius: ${spec.minTurningRadius}'`}
                                            >
                                                <span>{spec.icon}</span>
                                                <span className="truncate">{spec.name.split(' ')[0]}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Active Vehicles */}
                                {vehicles.length > 0 && (
                                    <div className="p-3 border-b border-slate-100">
                                        <div className="flex items-center justify-between mb-2">
                                            <p className="text-xs text-slate-500">Active vehicles ({vehicles.length}):</p>
                                            {vehicles.length > 1 && (
                                                <button
                                                    onClick={() => { setVehicles([]); setSelectedVehicle(null); }}
                                                    className="text-[10px] text-red-500 hover:text-red-700"
                                                >
                                                    Clear all
                                                </button>
                                            )}
                                        </div>
                                        <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                                            {vehicles.map(v => {
                                                const spec = VEHICLE_TYPES[v.type];
                                                return (
                                                    <div
                                                        key={v.id}
                                                        className={`flex items-center justify-between px-2 py-1.5 rounded text-xs cursor-pointer ${selectedVehicle === v.id ? 'bg-blue-100 text-blue-800 ring-1 ring-blue-300' : 'bg-slate-50 hover:bg-slate-100'}`}
                                                        onClick={() => setSelectedVehicle(v.id)}
                                                    >
                                                        <span className="flex items-center gap-1.5">
                                                            <span>{spec?.icon}</span>
                                                            <span className="font-medium">{spec?.name}</span>
                                                            <span className="text-[10px] text-slate-400">#{v.id}</span>
                                                        </span>
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); removeVehicle(v.id); }}
                                                            className="text-red-500 hover:text-red-700 px-1"
                                                        >
                                                            ✕
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* Selected Vehicle Controls */}
                                {selectedVehicle && (
                                    <div className="p-3 border-b border-slate-100">
                                        <p className="text-xs font-medium text-slate-600 mb-2">🎮 Drive Controls</p>

                                        {/* Keyboard guide */}
                                        <div className="bg-slate-50 rounded p-2 mb-2">
                                            <div className="grid grid-cols-3 gap-0.5 text-center mb-1">
                                                <div></div>
                                                <button
                                                    onClick={() => moveVehicle(selectedVehicle, vehicleSpeed)}
                                                    className="px-2 py-1 text-xs bg-slate-200 hover:bg-slate-300 rounded font-mono"
                                                    title="Move forward (W or ↑)"
                                                >
                                                    W ↑
                                                </button>
                                                <div></div>
                                            </div>
                                            <div className="grid grid-cols-3 gap-0.5 text-center">
                                                <button
                                                    onClick={() => steerVehicle(selectedVehicle, -25, vehicleSpeed * 0.5)}
                                                    className="px-2 py-1 text-xs bg-slate-200 hover:bg-slate-300 rounded font-mono"
                                                    title="Turn left (A or ←)"
                                                >
                                                    A ←
                                                </button>
                                                <button
                                                    onClick={() => moveVehicle(selectedVehicle, -vehicleSpeed)}
                                                    className="px-2 py-1 text-xs bg-slate-200 hover:bg-slate-300 rounded font-mono"
                                                    title="Move backward (S or ↓)"
                                                >
                                                    S ↓
                                                </button>
                                                <button
                                                    onClick={() => steerVehicle(selectedVehicle, 25, vehicleSpeed * 0.5)}
                                                    className="px-2 py-1 text-xs bg-slate-200 hover:bg-slate-300 rounded font-mono"
                                                    title="Turn right (D or →)"
                                                >
                                                    D →
                                                </button>
                                            </div>
                                        </div>

                                        {/* Speed control */}
                                        <div className="flex items-center gap-2 mb-2">
                                            <label className="text-xs text-slate-500">Speed:</label>
                                            <input
                                                type="range"
                                                min="1"
                                                max="5"
                                                value={vehicleSpeed}
                                                onChange={(e) => setVehicleSpeed(parseInt(e.target.value))}
                                                className="flex-1 h-1"
                                            />
                                            <span className="text-xs font-mono w-8">{vehicleSpeed} ft</span>
                                        </div>

                                        {/* Action buttons */}
                                        <div className="flex gap-1 flex-wrap">
                                            <button
                                                onClick={() => rotateVehicle(selectedVehicle, -15)}
                                                className="px-2 py-1 text-xs rounded bg-slate-100 hover:bg-slate-200"
                                                title="Rotate left 15° (Q)"
                                            >
                                                ↺ Q
                                            </button>
                                            <button
                                                onClick={() => rotateVehicle(selectedVehicle, 15)}
                                                className="px-2 py-1 text-xs rounded bg-slate-100 hover:bg-slate-200"
                                                title="Rotate right 15° (E)"
                                            >
                                                ↻ E
                                            </button>
                                            <button
                                                onClick={() => placeVehicleAtEntry(selectedVehicle)}
                                                className="px-2 py-1 text-xs rounded bg-green-100 hover:bg-green-200 text-green-700"
                                                title="Place at entry point"
                                            >
                                                📍 Entry
                                            </button>
                                            <button
                                                onClick={() => removeVehicle(selectedVehicle)}
                                                className="px-2 py-1 text-xs rounded bg-red-100 hover:bg-red-200 text-red-700"
                                                title="Remove vehicle"
                                            >
                                                🗑️
                                            </button>
                                        </div>

                                        {/* Keyboard shortcut hint */}
                                        <p className="text-[10px] text-slate-400 mt-2 text-center">
                                            Use WASD or Arrow keys to drive • C to clear trails
                                        </p>
                                    </div>
                                )}

                                {/* Trail Options */}
                                <div className="p-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <label className="text-xs text-slate-600 flex items-center gap-1">
                                            <input
                                                type="checkbox"
                                                checked={vehicleTrailsVisible}
                                                onChange={(e) => setVehicleTrailsVisible(e.target.checked)}
                                                className="w-3 h-3"
                                            />
                                            Show movement trails
                                        </label>
                                    </div>
                                    <div className="flex items-center justify-between mb-2">
                                        <label className="text-xs text-slate-600 flex items-center gap-1">
                                            <input
                                                type="checkbox"
                                                checked={vehicleTurningRadiusVisible}
                                                onChange={(e) => setVehicleTurningRadiusVisible(e.target.checked)}
                                                className="w-3 h-3"
                                            />
                                            Show turning radius
                                        </label>
                                    </div>
                                    {vehicles.length > 0 && (
                                        <button
                                            onClick={clearAllTrails}
                                            className="w-full px-2 py-1 text-xs rounded bg-slate-100 hover:bg-slate-200 text-slate-600"
                                        >
                                            Clear all trails
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Bottom Toolbar Overlay - Single compact row */}
                    <div className="absolute bottom-0 left-0 right-0 z-10 bg-white/95 backdrop-blur border-t border-slate-200 px-3 py-1.5 flex flex-wrap items-center gap-2">
                        {/* Draw Target (Boundary/Exclusion) - Always visible for drawing */}
                        <div className="flex items-center gap-1 border-r border-slate-300 pr-2 mr-1">
                            <button
                                onClick={() => setDrawMode('boundary')}
                                className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${drawMode === 'boundary'
                                    ? 'bg-green-100 text-green-800 ring-1 ring-green-400'
                                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                                title="Draw site boundary"
                            >
                                ⬛ Boundary
                            </button>
                            <button
                                onClick={() => setDrawMode('exclusion')}
                                className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${drawMode === 'exclusion'
                                    ? 'bg-red-100 text-red-800 ring-1 ring-red-400'
                                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                                title="Draw exclusion zone"
                            >
                                ⛔ Exclusion
                            </button>
                        </div>

                        {/* Undo/Redo */}
                        {boundary.length >= 3 && !isDrawing && (
                            <>
                                <button
                                    onClick={handleUndo}
                                    disabled={undoStack.length === 0}
                                    className={`px-2 py-0.5 text-xs rounded ${undoStack.length > 0 ? 'bg-slate-100 text-slate-600 hover:bg-slate-200' : 'bg-slate-50 text-slate-400 cursor-not-allowed'}`}
                                    title="Undo (Ctrl+Z)"
                                >
                                    ↩️
                                </button>
                                <button
                                    onClick={handleRedo}
                                    disabled={redoStack.length === 0}
                                    className={`px-2 py-0.5 text-xs rounded ${redoStack.length > 0 ? 'bg-slate-100 text-slate-600 hover:bg-slate-200' : 'bg-slate-50 text-slate-400 cursor-not-allowed'}`}
                                    title="Redo (Ctrl+Y)"
                                >
                                    ↪️
                                </button>
                                <div className="w-px h-4 bg-slate-300"></div>
                            </>
                        )}

                        {/* Edit/Draw buttons */}
                        {boundary.length >= 3 && !isDrawing && (
                            <>
                                <button
                                    onClick={() => {
                                        const newVal = !isEditingBoundary;
                                        setIsEditingBoundary(newVal);
                                        // Exit aisle edit mode when entering boundary edit
                                        if (newVal) {
                                            setIsEditingAisles(false);
                                            setIsDrawingAisle(false);
                                            setIsPlacingSpine(false);
                                        }
                                    }}
                                    className={`px-2 py-0.5 text-xs rounded ${isEditingBoundary ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                                    title="Edit boundary"
                                >
                                    📐 Edit
                                </button>
                                {viewMode === '3d' && (
                                    <button
                                        onClick={handleStartDrawing}
                                        className={`px-2 py-0.5 text-xs rounded ${isDrawingShape ? 'bg-teal-100 text-teal-800' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                                        title="Draw custom building"
                                    >
                                        ✏️ Draw
                                    </button>
                                )}
                                {selectedBuildingId && (
                                    <button
                                        onClick={() => handleDeleteBuilding(selectedBuildingId)}
                                        className="px-2 py-0.5 text-xs rounded bg-red-100 text-red-700 hover:bg-red-200"
                                        title="Delete selected"
                                    >
                                        🗑️
                                    </button>
                                )}
                                <div className="w-px h-4 bg-slate-300"></div>
                            </>
                        )}

                        {/* Snap toggle */}
                        {(boundary.length >= 3 || isDrawing) && (
                            <>
                                <button
                                    onClick={() => setSnapEnabled(!snapEnabled)}
                                    className={`px-2 py-0.5 text-xs rounded ${snapEnabled ? 'bg-blue-100 text-blue-800' : 'bg-slate-100 text-slate-500'}`}
                                    title="Toggle snapping"
                                >
                                    🧲 {snapEnabled ? 'ON' : 'OFF'}
                                </button>
                                {snapEnabled && (
                                    <>
                                        <button
                                            onClick={() => setSnapToGrid(!snapToGrid)}
                                            className={`px-2 py-0.5 text-xs rounded ${snapToGrid ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500'}`}
                                            title="Snap to grid"
                                        >
                                            ⊞
                                        </button>
                                        <button
                                            onClick={() => setOrthoMode(!orthoMode)}
                                            className={`px-2 py-0.5 text-xs rounded ${orthoMode ? 'bg-yellow-100 text-yellow-800' : 'bg-slate-100 text-slate-500'}`}
                                            title="Ortho mode"
                                        >
                                            ⊥
                                        </button>
                                    </>
                                )}
                                <div className="w-px h-4 bg-slate-300"></div>
                            </>
                        )}

                        {/* Vehicle Tracking / Swept Path Analysis */}
                        {boundary.length >= 3 && buildingType === 'parking' && massingType === 'surface' && (
                            <button
                                onClick={() => setShowVehiclePanel(!showVehiclePanel)}
                                className={`px-2 py-0.5 text-xs rounded ${showVehiclePanel ? 'bg-purple-100 text-purple-800' : 'bg-slate-100 text-slate-500'}`}
                                title="Vehicle tracking / Swept path analysis"
                            >
                                🚗 Vehicles {vehicles.length > 0 ? `(${vehicles.length})` : ''}
                            </button>
                        )}

                        {/* Spacer */}
                        <div className="flex-1"></div>

                        {/* Zoom controls - only in 2D mode */}
                        {viewMode === '2d' && (
                            <div className="flex items-center gap-1 border-r border-slate-300 pr-2 mr-2">
                                <button
                                    onClick={() => setCanvasZoom(z => Math.max(0.25, z * 0.9))}
                                    className="px-1.5 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Zoom out"
                                >
                                    −
                                </button>
                                <span className="text-xs text-slate-600 min-w-[3rem] text-center">
                                    {Math.round(canvasZoom * 100)}%
                                </span>
                                <button
                                    onClick={() => setCanvasZoom(z => Math.min(4, z * 1.1))}
                                    className="px-1.5 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Zoom in"
                                >
                                    +
                                </button>
                                <button
                                    onClick={handleResetZoom}
                                    className="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Reset zoom (fit to view)"
                                >
                                    ⟲
                                </button>
                            </div>
                        )}

                        {/* 3D View Zoom Controls */}
                        {viewMode === '3d' && (
                            <div className="flex items-center gap-1 border-r border-slate-300 pr-2 mr-2">
                                <button
                                    onClick={() => viewer3DRef.current?.zoomOut()}
                                    className="px-1.5 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Zoom out"
                                >
                                    −
                                </button>
                                <span className="text-xs text-slate-600 min-w-[3rem] text-center">
                                    {zoom3DLevel}%
                                </span>
                                <button
                                    onClick={() => viewer3DRef.current?.zoomIn()}
                                    className="px-1.5 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Zoom in"
                                >
                                    +
                                </button>
                                <button
                                    onClick={() => viewer3DRef.current?.fitToExtents()}
                                    className="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Fit to extents"
                                >
                                    ⤢
                                </button>
                                <button
                                    onClick={() => viewer3DRef.current?.resetView()}
                                    className="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-600 hover:bg-slate-200"
                                    title="Reset view"
                                >
                                    ⟲
                                </button>
                            </div>
                        )}

                        {/* Legend - compact */}
                        <div className="hidden sm:flex items-center gap-2 text-[10px] text-slate-500">
                            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-green-500/50 border border-green-500"></span>Site</span>
                            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-teal-500/50 border border-teal-500"></span>Building</span>
                            <span className="flex items-center gap-1"><span className="w-2 h-2 bg-yellow-500/50 border border-yellow-500"></span>Parking</span>
                        </div>

                        {/* Config selector */}
                        {results?.configurations?.length > 1 && (
                            <select
                                value={activeConfig}
                                onChange={e => setActiveConfig(parseInt(e.target.value))}
                                className="bg-slate-100 rounded px-2 py-0.5 text-xs"
                            >
                                {results.configurations.map((_, i) => (
                                    <option key={i} value={i}>Config {i + 1}</option>
                                ))}
                            </select>
                        )}
                    </div>{/* End Bottom Toolbar Overlay */}
                </div>
            </div>
        </div>
    );
}
