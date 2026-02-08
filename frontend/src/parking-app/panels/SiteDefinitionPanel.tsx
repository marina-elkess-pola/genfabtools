/**
 * GenFabTools Parking Engine - Site Definition Panel
 *
 * Allows users to define the site boundary:
 * - Draw rectangular boundary
 * - Upload DXF file
 * - Reset site
 *
 * This panel does NOT compute anything - it captures user intent.
 */

import React, { useState, useCallback } from "react";
import { useScenario } from "../state";
import { importBoundaryFromDxf, ParkingApiError } from "../api";
import {
    isDisplayablePolygon,
    isSupportedFile,
    BOUNDARY_FILE_EXTENSIONS,
    formatArea,
    calculateBounds,
} from "../utils";
import type { Polygon, Point } from "../types";

// Dev mode flag
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const IS_DEV = (import.meta as any).env?.DEV ?? false;

// =============================================================================
// Rectangle Input Mode
// =============================================================================

interface RectangleInputProps {
    onSubmit: (polygon: Polygon) => void;
}

function RectangleInput({ onSubmit }: RectangleInputProps) {
    const [width, setWidth] = useState<string>("300");
    const [height, setHeight] = useState<string>("200");
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = useCallback(
        (e: React.FormEvent) => {
            e.preventDefault();
            setError(null);

            const w = parseFloat(width);
            const h = parseFloat(height);

            if (isNaN(w) || w <= 0) {
                setError("Width must be a positive number");
                return;
            }
            if (isNaN(h) || h <= 0) {
                setError("Height must be a positive number");
                return;
            }
            if (w < 50 || h < 50) {
                setError("Minimum dimension is 50 feet");
                return;
            }

            // Create rectangle polygon (counterclockwise)
            const polygon: Polygon = {
                points: [
                    { x: 0, y: 0 },
                    { x: w, y: 0 },
                    { x: w, y: h },
                    { x: 0, y: h },
                ],
            };

            onSubmit(polygon);
        },
        [width, height, onSubmit]
    );

    return (
        <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                        Width (ft)
                    </label>
                    <input
                        type="number"
                        value={width}
                        onChange={(e) => setWidth(e.target.value)}
                        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                        min="50"
                        step="10"
                    />
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                        Height (ft)
                    </label>
                    <input
                        type="number"
                        value={height}
                        onChange={(e) => setHeight(e.target.value)}
                        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                        min="50"
                        step="10"
                    />
                </div>
            </div>
            {error && (
                <p className="text-xs text-red-600">{error}</p>
            )}
            <button
                type="submit"
                className="w-full px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition-colors"
            >
                Create Site
            </button>
        </form>
    );
}

// =============================================================================
// DXF Upload Mode
// =============================================================================

interface DxfUploadProps {
    onUpload: (polygon: Polygon) => void;
}

function DxfUpload({ onUpload }: DxfUploadProps) {
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleFileChange = useCallback(
        async (e: React.ChangeEvent<HTMLInputElement>) => {
            const file = e.target.files?.[0];
            if (!file) return;

            if (!isSupportedFile(file.name, BOUNDARY_FILE_EXTENSIONS)) {
                setError("Only DXF files are supported for boundary import");
                return;
            }

            setIsUploading(true);
            setError(null);

            try {
                const result = await importBoundaryFromDxf(file);

                // On success, check if we got any polygons
                if (result.polygons.length === 0) {
                    setError("No closed polylines found in file. Site boundary must be a closed polyline.");
                    return;
                }

                // Log warnings in dev mode
                if (IS_DEV && result.warnings.length > 0) {
                    console.log("[DXF Import] Warnings:", result.warnings);
                }

                // Use the first polygon as the site boundary
                onUpload(result.polygons[0]);
            } catch (err) {
                // ParkingApiError now contains the user-friendly message
                if (err instanceof ParkingApiError) {
                    setError(err.message);
                    // Dev mode: log additional details
                    if (IS_DEV && err.details) {
                        console.error("[DXF Import] Error details:", err.details);
                    }
                } else if (err instanceof Error) {
                    setError(err.message);
                } else {
                    setError("Failed to import DXF file");
                }
            } finally {
                setIsUploading(false);
                // Reset the input
                e.target.value = "";
            }
        },
        [onUpload]
    );

    return (
        <div className="space-y-3">
            <label className="block">
                <span className="sr-only">Upload DXF</span>
                <div className="relative">
                    <input
                        type="file"
                        accept=".dxf"
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
                </div>
            </label>
            {isUploading && (
                <p className="text-xs text-gray-500">Importing...</p>
            )}
            {error && (
                <p className="text-xs text-red-600">{error}</p>
            )}
            <p className="text-xs text-gray-500">
                Upload a DXF file containing the site boundary.
                The first closed polyline will be used.
            </p>
        </div>
    );
}

// =============================================================================
// Site Summary
// =============================================================================

interface SiteSummaryProps {
    polygon: Polygon;
    onReset: () => void;
}

function SiteSummary({ polygon, onReset }: SiteSummaryProps) {
    const bounds = calculateBounds(polygon);
    const width = bounds.maxX - bounds.minX;
    const height = bounds.maxY - bounds.minY;
    // Approximate area (actual calculation in backend)
    const approxArea = width * height;

    return (
        <div className="space-y-3">
            <div className="bg-green-50 border border-green-200 rounded p-3">
                <div className="flex items-center gap-2 mb-2">
                    <svg
                        className="w-4 h-4 text-green-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M5 13l4 4L19 7"
                        />
                    </svg>
                    <span className="text-sm font-medium text-green-800">
                        Site Defined
                    </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-green-700">
                    <div>
                        <span className="text-green-600">Dimensions:</span>
                        <br />
                        {width.toFixed(0)}' × {height.toFixed(0)}'
                    </div>
                    <div>
                        <span className="text-green-600">Area:</span>
                        <br />
                        {formatArea(approxArea)}
                    </div>
                </div>
            </div>
            <button
                onClick={onReset}
                className="w-full px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 transition-colors"
            >
                Reset Site
            </button>
        </div>
    );
}

// =============================================================================
// Main Component
// =============================================================================

type InputMode = "rectangle" | "dxf";

export function SiteDefinitionPanel() {
    const { activeScenario, setSiteBoundary } = useScenario();
    const [mode, setMode] = useState<InputMode>("rectangle");

    const handleSetBoundary = useCallback(
        (polygon: Polygon) => {
            if (!activeScenario) return;
            setSiteBoundary(activeScenario.id, polygon);
        },
        [activeScenario, setSiteBoundary]
    );

    const handleReset = useCallback(() => {
        if (!activeScenario) return;
        setSiteBoundary(activeScenario.id, null);
    }, [activeScenario, setSiteBoundary]);

    if (!activeScenario) {
        return (
            <div className="p-4 text-sm text-gray-500">
                Create a scenario to define the site.
            </div>
        );
    }

    const hasSite = isDisplayablePolygon(activeScenario.siteBoundary);

    return (
        <div className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-gray-900">
                Site Definition
            </h3>

            {hasSite ? (
                <SiteSummary
                    polygon={activeScenario.siteBoundary!}
                    onReset={handleReset}
                />
            ) : (
                <>
                    {/* Mode Toggle */}
                    <div className="flex border border-gray-200 rounded overflow-hidden">
                        <button
                            onClick={() => setMode("rectangle")}
                            className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${mode === "rectangle"
                                ? "bg-blue-600 text-white"
                                : "bg-white text-gray-700 hover:bg-gray-50"
                                }`}
                        >
                            Rectangle
                        </button>
                        <button
                            onClick={() => setMode("dxf")}
                            className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${mode === "dxf"
                                ? "bg-blue-600 text-white"
                                : "bg-white text-gray-700 hover:bg-gray-50"
                                }`}
                        >
                            Upload DXF
                        </button>
                    </div>

                    {/* Input Mode */}
                    {mode === "rectangle" ? (
                        <RectangleInput onSubmit={handleSetBoundary} />
                    ) : (
                        <DxfUpload onUpload={handleSetBoundary} />
                    )}
                </>
            )}
        </div>
    );
}
