import React, { useState, useRef, useEffect } from 'react';

// Conversion factors
const FT_TO_M = 0.3048;
const M_TO_FT = 1 / FT_TO_M;

// Standard parking structure dimensions
const STANDARDS = {
    floorToFloor: 10.5, // ft (3.2m) - typical for parking structures
    columnGridX: 30, // ft (9.1m) - typical column spacing
    columnGridY: 30, // ft (9.1m)
    rampWidth: 14, // ft (4.3m) - two-way ramp
    rampSlope: 0.05, // 5% slope
    rampLength: 60, // ft - typical straight ramp
    ventShaftSize: 8, // ft x 8 ft typical
};

// Parse DXF file to extract polylines/polygons - Enhanced for Rhino/Revit/AutoCAD
function parseDXF(content) {
    const lines = content.split('\n').map(l => l.trim());
    const entities = [];
    let currentEntity = null;
    let inEntities = false;
    let vertexPoints = []; // For POLYLINE with VERTEX entities

    for (let i = 0; i < lines.length; i++) {
        const code = lines[i];
        const value = lines[i + 1];

        if (code === 'ENTITIES') {
            inEntities = true;
            continue;
        }
        if (code === 'ENDSEC' && inEntities) {
            inEntities = false;
            continue;
        }

        if (!inEntities) continue;

        // Start of entity
        if (code === '0') {
            // Save previous entity
            if (currentEntity && currentEntity.points.length > 0) {
                entities.push(currentEntity);
            }

            // Handle VERTEX entities (part of POLYLINE)
            if (value === 'VERTEX') {
                // Will collect points for the current POLYLINE
                i++;
                continue;
            }

            // End of POLYLINE sequence
            if (value === 'SEQEND' && vertexPoints.length > 0) {
                if (currentEntity) {
                    currentEntity.points = [...vertexPoints];
                    entities.push(currentEntity);
                }
                vertexPoints = [];
                currentEntity = null;
                i++;
                continue;
            }

            // Supported entity types
            const supportedTypes = [
                'POLYLINE', 'LWPOLYLINE', 'LINE', 'SPLINE',
                '3DFACE', 'SOLID', 'TRACE', 'REGION',
                'CIRCLE', 'ARC', 'ELLIPSE', 'HATCH',
                'INSERT', 'DIMENSION'
            ];

            if (supportedTypes.includes(value)) {
                currentEntity = {
                    type: value,
                    points: [],
                    layer: '',
                    isClosed: false,
                    color: 0,
                    radius: 0,
                    center: null
                };
                vertexPoints = [];
            } else {
                currentEntity = null;
            }
            i++;
            continue;
        }

        if (!currentEntity) continue;

        // Layer name (group code 8)
        if (code === '8') {
            currentEntity.layer = value || '';
            i++;
            continue;
        }

        // Color (group code 62)
        if (code === '62') {
            currentEntity.color = parseInt(value) || 0;
            i++;
            continue;
        }

        // Closed flag for LWPOLYLINE (group code 70)
        if (code === '70') {
            const flag = parseInt(value) || 0;
            currentEntity.isClosed = (flag & 1) === 1;
            i++;
            continue;
        }

        // Radius for circles (group code 40)
        if (code === '40' && currentEntity.type === 'CIRCLE') {
            currentEntity.radius = parseFloat(value) || 0;
            i++;
            continue;
        }

        // X coordinate (group code 10, 11, 12, 13)
        if (code === '10' || code === '11' || code === '12' || code === '13') {
            const x = parseFloat(value);
            const nextCode = lines[i + 2];
            const expectedY = code === '10' ? '20' : code === '11' ? '21' : code === '12' ? '22' : '23';
            if (nextCode === expectedY) {
                const y = parseFloat(lines[i + 3]);
                if (!isNaN(x) && !isNaN(y)) {
                    if (currentEntity.type === 'CIRCLE') {
                        currentEntity.center = { x, y };
                    } else {
                        currentEntity.points.push({ x, y });
                    }
                }
                i += 3;
            }
            continue;
        }
    }

    // Don't forget last entity
    if (currentEntity && currentEntity.points.length > 0) {
        entities.push(currentEntity);
    }

    // Convert circles to polygons (approximate with 16 points)
    const processedEntities = entities.map(e => {
        if (e.type === 'CIRCLE' && e.center && e.radius > 0) {
            const points = [];
            for (let i = 0; i < 16; i++) {
                const angle = (i / 16) * Math.PI * 2;
                points.push({
                    x: e.center.x + e.radius * Math.cos(angle),
                    y: e.center.y + e.radius * Math.sin(angle)
                });
            }
            return { ...e, points, isClosed: true };
        }
        return e;
    });

    return processedEntities;
}

// Calculate polygon area (for finding largest boundary)
function polygonArea(points) {
    if (points.length < 3) return 0;
    let area = 0;
    for (let i = 0; i < points.length; i++) {
        const j = (i + 1) % points.length;
        area += points[i].x * points[j].y;
        area -= points[j].x * points[i].y;
    }
    return Math.abs(area / 2);
}

// Classify entities by layer name - Enhanced for Rhino/Revit
function classifyEntities(entities) {
    const result = {
        boundary: null,
        exclusions: [],
        columns: [],
        walls: [],
        rooms: [],
        allPolygons: []
    };

    // Common layer name patterns for different CAD software
    const boundaryPatterns = [
        'BOUNDARY', 'LIMIT', 'SITE', 'PERIMETER', 'OUTLINE', 'FLOOR',
        'SLAB', 'FOOTPRINT', 'EXTENT', 'AREA', 'REGION', 'ZONE',
        'A-FLOR', 'A-AREA', 'S-SLAB', // Revit/AIA patterns
        'DEFAULT', '0', 'DEFPOINTS' // Common default layers
    ];

    const wallPatterns = [
        'WALL', 'A-WALL', 'WALLS', 'PARTITION', 'INTERIOR',
        'EXTERIOR', 'FACADE', 'ENCLOSURE'
    ];

    const roomPatterns = [
        'ROOM', 'SPACE', 'AREA', 'A-ROOM', 'A-AREA-'
    ];

    const excludePatterns = [
        'MECH', 'MECHANICAL', 'STAIR', 'ELEVATOR', 'ELEV',
        'CORE', 'SHAFT', 'EXCLUDE', 'VOID', 'RAMP', 'DUCT',
        'HVAC', 'EQUIP', 'TOILET', 'RESTROOM', 'WC', 'UTILITY',
        'ELECTRICAL', 'ELEC', 'STORAGE', 'TRASH', 'SERVICE'
    ];

    const columnPatterns = [
        'COLUMN', 'COL', 'STRUCT', 'S-COLS', 'PILLAR', 'PIER', 'POST'
    ];

    for (const entity of entities) {
        const layer = (entity.layer || '').toUpperCase();
        const hasPoints = entity.points && entity.points.length >= 3;

        if (!hasPoints && entity.type !== 'CIRCLE') continue;

        // Calculate area for this polygon
        const area = polygonArea(entity.points);

        // Store all valid polygons for fallback
        if (entity.points.length >= 3) {
            result.allPolygons.push({
                points: entity.points,
                area,
                layer: entity.layer,
                isClosed: entity.isClosed
            });
        }

        // Check for boundary
        if (boundaryPatterns.some(p => layer.includes(p))) {
            if (!result.boundary || area > polygonArea(result.boundary)) {
                result.boundary = entity.points;
            }
        }
        // Check for walls (can be treated as exclusions or kept separate)
        else if (wallPatterns.some(p => layer.includes(p))) {
            result.walls.push({
                points: entity.points,
                layer: entity.layer,
                area
            });
        }
        // Check for rooms
        else if (roomPatterns.some(p => layer.includes(p))) {
            result.rooms.push({
                points: entity.points,
                layer: entity.layer,
                area
            });
        }
        // Check for exclusion zones
        else if (excludePatterns.some(p => layer.includes(p))) {
            const type = layer.includes('MECH') || layer.includes('HVAC') || layer.includes('EQUIP') ? 'mechanical' :
                layer.includes('STAIR') ? 'stairs' :
                    layer.includes('ELEV') ? 'elevator' :
                        layer.includes('TOILET') || layer.includes('RESTROOM') || layer.includes('WC') ? 'restroom' :
                            layer.includes('ELECTRICAL') || layer.includes('ELEC') ? 'electrical' : 'core';
            result.exclusions.push({
                type,
                points: entity.points,
                layer: entity.layer,
                area
            });
        }
        // Check for columns
        else if (columnPatterns.some(p => layer.includes(p))) {
            // Calculate center of column
            const cx = entity.points.reduce((s, p) => s + p.x, 0) / entity.points.length;
            const cy = entity.points.reduce((s, p) => s + p.y, 0) / entity.points.length;
            // Estimate size from bounding box
            const xs = entity.points.map(p => p.x);
            const ys = entity.points.map(p => p.y);
            const size = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
            result.columns.push({ x: cx, y: cy, size: size || 2 });
        }
    }

    // SMART FALLBACK: If no boundary found, use intelligent detection
    if (!result.boundary && result.allPolygons.length > 0) {
        // Sort by area (largest first)
        const sortedByArea = [...result.allPolygons]
            .filter(p => p.points.length >= 4) // At least a quadrilateral
            .sort((a, b) => b.area - a.area);

        if (sortedByArea.length > 0) {
            // Use the largest polygon as boundary
            result.boundary = sortedByArea[0].points;

            // If there are rooms, use the largest room as boundary
            if (result.rooms.length > 0) {
                const largestRoom = result.rooms.sort((a, b) => b.area - a.area)[0];
                if (largestRoom.area > polygonArea(result.boundary) * 0.5) {
                    // Room is significant, might be the actual boundary
                    result.boundary = largestRoom.points;
                }
            }

            // Treat smaller significant polygons as potential exclusions
            for (let i = 1; i < sortedByArea.length && i < 20; i++) {
                const poly = sortedByArea[i];
                // If polygon is 1-30% of boundary area, likely an exclusion
                const ratio = poly.area / sortedByArea[0].area;
                if (ratio > 0.01 && ratio < 0.3) {
                    // Check if not already in exclusions
                    const alreadyExcluded = result.exclusions.some(e =>
                        Math.abs(polygonArea(e.points) - poly.area) < 1
                    );
                    if (!alreadyExcluded) {
                        result.exclusions.push({
                            type: 'auto-detected',
                            points: poly.points,
                            layer: poly.layer || 'auto',
                            area: poly.area
                        });
                    }
                }
            }
        }
    }

    // Also check walls - if we have walls but no boundary, 
    // calculate bounding box of all walls as boundary
    if (!result.boundary && result.walls.length > 0) {
        const allWallPoints = result.walls.flatMap(w => w.points);
        if (allWallPoints.length > 0) {
            const xs = allWallPoints.map(p => p.x);
            const ys = allWallPoints.map(p => p.y);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            result.boundary = [
                { x: minX, y: minY },
                { x: maxX, y: minY },
                { x: maxX, y: maxY },
                { x: minX, y: maxY }
            ];
        }
    }

    return result;
}

// Simplified element roles: Boundary (parking area) and Constraint (everything to avoid)
const ELEMENT_ROLES = {
    none: { label: 'Unassigned', color: '#94a3b8', fill: '#f1f5f9' },
    boundary: { label: 'Boundary', color: '#0f172a', fill: '#e0f2fe', description: 'Parking area perimeter' },
    constraint: { label: 'Constraint', color: '#dc2626', fill: '#fef2f2', description: 'Objects to avoid (columns, stairs, rooms, etc.)' },
};

export default function ParkingGenerator() {
    const [unitSystem, setUnitSystem] = useState('imperial'); // 'imperial' (ft) or 'metric' (m)
    const [parkingType, setParkingType] = useState('surface'); // 'surface', 'structured', 'underground'
    const [numLevels, setNumLevels] = useState(3);
    const [activeLevel, setActiveLevel] = useState(1); // 1-based level selector
    const [showColumns, setShowColumns] = useState(true);
    const [showRamps, setShowRamps] = useState(true);

    const [width, setWidth] = useState(200);
    const [height, setHeight] = useState(150);
    const [stallWidth, setStallWidth] = useState(9);
    const [stallLength, setStallLength] = useState(18);
    const [aisleWidth, setAisleWidth] = useState(24);
    const [setback, setSetback] = useState(5);
    const [iterations, setIterations] = useState([]);
    const [activeIdx, setActiveIdx] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showGrid, setShowGrid] = useState(true);
    const [showDimensions, setShowDimensions] = useState(true);

    // NEW: Interactive CAD Upload state
    const [uploadFileName, setUploadFileName] = useState('');
    const [drawingScale, setDrawingScale] = useState(1);
    const [drawingUnits, setDrawingUnits] = useState('feet');
    const fileInputRef = useRef(null);

    // All imported elements (polygons, lines, circles, etc.)
    const [importedElements, setImportedElements] = useState([]);
    // Selected element index(es) for role assignment
    const [selectedElements, setSelectedElements] = useState([]);
    // Element role assignments: { elementId: 'boundary' | 'mechanical' | 'stairs' | ... }
    const [elementRoles, setElementRoles] = useState({});
    // View mode: 'assign' (assigning roles) or 'generate' (after generation)
    const [viewMode, setViewMode] = useState('assign');
    // Show unassigned elements
    const [showUnassigned, setShowUnassigned] = useState(true);
    // Legacy compatibility
    const [uploadedGeometry, setUploadedGeometry] = useState(null);
    const [showExclusions, setShowExclusions] = useState(true);

    // Zoom and pan state
    const [zoom, setZoom] = useState(1);
    const [pan, setPan] = useState({ x: 0, y: 0 });
    const [isPanning, setIsPanning] = useState(false);
    const [panStart, setPanStart] = useState({ x: 0, y: 0 });
    const [canvasContainerWidth, setCanvasContainerWidth] = useState(900);
    const canvasRef = useRef(null);

    // Fixed canvas dimensions
    const canvasWidth = '100%';
    const canvasHeight = 600;

    // Convert display value based on unit system (internal storage is always in feet)
    const toDisplay = (ftValue) => unitSystem === 'metric' ? +(ftValue * FT_TO_M).toFixed(2) : ftValue;
    const fromDisplay = (displayValue) => unitSystem === 'metric' ? displayValue * M_TO_FT : displayValue;
    const unitLabel = unitSystem === 'metric' ? 'm' : 'ft';

    const scale = 3;
    const margin = 80; // Increased margin for dimensions and annotations
    const gridSpacing = unitSystem === 'metric' ? 6 : 20; // Grid every 6m or 20ft

    // Calculate SVG dimensions
    const svgWidth = width * scale + margin * 2;
    const svgHeight = height * scale + margin * 2;

    // Calculate center position for the drawing
    const getCenteredPan = () => ({
        x: (canvasContainerWidth - svgWidth) / 2,
        y: (canvasHeight - svgHeight) / 2
    });

    // Zoom handlers
    const handleZoomIn = () => setZoom(z => Math.min(z * 1.25, 5));
    const handleZoomOut = () => setZoom(z => Math.max(z / 1.25, 0.25));
    const handleZoomReset = () => {
        setZoom(1);
        setPan(getCenteredPan());
    };

    // Fit drawing to canvas
    const handleZoomFit = () => {
        const padding = 20; // padding around the drawing
        const availableWidth = canvasContainerWidth - padding * 2;
        const availableHeight = canvasHeight - padding * 2;
        const scaleX = availableWidth / svgWidth;
        const scaleY = availableHeight / svgHeight;
        const fitZoom = Math.min(scaleX, scaleY, 2); // Cap at 200%
        setZoom(fitZoom);
        setPan({
            x: (canvasContainerWidth - svgWidth * fitZoom) / 2,
            y: (canvasHeight - svgHeight * fitZoom) / 2
        });
    };
    // Initialize centered position and track container width
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const updateSize = () => {
            const w = canvas.offsetWidth;
            setCanvasContainerWidth(w);
            setPan({
                x: (w - svgWidth) / 2,
                y: (canvasHeight - svgHeight) / 2
            });
        };

        updateSize();
        window.addEventListener('resize', updateSize);
        return () => window.removeEventListener('resize', updateSize);
    }, [svgWidth, svgHeight, canvasHeight]);

    // Attach non-passive wheel event listener to prevent page scroll
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const handleWheel = (e) => {
            e.preventDefault();
            e.stopPropagation();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            setZoom(z => Math.min(Math.max(z * delta, 0.25), 5));
        };

        canvas.addEventListener('wheel', handleWheel, { passive: false });
        return () => canvas.removeEventListener('wheel', handleWheel);
    }, []);

    // Pan handlers - only start panning if not clicking on an element
    const handleMouseDown = (e) => {
        // If clicking on an SVG element with an onClick handler, don't start panning
        if (e.target.tagName !== 'DIV' && e.target.closest('.imported-elements')) {
            return; // Let the element handle the click
        }
        if (e.button === 0) { // Left click
            setIsPanning(true);
            setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
        }
    };

    const handleMouseMove = (e) => {
        if (isPanning) {
            setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
        }
    };

    const handleMouseUp = () => {
        setIsPanning(false);
    };

    // Clear selection when clicking on empty canvas space
    const handleCanvasClick = (e) => {
        // Only clear if clicking on the background, not on an element
        if (e.target.tagName === 'rect' && e.target.getAttribute('fill') === '#fafafa') {
            setSelectedElements([]);
        }
    };

    const handleMouseLeave = () => {
        setIsPanning(false);
    };

    // Handle CAD file upload - NEW: Import all elements for interactive assignment
    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploadFileName(file.name);
        const ext = file.name.split('.').pop().toLowerCase();

        try {
            const content = await file.text();
            let elements = [];

            // Apply scale factor based on drawing units
            const scaleFactor = drawingUnits === 'meters' ? M_TO_FT :
                drawingUnits === 'inches' ? 1 / 12 : 1;
            const totalScale = scaleFactor * drawingScale;

            if (ext === 'dxf') {
                // Parse DXF file - get ALL entities
                const rawEntities = parseDXF(content);
                elements = rawEntities.map((entity, idx) => ({
                    id: `elem-${idx}`,
                    type: entity.type,
                    layer: entity.layer || 'Default',
                    points: entity.points.map(p => ({
                        x: p.x * totalScale,
                        y: p.y * totalScale
                    })),
                    isClosed: entity.isClosed,
                    isCircle: entity.type === 'CIRCLE',
                    radius: (entity.radius || 0) * totalScale,
                    center: entity.center ? {
                        x: entity.center.x * totalScale,
                        y: entity.center.y * totalScale
                    } : null
                }));
            } else if (ext === 'json' || ext === 'geojson') {
                // Parse JSON/GeoJSON
                const data = JSON.parse(content);
                if (data.features) {
                    // GeoJSON format
                    elements = data.features.map((f, idx) => ({
                        id: `elem-${idx}`,
                        type: 'polygon',
                        layer: f.properties?.layer || f.properties?.type || 'Default',
                        points: (f.geometry?.coordinates?.[0] || []).map(c => ({
                            x: c[0] * totalScale,
                            y: c[1] * totalScale
                        })),
                        isClosed: true
                    }));
                } else if (data.elements) {
                    // Direct elements array
                    console.log('Found data.elements array with', data.elements.length, 'items');
                    elements = data.elements.map((el, idx) => {
                        console.log('Parsing element', idx, ':', el.type, el.layer);
                        // Handle circle elements with center/radius
                        if (el.type === 'circle' && el.center) {
                            return {
                                id: `elem-${idx}`,
                                type: 'circle',
                                layer: el.layer || 'Default',
                                isCircle: true,
                                center: {
                                    x: el.center.x * totalScale,
                                    y: el.center.y * totalScale
                                },
                                radius: (el.radius || 1) * totalScale,
                                points: [],
                                isClosed: true
                            };
                        }
                        // Handle polygon/line elements with points
                        return {
                            id: `elem-${idx}`,
                            type: el.type || 'polygon',
                            layer: el.layer || 'Default',
                            points: (el.points || []).map(p => ({
                                x: p.x * totalScale,
                                y: p.y * totalScale
                            })),
                            isClosed: el.isClosed !== false,
                            isCircle: false,
                            center: null,
                            radius: 0
                        };
                    });
                    console.log('Parsed elements from JSON:', elements.length, 'elements');
                } else if (data.boundary) {
                    // Legacy format with boundary
                    elements.push({
                        id: 'elem-0',
                        type: 'polygon',
                        layer: 'BOUNDARY',
                        points: data.boundary.map(p => ({
                            x: p.x * totalScale,
                            y: p.y * totalScale
                        })),
                        isClosed: true
                    });
                    (data.exclusions || []).forEach((exc, idx) => {
                        elements.push({
                            id: `elem-${idx + 1}`,
                            type: 'polygon',
                            layer: exc.type || 'EXCLUSION',
                            points: (exc.points || exc.polygon || []).map(p => ({
                                x: p.x * totalScale,
                                y: p.y * totalScale
                            })),
                            isClosed: true
                        });
                    });
                }
            } else if (ext === 'svg') {
                // Parse SVG
                const parser = new DOMParser();
                const doc = parser.parseFromString(content, 'image/svg+xml');
                const paths = doc.querySelectorAll('path, polygon, polyline, rect, circle, ellipse, line');
                let idx = 0;

                paths.forEach(path => {
                    const id = path.getAttribute('id') || `elem-${idx}`;
                    const layer = path.getAttribute('data-layer') || path.getAttribute('class') || 'Default';

                    if (path.tagName === 'rect') {
                        const x = parseFloat(path.getAttribute('x') || 0) * totalScale;
                        const y = parseFloat(path.getAttribute('y') || 0) * totalScale;
                        const w = parseFloat(path.getAttribute('width') || 0) * totalScale;
                        const h = parseFloat(path.getAttribute('height') || 0) * totalScale;
                        elements.push({
                            id,
                            type: 'rect',
                            layer,
                            points: [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }],
                            isClosed: true
                        });
                    } else if (path.tagName === 'circle') {
                        const cx = parseFloat(path.getAttribute('cx') || 0) * totalScale;
                        const cy = parseFloat(path.getAttribute('cy') || 0) * totalScale;
                        const r = parseFloat(path.getAttribute('r') || 0) * totalScale;
                        elements.push({
                            id,
                            type: 'circle',
                            layer,
                            isCircle: true,
                            center: { x: cx, y: cy },
                            radius: r,
                            points: []
                        });
                    } else if (path.tagName === 'line') {
                        const x1 = parseFloat(path.getAttribute('x1') || 0) * totalScale;
                        const y1 = parseFloat(path.getAttribute('y1') || 0) * totalScale;
                        const x2 = parseFloat(path.getAttribute('x2') || 0) * totalScale;
                        const y2 = parseFloat(path.getAttribute('y2') || 0) * totalScale;
                        elements.push({
                            id,
                            type: 'line',
                            layer,
                            points: [{ x: x1, y: y1 }, { x: x2, y: y2 }],
                            isClosed: false
                        });
                    } else if (path.tagName === 'polygon' || path.tagName === 'polyline') {
                        const pts = path.getAttribute('points')?.split(/\s+/).filter(Boolean).map(p => {
                            const [x, y] = p.split(',').map(n => parseFloat(n) * totalScale);
                            return { x, y };
                        });
                        if (pts?.length) {
                            elements.push({
                                id,
                                type: path.tagName,
                                layer,
                                points: pts,
                                isClosed: path.tagName === 'polygon'
                            });
                        }
                    }
                    idx++;
                });
            }

            if (elements.length > 0) {
                // Normalize to origin - find bounding box of all elements
                const allPoints = elements.flatMap(el =>
                    el.isCircle && el.center
                        ? [{ x: el.center.x - el.radius, y: el.center.y - el.radius },
                        { x: el.center.x + el.radius, y: el.center.y + el.radius }]
                        : el.points
                );

                if (allPoints.length > 0) {
                    const xs = allPoints.map(p => p.x);
                    const ys = allPoints.map(p => p.y);
                    const minX = Math.min(...xs);
                    const minY = Math.min(...ys);
                    const maxX = Math.max(...xs);
                    const maxY = Math.max(...ys);

                    // Normalize all elements to origin
                    elements = elements.map(el => ({
                        ...el,
                        points: el.points.map(p => ({ x: p.x - minX, y: p.y - minY })),
                        center: el.center ? { x: el.center.x - minX, y: el.center.y - minY } : null
                    }));

                    // Update canvas dimensions
                    setWidth(Math.round(maxX - minX) || 200);
                    setHeight(Math.round(maxY - minY) || 150);
                }

                // Set imported elements and reset assignments
                console.log('Setting imported elements:', elements.length, 'elements');
                console.log('viewMode will be:', 'assign');
                setImportedElements(elements);
                setSelectedElements([]);
                setElementRoles({});
                setViewMode('assign');
                setIterations([]);
                setError(null);

                // Clear legacy geometry
                setUploadedGeometry(null);
            } else {
                setError('No geometry found in the uploaded file.');
            }
        } catch (err) {
            setError(`Error parsing file: ${err.message}`);
        }

        // Reset file input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    // Clear uploaded geometry and imported elements
    const clearUploadedGeometry = () => {
        setUploadedGeometry(null);
        setUploadFileName('');
        setImportedElements([]);
        setSelectedElements([]);
        setElementRoles({});
        setViewMode('assign');
        setIterations([]);
    };

    // Handle element click for selection
    const handleElementClick = (elementId, e) => {
        e.stopPropagation();
        if (e.shiftKey) {
            // Multi-select with shift
            setSelectedElements(prev =>
                prev.includes(elementId)
                    ? prev.filter(id => id !== elementId)
                    : [...prev, elementId]
            );
        } else {
            // Single select
            setSelectedElements(prev =>
                prev.length === 1 && prev[0] === elementId
                    ? []
                    : [elementId]
            );
        }
    };

    // Assign role to selected elements
    const assignRole = (role) => {
        if (selectedElements.length === 0) return;

        // For boundary, only allow one element
        if (role === 'boundary') {
            // Remove boundary from other elements first
            const newRoles = { ...elementRoles };
            Object.keys(newRoles).forEach(key => {
                if (newRoles[key] === 'boundary') {
                    delete newRoles[key];
                }
            });
            // Assign boundary to first selected element only
            newRoles[selectedElements[0]] = role;
            setElementRoles(newRoles);
        } else if (role === 'none') {
            // Remove role from selected elements
            const newRoles = { ...elementRoles };
            selectedElements.forEach(id => delete newRoles[id]);
            setElementRoles(newRoles);
        } else {
            // Assign role to all selected elements
            const newRoles = { ...elementRoles };
            selectedElements.forEach(id => {
                newRoles[id] = role;
            });
            setElementRoles(newRoles);
        }

        setSelectedElements([]);
    };

    // Get geometry from element roles for generation
    const getAssignedGeometry = () => {
        const boundaryId = Object.keys(elementRoles).find(id => elementRoles[id] === 'boundary');
        const boundaryElement = importedElements.find(el => el.id === boundaryId);

        // Get boundary points (use element or default rectangle)
        let boundary;
        if (boundaryElement?.points?.length >= 3) {
            boundary = boundaryElement.points;
            // Update width/height based on assigned boundary
            const xs = boundary.map(p => p.x);
            const ys = boundary.map(p => p.y);
            const newWidth = Math.round(Math.max(...xs) - Math.min(...xs));
            const newHeight = Math.round(Math.max(...ys) - Math.min(...ys));
            if (newWidth !== width) setWidth(newWidth);
            if (newHeight !== height) setHeight(newHeight);
        } else {
            boundary = [{ x: 0, y: 0 }, { x: width, y: 0 }, { x: width, y: height }, { x: 0, y: height }];
        }

        // Collect ALL constraints as exclusion zones
        // Any element marked as 'constraint' blocks stall placement
        const exclusions = [];

        console.log('[getAssignedGeometry] Checking elements for constraints...');
        console.log('[getAssignedGeometry] importedElements.length:', importedElements.length);
        console.log('[getAssignedGeometry] elementRoles:', JSON.stringify(elementRoles));

        importedElements.forEach(el => {
            // Skip the boundary element
            if (el.id === boundaryId) {
                console.log(`[getAssignedGeometry] Skipping boundary element: ${el.id}`);
                return;
            }

            const role = elementRoles[el.id];
            console.log(`[getAssignedGeometry] Element ${el.id}: role=${role}`);

            // Only include elements explicitly marked as 'constraint'
            if (role !== 'constraint') return;

            // Get polygon points
            let polygon = null;
            if (el.isCircle && el.center) {
                polygon = generateCirclePoints(el.center, el.radius, 12);
            } else if (el.points && el.points.length >= 3) {
                polygon = el.points;
            } else if (el.points && el.points.length === 2) {
                // Convert lines to rectangles with adequate width
                const p1 = el.points[0];
                const p2 = el.points[1];
                const dx = p2.x - p1.x;
                const dy = p2.y - p1.y;
                const len = Math.sqrt(dx * dx + dy * dy);
                if (len > 0) {
                    // Create a wall with reasonable width (at least 2 feet for detectability)
                    const wallWidth = 2;
                    const nx = -dy / len * wallWidth / 2;
                    const ny = dx / len * wallWidth / 2;
                    polygon = [
                        { x: p1.x + nx, y: p1.y + ny },
                        { x: p2.x + nx, y: p2.y + ny },
                        { x: p2.x - nx, y: p2.y - ny },
                        { x: p1.x - nx, y: p1.y - ny }
                    ];
                }
            }

            if (polygon && polygon.length >= 3) {
                exclusions.push({ type: 'constraint', polygon });
            }
        });

        console.log('=== GEOMETRY EXTRACTION ===');
        console.log('Boundary element:', boundaryId);
        console.log('Total imported elements:', importedElements.length);
        console.log('Constraints (exclusions) extracted:', exclusions.length);
        exclusions.forEach((exc, i) => {
            const xs = exc.polygon.map(p => p.x);
            const ys = exc.polygon.map(p => p.y);
            console.log(`  Constraint ${i + 1}: bbox (${Math.min(...xs).toFixed(1)}, ${Math.min(...ys).toFixed(1)}) to (${Math.max(...xs).toFixed(1)}, ${Math.max(...ys).toFixed(1)})`);
        });

        return { boundary, exclusions, columns: [] };
    };

    // Generate circle points for exclusion zones
    const generateCirclePoints = (center, radius, segments) => {
        const points = [];
        for (let i = 0; i < segments; i++) {
            const angle = (i / segments) * Math.PI * 2;
            points.push({
                x: center.x + radius * Math.cos(angle),
                y: center.y + radius * Math.sin(angle)
            });
        }
        return points;
    };

    async function generate() {
        setLoading(true);
        setError(null);

        // Get geometry from assigned elements
        const { boundary, exclusions, columns } = getAssignedGeometry();

        console.log('=== GENERATING PARKING LAYOUT ===');
        console.log('Boundary:', JSON.stringify(boundary));
        console.log('Boundary points count:', boundary.length);
        console.log('Exclusions count:', exclusions.length);
        console.log('Exclusions:', JSON.stringify(exclusions, null, 2));
        console.log('Columns count:', columns.length);
        console.log('Constraints:', { stallWidth, stallLength, aisleWidth, setback });

        // DEBUG: Show alert if no exclusions but we have constraint boxes
        const constraintCount = getConstraintBoxes().length;
        if (constraintCount > 0 && exclusions.length === 0) {
            console.warn(`WARNING: ${constraintCount} constraint boxes visible but 0 exclusions being sent!`);
        }

        try {
            const requestBody = {
                boundary,
                exclusions,
                constraints: { stallWidth, stallLength, aisleWidth, setback },
                parkingType,
                numLevels: parkingType === 'surface' ? 1 : numLevels,
                standards: {
                    floorToFloor: STANDARDS.floorToFloor,
                    columnGridX: STANDARDS.columnGridX,
                    columnGridY: STANDARDS.columnGridY,
                    rampWidth: STANDARDS.rampWidth,
                    rampSlope: STANDARDS.rampSlope,
                    rampLength: STANDARDS.rampLength,
                    ventShaftSize: STANDARDS.ventShaftSize
                }
            };
            console.log('Request body:', JSON.stringify(requestBody, null, 2));

            // Use circulation-only endpoint first for debugging
            const endpoint = '/api/parking/circulation';
            console.log(`Calling ${endpoint}...`);

            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });
            if (!res.ok) throw new Error(`Server error: ${res.status}`);
            const data = await res.json();
            console.log('Generated layout:', data);
            console.log('[DEBUG] Stalls from API:', data.iterations?.[0]?.stalls?.length || 0);
            console.log('[DEBUG] Streets from API:', data.iterations?.[0]?.streets?.length || 0);
            // Log each street segment to verify gaps around obstacles
            data.iterations?.[0]?.streets?.forEach((st, i) => {
                const poly = st.polyline || [];
                if (poly.length >= 2) {
                    console.log(`  Street ${i}: Y=${poly[0].y} X=[${poly[0].x} to ${poly[poly.length - 1].x}]`);
                }
            });
            setIterations(data.iterations || []);
            setActiveIdx(0);
            setActiveLevel(1); // Reset to first level on new generation
            setViewMode('generate'); // Switch to generate view after successful generation
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }

    // Helper to draw oriented rectangles as polygons
    const drawLanePolygon = (from, to, laneWidth, scaleFactor) => {
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) return [];
        const cx = (from.x + to.x) / 2;
        const cy = (from.y + to.y) / 2;
        const angle = Math.atan2(dy, dx);
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);
        const hw = len / 2;
        const hh = laneWidth / 2;
        return [
            { x: (cx + hw * cos - hh * sin) * scaleFactor, y: (cy + hw * sin + hh * cos) * scaleFactor },
            { x: (cx - hw * cos - hh * sin) * scaleFactor, y: (cy - hw * sin + hh * cos) * scaleFactor },
            { x: (cx - hw * cos + hh * sin) * scaleFactor, y: (cy - hw * sin - hh * cos) * scaleFactor },
            { x: (cx + hw * cos + hh * sin) * scaleFactor, y: (cy + hw * sin - hh * cos) * scaleFactor },
        ];
    };

    // Helper to draw a polyline-based street (continuous centerline)
    const drawPolylineStreet = (polyline, laneWidth, scaleFactor) => {
        if (!polyline || polyline.length < 2) return { path: '', outline: '' };

        // Create the centerline path
        const centerPath = polyline.map((p, i) => {
            const x = p.x * scaleFactor;
            const y = p.y * scaleFactor;
            return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
        }).join(' ');

        // Create offset paths for street width (left and right edges)
        const halfWidth = (laneWidth / 2) * scaleFactor;
        const leftPoints = [];
        const rightPoints = [];

        for (let i = 0; i < polyline.length; i++) {
            const curr = polyline[i];
            const prev = i > 0 ? polyline[i - 1] : curr;
            const next = i < polyline.length - 1 ? polyline[i + 1] : curr;

            // Calculate tangent direction (average of incoming and outgoing)
            let dx = 0, dy = 0;
            if (i > 0) {
                dx += curr.x - prev.x;
                dy += curr.y - prev.y;
            }
            if (i < polyline.length - 1) {
                dx += next.x - curr.x;
                dy += next.y - curr.y;
            }

            const len = Math.sqrt(dx * dx + dy * dy);
            if (len > 0) {
                dx /= len;
                dy /= len;
            }

            // Perpendicular direction
            const px = -dy;
            const py = dx;

            leftPoints.push({
                x: (curr.x + px * (laneWidth / 2)) * scaleFactor,
                y: (curr.y + py * (laneWidth / 2)) * scaleFactor
            });
            rightPoints.push({
                x: (curr.x - px * (laneWidth / 2)) * scaleFactor,
                y: (curr.y - py * (laneWidth / 2)) * scaleFactor
            });
        }

        // Build the outline path (go forward on left, backward on right)
        let outlinePath = `M ${leftPoints[0].x} ${leftPoints[0].y}`;
        for (let i = 1; i < leftPoints.length; i++) {
            outlinePath += ` L ${leftPoints[i].x} ${leftPoints[i].y}`;
        }
        for (let i = rightPoints.length - 1; i >= 0; i--) {
            outlinePath += ` L ${rightPoints[i].x} ${rightPoints[i].y}`;
        }
        outlinePath += ' Z';

        return { centerPath, outlinePath, leftPoints, rightPoints };
    };

    // Generate curved turn path at corners
    const generateCurvedTurn = (center, radius, startAngle, endAngle, scaleFactor) => {
        const r = radius * scaleFactor;
        const cx = center.x * scaleFactor;
        const cy = center.y * scaleFactor;
        const startRad = (startAngle * Math.PI) / 180;
        const endRad = (endAngle * Math.PI) / 180;
        const x1 = cx + r * Math.cos(startRad);
        const y1 = cy + r * Math.sin(startRad);
        const x2 = cx + r * Math.cos(endRad);
        const y2 = cy + r * Math.sin(endRad);
        const largeArc = Math.abs(endAngle - startAngle) > 180 ? 1 : 0;
        const sweep = endAngle > startAngle ? 1 : 0;
        return { cx, cy, r, x1, y1, x2, y2, largeArc, sweep };
    };

    // Build circulation path from streets and junctions
    const buildCirculationPath = () => {
        if (!it?.streets || it.streets.length === 0) return null;
        const paths = [];
        const junctions = it?.tjunctions || [];

        // Draw main street paths with rounded corners
        it.streets.forEach((st, idx) => {
            const fromX = st.from.x * scale;
            const fromY = st.from.y * scale;
            const toX = st.to.x * scale;
            const toY = st.to.y * scale;
            paths.push({ type: 'street', from: { x: fromX, y: fromY }, to: { x: toX, y: toY }, width: st.width });
        });

        // Generate curved corners at junction points
        junctions.forEach((tj, idx) => {
            const jx = tj.x * scale;
            const jy = tj.y * scale;
            const r = (tj.size || 24) * scale * 0.4;
            paths.push({ type: 'curve', cx: jx, cy: jy, r });
        });

        return paths;
    };

    const it = iterations[activeIdx] || {};
    const best = iterations.length > 0 ? iterations.reduce((a, b) => (b.stallCount > a.stallCount ? b : a), iterations[0]) : null;

    // Get current level data for structured/underground parking
    const currentLevelData = (() => {
        if (!it.levels || it.levels.length === 0) {
            // Surface parking - no levels, use base stalls
            return { stalls: it.stalls || [], columns: [], ramp: null, label: 'Surface' };
        }
        const levelData = it.levels.find(l => l.level === activeLevel) || it.levels[0];
        return levelData || { stalls: [], columns: [], ramp: null, label: 'L1' };
    })();

    // Get constraint bounding boxes for frontend filtering
    const getConstraintBoxes = () => {
        const boxes = [];
        importedElements.forEach(el => {
            const role = elementRoles[el.id];
            if (role !== 'constraint') return;

            let points = null;
            if (el.isCircle && el.center) {
                // Approximate circle as bounding box
                points = [
                    { x: el.center.x - el.radius, y: el.center.y - el.radius },
                    { x: el.center.x + el.radius, y: el.center.y - el.radius },
                    { x: el.center.x + el.radius, y: el.center.y + el.radius },
                    { x: el.center.x - el.radius, y: el.center.y + el.radius }
                ];
            } else if (el.points && el.points.length >= 3) {
                points = el.points;
            }

            if (points) {
                const xs = points.map(p => p.x);
                const ys = points.map(p => p.y);
                boxes.push({
                    minX: Math.min(...xs) - 2, // 2ft buffer
                    maxX: Math.max(...xs) + 2,
                    minY: Math.min(...ys) - 2,
                    maxY: Math.max(...ys) + 2
                });
            }
        });
        return boxes;
    };

    // Filter stalls that overlap constraints (belt-and-suspenders approach)
    // NOTE: Backend already filters stalls against constraints with proper buffers
    // This frontend filter is now disabled to avoid double-filtering
    const filterStallsForConstraints = (stalls) => {
        // Backend handles constraint filtering - return stalls as-is
        return stalls;

        /* Original filtering code - disabled
        const boxes = getConstraintBoxes();
        if (boxes.length === 0) return stalls;

        return stalls.filter(stall => {
            if (!stall.polygon || stall.polygon.length < 3) return true;
            const xs = stall.polygon.map(p => p.x);
            const ys = stall.polygon.map(p => p.y);
            const stallBox = {
                minX: Math.min(...xs),
                maxX: Math.max(...xs),
                minY: Math.min(...ys),
                maxY: Math.max(...ys)
            };

            // Check if stall overlaps any constraint
            for (const box of boxes) {
                const overlaps = !(stallBox.maxX <= box.minX || stallBox.minX >= box.maxX ||
                    stallBox.maxY <= box.minY || stallBox.minY >= box.maxY);
                if (overlaps) return false; // Filter out this stall
            }
            return true;
        });
        */
    };

    // Use level-specific stalls for rendering, filtered for constraints
    const rawStalls = currentLevelData.stalls || it.stalls || [];
    const displayStalls = filterStallsForConstraints(rawStalls);
    const displayColumns = (showColumns && currentLevelData.columns) || [];
    const displayRamp = (showRamps && currentLevelData.ramp) || null;

    // Debug: log constraint and stall info when layout changes
    React.useEffect(() => {
        if (it?.name) {
            const boxes = getConstraintBoxes();
            console.log(`=== RENDER DEBUG: ${it.name} ===`);
            console.log(`Constraint boxes: ${boxes.length}`);
            boxes.forEach((b, i) => console.log(`  Box ${i + 1}: (${b.minX.toFixed(1)}, ${b.minY.toFixed(1)}) to (${b.maxX.toFixed(1)}, ${b.maxY.toFixed(1)})`));
            console.log(`Raw stalls: ${rawStalls.length}, Display stalls: ${displayStalls.length}`);
            if (rawStalls.length !== displayStalls.length) {
                console.log(`  Frontend filtered ${rawStalls.length - displayStalls.length} stalls`);
            }
        }
    }, [it?.name, rawStalls.length]);

    return (
        <div style={{ padding: 24, maxWidth: 1400, fontFamily: "'Inter', 'Segoe UI', sans-serif" }}>
            {/* Title Block */}
            <div style={{ borderBottom: '3px solid #1e293b', marginBottom: 20, paddingBottom: 12 }}>
                <h2 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: '#0f172a', letterSpacing: '-0.5px' }}>
                    PARKCORE — PARKING LAYOUT GENERATOR
                </h2>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                    Architectural Site Plan • Scale: 1" = {Math.round(1 / scale * 100) / 100} {unitLabel}
                </div>
            </div>

            {/* CAD Drawing Upload Section */}
            <div style={{
                marginBottom: 20,
                padding: '16px 20px',
                background: 'linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)',
                border: '2px dashed #3b82f6',
                borderRadius: 8
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#1e40af', marginBottom: 4 }}>
                            📐 IMPORT CAD DRAWING
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                            Upload DXF, JSON, or SVG • Click elements to assign roles
                        </div>
                    </div>

                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".dxf,.json,.geojson,.svg"
                        onChange={handleFileUpload}
                        style={{ display: 'none' }}
                    />

                    <button
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                            padding: '8px 16px',
                            background: '#3b82f6',
                            color: '#fff',
                            border: 'none',
                            borderRadius: 4,
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6
                        }}
                    >
                        📁 Choose File
                    </button>

                    <button
                        onClick={async () => {
                            // Load demo data with boundary and obstacles
                            const demoElements = [
                                { id: 'demo-boundary', type: 'polygon', layer: 'boundary', points: [{ x: 0, y: 0 }, { x: 200, y: 0 }, { x: 200, y: 150 }, { x: 0, y: 150 }], isClosed: true },
                                { id: 'demo-obs1', type: 'polygon', layer: 'obstacle', points: [{ x: 80, y: 25 }, { x: 100, y: 25 }, { x: 100, y: 45 }, { x: 80, y: 45 }], isClosed: true },
                                { id: 'demo-obs2', type: 'polygon', layer: 'obstacle', points: [{ x: 50, y: 80 }, { x: 70, y: 80 }, { x: 70, y: 100 }, { x: 50, y: 100 }], isClosed: true },
                            ];
                            setImportedElements(demoElements);
                            setElementRoles({
                                'demo-boundary': 'boundary',
                                'demo-obs1': 'constraint',
                                'demo-obs2': 'constraint'
                            });
                            console.log('Demo loaded with 2 obstacles');
                        }}
                        style={{
                            padding: '8px 16px',
                            background: '#10b981',
                            color: '#fff',
                            border: 'none',
                            borderRadius: 4,
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            marginLeft: 8
                        }}
                    >
                        🧪 Load Demo
                    </button>

                    {importedElements.length > 0 && (
                        <>
                            <div style={{
                                padding: '6px 12px',
                                background: '#dcfce7',
                                border: '1px solid #16a34a',
                                borderRadius: 4,
                                fontSize: 11,
                                color: '#166534',
                                fontWeight: 500
                            }}>
                                ✓ {uploadFileName} ({importedElements.length} elements) | viewMode: {viewMode}
                            </div>
                            <button
                                onClick={clearUploadedGeometry}
                                style={{
                                    padding: '6px 10px',
                                    background: '#fee2e2',
                                    color: '#dc2626',
                                    border: '1px solid #dc2626',
                                    borderRadius: 4,
                                    fontSize: 11,
                                    fontWeight: 500,
                                    cursor: 'pointer'
                                }}
                            >
                                ✕ Clear
                            </button>
                        </>
                    )}

                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 10, color: '#64748b' }}>Drawing Units:</span>
                        <select
                            value={drawingUnits}
                            onChange={(e) => setDrawingUnits(e.target.value)}
                            style={{
                                padding: '4px 8px',
                                border: '1px solid #cbd5e1',
                                borderRadius: 4,
                                fontSize: 11,
                                background: '#fff'
                            }}
                        >
                            <option value="feet">Feet</option>
                            <option value="meters">Meters</option>
                            <option value="inches">Inches</option>
                        </select>
                    </div>

                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 10, color: '#64748b' }}>Scale:</span>
                        <input
                            type="number"
                            value={drawingScale}
                            onChange={(e) => setDrawingScale(parseFloat(e.target.value) || 1)}
                            min={0.01}
                            max={1000}
                            step={0.1}
                            style={{
                                width: 60,
                                padding: '4px 8px',
                                border: '1px solid #cbd5e1',
                                borderRadius: 4,
                                fontSize: 11
                            }}
                        />
                    </div>
                </div>

                {/* Interactive Role Assignment Panel */}
                {importedElements.length > 0 && (
                    <div style={{
                        marginTop: 16,
                        paddingTop: 16,
                        borderTop: '1px solid #93c5fd'
                    }}>
                        {/* Selection Info & Role Assignment Toolbar */}
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 12,
                            flexWrap: 'wrap',
                            marginBottom: 12
                        }}>
                            <div style={{
                                padding: '6px 12px',
                                background: selectedElements.length > 0 ? '#dbeafe' : '#f1f5f9',
                                borderRadius: 4,
                                fontSize: 11,
                                fontWeight: 600,
                                color: selectedElements.length > 0 ? '#1e40af' : '#64748b'
                            }}>
                                {selectedElements.length > 0
                                    ? `${selectedElements.length} element${selectedElements.length > 1 ? 's' : ''} selected`
                                    : 'Click elements on canvas to select'}
                            </div>

                            {selectedElements.length > 0 && (
                                <>
                                    <span style={{ fontSize: 11, color: '#64748b', fontWeight: 500 }}>Assign as:</span>
                                    {Object.entries(ELEMENT_ROLES).map(([role, { label, color }]) => (
                                        <button
                                            key={role}
                                            onClick={() => assignRole(role)}
                                            style={{
                                                padding: '4px 10px',
                                                background: role === 'none' ? '#f1f5f9' : color,
                                                color: role === 'none' ? '#64748b' : '#fff',
                                                border: `1px solid ${color}`,
                                                borderRadius: 4,
                                                fontSize: 10,
                                                fontWeight: 600,
                                                cursor: 'pointer',
                                                opacity: role === 'none' ? 1 : 0.9
                                            }}
                                        >
                                            {label}
                                        </button>
                                    ))}
                                </>
                            )}
                        </div>

                        {/* Assignment Summary */}
                        <div style={{
                            display: 'flex',
                            gap: 12,
                            fontSize: 11,
                            flexWrap: 'wrap',
                            alignItems: 'center'
                        }}>
                            {Object.entries(ELEMENT_ROLES).filter(([role]) => role !== 'none').map(([role, { label, color, fill }]) => {
                                const count = Object.values(elementRoles).filter(r => r === role).length;
                                if (count === 0) return null;
                                return (
                                    <div key={role} style={{
                                        padding: '4px 8px',
                                        background: fill,
                                        borderRadius: 4,
                                        border: `1px solid ${color}`,
                                        color: color
                                    }}>
                                        <strong>{label}:</strong> {count}
                                    </div>
                                );
                            })}
                            <div style={{ color: '#64748b', fontSize: 10 }}>
                                {importedElements.length - Object.keys(elementRoles).length} unassigned
                            </div>

                            {/* Quick action: Assign all non-boundary as Constraint */}
                            {Object.values(elementRoles).includes('boundary') &&
                                importedElements.length > 1 &&
                                Object.values(elementRoles).filter(r => r === 'constraint').length < importedElements.length - 1 && (
                                    <button
                                        onClick={() => {
                                            const boundaryId = Object.keys(elementRoles).find(id => elementRoles[id] === 'boundary');
                                            const newRoles = { ...elementRoles };
                                            importedElements.forEach(el => {
                                                if (el.id !== boundaryId && !newRoles[el.id]) {
                                                    newRoles[el.id] = 'constraint';
                                                }
                                            });
                                            setElementRoles(newRoles);
                                        }}
                                        style={{
                                            padding: '6px 12px',
                                            background: '#dc2626',
                                            color: '#fff',
                                            border: 'none',
                                            borderRadius: 4,
                                            fontSize: 10,
                                            fontWeight: 600,
                                            cursor: 'pointer'
                                        }}
                                    >
                                        ⚡ Mark All Others as Constraint
                                    </button>
                                )}

                            <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', marginLeft: 'auto' }}>
                                <input
                                    type="checkbox"
                                    checked={showUnassigned}
                                    onChange={(e) => setShowUnassigned(e.target.checked)}
                                />
                                Show Unassigned
                            </label>
                            {viewMode === 'generate' && (
                                <button
                                    onClick={() => setViewMode('assign')}
                                    style={{
                                        padding: '4px 10px',
                                        background: '#f1f5f9',
                                        color: '#475569',
                                        border: '1px solid #cbd5e1',
                                        borderRadius: 4,
                                        fontSize: 10,
                                        fontWeight: 500,
                                        cursor: 'pointer'
                                    }}
                                >
                                    ← Edit Assignments
                                </button>
                            )}
                        </div>

                        {/* Instructions */}
                        <div style={{
                            marginTop: 12,
                            padding: '10px 14px',
                            background: '#fff',
                            borderRadius: 4,
                            fontSize: 10,
                            color: '#64748b',
                            lineHeight: 1.6
                        }}>
                            <div style={{ fontWeight: 600, marginBottom: 4, color: '#475569' }}>
                                ✨ Simple 2-step workflow:
                            </div>
                            <div>
                                <strong>1.</strong> Click the outer perimeter and assign as <span style={{ color: ELEMENT_ROLES.boundary.color, fontWeight: 600 }}>Boundary</span><br />
                                <strong>2.</strong> Select all other elements (Shift+click or drag) and assign as <span style={{ color: ELEMENT_ROLES.constraint.color, fontWeight: 600 }}>Constraint</span><br />
                                <em style={{ fontSize: 9 }}>Tip: Use "Select All as Constraint" button to quickly assign all non-boundary elements</em>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Unit System Toggle */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Units:</span>
                    <div style={{ display: 'flex', border: '1px solid #cbd5e1', borderRadius: 4, overflow: 'hidden' }}>
                        <button
                            onClick={() => setUnitSystem('imperial')}
                            style={{
                                padding: '6px 14px',
                                background: unitSystem === 'imperial' ? '#0f172a' : '#f8fafc',
                                color: unitSystem === 'imperial' ? '#fff' : '#475569',
                                border: 'none',
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer'
                            }}
                        >
                            Imperial (ft)
                        </button>
                        <button
                            onClick={() => setUnitSystem('metric')}
                            style={{
                                padding: '6px 14px',
                                background: unitSystem === 'metric' ? '#0f172a' : '#f8fafc',
                                color: unitSystem === 'metric' ? '#fff' : '#475569',
                                border: 'none',
                                borderLeft: '1px solid #cbd5e1',
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer'
                            }}
                        >
                            Metric (m)
                        </button>
                    </div>
                </div>

                {/* Parking Type Selector */}
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Type:</span>
                    <div style={{ display: 'flex', border: '1px solid #cbd5e1', borderRadius: 4, overflow: 'hidden' }}>
                        {[
                            { key: 'surface', label: 'Surface' },
                            { key: 'structured', label: 'Structured' },
                            { key: 'underground', label: 'Underground' }
                        ].map((t, i) => (
                            <button
                                key={t.key}
                                onClick={() => { setParkingType(t.key); setActiveLevel(1); }}
                                style={{
                                    padding: '6px 14px',
                                    background: parkingType === t.key ? '#0f172a' : '#f8fafc',
                                    color: parkingType === t.key ? '#fff' : '#475569',
                                    border: 'none',
                                    borderLeft: i > 0 ? '1px solid #cbd5e1' : 'none',
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: 'pointer'
                                }}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Number of Levels - only for structured/underground */}
                {parkingType !== 'surface' && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 11, fontWeight: 500, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Levels:</span>
                        <input
                            type="number"
                            min={1}
                            max={10}
                            value={numLevels}
                            onChange={e => { setNumLevels(Math.max(1, Math.min(10, +e.target.value))); setActiveLevel(1); }}
                            style={{ width: 50, padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 3, fontSize: 14, fontWeight: 600, textAlign: 'center' }}
                        />
                    </div>
                )}
            </div>

            {/* Input Controls */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
                {[
                    { label: 'Lot Width', value: width, setter: setWidth },
                    { label: 'Lot Depth', value: height, setter: setHeight },
                    { label: 'Stall Width', value: stallWidth, setter: setStallWidth },
                    { label: 'Stall Depth', value: stallLength, setter: setStallLength },
                    { label: 'Aisle Width', value: aisleWidth, setter: setAisleWidth },
                    { label: 'Setback', value: setback, setter: setSetback },
                ].map(({ label, value, setter }) => (
                    <label key={label} style={{ display: 'flex', flexDirection: 'column', fontSize: 11, fontWeight: 500, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        {label}
                        <div style={{ display: 'flex', alignItems: 'center', marginTop: 4 }}>
                            <input
                                type="number"
                                step={unitSystem === 'metric' ? 0.1 : 1}
                                value={toDisplay(value)}
                                onChange={e => setter(fromDisplay(+e.target.value))}
                                style={{ flex: 1, padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 3, fontSize: 14, fontWeight: 600 }}
                            />
                            <span style={{ marginLeft: 6, fontSize: 11, color: '#94a3b8' }}>{unitLabel}</span>
                        </div>
                    </label>
                ))}
            </div>

            {/* Controls Row */}
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
                <button
                    onClick={generate}
                    disabled={loading}
                    style={{
                        padding: '10px 28px',
                        background: loading ? '#64748b' : '#0f172a',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 4,
                        fontWeight: 600,
                        fontSize: 13,
                        cursor: loading ? 'wait' : 'pointer',
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px'
                    }}
                >
                    {loading ? 'Computing...' : 'Generate Layout'}
                </button>

                {/* Boundary status indicator when elements are imported */}
                {importedElements.length > 0 && (
                    <div style={{
                        padding: '6px 12px',
                        background: Object.values(elementRoles).includes('boundary') ? '#dcfce7' : '#fef2f2',
                        border: `1px solid ${Object.values(elementRoles).includes('boundary') ? '#16a34a' : '#dc2626'}`,
                        borderRadius: 4,
                        fontSize: 11,
                        color: Object.values(elementRoles).includes('boundary') ? '#166534' : '#dc2626',
                        fontWeight: 500
                    }}>
                        {Object.values(elementRoles).includes('boundary')
                            ? '✓ Boundary assigned'
                            : '⚠ Assign a boundary first'}
                    </div>
                )}

                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#475569', cursor: 'pointer' }}>
                    <input type="checkbox" checked={showGrid} onChange={e => setShowGrid(e.target.checked)} />
                    Show Grid
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#475569', cursor: 'pointer' }}>
                    <input type="checkbox" checked={showDimensions} onChange={e => setShowDimensions(e.target.checked)} />
                    Show Dimensions
                </label>
            </div>

            {error && <div style={{ color: '#dc2626', marginBottom: 12, padding: 10, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 4 }}>{error}</div>}

            {/* Strategy Tabs */}
            {iterations.length > 0 && (
                <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
                    {iterations.map((iter, i) => (
                        <button
                            key={i}
                            onClick={() => setActiveIdx(i)}
                            style={{
                                padding: '8px 16px',
                                background: i === activeIdx ? '#0f172a' : '#f1f5f9',
                                color: i === activeIdx ? '#fff' : '#334155',
                                border: i === activeIdx ? 'none' : '1px solid #e2e8f0',
                                borderRadius: 3,
                                fontWeight: 600,
                                fontSize: 11,
                                cursor: 'pointer',
                                textTransform: 'uppercase',
                                letterSpacing: '0.3px'
                            }}
                        >
                            {iter.name} • {iter.stallCount} {iter === best && '★'}
                        </button>
                    ))}
                </div>
            )}

            {/* Summary Panel */}
            {(it.stallCount !== undefined || it.totalStallCount !== undefined) && (
                <div style={{
                    marginBottom: 16,
                    padding: '12px 16px',
                    background: '#f8fafc',
                    border: '2px solid #0f172a',
                    borderRadius: 4,
                    display: 'flex',
                    gap: 24,
                    fontSize: 12,
                    fontWeight: 500,
                    flexWrap: 'wrap'
                }}>
                    <div><span style={{ color: '#64748b' }}>STRATEGY:</span> <strong>{it.name?.toUpperCase()}</strong></div>

                    {/* Surface parking - single level */}
                    {parkingType === 'surface' && (
                        <>
                            <div><span style={{ color: '#64748b' }}>DISPLAYED STALLS:</span> <strong>{displayStalls.length}</strong></div>
                            {rawStalls.length !== displayStalls.length && (
                                <div style={{ color: '#dc2626' }}>
                                    <span style={{ color: '#64748b' }}>FILTERED:</span> <strong>{rawStalls.length - displayStalls.length} overlapping</strong>
                                </div>
                            )}
                            <div><span style={{ color: '#64748b' }}>CONSTRAINTS:</span> <strong>{getConstraintBoxes().length}</strong></div>
                            <div><span style={{ color: '#64748b' }}>API EXCLUSIONS:</span> <strong>{it.exclusions?.length || 0}</strong></div>
                            {it.accessInfo && (
                                <div style={{ color: '#0ea5e9' }}>
                                    <span style={{ color: '#64748b' }}>ACCESS:</span> <strong>{it.accessInfo.edge?.toUpperCase()} EDGE</strong>
                                </div>
                            )}
                            <div><span style={{ color: '#64748b' }}>LOT AREA:</span> <strong>{(width * height).toLocaleString()} SF</strong></div>
                            <div><span style={{ color: '#64748b' }}>SF/STALL:</span> <strong>{displayStalls.length > 0 ? Math.round(width * height / displayStalls.length) : '—'}</strong></div>
                        </>
                    )}

                    {/* Structured/Underground parking - multi-level */}
                    {parkingType !== 'surface' && (
                        <>
                            <div><span style={{ color: '#64748b' }}>TYPE:</span> <strong>{parkingType.toUpperCase()}</strong></div>
                            <div><span style={{ color: '#64748b' }}>LEVELS:</span> <strong>{numLevels}</strong></div>
                            <div><span style={{ color: '#64748b' }}>LEVEL {currentLevelData.label} STALLS:</span> <strong>{currentLevelData.stallCount || displayStalls.length}</strong></div>
                            <div><span style={{ color: '#64748b' }}>TOTAL STALLS:</span> <strong style={{ color: '#059669' }}>{it.totalStallCount}</strong></div>
                            <div><span style={{ color: '#64748b' }}>SF/LEVEL:</span> <strong>{(width * height).toLocaleString()}</strong></div>
                            <div><span style={{ color: '#64748b' }}>TOTAL SF:</span> <strong>{(width * height * numLevels).toLocaleString()}</strong></div>
                        </>
                    )}

                    {best && it === best && <div style={{ color: '#059669', fontWeight: 700 }}>✓ OPTIMAL</div>}
                </div>
            )}

            {/* Structural Details Panel - for structured/underground */}
            {parkingType !== 'surface' && displayColumns.length > 0 && (
                <div style={{
                    marginBottom: 16,
                    padding: '12px 16px',
                    background: '#fefce8',
                    border: '2px solid #ca8a04',
                    borderRadius: 4,
                    fontSize: 11
                }}>
                    <div style={{ fontWeight: 700, color: '#854d0e', marginBottom: 8, fontSize: 12 }}>
                        ⬛ STRUCTURAL COLUMN SCHEDULE
                    </div>
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                        <div>
                            <span style={{ color: '#a16207' }}>TOTAL COLUMNS:</span>{' '}
                            <strong style={{ color: '#854d0e' }}>{displayColumns.length}</strong>
                        </div>
                        <div>
                            <span style={{ color: '#a16207' }}>COLUMN SIZE:</span>{' '}
                            <strong style={{ color: '#854d0e' }}>
                                {displayColumns[0]?.size ? `${toDisplay(displayColumns[0].size)}${unitLabel} × ${toDisplay(displayColumns[0].size)}${unitLabel}` : '—'}
                            </strong>
                        </div>
                        <div>
                            <span style={{ color: '#a16207' }}>GRID SPACING:</span>{' '}
                            <strong style={{ color: '#854d0e' }}>
                                {toDisplay(STANDARDS.columnGridX)}{unitLabel} × {toDisplay(STANDARDS.columnGridY)}{unitLabel} (typ.)
                            </strong>
                        </div>
                        <div>
                            <span style={{ color: '#a16207' }}>FLOOR-TO-FLOOR:</span>{' '}
                            <strong style={{ color: '#854d0e' }}>{toDisplay(STANDARDS.floorToFloor)}{unitLabel}</strong>
                        </div>
                        <div>
                            <span style={{ color: '#a16207' }}>GRID PATTERN:</span>{' '}
                            <strong style={{ color: '#854d0e' }}>
                                {(() => {
                                    // Calculate grid dimensions from columns
                                    const xs = [...new Set(displayColumns.map(c => c.x))].sort((a, b) => a - b);
                                    const ys = [...new Set(displayColumns.map(c => c.y))].sort((a, b) => a - b);
                                    return `${xs.length} × ${ys.length} (${String.fromCharCode(65 + xs.length - 1)}${ys.length})`;
                                })()}
                            </strong>
                        </div>
                    </div>
                </div>
            )}

            {/* Zoom Controls & Level Selector */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontWeight: 500, color: '#1e293b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>View:</span>
                <button onClick={handleZoomIn} style={{ padding: '4px 12px', background: '#0f172a', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 14, fontWeight: 600 }}>+</button>
                <button onClick={handleZoomOut} style={{ padding: '4px 12px', background: '#0f172a', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 14, fontWeight: 600 }}>−</button>
                <button onClick={handleZoomFit} style={{ padding: '4px 12px', background: '#0f172a', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontWeight: 500 }}>Fit</button>
                <button onClick={handleZoomReset} style={{ padding: '4px 12px', background: '#0f172a', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 11, fontWeight: 500 }}>Reset</button>
                <span style={{ fontSize: 11, color: '#1e293b', fontWeight: 600, marginLeft: 8 }}>{Math.round(zoom * 100)}%</span>

                {/* Level Selector - for structured/underground */}
                {parkingType !== 'surface' && (
                    <>
                        <div style={{ width: 1, height: 20, background: '#cbd5e1', marginLeft: 8 }} />
                        <span style={{ fontSize: 11, fontWeight: 500, color: '#1e293b', textTransform: 'uppercase', letterSpacing: '0.5px', marginLeft: 8 }}>
                            {parkingType === 'underground' ? 'Basement' : 'Floor'}:
                        </span>
                        <div style={{ display: 'flex', border: '1px solid #cbd5e1', borderRadius: 4, overflow: 'hidden' }}>
                            {Array.from({ length: numLevels }, (_, i) => i + 1).map((level) => (
                                <button
                                    key={level}
                                    onClick={() => setActiveLevel(level)}
                                    style={{
                                        padding: '4px 10px',
                                        background: activeLevel === level ? '#3b82f6' : '#f8fafc',
                                        color: activeLevel === level ? '#fff' : '#475569',
                                        border: 'none',
                                        borderLeft: level > 1 ? '1px solid #cbd5e1' : 'none',
                                        fontSize: 11,
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        minWidth: 32
                                    }}
                                >
                                    {parkingType === 'underground' ? `B${level}` : `L${level}`}
                                </button>
                            ))}
                        </div>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#475569', cursor: 'pointer', marginLeft: 8 }}>
                            <input type="checkbox" checked={showColumns} onChange={e => setShowColumns(e.target.checked)} />
                            Columns
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#475569', cursor: 'pointer' }}>
                            <input type="checkbox" checked={showRamps} onChange={e => setShowRamps(e.target.checked)} />
                            Ramps
                        </label>
                    </>
                )}

                <span style={{ fontSize: 10, color: '#475569', marginLeft: 'auto' }}>Scroll to zoom • Drag to pan</span>
            </div>

            {/* Technical Drawing Canvas */}
            <div
                ref={canvasRef}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseLeave}
                style={{
                    width: canvasWidth,
                    height: canvasHeight,
                    background: showGrid
                        ? 'linear-gradient(#cbd5e1 1px, transparent 1px), linear-gradient(90deg, #cbd5e1 1px, transparent 1px), #e2e8f0'
                        : '#e2e8f0',
                    backgroundSize: showGrid ? '20px 20px' : 'auto',
                    border: '2px solid #1e293b',
                    borderRadius: 4,
                    overflow: 'hidden',
                    cursor: isPanning ? 'grabbing' : 'grab',
                    position: 'relative'
                }}
            >
                <svg
                    width={svgWidth}
                    height={svgHeight}
                    style={{
                        display: 'block',
                        transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                        transformOrigin: '0 0'
                    }}
                    xmlns="http://www.w3.org/2000/svg"
                >
                    <defs>
                        {/* Dimension arrow markers */}
                        <marker id="dimArrowStart" markerWidth="10" markerHeight="10" refX="0" refY="5" orient="auto">
                            <path d="M10,0 L0,5 L10,10 L8,5 Z" fill="#1e293b" />
                        </marker>
                        <marker id="dimArrowEnd" markerWidth="10" markerHeight="10" refX="10" refY="5" orient="auto">
                            <path d="M0,0 L10,5 L0,10 L2,5 Z" fill="#1e293b" />
                        </marker>
                        {/* Flow arrow for access */}
                        <marker id="flowArrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
                            <path d="M0,2 L10,6 L0,10 L3,6 Z" fill="#059669" />
                        </marker>
                        {/* Hatching patterns */}
                        <pattern id="hatchDrive" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
                            <line x1="0" y1="0" x2="0" y2="8" stroke="#475569" strokeWidth="1" />
                        </pattern>
                        <pattern id="hatchAisle" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(-45)">
                            <line x1="0" y1="0" x2="0" y2="6" stroke="#3b82f6" strokeWidth="0.5" />
                        </pattern>
                        <pattern id="hatchStall" patternUnits="userSpaceOnUse" width="4" height="4">
                            <circle cx="2" cy="2" r="0.5" fill="#d97706" />
                        </pattern>
                    </defs>

                    {/* Background - click to clear selection */}
                    <rect
                        width={svgWidth}
                        height={svgHeight}
                        fill="#fafafa"
                        onClick={handleCanvasClick}
                        style={{ cursor: viewMode === 'assign' && importedElements.length > 0 ? 'crosshair' : 'inherit' }}
                    />

                    <g transform={`translate(${margin},${margin})`}>
                        {/* Grid */}
                        {showGrid && (
                            <g>
                                {/* Vertical grid lines */}
                                {Array.from({ length: Math.floor(width / gridSpacing) + 1 }, (_, i) => (
                                    <line
                                        key={`vg-${i}`}
                                        x1={i * gridSpacing * scale}
                                        y1={0}
                                        x2={i * gridSpacing * scale}
                                        y2={height * scale}
                                        stroke="#e2e8f0"
                                        strokeWidth={i % 5 === 0 ? 1 : 0.5}
                                        strokeDasharray={i % 5 === 0 ? "none" : "2,4"}
                                    />
                                ))}
                                {/* Horizontal grid lines */}
                                {Array.from({ length: Math.floor(height / gridSpacing) + 1 }, (_, i) => (
                                    <line
                                        key={`hg-${i}`}
                                        x1={0}
                                        y1={i * gridSpacing * scale}
                                        x2={width * scale}
                                        y2={i * gridSpacing * scale}
                                        stroke="#e2e8f0"
                                        strokeWidth={i % 5 === 0 ? 1 : 0.5}
                                        strokeDasharray={i % 5 === 0 ? "none" : "2,4"}
                                    />
                                ))}
                            </g>
                        )}

                        {/* IMPORTED ELEMENTS - Render all imported CAD elements when in assign mode */}
                        {viewMode === 'assign' && importedElements.length > 0 && (
                            <g className="imported-elements">
                                {importedElements.map((el) => {
                                    const role = elementRoles[el.id] || 'none';
                                    const isSelected = selectedElements.includes(el.id);
                                    const roleStyle = ELEMENT_ROLES[role] || ELEMENT_ROLES.none;

                                    // Skip unassigned elements if not showing them
                                    if (!showUnassigned && role === 'none') return null;

                                    // Render circle
                                    if (el.isCircle && el.center) {
                                        return (
                                            <circle
                                                key={el.id}
                                                cx={el.center.x * scale}
                                                cy={el.center.y * scale}
                                                r={el.radius * scale}
                                                fill={isSelected ? '#bfdbfe' : roleStyle.fill}
                                                stroke={isSelected ? '#2563eb' : roleStyle.color}
                                                strokeWidth={isSelected ? 3 : 1.5}
                                                style={{ cursor: 'pointer' }}
                                                onClick={(e) => handleElementClick(el.id, e)}
                                            />
                                        );
                                    }

                                    // Render line
                                    if (el.type === 'line' || el.type === 'LINE' || (!el.isClosed && el.points.length === 2)) {
                                        return (
                                            <line
                                                key={el.id}
                                                x1={el.points[0]?.x * scale}
                                                y1={el.points[0]?.y * scale}
                                                x2={el.points[1]?.x * scale}
                                                y2={el.points[1]?.y * scale}
                                                stroke={isSelected ? '#2563eb' : roleStyle.color}
                                                strokeWidth={isSelected ? 3 : 1.5}
                                                style={{ cursor: 'pointer' }}
                                                onClick={(e) => handleElementClick(el.id, e)}
                                            />
                                        );
                                    }

                                    // Render polygon/polyline
                                    if (el.points && el.points.length >= 2) {
                                        const pointsStr = el.points.map(p => `${p.x * scale},${p.y * scale}`).join(' ');

                                        // Calculate center for label
                                        const xs = el.points.map(p => p.x);
                                        const ys = el.points.map(p => p.y);
                                        const cx = ((Math.min(...xs) + Math.max(...xs)) / 2) * scale;
                                        const cy = ((Math.min(...ys) + Math.max(...ys)) / 2) * scale;

                                        return (
                                            <g key={el.id}>
                                                {el.isClosed ? (
                                                    <polygon
                                                        points={pointsStr}
                                                        fill={isSelected ? '#bfdbfe' : roleStyle.fill}
                                                        stroke={isSelected ? '#2563eb' : roleStyle.color}
                                                        strokeWidth={isSelected ? 3 : 1.5}
                                                        style={{ cursor: 'pointer' }}
                                                        onClick={(e) => handleElementClick(el.id, e)}
                                                    />
                                                ) : (
                                                    <polyline
                                                        points={pointsStr}
                                                        fill="none"
                                                        stroke={isSelected ? '#2563eb' : roleStyle.color}
                                                        strokeWidth={isSelected ? 3 : 1.5}
                                                        style={{ cursor: 'pointer' }}
                                                        onClick={(e) => handleElementClick(el.id, e)}
                                                    />
                                                )}
                                                {/* Role label for assigned elements */}
                                                {role !== 'none' && (
                                                    <text
                                                        x={cx}
                                                        y={cy}
                                                        textAnchor="middle"
                                                        dominantBaseline="middle"
                                                        fontSize="9"
                                                        fontWeight="600"
                                                        fill={roleStyle.color}
                                                        style={{ pointerEvents: 'none', textTransform: 'uppercase' }}
                                                    >
                                                        {roleStyle.label}
                                                    </text>
                                                )}
                                            </g>
                                        );
                                    }

                                    return null;
                                })}
                            </g>
                        )}

                        {/* Lot boundary - show default rectangle when no imported boundary */}
                        {(() => {
                            const boundaryId = Object.keys(elementRoles).find(id => elementRoles[id] === 'boundary');
                            const boundaryEl = importedElements.find(el => el.id === boundaryId);

                            if (boundaryEl && boundaryEl.points && boundaryEl.points.length >= 3) {
                                // Show assigned boundary polygon
                                const pointsStr = boundaryEl.points.map(p => `${p.x * scale},${p.y * scale}`).join(' ');
                                return (
                                    <polygon
                                        points={pointsStr}
                                        fill="#fff"
                                        stroke="#0f172a"
                                        strokeWidth={3}
                                    />
                                );
                            } else if (viewMode !== 'assign' || importedElements.length === 0) {
                                // Show default rectangle boundary
                                return (
                                    <polygon
                                        points={`0,0 ${width * scale},0 ${width * scale},${height * scale} 0,${height * scale}`}
                                        fill="#fff"
                                        stroke="#0f172a"
                                        strokeWidth={3}
                                    />
                                );
                            }
                            return null;
                        })()}

                        {/* Render imported elements as background in generate mode (walls, lines, etc.) */}
                        {viewMode === 'generate' && importedElements.length > 0 && (
                            <g className="imported-background" opacity={0.4}>
                                {importedElements.map((el) => {
                                    const role = elementRoles[el.id];
                                    // Skip boundary (already rendered) and assigned exclusions (rendered separately)
                                    if (role === 'boundary' || (role && role !== 'none' && role !== 'wall')) return null;

                                    // Render line
                                    if (el.type === 'line' || el.type === 'LINE' || (!el.isClosed && el.points?.length === 2)) {
                                        return (
                                            <line
                                                key={`bg-${el.id}`}
                                                x1={el.points[0]?.x * scale}
                                                y1={el.points[0]?.y * scale}
                                                x2={el.points[1]?.x * scale}
                                                y2={el.points[1]?.y * scale}
                                                stroke="#64748b"
                                                strokeWidth={1}
                                            />
                                        );
                                    }

                                    // Render circle
                                    if (el.isCircle && el.center) {
                                        return (
                                            <circle
                                                key={`bg-${el.id}`}
                                                cx={el.center.x * scale}
                                                cy={el.center.y * scale}
                                                r={el.radius * scale}
                                                fill="none"
                                                stroke="#64748b"
                                                strokeWidth={1}
                                            />
                                        );
                                    }

                                    // Render polygon/polyline
                                    if (el.points && el.points.length >= 2) {
                                        const pointsStr = el.points.map(p => `${p.x * scale},${p.y * scale}`).join(' ');
                                        return el.isClosed ? (
                                            <polygon
                                                key={`bg-${el.id}`}
                                                points={pointsStr}
                                                fill="none"
                                                stroke="#64748b"
                                                strokeWidth={1}
                                            />
                                        ) : (
                                            <polyline
                                                key={`bg-${el.id}`}
                                                points={pointsStr}
                                                fill="none"
                                                stroke="#64748b"
                                                strokeWidth={1}
                                            />
                                        );
                                    }
                                    return null;
                                })}
                            </g>
                        )}

                        {/* Render assigned constraints (exclusions) in generate mode */}
                        {viewMode === 'generate' && showExclusions && importedElements.map((el) => {
                            const role = elementRoles[el.id];
                            // Only render elements marked as 'constraint'
                            if (role !== 'constraint') return null;

                            const roleStyle = ELEMENT_ROLES.constraint;

                            // Handle circles
                            if (el.isCircle && el.center) {
                                return (
                                    <circle
                                        key={`exc-${el.id}`}
                                        cx={el.center.x * scale}
                                        cy={el.center.y * scale}
                                        r={el.radius * scale}
                                        fill={roleStyle.fill}
                                        stroke={roleStyle.color}
                                        strokeWidth={2}
                                        strokeDasharray="6,3"
                                        opacity={0.85}
                                    />
                                );
                            }

                            if (!el.points || el.points.length < 3) return null;

                            const pointsStr = el.points.map(p => `${p.x * scale},${p.y * scale}`).join(' ');

                            return (
                                <polygon
                                    key={`exc-${el.id}`}
                                    points={pointsStr}
                                    fill={roleStyle.fill}
                                    stroke={roleStyle.color}
                                    strokeWidth={2}
                                    strokeDasharray="6,3"
                                    opacity={0.85}
                                />
                            );
                        })}

                        {/* Setback area - chain dashed */}
                        {setback > 0 && (
                            <rect
                                x={setback * scale}
                                y={setback * scale}
                                width={(width - 2 * setback) * scale}
                                height={(height - 2 * setback) * scale}
                                fill="none"
                                stroke="#64748b"
                                strokeWidth={1.5}
                                strokeDasharray="12,4,4,4"
                            />
                        )}

                        {/* Drive lanes - supports both polyline and from/to formats */}
                        {it?.streets && it.streets.length > 0 && (() => {
                            // Check if streets have polylines (medial axis format)
                            const hasPolylines = it.streets.some(st => st.polyline && st.polyline.length > 0);

                            console.log('[RENDER] Streets:', it.streets.length, 'hasPolylines:', hasPolylines);
                            it.streets.forEach((st, i) => {
                                const p = st.polyline || [];
                                console.log(`  [RENDER] Street ${i}: Y=${p[0]?.y} X=[${p[0]?.x} to ${p[p.length - 1]?.x}]`);
                            });

                            if (hasPolylines) {
                                // Render polyline-based streets - EACH SEGMENT IS SEPARATE
                                return (
                                    <g className="medial-axis-streets">
                                        {it.streets.map((st, idx) => {
                                            const polyline = st.polyline || [];
                                            if (polyline.length < 2) return null;

                                            const { centerPath, outlinePath } = drawPolylineStreet(polyline, st.width || 24, scale);
                                            console.log(`  [RENDER] Drawing street ${idx}: path="${centerPath}"`);

                                            return (
                                                <g key={`street-${idx}`}>
                                                    {/* Centerline - INDIVIDUAL SEGMENT (solid orange) */}
                                                    <path
                                                        d={centerPath}
                                                        fill="none"
                                                        stroke="#f97316"
                                                        strokeWidth={3}
                                                        strokeLinecap="round"
                                                        strokeLinejoin="round"
                                                    />
                                                </g>
                                            );
                                        })}
                                    </g>
                                );
                            }

                            // Fallback: Render from/to format streets (H/V segments)
                            const rects = it.streets.map(st => {
                                const corners = drawLanePolygon(st.from, st.to, st.width, scale);
                                return corners;
                            }).filter(c => c.length > 0);

                            if (rects.length === 0) return null;

                            // Turning radius in feet (3m ≈ 10ft)
                            const turnRadiusFt = 10;
                            const r = turnRadiusFt * scale;

                            // For loop/dual-access layouts (4 streets forming a rectangle), add corner fills
                            const streets = it.streets.filter(s => s.type === 'drive-lane');
                            const verticalStreets = streets.filter(s => Math.abs(s.to.x - s.from.x) < 0.1);
                            const horizontalStreets = streets.filter(s => Math.abs(s.to.y - s.from.y) < 0.1);

                            let cornerPathD = '';
                            const halfWidth = (streets[0]?.width || 24) * scale / 2;
                            const hw = halfWidth;

                            // Find all junction points (where streets intersect)
                            for (const vStreet of verticalStreets) {
                                for (const hStreet of horizontalStreets) {
                                    const vx = vStreet.from.x * scale;
                                    const hy = hStreet.from.y * scale;

                                    // Check if they actually intersect
                                    const vMinY = Math.min(vStreet.from.y, vStreet.to.y) * scale;
                                    const vMaxY = Math.max(vStreet.from.y, vStreet.to.y) * scale;
                                    const hMinX = Math.min(hStreet.from.x, hStreet.to.x) * scale;
                                    const hMaxX = Math.max(hStreet.from.x, hStreet.to.x) * scale;

                                    if (hy >= vMinY && hy <= vMaxY && vx >= hMinX && vx <= hMaxX) {
                                        // Determine which directions are open
                                        const hasTop = vMinY < hy - hw;
                                        const hasBottom = vMaxY > hy + hw;
                                        const hasLeft = hMinX < vx - hw;
                                        const hasRight = hMaxX > vx + hw;

                                        // Fill the center square
                                        cornerPathD += ` M ${vx - hw} ${hy - hw} L ${vx + hw} ${hy - hw} L ${vx + hw} ${hy + hw} L ${vx - hw} ${hy + hw} Z`;

                                        // Add curved fillets at dead-end corners (outer edges that need curves)
                                        // Top-right outer corner (when no top and no right)
                                        if (!hasTop && !hasRight) {
                                            cornerPathD += ` M ${vx + hw} ${hy - hw} L ${vx + hw + r} ${hy - hw} A ${r} ${r} 0 0 1 ${vx + hw} ${hy - hw - r} L ${vx + hw} ${hy - hw} Z`;
                                        }
                                        // Top-left outer corner
                                        if (!hasTop && !hasLeft) {
                                            cornerPathD += ` M ${vx - hw} ${hy - hw} L ${vx - hw} ${hy - hw - r} A ${r} ${r} 0 0 1 ${vx - hw - r} ${hy - hw} L ${vx - hw} ${hy - hw} Z`;
                                        }
                                        // Bottom-right outer corner
                                        if (!hasBottom && !hasRight) {
                                            cornerPathD += ` M ${vx + hw} ${hy + hw} L ${vx + hw} ${hy + hw + r} A ${r} ${r} 0 0 1 ${vx + hw + r} ${hy + hw} L ${vx + hw} ${hy + hw} Z`;
                                        }
                                        // Bottom-left outer corner
                                        if (!hasBottom && !hasLeft) {
                                            cornerPathD += ` M ${vx - hw} ${hy + hw} L ${vx - hw - r} ${hy + hw} A ${r} ${r} 0 0 1 ${vx - hw} ${hy + hw + r} L ${vx - hw} ${hy + hw} Z`;
                                        }

                                        // T-junction curves (one direction blocked, others open)
                                        // Vertical spine with right stub - curve at top-right and bottom-right outer
                                        if (hasTop && hasBottom && hasRight && !hasLeft) {
                                            // Curve at top-right outer edge
                                            cornerPathD += ` M ${vx + hw} ${hy - hw} L ${vx + hw + r} ${hy - hw} A ${r} ${r} 0 0 1 ${vx + hw} ${hy - hw - r} L ${vx + hw} ${hy - hw} Z`;
                                            // Curve at bottom-right outer edge
                                            cornerPathD += ` M ${vx + hw} ${hy + hw} L ${vx + hw} ${hy + hw + r} A ${r} ${r} 0 0 1 ${vx + hw + r} ${hy + hw} L ${vx + hw} ${hy + hw} Z`;
                                        }
                                        // Vertical spine with left stub
                                        if (hasTop && hasBottom && hasLeft && !hasRight) {
                                            cornerPathD += ` M ${vx - hw} ${hy - hw} L ${vx - hw} ${hy - hw - r} A ${r} ${r} 0 0 1 ${vx - hw - r} ${hy - hw} L ${vx - hw} ${hy - hw} Z`;
                                            cornerPathD += ` M ${vx - hw} ${hy + hw} L ${vx - hw - r} ${hy + hw} A ${r} ${r} 0 0 1 ${vx - hw} ${hy + hw + r} L ${vx - hw} ${hy + hw} Z`;
                                        }
                                    }
                                }
                            }

                            // Build the fill path (all rectangles + corners)
                            const fillPathD = rects.map(corners => {
                                return `M ${corners[0].x} ${corners[0].y} L ${corners[1].x} ${corners[1].y} L ${corners[2].x} ${corners[2].y} L ${corners[3].x} ${corners[3].y} Z`;
                            }).join(' ') + (cornerPathD ? ' ' + cornerPathD : '');

                            // Create unique ID for this mask
                            const maskId = `street-mask-${Math.random().toString(36).substr(2, 9)}`;

                            return (
                                <g>
                                    {/* Define a mask that shows only the outer edge */}
                                    <defs>
                                        <mask id={maskId}>
                                            {/* White background - shows stroke */}
                                            <rect x={-margin} y={-margin} width={svgWidth} height={svgHeight} fill="white" />
                                            {/* Black fill for street interiors - hides stroke inside */}
                                            <path
                                                d={fillPathD}
                                                fill="black"
                                                stroke="none"
                                            />
                                        </mask>
                                    </defs>

                                    {/* Fill all street areas */}
                                    <path
                                        d={fillPathD}
                                        fill="#f1f5f9"
                                        stroke="none"
                                    />

                                    {/* Draw stroke with mask - only visible on outer edges */}
                                    <path
                                        d={fillPathD}
                                        fill="none"
                                        stroke="#475569"
                                        strokeWidth={4}
                                        mask={`url(#${maskId})`}
                                    />
                                </g>
                            );
                        })()}

                        {/* Direction arrows for streets - shows traffic flow direction */}
                        {it?.streets?.map((st, i) => {
                            const dx = st.to.x - st.from.x;
                            const dy = st.to.y - st.from.y;
                            const len = Math.sqrt(dx * dx + dy * dy);
                            const midX = (st.from.x + st.to.x) / 2 * scale;
                            const midY = (st.from.y + st.to.y) / 2 * scale;
                            const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                            const laneWidth = (st.width || 24) * scale;

                            if (len <= 40) return null;

                            // Check if street is two-way or one-way (default to two-way for main drive lanes)
                            const isTwoWay = st.twoWay !== false; // Default to two-way unless explicitly one-way

                            if (isTwoWay) {
                                // Two-way: show arrows on each side of centerline pointing in opposite directions
                                const offset = laneWidth / 4; // Offset from center for each lane
                                const perpAngle = (angle + 90) * Math.PI / 180;
                                const offsetX = Math.cos(perpAngle) * offset;
                                const offsetY = Math.sin(perpAngle) * offset;

                                return (
                                    <g key={`arr-${i}`}>
                                        {/* Arrow for one direction (forward) */}
                                        <g transform={`translate(${midX + offsetX}, ${midY + offsetY}) rotate(${angle})`}>
                                            <polygon
                                                points="-6,-3 6,0 -6,3"
                                                fill="#64748b"
                                                opacity={0.7}
                                            />
                                        </g>
                                        {/* Arrow for opposite direction (backward) */}
                                        <g transform={`translate(${midX - offsetX}, ${midY - offsetY}) rotate(${angle + 180})`}>
                                            <polygon
                                                points="-6,-3 6,0 -6,3"
                                                fill="#64748b"
                                                opacity={0.7}
                                            />
                                        </g>
                                    </g>
                                );
                            } else {
                                // One-way: single centered arrow
                                return (
                                    <g key={`arr-${i}`} transform={`translate(${midX}, ${midY}) rotate(${angle})`}>
                                        <polygon
                                            points="-8,-4 8,0 -8,4"
                                            fill="#64748b"
                                            opacity={0.7}
                                        />
                                    </g>
                                );
                            }
                        })}

                        {/* Yellow centerline - connected path through all streets */}
                        {it?.streets && it.streets.length > 0 && (() => {
                            // Get street centerlines scaled
                            const streets = it.streets.map(st => ({
                                from: { x: st.from.x * scale, y: st.from.y * scale },
                                to: { x: st.to.x * scale, y: st.to.y * scale },
                                isHorizontal: Math.abs(st.to.y - st.from.y) < 1,
                                isVertical: Math.abs(st.to.x - st.from.x) < 1
                            }));

                            // Find bounds
                            const allX = streets.flatMap(s => [s.from.x, s.to.x]);
                            const allY = streets.flatMap(s => [s.from.y, s.to.y]);
                            const minX = Math.min(...allX);
                            const maxX = Math.max(...allX);
                            const minY = Math.min(...allY);
                            const maxY = Math.max(...allY);

                            const verticalStreets = streets.filter(s => s.isVertical);
                            const horizontalStreets = streets.filter(s => s.isHorizontal);

                            let pathD = '';

                            // Detect layout type based on street configuration
                            const numVertical = verticalStreets.length;
                            const numHorizontal = horizontalStreets.length;

                            if (numVertical === 4 || (numVertical === 2 && numHorizontal === 2 && streets.length === 4)) {
                                // LOOP or DUAL-ACCESS layout - 4 sides forming a closed rectangle
                                const allXs = [...new Set(streets.flatMap(s => [s.from.x, s.to.x]))].sort((a, b) => a - b);
                                const allYs = [...new Set(streets.flatMap(s => [s.from.y, s.to.y]))].sort((a, b) => a - b);

                                const leftX = allXs.find(x => verticalStreets.some(s => Math.abs(s.from.x - x) < 1));
                                const rightX = [...allXs].reverse().find(x => verticalStreets.some(s => Math.abs(s.from.x - x) < 1));
                                const topY = allYs.find(y => horizontalStreets.some(s => Math.abs(s.from.y - y) < 1));
                                const bottomY = [...allYs].reverse().find(y => horizontalStreets.some(s => Math.abs(s.from.y - y) < 1));

                                pathD = `M ${leftX} ${topY} L ${rightX} ${topY} L ${rightX} ${bottomY} L ${leftX} ${bottomY} Z`;
                            } else if (numVertical === 1 && numHorizontal === 1) {
                                // T-junction or L-junction - draw both streets
                                pathD = streets.map(s => `M ${s.from.x} ${s.from.y} L ${s.to.x} ${s.to.y}`).join(' ');
                            } else if (numVertical === 2 && numHorizontal >= 1) {
                                // Dual vertical with horizontal(s) - like dual-access or horizontal layout
                                // Get the two vertical street X positions
                                const vXs = [...new Set(verticalStreets.map(s => s.from.x))].sort((a, b) => a - b);
                                const leftX = vXs[0];
                                const rightX = vXs[vXs.length - 1] || leftX;

                                // Get horizontal Y positions
                                const hYs = [...new Set(horizontalStreets.map(s => s.from.y))].sort((a, b) => a - b);

                                if (hYs.length >= 2) {
                                    // Full U-shape with top and bottom horizontals - closed loop
                                    const topY = hYs[0];
                                    const bottomY = hYs[hYs.length - 1];
                                    pathD = `M ${leftX} ${topY} L ${rightX} ${topY} L ${rightX} ${bottomY} L ${leftX} ${bottomY} Z`;
                                } else if (hYs.length === 1) {
                                    // HORIZONTAL LAYOUT: 1 horizontal + 2 verticals
                                    const hY = hYs[0];
                                    const leftVert = verticalStreets.filter(s => Math.abs(s.from.x - leftX) < 1);
                                    const rightVert = verticalStreets.filter(s => Math.abs(s.from.x - rightX) < 1);
                                    const leftMaxY = Math.max(...leftVert.flatMap(s => [s.from.y, s.to.y]));
                                    const rightMaxY = Math.max(...rightVert.flatMap(s => [s.from.y, s.to.y]));

                                    pathD = `M ${leftX} ${leftMaxY} L ${leftX} ${hY} L ${rightX} ${hY} L ${rightX} ${rightMaxY}`;
                                }
                            } else if (numVertical === 1 && numHorizontal >= 2) {
                                // Single vertical with multiple horizontals - U-shape
                                const leftX = verticalStreets[0].from.x;
                                const hYs = [...new Set(horizontalStreets.map(s => s.from.y))].sort((a, b) => a - b);
                                const topY = hYs[0];
                                const bottomY = hYs[hYs.length - 1];

                                pathD = `M ${maxX} ${topY} L ${leftX} ${topY} L ${leftX} ${bottomY} L ${maxX} ${bottomY}`;
                            } else if (numHorizontal === 1 && numVertical >= 2) {
                                // Single horizontal with multiple verticals - rotated U-shape
                                const topY = horizontalStreets[0].from.y;
                                const vXs = [...new Set(verticalStreets.map(s => s.from.x))].sort((a, b) => a - b);
                                const leftX = vXs[0];
                                const rightX = vXs[vXs.length - 1];

                                pathD = `M ${leftX} ${minY} L ${leftX} ${topY} L ${rightX} ${topY} L ${rightX} ${minY}`;
                            } else {
                                // Fallback: draw individual centerlines
                                pathD = streets.map(s => `M ${s.from.x} ${s.from.y} L ${s.to.x} ${s.to.y}`).join(' ');
                            }

                            if (!pathD) return null;

                            // DISABLED: Yellow centerline was drawing over segment gaps
                            // return (
                            //     <path
                            //         d={pathD}
                            //         fill="none"
                            //         stroke="#eab308"
                            //         strokeWidth={2}
                            //         strokeDasharray="12,8"
                            //         strokeLinecap="round"
                            //         strokeLinejoin="round"
                            //     />
                            // );
                            return null;
                        })()}


                        {/* Aisles */}
                        {it?.aisles?.map((ai, i) => {
                            const corners = drawLanePolygon(ai.from, ai.to, ai.width, scale);
                            if (corners.length === 0) return null;
                            return (
                                <g key={`ai-${i}`}>
                                    <polygon
                                        points={corners.map(p => `${p.x},${p.y}`).join(' ')}
                                        fill="#f1f5f9"
                                        stroke="#64748b"
                                        strokeWidth={1.5}
                                    />
                                    {/* Center line - dashed */}
                                    <line
                                        x1={ai.from.x * scale}
                                        y1={ai.from.y * scale}
                                        x2={ai.to.x * scale}
                                        y2={ai.to.y * scale}
                                        stroke="#94a3b8"
                                        strokeWidth={1}
                                        strokeDasharray="4,4"
                                    />
                                </g>
                            );
                        })}

                        {/* Connectors */}
                        {it?.connectors?.map((c, i) => {
                            const corners = drawLanePolygon(c.from, c.to, c.width || 24, scale);
                            if (corners.length === 0) return null;
                            return (
                                <polygon
                                    key={`cn-${i}`}
                                    points={corners.map(p => `${p.x},${p.y}`).join(' ')}
                                    fill="none"
                                    stroke="#94a3b8"
                                    strokeWidth={1}
                                    strokeDasharray="6,3"
                                />
                            );
                        })}

                        {/* Access points */}
                        {it?.access?.map((acc, i) => {
                            const corners = drawLanePolygon(acc.from, acc.to, acc.width || 24, scale);
                            if (corners.length === 0) return null;
                            return (
                                <g key={`acc-${i}`}>
                                    <polygon
                                        points={corners.map(p => `${p.x},${p.y}`).join(' ')}
                                        fill="#dcfce7"
                                        stroke="#059669"
                                        strokeWidth={2.5}
                                    />
                                    {/* Flow arrow */}
                                    <line
                                        x1={acc.from.x * scale}
                                        y1={acc.from.y * scale}
                                        x2={acc.to.x * scale}
                                        y2={acc.to.y * scale}
                                        stroke="#059669"
                                        strokeWidth={2}
                                        markerEnd="url(#flowArrow)"
                                    />
                                    {/* Label */}
                                    <text
                                        x={(acc.from.x + acc.to.x) / 2 * scale}
                                        y={(acc.from.y + acc.to.y) / 2 * scale - 8}
                                        textAnchor="middle"
                                        fontSize="9"
                                        fontWeight="700"
                                        fill="#059669"
                                        style={{ textTransform: 'uppercase', letterSpacing: '1px' }}
                                    >
                                        ENTRY
                                    </text>
                                </g>
                            );
                        })}



                        {/* Stalls - outlined with stall numbers */}
                        {console.log('[RENDER] displayStalls:', displayStalls.length, displayStalls.slice(0, 3))}
                        {displayStalls.map((st, i) => {
                            if (!st.polygon || st.polygon.length < 3) return null;
                            const centerX = st.center?.x ?? (st.polygon.reduce((sum, p) => sum + p.x, 0) / st.polygon.length);
                            const centerY = st.center?.y ?? (st.polygon.reduce((sum, p) => sum + p.y, 0) / st.polygon.length);
                            return (
                                <g key={`stl-${i}`}>
                                    <polygon
                                        points={st.polygon.map(p => `${p.x * scale},${p.y * scale}`).join(' ')}
                                        fill="#fff"
                                        stroke="#334155"
                                        strokeWidth={0.75}
                                    />
                                    {/* Stall orientation indicator */}
                                    <circle
                                        cx={centerX * scale}
                                        cy={centerY * scale}
                                        r={2}
                                        fill="#64748b"
                                    />
                                </g>
                            );
                        })}

                        {/* Exclusion Zones from API (only when no imported elements - avoid duplicates) */}
                        {showExclusions && importedElements.length === 0 && (it.exclusions || uploadedGeometry?.exclusions || []).map((exc, i) => {
                            const points = exc.polygon || exc.points || [];
                            if (points.length < 3) return null;

                            // Color coding by type
                            const colors = {
                                mechanical: { fill: '#fef2f2', stroke: '#dc2626', pattern: 'mech' },
                                stairs: { fill: '#fefce8', stroke: '#ca8a04', pattern: 'stairs' },
                                elevator: { fill: '#f0fdf4', stroke: '#16a34a', pattern: 'elev' },
                                core: { fill: '#eff6ff', stroke: '#2563eb', pattern: 'core' },
                                exclusion: { fill: '#f5f5f4', stroke: '#78716c', pattern: 'exc' }
                            };
                            const style = colors[exc.type] || colors.exclusion;

                            return (
                                <g key={`exc-${i}`}>
                                    <polygon
                                        points={points.map(p => `${p.x * scale},${p.y * scale}`).join(' ')}
                                        fill={style.fill}
                                        stroke={style.stroke}
                                        strokeWidth={2}
                                        strokeDasharray="6,3"
                                        opacity={0.85}
                                    />
                                    {/* Diagonal hatch pattern */}
                                    {(() => {
                                        const xs = points.map(p => p.x);
                                        const ys = points.map(p => p.y);
                                        const minX = Math.min(...xs);
                                        const maxX = Math.max(...xs);
                                        const minY = Math.min(...ys);
                                        const maxY = Math.max(...ys);
                                        const cx = (minX + maxX) / 2;
                                        const cy = (minY + maxY) / 2;

                                        return (
                                            <>
                                                {/* Hatch lines */}
                                                {Array.from({ length: Math.ceil((maxX - minX) / 8) }, (_, j) => (
                                                    <line
                                                        key={`hatch-${i}-${j}`}
                                                        x1={(minX + j * 8) * scale}
                                                        y1={minY * scale}
                                                        x2={(minX + j * 8) * scale}
                                                        y2={maxY * scale}
                                                        stroke={style.stroke}
                                                        strokeWidth={0.5}
                                                        opacity={0.3}
                                                    />
                                                ))}
                                                {/* Type label */}
                                                <text
                                                    x={cx * scale}
                                                    y={cy * scale}
                                                    textAnchor="middle"
                                                    dominantBaseline="middle"
                                                    fontSize="9"
                                                    fontWeight="700"
                                                    fill={style.stroke}
                                                    style={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}
                                                >
                                                    {exc.type === 'mechanical' ? 'MECH' :
                                                        exc.type === 'stairs' ? 'STAIR' :
                                                            exc.type === 'elevator' ? 'ELEV' :
                                                                exc.type === 'core' ? 'CORE' : 'EXCL'}
                                                </text>
                                            </>
                                        );
                                    })()}
                                </g>
                            );
                        })}

                        {/* Structural Grid Lines - connect columns */}
                        {displayColumns.length > 0 && showColumns && (() => {
                            const xs = [...new Set(displayColumns.map(c => c.x))].sort((a, b) => a - b);
                            const ys = [...new Set(displayColumns.map(c => c.y))].sort((a, b) => a - b);
                            const gridLines = [];
                            // Vertical grid lines
                            xs.forEach((x, xi) => {
                                if (ys.length > 1) {
                                    gridLines.push(
                                        <line
                                            key={`grid-v-${xi}`}
                                            x1={x * scale}
                                            y1={Math.min(...ys) * scale}
                                            x2={x * scale}
                                            y2={Math.max(...ys) * scale}
                                            stroke="#ca8a04"
                                            strokeWidth={0.5}
                                            strokeDasharray="8,4"
                                            opacity={0.6}
                                        />
                                    );
                                }
                            });
                            // Horizontal grid lines
                            ys.forEach((y, yi) => {
                                if (xs.length > 1) {
                                    gridLines.push(
                                        <line
                                            key={`grid-h-${yi}`}
                                            x1={Math.min(...xs) * scale}
                                            y1={y * scale}
                                            x2={Math.max(...xs) * scale}
                                            y2={y * scale}
                                            stroke="#ca8a04"
                                            strokeWidth={0.5}
                                            strokeDasharray="8,4"
                                            opacity={0.6}
                                        />
                                    );
                                }
                            });
                            return gridLines;
                        })()}

                        {/* Structural Columns - shown for structured/underground parking */}
                        {displayColumns.map((col, i) => {
                            // Calculate grid label (A1, A2, B1, B2, etc.)
                            const xs = [...new Set(displayColumns.map(c => c.x))].sort((a, b) => a - b);
                            const ys = [...new Set(displayColumns.map(c => c.y))].sort((a, b) => a - b);
                            const colIdx = xs.indexOf(col.x);
                            const rowIdx = ys.indexOf(col.y);
                            const gridLabel = `${String.fromCharCode(65 + colIdx)}${rowIdx + 1}`;

                            return (
                                <g key={`col-${i}`}>
                                    {/* Column shadow */}
                                    <rect
                                        x={(col.x - col.size / 2 + 0.3) * scale}
                                        y={(col.y - col.size / 2 + 0.3) * scale}
                                        width={col.size * scale}
                                        height={col.size * scale}
                                        fill="#00000033"
                                    />
                                    {/* Column body */}
                                    <rect
                                        x={(col.x - col.size / 2) * scale}
                                        y={(col.y - col.size / 2) * scale}
                                        width={col.size * scale}
                                        height={col.size * scale}
                                        fill="#1e293b"
                                        stroke="#0f172a"
                                        strokeWidth={1.5}
                                    />
                                    {/* Column cross-hatch pattern */}
                                    <line
                                        x1={(col.x - col.size / 2) * scale}
                                        y1={(col.y - col.size / 2) * scale}
                                        x2={(col.x + col.size / 2) * scale}
                                        y2={(col.y + col.size / 2) * scale}
                                        stroke="#64748b"
                                        strokeWidth={0.75}
                                    />
                                    <line
                                        x1={(col.x + col.size / 2) * scale}
                                        y1={(col.y - col.size / 2) * scale}
                                        x2={(col.x - col.size / 2) * scale}
                                        y2={(col.y + col.size / 2) * scale}
                                        stroke="#64748b"
                                        strokeWidth={0.75}
                                    />
                                    {/* Column grid label */}
                                    <text
                                        x={col.x * scale}
                                        y={(col.y - col.size / 2 - 2) * scale}
                                        textAnchor="middle"
                                        fontSize="7"
                                        fontWeight="600"
                                        fill="#ca8a04"
                                        style={{ fontFamily: "'Courier New', monospace" }}
                                    >
                                        {gridLabel}
                                    </text>
                                </g>
                            );
                        })}

                        {/* Ramp - shown for structured/underground parking */}
                        {displayRamp && (
                            <g>
                                {/* Ramp footprint */}
                                <rect
                                    x={displayRamp.x * scale}
                                    y={displayRamp.y * scale}
                                    width={(displayRamp.orientation === 'vertical' ? displayRamp.width : displayRamp.length) * scale}
                                    height={(displayRamp.orientation === 'vertical' ? displayRamp.length : displayRamp.width) * scale}
                                    fill="#fef3c7"
                                    stroke="#d97706"
                                    strokeWidth={1.5}
                                />
                                {/* Ramp direction indicator (diagonal lines) */}
                                {Array.from({ length: 5 }, (_, i) => {
                                    const rampW = (displayRamp.orientation === 'vertical' ? displayRamp.width : displayRamp.length) * scale;
                                    const rampH = (displayRamp.orientation === 'vertical' ? displayRamp.length : displayRamp.width) * scale;
                                    const spacing = rampH / 6;
                                    return (
                                        <line
                                            key={`ramp-line-${i}`}
                                            x1={displayRamp.x * scale}
                                            y1={displayRamp.y * scale + spacing * (i + 1)}
                                            x2={displayRamp.x * scale + rampW}
                                            y2={displayRamp.y * scale + spacing * (i + 1)}
                                            stroke="#d97706"
                                            strokeWidth={0.5}
                                            strokeDasharray="4,2"
                                        />
                                    );
                                })}
                                {/* Ramp label */}
                                <text
                                    x={(displayRamp.x + (displayRamp.orientation === 'vertical' ? displayRamp.width / 2 : displayRamp.length / 2)) * scale}
                                    y={(displayRamp.y + (displayRamp.orientation === 'vertical' ? displayRamp.length / 2 : displayRamp.width / 2)) * scale}
                                    textAnchor="middle"
                                    dominantBaseline="middle"
                                    fontSize="10"
                                    fontWeight="700"
                                    fill="#92400e"
                                    style={{ textTransform: 'uppercase' }}
                                >
                                    RAMP {displayRamp.direction === 'down' ? '↓' : '↑'}
                                </text>
                                {/* Slope annotation */}
                                <text
                                    x={(displayRamp.x + (displayRamp.orientation === 'vertical' ? displayRamp.width / 2 : displayRamp.length / 2)) * scale}
                                    y={(displayRamp.y + (displayRamp.orientation === 'vertical' ? displayRamp.length / 2 : displayRamp.width / 2) + 10) * scale}
                                    textAnchor="middle"
                                    dominantBaseline="middle"
                                    fontSize="8"
                                    fill="#b45309"
                                >
                                    {(displayRamp.slope * 100).toFixed(0)}% SLOPE
                                </text>
                            </g>
                        )}

                        {/* Dimension lines */}
                        {showDimensions && (
                            <g style={{ fontFamily: "'Courier New', monospace" }}>
                                {/* Top dimension - Width */}
                                <line x1={0} y1={-30} x2={width * scale} y2={-30} stroke="#1e293b" strokeWidth={1} markerStart="url(#dimArrowStart)" markerEnd="url(#dimArrowEnd)" />
                                <line x1={0} y1={-10} x2={0} y2={-35} stroke="#1e293b" strokeWidth={0.5} />
                                <line x1={width * scale} y1={-10} x2={width * scale} y2={-35} stroke="#1e293b" strokeWidth={0.5} />
                                <rect x={(width * scale) / 2 - 35} y={-44} width={70} height={16} fill="#fff" />
                                <text x={(width * scale) / 2} y={-32} textAnchor="middle" fontSize="11" fontWeight="700" fill="#1e293b">
                                    {unitSystem === 'metric' ? `${toDisplay(width)} m` : `${width}'-0"`}
                                </text>

                                {/* Left dimension - Height */}
                                <line x1={-30} y1={0} x2={-30} y2={height * scale} stroke="#1e293b" strokeWidth={1} markerStart="url(#dimArrowStart)" markerEnd="url(#dimArrowEnd)" />
                                <line x1={-10} y1={0} x2={-35} y2={0} stroke="#1e293b" strokeWidth={0.5} />
                                <line x1={-10} y1={height * scale} x2={-35} y2={height * scale} stroke="#1e293b" strokeWidth={0.5} />
                                <g transform={`translate(-38, ${(height * scale) / 2}) rotate(-90)`}>
                                    <rect x={-35} y={-8} width={70} height={16} fill="#fff" />
                                    <text x={0} y={4} textAnchor="middle" fontSize="11" fontWeight="700" fill="#1e293b">
                                        {unitSystem === 'metric' ? `${toDisplay(height)} m` : `${height}'-0"`}
                                    </text>
                                </g>

                                {/* Grid labels */}
                                {Array.from({ length: Math.floor(width / gridSpacing) + 1 }, (_, i) => i * gridSpacing).filter((_, i) => i % 2 === 0).map(v => (
                                    <text key={`gl-x-${v}`} x={v * scale} y={height * scale + 20} textAnchor="middle" fontSize="8" fill="#94a3b8">
                                        {unitSystem === 'metric' ? `${toDisplay(v)}` : `${v}'`}
                                    </text>
                                ))}
                                {Array.from({ length: Math.floor(height / gridSpacing) + 1 }, (_, i) => i * gridSpacing).filter((_, i) => i % 2 === 0).map(v => (
                                    <text key={`gl-y-${v}`} x={width * scale + 15} y={v * scale + 3} textAnchor="start" fontSize="8" fill="#94a3b8">
                                        {unitSystem === 'metric' ? `${toDisplay(v)}` : `${v}'`}
                                    </text>
                                ))}
                            </g>
                        )}

                        {/* North arrow - positioned in top-right margin outside drawing */}
                        <g transform={`translate(${width * scale + 50}, 30)`}>
                            <polygon points="0,-20 5,0 0,-5 -5,0" fill="#1e293b" />
                            <text x={0} y={-24} textAnchor="middle" fontSize="10" fontWeight="700" fill="#1e293b">N</text>
                        </g>

                        {/* Scale bar */}
                        <g transform={`translate(20, ${height * scale + 35})`}>
                            <rect x={0} y={0} width={60} height={6} fill="#1e293b" />
                            <rect x={60} y={0} width={60} height={6} fill="#fff" stroke="#1e293b" strokeWidth={1} />
                            <text x={0} y={18} fontSize="8" fill="#1e293b">0</text>
                            <text x={60} y={18} fontSize="8" fill="#1e293b" textAnchor="middle">
                                {unitSystem === 'metric' ? `${toDisplay(Math.round(60 / scale))}` : `${Math.round(60 / scale)}'`}
                            </text>
                            <text x={120} y={18} fontSize="8" fill="#1e293b" textAnchor="middle">
                                {unitSystem === 'metric' ? `${toDisplay(Math.round(120 / scale))}` : `${Math.round(120 / scale)}'`}
                            </text>
                            <text x={140} y={6} fontSize="9" fill="#64748b">SCALE ({unitSystem === 'metric' ? 'M' : 'FT'})</text>
                        </g>
                    </g>
                </svg>
            </div>

            {/* Technical Legend */}
            <div style={{
                marginTop: 16,
                padding: 16,
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 4,
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 12,
                fontSize: 11,
                fontWeight: 500
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 16, background: '#fff', border: '2px solid #334155', position: 'relative' }}>
                        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: 4, height: 4, background: '#64748b', borderRadius: '50%' }} />
                    </div>
                    <span style={{ color: '#475569' }}>PARKING STALL</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 10, background: '#f1f5f9', border: '1.5px solid #64748b' }} />
                    <span style={{ color: '#475569' }}>PARKING AISLE ({unitSystem === 'metric' ? `${toDisplay(24)} m` : "24'"} TYP.)</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 10, background: '#f1f5f9', border: '2px solid #475569', position: 'relative' }}>
                        <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 2, background: '#eab308', transform: 'translateY(-50%)' }} />
                    </div>
                    <span style={{ color: '#475569' }}>DRIVE LANE</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <svg width="28" height="16" viewBox="0 0 28 16">
                        <polygon points="6,4 18,8 6,12" fill="#64748b" />
                    </svg>
                    <span style={{ color: '#475569' }}>TRAFFIC FLOW</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 16, background: '#dcfce7', border: '2.5px solid #059669' }} />
                    <span style={{ color: '#475569' }}>ACCESS POINT</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 28, height: 14, border: '1.5px dashed #64748b', background: 'repeating-linear-gradient(45deg, transparent, transparent 2px, #f1f5f9 2px, #f1f5f9 4px)' }} />
                    <span style={{ color: '#475569' }}>SETBACK LINE</span>
                </div>
            </div>

            {/* Drawing Notes */}
            <div style={{ marginTop: 16, padding: 12, background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 4, fontSize: 10, color: '#92400e' }}>
                <strong>NOTES:</strong>
                <ol style={{ margin: '8px 0 0 16px', padding: 0 }}>
                    <li>All dimensions in feet unless noted otherwise</li>
                    <li>Parking stall size: {stallWidth}' × {stallLength}' (90° angle)</li>
                    <li>Aisle width: {aisleWidth}' (two-way traffic)</li>
                    <li>Setback from property line: {setback}'</li>
                    <li>Verify all dimensions in field prior to construction</li>
                </ol>
            </div>
        </div>
    );
}
