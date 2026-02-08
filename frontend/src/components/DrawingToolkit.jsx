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
        <div className="rounded-md border bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
                <div className="font-semibold text-slate-800">Drawing Toolkit</div>
                <div className="text-sm text-slate-500">Tools for polygon & layout editing</div>
            </div>

            {/* Toolbar actions */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
                <button type="button" onClick={props.onClosePolygon} className="px-3 py-1.5 rounded-md border bg-white text-slate-800 border-slate-200 hover:bg-slate-50 text-sm">Close polygon</button>
                <button type="button" onClick={props.onResetDrawing} className="px-3 py-1.5 rounded-md border bg-white text-slate-800 border-slate-200 hover:bg-slate-50 text-sm">Reset drawing</button>
                <button type="button" onClick={props.onToggleMeasure} className={`px-3 py-1.5 rounded-md border text-sm ${props.mode === 'measure' ? 'bg-sky-600 text-white border-sky-700' : 'bg-white text-slate-800 border-slate-200 hover:bg-slate-50'}`}>{props.mode === 'measure' ? 'Exit Measure' : 'Measure'}</button>
                <button type="button" onClick={() => props.setMode(m => (m === 'pan' ? 'draw' : 'pan'))} className={`px-3 py-1.5 rounded-md border text-sm ${props.mode === 'pan' ? 'bg-emerald-600 text-white border-emerald-700' : 'bg-white text-slate-800 border-slate-200 hover:bg-slate-50'}`}>{props.mode === 'pan' ? 'Exit Pan' : 'Pan'}</button>
                <button type="button" onClick={props.onClearDims} className="px-3 py-1.5 rounded-md border bg-white text-slate-800 text-sm">Clear dims</button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Mode card */}
                <div className="border rounded-lg p-3 bg-slate-50">
                    <div className="flex items-center justify-between mb-2">
                        <div className="text-xs font-semibold text-slate-700">Mode</div>
                        <div className="text-xs text-slate-500">Active: <span className="font-semibold text-slate-700 ml-1">{mode === 'draw' ? 'Polygon' : mode}</span></div>
                    </div>

                    <div className="flex items-center gap-3">
                        <button type="button" onClick={() => setMode('draw')} className={`px-4 py-2 rounded-md text-sm border ${mode === 'draw' ? 'bg-sky-600 text-white border-sky-700' : 'bg-white text-slate-800 border-slate-200 hover:bg-slate-50'}`}>
                            Polygon
                        </button>

                        <div className="ml-2 flex items-center gap-3">
                            <label className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={snapToGrid} onChange={e => setSnapToGrid(e.target.checked)} />
                                <span className="text-sm">Snap to grid</span>
                            </label>

                            <label className="flex items-center gap-2 text-sm">
                                <span className="text-sm">Grid</span>
                                <input type="number" className="w-20 border rounded px-2 py-1 text-sm" value={gridSize} onChange={e => setGridSize(Number(e.target.value))} />
                            </label>
                        </div>
                    </div>
                </div>

                {/* Boundary rectangle card */}
                <div className="border rounded-lg p-3">
                    <div className="text-xs font-semibold text-slate-700 mb-2">Boundary Rectangle</div>
                    <div className="flex flex-wrap items-center gap-3">
                        <label className="flex items-center gap-2 text-sm">
                            <span>W ({unitSystem === 'metric' ? 'm' : 'ft'})</span>
                            <input type="number" className="w-24 border rounded px-2 py-1 text-sm" value={unitSystem === 'imperial' ? metersToFeet(rectToolWidthMeters) : rectToolWidthMeters} onChange={e => setRectToolWidthMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} />
                        </label>

                        <label className="flex items-center gap-2 text-sm">
                            <span>H ({unitSystem === 'metric' ? 'm' : 'ft'})</span>
                            <input type="number" className="w-24 border rounded px-2 py-1 text-sm" value={unitSystem === 'imperial' ? metersToFeet(rectToolHeightMeters) : rectToolHeightMeters} onChange={e => setRectToolHeightMeters(unitSystem === 'imperial' ? feetToMeters(Number(e.target.value) || 0) : (Number(e.target.value) || 0))} />
                        </label>

                        <label className="flex items-center gap-2 text-sm">
                            <span>Angle (°)</span>
                            <input type="number" className="w-20 border rounded px-2 py-1 text-sm" value={rectToolAngleDeg} onChange={e => setRectToolAngleDeg(Number(e.target.value))} />
                        </label>

                        <div className="ml-auto flex items-center gap-2">
                            <button className="px-3 py-1.5 bg-sky-600 text-white rounded" onClick={onInsertRectangle}>Insert</button>
                            <button className="px-3 py-1.5 bg-slate-700 text-white rounded" onClick={() => setRectToolCenter({ x: viewBox.x + viewBox.w / 2, y: viewBox.y + viewBox.h / 2 })}>Center</button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Measuring */}
            <div className="mt-4 border rounded-lg p-3 bg-slate-50">
                <div className="text-xs font-semibold text-slate-700 mb-2">Measuring</div>
                <div className="flex flex-wrap gap-4 items-center text-sm">
                    <label className="flex items-center gap-2">
                        <input type="checkbox" checked={snapMeasure} onChange={e => setSnapMeasure(e.target.checked)} />
                        <span>Snap to geometry</span>
                    </label>
                    <label className="flex items-center gap-2">
                        <input type="checkbox" checked={showDimensions} onChange={e => setShowDimensions(e.target.checked)} />
                        <span>Show dimensions</span>
                    </label>
                </div>
            </div>
        </div>
    );
}
