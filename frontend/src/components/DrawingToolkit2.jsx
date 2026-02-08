import React from 'react';

export default function DrawingToolkit(props) {
    const {
        mode, setMode,
        rectToolWidthMeters, setRectToolWidthMeters,
        rectToolHeightMeters, setRectToolHeightMeters,
        rectToolAngleDeg, setRectToolAngleDeg,
        rectToolCenter, setRectToolCenter,
        onInsertRectangle, viewBox,
        snapToGrid, setSnapToGrid,
        gridSize, setGridSize,
        snapMeasure, setSnapMeasure,
        showDimensions, setShowDimensions,
        unitSystem, metersToFeet, feetToMeters,
    } = props;

    return (
        <div className="rounded-md border bg-white p-3 shadow-sm">
            <div className="flex items-center justify-between mb-2">
                {props.showHeader !== false && (
                    <div className="font-semibold text-slate-800">{props.headerTitle || 'Drawing Toolkit'}</div>
                )}
                {/* Primary actions: close/reset/measure/clear - provided by parent via props */}
            </div>

            {/* Action buttons inside the card */}
            <div className="flex gap-2 mb-3">
                <button type="button" onClick={props.onClosePolygon} className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100 text-sm">Close polygon</button>
                <button type="button" onClick={props.onResetDrawing} className="px-3 py-1 rounded-md border bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100 text-sm">Reset drawing</button>
                <button type="button" onClick={props.onToggleMeasure} className={`px-3 py-1 rounded-md border text-sm ${props.mode === 'measure' ? 'bg-sky-600 text-white border-sky-700' : 'bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100'}`}>{props.mode === 'measure' ? 'Exit Measure' : 'Measure'}</button>
                <button type="button" onClick={() => props.setMode(m => (m === 'pan' ? 'draw' : 'pan'))} className={`px-3 py-1 rounded-md border text-sm ${props.mode === 'pan' ? 'bg-emerald-600 text-white border-emerald-700' : 'bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100'}`}>{props.mode === 'pan' ? 'Exit Pan' : 'Pan'}</button>
                <button type="button" onClick={props.onClearDims} className="px-3 py-1 rounded-md border bg-white text-slate-900 text-sm">Clear dims</button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="border rounded p-2">
                    <div className="flex items-center gap-2 text-xs">
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <button type="button" onClick={() => setMode('draw')} className={`border rounded px-2 py-1 text-sm ${mode === 'draw' ? 'bg-sky-600 text-white border-sky-700' : 'bg-white text-slate-800 border-slate-200 hover:bg-slate-50'}`}>
                                Polygon
                            </button>
                        </div>
                        <label className="ml-2 flex items-center gap-1">
                            <input type="checkbox" checked={snapToGrid} onChange={e => setSnapToGrid(e.target.checked)} />
                            <span>Snap to grid</span>
                        </label>
                        <label className="flex items-center gap-1">
                            <span>Grid</span>
                            <input type="number" className="w-16 border rounded px-1 py-0.5" value={gridSize} onChange={e => setGridSize(Number(e.target.value))} />
                        </label>
                    </div>
                </div>

                <div className="border rounded p-2">
                    <div className="text-xs font-semibold text-slate-700 mb-2">Boundary Rectangle</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                        <label>W ({unitSystem === 'metric' ? 'm' : 'ft'})
                            <input type="number" className="ml-1 w-20 border rounded px-1 py-0.5" value={unitSystem === 'imperial' ? metersToFeet(rectToolWidthMeters) : rectToolWidthMeters} onChange={e => setRectToolWidthMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} />
                        </label>
                        <label>H ({unitSystem === 'metric' ? 'm' : 'ft'})
                            <input type="number" className="ml-1 w-20 border rounded px-1 py-0.5" value={unitSystem === 'imperial' ? metersToFeet(rectToolHeightMeters) : rectToolHeightMeters} onChange={e => setRectToolHeightMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} />
                        </label>
                        <label>Angle (°)
                            <input type="number" className="ml-1 w-16 border rounded px-1 py-0.5" value={rectToolAngleDeg} onChange={e => setRectToolAngleDeg(Number(e.target.value))} />
                        </label>
                        <button className="ml-2 px-2 py-1 bg-slate-700 text-white rounded" onClick={onInsertRectangle}>Insert</button>
                        <button className="px-2 py-1 bg-slate-500 text-white rounded" onClick={() => setRectToolCenter({ x: viewBox.x + viewBox.w / 2, y: viewBox.y + viewBox.h / 2 })}>Center</button>
                    </div>
                </div>
            </div>

            <div className="mt-3 border rounded p-2">
                <div className="text-xs font-semibold text-slate-700 mb-2">Measuring</div>
                <div className="flex flex-wrap gap-3 items-center text-xs">
                    <label className="flex items-center gap-1">
                        <input type="checkbox" checked={snapMeasure} onChange={e => setSnapMeasure(e.target.checked)} />
                        <span>Snap to geometry</span>
                    </label>
                    <label className="flex items-center gap-1">
                        <input type="checkbox" checked={showDimensions} onChange={e => setShowDimensions(e.target.checked)} />
                        <span>Show dimensions</span>
                    </label>
                </div>
            </div>
        </div>
    );
}
