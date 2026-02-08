/**
 * GenFabTools Parking Engine - Scenario Manager
 *
 * Manages scenario list, selection, renaming, and comparison.
 * v1.1: Improved naming UX with edit icon and better visual feedback
 */

import React, { useCallback, useState, useRef, useEffect } from "react";
import { useScenario } from "../state";

// =============================================================================
// Inline Editable Name Component (v1.1: Improved visual feedback)
// =============================================================================

interface EditableNameProps {
    name: string;
    onRename: (newName: string) => void;
}

function EditableName({ name, onRename }: EditableNameProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(name);
    const [isHovered, setIsHovered] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [isEditing]);

    const startEditing = () => {
        setEditValue(name);
        setIsEditing(true);
    };

    const handleBlur = () => {
        const trimmed = editValue.trim();
        if (trimmed && trimmed !== name) {
            onRename(trimmed);
        }
        setIsEditing(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            handleBlur();
        } else if (e.key === "Escape") {
            setEditValue(name);
            setIsEditing(false);
        }
    };

    if (isEditing) {
        return (
            <div className="flex-1 flex items-center gap-1">
                <input
                    ref={inputRef}
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={handleBlur}
                    onKeyDown={handleKeyDown}
                    className="flex-1 px-2 py-1 text-sm border border-blue-400 rounded focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    maxLength={50}
                    placeholder="Scenario name..."
                />
                <span className="text-[10px] text-gray-400 whitespace-nowrap">
                    Enter to save • Esc to cancel
                </span>
            </div>
        );
    }

    return (
        <div
            className="flex-1 flex items-center gap-1 group cursor-pointer"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            onDoubleClick={startEditing}
            title="Double-click to rename"
        >
            <span className="px-2 py-1 text-sm hover:bg-gray-100 rounded truncate transition-colors">
                {name}
            </span>
            <button
                onClick={(e) => { e.stopPropagation(); startEditing(); }}
                className={`p-1 rounded hover:bg-gray-200 transition-all ${isHovered ? 'opacity-100' : 'opacity-0'}`}
                title="Edit name"
            >
                <svg className="w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
            </button>
        </div>
    );
}

// =============================================================================
// Scenario Comparison Table
// =============================================================================

function ScenarioComparison() {
    const { state } = useScenario();

    // Only show scenarios with results
    const completedScenarios = state.scenarios.filter(s => s.status === "complete" && s.result);

    if (completedScenarios.length < 2) {
        return (
            <div className="px-4 py-3 text-sm text-gray-500 bg-gray-50 border-b border-gray-200">
                Evaluate at least 2 scenarios to compare
            </div>
        );
    }

    return (
        <div className="overflow-x-auto border-b border-gray-200">
            <table className="w-full text-sm">
                <thead className="bg-gray-50">
                    <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Scenario</th>
                        <th className="px-3 py-2 text-right font-medium text-gray-600">Total Stalls</th>
                        <th className="px-3 py-2 text-right font-medium text-gray-600">ADA</th>
                        <th className="px-3 py-2 text-right font-medium text-gray-600">SF/Stall</th>
                        <th className="px-3 py-2 text-right font-medium text-gray-600">Efficiency</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                    {completedScenarios.map((scenario, idx) => {
                        const result = scenario.result?.parkingResult;
                        if (!result) return null;

                        // Extract metrics safely for both surface and structured
                        const totalStalls = result.metrics.totalStalls;
                        const adaStalls = result.type === "surface"
                            ? (result.metrics as { adaStalls?: number }).adaStalls ?? 0
                            : 0;

                        const totalArea = scenario.siteBoundary
                            ? Math.abs(scenario.siteBoundary.points.reduce((acc, p, i, arr) => {
                                const next = arr[(i + 1) % arr.length];
                                return acc + (p.x * next.y - next.x * p.y);
                            }, 0) / 2)
                            : 0;

                        const sfPerStall = totalStalls > 0
                            ? (totalArea / totalStalls).toFixed(0)
                            : "—";

                        const efficiency = totalArea > 0 && totalStalls > 0
                            ? ((totalStalls * 160) / totalArea * 100).toFixed(1)
                            : "—";

                        // Highlight best values
                        const maxStalls = Math.max(...completedScenarios.map(s =>
                            s.result?.parkingResult?.metrics?.totalStalls || 0
                        ));
                        const isBest = totalStalls === maxStalls;

                        return (
                            <tr key={scenario.id} className={idx % 2 === 0 ? "bg-white" : "bg-gray-25"}>
                                <td className="px-3 py-2 font-medium text-gray-800 truncate max-w-[150px]">
                                    {scenario.name}
                                </td>
                                <td className={`px-3 py-2 text-right tabular-nums ${isBest ? "text-green-600 font-semibold" : ""}`}>
                                    {totalStalls}
                                    {isBest && " ★"}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">
                                    {adaStalls}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">
                                    {sfPerStall}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">
                                    {efficiency}%
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

// =============================================================================
// Scenario Manager Component
// =============================================================================

export function ScenarioManager() {
    const {
        state,
        activeScenario,
        createScenario,
        setActiveScenario,
        deleteScenario,
        duplicateScenario,
        renameScenario,
    } = useScenario();

    const [showComparison, setShowComparison] = useState(false);

    const handleCreate = useCallback(() => {
        // Let the store determine the next available name
        createScenario();
    }, [createScenario]);

    const handleDuplicate = useCallback(() => {
        if (activeScenario) {
            duplicateScenario(activeScenario.id);
        }
    }, [activeScenario, duplicateScenario]);

    const handleDelete = useCallback(() => {
        if (activeScenario && state.scenarios.length > 1) {
            deleteScenario(activeScenario.id);
        }
    }, [activeScenario, deleteScenario, state.scenarios.length]);

    const handleRename = useCallback((newName: string) => {
        if (activeScenario) {
            renameScenario(activeScenario.id, newName);
        }
    }, [activeScenario, renameScenario]);

    const completedCount = state.scenarios.filter(s => s.status === "complete").length;

    return (
        <div>
            <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 border-b border-gray-200">
                {/* Scenario Selector */}
                <select
                    value={activeScenario?.id || ""}
                    onChange={(e) => setActiveScenario(e.target.value)}
                    className="w-32 px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {state.scenarios.length === 0 && (
                        <option value="">No scenarios</option>
                    )}
                    {state.scenarios.map((s, idx) => (
                        <option key={s.id} value={s.id}>
                            {s.name}
                            {s.status === "complete" && " ✓"}
                            {s.status === "error" && " ✗"}
                        </option>
                    ))}
                </select>

                {/* Editable Name */}
                {activeScenario && (
                    <EditableName
                        name={activeScenario.name}
                        onRename={handleRename}
                    />
                )}

                {/* Actions */}
                <button
                    onClick={handleCreate}
                    className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition-colors"
                    title="New Scenario"
                >
                    + New
                </button>

                <button
                    onClick={handleDuplicate}
                    disabled={!activeScenario}
                    className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors disabled:opacity-50"
                    title="Duplicate Scenario"
                >
                    Copy
                </button>

                <button
                    onClick={handleDelete}
                    disabled={!activeScenario || state.scenarios.length <= 1}
                    className="px-3 py-1.5 text-sm font-medium text-red-600 bg-white border border-red-200 rounded hover:bg-red-50 transition-colors disabled:opacity-50"
                    title="Delete Scenario"
                >
                    Delete
                </button>

                {/* Compare Toggle */}
                <button
                    onClick={() => setShowComparison(!showComparison)}
                    disabled={completedCount < 2}
                    className={`px-3 py-1.5 text-sm font-medium rounded transition-colors disabled:opacity-50 ${showComparison
                        ? "text-white bg-indigo-600 hover:bg-indigo-700"
                        : "text-indigo-600 bg-white border border-indigo-200 hover:bg-indigo-50"
                        }`}
                    title={completedCount < 2 ? "Evaluate 2+ scenarios to compare" : "Compare Scenarios"}
                >
                    Compare
                </button>
            </div>

            {/* Comparison Table */}
            {showComparison && <ScenarioComparison />}
        </div>
    );
}
