/**
 * GenFabTools Parking Engine - Constraints Panel
 *
 * Allows users to import and manage CAD/BIM constraints:
 * - Upload DXF / DWG / RVT files
 * - Display imported constraints
 * - Enable / disable constraints
 * - Color by constraint type
 *
 * This panel does NOT interpret or edit geometry.
 */

import React, { useCallback, useState } from "react";
import { useScenario } from "../state";
import { importConstraints, ParkingApiError } from "../api";
import {
    CONSTRAINT_COLORS,
    CONSTRAINT_LABELS,
    isSupportedFile,
    CONSTRAINT_FILE_EXTENSIONS,
} from "../utils";
import type { ConstraintType, ImportedConstraint } from "../types";

// Dev mode flag
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const IS_DEV = (import.meta as any).env?.DEV ?? false;

// =============================================================================
// Constraint Type Summary
// =============================================================================

interface ConstraintTypeSummaryProps {
    constraints: readonly ImportedConstraint[];
}

function ConstraintTypeSummary({ constraints }: ConstraintTypeSummaryProps) {
    // Count by type
    const counts = constraints.reduce(
        (acc, c) => {
            acc[c.constraintType] = (acc[c.constraintType] || 0) + 1;
            return acc;
        },
        {} as Record<ConstraintType, number>
    );

    const entries = Object.entries(counts) as [ConstraintType, number][];

    if (entries.length === 0) {
        return null;
    }

    return (
        <div className="space-y-1">
            {entries.map(([type, count]) => (
                <div
                    key={type}
                    className="flex items-center justify-between text-xs"
                >
                    <div className="flex items-center gap-2">
                        <div
                            className="w-3 h-3 rounded"
                            style={{ backgroundColor: CONSTRAINT_COLORS[type] }}
                        />
                        <span className="text-gray-700">
                            {CONSTRAINT_LABELS[type]}
                        </span>
                    </div>
                    <span className="text-gray-500">{count}</span>
                </div>
            ))}
        </div>
    );
}

// =============================================================================
// Constraint List
// =============================================================================

interface ConstraintListProps {
    constraints: readonly ImportedConstraint[];
}

function ConstraintList({ constraints }: ConstraintListProps) {
    const [expanded, setExpanded] = useState(false);

    if (constraints.length === 0) {
        return null;
    }

    const displayConstraints = expanded
        ? constraints
        : constraints.slice(0, 5);

    return (
        <div className="space-y-2">
            <div className="max-h-40 overflow-y-auto space-y-1">
                {displayConstraints.map((c) => (
                    <div
                        key={c.id}
                        className="flex items-center gap-2 text-xs bg-gray-50 rounded px-2 py-1"
                    >
                        <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{
                                backgroundColor:
                                    CONSTRAINT_COLORS[c.constraintType],
                            }}
                        />
                        <span className="truncate text-gray-600">
                            {c.layerName || c.categoryName || c.constraintType}
                        </span>
                    </div>
                ))}
            </div>
            {constraints.length > 5 && (
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="text-xs text-blue-600 hover:underline"
                >
                    {expanded
                        ? "Show less"
                        : `Show ${constraints.length - 5} more`}
                </button>
            )}
        </div>
    );
}

// =============================================================================
// File Upload
// =============================================================================

interface FileUploadProps {
    onImport: (constraints: readonly ImportedConstraint[]) => void;
}

function FileUpload({ onImport }: FileUploadProps) {
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleFileChange = useCallback(
        async (e: React.ChangeEvent<HTMLInputElement>) => {
            const file = e.target.files?.[0];
            if (!file) return;

            if (!isSupportedFile(file.name, CONSTRAINT_FILE_EXTENSIONS)) {
                setError("Supported formats: DXF");
                return;
            }

            setIsUploading(true);
            setError(null);

            try {
                const result = await importConstraints(file);

                // Log warnings in dev mode
                if (IS_DEV && result.warnings.length > 0) {
                    console.log("[Constraint Import] Warnings:", result.warnings);
                }

                if (result.polygons.length === 0) {
                    setError("No geometry found in file");
                    return;
                }

                // Convert polygons to ImportedConstraint objects
                // Layer name is used to classify constraint type
                const constraints: ImportedConstraint[] = result.polygons.map(
                    (polygon, index) => ({
                        id: `imported_${index}_${Date.now()}`,
                        geometry: polygon,
                        constraintType: "VOID" as const, // Default to VOID, user can reclassify
                        layerName: undefined,
                        categoryName: undefined,
                        sourceFile: file.name,
                    })
                );

                onImport(constraints);
            } catch (err) {
                // ParkingApiError now contains the user-friendly message
                if (err instanceof ParkingApiError) {
                    setError(err.message);
                    // Dev mode: log additional details
                    if (IS_DEV && err.details) {
                        console.error("[Constraint Import] Error details:", err.details);
                    }
                } else if (err instanceof Error) {
                    setError(err.message);
                } else {
                    setError("Failed to import constraints");
                }
            } finally {
                setIsUploading(false);
                e.target.value = "";
            }
        },
        [onImport]
    );

    return (
        <div className="space-y-2">
            <label className="block">
                <span className="sr-only">Upload Constraints</span>
                <input
                    type="file"
                    accept=".dxf,.dwg,.rvt"
                    onChange={handleFileChange}
                    disabled={isUploading}
                    className="block w-full text-sm text-gray-500
                        file:mr-3 file:py-2 file:px-4
                        file:rounded file:border-0
                        file:text-sm file:font-medium
                        file:bg-gray-100 file:text-gray-700
                        hover:file:bg-gray-200
                        disabled:opacity-50"
                />
            </label>
            {isUploading && (
                <p className="text-xs text-gray-500">Importing...</p>
            )}
            {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
    );
}

// =============================================================================
// Main Component
// =============================================================================

export function ConstraintsPanel() {
    const {
        activeScenario,
        setConstraints,
        toggleConstraints,
    } = useScenario();

    const handleImport = useCallback(
        (imported: readonly ImportedConstraint[]) => {
            if (!activeScenario) return;
            // Merge with existing constraints
            const merged = [...activeScenario.constraints, ...imported];
            setConstraints(activeScenario.id, merged);
            // Auto-enable when importing
            toggleConstraints(activeScenario.id, true);
        },
        [activeScenario, setConstraints, toggleConstraints]
    );

    const handleClear = useCallback(() => {
        if (!activeScenario) return;
        setConstraints(activeScenario.id, []);
        toggleConstraints(activeScenario.id, false);
    }, [activeScenario, setConstraints, toggleConstraints]);

    const handleToggle = useCallback(() => {
        if (!activeScenario) return;
        toggleConstraints(activeScenario.id, !activeScenario.constraintsEnabled);
    }, [activeScenario, toggleConstraints]);

    if (!activeScenario) {
        return (
            <div className="p-4 text-sm text-gray-500">
                Create a scenario to add constraints.
            </div>
        );
    }

    const hasConstraints = activeScenario.constraints.length > 0;

    return (
        <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">
                    Constraints
                </h3>
                {hasConstraints && (
                    <span className="text-xs text-gray-500">
                        {activeScenario.constraints.length} imported
                    </span>
                )}
            </div>

            {/* Enable/Disable Toggle */}
            {hasConstraints && (
                <div className="flex items-center justify-between bg-gray-50 rounded px-3 py-2">
                    <span className="text-sm text-gray-700">
                        Apply Constraints
                    </span>
                    <button
                        onClick={handleToggle}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${activeScenario.constraintsEnabled
                            ? "bg-blue-600"
                            : "bg-gray-300"
                            }`}
                    >
                        <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${activeScenario.constraintsEnabled
                                ? "translate-x-4"
                                : "translate-x-0.5"
                                }`}
                        />
                    </button>
                </div>
            )}

            {/* Constraint Type Summary */}
            {hasConstraints && (
                <div className="bg-gray-50 rounded p-3">
                    <p className="text-xs font-medium text-gray-600 mb-2">
                        By Type
                    </p>
                    <ConstraintTypeSummary
                        constraints={activeScenario.constraints}
                    />
                </div>
            )}

            {/* Constraint List */}
            {hasConstraints && (
                <ConstraintList constraints={activeScenario.constraints} />
            )}

            {/* v1.1: Circulation Limitation Note (shown when constraints enabled) */}
            {hasConstraints && activeScenario.constraintsEnabled && (
                <div className="bg-amber-50 border border-amber-100 rounded px-3 py-2">
                    <div className="flex items-start gap-2">
                        <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div>
                            <p className="text-xs font-medium text-amber-800">
                                Linear circulation only
                            </p>
                            <p className="text-[10px] text-amber-700 mt-0.5 leading-relaxed">
                                Secondary or curved connectors are not generated in this version.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Import */}
            <FileUpload onImport={handleImport} />

            {/* Clear Button */}
            {hasConstraints && (
                <button
                    onClick={handleClear}
                    className="w-full px-3 py-2 text-xs font-medium text-red-600 bg-white border border-red-200 rounded hover:bg-red-50 transition-colors"
                >
                    Clear All Constraints
                </button>
            )}

            {/* Info */}
            <p className="text-xs text-gray-500">
                Import DXF, DWG, or RVT files containing columns, cores, walls,
                or other constraints. Geometry editing is not supported.
            </p>
        </div>
    );
}
