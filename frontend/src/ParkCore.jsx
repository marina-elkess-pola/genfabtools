import React, { useState, useRef, useEffect } from 'react';
import { getMe } from './api2';
// temporarily disable grouped panels to fix compile error
// import PanelSection from './components/PanelSection';
// import './ParkCorePanel.css';
import ThreeView from './ThreeView';
import DrawingToolkit from './components/DrawingToolkit2';
import parkingCodes from './parking_codes.json';
import { generateBaselineSchemes, generateStructuralSchemes, AutoGeom, getAvailableParkingCodes } from './auto';

function numberOrZero(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
}

// Unit conversion constants/helpers
const M_TO_FT = 3.28084;
const M2_TO_FT2 = 10.76391041671;
function metersToFeet(m) { return Number(m) * M_TO_FT; }
function feetToMeters(ft) { return Number(ft) / M_TO_FT; }
function m2ToFt2(m2) { return Number(m2) * M2_TO_FT2; }
function ft2ToM2(ft2) { return Number(ft2) / M2_TO_FT2; }

export default function ParkCore() {
    const [lotArea, setLotArea] = useState(1000); // m²
    const [stallWidth, setStallWidth] = useState(2.6); // m
    const [unitSystem, setUnitSystem] = useState(() => localStorage.getItem('unitSystem') || 'metric'); // 'metric' | 'imperial'
    const [stallDepth, setStallDepth] = useState(5.0); // m
    const [aislePercent, setAislePercent] = useState(30); // % of area for aisles/circulation
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [userProfile, setUserProfile] = useState(null);

    // drawing editor state (simple SVG polygon editor)
    const [points, setPoints] = useState([]); // array of {x,y}
    const [closed, setClosed] = useState(false);
    const svgRef = useRef(null);

    // UX helpers
    const [snapToGrid, setSnapToGrid] = useState(true);
    const [gridSize, setGridSize] = useState(20); // svg units
    const [unitsPerMeter, setUnitsPerMeter] = useState(1); // how many svg units == 1 meter
    const [draggingIndex, setDraggingIndex] = useState(null);
    const [cursorPoint, setCursorPoint] = useState(null); // live cursor in svg coords
    const [angleSnap, setAngleSnap] = useState(15); // degrees
    const [snapToGeometry, setSnapToGeometry] = useState(true);
    const [snapThreshold, setSnapThreshold] = useState(12); // svg units
    const [fixedScreenHandles, setFixedScreenHandles] = useState(true); // keep strokes/handles a constant screen size by default
    const [worldHandleRadius, setWorldHandleRadius] = useState(8); // user units when world-scaled
    const [worldStrokeWidth, setWorldStrokeWidth] = useState(1);
    const [mode, setMode] = useState('draw'); // draw | pan | measure | stalls
    const [measurePoints, setMeasurePoints] = useState([]);
    const [measurePlacePending, setMeasurePlacePending] = useState(null); // {a:{x,y}, b:{x,y}}
    const [snapMeasure, setSnapMeasure] = useState(true); // snap measuring to geometry by default
    const [measureAnnotations, setMeasureAnnotations] = useState([]); // persistent dims: {a:{x,y}, b:{x,y}}
    const [showDimensions, setShowDimensions] = useState(true);
    const [editingDimIndex, setEditingDimIndex] = useState(null); // index of dimension being edited
    const [editingDimValue, setEditingDimValue] = useState(''); // string meters value in input
    const [editingDimFixed, setEditingDimFixed] = useState(null); // 'a' | 'b' chosen at edit start, not user-visible
    const [stallsPreview, setStallsPreview] = useState([]);
    // selected stalls indices for the active level (array of indices)
    const [selectedStalls, setSelectedStalls] = useState([]);
    // structured parking levels support
    const DEFAULT_FLOOR_HEIGHT = 3.5; // meters per level
    const [levels, setLevels] = useState([{ id: 'L1', name: 'Level 1', stallsPreview: [], visible: true, elevation: 0 }]);
    const [currentLevelIndex, setCurrentLevelIndex] = useState(0);
    const [editingLevelIdx, setEditingLevelIdx] = useState(null);
    const [editingLevelName, setEditingLevelName] = useState('');
    const [editingElevationIdx, setEditingElevationIdx] = useState(null);
    const [editingElevationValue, setEditingElevationValue] = useState('');
    const [orientationDeg, setOrientationDeg] = useState(0);
    // Construction plane (CPlane) like Rhino: origin and X direction
    const [cplaneOrigin, setCplaneOrigin] = useState({ x: 0, y: 0 });
    const [cplaneXDir, setCplaneXDir] = useState({ x: 1, y: 0 }); // unit vector
    const [cplaneVisible, setCplaneVisible] = useState(true);
    const [cplaneMode, setCplaneMode] = useState(null); // null | 'setOrigin' | 'setXDir'
    // view mode: 'top' draws orthographic grid, '3d' draws a tilted plane visualization
    const [viewMode, setViewMode] = useState('top'); // 'top' | '3d'
    const [stallAngleDeg, setStallAngleDeg] = useState(0); // 0,45,60
    // Optional override for drive width (meters). Null = use code presets
    const [driveWidthMeters, setDriveWidthMeters] = useState(null);
    // Optional override for row spacing (Y)
    const [rowSpacingMeters, setRowSpacingMeters] = useState(null); // Y spacing override (meters)
    // User-controlled column grid angle (degrees). Null = use CPlane/grid params
    const [columnGridAngleDeg, setColumnGridAngleDeg] = useState(null);
    // Multiple grids metadata
    const [columnGrids, setColumnGrids] = useState([]);
    // saved schemes/iterations for comparison
    const [schemes, setSchemes] = useState([]); // {id,name,points,closed,stallsPreview,lotArea,color,visible}
    // Column grid parameters used by both generator and dashed-grid renderer (single source of truth)
    const [columnGridParams, setColumnGridParams] = useState(null); // { angle, spacingX, spacingY, offsetX, offsetY }
    const [columnsLocked, setColumnsLocked] = useState(false);
    const [schemeName, setSchemeName] = useState('');
    const [editingSchemeId, setEditingSchemeId] = useState(null);
    // small UI hint: briefly highlight an applied scheme overlay
    const [highlightedSchemeId, setHighlightedSchemeId] = useState(null);
    // Auto-design panel UI state
    const [autoPanelOpen, setAutoPanelOpen] = useState(false); // expanded vs compact pill
    const [autoPanelHidden, setAutoPanelHidden] = useState(false); // hide entirely
    const [autoPanelCorner, setAutoPanelCorner] = useState('br'); // 'tr' | 'br' | 'tl' | 'bl'
    // Overlay visibility toggles for auto design previews
    const [showGridOverlay, setShowGridOverlay] = useState(true);
    // Aisles are merged into Streets; no separate overlay toggle
    const [showStreetsOverlay, setShowStreetsOverlay] = useState(true);
    const [showAccessOverlay, setShowAccessOverlay] = useState(true);
    const [showRampsOverlay, setShowRampsOverlay] = useState(true);
    const [showColumnsOverlay, setShowColumnsOverlay] = useState(true);
    const [showStallsOverlay, setShowStallsOverlay] = useState(true);
    const [showLegend, setShowLegend] = useState(false);
    // High-contrast overlay palette for better visual separation
    // More transparent, subtle palette (low visual weight, clear layering)
    const overlayPalette = {
        // Warm neutral for stalls (soft gold)
        stalls: { fill: 'rgba(220,170,40,0.16)', stroke: 'rgba(180,130,25,0.55)' },
        // Light desaturated teal for aisles
        aisles: { fill: 'rgba(40,160,150,0.14)', stroke: 'rgba(30,120,115,0.50)' },
        // Cool gray for streets (low dominance)
        streets: { fill: 'rgba(110,120,130,0.14)', stroke: 'rgba(90,100,110,0.45)' },
        // Soft green for access zones
        access: { fill: 'rgba(120,190,120,0.18)', stroke: 'rgba(90,150,90,0.55)' },
        // Muted terracotta for ramps
        ramps: { fill: 'rgba(200,110,70,0.18)', stroke: 'rgba(170,90,55,0.60)' },
        // Neutral charcoal with slight transparency for columns
        columns: { fill: 'rgba(60,60,60,0.28)', stroke: 'rgba(40,40,40,0.65)' },
    };

    // persist unit system selection
    useEffect(() => {
        try { localStorage.setItem('unitSystem', unitSystem); } catch (e) { }
    }, [unitSystem]);

    // one-shot / ephemeral measurement state (doesn't change persistent `mode`)
    const [oneShotMeasureActive, setOneShotMeasureActive] = useState(false);
    const [oneShotMeasureTempAnn, setOneShotMeasureTempAnn] = useState(null); // {a,b,label,offset,aIdx,bIdx}
    // Derived flag used throughout render/handlers to treat either persistent measure-mode or one-shot as "measuring"
    const measureActive = (mode === 'measure' || oneShotMeasureActive);

    // Global ESC handler: cancel any pending or one-shot measurements
    useEffect(() => {
        const onKey = (ev) => {
            if (ev.key === 'Escape' || ev.key === 'Esc') {
                setMeasurePoints([]);
                setMeasurePlacePending(null);
                setOneShotMeasureActive(false);
                setOneShotMeasureTempAnn(null);
                setEditingDimIndex(null);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    function getAutoPanelXY(w, h) {
        const pad = 16;
        const vb = { x: 0, y: 0, w: window.innerWidth || 800, h: window.innerHeight || 600 };
        switch (autoPanelCorner) {
            case 'tr': return { x: vb.x + vb.w - w - pad, y: vb.y + pad };
            case 'tl': return { x: vb.x + pad, y: vb.y + pad };
            case 'bl': return { x: vb.x + pad, y: vb.y + vb.h - h - pad };
            case 'br':
            default: return { x: vb.x + vb.w - w - pad, y: vb.y + vb.h - h - pad };
        }
    }
    function cycleAutoPanelCorner() {
        const order = ['tr', 'br', 'bl', 'tl'];
        const i = order.indexOf(autoPanelCorner);
        setAutoPanelCorner(order[(i + 1) % order.length]);
    }
    // selection & clipboard for copy/paste
    const [selectedPoints, setSelectedPoints] = useState([]); // array of point indices
    const [clipboardPoints, setClipboardPoints] = useState(null); // array of {x,y}
    // clipping acceptance threshold and diagnostics for clipped fragments
    const [clipAcceptance, setClipAcceptance] = useState(0.25); // fraction of full stall area required to accept clipped stall
    const [clipDiagnostics, setClipDiagnostics] = useState([]); // array of {ratio, poly}
    const [showClipDiagnostics, setShowClipDiagnostics] = useState(false);
    const [columnsRespectExisting, setColumnsRespectExisting] = useState(true);
    const [columnDebugPoints, setColumnDebugPoints] = useState([]); // {x,y,status}
    const [showColumnDebug, setShowColumnDebug] = useState(false);
    const [columnSizeMeters, setColumnSizeMeters] = useState(0.5);
    const [columnShape, setColumnShape] = useState('square'); // 'square' | 'circle' | 'template'
    const [columnTemplate, setColumnTemplate] = useState(null); // { name, poly: [{x,y}], unitSize }
    const fileInputRef = React.useRef(null);
    const [columnClearanceMeters, setColumnClearanceMeters] = useState(0.6);
    const [showColumnGrid, setShowColumnGrid] = useState(false);
    const [manualGridEnabled, setManualGridEnabled] = useState(false);
    const [manualGridSpacingX, setManualGridSpacingX] = useState(7.5);
    const [manualGridSpacingY, setManualGridSpacingY] = useState(7.5);
    const [columnGridPreviewPoints, setColumnGridPreviewPoints] = useState([]);
    // Aisle generation options
    const [autoConnectAisles, setAutoConnectAisles] = useState(true);
    const [aisleColumnGapMeters, setAisleColumnGapMeters] = useState(0.2); // extra clearance for aisle bands
    // Run result counts
    const [lastRunCounts, setLastRunCounts] = useState(null); // {stalls, aisles, connectors, columns}
    // Perimeter street / spine controls
    const [perimeterStreetEnabled, setPerimeterStreetEnabled] = useState(true);
    const [perimeterStreetOffsetMeters, setPerimeterStreetOffsetMeters] = useState(1.0);
    const [connectorSpacingMeters, setConnectorSpacingMeters] = useState(0.0);
    const [minConnectorCount, setMinConnectorCount] = useState(2);
    const [highlightConnectors, setHighlightConnectors] = useState(false);
    const [codeDesign, setCodeDesign] = useState('underground');
    const [parkingCode, setParkingCode] = useState('GENERIC'); // Building code for parking standards
    // Parking-type specific knobs
    const [surfaceLevels, setSurfaceLevels] = useState(1);
    const [surfacePerimeterStalls, setSurfacePerimeterStalls] = useState(true);
    const [landscapeBufferMeters, setLandscapeBufferMeters] = useState(1.0);
    const [evStallPercent, setEvStallPercent] = useState(5);
    const [undergroundLevels, setUndergroundLevels] = useState(2);
    const [undergroundColumnSpacingMeters, setUndergroundColumnSpacingMeters] = useState(7.5);
    const [enforceOrthogonalLayout, setEnforceOrthogonalLayout] = useState(true);
    const [validationWarnings, setValidationWarnings] = useState([]);
    // Structural span tolerance (meters) for local column adaptation
    const [spanToleranceMeters, setSpanToleranceMeters] = useState(0.5);
    // Minimum turning radius (meters) for aisle connectors
    const [minTurningRadiusMeters, setMinTurningRadiusMeters] = useState(6.0);
    const [addCentralSpine, setAddCentralSpine] = useState(false);
    // Minimal markers toggle (simplify point/dimension labels)
    const [minimalMarkers, setMinimalMarkers] = useState(false);
    // Auto design knobs: access & ramp placement plus core obstacles
    const [accessPlacement, setAccessPlacement] = useState('auto'); // 'auto' | 'min-edge' | 'max-edge' | 'center'
    const [rampPlacement, setRampPlacement] = useState('edge-min'); // 'edge-min' | 'edge-max' | 'center'
    // Circulation type selection (controls widths)
    const [aisleType, setAisleType] = useState('two-way'); // 'one-way' | 'two-way'
    const [streetType, setStreetType] = useState('two-way'); // 'one-way' | 'two-way' | 'spine'
    // Circulation presets
    const [circulationMode, setCirculationMode] = useState('loop'); // 'loop' | 'spine' | 'grid'
    const [bayOrientation, setBayOrientation] = useState('double-loaded'); // 'single-loaded' | 'double-loaded'
    const [avoidDeadEnds, setAvoidDeadEnds] = useState(true);
    const [separateEntryExit, setSeparateEntryExit] = useState(false);
    // Ramp sizing controls
    const [entryHeightMeters, setEntryHeightMeters] = useState(0.0); // rise from ground to this level (m)
    const [levelHeightMeters, setLevelHeightMeters] = useState(3.5); // typical level-to-level height (m)
    const [accessRampMaxSlopePercent, setAccessRampMaxSlopePercent] = useState(12); // % grade
    const [internalRampMaxSlopePercent, setInternalRampMaxSlopePercent] = useState(12); // % grade
    // Design priority for ranking schemes
    const [designPriority, setDesignPriority] = useState(null); // 'capacity' | 'comfort' | 'flow' | 'accessibility' | 'cost' | 'future' | null
    // Advanced inputs (string forms for comma-separated lists)
    const [anglesDegInput, setAnglesDegInput] = useState('0,12,-12,24,-24');
    const [stallAnglesInput, setStallAnglesInput] = useState('90,60');
    const [spanPresetsInput, setSpanPresetsInput] = useState('7.0,7.5,8.0');

    // Keep a simple preview lattice in sync with grid params and lot bounds (moved below state declarations to avoid TDZ)
    useEffect(() => {
        // Skip /me checks to avoid noisy dev 500/connection errors when backend isn't running
        // Previously attempted dev-only fetch; now disabled.
        if (!showColumnGrid || !points || points.length < 3) { setColumnGridPreviewPoints([]); return; }
        const angle = (columnGridParams && typeof columnGridParams.angle === 'number') ? columnGridParams.angle : Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
        const centroid = { x: points.reduce((s, p) => s + p.x, 0) / points.length, y: points.reduce((s, p) => s + p.y, 0) / points.length };
        const rotLot = rotatePolygon(points, centroid, -angle);
        const xsR = rotLot.map(p => p.x), ysR = rotLot.map(p => p.y);
        const minXr = Math.min(...xsR), maxXr = Math.max(...xsR), minYr = Math.min(...ysR), maxYr = Math.max(...ysR);
        let spacingX = null, spacingY = null, offX = 0, offY = 0;
        if (columnGridParams && columnGridParams.spacingX && columnGridParams.spacingY) {
            spacingX = columnGridParams.spacingX; spacingY = columnGridParams.spacingY;
            offX = columnGridParams.offsetX || 0; offY = columnGridParams.offsetY || 0;
        } else if (manualGridEnabled) {
            spacingX = Math.max(1e-3, Number(manualGridSpacingX || 1)) * Number(unitsPerMeter || 1);
            spacingY = Math.max(1e-3, Number(manualGridSpacingY || manualGridSpacingX || 1)) * Number(unitsPerMeter || 1);
            offX = ((minXr + spacingX / 2) % spacingX + spacingX) % spacingX;
            offY = ((minYr + spacingY / 2) % spacingY + spacingY) % spacingY;
        } else { setColumnGridPreviewPoints([]); return; }
        const startGX = Math.floor((minXr - offX) / spacingX) * spacingX + offX;
        const startGY = Math.floor((minYr - offY) / spacingY) * spacingY + offY;
        const pts = [];
        for (let x = startGX; x <= maxXr; x += spacingX) {
            for (let y = startGY; y <= maxYr; y += spacingY) {
                const world = rotatePoint({ x, y }, centroid, angle);
                pts.push(world);
            }
        }
        setColumnGridPreviewPoints(pts);
    }, [showColumnGrid, points, columnGridParams, manualGridEnabled, manualGridSpacingX, manualGridSpacingY, unitsPerMeter, cplaneXDir]);

    // --- basic geometry helpers ---
    function makeColumnRect(center, thicknessXUnits, thicknessYUnits) {
        const halfX = thicknessXUnits / 2, halfY = thicknessYUnits / 2;
        return { minX: center.x - halfX, maxX: center.x + halfX, minY: center.y - halfY, maxY: center.y + halfY };
    }
    function pointInPoly(pt, poly) {
        // Delegate to canonical implementation `pointInPolygon` (defined later)
        return pointInPolygon(pt, poly);
    }
    function rectIntersectsPolygon(rect, poly) {
        // quick tests: any vertex inside rect
        for (let i = 0; i < poly.length; i++) {
            const p = poly[i];
            if (p.x >= rect.minX && p.x <= rect.maxX && p.y >= rect.minY && p.y <= rect.maxY) return true;
        }
        // any rect corner inside polygon
        const corners = [
            { x: rect.minX, y: rect.minY },
            { x: rect.maxX, y: rect.minY },
            { x: rect.maxX, y: rect.maxY },
            { x: rect.minX, y: rect.maxY },
        ];
        for (const c of corners) { if (pointInPoly(c, poly)) return true; }
        return false;
    }
    function canConnectWithTurningRadius(a, b, Runits) {
        return Number(Runits) > 0 && Number.isFinite(a?.x) && Number.isFinite(a?.y) && Number.isFinite(b?.x) && Number.isFinite(b?.y);
    }
    const [validateResults, setValidateResults] = useState(null); // array of {type,message,items,suggestion}
    // OSNAP options
    const [osnapEndpoint, setOsnapEndpoint] = useState(true);
    const [osnapMid, setOsnapMid] = useState(true);
    const [osnapCenter, setOsnapCenter] = useState(false);
    const [osnapPerp, setOsnapPerp] = useState(true);
    const [osnapParallel, setOsnapParallel] = useState(true);
    const [osnapOrtho, setOsnapOrtho] = useState(true);
    const [smartTrack, setSmartTrack] = useState(true);

    // Quick rectangle insertion tool
    const [rectToolWidthMeters, setRectToolWidthMeters] = useState(30);
    const [rectToolHeightMeters, setRectToolHeightMeters] = useState(20);
    const [rectToolCenter, setRectToolCenter] = useState({ x: 0, y: 0 });
    const [rectToolAngleDeg, setRectToolAngleDeg] = useState(0);
    function insertRectangleFromTool() {
        const upm = Number(unitsPerMeter || 1);
        const w = Math.max(1e-3, Number(rectToolWidthMeters || 0)) * upm;
        const h = Math.max(1e-3, Number(rectToolHeightMeters || 0)) * upm;
        const ang = (Number(rectToolAngleDeg || 0) * Math.PI) / 180;
        const c = { x: Number(rectToolCenter.x || 0), y: Number(rectToolCenter.y || 0) };
        const t = { x: Math.cos(ang), y: Math.sin(ang) };
        const n = { x: -t.y, y: t.x };
        const hx = (w / 2), hy = (h / 2);
        const corners = [
            { x: c.x - t.x * hx - n.x * hy, y: c.y - t.y * hx - n.y * hy },
            { x: c.x + t.x * hx - n.x * hy, y: c.y + t.y * hx - n.y * hy },
            { x: c.x + t.x * hx + n.x * hy, y: c.y + t.y * hx + n.y * hy },
            { x: c.x - t.x * hx + n.x * hy, y: c.y - t.y * hx + n.y * hy },
        ];
        setPoints(corners);
        setClosed(true);
        pushHistoryFrom(corners, true, measureAnnotations);
    }

    // insertion mode for manual circulation/ramps/access/core placement
    const [insertionMode, setInsertionMode] = useState(null); // 'aisle' | 'street' | 'ramp' | 'access' | 'core' | null
    const [insertionStart, setInsertionStart] = useState(null); // {x,y}
    const [insertionRect, setInsertionRect] = useState(null); // {x,y,w,h}
    // selection marquee and group-drag state
    const [marqueeRect, setMarqueeRect] = useState(null); // {x,y,w,h} in user units
    const [marqueeStart, setMarqueeStart] = useState(null);
    const [pendingMarqueeStart, setPendingMarqueeStart] = useState(null); // {x,y,clientX,clientY}
    const [groupDragging, setGroupDragging] = useState(false);
    const [groupDragOrigin, setGroupDragOrigin] = useState(null); // {x,y}
    const [groupOriginalPoints, setGroupOriginalPoints] = useState([]); // [{x,y}]
    const [hoverInsert, setHoverInsert] = useState(null); // {i, p:{x,y}} nearest segment and projection

    // history (undo/redo)
    const [history, setHistory] = useState([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const pushHistoryFrom = (pts, closedFlag, annotations) => {
        const snap = {
            points: (pts || []).map(p => ({ x: p.x, y: p.y })),
            closed: !!closedFlag,
            measureAnnotations: (annotations !== undefined ? annotations : measureAnnotations).map(m => ({ a: { ...m.a }, b: { ...m.b }, label: m.label ? { ...m.label } : undefined, offset: m.offset, aIdx: m.aIdx, bIdx: m.bIdx }))
        };
        setHistory(prev => {
            const next = prev.slice(0, historyIndex + 1);
            next.push(snap);
            setHistoryIndex(next.length - 1);
            return next;
        });
    };
    const undo = () => {
        if (historyIndex <= 0) return;
        const idx = historyIndex - 1;
        const state = history[idx];
        setPoints(state.points.slice());
        setClosed(state.closed);
        setMeasureAnnotations((state.measureAnnotations || []).map(m => ({ a: { ...m.a }, b: { ...m.b }, label: m.label ? { ...m.label } : undefined, offset: m.offset, aIdx: m.aIdx, bIdx: m.bIdx })));
        setHistoryIndex(idx);
    };
    const redo = () => {
        if (historyIndex >= history.length - 1) return;
        const idx = historyIndex + 1;
        const state = history[idx];
        setPoints(state.points.slice());
        setClosed(state.closed);
        setMeasureAnnotations((state.measureAnnotations || []).map(m => ({ a: { ...m.a }, b: { ...m.b }, label: m.label ? { ...m.label } : undefined, offset: m.offset, aIdx: m.aIdx, bIdx: m.bIdx })));
        setHistoryIndex(idx);
    };

    const VB_WIDTH = 1600;
    const VB_HEIGHT = 960;
    const [viewBox, setViewBox] = useState({ x: 0, y: 0, w: VB_WIDTH, h: VB_HEIGHT });
    const [isPanning, setIsPanning] = useState(false);
    const panStartRef = useRef(null);
    const suppressNextClickRef = useRef(false); // prevent click after drags/pan

    // Initialize rectangle tool center after viewBox exists
    useEffect(() => {
        setRectToolCenter({ x: viewBox.x + viewBox.w / 2, y: viewBox.y + viewBox.h / 2 });
    }, []);

    // Rectangle controls merged into DrawingToolkit component

    const calc = () => {
        const A_display = numberOrZero(lotArea);
        const w_display = numberOrZero(stallWidth);
        const d_display = numberOrZero(stallDepth);
        // convert displayed units to meters for internal calculation
        const A = unitSystem === 'imperial' ? ft2ToM2(A_display) : A_display;
        const w = unitSystem === 'imperial' ? feetToMeters(w_display) : w_display;
        const d = unitSystem === 'imperial' ? feetToMeters(d_display) : d_display;
        const aisle = Math.min(Math.max(numberOrZero(aislePercent), 0), 90);
        const stallArea = w * d;
        const usable = A * (1 - aisle / 100);
        const est = stallArea > 0 ? Math.floor(usable / stallArea) : 0;
        const density = est / A || 0; // stalls per m² (internal)
        return { A, w, d, aisle, stallArea, usable, est, density };
    };

    const { A, w, d, aisle, stallArea, usable, est, density } = calc();

    // code selection
    const codeKeys = Object.keys(parkingCodes || {});
    const [codeFilter, setCodeFilter] = useState('');
    // produce alphabetically sorted keys by display name
    const sortedCodeKeys = codeKeys.slice().sort((a, b) => {
        const an = (parkingCodes[a]?.name || a).toString();
        const bn = (parkingCodes[b]?.name || b).toString();
        return an.localeCompare(bn);
    });
    const filteredCodeKeys = sortedCodeKeys.filter(k => {
        if (!codeFilter) return true;
        const needle = codeFilter.toLowerCase();
        const name = (parkingCodes[k]?.name || k).toString().toLowerCase();
        return name.includes(needle) || k.toLowerCase().includes(needle);
    });

    // selected code state and resolved currentCode
    const [selectedCode, setSelectedCode] = useState(filteredCodeKeys.length > 0 ? filteredCodeKeys[0] : (codeKeys[0] || ''));
    const currentCode = parkingCodes[selectedCode] || null;

    // Export GeoJSON for current preview (lots + stalls/features)
    function exportGeoJSON() {
        const fc = { type: 'FeatureCollection', features: [] };
        if (points && points.length >= 3) {
            fc.features.push({ type: 'Feature', properties: { type: 'lot' }, geometry: { type: 'Polygon', coordinates: [[...points.map(p => [p.x, p.y]), [points[0].x, points[0].y]]] } });
        }
        const lev = (levels && levels.length > 0) ? levels[0] : null;
        const items = lev?.stallsPreview || stallsPreview || [];
        for (const it of items) {
            if (it.poly && it.poly.length >= 3) {
                fc.features.push({ type: 'Feature', properties: { type: it.type || 'stall' }, geometry: { type: 'Polygon', coordinates: [[...it.poly.map(p => [p.x, p.y]), [it.poly[0].x, it.poly[0].y]]] } });
            }
        }
        const blob = new Blob([JSON.stringify(fc, null, 2)], { type: 'application/geo+json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'parkcore-export.geojson'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    }

    // Simple DXF export: writes each polygon as a POLYLINE
    function exportDXF() {
        const lines = [];
        function add(code, value) { lines.push(String(code)); lines.push(String(value)); }
        add(0, 'SECTION'); add(2, 'ENTITIES');

        const pushPoly = (poly) => {
            if (!poly || poly.length < 3) return;
            add(0, 'POLYLINE'); add(8, '0'); add(66, '1'); add(70, '1');
            for (const v of poly) {
                add(0, 'VERTEX'); add(8, '0'); add(10, v.x); add(20, v.y);
            }
            add(0, 'SEQEND');
        };

        if (points && points.length >= 3) pushPoly(points);
        const lev = (levels && levels.length > 0) ? levels[0] : null;
        const items = lev?.stallsPreview || stallsPreview || [];
        for (const it of items) {
            if (it.poly && it.poly.length >= 3) pushPoly(it.poly);
        }

        add(0, 'ENDSEC'); add(0, 'EOF');
        const blob = new Blob([lines.join('\n')], { type: 'application/dxf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'parkcore-export.dxf'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    }

    // Export the current SVG canvas as an SVG file
    function exportSVG() {
        try {
            const svg = svgRef.current;
            if (!svg) return alert('No SVG canvas available to export');
            // clone to avoid modifying live DOM
            const clone = svg.cloneNode(true);
            // inline computed styles by serializing outerHTML (simple approach)
            const str = new XMLSerializer().serializeToString(clone);
            const blob = new Blob([str], { type: 'image/svg+xml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'parkcore-canvas.svg'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        } catch (e) {
            console.error('exportSVG failed', e);
            alert('Failed to export SVG: ' + (e && e.message));
        }
    }

    // Export current preview as CSV (one row per item)
    function exportCSV() {
        try {
            const rows = [];
            rows.push(['type', 'x', 'y', 'hw', 'hd', 'poly'].join(','));
            const lev = (levels && levels.length > 0) ? levels[0] : null;
            const items = lev?.stallsPreview || stallsPreview || [];
            for (const it of items) {
                const type = it.type || 'stall';
                const x = (it.x !== null && it.x !== undefined) ? it.x : '';
                const y = (it.y !== null && it.y !== undefined) ? it.y : '';
                const hw = (it.hw !== null && it.hw !== undefined) ? it.hw : '';
                const hd = (it.hd !== null && it.hd !== undefined) ? it.hd : '';
                const poly = it.poly ? JSON.stringify(it.poly.map(p => [p.x, p.y])) : '';
                // wrap poly in quotes and escape any quotes inside
                const safePoly = '"' + poly.replace(/"/g, '""') + '"';
                rows.push([type, x, y, hw, hd, safePoly].join(','));
            }
            const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a'); a.href = url; a.download = 'parkcore-export.csv'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
        } catch (e) {
            console.error('exportCSV failed', e);
            alert('Failed to export CSV: ' + (e && e.message));
        }
    }

    function computePolygonArea(pts) {
        // Shoelace formula. pts: [{x,y},...]
        if (!pts || pts.length < 3) return 0;
        let sum = 0;
        for (let i = 0; i < pts.length; i++) {
            const a = pts[i];
            const b = pts[(i + 1) % pts.length];
            sum += a.x * b.y - b.x * a.y;
        }
        return Math.abs(sum) / 2; // area in SVG user units — we'll treat as m² if user draws to scale
    }

    // Helpers for code-derived requirements
    function requiredAccessibleStalls(totalStalls) {
        const pct = Number(currentCode?.accessiblePercent || 0);
        if (!Number.isFinite(totalStalls) || totalStalls <= 0) return 0;
        return Math.ceil((totalStalls * pct) / 100);
    }

    function requiredExtinguishers(totalStalls) {
        const ratio = Number(currentCode?.extinguisherRatio || 200);
        if (!Number.isFinite(totalStalls) || totalStalls <= 0) return 0;
        return Math.ceil(totalStalls / Math.max(1, ratio));
    }

    function handleSvgClick(e) {
        // Avoid creating points while dragging or panning/marquee operations
        if (suppressNextClickRef.current || draggingIndex !== null || groupDragging || isPanning || marqueeStart) {
            suppressNextClickRef.current = false;
            return;
        }
        const svg = svgRef.current;
        if (!svg) return;
        const pt = svg.createSVGPoint();
        pt.x = e.clientX; pt.y = e.clientY;
        const ctm = svg.getScreenCTM().inverse();
        const cursor = pt.matrixTransform(ctm);
        // use snapped cursor (considering keys/modifiers)
        const snapped = getSnappedPoint(cursor, e);
        // CPlane interactive modes: set origin or set X direction by clicking on canvas
        if (cplaneMode === 'setOrigin') {
            setCplaneOrigin({ x: snapped.x, y: snapped.y });
            setCplaneMode(null);
            return;
        }
        if (cplaneMode === 'setXDir') {
            const ox = cplaneOrigin.x, oy = cplaneOrigin.y;
            const vx = snapped.x - ox, vy = snapped.y - oy;
            const len = Math.hypot(vx, vy);
            if (len < 1e-6) { alert('Pick a point away from the origin to set X direction'); setCplaneMode(null); return; }
            setCplaneXDir({ x: vx / len, y: vy / len });
            setCplaneMode(null);
            return;
        }
        // If measure mode (persistent or one-shot), handle measuring regardless of closed/open
        if (measureActive) {
            const p = snapMeasure ? getMeasureSnappedPoint(cursor, e) : cursor;
            // One-shot flow: two-click ephemeral measurement (do not persist annotations)
            if (oneShotMeasureActive) {
                setMeasurePoints(prev => {
                    const idx = snapMeasure ? getNearestVertexIndex(p) : -1;
                    if (!prev || prev.length === 0) {
                        return [{ x: p.x, y: p.y, idx: idx >= 0 ? idx : undefined }];
                    }
                    // second click: produce temp annotation and exit one-shot mode
                    const a = prev[0];
                    const b = { x: p.x, y: p.y, idx: idx >= 0 ? idx : undefined };
                    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
                    // compute signed offset from midpoint to clicked point along normal
                    const dx = b.x - a.x, dy = b.y - a.y;
                    const len = Math.hypot(dx, dy) || 1;
                    const ux = dx / len, uy = dy / len; // along AB
                    const nx = -uy, ny = ux; // normal
                    const off = (p.x - mx) * nx + (p.y - my) * ny;
                    const label = { x: mx, y: my };
                    setOneShotMeasureTempAnn({ a, b, label, offset: off, aIdx: a.idx, bIdx: b.idx });
                    // small timeout to allow render of temp ann then clear points and deactivate
                    setTimeout(() => {
                        setMeasurePoints([]);
                        setOneShotMeasureActive(false);
                        setOneShotMeasureTempAnn(null);
                    }, 50);
                    return [];
                });
                return;
            }
            // persistent measure mode: accumulate two clicks then prompt for label placement
            setMeasurePoints(prev => {
                const idx = snapMeasure ? getNearestVertexIndex(p) : -1;
                const next = [...prev, { x: p.x, y: p.y, idx: idx >= 0 ? idx : undefined }];
                if (next.length === 2) {
                    // two points picked: ask user to place the dimension label/leader (third click)
                    setMeasurePlacePending({ a: next[0], b: next[1], aIdx: next[0].idx, bIdx: next[1].idx });
                    return [];
                }
                return next;
            });
            return;
        }

        // clicking on an existing segment inserts a point (works even when closed)
        const segIdx = findSegmentIndexNearPoint(snapped, points, snapThreshold);
        if (segIdx >= 0) {
            const insertAt = segIdx + 1;
            // Use the same projection shown by hover '+' if available; otherwise project cursor to segment
            let ins = hoverInsert && hoverInsert.p ? hoverInsert.p : null;
            if (!ins) {
                const a = points[segIdx];
                const b = (segIdx + 1 < points.length) ? points[segIdx + 1] : points[0];
                ins = projectPointToSegment(snapped, a, b);
            }
            const updatedPoints = points.slice();
            updatedPoints.splice(insertAt, 0, { x: ins.x, y: ins.y });
            // Adjust any bound dimension indices at or after the insertion point
            const updatedAnns = measureAnnotations.map(m => {
                const adj = (idx) => Number.isInteger(idx) ? (idx >= insertAt ? idx + 1 : idx) : idx;
                return { ...m, aIdx: adj(m.aIdx), bIdx: adj(m.bIdx) };
            });
            setPoints(updatedPoints);
            setMeasureAnnotations(updatedAnns);
            // Ensure we don't immediately treat the new point as selected/dragged
            setSelectedPoints([]);
            setDraggingIndex(null);
            // record history for insertion with corrected annotations
            try { pushHistoryFrom(updatedPoints, closed, updatedAnns); } catch (err) { }
            return;
        }

        // Selection mode: clicking empty space clears selection (unless ctrl/meta)
        if (mode === 'select' && closed) {
            if (!(e.ctrlKey || e.metaKey)) setSelectedPoints([]);
            return;
        }

        // If polygon is closed and we didn't click a segment, and not in draw mode, exit
        if (closed && mode !== 'draw') {
            return;
        }

        // Only add points when in draw mode
        if (mode !== 'draw') return;

        // Orthogonal snapping: hold Shift to align to horizontal/vertical relative to last point
        let x = snapped.x, y = snapped.y;
        if (e.shiftKey && points.length > 0) {
            const last = points[points.length - 1];
            // choose alignment to nearest axis
            if (Math.abs(last.x - x) < Math.abs(last.y - y)) {
                x = last.x; // vertical line
            } else {
                y = last.y; // horizontal line
            }
        }
        // If click is near the start point, auto-close (use visual hit radius for reliability)
        if (points.length >= 3) {
            const first = points[0];
            const hit = getHitRadius(14);
            const d2 = (first.x - x) * (first.x - x) + (first.y - y) * (first.y - y);
            if (d2 <= (hit * hit)) {
                setClosed(true);
                const areaUnits = computePolygonArea(points);
                const areaMeters = areaUnits / (unitsPerMeter * unitsPerMeter);
                const displayArea = unitSystem === 'imperial' ? Math.max(1, Math.round(m2ToFt2(areaMeters))) : Math.max(1, Math.round(areaMeters));
                setLotArea(displayArea);
                pushHistoryFrom(points, true);
                return;
            }
        }

        const newPts = points.concat([{ x, y }]);
        setPoints(newPts);
        pushHistoryFrom(newPts, closed);
    }

    function closePolygon() {
        if (points.length < 3) return alert('Need at least 3 points');
        setClosed(true);
        const areaUnits = computePolygonArea(points);
        const areaMeters = areaUnits / (unitsPerMeter * unitsPerMeter);
        // Treat area in meters squared when a scale is provided
        setClosed(true);
        const displayArea = unitSystem === 'imperial' ? Math.max(1, Math.round(m2ToFt2(areaMeters))) : Math.max(1, Math.round(areaMeters));
        setLotArea(displayArea);
        pushHistoryFrom(points, true);
    }

    function handleSvgDoubleClick(e) {
        // double-click to close polygon
        if (points.length >= 3 && !closed) closePolygon();
    }

    function startEditDimension(i, ev) {
        if (measureActive) return; // avoid editing while measuring
        const dim = measureAnnotations[i];
        if (!dim) return;
        const a = dim.a, b = dim.b;
        const du = Math.hypot(b.x - a.x, b.y - a.y);
        const meters = du / Math.max(1, Number(unitsPerMeter || 1));
        setEditingDimIndex(i);
        setEditingDimValue(unitSystem === 'imperial' ? metersToFeet(meters).toFixed(2) : meters.toFixed(2));
        // Choose fixed endpoint contextually: nearest to cursor if clearly nearer; otherwise axis-based default
        let fixed = 'a';
        const dx = b.x - a.x, dy = b.y - a.y;
        const vertical = Math.abs(dy) >= Math.abs(dx);
        if (vertical) {
            // keep lower endpoint fixed by default (move the upper, Revit-like)
            fixed = (a.y > b.y) ? 'a' : 'b';
        } else {
            // keep left endpoint fixed by default (move the right)
            fixed = (a.x <= b.x) ? 'a' : 'b';
        }
        const cp = cursorPoint || { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        const da = Math.hypot(cp.x - a.x, cp.y - a.y);
        const db = Math.hypot(cp.x - b.x, cp.y - b.y);
        if (Math.abs(da - db) > 8) { // only override if clearly nearer (8 user units threshold)
            fixed = (da < db) ? 'a' : 'b';
        }
        setEditingDimFixed(fixed);
    }

    function parseLengthInput(v) {
        if (typeof v !== 'string') return null;
        const trimmedRaw = v.trim().toLowerCase();
        // explicit unit suffix handling
        if (trimmedRaw.endsWith('m')) {
            const n = Number(trimmedRaw.replace(/m$/, '').trim());
            return Number.isFinite(n) && n > 0 ? n : null; // meters
        }
        if (trimmedRaw.endsWith('ft') || trimmedRaw.endsWith("'")) {
            const n = Number(trimmedRaw.replace(/ft$/, '').replace(/'$/, '').trim());
            return Number.isFinite(n) && n > 0 ? feetToMeters(n) : null; // convert feet -> meters
        }
        // no suffix: interpret according to current UI unit system
        const num = Number(trimmedRaw.replace(/[a-z]+$/, ''));
        if (!Number.isFinite(num) || num <= 0) return null;
        return unitSystem === 'imperial' ? feetToMeters(num) : num;
    }

    function commitEditDimension() {
        if (editingDimIndex == null) return;
        const dim = measureAnnotations[editingDimIndex];
        if (!dim) { cancelEditDimension(); return; }
        const desiredMeters = parseLengthInput(editingDimValue);
        if (desiredMeters == null) { cancelEditDimension(); return; }
        const desiredUnits = desiredMeters * Number(unitsPerMeter || 1);
        let a = dim.a, b = dim.b;
        const fixedEnd = editingDimFixed === 'a' || editingDimFixed === 'b' ? editingDimFixed : 'a';
        const fixedIdx = fixedEnd === 'a' ? (Number.isInteger(dim.aIdx) ? dim.aIdx : null) : (Number.isInteger(dim.bIdx) ? dim.bIdx : null);
        const moveIdx = fixedEnd === 'a' ? (Number.isInteger(dim.bIdx) ? dim.bIdx : null) : (Number.isInteger(dim.aIdx) ? dim.aIdx : null);
        const fixedPt = (fixedIdx !== null && points[fixedIdx]) ? points[fixedIdx] : (fixedEnd === 'a' ? a : b);
        const movingPt = (moveIdx !== null && points[moveIdx]) ? points[moveIdx] : (fixedEnd === 'a' ? b : a);
        // direction from fixed to moving
        const dx = movingPt.x - fixedPt.x; const dy = movingPt.y - fixedPt.y; const currentLen = Math.hypot(dx, dy) || 1;
        const ux = dx / currentLen; const uy = dy / currentLen; // unit along-dimension direction
        const newMoving = { x: fixedPt.x + ux * desiredUnits, y: fixedPt.y + uy * desiredUnits };
        let newPoints = points.slice();
        if (moveIdx !== null && newPoints[moveIdx]) {
            // Compute translation delta
            const delta = { x: newMoving.x - movingPt.x, y: newMoving.y - movingPt.y };
            // Move the entire "face" line that shares the same projection along the dimension axis as the moving point.
            // Any vertex p with dot(p, u) ≈ dot(movingPt, u) will be translated by the same delta.
            const proj = (p) => p.x * ux + p.y * uy;
            const k = proj(movingPt);
            const tol = Math.max(1e-6, (snapThreshold || 8) * 0.25); // tolerance in user units
            for (let j = 0; j < newPoints.length; j++) {
                const pj = newPoints[j];
                if (Math.abs(proj(pj) - k) <= tol) {
                    newPoints[j] = { x: pj.x + delta.x, y: pj.y + delta.y };
                }
            }
            setPoints(newPoints);
        }
        // Update annotation endpoints explicitly
        const newA = fixedEnd === 'a' ? fixedPt : newMoving;
        const newB = fixedEnd === 'a' ? newMoving : fixedPt;
        setMeasureAnnotations(prev => prev.map((m, i) => i === editingDimIndex ? { ...m, a: newA, b: newB } : m));
        try { pushHistoryFrom(newPoints, closed, measureAnnotations.map((m, i) => i === editingDimIndex ? { ...m, a: newA, b: newB } : m)); } catch (e) { }
        cancelEditDimension();
    }

    function cancelEditDimension() {
        setEditingDimIndex(null);
        setEditingDimValue('');
        setEditingDimFixed(null);
    }

    // geometry snapping helpers
    function projectPointToSegment(p, a, b) {
        const l2 = (b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y);
        if (l2 === 0) return { x: a.x, y: a.y };
        let t = ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / l2;
        t = Math.max(0, Math.min(1, t));
        return { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) };
    }

    // find nearest vertex index within threshold; returns index or -1
    function getNearestVertexIndex(pt, threshold = snapThreshold) {
        if (!points || points.length === 0) return -1;
        let bestIdx = -1; let best = Infinity;
        for (let i = 0; i < points.length; i++) {
            const v = points[i];
            const d = Math.hypot(pt.x - v.x, pt.y - v.y);
            if (d < best) { best = d; bestIdx = i; }
        }
        return best <= threshold ? bestIdx : -1;
    }

    function getSnappedPoint(cursor, e) {
        let x = cursor.x, y = cursor.y;
        // grid snap first
        if (snapToGrid) { x = Math.round(x / gridSize) * gridSize; y = Math.round(y / gridSize) * gridSize; }

        const candidate = { x, y };
        // geometry snap (vertex or edge) — if enabled
        if (snapToGeometry && points && points.length > 0) {
            // find nearest vertex
            let best = { type: null, dist: Infinity, point: null };
            for (const v of points) {
                const d = Math.hypot(candidate.x - v.x, candidate.y - v.y);
                if (d < best.dist) { best = { type: 'vertex', dist: d, point: { x: v.x, y: v.y } }; }
            }
            // find nearest edge projection
            for (let i = 0; i < points.length - 1; i++) {
                const a = points[i], b = points[i + 1];
                const proj = projectPointToSegment(candidate, a, b);
                const d = Math.hypot(candidate.x - proj.x, candidate.y - proj.y);
                if (d < best.dist) { best = { type: 'edge', dist: d, point: proj }; }
            }
            if (points.length >= 3) {
                const a = points[points.length - 1], b = points[0];
                const proj = projectPointToSegment(candidate, a, b);
                const d = Math.hypot(candidate.x - proj.x, candidate.y - proj.y);
                if (d < best.dist) { best = { type: 'edge', dist: d, point: proj }; }
            }
            if (best.dist <= snapThreshold) {
                candidate.x = best.point.x; candidate.y = best.point.y;
            }
        }

        // angle snapping (like Revit/Rhino) only while drawing; Shift enforces orthogonal instead
        if (mode === 'draw' && points.length > 0) {
            const last = points[points.length - 1];
            const dx = candidate.x - last.x; const dy = candidate.y - last.y;
            const r = Math.hypot(dx, dy);
            if (r > 0.0001) {
                if (e && e.shiftKey) {
                    // orthogonal to last point (already handled in click for final placement)
                    // but for preview, snap to nearest axis
                    if (Math.abs(dx) > Math.abs(dy)) {
                        candidate.y = last.y;
                    } else {
                        candidate.x = last.x;
                    }
                } else if (angleSnap > 0) {
                    const ang = Math.atan2(dy, dx);
                    const deg = ang * 180 / Math.PI;
                    const snappedDeg = Math.round(deg / angleSnap) * angleSnap;
                    const snappedRad = snappedDeg * Math.PI / 180;
                    candidate.x = last.x + Math.cos(snappedRad) * r;
                    candidate.y = last.y + Math.sin(snappedRad) * r;
                }
            }
        }

        return candidate;
    }

    // Measure-mode snap: grid + geometry only (no angle snap), prefer vertices over edges when both are within threshold
    function getMeasureSnappedPoint(cursor, e) {
        let x = cursor.x, y = cursor.y;
        if (snapToGrid) { x = Math.round(x / gridSize) * gridSize; y = Math.round(y / gridSize) * gridSize; }

        const candidate = { x, y };
        if (snapToGeometry && points && points.length > 0) {
            let nearestVertex = { dist: Infinity, point: null };
            for (const v of points) {
                const d = Math.hypot(candidate.x - v.x, candidate.y - v.y);
                if (d < nearestVertex.dist) nearestVertex = { dist: d, point: { x: v.x, y: v.y } };
            }
            let nearestEdge = { dist: Infinity, point: null };
            for (let i = 0; i < points.length - 1; i++) {
                const a = points[i], b = points[i + 1];
                const proj = projectPointToSegment(candidate, a, b);
                const d = Math.hypot(candidate.x - proj.x, candidate.y - proj.y);
                if (d < nearestEdge.dist) nearestEdge = { dist: d, point: proj };
            }
            if (points.length >= 3) {
                const a = points[points.length - 1], b = points[0];
                const proj = projectPointToSegment(candidate, a, b);
                const d = Math.hypot(candidate.x - proj.x, candidate.y - proj.y);
                if (d < nearestEdge.dist) nearestEdge = { dist: d, point: proj };
            }
            const thresh = snapThreshold;
            // Prefer vertex when both qualify; otherwise use whichever qualifies
            if (nearestVertex.dist <= thresh) {
                candidate.x = nearestVertex.point.x; candidate.y = nearestVertex.point.y;
            } else if (nearestEdge.dist <= thresh) {
                candidate.x = nearestEdge.point.x; candidate.y = nearestEdge.point.y;
            }
        }
        return candidate;
    }

    // compute handle radius in SVG user units so handles stay a fixed screen size
    function getHandleRadius(px = 10) {
        const svg = svgRef.current;
        if (!svg) return px; // fallback in user units
        const clientW = svg.clientWidth || VB_WIDTH;
        // px on screen corresponds to (viewBox.w / clientW) user units per screen px
        const unitsPerPx = viewBox.w / clientW;
        return Math.max(2, px * unitsPerPx);
    }

    function getHitRadius(px = 14) {
        return getHandleRadius(px);
    }

    function getStrokeUserWidth(basePx = 1) {
        // when fixedScreenHandles is true, convert pixel stroke to user units so stroke appears constant on screen
        if (fixedScreenHandles) {
            const svg = svgRef.current;
            if (!svg) return basePx;
            const clientW = svg.clientWidth || VB_WIDTH;
            const unitsPerPx = viewBox.w / clientW;
            return Math.max(0.2, basePx * unitsPerPx);
        }
        // world-scaled: return worldStrokeWidth in user units
        return worldStrokeWidth;
    }

    function resetDrawing() {
        setPoints([]); setClosed(false);
        setStallsPreview([]);
        // clear stalls/columns on all levels when resetting the drawing
        setLevels(prev => prev.map(l => ({ ...l, stallsPreview: [] })));
        setMeasurePoints([]);
        setMeasureAnnotations([]);
        setMode('draw');
        setSelectedStalls([]);
        setClipDiagnostics([]);
        setColumnDebugPoints([]);
        setShowColumnDebug(false);
        setValidateResults(null);
        pushHistoryFrom([], false);
    }

    function undoLastPoint() {
        setPoints(prev => {
            const next = prev.slice(0, -1);
            pushHistoryFrom(next, closed);
            return next;
        });
    }

    function togglePointSelection(idx, e) {
        e.stopPropagation();
        const accumulate = e.ctrlKey || e.metaKey;
        setSelectedPoints(prev => {
            if (!accumulate) return [idx];
            const has = prev.includes(idx);
            if (has) return prev.filter(i => i !== idx);
            return [...prev, idx].sort((a, b) => a - b);
        });
    }

    function selectAllPoints() {
        setSelectedPoints(points.map((_, i) => i));
    }

    function clearSelection() {
        setSelectedPoints([]);
    }

    function copySelection() {
        if (selectedPoints && selectedPoints.length > 0) {
            const pts = selectedPoints.map(i => points[i]).map(p => ({ x: p.x, y: p.y }));
            setClipboardPoints(pts);
        } else if (points && points.length > 0) {
            // copy whole polygon if nothing selected
            setClipboardPoints(points.map(p => ({ x: p.x, y: p.y })));
        }
    }

    function pasteClipboard() {
        if (!clipboardPoints || clipboardPoints.length === 0) return;
        // compute centroid of clipboard and target
        const src = clipboardPoints;
        const cx = src.reduce((s, p) => s + p.x, 0) / src.length;
        const cy = src.reduce((s, p) => s + p.y, 0) / src.length;
        // paste at cursor if available, otherwise offset by +10,+10
        let dx = 10, dy = 10;
        if (cursorPoint) { dx = cursorPoint.x - cx; dy = cursorPoint.y - cy; }
        const pasted = src.map(p => ({ x: p.x + dx, y: p.y + dy }));
        // append pasted points
        const baseIndex = points.length;
        const newPoints = points.concat(pasted);
        setPoints(newPoints);
        // select newly pasted points
        setSelectedPoints(pasted.map((_, i) => baseIndex + i));
        pushHistoryFrom(newPoints, closed);
    }

    function deleteSelectedPoints() {
        if (!selectedPoints || selectedPoints.length === 0) return;
        const toRemove = new Set(selectedPoints);
        const next = points.filter((_, i) => !toRemove.has(i));
        setPoints(next);
        setSelectedPoints([]);
        pushHistoryFrom(next, closed);
    }

    // Dragging behavior: update point while mouse moves
    React.useEffect(() => {
        if (draggingIndex === null) return;
        const handleMove = (e) => {
            const svg = svgRef.current;
            if (!svg) return;
            const pt = svg.createSVGPoint();
            pt.x = e.clientX; pt.y = e.clientY;
            const ctm = svg.getScreenCTM().inverse();
            const cursor = pt.matrixTransform(ctm);
            let x = cursor.x, y = cursor.y;
            const noSnap = e.altKey; // hold Alt to disable all snapping while dragging
            if (!noSnap && snapToGrid) { x = Math.round(x / gridSize) * gridSize; y = Math.round(y / gridSize) * gridSize; }
            // Snap to existing vertices (excluding the one being dragged and its immediate neighbors), only if geometry snap enabled and not bypassed
            if (!noSnap && snapToGeometry) {
                const thresh = (snapThreshold || 12) * 0.6;
                let bestIdx = -1; let bestDist = Infinity;
                // compute adjacent indices to avoid collapsing edges
                const prevIdx = draggingIndex - 1 >= 0 ? draggingIndex - 1 : (closed ? points.length - 1 : -1);
                const nextIdx = draggingIndex + 1 < points.length ? draggingIndex + 1 : (closed ? 0 : -1);
                for (let i = 0; i < points.length; i++) {
                    if (i === draggingIndex || i === prevIdx || i === nextIdx) continue;
                    const p = points[i];
                    const d = Math.hypot(p.x - x, p.y - y);
                    if (d < bestDist) { bestDist = d; bestIdx = i; }
                }
                if (bestDist <= thresh && bestIdx >= 0) {
                    x = points[bestIdx].x; y = points[bestIdx].y;
                }
            }
            // Constraint: if this point participates in a dimension, constrain movement along that dimension axis
            if (!noSnap && measureAnnotations && measureAnnotations.length > 0) {
                // find a dimension that binds this vertex
                let bound = null; let axis = null;
                for (let m of measureAnnotations) {
                    if (m && (m.aIdx === draggingIndex || m.bIdx === draggingIndex)) {
                        const a = Number.isInteger(m.aIdx) && points[m.aIdx] ? points[m.aIdx] : m.a;
                        const b = Number.isInteger(m.bIdx) && points[m.bIdx] ? points[m.bIdx] : m.b;
                        const dx = b.x - a.x, dy = b.y - a.y; const len = Math.hypot(dx, dy);
                        if (len > 1e-6) { axis = { x: dx / len, y: dy / len }; bound = { a, b }; break; }
                    }
                }
                if (axis) {
                    // project movement to the axis direction passing through the original point
                    const p0 = points[draggingIndex];
                    const vx = x - p0.x, vy = y - p0.y;
                    const dot = vx * axis.x + vy * axis.y;
                    x = p0.x + axis.x * dot;
                    y = p0.y + axis.y * dot;
                }
            }
            setPoints(prev => prev.map((p, i) => i === draggingIndex ? { x, y } : p));
        };
        const handleUp = () => { setDraggingIndex(null); suppressNextClickRef.current = true; };
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp);
        return () => { window.removeEventListener('mousemove', handleMove); window.removeEventListener('mouseup', handleUp); };
    }, [draggingIndex, snapToGrid, gridSize, snapToGeometry, snapThreshold, closed, points.length]);

    // when dragging ends, push history (track completed move)
    React.useEffect(() => {
        if (draggingIndex !== null) return;
        // pushing history for current points
        pushHistoryFrom(points, closed);
    }, [draggingIndex]);

    // Keep dimension endpoints attached to moved polygon vertices
    React.useEffect(() => {
        if (!measureAnnotations || measureAnnotations.length === 0) return;
        let changed = false;
        const next = measureAnnotations.map(m => {
            let a = m.a, b = m.b;
            if (Number.isInteger(m.aIdx) && points[m.aIdx]) {
                const p = points[m.aIdx];
                if (!a || a.x !== p.x || a.y !== p.y) { a = { x: p.x, y: p.y }; changed = true; }
            }
            if (Number.isInteger(m.bIdx) && points[m.bIdx]) {
                const p = points[m.bIdx];
                if (!b || b.x !== p.x || b.y !== p.y) { b = { x: p.x, y: p.y }; changed = true; }
            }
            if (changed) return { ...m, a, b };
            return m;
        });
        if (changed) setMeasureAnnotations(next);
    }, [points]);

    // Pan (drag background) and zoom (wheel)
    React.useEffect(() => {
        const svg = svgRef.current;
        if (!svg) return;

        const getPoint = (clientX, clientY) => {
            const pt = svg.createSVGPoint(); pt.x = clientX; pt.y = clientY; return pt.matrixTransform(svg.getScreenCTM().inverse());
        };

        const handleMouseDown = (e) => {
            if (mode === 'pan' || (e.button === 1)) {
                setIsPanning(true);
                panStartRef.current = { clientX: e.clientX, clientY: e.clientY, viewBox: { ...viewBox } };
                e.preventDefault();
            }
        };

        const handleMouseMove = (e) => {
            if (!isPanning || !panStartRef.current) return;
            const dx = (e.clientX - panStartRef.current.clientX) * (panStartRef.current.viewBox.w / svg.clientWidth);
            const dy = (e.clientY - panStartRef.current.clientY) * (panStartRef.current.viewBox.h / svg.clientHeight);
            setViewBox({ x: panStartRef.current.viewBox.x - dx, y: panStartRef.current.viewBox.y - dy, w: panStartRef.current.viewBox.w, h: panStartRef.current.viewBox.h });
        };

        const handleMouseUp = () => {
            // Only suppress the following click if we were actually panning
            if (isPanning) suppressNextClickRef.current = true;
            setIsPanning(false);
            panStartRef.current = null;
        };

        const handleWheel = (e) => {
            // zoom in/out centered on cursor
            e.preventDefault();
            const scale = e.deltaY > 0 ? 1.12 : 0.9;
            const svgPt = getPoint(e.clientX, e.clientY);
            const newW = viewBox.w * scale;
            const newH = viewBox.h * scale;
            const nx = svgPt.x - (svgPt.x - viewBox.x) * (newW / viewBox.w);
            const ny = svgPt.y - (svgPt.y - viewBox.y) * (newH / viewBox.h);
            setViewBox({ x: nx, y: ny, w: newW, h: newH });
        };

        svg.addEventListener('mousedown', handleMouseDown);
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
        svg.addEventListener('wheel', handleWheel, { passive: false });

        return () => {
            svg.removeEventListener('mousedown', handleMouseDown);
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
            svg.removeEventListener('wheel', handleWheel);
        };
    }, [isPanning, mode, viewBox, gridSize, viewMode]);

    // Basic OBJ parser: extract vertex lines and compute convex hull area projected to XY
    function parseOBJ(text) {
        const lines = text.split('\n');
        const verts = [];
        for (const l of lines) {
            if (l.startsWith('v ')) {
                const parts = l.trim().split(/\s+/).slice(1).map(Number);
                if (parts.length >= 2 && Number.isFinite(parts[0]) && Number.isFinite(parts[1])) {
                    verts.push([parts[0], parts[1]]);
                }
            }
        }
        return verts;
    }

    // monotone chain convex hull
    function convexHull(points) {
        if (points.length <= 1) return points.slice();
        const pts = points.map(p => [p[0], p[1]]).sort((a, b) => a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]);
        const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
        const lower = [];
        for (const p of pts) {
            while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
            lower.push(p);
        }
        const upper = [];
        for (let i = pts.length - 1; i >= 0; i--) {
            const p = pts[i];
            while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
            upper.push(p);
        }
        upper.pop(); lower.pop();
        return lower.concat(upper);
    }

    function areaFromPolygonCoords(coords) {
        // Convert from [[x,y],...] to [{x,y},...] and delegate to computePolygonArea
        if (!coords || coords.length < 3) return 0;
        const pts = coords.map(c => ({ x: c[0], y: c[1] }));
        return computePolygonArea(pts);
    }

    function pointInPolygon(pt, polygon) {
        // polygon: [{x,y},...]
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            const xi = polygon[i].x, yi = polygon[i].y;
            const xj = polygon[j].x, yj = polygon[j].y;
            const intersect = ((yi > pt.y) !== (yj > pt.y)) && (pt.x < (xj - xi) * (pt.y - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    // compute distance from point to segment and find if within threshold
    function distPointToSegment(p, v, w) {
        // p, v, w are {x,y}
        const l2 = (w.x - v.x) * (w.x - v.x) + (w.y - v.y) * (w.y - v.y);
        if (l2 === 0) return Math.hypot(p.x - v.x, p.y - v.y);
        let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
        t = Math.max(0, Math.min(1, t));
        const proj = { x: v.x + t * (w.x - v.x), y: v.y + t * (w.y - v.y) };
        return Math.hypot(p.x - proj.x, p.y - proj.y);
    }

    function findSegmentIndexNearPoint(p, poly, threshold) {
        if (!poly || poly.length < 2) return -1;
        for (let i = 0; i < poly.length - 1; i++) {
            const a = poly[i], b = poly[i + 1];
            if (distPointToSegment(p, a, b) <= threshold) return i;
        }
        // also check closing segment
        if (poly.length >= 3) {
            const a = poly[poly.length - 1], b = poly[0];
            if (distPointToSegment(p, a, b) <= threshold) return poly.length - 1;
        }
        return -1;
    }

    // generateStallsGrid removed (moderate cleanup). Use Aisle-first Layout for realistic generation.

    // autoGenerateAll removed (moderate cleanup).
    // Use the dedicated Aisle-first generator (`generateAisleFirstLayout`) and
    // the export/optimizer tools for layout experimentation.

    // Aisle-first layout: create continuous aisles and place only full stalls adjacent to aisles
    // This produces realistic, continuous circulation and avoids clipped fragments at lot edges.
    function generateAisleFirstLayout() {
        if (!points || points.length < 3) return alert('Draw and close a polygon first');
        const _stallWidth_m = unitSystem === 'imperial' ? feetToMeters(Number(stallWidth)) : Number(stallWidth);
        const _stallDepth_m = unitSystem === 'imperial' ? feetToMeters(Number(stallDepth)) : Number(stallDepth);
        const unitW = _stallWidth_m * unitsPerMeter;
        const unitD = _stallDepth_m * unitsPerMeter;
        // choose aisle preferences based on selected code (fallback defaults)
        const codePrefs = {
            US: { twoWay: true, driveWidthMeters: 6 },
            CA: { twoWay: true, driveWidthMeters: 6 },
            AU: { twoWay: true, driveWidthMeters: 6 },
            DE: { twoWay: true, driveWidthMeters: 6 },
            FR: { twoWay: true, driveWidthMeters: 6 },
            UK: { twoWay: false, driveWidthMeters: 3.6 },
            SG: { twoWay: false, driveWidthMeters: 3.5 },
            IN: { twoWay: false, driveWidthMeters: 3.5 },
            ZA: { twoWay: false, driveWidthMeters: 3.5 },
            default: { twoWay: true, driveWidthMeters: 6 }
        };
        const pref = (codePrefs[selectedCode] || codePrefs.default);
        // Use user override when set, else code preset; convert to user units
        const driveWidthMetersResolved = (driveWidthMeters !== null && Number.isFinite(Number(driveWidthMeters)))
            ? Number(driveWidthMeters)
            : (pref.driveWidthMeters || 6);
        const driveWidth = Math.max(driveWidthMetersResolved * unitsPerMeter, unitD * 0.8);
        // spacing between row centers: default stall depth + drive width, or user override
        const spacingY = (rowSpacingMeters !== null && Number.isFinite(Number(rowSpacingMeters)))
            ? Math.max(0.001, Number(rowSpacingMeters)) * Number(unitsPerMeter || 1)
            : (unitD + driveWidth);

        const centroid = { x: points.reduce((s, p) => s + p.x, 0) / points.length, y: points.reduce((s, p) => s + p.y, 0) / points.length };
        // Prefer saved grid angle for perfect alignment; fallback to CPlane X dir
        const angle = (columnGridParams && typeof columnGridParams.angle === 'number')
            ? columnGridParams.angle
            : Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
        const rotLot = rotatePolygon(points, centroid, -angle);
        const xsR = rotLot.map(p => p.x); const ysR = rotLot.map(p => p.y);
        const minXr = Math.min(...xsR), maxXr = Math.max(...xsR), minYr = Math.min(...ysR), maxYr = Math.max(...ysR);

        const stalls = [];
        const aisles = [];
        // reset diagnostics for this run
        setClipDiagnostics([]);
        // Underground convention: keep stalls orthogonal to aisles (no diagonal drift)
        const angleOffsetRad = 0;

        // collect existing column footprints (rotated to lot coords) so stalls and aisles avoid them
        const existingFeatures = (levels[currentLevelIndex]?.stallsPreview || []) || [];
        const existingColumnsR = existingFeatures.filter(f => f.type === 'column' && f.poly).map(f => rotatePolygon(f.poly, centroid, -angle));
        // Inflate column footprints by clearance to keep aisles safely away
        const inflate = (poly, r) => {
            const xs = poly.map(p => p.x), ys = poly.map(p => p.y);
            const minX = Math.min(...xs) - r, maxX = Math.max(...xs) + r;
            const minY = Math.min(...ys) - r, maxY = Math.max(...ys) + r;
            return [
                { x: minX, y: minY }, { x: maxX, y: minY }, { x: maxX, y: maxY }, { x: minX, y: maxY }
            ];
        };
        const columnClearR = (driveWidth / 2) + Math.max(0, Number(aisleColumnGapMeters || 0)) * Number(unitsPerMeter || 1);
        const inflatedColumnsR = existingColumnsR.map(c => inflate(c, columnClearR));

        // place continuous aisles as long thin rectangles spanning lot width
        for (let y = minYr + unitD / 2 + driveWidth / 2; y <= maxYr - unitD / 2; y += spacingY) {
            const extra = Math.max(0, Number(aisleColumnGapMeters || 0)) * Number(unitsPerMeter || 1);
            const baseRect = { x: (minXr + maxXr) / 2, y: y, hw: (maxXr - minXr) / 2, hd: driveWidth / 2 + extra, type: 'aisle' };
            if (!sampleRectInside(baseRect, rotLot, 6)) continue;
            // build blocked X-intervals where columns intersect the aisle band in rotated space
            const bandYmin = y - baseRect.hd, bandYmax = y + baseRect.hd;
            const blockers = [];
            for (const cpoly of inflatedColumnsR) {
                const xs = cpoly.map(p => p.x), ys = cpoly.map(p => p.y);
                const cxmin = Math.min(...xs), cxmax = Math.max(...xs);
                const cymin = Math.min(...ys), cymax = Math.max(...ys);
                // if column bbox overlaps band in Y, mark its X interval as blocked
                if (!(cymax < bandYmin || cymin > bandYmax)) {
                    blockers.push([cxmin - extra, cxmax + extra]);
                }
            }
            if (blockers.length === 0) { aisles.push(baseRect); continue; }
            // merge blocked intervals
            blockers.sort((a, b) => a[0] - b[0]);
            const merged = [];
            for (const iv of blockers) {
                if (merged.length === 0 || iv[0] > merged[merged.length - 1][1]) merged.push(iv);
                else merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], iv[1]);
            }
            // create gap intervals across lot width
            let cursor = minXr;
            const minGap = Math.max(driveWidth, unitW) * 1.2; // stricter minimum to avoid tiny fragments
            for (const [bx0, bx1] of merged) {
                if (bx0 > cursor) {
                    const gx0 = cursor, gx1 = bx0;
                    if (gx1 - gx0 >= minGap) {
                        const rect = { x: (gx0 + gx1) / 2, y, hw: (gx1 - gx0) / 2, hd: baseRect.hd, type: 'aisle' };
                        if (sampleRectInside(rect, rotLot, 6)) aisles.push(rect);
                    }
                }
                cursor = Math.max(cursor, bx1);
            }
            if (cursor < maxXr) {
                const gx0 = cursor, gx1 = maxXr;
                if (gx1 - gx0 >= minGap) {
                    const rect = { x: (gx0 + gx1) / 2, y, hw: (gx1 - gx0) / 2, hd: baseRect.hd, type: 'aisle' };
                    if (sampleRectInside(rect, rotLot, 6)) aisles.push(rect);
                }
            }
        }

        // Fallback: if no aisles were generated, place a central aisle band
        if (aisles.length === 0) {
            const y = (minYr + maxYr) / 2;
            const rect = { x: (minXr + maxXr) / 2, y, hw: (maxXr - minXr) / 2, hd: driveWidth / 2, type: 'aisle' };
            if (sampleRectInside(rect, rotLot, 6)) aisles.push(rect);
        }

        // For each aisle, place stalls on both sides using dynamic spacing based on rotated footprint
        const xGap = 0.2 * unitsPerMeter; // small gap between stalls
        const rejectedFragments = [];
        // Track placed stalls across all aisle segments to prevent cross-segment duplicates
        const placedStallsGlobalR = [];
        for (let ai = 0; ai < aisles.length; ai++) {
            const aisleRect = aisles[ai];
            const rowCenters = [aisleRect.y - (driveWidth / 2 + unitD / 2), aisleRect.y + (driveWidth / 2 + unitD / 2)];
            // keep placed footprints in rotated-lot coords to test collisions
            const placedStallsR = [];
            for (let side = 0; side < rowCenters.length; side++) {
                const ry = rowCenters[side];
                if (ry - unitD / 2 < minYr || ry + unitD / 2 > maxYr) continue;
                // stagger start for alternating rows to avoid direct overlap
                // Constrain to the current aisle segment bounds
                const segMinX = Math.max(minXr, aisleRect.x - aisleRect.hw);
                const segMaxX = Math.min(maxXr, aisleRect.x + aisleRect.hw);
                let startX = segMinX + unitW / 2; // deterministic start without alternating stagger
                let x = startX;
                while (x <= segMaxX - unitW / 2) {
                    const hw = unitW / 2, hd = unitD / 2;
                    const baseCorners = [
                        { x: x - hw, y: ry - hd },
                        { x: x + hw, y: ry - hd },
                        { x: x + hw, y: ry + hd },
                        { x: x - hw, y: ry + hd },
                    ];
                    // compute mirrored/alternating angle per side/aisle
                    // keep stalls axis-aligned to aisle bands
                    let cornersR = baseCorners;
                    // compute footprint width along X in rotated-lot coords
                    const xs = cornersR.map(c => c.x); const minXc = Math.min(...xs); const maxXc = Math.max(...xs);
                    const bboxWidth = maxXc - minXc;
                    const xStep = Math.max(bboxWidth + xGap, unitW + xGap);

                    // collision check against already placed stalls (rotated coords) and existing columns
                    const collidesWithPlaced = placedStallsR.some(s => polygonsOverlap(s, cornersR))
                        || placedStallsGlobalR.some(s => polygonsOverlap(s, cornersR));
                    const collidesWithColumn = existingColumnsR.some(c => polygonsOverlap(c, cornersR));
                    const collides = collidesWithPlaced || collidesWithColumn;

                    // containment / clipping test
                    const allInside = cornersR.every(c => pointInPolygon(c, rotLot));
                    const clipped = polygonClip(cornersR, rotLot);
                    const clippedArea = computePolygonArea(clipped);
                    const fullArea = computePolygonArea(cornersR);
                    const ratio = fullArea > 0 ? (clippedArea / fullArea) : 0;

                    if (!collides && (allInside || ratio >= Number(clipAcceptance || 0))) {
                        // accept stall
                        placedStallsR.push(cornersR);
                        placedStallsGlobalR.push(cornersR);
                        const worldPoly = rotatePolygon(allInside ? cornersR : clipped, centroid, angle);
                        const centerWorld = rotatePoint({ x, y: ry }, centroid, angle);
                        stalls.push({ x: centerWorld.x, y: centerWorld.y, hw, hd, poly: worldPoly, type: 'stall', clipRatio: allInside ? 1 : ratio, angleDeg: Number(stallAngleDeg) || 0 });
                    } else {
                        // record rejected fragment in world coords
                        const worldPoly = rotatePolygon(clipped.length ? clipped : cornersR, centroid, angle);
                        rejectedFragments.push({ ratio, poly: worldPoly });
                    }

                    x += xStep;
                }
            }
        }

        // Simple vertical/horizontal connectors with turning-radius constraints between aisle bands to ensure continuity
        if (autoConnectAisles && aisles.length > 0) {
            const safeConnectors = [];
            const R = Math.max(0.1, Number(minTurningRadiusMeters || 0)) * Number(unitsPerMeter || 1);
            // grid-aligned X buckets from columnGridParams or inferred from aisles
            let bucketsX = [];
            if (columnGridParams && columnGridParams.spacingX) {
                const sx = Math.max(1e-3, Number(columnGridParams.spacingX));
                const offX = Number(columnGridParams.offsetX || 0);
                const startGX = Math.floor((minXr - offX) / sx) * sx + offX;
                for (let gx = startGX; gx <= maxXr; gx += sx) bucketsX.push(gx);
                // also midpoints
                const mids = [];
                for (let i = 0; i < bucketsX.length - 1; i++) mids.push((bucketsX[i] + bucketsX[i + 1]) / 2);
                bucketsX = bucketsX.concat(mids);
            } else {
                // fallback uniform buckets
                const step = Math.max(unitW * 2, driveWidth * 2);
                for (let gx = minXr + step; gx <= maxXr - step; gx += step) bucketsX.push(gx);
            }
            // Vertical connectors between adjacent bands (require enough gap for two quarter-turns)
            for (let i = 0; i < aisles.length - 1; i++) {
                const A = aisles[i];
                const B = aisles[i + 1];
                const gapY = (B.y - B.hd) - (A.y + A.hd);
                if (gapY <= 0 || gapY < 2 * R) continue; // require room to turn at both ends
                const midY = (A.y + A.hd) + gapY / 2;
                for (const gx of bucketsX) {
                    const hw = Math.max(driveWidth / 2, R); // width supports turning radius
                    const hd = gapY / 2;
                    const conn = { x: gx, y: midY, hw, hd, type: 'aisle' };
                    const rectPoly = [
                        { x: conn.x - conn.hw, y: conn.y - conn.hd },
                        { x: conn.x + conn.hw, y: conn.y - conn.hd },
                        { x: conn.x + conn.hw, y: conn.y + conn.hd },
                        { x: conn.x - conn.hw, y: conn.y + conn.hd },
                    ];
                    let bad = false;
                    for (const cpoly of inflatedColumnsR) { try { if (polygonsOverlap(rectPoly, cpoly)) { bad = true; break; } } catch (e) { } }
                    if (!bad && sampleRectInside(conn, rotLot, 6)) safeConnectors.push(conn);
                }
            }
            // Horizontal connectors across split segments in the same band (turning at both ends)
            const byBandY = new Map();
            for (const a of aisles) {
                const key = Math.round(a.y * 100) / 100;
                if (!byBandY.has(key)) byBandY.set(key, []);
                byBandY.get(key).push(a);
            }
            for (const group of byBandY.values()) {
                const sorted = group.slice().sort((u, v) => (u.x - u.hw) - (v.x - v.hw));
                for (let i = 0; i < sorted.length - 1; i++) {
                    const L = sorted[i]; const R = sorted[i + 1];
                    const gapX = (R.x - R.hw) - (L.x + L.hw);
                    if (gapX <= 0 || gapX > driveWidth * 2 || gapX < 2 * R) continue;
                    const midX = (L.x + L.hw) + gapX / 2;
                    const hw = gapX / 2;
                    const hd = Math.max(driveWidth / 2, R);
                    const conn = { x: midX, y: L.y, hw, hd, type: 'aisle' };
                    const rectPoly = [
                        { x: conn.x - conn.hw, y: conn.y - conn.hd },
                        { x: conn.x + conn.hw, y: conn.y - conn.hd },
                        { x: conn.x + conn.hw, y: conn.y + conn.hd },
                        { x: conn.x - conn.hw, y: conn.y + conn.hd },
                    ];
                    let bad = false;
                    for (const cpoly of inflatedColumnsR) { try { if (polygonsOverlap(rectPoly, cpoly)) { bad = true; break; } } catch (e) { } }
                    if (!bad && sampleRectInside(conn, rotLot, 6)) safeConnectors.push(conn);
                }
            }
            aisles.push(...safeConnectors);
        }
        // write diagnostics once
        setClipDiagnostics(rejectedFragments);

        // convert aisles to world-space polygons
        const features = aisles.map(a => {
            const cornersR = [
                { x: a.x - a.hw, y: a.y - a.hd },
                { x: a.x + a.hw, y: a.y - a.hd },
                { x: a.x + a.hw, y: a.y + a.hd },
                { x: a.x - a.hw, y: a.y + a.hd },
            ];
            return { ...a, poly: rotatePolygon(cornersR, centroid, angle) };
        });

        // Perimeter street: add inner boundary streets and connectors
        let connectorsAdded = 0;

        if (perimeterStreetEnabled) {
            const off = Math.max(0, Number(perimeterStreetOffsetMeters || 0)) * Number(unitsPerMeter || 1);
            // Build inset rectangle from rotated lot bbox
            const xs = rotLot.map(p => p.x), ys = rotLot.map(p => p.y);
            const lx0 = Math.min(...xs) + off, lx1 = Math.max(...xs) - off;
            const ly0 = Math.min(...ys) + off, ly1 = Math.max(...ys) - off;
            const streetRectsR = [];
            // top horizontal
            if (ly0 < ly1 && lx0 < lx1) {
                streetRectsR.push({ x: (lx0 + lx1) / 2, y: ly0, hw: (lx1 - lx0) / 2, hd: driveWidth / 2, type: 'street' });
                // bottom
                streetRectsR.push({ x: (lx0 + lx1) / 2, y: ly1, hw: (lx1 - lx0) / 2, hd: driveWidth / 2, type: 'street' });
                // left vertical
                streetRectsR.push({ x: lx0, y: (ly0 + ly1) / 2, hw: driveWidth / 2, hd: (ly1 - ly0) / 2, type: 'street' });
                // right vertical
                streetRectsR.push({ x: lx1, y: (ly0 + ly1) / 2, hw: driveWidth / 2, hd: (ly1 - ly0) / 2, type: 'street' });
            }
            const streetFeatures = streetRectsR.map(a => {
                const cornersR = [
                    { x: a.x - a.hw, y: a.y - a.hd },
                    { x: a.x + a.hw, y: a.y - a.hd },
                    { x: a.x + a.hw, y: a.y + a.hd },
                    { x: a.x - a.hw, y: a.y + a.hd },
                ];
                return { ...a, poly: rotatePolygon(cornersR, centroid, angle) };
            });
            features.push(...streetFeatures);

            // Connect each aisle to nearest street segment at grid buckets
            const spacingUnits = Math.max(1, Number(connectorSpacingMeters || 8)) * Number(unitsPerMeter || 1);
            const R = Math.max(0.1, Number(minTurningRadiusMeters || 0)) * Number(unitsPerMeter || 1);
            // buckets across lot width in rotated space
            const bucketsX = [];
            for (let gx = lx0; gx <= lx1; gx += spacingUnits) bucketsX.push(gx);
            const addConnectorIfSafe = (connR) => {
                const rectPoly = [
                    { x: connR.x - connR.hw, y: connR.y - connR.hd },
                    { x: connR.x + connR.hw, y: connR.y - connR.hd },
                    { x: connR.x + connR.hw, y: connR.y + connR.hd },
                    { x: connR.x - connR.hw, y: connR.y + connR.hd },
                ];
                let bad = false;
                for (const cpoly of inflatedColumnsR) { try { if (polygonsOverlap(rectPoly, cpoly)) { bad = true; break; } } catch (e) { } }
                if (!bad && sampleRectInside(connR, rotLot, 6)) {
                    const poly = rotatePolygon(rectPoly, centroid, angle);
                    features.push({ x: null, y: null, hw: null, hd: null, poly, type: 'aisle' });
                    connectorsAdded++;
                }
            };
            for (const a of aisles) {
                for (const gx of bucketsX) {
                    // connect upwards to top street
                    const topY = ly0;
                    const gapUp = (topY - driveWidth / 2) - (a.y + a.hd);
                    if (gapUp >= 2 * R) addConnectorIfSafe({ x: gx, y: (a.y + a.hd) + gapUp / 2, hw: Math.max(driveWidth / 2, R), hd: gapUp / 2, type: 'aisle' });
                    // connect downwards to bottom street
                    const botY = ly1;
                    const gapDown = (a.y - a.hd) - (botY + driveWidth / 2);
                    if (gapDown >= 2 * R) addConnectorIfSafe({ x: gx, y: (botY + driveWidth / 2) + gapDown / 2, hw: Math.max(driveWidth / 2, R), hd: gapDown / 2, type: 'aisle' });
                }
            }

            // Optional central spine horizontally through the center
            if (addCentralSpine) {
                const cy = (ly0 + ly1) / 2;
                const spineR = { x: (lx0 + lx1) / 2, y: cy, hw: (lx1 - lx0) / 2, hd: driveWidth / 2, type: 'street' };
                const spinePoly = rotatePolygon([
                    { x: spineR.x - spineR.hw, y: spineR.y - spineR.hd },
                    { x: spineR.x + spineR.hw, y: spineR.y - spineR.hd },
                    { x: spineR.x + spineR.hw, y: spineR.y + spineR.hd },
                    { x: spineR.x - spineR.hw, y: spineR.y + spineR.hd },
                ], centroid, angle);
                features.push({ x: null, y: null, hw: null, hd: null, poly: spinePoly, type: 'street' });
                // connect aisles to spine
                for (const a of aisles) {
                    const gap = Math.abs(a.y - cy) - (a.hd + driveWidth / 2);
                    if (gap > 0) addConnectorIfSafe({ x: a.x, y: (a.y + cy) / 2, hw: driveWidth / 2, hd: gap / 2, type: 'aisle' });
                }
            }
        }

        // Build final features and preserve columns using the latest snapshot inside the state update
        setLevels(prev => {
            const cp = prev.slice();
            const colsLatest = (cp[currentLevelIndex]?.stallsPreview || []).filter(f => f && f.type === 'column');
            const finalFeatures = stalls
                .concat(features.map(f => ({ x: null, y: null, hw: null, hd: null, poly: f.poly, type: f.type })))
                .concat(colsLatest.map(c => ({ ...c })));
            cp.forEach((lvl, idx) => {
                if (idx === currentLevelIndex) {
                    cp[idx] = { ...cp[idx], stallsPreview: finalFeatures.map(f => ({ ...f })) };
                } else {
                    // leave other levels untouched
                    cp[idx] = { ...cp[idx] };
                }
            });
            return cp;
        });
        // update global preview for UI: include columns as well
        setStallsPreview(finalFeatures.filter(f => f.type === 'stall' || f.type === 'column'));
        setSelectedStalls([]);
        try { pushHistoryFrom(points, closed); } catch (e) { }
        // counts
        const colCount = existingFeatures.filter(f => f.type === 'column').length;
        const connectorCount = Math.max(0, (aisles.length - Math.max(0, Math.floor((maxYr - minYr - unitD) / spacingY))));
        setLastRunCounts({ stalls: stalls.length, aisles: features.length, connectors: autoConnectAisles ? connectorCount + connectorsAdded : connectorsAdded, columns: colCount });
        alert(`Aisle-first layout finished — stalls: ${stalls.length}, aisles: ${features.length}, connectors: ${(autoConnectAisles ? connectorCount : 0) + connectorsAdded}`);
    }

    // generate a regular column grid that fits inside the drawn boundary
    function generateColumns() {
        if (!points || points.length < 3) return alert('Draw and close a polygon first');
        // code-driven default column spacing (meters)
        const codeCols = { US: 7.5, CA: 7.5, AU: 7.2, UK: 7.2, SG: 6.0, IN: 6.0, DE: 7.5, FR: 7.5, default: 7.5 };
        const spacingMeters = (codeCols[selectedCode] || codeCols.default);
        // convert to user units (SVG units per meter)
        const spacingBase = Math.max(0.1, Number(unitsPerMeter || 1)) * spacingMeters;
        const colSizeMeters = Number(columnSizeMeters) || 0.5; // nominal column square side in meters (user-controlled)
        const colHalf = (colSizeMeters * Number(unitsPerMeter || 1)) / 2;

        const centroid = { x: points.reduce((s, p) => s + p.x, 0) / points.length, y: points.reduce((s, p) => s + p.y, 0) / points.length };
        // Column grid angle priority: explicit user angle > existing grid params angle > CPlane X direction > principal axis fallback
        let angle;
        if (columnGridAngleDeg !== null) angle = columnGridAngleDeg * Math.PI / 180;
        else if (columnGridParams && typeof columnGridParams.angle === 'number') angle = columnGridParams.angle;
        else if (cplaneXDir) angle = Math.atan2(cplaneXDir.y, cplaneXDir.x);
        else angle = computePrincipalAxis(points);
        const rotLot = rotatePolygon(points, centroid, -angle);
        const xsR = rotLot.map(p => p.x); const ysR = rotLot.map(p => p.y);
        const minXr = Math.min(...xsR), maxXr = Math.max(...xsR), minYr = Math.min(...ysR), maxYr = Math.max(...ysR);

        const placed = [];
        const allFeatures = (levels[currentLevelIndex]?.stallsPreview || []) || [];
        // when respecting existing features, only treat aisles/streets/ramps as blockers by default
        const featuresExisting = columnsRespectExisting ? allFeatures.filter(f => (f.type === 'aisle' || f.type === 'street' || f.type === 'ramp')).map(f => f.poly).filter(Boolean) : [];
        let candidateCount = 0, insideCount = 0, intersectCount = 0, acceptedCount = 0;
        const debugPts = [];

        // If a grid has been established already, use it exactly (spacing + offsets)
        if (columnGridParams && columnGridParams.spacingX && columnGridParams.spacingY) {
            const spacingXUnits = Math.max(1e-3, Number(columnGridParams.spacingX));
            const spacingYUnits = Math.max(1e-3, Number(columnGridParams.spacingY));
            const offX = Number(columnGridParams.offsetX || 0);
            const offY = Number(columnGridParams.offsetY || 0);
            const startGX = Math.floor((minXr - offX) / spacingXUnits) * spacingXUnits + offX;
            const startGY = Math.floor((minYr - offY) / spacingYUnits) * spacingYUnits + offY;
            for (let x = startGX; x <= maxXr; x += spacingXUnits) {
                for (let y = startGY; y <= maxYr; y += spacingYUnits) {
                    candidateCount++;
                    const worldCenter = rotatePoint({ x, y }, centroid, angle);
                    if (!pointInPolygon({ x, y }, rotLot)) { debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'outside' }); continue; }
                    insideCount++;
                    let polyR = null;
                    if (columnShape === 'template' && columnTemplate && columnTemplate.poly) {
                        const desiredUnits = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1);
                        const scale = desiredUnits / (columnTemplate.unitSize || 1);
                        polyR = columnTemplate.poly.map(p => ({ x: x + p.x * scale, y: y + p.y * scale }));
                    } else if (columnShape === 'circle') {
                        const radius = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1) / 2; const sides = 16; polyR = [];
                        for (let si = 0; si < sides; si++) { const a = (si / sides) * Math.PI * 2; polyR.push({ x: x + Math.cos(a) * radius, y: y + Math.sin(a) * radius }); }
                    } else {
                        const colHalfLocal = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1) / 2;
                        polyR = [{ x: x - colHalfLocal, y: y - colHalfLocal }, { x: x + colHalfLocal, y: y - colHalfLocal }, { x: x + colHalfLocal, y: y + colHalfLocal }, { x: x - colHalfLocal, y: y + colHalfLocal }];
                    }
                    const worldPoly = rotatePolygon(polyR, centroid, angle);
                    const aislesPolys = allFeatures.filter(f => (f.type === 'aisle' || f.type === 'street' || f.type === 'ramp')).map(f => f.poly).filter(Boolean);
                    const clearanceUnits = Math.max(0, Number(columnClearanceMeters || 0)) * Number(unitsPerMeter || 1);
                    let tooCloseToAisle = false; try { if (clearanceUnits > 0 && aislesPolys.length > 0) { for (const ap of aislesPolys) { const d = pointToPolygonDistance(worldCenter, ap); if (d < clearanceUnits) { tooCloseToAisle = true; break; } } } } catch (e) { }
                    if (tooCloseToAisle) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'near_aisle' }); continue; }
                    let intersects = false; if (columnsRespectExisting) { for (const ex of featuresExisting) { try { if (polygonsOverlap(ex, worldPoly)) { intersects = true; break; } } catch (e) { } } }
                    // Avoid stall footprints explicitly, and try nudging within span tolerance before giving up
                    let acceptedCenterR = null;
                    if (!intersects) {
                        const stallPolys = allFeatures.filter(f => f.type === 'stall').map(f => f.poly).filter(Boolean);
                        const thicknessXUnits = Math.max(1, Number(columnSizeMeters || 0.5)) * Number(unitsPerMeter || 1);
                        const thicknessYUnits = thicknessXUnits;
                        const tol = Math.max(0, Number(spanToleranceMeters || 0)) * Number(unitsPerMeter || 1);
                        const candidates = tol > 0 ? [
                            { x, y }, { x: x + tol, y }, { x: x - tol, y }, { x, y: y + tol }, { x, y: y - tol },
                            { x: x + tol, y: y + tol }, { x: x - tol, y: y - tol }, { x: x + tol, y: y - tol }, { x: x - tol, y: y + tol }
                        ] : [{ x, y }];
                        for (const c of candidates) {
                            const rect = makeColumnRect(c, thicknessXUnits, thicknessYUnits);
                            let bad = false;
                            for (const sp of stallPolys) { if (rectIntersectsPolygon(rect, sp)) { bad = true; break; } }
                            if (bad) continue;
                            // re-check aisle clearance distance for nudged center
                            let nearAisle = false; try { if (clearanceUnits > 0 && aislesPolys.length > 0) { for (const ap of aislesPolys) { const d = pointToPolygonDistance(c, ap); if (d < clearanceUnits) { nearAisle = true; break; } } } } catch (e) { }
                            if (nearAisle) continue;
                            acceptedCenterR = c; break;
                        }
                        if (!acceptedCenterR) intersects = true;
                    }
                    if (intersects) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'intersect' }); continue; }
                    // Shift footprint to accepted center if nudged
                    const dx = (acceptedCenterR ? acceptedCenterR.x : x) - x;
                    const dy = (acceptedCenterR ? acceptedCenterR.y : y) - y;
                    const shiftedR = polyR.map(p => ({ x: p.x + dx, y: p.y + dy }));
                    const finalWorldPoly = rotatePolygon(shiftedR, centroid, angle);
                    const finalWorldCenter = rotatePoint(acceptedCenterR ? acceptedCenterR : { x, y }, centroid, angle);
                    placed.push({ poly: finalWorldPoly, type: 'column', gridId: columnGridParams.gridId || 'G1' }); acceptedCount++; debugPts.push({ x: finalWorldCenter.x, y: finalWorldCenter.y, status: 'accepted' });
                }
            }
            setColumnDebugPoints(debugPts);
            setShowColumnDebug(prev => prev || placed.length === 0);
            if (placed.length === 0) return alert(`No column locations found for current grid. Tested ${candidateCount} centers, ${insideCount} inside lot, ${intersectCount} rejected.`);
            // Update grid angle in params and grids so dashed lines match used angle
            try {
                const gid = (columnGridParams && columnGridParams.gridId) ? columnGridParams.gridId : 'G1';
                setColumnGridParams(prev => prev ? { ...prev, angle } : prev);
                setColumnGrids(prev => Array.isArray(prev) ? prev.map(g => (g.id === gid ? { ...g, params: { ...g.params, angle } } : g)) : prev);
            } catch { }
            setLevels(prev => prev.map((l, i) => {
                if (i !== currentLevelIndex) return l;
                const base = columnsLocked ? (l.stallsPreview || []) : (l.stallsPreview || []).filter(f => f.type !== 'column');
                return { ...l, stallsPreview: base.concat(placed) };
            }));
            alert(`Placed ${placed.length} columns using current grid (X ${((columnGridParams.spacingX || 0) / Number(unitsPerMeter || 1)).toFixed(2)}m, Y ${((columnGridParams.spacingY || 0) / Number(unitsPerMeter || 1)).toFixed(2)}m). Tested ${candidateCount} centers, ${insideCount} inside, ${acceptedCount} accepted, ${intersectCount} rejected.`);
            return;
        }

        // if manual grid is enabled, use user-specified X/Y spacing (single pass)
        if (manualGridEnabled) {
            const spacingXUnits = Math.max(1e-3, Number(manualGridSpacingX || 1)) * Number(unitsPerMeter || 1);
            const spacingYUnits = Math.max(1e-3, Number(manualGridSpacingY || manualGridSpacingX || 1)) * Number(unitsPerMeter || 1);
            const startX = minXr + spacingXUnits / 2;
            const startY = minYr + spacingYUnits / 2;
            for (let x = startX; x <= maxXr - spacingXUnits / 2; x += spacingXUnits) {
                for (let y = startY; y <= maxYr - spacingYUnits / 2; y += spacingYUnits) {
                    candidateCount++;
                    const worldCenter = rotatePoint({ x, y }, centroid, angle);
                    if (!pointInPolygon({ x, y }, rotLot)) {
                        debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'outside' });
                        continue;
                    }
                    insideCount++;
                    // build candidate footprint
                    let polyR = null;
                    if (columnShape === 'template' && columnTemplate && columnTemplate.poly) {
                        const desiredUnits = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1);
                        const scale = desiredUnits / (columnTemplate.unitSize || 1);
                        polyR = columnTemplate.poly.map(p => ({ x: x + p.x * scale, y: y + p.y * scale }));
                    } else if (columnShape === 'circle') {
                        const radius = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1) / 2;
                        const sides = 16; polyR = [];
                        for (let si = 0; si < sides; si++) { const a = (si / sides) * Math.PI * 2; polyR.push({ x: x + Math.cos(a) * radius, y: y + Math.sin(a) * radius }); }
                    } else {
                        const colHalfLocal = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1) / 2;
                        polyR = [{ x: x - colHalfLocal, y: y - colHalfLocal }, { x: x + colHalfLocal, y: y - colHalfLocal }, { x: x + colHalfLocal, y: y + colHalfLocal }, { x: x - colHalfLocal, y: y + colHalfLocal }];
                    }
                    const worldPoly = rotatePolygon(polyR, centroid, angle);
                    // clearance to aisles
                    const aislesPolys = allFeatures.filter(f => (f.type === 'aisle' || f.type === 'street' || f.type === 'ramp')).map(f => f.poly).filter(Boolean);
                    const clearanceUnits = Math.max(0, Number(columnClearanceMeters || 0)) * Number(unitsPerMeter || 1);
                    let tooCloseToAisle = false;
                    try { if (clearanceUnits > 0 && aislesPolys.length > 0) { for (const ap of aislesPolys) { const d = pointToPolygonDistance(worldCenter, ap); if (d < clearanceUnits) { tooCloseToAisle = true; break; } } } } catch (e) { tooCloseToAisle = false; }
                    if (tooCloseToAisle) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'near_aisle' }); continue; }
                    let intersects = false;
                    if (columnsRespectExisting) { for (const ex of featuresExisting) { try { if (polygonsOverlap(ex, worldPoly)) { intersects = true; break; } } catch (e) { } } }
                    // Avoid stall footprints; attempt span-tolerance nudge before giving up
                    let acceptedCenterR = null;
                    if (!intersects) {
                        const stallPolys = allFeatures.filter(f => f.type === 'stall').map(f => f.poly).filter(Boolean);
                        const thicknessXUnits = Math.max(1, Number(columnSizeMeters || 0.5)) * Number(unitsPerMeter || 1);
                        const thicknessYUnits = thicknessXUnits;
                        const tol = Math.max(0, Number(spanToleranceMeters || 0)) * Number(unitsPerMeter || 1);
                        const candidates = tol > 0 ? [
                            { x, y }, { x: x + tol, y }, { x: x - tol, y }, { x, y: y + tol }, { x, y: y - tol },
                            { x: x + tol, y: y + tol }, { x: x - tol, y: y - tol }, { x: x + tol, y: y - tol }, { x: x - tol, y: y + tol }
                        ] : [{ x, y }];
                        for (const c of candidates) {
                            const rect = makeColumnRect(c, thicknessXUnits, thicknessYUnits);
                            let bad = false; for (const sp of stallPolys) { if (rectIntersectsPolygon(rect, sp)) { bad = true; break; } }
                            if (bad) continue;
                            // aisle clearance check at nudged center
                            const aislesPolys = allFeatures.filter(f => (f.type === 'aisle' || f.type === 'street' || f.type === 'ramp')).map(f => f.poly).filter(Boolean);
                            const clearanceUnits = Math.max(0, Number(columnClearanceMeters || 0)) * Number(unitsPerMeter || 1);
                            let nearAisle = false; try { if (clearanceUnits > 0 && aislesPolys.length > 0) { for (const ap of aislesPolys) { const d = pointToPolygonDistance(c, ap); if (d < clearanceUnits) { nearAisle = true; break; } } } } catch (e) { }
                            if (nearAisle) continue;
                            acceptedCenterR = c; break;
                        }
                        if (!acceptedCenterR) intersects = true;
                    }
                    if (intersects) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'intersect' }); continue; }
                    const dx = (acceptedCenterR ? acceptedCenterR.x : x) - x;
                    const dy = (acceptedCenterR ? acceptedCenterR.y : y) - y;
                    const shiftedR = polyR.map(p => ({ x: p.x + dx, y: p.y + dy }));
                    const finalWorldPoly = rotatePolygon(shiftedR, centroid, angle);
                    const finalWorldCenter = rotatePoint(acceptedCenterR ? acceptedCenterR : { x, y }, centroid, angle);
                    placed.push({ poly: finalWorldPoly, type: 'column' }); acceptedCount++; debugPts.push({ x: finalWorldCenter.x, y: finalWorldCenter.y, status: 'accepted' });
                }
            }
            setColumnDebugPoints(debugPts);
            setShowColumnDebug(prev => prev || placed.length === 0);
            if (placed.length === 0) return alert(`No column locations found for manual spacing. Tested ${candidateCount} centers, ${insideCount} inside lot, ${intersectCount} rejected.`);
            // Save grid params so dashed grid matches exact sampling used
            const mod = (v, s) => ((v % s) + s) % s;
            const manualGridId = `G${columnGrids.length + 1}`;
            const manualParams = { angle, spacingX: spacingXUnits, spacingY: spacingYUnits, offsetX: mod(startX, spacingXUnits), offsetY: mod(startY, spacingYUnits), gridId: manualGridId };
            setColumnGridParams(manualParams);
            setColumnGrids(prev => (columnsLocked ? prev.concat({ id: manualGridId, params: manualParams, visible: true }) : [{ id: manualGridId, params: manualParams, visible: true }]));
            setLevels(prev => prev.map((l, i) => {
                if (i !== currentLevelIndex) return l;
                const base = columnsLocked ? (l.stallsPreview || []) : (l.stallsPreview || []).filter(f => f.type !== 'column');
                return { ...l, stallsPreview: base.concat(placed.map(p => ({ ...p, gridId: manualGridId }))) };
            }));
            alert(`Placed ${placed.length} columns using manual spacing. Tested ${candidateCount} centers, ${insideCount} inside, ${acceptedCount} accepted, ${intersectCount} rejected.`);
            return;
        }
        const attempts = [1, 0.75, 0.5, 0.33, 0.25];
        let usedFactor = null;
        for (const factor of attempts) {
            const spacing = Math.max(1e-3, spacingBase * factor);
            const startX = minXr + spacing / 2;
            const startY = minYr + spacing / 2;
            const placedLocal = [];
            for (let x = startX; x <= maxXr - spacing / 2; x += spacing) {
                for (let y = startY; y <= maxYr - spacing / 2; y += spacing) {
                    candidateCount++;
                    const worldCenter = rotatePoint({ x, y }, centroid, angle);
                    if (!pointInPolygon({ x, y }, rotLot)) {
                        debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'outside' });
                        continue;
                    }
                    insideCount++;
                    // build candidate footprint in rotated-lot coordinates according to selected shape/template
                    let polyR = null;
                    if (columnShape === 'template' && columnTemplate && columnTemplate.poly) {
                        // scale normalized template so its max-dimension equals desired size in user units
                        const desiredUnits = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1);
                        const scale = desiredUnits / (columnTemplate.unitSize || 1);
                        polyR = columnTemplate.poly.map(p => ({ x: x + p.x * scale, y: y + p.y * scale }));
                    } else if (columnShape === 'circle') {
                        const radius = (Number(columnSizeMeters) || 0.5) * Number(unitsPerMeter || 1) / 2;
                        const sides = 16;
                        polyR = [];
                        for (let si = 0; si < sides; si++) {
                            const a = (si / sides) * Math.PI * 2;
                            polyR.push({ x: x + Math.cos(a) * radius, y: y + Math.sin(a) * radius });
                        }
                    } else {
                        // square by default
                        polyR = [
                            { x: x - colHalf, y: y - colHalf },
                            { x: x + colHalf, y: y - colHalf },
                            { x: x + colHalf, y: y + colHalf },
                            { x: x - colHalf, y: y + colHalf }
                        ];
                    }
                    const worldPoly = rotatePolygon(polyR, centroid, angle);
                    // check clearance to any aisle/street/ramp polygons (in world coords)
                    const aislesPolys = allFeatures.filter(f => (f.type === 'aisle' || f.type === 'street' || f.type === 'ramp')).map(f => f.poly).filter(Boolean);
                    const clearanceUnits = Math.max(0, Number(columnClearanceMeters || 0)) * Number(unitsPerMeter || 1);
                    let tooCloseToAisle = false;
                    try {
                        if (clearanceUnits > 0 && aislesPolys.length > 0) {
                            for (const ap of aislesPolys) {
                                try {
                                    const d = pointToPolygonDistance(worldCenter, ap);
                                    if (d < clearanceUnits) { tooCloseToAisle = true; break; }
                                } catch (e) { }
                            }
                        }
                    } catch (e) { tooCloseToAisle = false; }
                    if (tooCloseToAisle) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'near_aisle' }); continue; }
                    let intersects = false;
                    if (columnsRespectExisting) {
                        for (const ex of featuresExisting) {
                            try { if (polygonsOverlap(ex, worldPoly)) { intersects = true; break; } } catch (e) { }
                        }
                    }
                    if (intersects) { intersectCount++; debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'intersect' }); continue; }
                    placedLocal.push({ poly: worldPoly, type: 'column' });
                    acceptedCount++;
                    debugPts.push({ x: worldCenter.x, y: worldCenter.y, status: 'accepted' });
                }
            }
            if (placedLocal.length > 0) { placed.push(...placedLocal); usedFactor = factor; break; }
        }
        // expose debug points so user can visualize tested centers
        setColumnDebugPoints(debugPts);
        setShowColumnDebug(prev => prev || placed.length === 0);

        if (placed.length === 0) {
            return alert(`No column locations found for the selected spacing (${spacingMeters}m) and lot. Tested ${candidateCount} centers, ${insideCount} inside lot, ${intersectCount} rejected by intersecting existing features.` + (columnsRespectExisting ? ' You can uncheck "Avoid existing features" to force placements.' : ''));
        }
        // Save grid params for auto mode using the spacing that accepted points were sampled from
        const spacingUsed = Math.max(1e-3, spacingBase * (usedFactor || 1));
        const mod = (v, s) => ((v % s) + s) % s;
        const autoStartX = minXr + spacingUsed / 2;
        const autoStartY = minYr + spacingUsed / 2;
        const autoGridId = `G${columnGrids.length + 1}`;
        const autoParams = { angle, spacingX: spacingUsed, spacingY: spacingUsed, offsetX: mod(autoStartX, spacingUsed), offsetY: mod(autoStartY, spacingUsed), gridId: autoGridId };
        setColumnGridParams(autoParams);
        setColumnGrids(prev => (columnsLocked ? prev.concat({ id: autoGridId, params: autoParams, visible: true }) : [{ id: autoGridId, params: autoParams, visible: true }]));

        setLevels(prev => prev.map((l, i) => {
            if (i !== currentLevelIndex) return l;
            const base = columnsLocked ? (l.stallsPreview || []) : (l.stallsPreview || []).filter(f => f.type !== 'column');
            return { ...l, stallsPreview: base.concat(placed.map(p => ({ ...p, gridId: autoGridId }))) };
        }));
        alert(`Placed ${placed.length} columns using ${spacingMeters * (usedFactor || 1)}m effective spacing (requested ${spacingMeters}m). Tested ${candidateCount} centers, ${insideCount} inside, ${acceptedCount} accepted, ${intersectCount} rejected.`);
    }

    // optimizeLayout removed (moderate cleanup). Use the Aisle-first generator and explicit optimization tooling.

    // helper: sample points inside a rectangle to ensure the candidate feature lies mostly inside the polygon
    function sampleRectInside(rect, poly, samples = 6) {
        // deterministic grid sampling across rect (avoids randomness)
        if (!poly || poly.length < 3) return false;
        const sx = rect.x - rect.hw, ex = rect.x + rect.hw;
        const sy = rect.y - rect.hd, ey = rect.y + rect.hd;
        const n = Math.max(2, Math.ceil(Math.sqrt(samples)));
        let insideCount = 0; let total = 0;
        for (let i = 0; i < n; i++) {
            const tx = sx + (i + 0.5) * (ex - sx) / n;
            for (let j = 0; j < n; j++) {
                const ty = sy + (j + 0.5) * (ey - sy) / n;
                total++;
                if (pointInPolygon({ x: tx, y: ty }, poly)) insideCount++;
            }
        }
        return insideCount / total >= 0.6; // keep feature if >=60% of samples fall inside
    }

    // axis-aligned rectangle intersection test (rectangles stored as center x,y and half-widths hw,hd)
    function rectsIntersect(a, b) {
        const aMinX = a.x - a.hw, aMaxX = a.x + a.hw, aMinY = a.y - a.hd, aMaxY = a.y + a.hd;
        const bMinX = b.x - b.hw, bMaxX = b.x + b.hw, bMinY = b.y - b.hd, bMaxY = b.y + b.hd;
        return !(aMaxX <= bMinX || aMinX >= bMaxX || aMaxY <= bMinY || aMinY >= bMaxY);
    }

    function polygonBoundingBox(poly) {
        if (!poly || poly.length === 0) return null;
        const xs = poly.map(p => p.x); const ys = poly.map(p => p.y);
        return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
    }

    // normalize a template polygon: center at origin and compute unit size (max span)
    function normalizeTemplatePoly(poly) {
        if (!poly || poly.length < 3) return null;
        const c = centroidOf(poly);
        const shifted = poly.map(p => ({ x: p.x - c.x, y: p.y - c.y }));
        const bb = polygonBoundingBox(shifted);
        const spanX = bb.maxX - bb.minX; const spanY = bb.maxY - bb.minY;
        const unitSize = Math.max(spanX, spanY) || 1;
        const normalized = shifted.map(p => ({ x: p.x / unitSize, y: p.y / unitSize }));
        return { poly: normalized, unitSize };
    }

    function tryParseGeoJSON(text) {
        try {
            const obj = JSON.parse(text);
            if (obj.type === 'FeatureCollection') {
                for (const f of obj.features || []) {
                    if (f.geometry && (f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon')) {
                        const coords = (f.geometry.type === 'Polygon') ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0];
                        const poly = coords.map(c => ({ x: Number(c[0]), y: Number(c[1]) }));
                        return poly;
                    }
                }
            } else if (obj.type === 'Feature' && obj.geometry && obj.geometry.type === 'Polygon') {
                const coords = obj.geometry.coordinates[0];
                return coords.map(c => ({ x: Number(c[0]), y: Number(c[1]) }));
            }
        } catch (e) { }
        return null;
    }

    function tryParseSVG(text) {
        try {
            // look for <polygon points="..." />
            const polyMatch = text.match(/<polygon[^>]*points=["']([^"']+)["'][^>]*>/i);
            if (polyMatch) {
                const pts = polyMatch[1].trim().split(/\s+|,/).map(Number);
                const poly = [];
                for (let i = 0; i + 1 < pts.length; i += 2) poly.push({ x: pts[i], y: pts[i + 1] });
                if (poly.length >= 3) return poly;
            }
            // look for simple path 'M x y L x y ... Z' patterns
            const pathMatch = text.match(/<path[^>]*d=["']([^"']+)["'][^>]*>/i);
            if (pathMatch) {
                const d = pathMatch[1];
                const nums = d.match(/-?[0-9]*\.?[0-9]+/g)?.map(Number) || [];
                const poly = [];
                for (let i = 0; i + 1 < nums.length; i += 2) poly.push({ x: nums[i], y: nums[i + 1] });
                if (poly.length >= 3) return poly;
            }
        } catch (e) { }
        return null;
    }

    function handleTemplateUpload(e) {
        const f = e.target.files && e.target.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            const text = String(ev.target.result || '');
            let poly = tryParseGeoJSON(text);
            if (!poly) poly = tryParseSVG(text);
            if (!poly) return alert('Could not parse template file (expect GeoJSON Polygon or simple SVG polygon/path)');
            const norm = normalizeTemplatePoly(poly);
            setColumnTemplate({ name: f.name, poly: norm.poly, unitSize: norm.unitSize });
            setColumnShape('template');
            e.target.value = null;
        };
        reader.readAsText(f);
    }

    function pointToSegmentDistance(p, a, b) {
        // Delegate to single distance helper
        return distPointToSegment(p, a, b);
    }

    function pointToPolygonDistance(pt, poly) {
        if (!poly || poly.length === 0) return Infinity;
        // if inside, distance is 0
        if (pointInPolygon(pt, poly)) return 0;
        let minD = Infinity;
        for (let i = 0; i < poly.length; i++) {
            const a = poly[i]; const b = poly[(i + 1) % poly.length];
            const d = pointToSegmentDistance(pt, a, b);
            if (d < minD) minD = d;
        }
        return minD;
    }

    function polygonsOverlap(a, b) {
        if (!a || !b || !a.length || !b.length) return false;
        const clipped = polygonClip(a, b);
        const area = computePolygonArea(clipped);
        return area > 1e-6;
    }

    function centroidOf(poly) {
        if (!poly || poly.length === 0) return { x: 0, y: 0 };
        let cx = 0, cy = 0; let A = 0;
        for (let i = 0; i < poly.length; i++) {
            const a = poly[i]; const b = poly[(i + 1) % poly.length];
            const cross = a.x * b.y - b.x * a.y; A += cross; cx += (a.x + b.x) * cross; cy += (a.y + b.y) * cross;
        }
        A = A / 2;
        if (Math.abs(A) < 1e-9) return { x: poly[0].x, y: poly[0].y };
        return { x: cx / (6 * A), y: cy / (6 * A) };
    }

    // validate current layout on the active level
    function validateLayout() {
        const lvl = (levels && levels[currentLevelIndex]) || null;
        if (!lvl) return alert('No level loaded');
        const items = lvl.stallsPreview || [];
        const stalls = items.map((it, idx) => ({ ...it, _idx: idx })).filter(i => i.type === 'stall');
        const aisles = items.map((it, idx) => ({ ...it, _idx: idx })).filter(i => i.type === 'aisle' || i.type === 'street' || i.type === 'ramp');
        const results = [];

        // 1) Overlap checks between stalls
        for (let i = 0; i < stalls.length; i++) {
            for (let j = i + 1; j < stalls.length; j++) {
                try {
                    if (polygonsOverlap(stalls[i].poly, stalls[j].poly)) {
                        results.push({ type: 'overlap', message: `Stall ${stalls[i]._idx} overlaps stall ${stalls[j]._idx}`, items: [stalls[i]._idx, stalls[j]._idx], suggestion: 'Remove one of the overlapping stalls.' });
                    }
                } catch (e) { /* ignore bad polys */ }
            }
        }

        // 2) Stalls partially or fully outside lot
        if (points && points.length >= 3) {
            for (const s of stalls) {
                const outsideCount = (s.poly || []).filter(p => !pointInPolygon(p, points)).length;
                if (outsideCount > 0) {
                    results.push({ type: 'outside', message: `Stall ${s._idx} is partially outside the lot (${outsideCount}/${(s.poly || []).length} corners)`, items: [s._idx], suggestion: 'Move or remove this stall.' });
                }
            }
        }

        // compute typical drive width for accessibility tests (respect selected code prefs)
        // convert stall depth to meters first (UI may be in ft when unitSystem==='imperial')
        const _stallDepth_m = unitSystem === 'imperial' ? feetToMeters(Number(stallDepth)) : Number(stallDepth);
        const unitD = _stallDepth_m * unitsPerMeter;
        const codePrefs_local = {
            US: { twoWay: true, driveWidthMeters: 6 }, UK: { twoWay: false, driveWidthMeters: 3.6 },
            CA: { twoWay: true, driveWidthMeters: 6 }, AU: { twoWay: true, driveWidthMeters: 6 },
            SG: { twoWay: false, driveWidthMeters: 3.5 }, IN: { twoWay: false, driveWidthMeters: 3.5 },
            DE: { twoWay: true, driveWidthMeters: 6 }, FR: { twoWay: true, driveWidthMeters: 6 },
            default: { twoWay: true, driveWidthMeters: 6 }
        };
        const pref_local = (codePrefs_local[selectedCode] || codePrefs_local.default);
        const driveWidth = Math.max((pref_local.driveWidthMeters || 6) * unitsPerMeter, unitD * 0.8);

        // 3) Isolated stalls: no aisle within reasonable approach distance
        for (const s of stalls) {
            const c = centroidOf(s.poly || []);
            let nearAisle = false;
            for (const a of aisles) {
                const d = pointToPolygonDistance(c, a.poly || []);
                if (d <= Math.max(driveWidth * 1.2, unitD)) { nearAisle = true; break; }
            }
            if (!nearAisle) {
                results.push({ type: 'isolated', message: `Stall ${s._idx} appears isolated (no aisle within ${Math.round(Math.max(driveWidth * 1.2, unitD))} units)`, items: [s._idx], suggestion: 'Consider adding an aisle or moving the stall.' });
            }
        }

        // 4) Aisle continuity: group aisles by adjacency and report disconnected components
        if (aisles.length > 0 && autoConnectAisles) {
            const adj = new Map();
            for (let i = 0; i < aisles.length; i++) adj.set(aisles[i]._idx, new Set());
            for (let i = 0; i < aisles.length; i++) {
                const A = aisles[i]; const bbA = polygonBoundingBox(A.poly || []);
                for (let j = i + 1; j < aisles.length; j++) {
                    const B = aisles[j]; const bbB = polygonBoundingBox(B.poly || []);
                    if (!bbA || !bbB) continue;
                    // expand bboxes slightly for gap tolerance
                    const pad = 4 * unitsPerMeter;
                    const Ai = { x: (bbA.minX + bbA.maxX) / 2, y: (bbA.minY + bbA.maxY) / 2, hw: (bbA.maxX - bbA.minX) / 2 + pad, hd: (bbA.maxY - bbA.minY) / 2 + pad };
                    const Bi = { x: (bbB.minX + bbB.maxX) / 2, y: (bbB.minY + bbB.maxY) / 2, hw: (bbB.maxX - bbB.minX) / 2 + pad, hd: (bbB.maxY - bbB.minY) / 2 + pad };
                    if (rectsIntersect(Ai, Bi) || polygonsOverlap(A.poly, B.poly)) {
                        adj.get(A._idx).add(B._idx); adj.get(B._idx).add(A._idx);
                    }
                }
            }
            // find components
            const visited = new Set(); const components = [];
            for (const a of aisles) {
                if (visited.has(a._idx)) continue;
                const comp = []; const stack = [a._idx];
                while (stack.length) {
                    const n = stack.pop(); if (visited.has(n)) continue; visited.add(n); comp.push(n);
                    for (const nb of adj.get(n) || []) if (!visited.has(nb)) stack.push(nb);
                }
                components.push(comp);
            }
            if (components.length > 1) {
                results.push({ type: 'aisle_disconnected', message: `Aisles are disconnected into ${components.length} groups`, items: components, suggestion: 'Add connectors or extend aisles so circulation is continuous.' });
                // Auto-connect components with simple connectors aligned to lot axes
                const centers = aisles.map(a => {
                    const bb = polygonBoundingBox(a.poly || []);
                    return { idx: a._idx, x: (bb.minX + bb.maxX) / 2, y: (bb.minY + bb.maxY) / 2 };
                });
                const byIdx = new Map(centers.map(c => [c.idx, c]));
                const drive = driveWidth;
                const connectorsR = [];
                for (let ci = 0; ci < components.length - 1; ci++) {
                    const compA = components[ci];
                    const compB = components[ci + 1];
                    let best = null;
                    for (const ia of compA) {
                        for (const ib of compB) {
                            const ca = byIdx.get(ia), cb = byIdx.get(ib);
                            const d = Math.hypot(ca.x - cb.x, ca.y - cb.y);
                            if (!best || d < best.d) best = { a: ca, b: cb, d };
                        }
                    }
                    if (best) {
                        // Simple straight connector along X or Y based on shorter delta
                        const horiz = Math.abs(best.a.x - best.b.x) >= Math.abs(best.a.y - best.b.y);
                        if (horiz) {
                            const midY = (best.a.y + best.b.y) / 2;
                            const cx = (best.a.x + best.b.x) / 2;
                            connectorsR.push({ x: cx, y: midY, hw: Math.abs(best.a.x - best.b.x) / 2, hd: drive / 2, type: 'aisle' });
                        } else {
                            const midX = (best.a.x + best.b.x) / 2;
                            const cy = (best.a.y + best.b.y) / 2;
                            connectorsR.push({ x: midX, y: cy, hw: drive / 2, hd: Math.abs(best.a.y - best.b.y) / 2, type: 'aisle' });
                        }
                    }
                }
                // append connectors that don't overlap columns (in rotated space)
                const safeConnectors = [];
                for (const a of connectorsR) {
                    const rectPoly = [
                        { x: a.x - a.hw, y: a.y - a.hd },
                        { x: a.x + a.hw, y: a.y - a.hd },
                        { x: a.x + a.hw, y: a.y + a.hd },
                        { x: a.x - a.hw, y: a.y + a.hd },
                    ];
                    let bad = false;
                    for (const cpoly of existingColumnsR) {
                        try { if (polygonsOverlap(rectPoly, cpoly)) { bad = true; break; } } catch (e) { }
                    }
                    if (!bad) safeConnectors.push(a);
                }
                aisles.push(...safeConnectors);
            }
        }

        if (results.length === 0) {
            setValidateResults([{ type: 'ok', message: 'No issues found. Layout looks good.', items: [] }]);
            alert('Validation complete — no issues found.');
        } else {
            setValidateResults(results);
            // also show a concise alert
            alert(`Validation found ${results.length} issues — see Diagnostics panel for details.`);
        }
    }

    function removeStallsByIndices(levelIndex, indices) {
        setLevels(prev => prev.map((l, i) => {
            if (i !== levelIndex) return l;
            const nextStalls = (l.stallsPreview || []).filter((s, si) => !indices.includes(si));
            return { ...l, stallsPreview: nextStalls };
        }));
        setValidateResults(null);
    }

    // polygon clipping: Sutherland-Hodgman (clips subject polygon by clip polygon)
    // Note: works best when clip polygon is convex. For complex concave lots this is a reasonable approximation.
    function polygonClip(subject, clip) {
        if (!subject || subject.length === 0) return [];
        let outputList = subject.slice();
        const cpLen = clip.length;
        for (let i = 0; i < cpLen; i++) {
            const inputList = outputList.slice();
            outputList = [];
            const A = clip[i];
            const B = clip[(i + 1) % cpLen];

            const isInside = (p) => {
                // inside test: point is to left of edge AB
                return ((B.x - A.x) * (p.y - A.y) - (B.y - A.y) * (p.x - A.x)) >= 0;
            };

            const computeIntersection = (P, Q) => {
                // line-line intersection between segment PQ and AB
                const A1 = Q.y - P.y;
                const B1 = P.x - Q.x;
                const C1 = A1 * P.x + B1 * P.y;
                const A2 = B.y - A.y;
                const B2 = A.x - B.x;
                const C2 = A2 * A.x + B2 * A.y;
                const det = A1 * B2 - A2 * B1;
                if (Math.abs(det) < 1e-9) return null;
                const x = (B2 * C1 - B1 * C2) / det;
                const y = (A1 * C2 - A2 * C1) / det;
                return { x, y };
            };

            if (inputList.length === 0) break;
            let S = inputList[inputList.length - 1];
            for (const E of inputList) {
                if (isInside(E)) {
                    if (!isInside(S)) {
                        const ip = computeIntersection(S, E);
                        if (ip) outputList.push(ip);
                    }
                    outputList.push(E);
                } else if (isInside(S)) {
                    const ip = computeIntersection(S, E);
                    if (ip) outputList.push(ip);
                }
                S = E;
            }
        }
        return outputList;
    }

    // rotate a point around origin by angle (radians)
    function rotatePoint(p, origin, angle) {
        const s = Math.sin(angle), c = Math.cos(angle);
        const tx = p.x - origin.x, ty = p.y - origin.y;
        return { x: origin.x + (tx * c - ty * s), y: origin.y + (tx * s + ty * c) };
    }

    function rotatePolygon(poly, origin, angle) {
        return poly.map(p => rotatePoint(p, origin, angle));
    }

    // compute principal axis angle (radians) of polygon via covariance (PCA)
    function computePrincipalAxis(poly) {
        if (!poly || poly.length === 0) return 0;
        const cx = poly.reduce((s, p) => s + p.x, 0) / poly.length;
        const cy = poly.reduce((s, p) => s + p.y, 0) / poly.length;
        let sxx = 0, sxy = 0, syy = 0;
        for (const p of poly) {
            const dx = p.x - cx, dy = p.y - cy;
            sxx += dx * dx; sxy += dx * dy; syy += dy * dy;
        }
        // angle of principal eigenvector
        const theta = 0.5 * Math.atan2(2 * sxy, sxx - syy);
        return theta; // radians
    }

    function toggleStallSelection(idx, levelIndex, e) {
        if (e) e.stopPropagation();
        if (levelIndex !== currentLevelIndex) setCurrentLevelIndex(levelIndex);
        // only allow selecting real stalls (not aisles/streets/ramps)
        const lvl = levels[levelIndex] || {};
        const item = (lvl.stallsPreview || [])[idx];
        if (!item || item.type !== 'stall') return; // ignore non-stall clicks
        setSelectedStalls(prev => {
            const has = prev.includes(idx);
            if (has) return prev.filter(i => i !== idx);
            return [...prev, idx].sort((a, b) => a - b);
        });
    }

    function deleteSelectedStalls() {
        if (!selectedStalls || selectedStalls.length === 0) return;
        setLevels(prev => prev.map((l, i) => {
            if (i !== currentLevelIndex) return l;
            const nextStalls = (l.stallsPreview || []).filter((s, si) => !selectedStalls.includes(si));
            return { ...l, stallsPreview: nextStalls };
        }));
        // clear selection and update preview
        setSelectedStalls([]);
        setStallsPreview([]);
    }

    // finalize a manual insertion rectangle as a feature (aisle/street/ramp/access)
    function finalizeInsertionRect(rect) {
        if (!rect) return;
        const x = rect.x + rect.w / 2; const y = rect.y + rect.h / 2; const hw = rect.w / 2; const hd = rect.h / 2;
        const baseFeature = { x, y, hw, hd, type: insertionMode };
        // determine ramp endpoints if inserting a ramp
        if (insertionMode === 'ramp') {
            baseFeature.from = currentLevelIndex;
            baseFeature.to = Math.min(currentLevelIndex + 1, Math.max(0, (levels || []).length - 1));
        }

        setLevels(prev => prev.map((lvl, idx) => {
            // remove intersecting stalls from this level so the band is continuous
            const filtered = (lvl.stallsPreview || []).filter(s => !(s.type === 'stall' && rectsIntersect(s, baseFeature)));
            // ramps should be present on both connected levels
            if (insertionMode === 'ramp') {
                if (idx === baseFeature.from || idx === baseFeature.to) {
                    return { ...lvl, stallsPreview: filtered.concat([{ ...baseFeature }]) };
                }
                return { ...lvl, stallsPreview: filtered };
            }
            return { ...lvl, stallsPreview: filtered.concat([{ ...baseFeature }]) };
        }));
        setSelectedStalls([]);
        setStallsPreview([]);
    }

    function clearStallsOnLevel() {
        setLevels(prev => prev.map((l, i) => {
            if (i !== currentLevelIndex) return l;
            const keep = columnsLocked ? (l.stallsPreview || []).filter(f => f.type === 'column') : [];
            return { ...l, stallsPreview: keep };
        }));
        setSelectedStalls([]);
        setStallsPreview([]);
        // also clear any debug/diagnostic overlays related to columns
        setColumnDebugPoints([]);
        setShowColumnDebug(false);
        setClipDiagnostics([]);
        setValidateResults(null);
    }

    // level management
    function addLevel(elevation) {
        setLevels(prev => {
            const id = Date.now().toString(36);
            const name = `Level ${prev.length + 1}`;
            const elev = typeof elevation === 'number' ? elevation : ((prev[currentLevelIndex]?.elevation) || 0) + DEFAULT_FLOOR_HEIGHT;
            const item = { id, name, stallsPreview: [], visible: true, elevation: elev };
            const next = prev.concat(item).slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const newIndex = next.findIndex(l => l.id === id);
            setCurrentLevelIndex(newIndex === -1 ? 0 : newIndex);
            return next;
        });
    }

    function duplicateLevel(idx) {
        setLevels(prev => {
            const copy = prev.slice();
            const src = copy[idx] || prev[0];
            const id = Date.now().toString(36);
            const newItem = { id, name: `${src.name} copy`, stallsPreview: (src.stallsPreview || []).map(s => ({ ...s })), visible: true, elevation: src.elevation };
            copy.splice(idx + 1, 0, newItem);
            const next = copy.slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const newIndex = next.findIndex(l => l.id === id);
            setCurrentLevelIndex(newIndex === -1 ? 0 : newIndex);
            return next;
        });
    }

    function removeLevel(idx) {
        if (levels.length <= 1) return alert('Cannot remove the last level');
        setLevels(prev => {
            const copy = prev.slice();
            copy.splice(idx, 1);
            const next = copy.slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const newIndex = Math.min(Math.max(0, idx - 1), next.length - 1);
            setCurrentLevelIndex(newIndex);
            return next;
        });
    }

    function toggleLevelVisibility(idx) {
        setLevels(prev => prev.map((l, i) => i === idx ? { ...l, visible: !l.visible } : l));
    }

    function renameLevel(idx, newName) {
        setLevels(prev => prev.map((l, i) => i === idx ? { ...l, name: newName } : l));
    }

    // add an underground level below current level with a default negative elevation
    function addUndergroundLevel() {
        setLevels(prev => {
            const currentElevation = (prev[currentLevelIndex]?.elevation) || 0;
            const elev = currentElevation - DEFAULT_FLOOR_HEIGHT;
            const id = Date.now().toString(36);
            const undergroundCount = prev.filter(l => (Number(l.elevation) || 0) < 0).length;
            const name = `B${undergroundCount + 1}`;
            const item = { id, name, stallsPreview: [], visible: true, elevation: elev };
            const next = prev.concat(item).slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const newIndex = next.findIndex(l => l.id === id);
            setCurrentLevelIndex(newIndex === -1 ? 0 : newIndex);
            return next;
        });
    }

    // begin inline edit: set editing state so UI can render an input instead of a prompt
    function editLevelElevation(idx) {
        const lvl = levels[idx];
        if (!lvl) return;
        setEditingElevationIdx(idx);
        setEditingElevationValue(String(Number(lvl.elevation) || 0));
    }

    function commitLevelElevation(idx, rawVal) {
        const n = Number(rawVal);
        if (!Number.isFinite(n)) return alert('Invalid elevation');
        setLevels(prev => {
            const updated = prev.map((l, i) => i === idx ? { ...l, elevation: n } : l);
            const sorted = updated.slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const currentId = prev[idx]?.id;
            const newIndex = sorted.findIndex(l => l.id === currentId);
            setCurrentLevelIndex(newIndex === -1 ? 0 : newIndex);
            return sorted;
        });
        setEditingElevationIdx(null);
        setEditingElevationValue('');
    }

    function cancelEditElevation() {
        setEditingElevationIdx(null);
        setEditingElevationValue('');
    }

    // small schemes (iterations) feature: save/load/compare different layouts
    function randColor() {
        // muted palette so schemes remain distinguishable without bright accents
        const PALETTE = ['#475569', '#334155', '#475b67', '#52525b', '#4b5563', '#374151', '#3f3f46'];
        const idx = Math.floor(Math.random() * PALETTE.length);
        return PALETTE[idx];
    }

    // persist schemes to localStorage
    const LS_SCHEMES_KEY = 'parkcore_schemes_v1';
    React.useEffect(() => {
        try {
            const raw = localStorage.getItem(LS_SCHEMES_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) setSchemes(parsed);
            }
        } catch (err) {
            // ignore localStorage errors
            console.warn('Failed to load schemes from localStorage', err);
        }
    }, []);

    // persist levels to localStorage so underground / multi-level setups are retained
    const LS_LEVELS_KEY = 'parkcore_levels_v1';
    React.useEffect(() => {
        try {
            const raw = localStorage.getItem(LS_LEVELS_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) setLevels(parsed);
            }
        } catch (err) {
            console.warn('Failed to load levels from localStorage', err);
        }
    }, []);

    React.useEffect(() => {
        try {
            localStorage.setItem(LS_LEVELS_KEY, JSON.stringify(levels));
        } catch (err) {
            console.warn('Failed to save levels to localStorage', err);
        }
    }, [levels]);

    // Keep levels ordered by elevation (ascending: underground first B1, then ground, then upper levels)
    React.useEffect(() => {
        setLevels(prev => {
            if (!Array.isArray(prev) || prev.length <= 1) return prev;
            const sorted = prev.slice().sort((a, b) => (Number(a.elevation) || 0) - (Number(b.elevation) || 0));
            const prevIds = prev.map(l => l.id).join(',');
            const sortedIds = sorted.map(l => l.id).join(',');
            if (prevIds === sortedIds) return prev; // already sorted
            // try to preserve current selection by id
            const currentId = prev[currentLevelIndex]?.id;
            const newIndex = sorted.findIndex(l => l.id === currentId);
            setCurrentLevelIndex(newIndex === -1 ? 0 : newIndex);
            return sorted;
        });
    }, [levels]);

    React.useEffect(() => {
        try {
            localStorage.setItem(LS_SCHEMES_KEY, JSON.stringify(schemes));
        } catch (err) {
            console.warn('Failed to save schemes to localStorage', err);
        }
    }, [schemes]);

    function saveScheme() {
        const name = schemeName && schemeName.trim() ? schemeName.trim() : `Scheme ${schemes.length + 1}`;
        if (editingSchemeId) {
            // update existing scheme
            setSchemes(prev => prev.map(s => s.id === editingSchemeId ? {
                ...s,
                name,
                points: points.map(p => ({ x: p.x, y: p.y })),
                closed: !!closed,
                stallsPreview: stallsPreview.map(sp => ({ ...sp })),
                lotArea,
                lotAreaMeters: unitSystem === 'imperial' ? ft2ToM2(Number(lotArea)) : Number(lotArea),
            } : s));
            setEditingSchemeId(null);
            setSchemeName('');
            return;
        }
        const id = Date.now().toString(36);
        const color = randColor();
        const item = { id, name, points: points.map(p => ({ x: p.x, y: p.y })), closed, stallsPreview: stallsPreview.map(s => ({ ...s })), lotArea, lotAreaMeters: unitSystem === 'imperial' ? ft2ToM2(Number(lotArea)) : Number(lotArea), color, visible: true };
        setSchemes(prev => [...prev, item]);
        setSchemeName('');
    }

    function deleteScheme(id) {
        setSchemes(prev => prev.filter(s => s.id !== id));
        // if user was editing this scheme, clear the edit state to avoid confusion
        if (editingSchemeId === id) {
            setEditingSchemeId(null);
            setSchemeName('');
        }
    }

    function toggleSchemeVisibility(id) {
        setSchemes(prev => prev.map(s => s.id === id ? { ...s, visible: !s.visible } : s));
    }

    function setActiveScheme(id) {
        setSchemes(prev => prev.map(s => ({ ...s, visible: s.id === id })));
        setHighlightedSchemeId(id);
        window.setTimeout(() => setHighlightedSchemeId(null), 900);
    }

    function applyScheme(id) {
        const s = schemes.find(x => x.id === id);
        if (!s) return;
        // Load boundary geometry
        setPoints(s.points.map(p => ({ x: p.x, y: p.y })));
        setClosed(!!s.closed);
        if (s.lotAreaMeters !== undefined) {
            const displayArea = unitSystem === 'imperial' ? m2ToFt2(Number(s.lotAreaMeters)) : Number(s.lotAreaMeters);
            setLotArea(displayArea);
        } else {
            setLotArea(s.lotArea || lotArea);
        }
        pushHistoryFrom(s.points, s.closed);
        // Promote scheme overlays into the active level features so it becomes the working design
        setLevels(prev => {
            const next = prev.slice();
            const li = currentLevelIndex;
            const level = { ...(next[li] || { id: 'L1', name: 'Level 1', visible: true, elevation: 0 }) };
            // Convert previews into level features
            const feats = [];
            (s.stallsPreview || []).forEach(st => feats.push({ type: 'stall', x: st.x, y: st.y, hw: st.hw, hd: st.hd }));
            (s.aislesPreview || []).forEach(a => feats.push({ type: 'aisle', x: a.x, y: a.y, hw: a.hw, hd: a.hd }));
            // Rebuild street features from unified circulation to avoid using generator's raw streets
            deriveStreetsFromCirculation(s).forEach(st => feats.push({ type: 'street', x: st.x, y: st.y, hw: st.hw, hd: st.hd }));
            (s.accessPreview || []).forEach(ac => feats.push({ type: 'access', x: ac.x, y: ac.y, hw: ac.hw, hd: ac.hd }));
            (s.rampsPreview || []).forEach(rp => feats.push({ type: 'ramp', x: rp.x, y: rp.y, hw: rp.hw, hd: rp.hd }));
            (s.columnsPreview || []).forEach(c => feats.push({ type: 'column', x: c.x, y: c.y }));
            level.stallsPreview = feats;
            next[li] = level;
            return next;
        });
        setStallsPreview([]); // clear transient preview cache; features live in level now
        // clear current selection to avoid accidental edits of a previously selected set
        setSelectedPoints([]);
        // briefly highlight the applied scheme overlay so the user can see which scheme loaded
        setHighlightedSchemeId(s.id);
        window.setTimeout(() => setHighlightedSchemeId(null), 1400);
    }

    // Live Auto Design toggle and debounce helper
    const [autoLive, setAutoLive] = useState(true);
    let autoDesignDebounceTimer = null;
    function autoDesignGenerateDebounced(ms = 300) {
        if (autoDesignDebounceTimer) { window.clearTimeout(autoDesignDebounceTimer); }
        autoDesignDebounceTimer = window.setTimeout(() => {
            autoDesignGenerate();
            autoDesignDebounceTimer = null;
        }, Math.max(50, ms));
    }

    // Auto Design (Stages 1+2): generate top candidate schemes from current boundary
    function autoDesignGenerate() {
        if (!points || points.length < 3 || !closed) {
            alert('Close a boundary polygon first.'); return;
        }
        const stallAngle = (Number(stallAngleDeg) || 0);
        // Parse advanced inputs if provided
        const parseNums = (str) => {
            try {
                if (!str || typeof str !== 'string') return null;
                const arr = str.split(/[,\s]+/).map(s => Number(s)).filter(n => Number.isFinite(n));
                return arr.length ? arr : null;
            } catch { return null; }
        };
        const anglesParsed = parseNums(anglesDegInput);
        const stallAnglesParsed = parseNums(stallAnglesInput);
        const spansParsed = parseNums(spanPresetsInput);

        // Convert UI values to meters for generator which expects metric inputs
        const _stallWidthMeters = unitSystem === 'imperial' ? feetToMeters(Number(stallWidth || 2.6)) : Number(stallWidth || 2.6);
        const _stallDepthMeters = unitSystem === 'imperial' ? feetToMeters(Number(stallDepth || 5.0)) : Number(stallDepth || 5.0);
        const _driveWidthMeters = unitSystem === 'imperial' ? feetToMeters(Number(driveWidthMeters || 6.0)) : Number(driveWidthMeters || 6.0);
        const _connectorSpacingMeters = unitSystem === 'imperial' ? feetToMeters(Number(connectorSpacingMeters || 0)) : Number(connectorSpacingMeters || 0);
        const _columnClearanceMeters = unitSystem === 'imperial' ? feetToMeters(Number(columnClearanceMeters || 0.3)) : Number(columnClearanceMeters || 0.3);
        const _perimeterStreetOffsetMeters = unitSystem === 'imperial' ? feetToMeters(Number(perimeterStreetOffsetMeters || 1.0)) : Number(perimeterStreetOffsetMeters || 1.0);

        // Determine angle/span presets depending on parking type
        const stallAnglesToUse = (codeDesign === 'underground') ? [90] : (stallAnglesParsed || [90, 60]);
        const anglesDegToUse = (codeDesign === 'underground') ? [0] : (anglesParsed || [0, 45, -45]);
        const spanPresetsMetersToUse = (codeDesign === 'underground') ? [7.5] : (spansParsed || undefined);

        const params = {
            unitsPerMeter: Number(unitsPerMeter || 1),
            stallWidth: _stallWidthMeters,
            stallDepth: _stallDepthMeters,
            driveWidth: _driveWidthMeters,
            // Stall angle presets and angle choices depend on parking type
            stallAngles: stallAnglesToUse,
            anglesDeg: anglesDegToUse,
            // Use columnSpacing only if explicitly set; generator will otherwise test presets
            columnSpacing: (columnGridParams && columnGridParams.spacingX) ? (Number(columnGridParams.spacingX) / Math.max(1, Number(unitsPerMeter || 1))) : undefined,
            // Span presets (may be type-specific)
            spanPresetsMeters: spanPresetsMetersToUse,
            columnClearance: _columnClearanceMeters,
            clipAcceptance: Number(clipAcceptance || 0.25),
            keepTop: 1,
            accessPlacement: accessPlacement,
            rampPlacement: rampPlacement,
            aisleType,
            streetType,
            connectorSpacingMeters: _connectorSpacingMeters,
            minConnectorCount: Number(minConnectorCount || 2),
            codeDesign: codeDesign,
            codeSet: parkingCode, // Building code for parking standards
            // Circulation presets
            circulationMode: circulationMode,
            bayOrientation: bayOrientation,
            avoidDeadEnds: !!avoidDeadEnds,
            // Default orthogonal enforcement (may be overridden by parking type)
            enforceOrthogonalLayout: false,
            separateEntryExit: !!separateEntryExit,
            // Perimeter ring street controls
            perimeterStreetEnabled: true,
            // Allow applying perimeter ring generation when surface parking and user enabled perimeter streets
            applyRingToGenerator: !!perimeterStreetEnabled,
            perimeterStreetOffsetMeters: _perimeterStreetOffsetMeters,
            // Ramp and vertical geometry (generator expects meters + slope percents)
            groundEntryHeightMeters: unitSystem === 'imperial' ? feetToMeters(Number(entryHeightMeters || 0)) : Number(entryHeightMeters || 0),
            levelHeightMeters: unitSystem === 'imperial' ? feetToMeters(Number(levelHeightMeters || 0)) : Number(levelHeightMeters || 0),
            accessRampMaxSlopePercent: Number(accessRampMaxSlopePercent || 12),
            internalRampMaxSlopePercent: Number(internalRampMaxSlopePercent || 12),
            aislePercent: Number(aislePercent || 30),
            // Per-type defaults (may be overridden below)
            enablePerimeterStalls: false,
            // Disable connectors and end-caps for clean structural-only
            enableConnectors: false,
            // DEV: force connector creation for visual debugging (temporary)
            forceConnectors: true,
            enableEndCaps: false,
            // Align modules to dominant boundary edges for orthogonal correctness
            axisStrategy: 'edge-longest',
        };
        // Parking-type specific parameter injection
        if (codeDesign === 'surface') {
            params.enablePerimeterStalls = !!surfacePerimeterStalls;
            params.surfaceLevels = Number(surfaceLevels || 1);
            params.landscapeBufferMeters = unitSystem === 'imperial' ? feetToMeters(Number(landscapeBufferMeters || 1)) : Number(landscapeBufferMeters || 1);
            params.evStallPercent = Number(evStallPercent || 0);
        } else if (codeDesign === 'underground') {
            params.enforceOrthogonalLayout = !!enforceOrthogonalLayout;
            // column spacing (single axis) hint for structural generator
            params.columnSpacing = unitSystem === 'imperial' ? feetToMeters(Number(undergroundColumnSpacingMeters || 7.5)) : Number(undergroundColumnSpacingMeters || 7.5);
            params.structuralLevels = Number(undergroundLevels || 1);
        }
        // Inject obstacles (cores) into params
        try {
            const lvl = (levels && levels[currentLevelIndex]) || null;
            if (lvl && Array.isArray(lvl.stallsPreview)) {
                const cores = lvl.stallsPreview.filter(f => f && f.type === 'core');
                if (cores.length > 0) {
                    params.obstacles = cores.map(c => ({ x: c.x, y: c.y, w: c.hw * 2, h: c.hd * 2, angle: 0 }));
                }
            }
        } catch { }
        try {
            // Choose generator strategy by parking type:
            // - For surface parking prefer baseline heuristics (angled bays, perimeter stalls)
            // - For underground prefer structural-first (columns -> modules -> stalls)
            let res = null;
            if (codeDesign === 'surface') {
                res = generateBaselineSchemes(points, params);
                if (!res || res.length === 0) {
                    // fallback to structural if baseline fails
                    res = generateStructuralSchemes(points, params);
                }
                // Baseline now generates connectors natively in layoutOnce, no merge needed
            } else {
                // structural-first attempt: columns → modules → stalls/aisles
                res = generateStructuralSchemes(points, params);
                if (!res || res.length === 0) {
                    // fallback to baseline heuristic if structural fails
                    res = generateBaselineSchemes(points, params);
                }
            }
            if (!res || res.length === 0) { alert('No viable layouts found. Try adjusting parameters.'); return; }
            // Log generator diagnostic: which generator produced results and top counts
            try {
                const top = (res && res[0]) || null;
                console.info('AutoDesign: generator=', codeDesign === 'surface' ? 'baseline-preferred' : 'structural-preferred', 'results=', (res || []).length, 'topCounts=', top && top.counts ? top.counts : null);
            } catch (e) { }
            const now = Date.now().toString(36);
            const mapped = res.map((r, i) => ({
                id: `auto-${now}-${i}`,
                name: `Auto ${i + 1}`,
                points: r.points.map(p => ({ x: p.x, y: p.y })),
                closed: !!r.closed,
                stallsPreview: (r.stalls || []).map(s => ({ x: s.x, y: s.y, hw: s.hw, hd: s.hd })),
                // Aisles are merged into streets; keep aislesPreview empty to avoid duplicate rendering
                aislesPreview: [],
                // For surface lots, avoid double-render by hiding raw streets layer; use unified circulation only
                streetsPreview: (codeDesign === 'surface' ? [] : (r.streets || []).map(st => ({ x: st.x, y: st.y, hw: st.w / 2, hd: st.h / 2, angle: st.angle || 0, type: st.type || 'street' }))),
                accessPreview: (r.access || []).map(ac => ({ x: ac.x, y: ac.y, hw: ac.w / 2, hd: ac.h / 2, angle: ac.angle || 0, type: 'access' })),
                rampsPreview: (r.ramps || []).map(rp => ({ x: rp.x, y: rp.y, hw: rp.w / 2, hd: rp.h / 2, angle: rp.angle || 0, type: 'ramp' })),
                // Unified circulation layer (merged aisles, streets, access, ramps) deduped for robust connectivity
                circulationPreview: (() => {
                    const merged = [];
                    const push = (it) => { if (!it) return; merged.push(it); };
                    // Aisles are represented within streets as type 'aisle'
                    (r.streets || []).forEach(sv => push({ x: sv.x, y: sv.y, hw: sv.w / 2, hd: sv.h / 2, angle: sv.angle || 0, type: sv.type || 'street' }));
                    (r.access || []).forEach(ac => push({ x: ac.x, y: ac.y, hw: ac.w / 2, hd: ac.h / 2, angle: ac.angle || 0, type: 'access' }));
                    (r.ramps || []).forEach(rp => push({ x: rp.x, y: rp.y, hw: rp.w / 2, hd: rp.h / 2, angle: rp.angle || 0, type: 'ramp' }));
                    // clustering merge: group near-duplicate bands by proximity, angle, and size
                    const clusters = [];
                    const typePriority = { connector: 5, aisle: 4, street: 3, access: 2, ramp: 1 };
                    for (const b of merged) {
                        if (!b) continue;
                        let mergedInto = null;
                        for (const c of clusters) {
                            const dx = (b.x || 0) - (c.x || 0);
                            const dy = (b.y || 0) - (c.y || 0);
                            const dist = Math.hypot(dx, dy);
                            const angDiff = Math.abs(((b.angle || 0) - (c.angle || 0)) % (Math.PI));
                            const angClose = Math.min(Math.abs(angDiff), Math.abs(Math.PI - angDiff));
                            const avgLen = Math.max(1, ((b.hw * 2 || 0) + (c.hw * 2 || 0)) / 2);
                            const centerThresh = Math.max(3, avgLen * 0.5);
                            const sizeRatioW = Math.max(0.01, Math.min((b.hw * 2 || 0) / (c.hw * 2 || 1), (c.hw * 2 || 1) / Math.max(0.01, (b.hw * 2 || 0))));
                            const sizeRatioH = Math.max(0.01, Math.min((b.hd * 2 || 0) / (c.hd * 2 || 1), (c.hd * 2 || 1) / Math.max(0.01, (b.hd * 2 || 0))));
                            const sizeSimilar = sizeRatioW > 0.5 && sizeRatioH > 0.5;
                            if (dist <= centerThresh && angClose < 0.2 && sizeSimilar) { mergedInto = c; break; }
                        }
                        if (mergedInto) {
                            mergedInto.x = (mergedInto.x + b.x) / 2;
                            mergedInto.y = (mergedInto.y + b.y) / 2;
                            mergedInto.hw = Math.max(mergedInto.hw || 0, b.hw || 0);
                            mergedInto.hd = Math.max(mergedInto.hd || 0, b.hd || 0);
                            const te = mergedInto.type || 'street'; const tn = b.type || 'street';
                            if ((typePriority[tn] || 0) > (typePriority[te] || 0)) mergedInto.type = tn;
                        } else {
                            clusters.push(Object.assign({}, b));
                        }
                    }
                    return clusters;
                })(),
                columnsPreview: (codeDesign === 'surface' ? [] : (r.columns || []).map(c => (c.x != null && c.y != null ? { x: c.x, y: c.y } : c))),
                lotArea,
                color: r.color || '#475569',
                visible: i === 0,
                counts: r.counts,
            }));
            setSchemes(mapped);
            try { setValidationWarnings(validateConnectivityWarnings(mapped[0])); } catch { setValidationWarnings([]); }
            // briefly highlight best candidate
            setHighlightedSchemeId(mapped[0].id);
            window.setTimeout(() => setHighlightedSchemeId(null), 1200);
            // Show compact pill by default so it doesn't cover drawing
            setAutoPanelHidden(false);
            setAutoPanelOpen(false);
        } catch (err) {
            console.error('Auto design error', err);
            alert('Auto design failed. See console for details.');
        }
    }

    // Live sync: when autoLive is enabled, changes to key parameters regenerate candidates
    useEffect(() => {
        if (!autoLive) return;
        // Guard: only regenerate when a valid closed boundary exists
        if (!closed || !points || points.length < 3) return;
        // regenerate on parameter changes relevant to generator
        autoDesignGenerateDebounced(250);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [
        unitsPerMeter,
        stallWidth,
        stallDepth,
        driveWidthMeters,
        stallAngleDeg,
        clipAcceptance,
        columnGridParams,
        columnClearanceMeters,
        accessPlacement,
        rampPlacement,
        aisleType,
        streetType,
        connectorSpacingMeters,
        minConnectorCount,
        codeDesign,
        entryHeightMeters,
        levelHeightMeters,
        accessRampMaxSlopePercent,
        internalRampMaxSlopePercent,
        circulationMode,
        bayOrientation,
        avoidDeadEnds,
        separateEntryExit,
        designPriority,
        perimeterStreetEnabled,
        perimeterStreetOffsetMeters,
        // new parking-type specific dependencies
        surfaceLevels,
        surfacePerimeterStalls,
        landscapeBufferMeters,
        evStallPercent,
        undergroundLevels,
        undergroundColumnSpacingMeters,
        enforceOrthogonalLayout,
        points,
        closed
    ]);

    // Dev: trigger regeneration when modules hot-reload (generator changes)
    useEffect(() => {
        if (import.meta && import.meta.hot) {
            const dispose = import.meta.hot.accept(() => {
                // On HMR update, re-run generation immediately if live mode is on
                if (autoLive && closed && points && points.length >= 3) {
                    autoDesignGenerateDebounced(0);
                }
            });
            return () => { try { dispose && dispose(); } catch { } };
        }
    }, [autoLive, closed, points]);

    // Preset auto-tuning: set typical widths/spans and min connectors from boundary size
    useEffect(() => {
        if (!points || points.length < 3 || !closed) return;
        // compute principal axis extents in user units
        const axisAngle = Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
        const t = { x: Math.cos(axisAngle), y: Math.sin(axisAngle) };
        const n = { x: -t.y, y: t.x };
        const extT = AutoGeom.projectionsExtent(points, t);
        const lotWidthUnits = Math.abs(extT.max - extT.min);
        const lotWidthMeters = lotWidthUnits / Math.max(1, Number(unitsPerMeter || 1));
        // presets
        if (codeDesign === 'underground') {
            // typical underground: drive 6.0-6.5m, stalls 2.6x5.0, columns ~7.5m spans
            setDriveWidthMeters(prev => (prev == null ? 6.0 : prev));
            setStallWidth(prev => (Number(prev) || 0) <= 0 ? 2.6 : prev);
            setStallDepth(prev => (Number(prev) || 0) <= 0 ? 5.0 : prev);
        } else if (codeDesign === 'surface') {
            // surface: drive ~6.0m, stalls 2.7x5.5 often used
            setDriveWidthMeters(prev => (prev == null ? 6.0 : prev));
            setStallWidth(prev => (Number(prev) || 0) <= 0 ? 2.7 : prev);
            setStallDepth(prev => (Number(prev) || 0) <= 0 ? 5.5 : prev);
        }
        // auto min connectors: roughly one connector per 12m of width, min 2
        const autoMinConn = Math.max(2, Math.floor(lotWidthMeters / 12));
        setMinConnectorCount(prev => (Number(prev) || 0) <= 0 ? autoMinConn : prev);
        if (autoLive) autoDesignGenerateDebounced(200);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [codeDesign, points, closed]);

    function rectsOverlap(ax, ay, ahw, ahd, bx, by, bhw, bhd) {
        const ax0 = ax - ahw, ax1 = ax + ahw, ay0 = ay - ahd, ay1 = ay + ahd;
        const bx0 = bx - bhw, bx1 = bx + bhw, by0 = by - bhd, by1 = by + bhd;
        return ax0 <= bx1 && ax1 >= bx0 && ay0 <= by1 && ay1 >= by0;
    }
    // Derive street-like bands from the unified circulation preview by filtering and clustering
    function deriveStreetsFromCirculation(scheme) {
        if (!scheme) return [];
        const upmLocal = Number(unitsPerMeter) || 1;
        const raw = (scheme.circulationPreview || []).filter(b => b && (b.type === 'street' || b.type === 'aisle' || b.type === 'connector'));
        const clusters = [];
        for (const b of raw) {
            let found = null;
            for (const c of clusters) {
                const dx = (b.x || 0) - (c.x || 0);
                const dy = (b.y || 0) - (c.y || 0);
                const dist = Math.hypot(dx, dy);
                const angDiff = Math.abs(((b.angle || 0) - (c.angle || 0)) % Math.PI);
                const angClose = Math.min(Math.abs(angDiff), Math.abs(Math.PI - angDiff));
                const avgLen = Math.max(1, ((b.hw * 2 || 0) + (c.hw * 2 || 0)) / 2);
                const centerThresh = Math.max(2 * upmLocal, avgLen * 0.5);
                if (dist <= centerThresh && angClose < 0.35) { found = c; break; }
            }
            if (found) {
                // merge into cluster (simple average + max sizes)
                found.x = (found.x + b.x) / 2;
                found.y = (found.y + b.y) / 2;
                found.hw = Math.max(found.hw, b.hw || 0);
                found.hd = Math.max(found.hd, b.hd || 0);
                // keep angle closer to cluster (weighted)
                found.angle = ((found.angle || 0) + (b.angle || 0)) / 2;
                if (!found.type && b.type) found.type = b.type;
            } else {
                clusters.push({ x: b.x, y: b.y, hw: b.hw || 1, hd: b.hd || 1, angle: b.angle || 0, type: b.type || 'street' });
            }
        }
        return clusters;
    }
    function validateConnectivityWarnings(scheme) {
        if (!scheme) return [];
        const aisles = (scheme.aislesPreview || []);
        const streets = deriveStreetsFromCirculation(scheme);
        const access = (scheme.accessPreview || []);
        const nodes = [];
        aisles.forEach((a, i) => nodes.push({ id: 'A' + i, x: a.x, y: a.y, hw: a.hw, hd: a.hd, type: 'aisle' }));
        streets.forEach((st, i) => nodes.push({ id: 'S' + i, x: st.x, y: st.y, hw: st.hw, hd: st.hd, type: st.type || 'street' }));
        access.forEach((ac, i) => nodes.push({ id: 'X' + i, x: ac.x, y: ac.y, hw: ac.hw, hd: ac.hd, type: 'access' }));
        const edges = new Map(); nodes.forEach(n => edges.set(n.id, new Set()));
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = nodes[i], b = nodes[j];
                const eligible = (a.type !== 'aisle' || b.type !== 'aisle');
                if (!eligible) continue;
                if (rectsOverlap(a.x, a.y, a.hw, a.hd, b.x, b.y, b.hw, b.hd)) {
                    edges.get(a.id).add(b.id);
                    edges.get(b.id).add(a.id);
                }
            }
        }
        const startIds = nodes.filter(n => n.type === 'access').map(n => n.id);
        const visited = new Set(startIds);
        const q = [...startIds];
        while (q.length) {
            const cur = q.shift();
            for (const nxt of (edges.get(cur) || [])) if (!visited.has(nxt)) { visited.add(nxt); q.push(nxt); }
        }
        const disconnectedAisles = nodes.filter(n => n.type === 'aisle' && !visited.has(n.id));
        const warns = [];
        if (disconnectedAisles.length > 0) warns.push(`${disconnectedAisles.length} aisle band(s) are not connected to access.`);
        return warns;
    }

    function editScheme(id) {
        const s = schemes.find(x => x.id === id);
        if (!s) return;
        // load scheme into editor for editing and mark editing id
        setPoints(s.points.map(p => ({ x: p.x, y: p.y })));
        setClosed(!!s.closed);
        setStallsPreview(s.stallsPreview.map(x => ({ ...x })));
        setLotArea(s.lotArea || lotArea);
        setSchemeName(s.name || '');
        setEditingSchemeId(s.id);
        pushHistoryFrom(s.points, s.closed);
    }

    // track mouse for preview guideline
    function handleSvgMouseMove(e) {
        if (!svgRef.current) return;
        const svg = svgRef.current;
        const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
        const cursor = pt.matrixTransform(svg.getScreenCTM().inverse());
        const snapped = (measureActive && snapMeasure) ? getMeasureSnappedPoint(cursor, e) : getSnappedPoint(cursor, e);
        // update cursor (in measure mode or one-shot allow free cursor when snapMeasure is off)
        if (measureActive && !snapMeasure) {
            setCursorPoint(cursor);
        } else {
            setCursorPoint(snapped);
        }

        // if marquee selection is active (started in select mode), update marquee rect
        // start marquee if pending start exists and mouse moved beyond threshold
        if (pendingMarqueeStart && (Math.hypot(e.clientX - pendingMarqueeStart.clientX, e.clientY - pendingMarqueeStart.clientY) > 6)) {
            setMarqueeStart({ x: pendingMarqueeStart.x, y: pendingMarqueeStart.y });
            setMarqueeRect({ x: pendingMarqueeStart.x, y: pendingMarqueeStart.y, w: 0, h: 0 });
            setPendingMarqueeStart(null);
        }

        if (marqueeStart) {
            const x1 = marqueeStart.x; const y1 = marqueeStart.y;
            const x2 = snapped.x; const y2 = snapped.y;
            const rx = Math.min(x1, x2); const ry = Math.min(y1, y2);
            const rw = Math.abs(x2 - x1); const rh = Math.abs(y2 - y1);
            setMarqueeRect({ x: rx, y: ry, w: rw, h: rh });
        }

        // insertion rectangle preview for manual insertion modes
        if (insertionStart) {
            const x1 = insertionStart.x; const y1 = insertionStart.y;
            const x2 = snapped.x; const y2 = snapped.y;
            const rx = Math.min(x1, x2); const ry = Math.min(y1, y2);
            const rw = Math.abs(x2 - x1); const rh = Math.abs(y2 - y1);
            setInsertionRect({ x: rx, y: ry, w: rw, h: rh });
        }

        // if group dragging, move selected points together
        if (groupDragging && groupDragOrigin && selectedPoints && selectedPoints.length > 0) {
            const dx = snapped.x - groupDragOrigin.x;
            const dy = snapped.y - groupDragOrigin.y;
            setPoints(prev => {
                const next = prev.slice();
                selectedPoints.forEach((idx, i) => {
                    const orig = groupOriginalPoints[i];
                    if (!orig) return;
                    next[idx] = { x: orig.x + dx, y: orig.y + dy };
                });
                return next;
            });
        }

        // hover insert indicator: show a + when near a segment to hint insertion
        if (points && points.length >= 2) {
            // For insert preview, use grid-only snap so '+' stays under the mouse when grid snapping is enabled.
            const insertBase = snapToGrid
                ? { x: Math.round(cursor.x / gridSize) * gridSize, y: Math.round(cursor.y / gridSize) * gridSize }
                : { x: cursor.x, y: cursor.y };
            let nearest = { i: -1, p: null, d: Infinity };
            for (let i = 0; i < points.length - 1; i++) {
                const a = points[i], b = points[i + 1];
                const p = projectPointToSegment(insertBase, a, b);
                const d = Math.hypot(insertBase.x - p.x, insertBase.y - p.y);
                if (d < nearest.d) nearest = { i, p, d };
            }
            if (points.length >= 3) {
                const a = points[points.length - 1], b = points[0];
                const p = projectPointToSegment(insertBase, a, b);
                const d = Math.hypot(insertBase.x - p.x, insertBase.y - p.y);
                if (d < nearest.d) nearest = { i: points.length - 1, p, d };
            }
            const thresh = snapThreshold || 12;
            if (nearest.d <= Math.max(6, thresh)) {
                setHoverInsert({ i: nearest.i, p: nearest.p });
            } else {
                setHoverInsert(null);
            }
        } else {
            setHoverInsert(null);
        }
    }

    // live length tooltip while drawing (like Revit): returns {d, m, mid} or null
    function getLiveLength() {
        if (mode !== 'draw' || closed || !cursorPoint || points.length === 0) return null;
        const last = points[points.length - 1];
        const dx = cursorPoint.x - last.x; const dy = cursorPoint.y - last.y;
        const d = Math.hypot(dx, dy);
        const m = d / Math.max(1, unitsPerMeter);
        const mid = { x: last.x + dx * 0.5, y: last.y + dy * 0.5 };
        return { d, m, mid };
    }

    // compute guidance markers (end, mid, center, parallel, perpendicular) for drawing assistance
    function getGuides() {
        if (mode !== 'draw' || closed || !cursorPoint || points.length === 0) return null;
        const last = points[points.length - 1];
        const guideThresholdUser = snapThreshold; // in user units
        let nearestVertex = null; let nearestVertexDist = Infinity;
        for (let i = 0; i < points.length; i++) {
            const v = points[i]; const d = Math.hypot(cursorPoint.x - v.x, cursorPoint.y - v.y);
            if (d < nearestVertexDist) { nearestVertex = { p: v, idx: i }; nearestVertexDist = d; }
        }
        let nearestSeg = null; let nearestSegDist = Infinity; let proj = null;
        for (let i = 0; i < points.length - 1; i++) {
            const a = points[i], b = points[i + 1];
            const p = projectPointToSegment(cursorPoint, a, b);
            const d = Math.hypot(cursorPoint.x - p.x, cursorPoint.y - p.y);
            if (d < nearestSegDist) { nearestSegDist = d; nearestSeg = { a, b, i }; proj = p; }
        }
        if (points.length >= 3) {
            const a = points[points.length - 1], b = points[0];
            const p = projectPointToSegment(cursorPoint, a, b);
            const d = Math.hypot(cursorPoint.x - p.x, cursorPoint.y - p.y);
            if (d < nearestSegDist) { nearestSegDist = d; nearestSeg = { a, b, i: points.length - 1 }; proj = p; }
        }

        const guides = {};
        if (nearestVertexDist <= Math.max(6, guideThresholdUser)) {
            guides.endpoint = nearestVertex.p;
        }
        if (nearestSeg && nearestSegDist <= Math.max(6, guideThresholdUser)) {
            // midpoint of segment
            guides.midpoint = { x: (nearestSeg.a.x + nearestSeg.b.x) / 2, y: (nearestSeg.a.y + nearestSeg.b.y) / 2 };
            guides.proj = proj;
        }

        // simple polygon centroid as "center" candidate when polygon exists
        if (points.length >= 3) {
            const area2 = (() => {
                let s = 0; for (let i = 0; i < points.length; i++) { const a = points[i]; const b = points[(i + 1) % points.length]; s += a.x * b.y - b.x * a.y; } return s;
            })();
            if (Math.abs(area2) > 1e-6) {
                let cx = 0, cy = 0;
                for (let i = 0; i < points.length; i++) {
                    const a = points[i]; const b = points[(i + 1) % points.length];
                    const f = (a.x * b.y - b.x * a.y);
                    cx += (a.x + b.x) * f; cy += (a.y + b.y) * f;
                }
                const f = area2; cx = cx / (3 * f); cy = cy / (3 * f);
                guides.center = { x: cx, y: cy };
            }
        }

        // parallel / perpendicular hint to nearest segment from the last point
        if (nearestSeg && last) {
            const segVx = nearestSeg.b.x - nearestSeg.a.x; const segVy = nearestSeg.b.y - nearestSeg.a.y;
            const vdx = cursorPoint.x - last.x; const vdy = cursorPoint.y - last.y;
            const segLen = Math.hypot(segVx, segVy); const vLen = Math.hypot(vdx, vdy);
            if (segLen > 0.0001 && vLen > 0.0001) {
                const segNorm = { x: segVx / segLen, y: segVy / segLen };
                const dot = (vdx * segNorm.x + vdy * segNorm.y) / vLen; // cos theta
                const angleDeg = Math.acos(Math.max(-1, Math.min(1, dot))) * 180 / Math.PI;
                if (Math.abs(angleDeg) < 8) {
                    // parallel
                    // project vector onto segNorm
                    const projLen = vdx * segNorm.x + vdy * segNorm.y;
                    const target = { x: last.x + segNorm.x * projLen, y: last.y + segNorm.y * projLen };
                    guides.parallel = { target, seg: nearestSeg, angle: angleDeg };
                } else if (Math.abs(Math.abs(angleDeg) - 90) < 8) {
                    // perpendicular
                    // projection of last->cursor onto perpendicular of seg: compute perp normal
                    const perp = { x: -segNorm.y, y: segNorm.x };
                    const projLen = vdx * perp.x + vdy * perp.y;
                    const target = { x: last.x + perp.x * projLen, y: last.y + perp.y * projLen };
                    guides.perpendicular = { target, seg: nearestSeg, angle: angleDeg };
                }
            }
        }

        return guides;
    }

    // keyboard shortcuts
    React.useEffect(() => {
        const onKey = (e) => {
            const tgt = e.target || {};
            const tag = (tgt.tagName || '').toUpperCase();
            const isTypingField = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tgt.isContentEditable);
            // If focus is in a form field, avoid handling editing keys like Backspace/Enter/Escape here
            if (isTypingField) {
                if (e.key === 'Backspace' || e.key === 'Enter' || e.key === 'Escape') return; // let the field handle them
                // allow clipboard/undo shortcuts to continue below
            }
            if (e.key === 'Enter') {
                if (!closed && points.length >= 3) closePolygon();
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                // Ctrl+Z undo
                e.preventDefault(); undo();
            } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
                // Ctrl+Y or Ctrl+Shift+Z redo
                e.preventDefault(); redo();
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
                // copy selection
                e.preventDefault(); copySelection();
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
                // paste
                e.preventDefault(); pasteClipboard();
            } else if (e.key === 'Backspace') {
                undoLastPoint();
            } else if (e.key === 'Escape') {
                // Non-destructive cancel: stop current operations instead of clearing drawing
                let handled = false;
                if (insertionMode || insertionStart || insertionRect) {
                    setInsertionMode(null); setInsertionStart(null); setInsertionRect(null); handled = true; suppressNextClickRef.current = true;
                }
                if (marqueeRect || marqueeStart || pendingMarqueeStart) {
                    setMarqueeRect(null); setMarqueeStart(null); setPendingMarqueeStart(null); handled = true; suppressNextClickRef.current = true;
                }
                if (draggingIndex !== null || groupDragging) {
                    setDraggingIndex(null); setGroupDragging(false); setGroupDragOrigin(null); setGroupOriginalPoints([]); handled = true; suppressNextClickRef.current = true;
                }
                if (measureActive && (measurePoints?.length || 0) > 0) {
                    setMeasurePoints([]); setOneShotMeasureActive(false); setOneShotMeasureTempAnn(null); handled = true;
                }
                if (!handled) {
                    if (selectedPoints && selectedPoints.length > 0) { setSelectedPoints([]); }
                    else { setMode('select'); }
                }
            } else if (e.key.toLowerCase() === 'd') {
                setMode('draw');
            } else if (e.key.toLowerCase() === 'm') {
                setMode('measure');
            } else if (e.key.toLowerCase() === 's') {
                setMode('select');
            } else if (e.key.toLowerCase() === 'p') {
                setMode('pan');
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [points, closed, gridSize, snapToGrid]);

    async function handleFileUpload(e) {
        const files = Array.from(e.target.files || []);
        if (!files.length) return;
        const added = [];
        for (const f of files) {
            const name = f.name;
            const reader = new FileReader();
            const text = await new Promise((res, rej) => { reader.onerror = rej; reader.onload = () => res(reader.result); reader.readAsText(f); });
            const lower = name.toLowerCase();
            let meta = { name };
            if (lower.endsWith('.obj')) {
                const verts = parseOBJ(text);
                if (verts.length >= 3) {
                    const hull = convexHull(verts);
                    const a = areaFromPolygonCoords(hull);
                    meta.preview = `OBJ vertices: ${verts.length}, convex-hull area ≈ ${Math.round(a)} (units²)`;
                    // set drawing to hull for quick editing
                    const hullPoints = hull.map(p => ({ x: p[0], y: p[1] }));
                    setPoints(hullPoints);
                    setClosed(true);
                    setLotArea(unitSystem === 'imperial' ? Math.max(1, Math.round(m2ToFt2(a))) : Math.max(1, Math.round(a)));
                } else {
                    meta.preview = `OBJ parsed, vertices: ${verts.length}`;
                }
            } else if (lower.endsWith('.svg')) {
                meta.preview = 'SVG uploaded — you can import points by copying an exported GeoJSON or redraw on the canvas.';
            } else if (lower.endsWith('.json') || lower.endsWith('.geojson')) {
                try {
                    const json = JSON.parse(text);
                    if (json?.features?.length) {
                        const feat = json.features[0];
                        if (feat.geometry?.type === 'Polygon') {
                            const coords = feat.geometry.coordinates[0];
                            const pts = coords.map(c => ({ x: c[0], y: c[1] }));
                            setPoints(pts);
                            setClosed(true);
                            const a = areaFromPolygonCoords(coords);
                            setLotArea(unitSystem === 'imperial' ? Math.max(1, Math.round(m2ToFt2(a))) : Math.max(1, Math.round(a)));
                            meta.preview = `GeoJSON polygon loaded — ${coords.length} coords, area ≈ ${Math.round(a)}`;
                        }
                    }
                } catch (e) {
                    meta.preview = 'JSON uploaded but failed to parse';
                }
            } else if (lower.endsWith('.gltf') || lower.endsWith('.glb')) {
                meta.preview = 'GLTF/GLB uploaded — complex model; consider exporting an OBJ or 2D footprint for reliable area estimates.';
            } else {
                meta.preview = 'File uploaded — preview not available';
            }
            added.push(meta);
        }
        setUploadedFiles(prev => [...prev, ...added]);
        // reset input value so same file can be uploaded again
        e.target.value = '';
    }

    // lightweight toolbar actions
    function clearPoints() {
        setPoints([]);
        setClosed(false);
        setMeasureAnnotations([]);
        setSelectedPoints([]);
        setHistory([]);
        setHistoryIndex(-1);
    }
    function fitViewToBoundary() {
        if (!points || points.length === 0) return;
        const xs = points.map(p => p.x), ys = points.map(p => p.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        const pad = 40;
        setViewBox({ x: minX - pad, y: minY - pad, w: (maxX - minX) + pad * 2, h: (maxY - minY) + pad * 2 });
    }
    const [showAdvanced, setShowAdvanced] = useState(false);

    return (
        <div className="w-full px-4 sm:px-6 lg:px-8">
            <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-extrabold">ParkCore — Parking estimator</h1>
                    <p className="text-slate-600 mt-1">Quickly estimate parking capacity from lot area and typical stall dimensions.</p>
                </div>
                <div className="flex items-center gap-2">
                    <label className="text-sm text-slate-700">Units</label>
                    <select value={unitSystem} onChange={e => {
                        const next = e.target.value;
                        // convert existing numeric values so they represent the same real-world size
                        if (next !== unitSystem) {
                            if (next === 'imperial') {
                                setLotArea(prev => Math.round(m2ToFt2(Number(prev)) * 100) / 100);
                                setStallWidth(prev => Math.round(metersToFeet(Number(prev)) * 100) / 100);
                                setStallDepth(prev => Math.round(metersToFeet(Number(prev)) * 100) / 100);
                            } else {
                                setLotArea(prev => Math.round(ft2ToM2(Number(prev)) * 100) / 100);
                                setStallWidth(prev => Math.round(feetToMeters(Number(prev)) * 100) / 100);
                                setStallDepth(prev => Math.round(feetToMeters(Number(prev)) * 100) / 100);
                            }
                        }
                        setUnitSystem(next);
                    }} className="rounded border px-2 py-1 text-sm">
                        <option value="metric">Metric (m, m²)</option>
                        <option value="imperial">Imperial (ft, ft²)</option>
                    </select>
                </div>
            </div>
            {/* Use full-page responsive grid for basic inputs */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                <label className="block lg:col-span-1">
                    <div className="text-sm text-slate-700">Lot area ({unitSystem === 'metric' ? 'm²' : 'ft²'})</div>
                    <input type="number" value={lotArea} onChange={e => setLotArea(e.target.value)} className="mt-1 w-full rounded-md border px-3 py-2" />
                </label>

                <label className="block lg:col-span-1">
                    <div className="text-sm text-slate-700">Aisle / circulation (%)</div>
                    <input type="number" value={aislePercent} onChange={e => setAislePercent(e.target.value)} className="mt-1 w-full rounded-md border px-3 py-2" />
                </label>

                <label className="block lg:col-span-1">
                    <div className="text-sm text-slate-700">Stall width ({unitSystem === 'metric' ? 'm' : 'ft'})</div>
                    <input type="number" value={stallWidth} onChange={e => setStallWidth(e.target.value)} className="mt-1 w-full rounded-md border px-3 py-2" />
                </label>

                <label className="block lg:col-span-1">
                    <div className="text-sm text-slate-700">Stall depth ({unitSystem === 'metric' ? 'm' : 'ft'})</div>
                    <input type="number" value={stallDepth} onChange={e => setStallDepth(e.target.value)} className="mt-1 w-full rounded-md border px-3 py-2" />
                </label>
            </div>

            {/* Code selection and derived requirements */}
            <div className="mt-6 bg-white p-4 rounded-md border">
                <div className="flex items-center justify-between">
                    <div style={{ minWidth: 280 }}>
                        <div className="text-sm text-slate-700">Design codes / country</div>
                        <input
                            aria-label="Search codes"
                            placeholder="Search country or code (e.g. KSA, Egypt)"
                            value={codeFilter}
                            onChange={e => setCodeFilter(e.target.value)}
                            className="mt-1 w-full rounded border px-3 py-2 text-sm"
                        />
                        <select value={selectedCode || ''} onChange={e => setSelectedCode(e.target.value)} className="mt-2 rounded border px-3 py-2 w-full text-sm">
                            {filteredCodeKeys.map(k => <option key={k} value={k}>{parkingCodes[k].name}</option>)}
                        </select>
                    </div>
                    <div className="text-sm text-slate-500">Reference: {currentCode?.references?.join(', ')}</div>
                </div>

                {currentCode && (
                    <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div className="p-3 rounded border bg-slate-50">
                            <div className="text-xs text-slate-600">Accessible stalls required</div>
                            <div className="text-xl font-semibold">{requiredAccessibleStalls(est)}</div>
                            <div className="text-xs text-slate-500">{currentCode.accessiblePercent}% of stalls</div>
                        </div>
                        <div className="p-3 rounded border bg-slate-50">
                            <div className="text-xs text-slate-600">Fire extinguishers required</div>
                            <div className="text-xl font-semibold">{requiredExtinguishers(est)}</div>
                            <div className="text-xs text-slate-500">1 per {currentCode.extinguisherRatio} stalls (approx)</div>
                        </div>
                        <div className="p-3 rounded border bg-slate-50">
                            <div className="text-xs text-slate-600">Suggested EV provision</div>
                            <div className="text-xl font-semibold">{Math.ceil(est * (currentCode.evPercentage / 100) || 0)}</div>
                            <div className="text-xs text-slate-500">{currentCode.evPercentage}% recommended</div>
                        </div>
                    </div>
                )}

                {currentCode && (
                    <div className="mt-4 text-sm text-slate-700">
                        <div><strong>Sprinkler</strong>: {currentCode.sprinklerRequired}</div>
                        <div><strong>Mechanical ventilation</strong>: {currentCode.mechanicalVentilation}</div>
                        <div><strong>Electrical notes</strong>: {currentCode.electricalNotes}</div>
                        <div className="mt-2 text-xs text-slate-500">Notes: these are high-level guidance snippets. Consult the listed references and local authority having jurisdiction for enforceable requirements.</div>
                    </div>
                )}
            </div>

            {/* Full-width responsive metrics */}
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-white p-4 rounded-md border">
                    <div className="text-sm text-slate-500">Usable area ({unitSystem === 'metric' ? 'm²' : 'ft²'})</div>
                    <div className="text-2xl font-semibold">{(unitSystem === 'metric' ? usable : m2ToFt2(usable)).toFixed(0)}</div>
                </div>
                <div className="bg-white p-4 rounded-md border">
                    <div className="text-sm text-slate-500">Estimated stalls</div>
                    <div className="text-2xl font-semibold">{est}</div>
                </div>
                <div className="bg-white p-4 rounded-md border">
                    <div className="text-sm text-slate-500">Stalls / 1000 {unitSystem === 'metric' ? 'm²' : 'ft²'}</div>
                    <div className="text-2xl font-semibold">{(unitSystem === 'metric' ? (density * 1000) : (est * 1000 / Math.max(1, m2ToFt2(A)))).toFixed(1)}</div>
                </div>
            </div>

            {/* File upload + drawing editor */}
            <div className="mt-6 bg-white p-4 rounded-md border">
                <div className="flex items-center justify-between">
                    <div>
                        <div className="text-sm text-slate-700">Upload model or footprint (OBJ, GLTF, SVG, GeoJSON)</div>
                        <input type="file" accept=".obj,.gltf,.glb,.svg,.json,.geojson" multiple onChange={handleFileUpload} className="mt-2" />
                    </div>
                    <div className="text-sm text-slate-500">Uploaded: {uploadedFiles.length}</div>
                </div>

                {uploadedFiles.length > 0 && (
                    <ul className="mt-3 list-disc pl-5 text-sm text-slate-600">
                        {uploadedFiles.map((f, i) => (
                            <li key={i}><strong>{f.name}</strong> — {f.preview || 'uploaded'}</li>
                        ))}
                    </ul>
                )}

                <div className="mt-4">
                    <div className="flex items-center justify-between">
                        <div className="text-sm text-slate-700 mb-2">Drawing editor (click to add points)</div>
                        {/* Compact primary toolbar */}
                        <div className="flex items-center gap-2">
                            <button className="px-2 py-1 text-xs rounded bg-slate-500 text-white" onClick={fitViewToBoundary} title="Fit view to boundary">Fit view</button>
                            <button className="ml-3 px-2 py-1 text-xs rounded bg-sky-600 text-white hover:bg-sky-700" onClick={autoDesignGenerate} title="Run Auto Design">Generate</button>
                            <button className="ml-1 px-2 py-1 text-xs rounded border border-slate-200 bg-white text-slate-700 hover:bg-slate-50" onClick={() => setShowAdvanced(v => !v)} title="Toggle advanced">Advanced {showAdvanced ? '▾' : '▸'}</button>
                        </div>
                    </div>
                    {/* Advanced drawer: muted by default */}
                    {showAdvanced && (
                        <div className="mt-2 p-2 rounded border bg-slate-50">
                            <div className="flex flex-wrap items-center gap-3">
                                <label className="text-xs">Units per meter <input type="number" value={unitsPerMeter} onChange={e => setUnitsPerMeter(Number(e.target.value) || 1)} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                                <label className="text-xs">Fixed handles <input type="checkbox" checked={fixedScreenHandles} onChange={e => setFixedScreenHandles(e.target.checked)} className="ml-1" /></label>
                                <label className="text-xs">World handle size <input type="number" value={worldHandleRadius} onChange={e => setWorldHandleRadius(Number(e.target.value) || 1)} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                                <label className="text-xs">Live Auto <input type="checkbox" checked={autoLive} onChange={e => setAutoLive(e.target.checked)} className="ml-1" /></label>
                                {/* Preset removed from here; Parking Type selector is shown under Circulation for clearer placement */}
                            </div>
                        </div>
                    )}
                    {/* Auto design overlay toggles */}
                    {schemes && schemes.length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-700">
                            <span className="text-slate-600">Overlay:</span>
                            <label>Grid <input type="checkbox" checked={showGridOverlay} onChange={e => setShowGridOverlay(e.target.checked)} className="ml-1" /></label>
                            {/* Aisles removed: merged under Streets overlay */}
                            <label>Streets <input type="checkbox" checked={showStreetsOverlay} onChange={e => setShowStreetsOverlay(e.target.checked)} className="ml-1" /></label>
                            <label>Stalls <input type="checkbox" checked={showStallsOverlay} onChange={e => setShowStallsOverlay(e.target.checked)} className="ml-1" /></label>
                            <label className="ml-2">Min connectors <input type="number" min={0} max={10} value={minConnectorCount} onChange={e => setMinConnectorCount(Math.max(0, Number(e.target.value) || 0))} className="ml-1 w-16 rounded border px-1 py-0.5" /></label>
                            {/* Highlight connectors removed per request */}
                            {validationWarnings && validationWarnings.length > 0 && (
                                <span className="ml-3 text-red-600">{validationWarnings[0]}</span>
                            )}
                            <label>Access <input type="checkbox" checked={showAccessOverlay} onChange={e => setShowAccessOverlay(e.target.checked)} className="ml-1" /></label>
                            <label>Ramps <input type="checkbox" checked={showRampsOverlay} onChange={e => setShowRampsOverlay(e.target.checked)} className="ml-1" /></label>
                            <label>Columns <input type="checkbox" checked={showColumnsOverlay} onChange={e => setShowColumnsOverlay(e.target.checked)} className="ml-1" /></label>
                        </div>
                    )}
                    <div className="border rounded-md overflow-hidden" style={{ position: 'relative' }}>
                        {viewMode === 'top' ? (
                            <svg
                                ref={svgRef}
                                onClick={handleSvgClick}
                                onDoubleClick={handleSvgDoubleClick}
                                onMouseMove={handleSvgMouseMove}
                                onMouseDown={(e) => {
                                    // start pending marquee on background click for Draw or Select modes
                                    if (!svgRef.current) return;
                                    const pt = svgRef.current.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
                                    const cursor = pt.matrixTransform(svgRef.current.getScreenCTM().inverse());
                                    // if an insertion tool is active, start insertion drag instead
                                    if (insertionMode) {
                                        setInsertionStart({ x: cursor.x, y: cursor.y });
                                        setInsertionRect({ x: cursor.x, y: cursor.y, w: 0, h: 0 });
                                        return;
                                    }
                                    if (mode === 'select') {
                                        setPendingMarqueeStart({ x: cursor.x, y: cursor.y, clientX: e.clientX, clientY: e.clientY });
                                    }
                                }}
                                onMouseUp={(e) => {
                                    // if insertion rectangle exists and an insertion tool is active, finalize insertion
                                    if (insertionRect && insertionMode) {
                                        const r = insertionRect;
                                        // require a small minimum size to avoid accidental clicks
                                        if (Math.abs(r.w) > 4 && Math.abs(r.h) > 4) {
                                            finalizeInsertionRect(r);
                                        }
                                        setInsertionStart(null);
                                        setInsertionRect(null);
                                        setInsertionMode(null);
                                        return;
                                    }

                                    // Auto-close if mouse up near first point and we are in draw mode with >=3 points
                                    if (!closed && mode === 'draw' && points.length >= 3) {
                                        const svg = svgRef.current; if (svg) {
                                            const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
                                            const cursor = pt.matrixTransform(svg.getScreenCTM().inverse());
                                            const first = points[0];
                                            const hit = getHitRadius(14);
                                            const d2 = (first.x - cursor.x) ** 2 + (first.y - cursor.y) ** 2;
                                            if (d2 <= hit * hit) {
                                                setClosed(true);
                                                const areaUnits = computePolygonArea(points);
                                                const areaMeters = areaUnits / (unitsPerMeter * unitsPerMeter);
                                                const displayArea = unitSystem === 'imperial' ? Math.max(1, Math.round(m2ToFt2(areaMeters))) : Math.max(1, Math.round(areaMeters));
                                                setLotArea(displayArea);
                                                pushHistoryFrom(points, true);
                                                return;
                                            }
                                        }
                                    }

                                    // if marqueeRect exists, finalize selection (works in draw or select modes)
                                    if (marqueeRect) {
                                        const r = marqueeRect;
                                        const inside = (p) => p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
                                        setSelectedPoints(points.map((p, i) => inside(p) ? i : -1).filter(i => i >= 0));
                                        setMarqueeStart(null);
                                        setMarqueeRect(null);
                                    }
                                    // clear pending marquee if it never became an actual marquee
                                    if (pendingMarqueeStart) setPendingMarqueeStart(null);
                                    if (groupDragging) {
                                        // finish group drag
                                        setGroupDragging(false);
                                        setGroupDragOrigin(null);
                                        setGroupOriginalPoints([]);
                                        pushHistoryFrom(points, closed);
                                        suppressNextClickRef.current = true;
                                    }
                                }}
                                width="100%" height="480" viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`} style={{ background: '#f8fafc', cursor: ((mode === 'draw') || measureActive) ? 'crosshair' : (hoverInsert ? 'copy' : undefined) }}
                            >
                                {/* grid: render a large, effectively "infinite" grid based on current viewBox extents */}
                                {(() => {
                                    // Compute an expanded extent so grid appears infinite when panning/zooming
                                    const pad = 3; // how many view widths/heights beyond current view to render
                                    const minX = Math.floor((viewBox.x - viewBox.w * pad) / gridSize) * gridSize;
                                    const maxX = Math.ceil((viewBox.x + viewBox.w * (pad + 1)) / gridSize) * gridSize;
                                    const minY = Math.floor((viewBox.y - viewBox.h * pad) / gridSize) * gridSize;
                                    const maxY = Math.ceil((viewBox.y + viewBox.h * (pad + 1)) / gridSize) * gridSize;
                                    const xs = [];
                                    for (let x = minX; x <= maxX; x += gridSize) xs.push(x);
                                    const ys = [];
                                    for (let y = minY; y <= maxY; y += gridSize) ys.push(y);

                                    // When in top view, draw orthographic grid; when in 3d, draw a tilted plane with its own grid
                                    if (viewMode === 'top') {
                                        return (
                                            <g>
                                                {xs.map(x => <line key={'gx' + x} x1={x} y1={minY} x2={x} y2={maxY} stroke="#e6eef6" strokeWidth={getStrokeUserWidth(0.5)} />)}
                                                {ys.map(y => <line key={'gy' + y} x1={minX} y1={y} x2={maxX} y2={y} stroke="#e6eef6" strokeWidth={getStrokeUserWidth(0.5)} />)}
                                                {/* draw CPlane X/Y axes colored (Rhino-like): X=red, Y=green */}
                                                {cplaneVisible && (() => {
                                                    const ox = cplaneOrigin.x, oy = cplaneOrigin.y;
                                                    const axisLen = Math.max(viewBox.w, viewBox.h) * 4;
                                                    const xEnd = { x: ox + cplaneXDir.x * axisLen, y: oy + cplaneXDir.y * axisLen };
                                                    const xStart = { x: ox - cplaneXDir.x * axisLen, y: oy - cplaneXDir.y * axisLen };
                                                    const yDir = { x: -cplaneXDir.y, y: cplaneXDir.x };
                                                    const yEnd = { x: ox + yDir.x * axisLen, y: oy + yDir.y * axisLen };
                                                    const yStart = { x: ox - yDir.x * axisLen, y: oy - yDir.y * axisLen };
                                                    return (
                                                        <g key="cplane-global-axes">
                                                            <line x1={xStart.x} y1={xStart.y} x2={xEnd.x} y2={xEnd.y} stroke="#ef4444" strokeWidth={getStrokeUserWidth(1.2)} />
                                                            <line x1={yStart.x} y1={yStart.y} x2={yEnd.x} y2={yEnd.y} stroke="#10b981" strokeWidth={getStrokeUserWidth(1.2)} />
                                                        </g>
                                                    );
                                                })()}
                                            </g>
                                        );
                                    }

                                    // 3d view: render a tilted plane (parallelogram) centered on cplaneOrigin with gridlines along X/Y directions
                                    if (viewMode === '3d') {
                                        // Render a subtle tilted plane hint with gridlines along u/v (lighter than earlier heavy plane)
                                        const ox = cplaneOrigin.x, oy = cplaneOrigin.y;
                                        const axisLen = Math.max(viewBox.w, viewBox.h) * 1.1;
                                        const u = { x: cplaneXDir.x * axisLen, y: cplaneXDir.y * axisLen };
                                        const v = { x: -cplaneXDir.y * axisLen * 0.5, y: cplaneXDir.x * axisLen * 0.5 }; // foreshortened Y

                                        // corners of parallelogram (for grid extents)
                                        const corners = [
                                            { x: ox - u.x - v.x, y: oy - u.y - v.y },
                                            { x: ox + u.x - v.x, y: oy + u.y - v.y },
                                            { x: ox + u.x + v.x, y: oy + u.y + v.y },
                                            { x: ox - u.x + v.x, y: oy - u.y + v.y },
                                        ];

                                        // gridline counts (keep modest to avoid visual clutter)
                                        const uCount = Math.max(4, Math.floor((axisLen * 2) / (gridSize * 1.5)));
                                        const vCount = Math.max(4, Math.floor((axisLen * 1.0) / (gridSize * 1.5)));
                                        const uStep = { x: (2 * u.x) / uCount, y: (2 * u.y) / uCount };
                                        const vStep = { x: (2 * v.x) / vCount, y: (2 * v.y) / vCount };

                                        const gridLines = [];
                                        for (let i = 0; i <= uCount; i++) {
                                            const s = { x: corners[0].x + uStep.x * i, y: corners[0].y + uStep.y * i };
                                            const e = { x: corners[3].x + uStep.x * i, y: corners[3].y + uStep.y * i };
                                            gridLines.push({ s, e });
                                        }
                                        for (let j = 0; j <= vCount; j++) {
                                            const s = { x: corners[0].x + vStep.x * j, y: corners[0].y + vStep.y * j };
                                            const e = { x: corners[1].x + vStep.x * j, y: corners[1].y + vStep.y * j };
                                            gridLines.push({ s, e });
                                        }

                                        return (
                                            <g>
                                                {/* subtle gridlines */}
                                                {gridLines.map((gline, idx) => (
                                                    <line key={'3g' + idx} x1={gline.s.x} y1={gline.s.y} x2={gline.e.x} y2={gline.e.y} stroke="#e6eef6" strokeWidth={getStrokeUserWidth(0.45)} opacity={0.95} />
                                                ))}
                                                {/* faint outline of plane for context, no fill */}
                                                <polyline points={`${corners.map(c => `${c.x},${c.y}`).join(' ')} ${corners[0].x},${corners[0].y}`} fill="none" stroke="rgba(2,6,23,0.06)" strokeWidth={getStrokeUserWidth(0.6)} />
                                                {/* axes on plane */}
                                                <line x1={ox - u.x * 0.7} y1={oy - u.y * 0.7} x2={ox + u.x * 0.7} y2={oy + u.y * 0.7} stroke="#ef4444" strokeWidth={getStrokeUserWidth(1)} opacity={0.98} markerEnd="url(#cplaneArrowX)" />
                                                <line x1={ox - v.x * 0.7} y1={oy - v.y * 0.7} x2={ox + v.x * 0.7} y2={oy + v.y * 0.7} stroke="#10b981" strokeWidth={getStrokeUserWidth(1)} opacity={0.98} markerEnd="url(#cplaneArrowY)" />
                                                <circle cx={ox} cy={oy} r={getHandleRadius(6)} fill="#0f172a" opacity={0.12} />
                                                <text x={ox + u.x * 0.65} y={oy + u.y * 0.65} fontSize={14} fill="#ef4444">X</text>
                                                <text x={ox + v.x * 0.65} y={oy + v.y * 0.65} fontSize={14} fill="#10b981">Y</text>
                                            </g>
                                        );
                                    }

                                    return null;
                                })()}
                                <defs>
                                    <marker id="dot" markerWidth="4" markerHeight="4" refX="2" refY="2"><circle cx="2" cy="2" r="2" fill="#111" /></marker>
                                    <marker id="cplaneArrowX" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">
                                        <path d="M0,0 L6,3 L0,6 z" fill="#ef4444" />
                                    </marker>
                                    <marker id="cplaneArrowY" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">
                                        <path d="M0,0 L6,3 L0,6 z" fill="#10b981" />
                                    </marker>
                                </defs>
                                {/* render saved schemes as overlays for comparison (respect overlay toggles) */}
                                {schemes.map((s) => s.visible && s.points && s.points.length > 0 && (() => {
                                    const isHighlighted = highlightedSchemeId === s.id;
                                    const strokeW = isHighlighted ? getStrokeUserWidth(2.2) : getStrokeUserWidth(0.9);
                                    // Use a very light neutral fill independent of scheme color to avoid dark interior
                                    const schemeFill = isHighlighted ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)';
                                    const schemeStroke = isHighlighted ? 'rgba(160,160,160,0.85)' : 'rgba(180,180,180,0.55)';
                                    const stallAlpha = isHighlighted ? 0.18 : 0.12;
                                    return (
                                        <g key={'scheme-' + s.id}>
                                            {s.closed && s.points.length >= 3 ? (
                                                <polygon points={s.points.map(p => `${p.x},${p.y}`).join(' ')} fill={schemeFill} stroke={schemeStroke} strokeWidth={strokeW} />
                                            ) : (
                                                <polyline points={s.points.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke={schemeStroke} strokeWidth={strokeW} strokeDasharray="5 4" />
                                            )}
                                            {(s.circulationPreview || []).map((st, si) => {
                                                const type = st.type || 'street';
                                                // Determine whether this item should be visible given user toggles
                                                const visibleByToggle = (type === 'aisle' && showStreetsOverlay)
                                                    || (type === 'street' && showStreetsOverlay)
                                                    || (type === 'connector' && showStreetsOverlay)
                                                    || (type === 'access' && showAccessOverlay)
                                                    || (type === 'ramp' && showRampsOverlay);
                                                if (!visibleByToggle) return null;
                                                const isConnector = type === 'connector';
                                                const style = (type === 'aisle') ? overlayPalette.aisles : (type === 'access') ? overlayPalette.access : (type === 'ramp') ? overlayPalette.ramps : overlayPalette.streets;
                                                const fill = style.fill;
                                                const stroke = style.stroke;
                                                const sw = getStrokeUserWidth(type === 'aisle' ? 0.9 : 1);
                                                const angDeg = (st.angle || 0) * 180 / Math.PI;
                                                const fullLen = st.hw * 2;
                                                const fullHt = st.hd * 2;
                                                const upmLocal = Number(unitsPerMeter) || 1;
                                                const m2u = (m) => m * upmLocal;
                                                const rx = Math.min(st.hd, Math.max(1, m2u(0.5)));
                                                const arrowW = Math.min(m2u(1.6), Math.max(m2u(0.45), fullLen * 0.06));
                                                const arrowH = Math.min(m2u(1.1), Math.max(m2u(0.25), fullHt * 0.35));
                                                const spacing = m2u(12);
                                                const margin = Math.max(arrowW * 1.2, m2u(1.0));
                                                const usable = Math.max(0, fullLen - 2 * margin);
                                                const count = usable > spacing ? Math.max(1, Math.floor(usable / spacing)) : (usable > 0 ? 1 : 0);
                                                const arrowPositions = [];
                                                if (count > 0) {
                                                    const step = usable / (count + 1);
                                                    for (let i = 1; i <= count; i++) {
                                                        const pos = -fullLen / 2 + margin + step * i;
                                                        arrowPositions.push(pos);
                                                    }
                                                }
                                                return (
                                                    <g key={s.id + '-cir-' + si}>
                                                        <rect x={st.x - st.hw} y={st.y - st.hd} width={fullLen} height={fullHt} fill={fill} stroke={stroke} strokeWidth={sw} rx={rx} ry={rx} transform={`rotate(${angDeg}, ${st.x}, ${st.y})`} />
                                                        {arrowPositions.map((pos, k) => (
                                                            <g key={k} transform={`translate(${st.x + Math.cos((st.angle || 0)) * pos},${st.y + Math.sin((st.angle || 0)) * pos}) rotate(${angDeg})`}>
                                                                <polygon points={`0,${-arrowH} ${arrowW},0 0,${arrowH}`} fill={stroke} opacity={isConnector ? 0.6 : 0.9} />
                                                            </g>
                                                        ))}
                                                    </g>
                                                );
                                            })}
                                            {/* Rounded fillet circles at intersections between circulation bands */}
                                            {(() => {
                                                // Tight dedupe: collapse near-duplicate bands to avoid stacked rendering
                                                // Tight dedupe: collapse near-duplicate bands to avoid stacked rendering
                                                const bandsRaw = (s.circulationPreview || []).map(b => ({ ...b }));
                                                const seenKeys = new Set();
                                                const bands = [];
                                                for (const b of bandsRaw) {
                                                    if (!b) continue;
                                                    const k = `${Math.round((b.x || 0) * 100)}_${Math.round((b.y || 0) * 100)}_${Math.round((b.hw || 0) * 100)}_${Math.round((b.hd || 0) * 100)}_${Math.round(((b.angle || 0)) * 100)}`;
                                                    if (seenKeys.has(k)) continue;
                                                    seenKeys.add(k);
                                                    bands.push(b);
                                                }
                                                const out = [];
                                                const eps = 1e-6;
                                                function intersectCenterlines(a, b) {
                                                    const aAng = (a.angle || 0);
                                                    const bAng = (b.angle || 0);
                                                    const u1 = { x: Math.cos(aAng), y: Math.sin(aAng) };
                                                    const u2 = { x: Math.cos(bAng), y: Math.sin(bAng) };
                                                    const dx = (b.x - a.x), dy = (b.y - a.y);
                                                    const det = u1.y * u2.x - u1.x * u2.y;
                                                    if (Math.abs(det) < eps) return null; // parallel or nearly
                                                    const s = (u2.x * dy - u2.y * dx) / det;
                                                    const t = (u1.x * dy - u1.y * dx) / det;
                                                    const half1 = a.hw; const half2 = b.hw;
                                                    if (Math.abs(s) <= half1 + Math.max(1, half1 * 0.1) && Math.abs(t) <= half2 + Math.max(1, half2 * 0.1)) {
                                                        return { x: a.x + u1.x * s, y: a.y + u1.y * s };
                                                    }
                                                    return null;
                                                }
                                                for (let i = 0; i < bands.length; i++) {
                                                    for (let j = i + 1; j < bands.length; j++) {
                                                        const A = bands[i], B = bands[j];
                                                        if (!A || !B) continue;
                                                        const pt = intersectCenterlines(A, B);
                                                        if (!pt) continue;
                                                        // For T-junctions between perpendicular through-streets draw small protective islands
                                                        const upmLocal = Number(unitsPerMeter) || 1;
                                                        const isStreetPair = ((A.type === 'street' || A.type === 'connector' || A.type === 'aisle') && (B.type === 'street' || B.type === 'connector' || B.type === 'aisle'));
                                                        if (isStreetPair && Math.abs(((A.angle || 0) - (B.angle || 0)) % Math.PI - Math.PI / 2) < 0.2) {
                                                            // choose through band as the longer one (compare half-length hw)
                                                            const through = (A.hw || 0) >= (B.hw || 0) ? A : B;
                                                            const thruAng = through.angle || 0;
                                                            const thruDeg = (thruAng) * 180 / Math.PI;
                                                            const thruLen = Math.max(through.hw * 2, upmLocal * 3);
                                                            const thruW = Math.max(through.hd * 2 * 1.1, upmLocal * 1.0);
                                                            const mainLen = Math.min(upmLocal * 6, Math.max(upmLocal * 3, thruLen * 0.22));
                                                            const mainW = Math.max(thruW * 1.1, upmLocal * 1.0);
                                                            const mainX = pt.x - mainLen / 2;
                                                            const mainY = pt.y - mainW / 2;
                                                            const mainKey = `island-${s.id}-${i}-${j}`;
                                                            out.push(
                                                                <g key={mainKey}>
                                                                    <rect x={mainX} y={mainY} width={mainLen} height={mainW} fill={overlayPalette.streets.fill} stroke={overlayPalette.streets.stroke} strokeWidth={getStrokeUserWidth(0.8)} transform={`rotate(${thruDeg}, ${pt.x}, ${pt.y})`} rx={Math.max(2, upmLocal * 0.3)} ry={Math.max(2, upmLocal * 0.3)} />
                                                                    {/* perpendicular splitter bar */}
                                                                    <rect x={pt.x - (mainW * 0.35)} y={pt.y - (mainW * 0.35)} width={Math.max(upmLocal * 1.2, mainW * 0.5)} height={Math.max(upmLocal * 0.6, mainW * 0.35)} fill={overlayPalette.streets.fill} stroke={overlayPalette.streets.stroke} strokeWidth={getStrokeUserWidth(0.8)} transform={`rotate(${thruDeg}, ${pt.x}, ${pt.y}) rotate(90, ${pt.x}, ${pt.y})`} rx={Math.max(1, upmLocal * 0.2)} ry={Math.max(1, upmLocal * 0.2)} />
                                                                </g>
                                                            );
                                                        }
                                                    }
                                                }
                                                return out;
                                            })()}
                                            {/* debug overlay removed */}
                                            {showColumnsOverlay && (s.columnsPreview || []).map((co, ci) => {
                                                const cw = Math.max(0.15, (Number(stallWidth) || 2.6) * 0.08) * (Number(unitsPerMeter) || 1); // world-size half-width
                                                if (co.poly && co.poly.length >= 3) {
                                                    return (
                                                        <polygon key={s.id + '-co-' + ci} points={co.poly.map(p => `${p.x},${p.y}`).join(' ')} fill={overlayPalette.columns.fill} stroke={overlayPalette.columns.stroke} strokeWidth={getStrokeUserWidth(0.9)} />
                                                    );
                                                }
                                                if (co.x != null && co.y != null) {
                                                    return (
                                                        <rect key={s.id + '-coc-' + ci} x={co.x - cw} y={co.y - cw} width={cw * 2} height={cw * 2} fill={overlayPalette.columns.fill} stroke={overlayPalette.columns.stroke} strokeWidth={getStrokeUserWidth(0.8)} />
                                                    );
                                                }
                                                return null;
                                            })}
                                            {showStallsOverlay && (s.stallsPreview || []).map((sv, si) => (
                                                <rect key={s.id + '-st-' + si} x={sv.x - sv.hw} y={sv.y - sv.hd} width={sv.hw * 2} height={sv.hd * 2} fill={overlayPalette.stalls.fill} stroke={overlayPalette.stalls.stroke} strokeWidth={getStrokeUserWidth(1.0)} />
                                            ))}
                                        </g>
                                    );
                                })())}
                                <polyline points={points.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="rgba(160,160,160,0.55)" strokeWidth={getStrokeUserWidth(1)} />
                                {/* preview guideline from last point to cursor when drawing */}
                                {mode === 'draw' && !closed && points.length > 0 && cursorPoint && (
                                    <>
                                        <line x1={points[points.length - 1].x} y1={points[points.length - 1].y} x2={cursorPoint.x} y2={cursorPoint.y} stroke="rgba(0,0,0,0.35)" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                        {/* live length tooltip */}
                                        {(() => {
                                            const live = getLiveLength();
                                            if (!live) return null;
                                            const px = Math.max(8, getHandleRadius(8));
                                            // place label slightly above the midpoint
                                            const lx = live.mid.x - px; const ly = live.mid.y - px * 1.6;
                                            const label = unitSystem === 'metric' ? `${live.m.toFixed(2)} m` : `${metersToFeet(live.m).toFixed(2)} ft`;
                                            return (
                                                <g>
                                                    <rect x={lx - 6} y={ly - 12} rx={4} ry={4} width={Math.max(40, label.length * 7)} height={18} fill="rgba(15,23,42,0.9)" />
                                                    <text x={lx} y={ly} fontSize={12} fill="#fff">{label}</text>
                                                </g>
                                            );
                                        })()}
                                        {/* guidance markers (end/mid/center/parallel/perp) */}
                                        {(() => {
                                            const g = getGuides(); if (!g) return null;
                                            const items = [];
                                            if (g.endpoint) {
                                                items.push(
                                                    <g key="g-end">
                                                        <circle cx={g.endpoint.x} cy={g.endpoint.y} r={getHandleRadius(6)} fill="none" stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.8)} />
                                                        <text x={g.endpoint.x + getHandleRadius(8)} y={g.endpoint.y - getHandleRadius(8)} fontSize={12} fill="#0f172a">end</text>
                                                    </g>
                                                );
                                            }
                                            if (g.midpoint) {
                                                items.push(
                                                    <g key="g-mid">
                                                        <circle cx={g.midpoint.x} cy={g.midpoint.y} r={getHandleRadius(5)} fill="none" stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.6)} strokeDasharray="2 2" />
                                                        <text x={g.midpoint.x + getHandleRadius(6)} y={g.midpoint.y - getHandleRadius(6)} fontSize={12} fill="#0f172a">mid</text>
                                                    </g>
                                                );
                                            }
                                            if (g.center) {
                                                items.push(
                                                    <g key="g-center">
                                                        <rect x={g.center.x - getHandleRadius(4)} y={g.center.y - getHandleRadius(4)} width={getHandleRadius(8)} height={getHandleRadius(8)} fill="none" stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.6)} />
                                                        <text x={g.center.x + getHandleRadius(8)} y={g.center.y - getHandleRadius(8)} fontSize={12} fill="#0f172a">center</text>
                                                    </g>
                                                );
                                            }
                                            if (g.parallel) {
                                                const t = g.parallel.target; items.push(
                                                    <g key="g-parallel">
                                                        <line x1={points[points.length - 1].x} y1={points[points.length - 1].y} x2={t.x} y2={t.y} stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.8)} strokeDasharray="6 4" />
                                                        <text x={t.x + getHandleRadius(6)} y={t.y - getHandleRadius(6)} fontSize={12} fill="#0f172a">parallel</text>
                                                    </g>
                                                );
                                            }
                                            if (g.perpendicular) {
                                                const t = g.perpendicular.target; items.push(
                                                    <g key="g-perp">
                                                        <line x1={points[points.length - 1].x} y1={points[points.length - 1].y} x2={t.x} y2={t.y} stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.8)} strokeDasharray="4 4" />
                                                        <text x={t.x + getHandleRadius(6)} y={t.y - getHandleRadius(6)} fontSize={12} fill="#0f172a">perp</text>
                                                    </g>
                                                );
                                            }
                                            return items;
                                        })()}
                                    </>
                                )}
                                {/* Counts badge */}
                                {lastRunCounts && (
                                    <g key="counts-badge" pointerEvents="none">
                                        <foreignObject x={viewBox.x + 8} y={viewBox.y + 8} width={280} height={40}>
                                            <div xmlns="http://www.w3.org/1999/xhtml" style={{
                                                background: 'rgba(15,23,42,0.75)', color: '#e5e7eb', borderRadius: '8px', padding: '6px 10px', fontSize: '12px',
                                                display: 'inline-flex', gap: '10px', alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.25)'
                                            }}>
                                                <span>Stalls: {lastRunCounts.stalls}</span>
                                                <span>| Aisles: {lastRunCounts.aisles}</span>
                                                <span>| Connectors: {lastRunCounts.connectors}</span>
                                                <span>| Columns: {lastRunCounts.columns}</span>
                                            </div>
                                        </foreignObject>
                                    </g>
                                )}
                                {/* Simple on-canvas legend */}
                                {showLegend && (
                                    <g key="legend" pointerEvents="none">
                                        {(() => {
                                            // Keep legend a constant on-screen size and anchor at bottom-right
                                            // Compute compact size from content to avoid large blank area
                                            const padPx = 10; // screen pixels
                                            const widthPx = 140; // tighter width to remove extra white space
                                            const rowPx = 12; // line height
                                            const gapPx = 2; // row gap
                                            const rows = 7; // Aisles, Streets, Connectors, Stalls, Columns, Access, Ramp
                                            const heightPx = 6 + rows * (rowPx + gapPx) + 6; // top/bottom padding
                                            const pad = getStrokeUserWidth(padPx);
                                            const userW = getStrokeUserWidth(widthPx);
                                            const userH = getStrokeUserWidth(heightPx);
                                            const lx = viewBox.x + viewBox.w - userW - pad;
                                            const ly = viewBox.y + viewBox.h - userH - pad;
                                            return (
                                                <foreignObject x={lx} y={ly} width={userW} height={userH}>
                                                    <div xmlns="http://www.w3.org/1999/xhtml" style={{
                                                        background: 'rgba(255,255,255,0.78)', color: '#0f172a', borderRadius: 6, padding: '6px 8px',
                                                        fontSize: 10, lineHeight: 1.35, boxShadow: '0 1px 4px rgba(0,0,0,0.10)', width: 'fit-content'
                                                    }}>
                                                        <div style={{ display: 'grid', gridTemplateColumns: 'auto auto', columnGap: 6, rowGap: 2 }}>
                                                            <div style={{ background: overlayPalette.aisles.fill, border: `1px solid ${overlayPalette.aisles.stroke}`, width: 10, height: 10 }} />
                                                            <div>Aisles</div>
                                                            <div style={{ background: overlayPalette.streets.fill, border: `1px solid ${overlayPalette.streets.stroke}`, width: 10, height: 10 }} />
                                                            <div>Streets</div>
                                                            <div style={{ background: overlayPalette.streets.fill, border: `1px solid ${overlayPalette.streets.stroke}`, width: 10, height: 10 }} />
                                                            <div>Connectors</div>
                                                            <div style={{ background: overlayPalette.stalls.fill, border: `1px solid ${overlayPalette.stalls.stroke}`, width: 10, height: 10 }} />
                                                            <div>Stalls</div>
                                                            <div style={{ background: overlayPalette.columns.fill, border: `1px solid ${overlayPalette.columns.stroke}`, width: 10, height: 10 }} />
                                                            <div>Columns</div>
                                                            <div style={{ background: overlayPalette.access.fill, border: `1px solid ${overlayPalette.access.stroke}`, width: 10, height: 10 }} />
                                                            <div>Access</div>
                                                            <div style={{ background: overlayPalette.ramps.fill, border: `1px solid ${overlayPalette.ramps.stroke}`, width: 10, height: 10 }} />
                                                            <div>Ramp</div>
                                                        </div>
                                                    </div>
                                                </foreignObject>
                                            );
                                        })()}
                                    </g>
                                )}
                                {/* Auto Design panel moved to fixed HTML overlay (outside SVG) */}
                                {closed && points.length >= 3 && (
                                    <polygon points={points.map(p => `${p.x},${p.y}`).join(' ')} fill="rgba(50,130,230,0.08)" stroke="#124" strokeWidth={getStrokeUserWidth(1.5)} />
                                )}
                                {points.map((p, i) => (
                                    <g key={i}>
                                        <circle
                                            cx={p.x} cy={p.y} r={getHandleRadius()} fill={selectedPoints.includes(i) ? '#f6c84c' : '#111'} stroke="#fff" strokeWidth={Math.max(1, getHandleRadius() * 0.15)} style={{ cursor: measureActive ? 'crosshair' : 'grab', pointerEvents: measureActive ? 'none' : 'auto' }}
                                            onMouseDown={(ev) => {
                                                if (measureActive) return; // let measure clicks pass through
                                                ev.stopPropagation();
                                                if (!svgRef.current) { setDraggingIndex(i); return; }
                                                const pt = svgRef.current.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
                                                const cursor = pt.matrixTransform(svgRef.current.getScreenCTM().inverse());
                                                if (selectedPoints.includes(i)) {
                                                    setGroupDragging(true);
                                                    setGroupDragOrigin(cursor);
                                                    setGroupOriginalPoints(selectedPoints.map(idx => ({ x: points[idx].x, y: points[idx].y })));
                                                } else {
                                                    setDraggingIndex(i);
                                                }
                                            }}
                                            onClick={(ev) => { if (!measureActive) togglePointSelection(i, ev); }}
                                            onContextMenu={(ev) => { if (measureActive) return; ev.preventDefault(); setPoints(prev => prev.filter((_, idx) => idx !== i)); }}
                                        />
                                        {/* Point labels removed per request for cleaner UI */}
                                    </g>
                                ))}
                                {/* Persistent dimension annotations */}
                                {showDimensions && measureAnnotations && measureAnnotations.length > 0 && (
                                    <g key="dims-persistent" pointerEvents="visiblePainted" opacity={0.85}>
                                        {measureAnnotations.map((m, i) => {
                                            // Resolve endpoints live from bound vertices to avoid lag/duplication while dragging
                                            const a = (Number.isInteger(m.aIdx) && points[m.aIdx]) ? points[m.aIdx] : m.a;
                                            const b = (Number.isInteger(m.bIdx) && points[m.bIdx]) ? points[m.bIdx] : m.b;
                                            const du = Math.hypot(b.x - a.x, b.y - a.y); if (du < 1e-6) return null;
                                            const dm = du / Math.max(1, Number(unitsPerMeter || 1));
                                            const ux = (b.x - a.x) / du, uy = (b.y - a.y) / du;
                                            const nx = -uy, ny = ux;
                                            let off = Number(m.offset);
                                            if (!Number.isFinite(off)) {
                                                // backwards compat: derive offset from existing label if any
                                                const midx = (a.x + b.x) / 2, midy = (a.y + b.y) / 2;
                                                if (m.label && Number.isFinite(m.label.x) && Number.isFinite(m.label.y)) {
                                                    off = (m.label.x - midx) * nx + (m.label.y - midy) * ny;
                                                } else {
                                                    off = 0;
                                                }
                                            }
                                            const ap = { x: a.x + nx * off, y: a.y + ny * off };
                                            const bp = { x: b.x + nx * off, y: b.y + ny * off };
                                            const midp = { x: (ap.x + bp.x) / 2, y: (ap.y + bp.y) / 2 };
                                            const labelTxt = unitSystem === 'metric' ? `${dm.toFixed(2)} m` : `${metersToFeet(dm).toFixed(2)} ft`;
                                            const charW = 7, padding = 16; const approxW = Math.max(60, labelTxt.length * charW + padding);
                                            const tick = getHandleRadius(5);
                                            const isEditing = editingDimIndex === i;
                                            return (
                                                <g key={`dim-${i}`} style={{ cursor: !measureActive ? 'pointer' : 'default' }} onClick={(ev) => { ev.stopPropagation(); if (!measureActive) startEditDimension(i); }}>
                                                    {/* extension lines */}
                                                    <line x1={a.x} y1={a.y} x2={ap.x} y2={ap.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                                    <line x1={b.x} y1={b.y} x2={bp.x} y2={bp.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                                    {/* dimension line (parallel to segment) */}
                                                    <line x1={ap.x} y1={ap.y} x2={bp.x} y2={bp.y} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.8)} />
                                                    {/* ticks at ends */}
                                                    <line x1={ap.x - nx * tick} y1={ap.y - ny * tick} x2={ap.x + nx * tick} y2={ap.y + ny * tick} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                                    <line x1={bp.x - nx * tick} y1={bp.y - ny * tick} x2={bp.x + nx * tick} y2={bp.y + ny * tick} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                                    {/* centered label */}
                                                    {isEditing ? (
                                                        <foreignObject x={midp.x - approxW / 2} y={midp.y - 20} width={approxW} height={24}>
                                                            <div xmlns="http://www.w3.org/1999/xhtml" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
                                                                <input autoFocus value={editingDimValue} onChange={e => setEditingDimValue(e.target.value)} onBlur={commitEditDimension} onKeyDown={e => { if (e.key === 'Enter') { commitEditDimension(); } else if (e.key === 'Escape') { cancelEditDimension(); } }} style={{ width: '100%', height: '100%', background: 'rgba(15,23,42,0.95)', color: '#fff', border: '1px solid rgba(255,255,255,0.35)', borderRadius: 6, textAlign: 'center', fontSize: 12 }} />
                                                            </div>
                                                        </foreignObject>
                                                    ) : (
                                                        <>
                                                            <rect x={midp.x - approxW / 2} y={midp.y - 18} width={approxW} height={20} rx={6} fill="rgba(15,23,42,0.70)" stroke="rgba(2,6,23,0.2)" strokeWidth={getStrokeUserWidth(0.8)} />
                                                            <text x={midp.x} y={midp.y - 4} fontSize={12} fill="#ffffff" textAnchor="middle">{labelTxt}</text>
                                                        </>
                                                    )}
                                                </g>
                                            );
                                        })}
                                    </g>
                                )}
                                {/* One-shot temporary annotation (ephemeral) */}
                                {oneShotMeasureTempAnn && showDimensions && (
                                    <g key="dims-temp" pointerEvents="none" opacity={0.95}>
                                        {(() => {
                                            const m = oneShotMeasureTempAnn;
                                            const a = (Number.isInteger(m.aIdx) && points[m.aIdx]) ? points[m.aIdx] : m.a;
                                            const b = (Number.isInteger(m.bIdx) && points[m.bIdx]) ? points[m.bIdx] : m.b;
                                            const du = Math.hypot(b.x - a.x, b.y - a.y); if (du < 1e-6) return null;
                                            const dm = du / Math.max(1, Number(unitsPerMeter || 1));
                                            const ux = (b.x - a.x) / du, uy = (b.y - a.y) / du;
                                            const nx = -uy, ny = ux;
                                            const off = Number(m.offset) || 0;
                                            const ap = { x: a.x + nx * off, y: a.y + ny * off };
                                            const bp = { x: b.x + nx * off, y: b.y + ny * off };
                                            const midp = { x: (ap.x + bp.x) / 2, y: (ap.y + bp.y) / 2 };
                                            const labelTxt = unitSystem === 'metric' ? `${dm.toFixed(2)} m` : `${metersToFeet(dm).toFixed(2)} ft`;
                                            const charW = 7, padding = 16; const approxW = Math.max(60, labelTxt.length * charW + padding);
                                            const tick = getHandleRadius(5);
                                            return (
                                                <g>
                                                    <line x1={a.x} y1={a.y} x2={ap.x} y2={ap.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                                    <line x1={b.x} y1={b.y} x2={bp.x} y2={bp.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                                    <line x1={ap.x} y1={ap.y} x2={bp.x} y2={bp.y} stroke="#06b6d4" strokeWidth={getStrokeUserWidth(1.8)} />
                                                    <line x1={ap.x - nx * tick} y1={ap.y - ny * tick} x2={ap.x + nx * tick} y2={ap.y + ny * tick} stroke="#06b6d4" strokeWidth={getStrokeUserWidth(1.2)} />
                                                    <line x1={bp.x - nx * tick} y1={bp.y - ny * tick} x2={bp.x + nx * tick} y2={bp.y + ny * tick} stroke="#06b6d4" strokeWidth={getStrokeUserWidth(1.2)} />
                                                    <rect x={midp.x - approxW / 2} y={midp.y - 18} width={approxW} height={20} rx={6} fill="rgba(15,23,42,0.85)" stroke="rgba(2,6,23,0.3)" strokeWidth={getStrokeUserWidth(1)} />
                                                    <text x={midp.x} y={midp.y - 4} fontSize={12} fill="#ffffff" textAnchor="middle">{labelTxt}</text>
                                                </g>
                                            );
                                        })()}
                                    </g>
                                )}
                                {/* Measure placement preview (third click to place label) */}
                                {(mode === 'measure') && measurePlacePending && cursorPoint && (() => {
                                    const a = measurePlacePending.a, b = measurePlacePending.b; const du = Math.hypot(b.x - a.x, b.y - a.y); if (du < 1e-6) return null;
                                    const dm = du / Math.max(1, Number(unitsPerMeter || 1));
                                    const ux = (b.x - a.x) / du, uy = (b.y - a.y) / du; const nx = -uy, ny = ux;
                                    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
                                    const off = (cursorPoint.x - mx) * nx + (cursorPoint.y - my) * ny;
                                    const ap = { x: a.x + nx * off, y: a.y + ny * off };
                                    const bp = { x: b.x + nx * off, y: b.y + ny * off };
                                    const midp = { x: (ap.x + bp.x) / 2, y: (ap.y + bp.y) / 2 };
                                    const labelTxt = unitSystem === 'metric' ? `${dm.toFixed(2)} m` : `${metersToFeet(dm).toFixed(2)} ft`;
                                    const charW = 7, padding = 16; const approxW = Math.max(60, labelTxt.length * charW + padding);
                                    const tick = getHandleRadius(5);
                                    return (
                                        <g pointerEvents="none" opacity={0.95}>
                                            {/* extension lines */}
                                            <line x1={a.x} y1={a.y} x2={ap.x} y2={ap.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                            <line x1={b.x} y1={b.y} x2={bp.x} y2={bp.y} stroke="#94a3b8" strokeWidth={getStrokeUserWidth(1)} strokeDasharray="4 4" />
                                            {/* dimension line */}
                                            <line x1={ap.x} y1={ap.y} x2={bp.x} y2={bp.y} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(2)} />
                                            {/* ticks */}
                                            <line x1={ap.x - nx * tick} y1={ap.y - ny * tick} x2={ap.x + nx * tick} y2={ap.y + ny * tick} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                            <line x1={bp.x - nx * tick} y1={bp.y - ny * tick} x2={bp.x + nx * tick} y2={bp.y + ny * tick} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                            {/* centered label */}
                                            <rect x={midp.x - approxW / 2} y={midp.y - 18} width={approxW} height={20} rx={6} fill="rgba(15,23,42,0.85)" stroke="rgba(2,6,23,0.3)" strokeWidth={getStrokeUserWidth(1)} />
                                            <text x={midp.x} y={midp.y - 4} fontSize={12} fill="#ffffff" textAnchor="middle">{labelTxt}</text>
                                        </g>
                                    );
                                })()}
                                {/* Live measuring overlay (one anchor picked) */}
                                {(measureActive) && measurePoints.length === 1 && cursorPoint && (() => {
                                    const a = measurePoints[0], b = cursorPoint; const du = Math.hypot(b.x - a.x, b.y - a.y); const dm = du / Math.max(1, Number(unitsPerMeter || 1));
                                    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2; const label = unitSystem === 'metric' ? `${dm.toFixed(2)} m` : `${metersToFeet(dm).toFixed(2)} ft`;
                                    const charW = 7, padding = 16; const approxW = Math.max(60, label.length * charW + padding);
                                    return (
                                        <g>
                                            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(2)} strokeDasharray="4 4" />
                                            <circle cx={a.x} cy={a.y} r={getHandleRadius(6)} fill="#0ea5e9" stroke="#0f172a" strokeWidth={getStrokeUserWidth(1)} />
                                            <rect x={mx - approxW / 2} y={my - 18} width={approxW} height={20} rx={6} fill="rgba(15,23,42,0.85)" stroke="rgba(2,6,23,0.3)" strokeWidth={getStrokeUserWidth(1)} />
                                            <text x={mx} y={my - 4} fontSize={12} fill="#ffffff" textAnchor="middle">{label}</text>
                                        </g>
                                    );
                                })()}
                                {/* CPlane axes: draw when visible */}
                                {cplaneVisible && (() => {
                                    const ox = cplaneOrigin.x, oy = cplaneOrigin.y;
                                    const axisLen = Math.max(viewBox.w, viewBox.h) * 0.6;
                                    const xEnd = { x: ox + cplaneXDir.x * axisLen, y: oy + cplaneXDir.y * axisLen };
                                    const yDir = { x: -cplaneXDir.y, y: cplaneXDir.x };
                                    const yEnd = { x: ox + yDir.x * axisLen, y: oy + yDir.y * axisLen };
                                    const labelOffset = 12;
                                    return (
                                        <g key="cplane-axes" opacity={0.9}>
                                            <line x1={ox - cplaneXDir.x * 0.2 * axisLen} y1={oy - cplaneXDir.y * 0.2 * axisLen} x2={xEnd.x} y2={xEnd.y} stroke="#ef4444" strokeWidth={getStrokeUserWidth(1)} markerEnd="url(#cplaneArrowX)" />
                                            <line x1={ox - yDir.x * 0.2 * axisLen} y1={oy - yDir.y * 0.2 * axisLen} x2={yEnd.x} y2={yEnd.y} stroke="#10b981" strokeWidth={getStrokeUserWidth(1)} markerEnd="url(#cplaneArrowY)" />
                                            <circle cx={ox} cy={oy} r={getHandleRadius(6)} fill="#0f172a" opacity={0.14} stroke="#0f172a" strokeWidth={getStrokeUserWidth(0.8)} />
                                            <text x={xEnd.x + (cplaneXDir.x * labelOffset)} y={xEnd.y + (cplaneXDir.y * labelOffset)} fontSize={14} fill="#0f172a">X</text>
                                            <text x={yEnd.x + (yDir.x * labelOffset)} y={yEnd.y + (yDir.y * labelOffset)} fontSize={14} fill="#0f172a">Y</text>
                                        </g>
                                    );
                                })()}
                                {/* show small hit-circle around start point to indicate auto-close */}
                                {points.length > 0 && !closed && (
                                    <circle cx={points[0].x} cy={points[0].y} r={getHitRadius()} fill="rgba(0,0,0,0.04)" stroke="rgba(0,0,0,0.06)" />
                                )}
                                {/* hover insert indicator (+) to hint adding a vertex */}
                                {!measureActive && hoverInsert && hoverInsert.p && (
                                    <g pointerEvents="none" opacity={0.9}>
                                        <circle cx={hoverInsert.p.x} cy={hoverInsert.p.y} r={getHandleRadius(6)} fill="rgba(14,165,233,0.25)" stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(0.8)} />
                                        <line x1={hoverInsert.p.x - getHandleRadius(4)} y1={hoverInsert.p.y} x2={hoverInsert.p.x + getHandleRadius(4)} y2={hoverInsert.p.y} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                        <line x1={hoverInsert.p.x} y1={hoverInsert.p.y - getHandleRadius(4)} x2={hoverInsert.p.x} y2={hoverInsert.p.y + getHandleRadius(4)} stroke="#0ea5e9" strokeWidth={getStrokeUserWidth(1.2)} />
                                    </g>
                                )}
                                {/* marquee selection rect (user space) */}
                                {marqueeRect && (
                                    <rect x={marqueeRect.x} y={marqueeRect.y} width={marqueeRect.w} height={marqueeRect.h} fill="rgba(15,23,42,0.04)" stroke="rgba(15,23,42,0.14)" strokeWidth={getStrokeUserWidth(0.5)} strokeDasharray="4 4" />
                                )}

                                {/* clipped diagnostics: show rejected clipped fragments as ghost red polygons */}
                                {showClipDiagnostics && clipDiagnostics && clipDiagnostics.length > 0 && (
                                    <g key="clip-diags" opacity={0.95} pointerEvents="none">
                                        {clipDiagnostics.map((d, idx) => {
                                            if (!d || !d.poly || d.poly.length < 3) return null;
                                            const pts = d.poly.map(p => `${p.x},${p.y}`).join(' ');
                                            return (
                                                <polygon key={'clipdiag-' + idx} points={pts}
                                                    fill={'rgba(220,38,38,0.10)'}
                                                    stroke={'rgba(220,38,38,0.55)'}
                                                    strokeWidth={getStrokeUserWidth(0.6)}
                                                    strokeDasharray="6 4"
                                                />
                                            );
                                        })}
                                    </g>
                                )}
                                {/* Column debug overlay: show tested centers color-coded */}
                                {showColumnDebug && columnDebugPoints && columnDebugPoints.length > 0 && (
                                    <g key="col-debug" pointerEvents="none">
                                        {columnDebugPoints.map((p, idx) => {
                                            let color = 'rgba(100,116,139,0.7)';
                                            if (p.status === 'accepted') color = 'rgba(34,197,94,0.95)';
                                            else if (p.status === 'intersect' || p.status === 'intersect_aisle' || p.status === 'intersect_feature') color = 'rgba(249,115,22,0.95)';
                                            else if (p.status === 'outside') color = 'rgba(148,163,184,0.6)';
                                            const r = getHandleRadius(6);
                                            return (
                                                <g key={'coldbg-' + idx}>
                                                    <circle cx={p.x} cy={p.y} r={r} fill={color} stroke={"rgba(0,0,0,0.06)"} strokeWidth={getStrokeUserWidth(0.6)} />
                                                </g>
                                            );
                                        })}
                                    </g>
                                )}
                                {/* Column grid preview (light dots) */}
                                {showColumnGrid && columnGridParams && columnGridPreviewPoints && columnGridPreviewPoints.length > 0 && (
                                    <g key="col-grid-preview" opacity={0.85} pointerEvents="none">
                                        {columnGridPreviewPoints.map((p, i) => (
                                            <circle key={'gridpt-' + i} cx={p.x} cy={p.y} r={Math.max(1, getHandleRadius(3))} fill={'rgba(100,116,139,0.18)'} stroke={'rgba(100,116,139,0.08)'} strokeWidth={getStrokeUserWidth(0.3)} />
                                        ))}
                                    </g>
                                )}
                                {/* Revit-like dashed grid lines (align to preview points when available) */}
                                {showColumnGrid && columnGridParams && points && points.length > 2 && (
                                    (() => {
                                        // Compute axis-aligned bounds in view space
                                        const xs = points.map(p => p.x);
                                        const ys = points.map(p => p.y);
                                        const minX = Math.min(...xs);
                                        const maxX = Math.max(...xs);
                                        const minY = Math.min(...ys);
                                        const maxY = Math.max(...ys);
                                        // Prefer saved grid params for exact alignment; fall back to CPlane
                                        const angle = (columnGridParams && typeof columnGridParams.angle === 'number')
                                            ? columnGridParams.angle
                                            : Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
                                        const cosA = Math.cos(angle);
                                        const sinA = Math.sin(angle);
                                        // Helper to rotate a point around origin
                                        const rot = (pt) => ({ x: pt.x * cosA - pt.y * sinA, y: pt.x * sinA + pt.y * cosA });
                                        const invRot = (pt) => ({ x: pt.x * cosA + pt.y * sinA * -1, y: pt.x * sinA + pt.y * cosA });
                                        // Choose a grid origin at the lower-left of bounds projected into local grid space
                                        // Transform bounds corners to grid-local, then build lines at spacing intervals
                                        const corners = [
                                            { x: minX, y: minY },
                                            { x: maxX, y: minY },
                                            { x: maxX, y: maxY },
                                            { x: minX, y: maxY }
                                        ];
                                        const localCorners = corners.map(c => ({ x: c.x * cosA + c.y * sinA, y: -c.x * sinA + c.y * cosA }));
                                        const localMinX = Math.min(...localCorners.map(c => c.x));
                                        const localMaxX = Math.max(...localCorners.map(c => c.x));
                                        const localMinY = Math.min(...localCorners.map(c => c.y));
                                        const localMaxY = Math.max(...localCorners.map(c => c.y));
                                        const lines = [];
                                        // If we have saved params from the generator, use them directly
                                        if (columnGridParams && columnGridParams.spacingX && columnGridParams.spacingY) {
                                            const sx = Math.max(0.001, columnGridParams.spacingX);
                                            const sy = Math.max(0.001, columnGridParams.spacingY);
                                            const offX = Math.max(0, columnGridParams.offsetX || 0);
                                            const offY = Math.max(0, columnGridParams.offsetY || 0);
                                            const startGX = Math.floor((localMinX - offX) / sx) * sx + offX;
                                            const startGY = Math.floor((localMinY - offY) / sy) * sy + offY;
                                            for (let gx = startGX; gx <= localMaxX; gx += sx) {
                                                const p0Local = { x: gx, y: localMinY };
                                                const p1Local = { x: gx, y: localMaxY };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                            for (let gy = startGY; gy <= localMaxY; gy += sy) {
                                                const p0Local = { x: localMinX, y: gy };
                                                const p1Local = { x: localMaxX, y: gy };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                        } else if (Array.isArray(columnGridPreviewPoints) && columnGridPreviewPoints.length > 0) {
                                            // Otherwise align to preview points by inferring spacing and buckets
                                            let sx = Math.max(0.001, manualGridSpacingX || 8);
                                            let sy = Math.max(0.001, manualGridSpacingY || 8);
                                            // Project preview points to local grid space
                                            const localPts = columnGridPreviewPoints.map(pt => ({ x: pt.x * cosA + pt.y * sinA, y: -pt.x * sinA + pt.y * cosA }));
                                            // If manual grid disabled, infer spacing from preview
                                            if (!manualGridEnabled && localPts.length > 1) {
                                                // compute nearest neighbor distances along X and Y
                                                const xsOnly = localPts.map(p => p.x).sort((a, b) => a - b);
                                                const ysOnly = localPts.map(p => p.y).sort((a, b) => a - b);
                                                const dxs = []; const dys = [];
                                                for (let i = 1; i < xsOnly.length; i++) { const d = xsOnly[i] - xsOnly[i - 1]; if (d > 1e-6) dxs.push(d); }
                                                for (let i = 1; i < ysOnly.length; i++) { const d = ysOnly[i] - ysOnly[i - 1]; if (d > 1e-6) dys.push(d); }
                                                const median = arr => arr.length ? arr.sort((a, b) => a - b)[Math.floor(arr.length / 2)] : null;
                                                sx = Math.max(0.001, median(dxs) || sx);
                                                sy = Math.max(0.001, median(dys) || sy);
                                            }
                                            const snapX = (v) => Math.round(v / sx) * sx;
                                            const snapY = (v) => Math.round(v / sy) * sy;
                                            const xSet = new Map();
                                            const ySet = new Map();
                                            for (const lp of localPts) { xSet.set(snapX(lp.x), true); ySet.set(snapY(lp.y), true); }
                                            // Build lines passing through the buckets
                                            for (const [gx] of xSet) {
                                                const p0Local = { x: gx, y: localMinY };
                                                const p1Local = { x: gx, y: localMaxY };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                            for (const [gy] of ySet) {
                                                const p0Local = { x: localMinX, y: gy };
                                                const p1Local = { x: localMaxX, y: gy };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                        } else {
                                            // Fallback: uniform grid from bounds
                                            const sx = Math.max(0.001, manualGridSpacingX || 8);
                                            const sy = Math.max(0.001, manualGridSpacingY || 8);
                                            for (let gx = Math.floor(localMinX / sx) * sx; gx <= localMaxX; gx += sx) {
                                                const p0Local = { x: gx, y: localMinY };
                                                const p1Local = { x: gx, y: localMaxY };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                            for (let gy = Math.floor(localMinY / sy) * sy; gy <= localMaxY; gy += sy) {
                                                const p0Local = { x: localMinX, y: gy };
                                                const p1Local = { x: localMaxX, y: gy };
                                                const p0 = { x: p0Local.x * cosA - p0Local.y * sinA, y: p0Local.x * sinA + p0Local.y * cosA };
                                                const p1 = { x: p1Local.x * cosA - p1Local.y * sinA, y: p1Local.x * sinA + p1Local.y * cosA };
                                                lines.push({ p0, p1 });
                                            }
                                        }
                                        // Compute grid origin crosshair in world space
                                        let originWorld = null;
                                        if (columnGridParams && columnGridParams.spacingX && columnGridParams.spacingY) {
                                            const offX = Math.max(0, columnGridParams.offsetX || 0);
                                            const offY = Math.max(0, columnGridParams.offsetY || 0);
                                            // origin at (offX, offY) in local space
                                            originWorld = { x: offX * cosA - offY * sinA, y: offX * sinA + offY * cosA };
                                        } else {
                                            // fallback: lower-left local corner
                                            originWorld = { x: localMinX * cosA - localMinY * sinA, y: localMinX * sinA + localMinY * cosA };
                                        }
                                        // Simple edge labels every N lines
                                        const labelEvery = 3;
                                        return (
                                            <g key="col-grid-lines" pointerEvents="none">
                                                {lines.map((ln, i) => (
                                                    <line
                                                        key={'gridln-' + i}
                                                        x1={ln.p0.x}
                                                        y1={ln.p0.y}
                                                        x2={ln.p1.x}
                                                        y2={ln.p1.y}
                                                        stroke={"#64748B"}
                                                        strokeWidth={getStrokeUserWidth(0.6)}
                                                        strokeDasharray={`${getStrokeUserWidth(3)} ${getStrokeUserWidth(3)}`}
                                                        opacity={0.35}
                                                    />
                                                ))}
                                                {/* Grid origin crosshair */}
                                                {originWorld && (
                                                    <g>
                                                        <line x1={originWorld.x - getHandleRadius(8)} y1={originWorld.y} x2={originWorld.x + getHandleRadius(8)} y2={originWorld.y} stroke="#64748B" strokeWidth={getStrokeUserWidth(0.8)} />
                                                        <line x1={originWorld.x} y1={originWorld.y - getHandleRadius(8)} x2={originWorld.x} y2={originWorld.y + getHandleRadius(8)} stroke="#64748B" strokeWidth={getStrokeUserWidth(0.8)} />
                                                        <circle cx={originWorld.x} cy={originWorld.y} r={getHandleRadius(2)} fill="#64748B" />
                                                    </g>
                                                )}
                                            </g>
                                        );
                                    })()
                                )}
                                {/* render stalls preview for levels: active level full opacity, others faded */}
                                {levels.map((lvl, li) => (
                                    (lvl.visible && lvl.stallsPreview && lvl.stallsPreview.length > 0) ? (
                                        <g key={'level-' + lvl.id} opacity={li === currentLevelIndex ? 1 : 0.36}>
                                            {lvl.stallsPreview.map((s, i) => {
                                                const t = s.type || 'stall';
                                                if (t === 'stall') {
                                                    const isSelected = li === currentLevelIndex && selectedStalls.includes(i);
                                                    const fill = isSelected ? 'rgba(245,158,11,0.22)' : (li === currentLevelIndex ? 'rgba(30,100,200,0.18)' : 'rgba(30,100,200,0.08)');
                                                    const stroke = isSelected ? '#f59e0b' : (li === currentLevelIndex ? '#155' : '#0b5566');
                                                    // render clipped polygon if present, otherwise axis-aligned rect
                                                    if (s.poly && s.poly.length >= 3) {
                                                        const pts = s.poly.map(p => `${p.x},${p.y}`).join(' ');
                                                        return (
                                                            <polygon key={lvl.id + '-st' + i} points={pts} fill={fill} stroke={stroke} strokeWidth={getStrokeUserWidth(isSelected ? 1.4 : 0.8)} style={{ cursor: measureActive ? 'crosshair' : 'pointer', pointerEvents: measureActive ? 'none' : 'auto' }} onClick={(ev) => { if (!measureActive) toggleStallSelection(i, li, ev); }} />
                                                        );
                                                    }
                                                    return (
                                                        <rect
                                                            key={lvl.id + '-st' + i}
                                                            x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={fill}
                                                            stroke={stroke}
                                                            strokeWidth={getStrokeUserWidth(isSelected ? 1.4 : 0.8)}
                                                            style={{ cursor: measureActive ? 'crosshair' : 'pointer', pointerEvents: measureActive ? 'none' : 'auto' }}
                                                            onClick={(ev) => { if (!measureActive) toggleStallSelection(i, li, ev); }}
                                                        />
                                                    );
                                                }
                                                if (t === 'aisle') {
                                                    return (
                                                        <rect key={lvl.id + '-aisle' + i} x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={'rgba(148,163,184,0.18)'} stroke={'rgba(100,116,139,0.28)'} strokeWidth={getStrokeUserWidth(0.7)} style={{ pointerEvents: 'none' }} />
                                                    );
                                                }
                                                if (t === 'street' || t === 'perimeter') {
                                                    return (
                                                        <rect key={lvl.id + '-street' + i} x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={'rgba(2,6,23,0.12)'} stroke={'rgba(2,6,23,0.24)'} strokeWidth={getStrokeUserWidth(0.9)} style={{ pointerEvents: 'none' }} />
                                                    );
                                                }
                                                if (t === 'access') {
                                                    return (
                                                        <rect key={lvl.id + '-access' + i} x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={'rgba(16,185,129,0.22)'} stroke={'#10b981'} strokeWidth={getStrokeUserWidth(0.9)} style={{ pointerEvents: 'none' }} />
                                                    );
                                                }
                                                if (t === 'ramp') {
                                                    return (
                                                        <rect key={lvl.id + '-ramp' + i} x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={'rgba(245,158,11,0.32)'} stroke={'#f59e0b'} strokeWidth={getStrokeUserWidth(1)} style={{ pointerEvents: 'auto', cursor: 'default' }} />
                                                    );
                                                }
                                                if (t === 'core') {
                                                    return (
                                                        <rect key={lvl.id + '-core' + i} x={s.x - s.hw} y={s.y - s.hd} width={s.hw * 2} height={s.hd * 2}
                                                            fill={'rgba(100,116,139,0.22)'} stroke={'#475569'} strokeWidth={getStrokeUserWidth(0.9)} style={{ pointerEvents: 'none' }} />
                                                    );
                                                }
                                                if (t === 'column') {
                                                    if (s.poly && s.poly.length >= 3) {
                                                        const pts = s.poly.map(p => `${p.x},${p.y}`).join(' ');
                                                        return (
                                                            <polygon key={lvl.id + '-col' + i} points={pts} fill={'rgba(30,58,138,0.35)'} stroke={'rgba(30,58,138,0.95)'} strokeWidth={getStrokeUserWidth(1.1)} style={{ pointerEvents: 'none' }} />
                                                        );
                                                    }
                                                    // fallback: draw a small world-sized square at center
                                                    if (s.x != null && s.y != null) {
                                                        const cw = Math.max(0.15, (Number(stallWidth) || 2.6) * 0.08) * (Number(unitsPerMeter) || 1);
                                                        return (
                                                            <rect key={lvl.id + '-colc' + i} x={s.x - cw} y={s.y - cw} width={cw * 2} height={cw * 2} fill={'rgba(30,58,138,0.35)'} stroke={'rgba(30,58,138,0.95)'} strokeWidth={getStrokeUserWidth(0.9)} />
                                                        );
                                                    }
                                                    return null;
                                                }
                                                return null;
                                            })}
                                        </g>
                                    ) : null
                                ))}
                                {/* live area */}
                                {/* insertion preview rectangle when using insertion tools */}
                                {insertionRect && (() => {
                                    const r = insertionRect;
                                    let fill = 'rgba(148,163,184,0.18)';
                                    let stroke = 'rgba(100,116,139,0.28)';
                                    if (insertionMode === 'street') { fill = 'rgba(2,6,23,0.12)'; stroke = 'rgba(2,6,23,0.28)'; }
                                    else if (insertionMode === 'ramp') { fill = 'rgba(245,158,11,0.28)'; stroke = '#f59e0b'; }
                                    else if (insertionMode === 'access') { fill = 'rgba(16,185,129,0.22)'; stroke = '#10b981'; }
                                    else if (insertionMode === 'core') { fill = 'rgba(100,116,139,0.22)'; stroke = '#475569'; }
                                    return (
                                        <rect x={r.x} y={r.y} width={r.w} height={r.h} fill={fill} stroke={stroke} strokeWidth={getStrokeUserWidth(0.9)} opacity={0.9} />
                                    );
                                })()}
                                {points.length >= 3 && !minimalMarkers && (() => {
                                    const areaMeters = computePolygonArea(points) / (unitsPerMeter * unitsPerMeter);
                                    const areaDisplay = unitSystem === 'imperial' ? Math.round(m2ToFt2(areaMeters)) : Math.round(areaMeters);
                                    return (<text x={12} y={20} fontSize={16} fill="#0f172a">Area: {areaDisplay} {unitSystem === 'metric' ? 'm²' : 'ft²'}</text>);
                                })()}
                            </svg>
                        ) : null}

                        {viewMode === '3d' ? (
                            <div style={{ width: '100%', height: 480 }}>
                                <ThreeView
                                    points={points}
                                    levels={levels}
                                    currentLevelIndex={currentLevelIndex}
                                    unitsPerMeter={unitsPerMeter}
                                    cplaneOrigin={cplaneOrigin}
                                    cplaneXDir={cplaneXDir}
                                    onPointsChange={(updated) => {
                                        // update live while dragging in 3D; do not push history on every move
                                        setPoints(updated);
                                    }}
                                    onPointsDragEnd={(updated) => {
                                        // finalize drag: update points and push history so undo works
                                        setPoints(updated);
                                        pushHistoryFrom(updated, closed);
                                    }}
                                />
                            </div>
                        ) : null}

                        {/* Miniature corner CPlane / 3D indicator (non-interactive) */}
                        <div style={{ position: 'absolute', top: 8, right: 8, width: 96, height: 96, pointerEvents: 'none', zIndex: 20 }} aria-hidden>
                            <svg width="100%" height="100%" viewBox="0 0 96 96">
                                <defs>
                                    <marker id="miniArrowX" markerWidth="3" markerHeight="3" refX="2.5" refY="1.5" orient="auto">
                                        <path d="M0,0 L3,1.5 L0,3 z" fill="#ef4444" />
                                    </marker>
                                    <marker id="miniArrowY" markerWidth="3" markerHeight="3" refX="2.5" refY="1.5" orient="auto">
                                        <path d="M0,0 L3,1.5 L0,3 z" fill="#10b981" />
                                    </marker>
                                    <marker id="miniArrowZ" markerWidth="3" markerHeight="3" refX="2.5" refY="1.5" orient="auto">
                                        <path d="M0,0 L3,1.5 L0,3 z" fill="#6b7280" />
                                    </marker>
                                </defs>
                                <rect x="0" y="0" width="96" height="96" rx="6" fill="rgba(255,255,255,0.88)" stroke="rgba(2,6,23,0.06)" />
                                {viewMode === 'top' ? (
                                    // top view: simple X (red) to right, Y (green) up
                                    <g transform="translate(16,72)">
                                        <line x1="0" y1="0" x2="40" y2="0" stroke="#ef4444" strokeWidth="1" markerEnd="url(#miniArrowX)" />
                                        <text x="44" y="4" fontSize="9" fill="#ef4444">X</text>
                                        <line x1="0" y1="0" x2="0" y2="-40" stroke="#10b981" strokeWidth="1" markerEnd="url(#miniArrowY)" />
                                        <text x="2" y="-44" fontSize="9" fill="#10b981">Y</text>
                                        <circle cx="0" cy="0" r="2.5" fill="#0f172a" />
                                    </g>
                                ) : (
                                    // 3d view: isometric corner: X (red) right-down, Y (green) left-down, Z up-left
                                    <g transform="translate(48,48)">
                                        {/* X axis */}
                                        <line x1="0" y1="0" x2="28" y2="8" stroke="#ef4444" strokeWidth="1.2" markerEnd="url(#miniArrowX)" />
                                        <text x="30" y="12" fontSize="8" fill="#ef4444">X</text>
                                        {/* Y axis */}
                                        <line x1="0" y1="0" x2="-20" y2="12" stroke="#10b981" strokeWidth="1.2" markerEnd="url(#miniArrowY)" />
                                        <text x="-30" y="18" fontSize="8" fill="#10b981">Y</text>
                                        {/* Z axis */}
                                        <line x1="0" y1="0" x2="-6" y2="-28" stroke="#6b7280" strokeWidth="1.2" markerEnd="url(#miniArrowZ)" />
                                        <text x="-10" y="-34" fontSize="8" fill="#6b7280">Z</text>
                                        <circle cx="0" cy="0" r="2.5" fill="#0f172a" />
                                        {/* tiny plane surface */}
                                        <polygon points="6,2 28,10 22,18 2,10" fill="rgba(148,163,184,0.18)" stroke="rgba(2,6,23,0.06)" />
                                    </g>
                                )}
                            </svg>
                        </div>

                        {/* Fixed Auto Design overlay (does not scale with SVG zoom) */}
                        {schemes && schemes.length > 0 && !autoPanelHidden && (
                            <div
                                style={{
                                    position: 'absolute',
                                    zIndex: 30,
                                    pointerEvents: 'auto',
                                    ...(autoPanelCorner === 'tr' ? { top: 8, right: 8 } : {}),
                                    ...(autoPanelCorner === 'br' ? { bottom: 8, right: 8 } : {}),
                                    ...(autoPanelCorner === 'tl' ? { top: 8, left: 8 } : {}),
                                    ...(autoPanelCorner === 'bl' ? { bottom: 8, left: 8 } : {}),
                                }}
                                onClick={(e) => e.stopPropagation()}
                                onMouseDown={(e) => e.stopPropagation()}
                                onMouseUp={(e) => e.stopPropagation()}
                                onWheel={(e) => e.stopPropagation()}
                                onPointerDown={(e) => e.stopPropagation()}
                                onPointerUp={(e) => e.stopPropagation()}
                            >
                                {!autoPanelOpen ? (
                                    <div
                                        style={{
                                            background: 'rgba(15,23,42,0.88)',
                                            color: '#e5e7eb',
                                            borderRadius: 16,
                                            padding: '6px 10px',
                                            fontSize: 12,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'space-between',
                                            gap: 8,
                                            height: 32,
                                            minWidth: 140,
                                            cursor: 'pointer',
                                            boxShadow: '0 2px 8px rgba(0,0,0,0.25)'
                                        }}
                                        title="Show Auto Designs"
                                        onClick={() => setAutoPanelOpen(true)}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <span style={{ width: 10, height: 10, background: schemes[0]?.color || '#64748b', borderRadius: 3, display: 'inline-block' }} />
                                            <span>Auto ({schemes.length})</span>
                                        </div>
                                        <span style={{ opacity: 0.9 }}>▾</span>
                                    </div>
                                ) : (
                                    <div
                                        style={{
                                            background: 'rgba(15,23,42,0.92)',
                                            color: '#e5e7eb',
                                            borderRadius: 10,
                                            padding: 8,
                                            fontSize: 12,
                                            width: 420,
                                            maxHeight: '40vh',
                                            minHeight: 140,
                                            display: 'flex',
                                            flexDirection: 'column',
                                            boxShadow: '0 2px 10px rgba(0,0,0,0.3)'
                                        }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                                            <div style={{ fontWeight: 600 }}>Auto Designs</div>
                                            {/* Section toggles for organized parameters */}
                                            <div className="mt-2 flex flex-wrap gap-2">
                                                <button title="Cycle panel corner" onClick={cycleAutoPanelCorner} className="px-2 py-1 text-xs rounded border bg-slate-700 text-slate-200">Move Panel</button>
                                            </div>
                                            <div style={{ display: 'flex', gap: 6 }}>
                                                <button onClick={() => cycleAutoPanelCorner()} style={{ padding: '2px 6px', fontSize: 11, background: 'transparent', color: '#e5e7eb', border: '1px solid #475569', borderRadius: 4 }}>Move</button>
                                                <button onClick={() => setAutoPanelOpen(false)} style={{ padding: '2px 6px', fontSize: 11, background: 'transparent', color: '#e5e7eb', border: '1px solid #475569', borderRadius: 4 }}>Minimize</button>
                                                <button onClick={() => setAutoPanelHidden(true)} style={{ padding: '2px 6px', fontSize: 11, background: 'transparent', color: '#e5e7eb', border: '1px solid #475569', borderRadius: 4 }}>Hide</button>
                                            </div>
                                        </div>
                                        {/* Active preset preview pill */}
                                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                                            <span style={{ padding: '2px 6px', borderRadius: 8, background: '#1f2937', border: '1px solid #374151' }} title="Optimize priority">
                                                Priority: {designPriority ? String(designPriority) : 'Default'}
                                            </span>
                                            <span style={{ padding: '2px 6px', borderRadius: 8, background: '#1f2937', border: '1px solid #374151' }} title="Circulation mode">
                                                Circulation: {circulationMode}
                                            </span>
                                            {avoidDeadEnds ? (
                                                <span style={{ padding: '2px 6px', borderRadius: 8, background: '#1f2937', border: '1px solid #374151' }} title="Dead-end avoidance">
                                                    Avoid Dead-ends
                                                </span>
                                            ) : null}
                                            {separateEntryExit ? (
                                                <span style={{ padding: '2px 6px', borderRadius: 8, background: '#1f2937', border: '1px solid #374151' }} title="Separate entry/exit">
                                                    Separate Entry/Exit
                                                </span>
                                            ) : null}
                                        </div>
                                        <div style={{ overflowY: 'auto' }}>
                                            {schemes.map((s) => (
                                                <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '160px 1fr auto', alignItems: 'center', columnGap: 12, rowGap: 4, padding: '2px 0' }}>
                                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', opacity: s.visible ? 1 : 0.8 }} onClick={() => setActiveScheme(s.id)} title="Preview this layout">
                                                        <span style={{ width: 10, height: 10, background: s.color, borderRadius: 3, display: 'inline-block' }} />
                                                        <span style={{ width: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name || s.id}{s.visible ? ' •' : ''}</span>
                                                    </div>
                                                    <div style={{ opacity: 0.9, fontSize: 11, display: 'flex', alignItems: 'center', gap: 10 }}>
                                                        <span>St {s.counts?.stalls || 0}</span>
                                                        <span>Ai {s.counts?.aisles || 0}</span>
                                                        <span>Sc {s.counts?.score?.toFixed ? s.counts.score.toFixed(0) : s.counts?.score}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', gap: 6, justifyContent: 'end' }}>
                                                        <button onClick={() => setActiveScheme(s.id)} style={{ padding: '2px 8px', fontSize: 11, background: 'transparent', color: '#e5e7eb', border: '1px solid #475569', borderRadius: 4 }}>Preview</button>
                                                        <button onClick={() => applyScheme(s.id)} style={{ padding: '2px 8px', fontSize: 11, background: '#0ea5e9', color: '#fff', borderRadius: 4, border: '1px solid #0369a1' }}>Apply</button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Revert grouping: Layout */}
                    <div className="mt-3 flex items-start justify-between gap-3 flex-wrap">
                        {/* Left actions moved into Drawing Tools card */}

                        {/* Right: Drawing Tools card (includes measuring toggles) */}
                        <div className="w-full">
                            <div className="text-sm font-semibold text-slate-900 bg-white px-3 py-1 rounded border border-slate-300 shadow-sm" style={{ letterSpacing: '0.2px' }}>Drawing Tools</div>
                            <div className="mt-2 p-3 rounded border border-slate-300 bg-white shadow-sm w-full">
                                <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                                    <button onClick={() => { setOneShotMeasureActive(true); setOneShotMeasureTempAnn(null); setMeasurePoints([]); }} style={{ padding: '6px 10px', fontSize: 12, background: '#0ea5e9', color: '#fff', borderRadius: 6, border: '1px solid #0369a1' }}>Quick Measure</button>
                                    <div style={{ alignSelf: 'center', color: '#475569', fontSize: 13 }}>or toggle Measure for persistent annotations</div>
                                </div>
                                <DrawingToolkit showHeader={false}
                                    onClosePolygon={closePolygon}
                                    onResetDrawing={resetDrawing}
                                    onToggleMeasure={() => setMode(m => (m === 'measure' ? 'draw' : 'measure'))}
                                    onClearDims={() => { setMeasureAnnotations([]); try { pushHistoryFrom(points, closed, []); } catch (e) { } }}
                                    mode={mode}
                                    setMode={setMode}
                                    rectToolWidthMeters={rectToolWidthMeters}
                                    setRectToolWidthMeters={setRectToolWidthMeters}
                                    rectToolHeightMeters={rectToolHeightMeters}
                                    setRectToolHeightMeters={setRectToolHeightMeters}
                                    rectToolAngleDeg={rectToolAngleDeg}
                                    setRectToolAngleDeg={setRectToolAngleDeg}
                                    rectToolCenter={rectToolCenter}
                                    setRectToolCenter={setRectToolCenter}
                                    onInsertRectangle={insertRectangleFromTool}
                                    viewBox={viewBox}
                                    snapToGrid={snapToGrid}
                                    setSnapToGrid={setSnapToGrid}
                                    gridSize={gridSize}
                                    setGridSize={setGridSize}
                                    snapMeasure={snapMeasure}
                                    setSnapMeasure={setSnapMeasure}
                                    showDimensions={showDimensions}
                                    setShowDimensions={setShowDimensions}
                                    unitSystem={unitSystem}
                                    metersToFeet={metersToFeet}
                                    feetToMeters={feetToMeters}
                                />
                            </div>
                        </div>
                    </div>
                    {/* Visual separator */}
                    <div className="border-t border-slate-600 my-3" />
                    {/* Grouped: Circulation */}
                    <div className="mt-2 flex flex-col gap-2">
                        <div className="text-sm font-semibold text-slate-900 bg-white px-3 py-1 rounded border border-slate-300 shadow-sm" style={{ letterSpacing: '0.2px' }}>Circulation</div>
                        {/* Parking Type selector and type-specific parameters */}
                        <div className="mt-2 p-3 rounded border border-slate-300 bg-white shadow-sm">
                            <div className="flex items-center gap-3 mb-2">
                                <div className="text-xs font-semibold text-slate-700">Parking Type</div>
                                <select value={codeDesign} onChange={e => { setCodeDesign(e.target.value); autoDesignGenerateDebounced(0); }} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="surface">Surface</option>
                                    <option value="underground">Underground</option>
                                </select>
                                <div className="text-xs text-slate-500 ml-3">Choose surface or structured underground presets</div>
                            </div>
                            <div className="flex items-center gap-3 mb-2">
                                <div className="text-xs font-semibold text-slate-700">Building Code</div>
                                <select value={parkingCode} onChange={e => { setParkingCode(e.target.value); autoDesignGenerateDebounced(0); }} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    {getAvailableParkingCodes().map(c => (
                                        <option key={c.code} value={c.code}>{c.label}</option>
                                    ))}
                                </select>
                                <div className="text-xs text-slate-500 ml-3">Circulation and stall dimensions per code</div>
                            </div>

                            {codeDesign === 'surface' && (
                                <div className="flex flex-wrap gap-3 text-xs">
                                    <label>Surface levels <input type="number" min={1} value={surfaceLevels} onChange={e => setSurfaceLevels(Number(e.target.value) || 1)} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                                    <label>Perimeter stalls <input type="checkbox" checked={surfacePerimeterStalls} onChange={e => setSurfacePerimeterStalls(e.target.checked)} className="ml-1" /></label>
                                    <label>Landscape buffer ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" value={unitSystem === 'imperial' ? metersToFeet(landscapeBufferMeters) : landscapeBufferMeters} onChange={e => setLandscapeBufferMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-24 rounded border px-1 py-0.5" /></label>
                                    <label>EV stalls (%) <input type="number" min={0} max={100} value={evStallPercent} onChange={e => setEvStallPercent(Number(e.target.value) || 0)} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                                </div>
                            )}

                            {codeDesign === 'underground' && (
                                <div className="flex flex-wrap gap-3 text-xs">
                                    <label>Underground levels <input type="number" min={1} value={undergroundLevels} onChange={e => setUndergroundLevels(Number(e.target.value) || 1)} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                                    <label>Column spacing ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" value={unitSystem === 'imperial' ? metersToFeet(undergroundColumnSpacingMeters) : undergroundColumnSpacingMeters} onChange={e => setUndergroundColumnSpacingMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-24 rounded border px-1 py-0.5" /></label>
                                    <label>Enforce orthogonal layout <input type="checkbox" checked={enforceOrthogonalLayout} onChange={e => setEnforceOrthogonalLayout(e.target.checked)} className="ml-1" /></label>
                                </div>
                            )}
                        </div>
                        {/* Designer Decision: Optimize For */}
                        <div className="mt-1 flex flex-wrap gap-2">
                            <span className="text-[12px] text-slate-600 mr-2">Optimize for:</span>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="Maximize stall count and reduce conflicts" onClick={() => { setDesignPriority('capacity'); autoDesignGenerateDebounced(0); }}>Capacity</button>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="Gentle ramps, wider aisles, fewer tight turns" onClick={() => { setDesignPriority('comfort'); autoDesignGenerateDebounced(0); }}>Comfort</button>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="Loop continuity and minimal dead-ends" onClick={() => { setDesignPriority('flow'); autoDesignGenerateDebounced(0); }}>Flow</button>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="Short walk to cores and exits" onClick={() => { setDesignPriority('accessibility'); autoDesignGenerateDebounced(0); }}>Accessibility</button>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="Simpler spans and shorter streets" onClick={() => { setDesignPriority('cost'); autoDesignGenerateDebounced(0); }}>Cost</button>
                            <button type="button" className="px-2 py-1 rounded border bg-white text-slate-800 text-xs" title="EV readiness and sensor-friendly loops" onClick={() => { setDesignPriority('future'); autoDesignGenerateDebounced(0); }}>Future-Ready</button>
                        </div>
                        <div className="text-[12px] text-slate-600 mt-1">Configure aisle and street behavior, widths, and connector continuity.</div>
                        <div className="flex gap-2 flex-wrap p-3 rounded border border-slate-300 bg-white shadow-sm">
                            <button onClick={() => { generateAisleFirstLayout(); setMode('stalls'); }} className="px-3 py-1 rounded-md bg-sky-600 text-white">Aisle-first Layout</button>
                            <label className="ml-2 text-xs" title="Automatically connect aisles to improve circulation">Auto-connect aisles <input type="checkbox" checked={autoConnectAisles} onChange={e => setAutoConnectAisles(e.target.checked)} className="ml-1" /></label>
                            <label className="ml-2 text-xs" title="Extra clearance added around aisle bands for column avoidance">Aisle column gap ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" value={unitSystem === 'imperial' ? metersToFeet(aisleColumnGapMeters) : aisleColumnGapMeters} onChange={e => setAisleColumnGapMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs" title="Override two-way drive width (defaults to code preset)">Drive width ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" value={driveWidthMeters == null ? '' : (unitSystem === 'imperial' ? metersToFeet(driveWidthMeters) : driveWidthMeters)} placeholder="auto" onChange={e => setDriveWidthMeters(e.target.value === '' ? null : (unitSystem === 'imperial' ? feetToMeters(Number(e.target.value)) : Number(e.target.value)))} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs" title="Sets aisle width from circulation type">Aisle type
                                <select value={aisleType} onChange={e => setAisleType(e.target.value)} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="two-way">Two-way</option>
                                    <option value="one-way">One-way</option>
                                </select>
                            </label>
                            <label className="ml-2 text-xs" title="Perimeter or spine street width by circulation type">Street type
                                <select value={streetType} onChange={e => setStreetType(e.target.value)} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="two-way">Two-way</option>
                                    <option value="one-way">One-way</option>
                                    <option value="spine">Spine</option>
                                </select>
                            </label>
                            {/* Circulation Presets */}
                            <div className="w-full" />
                            <div className="text-xs text-slate-700">Circulation Presets</div>
                            <label className="ml-2 text-xs" title="Overall circulation strategy">
                                Mode
                                <select value={circulationMode} onChange={e => { setCirculationMode(e.target.value); autoDesignGenerateDebounced(0); }} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="loop">Loop</option>
                                    <option value="spine">Spine</option>
                                    <option value="grid">Grid</option>
                                </select>
                            </label>
                            <label className="ml-2 text-xs" title="Bay arrangement relative to aisles">
                                Bay orientation
                                <select value={bayOrientation} onChange={e => { setBayOrientation(e.target.value); autoDesignGenerateDebounced(0); }} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="double-loaded">Double-loaded</option>
                                    <option value="single-loaded">Single-loaded</option>
                                </select>
                            </label>
                            <label className="ml-2 text-xs" title="Discourage isolated cul-de-sacs">
                                Avoid dead-ends <input type="checkbox" checked={avoidDeadEnds} onChange={e => { setAvoidDeadEnds(e.target.checked); autoDesignGenerateDebounced(0); }} className="ml-1" />
                            </label>
                            <label className="ml-2 text-xs" title="Prefer distinct ingress/egress bands">
                                Separate entry / exit <input type="checkbox" checked={separateEntryExit} onChange={e => { setSeparateEntryExit(e.target.checked); autoDesignGenerateDebounced(0); }} className="ml-1" />
                            </label>
                            {/* Perimeter street and connector controls */}
                            <label className="ml-2 text-xs" title="Toggle perimeter streets along long edges">Enable perimeter street <input type="checkbox" checked={perimeterStreetEnabled} onChange={e => setPerimeterStreetEnabled(e.target.checked)} className="ml-1" /></label>
                            <label className="ml-2 text-xs" title="Inset distance from polygon edge">Street offset ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" step="0.1" value={unitSystem === 'imperial' ? metersToFeet(perimeterStreetOffsetMeters) : perimeterStreetOffsetMeters} onChange={e => setPerimeterStreetOffsetMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-16 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs" title="When set to 0, uses Min connectors evenly spaced">Connector spacing ({unitSystem === 'metric' ? 'm' : 'ft'}, 0 = use Min) <input type="number" step="0.5" value={unitSystem === 'imperial' ? metersToFeet(connectorSpacingMeters) : connectorSpacingMeters} onChange={e => setConnectorSpacingMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-24 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs">Turning radius ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" step="0.5" value={unitSystem === 'imperial' ? metersToFeet(minTurningRadiusMeters) : minTurningRadiusMeters} onChange={e => setMinTurningRadiusMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs">Span tolerance ({unitSystem === 'metric' ? 'm' : 'ft'}) <input type="number" step="0.1" value={unitSystem === 'imperial' ? metersToFeet(spanToleranceMeters) : spanToleranceMeters} onChange={e => setSpanToleranceMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-20 rounded border px-1 py-0.5" /></label>
                            <label className="ml-2 text-xs" title="Select preferred access zone location">Access placement
                                <select value={accessPlacement} onChange={e => setAccessPlacement(e.target.value)} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="auto">Auto</option>
                                    <option value="min-edge">Min edge</option>
                                    <option value="max-edge">Max edge</option>
                                    <option value="center">Center</option>
                                </select>
                            </label>
                            <label className="ml-2 text-xs" title="Place ramp near min edge, center, or max edge">Ramp placement
                                <select value={rampPlacement} onChange={e => setRampPlacement(e.target.value)} className="ml-1 rounded border px-1 py-0.5 text-xs">
                                    <option value="edge-min">Edge min</option>
                                    <option value="edge-max">Edge max</option>
                                    <option value="center">Center</option>
                                </select>
                            </label>
                            {/* Visual separator */}
                            <div className="border-t border-slate-600 w-full my-2" />
                            {/* Ramps: sizing from heights and slope */}
                            <div className="text-sm font-semibold text-slate-900 bg-white px-3 py-1 rounded border border-slate-300 shadow-sm w-full" style={{ letterSpacing: '0.2px' }}>Ramps</div>
                            <div className="text-[12px] text-slate-600 w-full mt-1">Set ramp placement and derive length from height and max slope.</div>
                            <label className="ml-2 text-xs" title="Vertical rise from grade to this parking level">Entry rise ({unitSystem === 'metric' ? 'm' : 'ft'})
                                <input type="number" step="0.1" value={unitSystem === 'imperial' ? metersToFeet(entryHeightMeters) : entryHeightMeters} onChange={e => setEntryHeightMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-20 rounded border px-1 py-0.5" />
                            </label>
                            <label className="ml-2 text-xs" title="Typical level-to-level height used for internal ramp sizing">Level height ({unitSystem === 'metric' ? 'm' : 'ft'})
                                <input type="number" step="0.1" value={unitSystem === 'imperial' ? metersToFeet(levelHeightMeters) : levelHeightMeters} onChange={e => setLevelHeightMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} className="ml-1 w-20 rounded border px-1 py-0.5" />
                            </label>
                            <label className="ml-2 text-xs" title="Maximum slope allowed for external access ramp">Access slope (%)
                                <input type="number" step="0.5" value={accessRampMaxSlopePercent} onChange={e => setAccessRampMaxSlopePercent(Number(e.target.value) || 0)} className="ml-1 w-20 rounded border px-1 py-0.5" />
                            </label>
                            <label className="ml-2 text-xs" title="Maximum slope allowed for internal level-to-level ramp">Internal slope (%)
                                <input type="number" step="0.5" value={internalRampMaxSlopePercent} onChange={e => setInternalRampMaxSlopePercent(Number(e.target.value) || 0)} className="ml-1 w-20 rounded border px-1 py-0.5" />
                            </label>
                            <button onClick={() => setInsertionMode(m => m === 'core' ? null : 'core')} className={`px-3 py-1 rounded-md border text-xs ${insertionMode === 'core' ? 'bg-slate-700 text-white' : 'bg-white text-slate-700'}`}>Place core</button>
                            <label className="ml-2 text-xs">Central spine <input type="checkbox" checked={addCentralSpine} onChange={e => setAddCentralSpine(e.target.checked)} className="ml-1" /></label>
                            {/* Visual separator */}
                            <div className="border-t border-slate-600 w-full my-2" />
                            {/* Advanced: collapsible */}
                            <details className="mt-2 w-full">
                                <summary className="text-sm font-semibold text-slate-900 bg-white px-3 py-1 rounded border border-slate-300 shadow-sm cursor-pointer select-none" style={{ letterSpacing: '0.2px' }}>Advanced Parameters</summary>
                                <div className="mt-2 flex gap-2 flex-wrap p-3 rounded border border-slate-300 bg-white shadow-sm">
                                    <label className="ml-2 text-xs" title="Candidate axis angle offsets to explore">Angles (deg, comma-separated)
                                        <input type="text" placeholder="0,12,-12,24,-24" className="ml-1 w-32 rounded border px-1 py-0.5" value={(anglesDegInput ?? '')}
                                            onChange={e => setAnglesDegInput(e.target.value)} />
                                    </label>
                                    <label className="ml-2 text-xs" title="Stall angles to try for baseline schemes">Stall angles (deg, comma-separated)
                                        <input type="text" placeholder="90,60" className="ml-1 w-24 rounded border px-1 py-0.5" value={(stallAnglesInput ?? '')}
                                            onChange={e => setStallAnglesInput(e.target.value)} />
                                    </label>
                                    <label className="ml-2 text-xs" title="Override structural span presets (meters)">Span presets (m, comma-separated)
                                        <input type="text" placeholder="7.0,7.5,8.0" className="ml-1 w-32 rounded border px-1 py-0.5" value={(spanPresetsInput ?? '')}
                                            onChange={e => setSpanPresetsInput(e.target.value)} />
                                    </label>
                                </div>
                            </details>
                        </div>
                    </div>
                    {/* Column spacing controls (drive structural grid) */}
                    {/* Revert grouping: Structure */}
                    <label className="ml-2 text-xs">Column spacing X (m)
                        <input
                            type="number"
                            value={columnGridParams && columnGridParams.spacingX ? (columnGridParams.spacingX / Math.max(1, Number(unitsPerMeter || 1))) : ''}
                            placeholder="auto"
                            onChange={e => {
                                const val = e.target.value === '' ? null : Number(e.target.value);
                                setColumnGridParams(prev => {
                                    if (val === null) return prev ? { ...prev, spacingX: undefined } : prev;
                                    const spacingUnits = Math.max(0.001, val) * Math.max(1, Number(unitsPerMeter || 1));
                                    const angle = (prev && typeof prev.angle === 'number') ? prev.angle : Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
                                    return { ...(prev || {}), spacingX: spacingUnits, angle, gridId: (prev?.gridId || 'G1') };
                                });
                                setShowColumnGrid(true);
                            }}
                            className="ml-1 w-24 rounded border px-1 py-0.5"
                        />
                    </label>
                    <label className="ml-2 text-xs">Column spacing Y (m)
                        <input
                            type="number"
                            value={columnGridParams && columnGridParams.spacingY ? (columnGridParams.spacingY / Math.max(1, Number(unitsPerMeter || 1))) : ''}
                            placeholder="auto"
                            onChange={e => {
                                const val = e.target.value === '' ? null : Number(e.target.value);
                                setColumnGridParams(prev => {
                                    if (val === null) return prev ? { ...prev, spacingY: undefined } : prev;
                                    const spacingUnits = Math.max(0.001, val) * Math.max(1, Number(unitsPerMeter || 1));
                                    const angle = (prev && typeof prev.angle === 'number') ? prev.angle : Math.atan2(cplaneXDir?.y || 0, cplaneXDir?.x || 1);
                                    return { ...(prev || {}), spacingY: spacingUnits, angle, gridId: (prev?.gridId || 'G1') };
                                });
                                setShowColumnGrid(true);
                            }}
                            className="ml-1 w-24 rounded border px-1 py-0.5"
                        />
                    </label>
                    <label className="ml-2 text-xs">Row spacing (Y, m) <input type="number" value={rowSpacingMeters ?? ''} placeholder="auto" onChange={e => setRowSpacingMeters(e.target.value === '' ? null : Number(e.target.value))} className="ml-1 w-24 rounded border px-1 py-0.5" /></label>
                    {/* end Structure */}
                    {/* Stall spacing override removed: X spacing derives from stall footprint + gap */}
                    {/* Revert grouping: Generation */}
                    <button onClick={() => validateLayout()} className="px-3 py-1 rounded-md border bg-white text-slate-900">Validate layout</button>
                    <button onClick={() => generateColumns()} className="px-3 py-1 rounded-md border bg-white text-slate-900">Generate Columns</button>
                    <button
                        onClick={() => {
                            // Hide debug for clarity, then wait for columns to commit before running aisles
                            setShowColumnDebug(false);
                            // Ensure perimeter streets/connectors are enabled for full circulation
                            setPerimeterStreetEnabled(true);
                            // Align connector spacing to grid spacing when available
                            try {
                                const sx = columnGridParams?.spacingX ? (columnGridParams.spacingX / Math.max(1, Number(unitsPerMeter || 1))) : null;
                                if (sx && Number.isFinite(sx)) setConnectorSpacingMeters(Math.max(2, sx));
                            } catch { }
                            const countColumns = () => {
                                try {
                                    const arr = (levels[currentLevelIndex]?.stallsPreview || []);
                                    return arr.filter(f => f && f.type === 'column').length;
                                } catch { return 0; }
                            };
                            const before = countColumns();
                            generateColumns();
                            const start = Date.now();
                            const waitAndRun = () => {
                                const after = countColumns();
                                if (after > before || (Date.now() - start) > 600) {
                                    generateAisleFirstLayout();
                                } else {
                                    setTimeout(waitAndRun, 16);
                                }
                            };
                            setTimeout(waitAndRun, 16);
                        }}
                        className="px-3 py-1 rounded-md bg-slate-900 text-white"
                        title="Structural-first: generate columns, then aisles"
                    >
                        Apply Grid → Columns → Aisles
                    </button>
                    {/* end Generation */}
                    {/* Revert grouping: Columns */}
                    <label className="text-sm flex items-center gap-2">
                        <span className="text-xs">Grid angle</span>
                        <input type="number" step="1" value={columnGridAngleDeg === null ? '' : columnGridAngleDeg} placeholder="auto" onChange={e => {
                            const v = e.target.value;
                            if (v === '') { setColumnGridAngleDeg(null); } else { setColumnGridAngleDeg(Number(v)); }
                        }} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm w-16" />
                    </label>
                    <button onClick={() => { setColumnGridAngleDeg(null); }} className="px-2 py-1 rounded-md border bg-white text-slate-700 text-sm" title="Reset grid angle to CPlane">Reset angle</button>
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={columnsRespectExisting} onChange={e => setColumnsRespectExisting(e.target.checked)} />
                        <span className="text-xs">Avoid existing features</span>
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={columnsLocked} onChange={e => setColumnsLocked(e.target.checked)} />
                        <span className="text-xs">Lock columns</span>
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={showColumnGrid} onChange={e => setShowColumnGrid(e.target.checked)} />
                        <span className="text-xs">Show column grid</span>
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={manualGridEnabled} onChange={e => setManualGridEnabled(e.target.checked)} />
                        <span className="text-xs">Manual grid</span>
                    </label>
                    {manualGridEnabled && (
                        <>
                            <label className="text-sm flex items-center gap-2">
                                <span className="text-xs">Grid X (m)</span>
                                <input type="number" step="0.1" min="0.1" value={manualGridSpacingX} onChange={e => setManualGridSpacingX(Number(e.target.value))} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm w-20" />
                            </label>
                            <label className="text-sm flex items-center gap-2">
                                <span className="text-xs">Grid Y (m)</span>
                                <input type="number" step="0.1" min="0.1" value={manualGridSpacingY} onChange={e => setManualGridSpacingY(Number(e.target.value))} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm w-20" />
                            </label>
                        </>
                    )}
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={showColumnDebug} onChange={e => setShowColumnDebug(e.target.checked)} />
                        <span className="text-xs">Show column debug</span>
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <span className="text-xs">Column size (m)</span>
                        <input type="number" step="0.05" min="0.05" value={columnSizeMeters} onChange={e => setColumnSizeMeters(Number(e.target.value))} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm w-20" />
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <span className="text-xs">Clearance (m)</span>
                        <input type="number" step="0.05" min="0" value={columnClearanceMeters} onChange={e => setColumnClearanceMeters(Number(e.target.value))} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm w-20" />
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <span className="text-xs">Shape</span>
                        <select value={columnShape} onChange={e => setColumnShape(e.target.value)} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm">
                            <option value="square">Square</option>
                            <option value="circle">Circle</option>
                            <option value="template">Custom template</option>
                        </select>
                    </label>
                    <label className="text-sm flex items-center gap-2">
                        <button onClick={() => fileInputRef.current && fileInputRef.current.click()} className="px-2 py-1 rounded-md border bg-white text-slate-700 text-sm">Load column template</button>
                        <input ref={fileInputRef} type="file" accept=".geojson,.json,.svg" style={{ display: 'none' }} onChange={(e) => handleTemplateUpload(e)} />
                        <span className="text-xs text-slate-500">{columnTemplate ? columnTemplate.name : ''}</span>
                    </label>
                    {/* end Columns */}
                    {/* Revert grouping: Stalls */}
                    <label className="text-sm flex items-center gap-2">
                        <span className="text-xs">Stall angle</span>
                        <select value={stallAngleDeg} onChange={e => setStallAngleDeg(Number(e.target.value))} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm">
                            <option value={0}>0°</option>
                            <option value={45}>45°</option>
                            <option value={60}>60°</option>
                        </select>
                    </label>
                    {/* Insert buttons temporarily removed per request */}
                    <label className="text-sm flex items-center gap-2">
                        <input type="checkbox" checked={minimalMarkers} onChange={e => setMinimalMarkers(e.target.checked)} />
                        <span className="text-xs">Minimal markers</span>
                    </label>
                    <button onClick={deleteSelectedStalls} className="px-3 py-1 rounded-md border bg-white text-red-600">Delete selected stalls</button>
                    <button onClick={clearStallsOnLevel} className="px-3 py-1 rounded-md border bg-white text-slate-700">Clear stalls (level)</button>
                    {/* end Stalls */}
                    {/* Revert grouping: CPlane & View */}
                    <div className="flex items-center gap-2 border rounded-md px-2 py-1 bg-white">
                        <label className="text-xs">CPlane <input type="checkbox" checked={cplaneVisible} onChange={e => setCplaneVisible(e.target.checked)} className="ml-1" /></label>
                        <button title="Set CPlane origin (click canvas)" onClick={() => setCplaneMode('setOrigin')} className={`px-2 py-1 rounded-md border bg-white text-slate-700 text-sm ${cplaneMode === 'setOrigin' ? 'ring-2 ring-slate-300' : ''}`}>Set origin</button>
                        <button title="Set CPlane X direction (click canvas)" onClick={() => setCplaneMode('setXDir')} className={`px-2 py-1 rounded-md border bg-white text-slate-700 text-sm ${cplaneMode === 'setXDir' ? 'ring-2 ring-slate-300' : ''}`}>Set X dir</button>
                        <button title="Reset CPlane" onClick={() => { setCplaneOrigin({ x: 0, y: 0 }); setCplaneXDir({ x: 1, y: 0 }); setCplaneMode(null); }} className="px-2 py-1 rounded-md border bg-white text-slate-700 text-sm">Reset</button>
                        <div className="text-xs text-slate-600">Origin: {cplaneOrigin.x.toFixed(1)}, {cplaneOrigin.y.toFixed(1)}</div>
                        <div className="text-xs text-slate-600">Xθ: {(Math.atan2(cplaneXDir.y, cplaneXDir.x) * 180 / Math.PI).toFixed(1)}°</div>
                        <div className="h-0.5 bg-slate-100 w-px mx-1" />
                        <label className="text-xs">View:</label>
                        <select value={viewMode} onChange={e => setViewMode(e.target.value)} className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm">
                            <option value="top">Top</option>
                            <option value="3d">3D</option>
                        </select>
                    </div>
                    {/* end CPlane & View */}
                    {/* clipping diagnostics & acceptance control */}
                    {/* Revert grouping: Validation */}
                    <div className="ml-2 flex items-center gap-3">
                        <label className="text-sm">Clip accept</label>
                        <input type="range" min="0" max="1" step="0.01" value={clipAcceptance} onChange={e => setClipAcceptance(Number(e.target.value))} />
                        <div className="text-sm text-slate-700">{Math.round(clipAcceptance * 100)}%</div>
                        <label className="text-xs">Show clip diagnostics <input type="checkbox" checked={showClipDiagnostics} onChange={e => setShowClipDiagnostics(e.target.checked)} className="ml-1" /></label>
                        <button onClick={() => setClipDiagnostics([])} className="px-2 py-1 rounded-md border bg-white text-sm">Clear diagnostics</button>
                    </div>
                    {clipDiagnostics && clipDiagnostics.length > 0 && (
                        <div className="ml-2 mt-2 p-2 border rounded bg-white" style={{ maxHeight: 140, overflow: 'auto' }}>
                            <div className="text-xs font-medium">Rejected clipped fragments: {clipDiagnostics.length}</div>
                            {clipDiagnostics.slice(0, 10).map((d, i) => (
                                <div key={i} className="text-xs">{i + 1}: {(d.ratio * 100).toFixed(1)}%</div>
                            ))}
                            <div className="mt-1 text-xs text-slate-600">Tip: Lower the <strong>Clip accept</strong> slider to allow more partial stalls, or use <strong>Aisle-first Layout</strong> for continuous aisles and full stalls.</div>
                        </div>
                    )}
                    {/* end Validation */}
                    {columnGrids && columnGrids.length > 0 && (
                        <div className="ml-2 mt-2 p-2 border rounded bg-white" style={{ maxHeight: 160, overflow: 'auto' }}>
                            <div className="text-xs font-medium mb-1">Column grids: {columnGrids.length}</div>
                            {columnGrids.map(g => (
                                <div key={g.id} className="flex items-center gap-2 text-xs mb-1">
                                    <span className="font-mono">{g.id}</span>
                                    <span>{(g.params.spacingX / Number(unitsPerMeter || 1)).toFixed(2)}m</span>
                                    <span>θ {(g.params.angle * 180 / Math.PI).toFixed(1)}°</span>
                                    <label className="flex items-center gap-1">
                                        <input type="checkbox" checked={g.visible} onChange={e => {
                                            const vis = e.target.checked;
                                            setColumnGrids(prev => prev.map(pg => pg.id === g.id ? { ...pg, visible: vis } : pg));
                                            setLevels(prev => prev.map((l, i) => i === currentLevelIndex ? { ...l, stallsPreview: (l.stallsPreview || []).map(f => (f.type === 'column' && f.gridId === g.id) ? { ...f, hidden: !vis } : f) } : l));
                                        }} />
                                        <span>show</span>
                                    </label>
                                    <button className="px-1 py-0.5 border rounded" title="Delete grid" onClick={() => {
                                        setColumnGrids(prev => prev.filter(pg => pg.id !== g.id));
                                        setLevels(prev => prev.map((l, i) => i === currentLevelIndex ? { ...l, stallsPreview: (l.stallsPreview || []).filter(f => !(f.type === 'column' && f.gridId === g.id)) } : l));
                                    }}>✕</button>
                                </div>
                            ))}
                        </div>
                    )}
                    {/* Revert grouping: Levels */}
                    {validateResults && validateResults.length > 0 && (
                        <div className="ml-2 mt-2 p-2 border rounded bg-white" style={{ maxHeight: 220, overflow: 'auto' }}>
                            <div className="text-sm font-medium">Validation results: {validateResults.length}</div>
                            {validateResults.map((r, i) => (
                                <div key={i} className="text-xs mt-1">
                                    <div><strong>{r.type}</strong>: {r.message}</div>
                                    <div className="text-xs text-slate-600">Suggestion: {r.suggestion}</div>
                                    {r.items && r.items.length > 0 && (
                                        <div className="mt-1">
                                            <button onClick={() => { if (r.type === 'overlap' || r.type === 'isolated' || r.type === 'outside') removeStallsByIndices(currentLevelIndex, Array.isArray(r.items[0]) ? r.items.flat() : r.items); }} className="px-2 py-1 text-xs rounded-md border bg-white text-red-600">Remove offending stalls</button>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                    <div className="ml-2 flex items-center gap-2">
                        <button title="Previous level" onClick={() => setCurrentLevelIndex(i => Math.max(0, i - 1))} className="px-2 py-1 rounded-md bg-white text-slate-700 border">◀</button>

                        <div className="flex items-center gap-2">
                            {editingLevelIdx === currentLevelIndex ? (
                                <input
                                    autoFocus
                                    value={editingLevelName}
                                    onChange={e => setEditingLevelName(e.target.value)}
                                    onBlur={() => {
                                        const idx = currentLevelIndex;
                                        const newName = String(editingLevelName || '').trim();
                                        if (newName.length === 0) { alert('Name cannot be empty'); return; }
                                        renameLevel(idx, newName);
                                        setEditingLevelIdx(null); setEditingLevelName('');
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') { e.preventDefault(); const idx = currentLevelIndex; const newName = String(editingLevelName || '').trim(); if (newName.length === 0) return alert('Name cannot be empty'); renameLevel(idx, newName); setEditingLevelIdx(null); setEditingLevelName(''); }
                                        else if (e.key === 'Escape') { e.preventDefault(); setEditingLevelIdx(null); setEditingLevelName(''); }
                                    }}
                                    className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm"
                                    style={{ minWidth: 160 }}
                                />
                            ) : (
                                <>
                                    <select
                                        value={currentLevelIndex}
                                        onChange={e => setCurrentLevelIndex(Number(e.target.value))}
                                        className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm"
                                        style={{ minWidth: 160 }}
                                        aria-label="Select level"
                                    >
                                        {levels.map((l, i) => {
                                            const elev = Number(l.elevation) || 0;
                                            const label = `${l.name} ${isFinite(elev) ? `(${elev.toFixed(1)} m)` : ''}`;
                                            return <option value={i} key={l.id}>{label}</option>;
                                        })}
                                    </select>

                                    <div className="flex items-center gap-1">
                                        <button title="Rename current level" onClick={() => { setEditingLevelIdx(currentLevelIndex); setEditingLevelName(levels[currentLevelIndex]?.name || ''); }} className="px-2 py-1 rounded-md bg-white text-slate-700 border">✎</button>

                                        {/* elevation display / inline editor */}
                                        {editingElevationIdx === currentLevelIndex ? (
                                            <input
                                                autoFocus
                                                type="number"
                                                step="0.1"
                                                value={editingElevationValue}
                                                onChange={e => setEditingElevationValue(e.target.value)}
                                                onBlur={() => commitLevelElevation(currentLevelIndex, editingElevationValue)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') { e.preventDefault(); commitLevelElevation(currentLevelIndex, editingElevationValue); }
                                                    else if (e.key === 'Escape') { e.preventDefault(); cancelEditElevation(); }
                                                }}
                                                className="px-2 py-1 rounded-md border bg-white text-slate-800 text-sm"
                                                style={{ width: 84 }}
                                                aria-label="Edit level elevation in meters"
                                            />
                                        ) : (
                                            <button title="Edit elevation" onClick={() => { setEditingElevationIdx(currentLevelIndex); setEditingElevationValue(String(Number(levels[currentLevelIndex]?.elevation) || 0)); }} className="px-2 py-1 rounded-md bg-white text-slate-700 border text-sm">{(Number(levels[currentLevelIndex]?.elevation) || 0).toFixed(1)} m</button>
                                        )}
                                    </div>
                                </>
                            )}
                        </div>

                        <button title="Next level" onClick={() => setCurrentLevelIndex(i => Math.min(levels.length - 1, i + 1))} className="px-2 py-1 rounded-md bg-white text-slate-700 border">▶</button>

                        <div className="flex items-center gap-1">
                            <button title="Add level" onClick={() => addLevel()} className="px-2 py-1 rounded-md bg-white text-slate-700 border">＋</button>
                            <button title="Add underground level" onClick={addUndergroundLevel} className="px-2 py-1 rounded-md bg-white text-slate-700 border">B＋</button>
                            <button title="Duplicate level" onClick={() => duplicateLevel(currentLevelIndex)} className="px-2 py-1 rounded-md bg-white text-slate-700 border">⎘</button>
                            <button title="Remove level" onClick={() => removeLevel(currentLevelIndex)} className="px-2 py-1 rounded-md bg-white text-red-600 border">✕</button>
                            {/* Elevation is editable inline via the level selector; remove duplicate 'elev' button */}
                        </div>
                    </div>
                    {/* end Levels */}
                    {/* Revert grouping: Export & History */}
                    <button onClick={exportSVG} className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100">Export SVG</button>
                    <button onClick={exportGeoJSON} className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100">Export GeoJSON</button>
                    <button onClick={undo} title="Undo (history)" aria-label="Undo history" className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100">↶</button>
                    <button onClick={redo} title="Redo (history)" aria-label="Redo history" className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100">↷</button>
                    {/* end Export & History */}
                </div>
                {/* Schemes & selection panel: use a solid, neutral card to ensure visibility over any backdrop */}
                <div style={{ marginTop: 12 }}>
                    <div style={{ position: 'relative' }}>
                        <div
                            role="region"
                            aria-label="Schemes and selection controls"
                            style={{
                                position: 'relative',
                                zIndex: 20,
                                backgroundColor: 'rgba(255,255,255,0.98)',
                                color: '#0f172a',
                                border: '1px solid rgba(15,23,42,0.06)',
                                boxShadow: '0 6px 18px rgba(2,6,23,0.08)',
                                padding: 12,
                                borderRadius: 8,
                            }}
                        >
                            <div className="flex items-center gap-2">
                                <input value={schemeName} onChange={e => setSchemeName(e.target.value)} placeholder="Scheme name (optional)" className="rounded border px-2 py-1 w-48 text-sm" />
                                <button onClick={saveScheme} className="px-3 py-1 rounded-md bg-slate-700 text-white">{editingSchemeId ? 'Update scheme' : 'Save scheme'}</button>
                                {editingSchemeId && (
                                    <button onClick={() => { setEditingSchemeId(null); setSchemeName(''); }} className="px-3 py-1 rounded-md border bg-white text-slate-700">Cancel edit</button>
                                )}
                                <button onClick={() => { setSchemes([]); localStorage.removeItem('parkcore_schemes_v1'); }} className="px-3 py-1 rounded-md border bg-white text-slate-700">Clear schemes</button>
                            </div>
                            {/* Column debug legend (top-left) */}
                            <div style={{ position: 'relative', marginTop: 8, marginBottom: 8, pointerEvents: 'none', zIndex: 1 }} aria-hidden>
                                <div style={{ background: 'rgba(255,255,255,0.98)', border: '1px solid rgba(2,6,23,0.06)', padding: 8, borderRadius: 6, fontSize: 12, color: '#0f172a', display: 'inline-block' }}>
                                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Legend</div>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <div style={{ width: 12, height: 12, background: 'rgba(34,197,94,0.95)', borderRadius: 8 }} />
                                        <div>Accepted center</div>
                                    </div>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <div style={{ width: 12, height: 12, background: 'rgba(249,115,22,0.95)', borderRadius: 8 }} />
                                        <div>Rejected (aisle / feature)</div>
                                    </div>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <div style={{ width: 12, height: 12, background: 'rgba(148,163,184,0.6)', borderRadius: 8 }} />
                                        <div>Outside lot</div>
                                    </div>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                        <div style={{ width: 12, height: 12, background: 'rgba(30,58,138,0.12)', border: '1px solid rgba(30,58,138,0.9)' }} />
                                        <div>Placed column footprint</div>
                                    </div>
                                </div>
                            </div>

                            {schemes.length > 0 && (
                                <div className="mt-3 space-y-2 text-sm">
                                    {schemes.map(s => (
                                        <div key={s.id} className="flex items-center gap-2">
                                            {/* neutral swatch to avoid bright, user-disliked colors */}
                                            <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid rgba(15,23,42,0.08)', background: '#eef2f6' }} />
                                            <strong className="text-sm text-slate-800">{s.name}</strong>
                                            <label className="text-xs ml-2">Visible <input type="checkbox" checked={!!s.visible} onChange={() => toggleSchemeVisibility(s.id)} className="ml-1" /></label>
                                            <button onClick={() => applyScheme(s.id)} title="Load scheme into editor" className="ml-2 px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm" style={{ opacity: 1, pointerEvents: 'auto' }}>Load</button>
                                            <button onClick={() => editScheme(s.id)} title="Edit scheme" className="ml-1 px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm" style={{ opacity: 1, pointerEvents: 'auto' }}>Edit</button>
                                            <button onClick={() => deleteScheme(s.id)} title="Delete scheme" className="ml-1 px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm" style={{ opacity: 1, pointerEvents: 'auto' }}>Delete</button>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <div className="mt-3 flex items-center gap-2">
                                <button onClick={selectAllPoints} title="Select all points" className="px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm">Select all</button>
                                <button onClick={clearSelection} title="Clear selection" className="px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm">Clear sel</button>
                                <button onClick={copySelection} title="Copy selection" className="px-3 py-1 rounded-md bg-slate-700 text-white shadow-sm text-sm">Copy</button>
                                <button onClick={pasteClipboard} title="Paste clipboard" className="px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm">Paste</button>
                                <button onClick={deleteSelectedPoints} title="Delete selected points" className="px-3 py-1 rounded-md bg-white text-slate-700 border shadow-sm text-sm">Delete sel</button>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="mt-2 text-xs text-slate-500">Tip: after closing the polygon the calculated area is copied into the Lot area field as an approximate plan area (units are treated as {unitSystem === 'metric' ? 'm²' : 'ft²'}).</div>
            </div>

            <div className="mt-6 flex gap-3">
                <button onClick={exportCSV} className="px-4 py-2 rounded-md bg-slate-900 text-white">Export CSV</button>
                <button onClick={() => { setLotArea(1000); setStallWidth(2.6); setStallDepth(5.0); setAislePercent(30); }} className="px-4 py-2 rounded-md border bg-slate-50 text-slate-900 border-slate-200">Reset</button>
            </div>
        </div>
    );
}
