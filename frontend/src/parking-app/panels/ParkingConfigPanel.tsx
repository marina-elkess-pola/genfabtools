/**
 * GenFabTools Parking Engine - Parking Configuration Panel
 *
 * Allows users to configure parking type and options:
 * - Surface / Structured toggle
 * - Aisle direction
 * - Structured options (levels, ramp type, etc.)
 *
 * This panel does NOT compute anything - it captures user intent.
 */

import React, { useCallback } from "react";
import { useScenario } from "../state";
import type {
    ParkingType,
    AisleDirection,
    StallAngle,
    StructuredConfig,
    RampType,
    RampLocation,
    CoreType,
    Setbacks,
} from "../types";

// =============================================================================
// Default Setbacks
// =============================================================================

const DEFAULT_SETBACKS: Setbacks = {
    north: 5.0,
    south: 5.0,
    east: 5.0,
    west: 5.0,
};

// =============================================================================
// Option Definitions
// =============================================================================

const AISLE_OPTIONS: { value: AisleDirection; label: string }[] = [
    { value: "ONE_WAY", label: "One-Way" },
    { value: "TWO_WAY", label: "Two-Way" },
];

const STALL_ANGLE_OPTIONS: { value: StallAngle; label: string }[] = [
    { value: 45, label: "45°" },
    { value: 60, label: "60°" },
    { value: 90, label: "90°" },
];

const RAMP_TYPE_OPTIONS: { value: RampType; label: string }[] = [
    { value: "single_helix", label: "Single Helix" },
    { value: "double_helix", label: "Double Helix" },
    { value: "split_level", label: "Split Level" },
    { value: "straight", label: "Straight" },
];

const LOCATION_OPTIONS: { value: RampLocation; label: string }[] = [
    { value: "northeast", label: "Northeast" },
    { value: "northwest", label: "Northwest" },
    { value: "southeast", label: "Southeast" },
    { value: "southwest", label: "Southwest" },
    { value: "center", label: "Center" },
];

const CORE_TYPE_OPTIONS: { value: CoreType; label: string }[] = [
    { value: "stair_only", label: "Stair Only" },
    { value: "stair_elevator", label: "Stair + Elevator" },
    { value: "dual_stair_elevator", label: "Dual Stair + Elevator" },
];

const DEFAULT_STRUCTURED_CONFIG: StructuredConfig = {
    levels: 4,
    floorToFloorHeight: 10.5,
    rampType: "single_helix",
    rampLocation: "northeast",
    coreType: "stair_elevator",
    coreLocation: "center",
};

// =============================================================================
// Structured Options Component
// =============================================================================

interface StructuredOptionsProps {
    config: StructuredConfig;
    onChange: (config: Partial<StructuredConfig>) => void;
}

function StructuredOptions({ config, onChange }: StructuredOptionsProps) {
    return (
        <div className="space-y-4 pt-3 border-t border-gray-200">
            {/* Level Count */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Number of Levels
                </label>
                <input
                    type="number"
                    value={config.levels}
                    onChange={(e) =>
                        onChange({ levels: parseInt(e.target.value) || 2 })
                    }
                    min="2"
                    max="12"
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                />
            </div>

            {/* Floor-to-Floor Height */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Floor-to-Floor Height (ft)
                </label>
                <input
                    type="number"
                    value={config.floorToFloorHeight}
                    onChange={(e) =>
                        onChange({
                            floorToFloorHeight: parseFloat(e.target.value) || 10,
                        })
                    }
                    min="9"
                    max="14"
                    step="0.5"
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                />
            </div>

            {/* Ramp Type */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Ramp Type
                </label>
                <select
                    value={config.rampType}
                    onChange={(e) =>
                        onChange({ rampType: e.target.value as RampType })
                    }
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {RAMP_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
            </div>

            {/* Ramp Location */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Ramp Location
                </label>
                <select
                    value={config.rampLocation}
                    onChange={(e) =>
                        onChange({ rampLocation: e.target.value as RampLocation })
                    }
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {LOCATION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
            </div>

            {/* Core Type */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Core Type
                </label>
                <select
                    value={config.coreType}
                    onChange={(e) =>
                        onChange({ coreType: e.target.value as CoreType })
                    }
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {CORE_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
            </div>

            {/* Core Location */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Core Location
                </label>
                <select
                    value={config.coreLocation}
                    onChange={(e) =>
                        onChange({ coreLocation: e.target.value as RampLocation })
                    }
                    className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                >
                    {LOCATION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                            {opt.label}
                        </option>
                    ))}
                </select>
            </div>
        </div>
    );
}

// =============================================================================
// Main Component
// =============================================================================

export function ParkingConfigPanel() {
    const { activeScenario, setParkingConfig } = useScenario();

    const handleParkingTypeChange = useCallback(
        (type: ParkingType) => {
            if (!activeScenario) return;
            setParkingConfig(activeScenario.id, {
                parkingType: type,
                structuredConfig:
                    type === "structured"
                        ? activeScenario.parkingConfig.structuredConfig ||
                        DEFAULT_STRUCTURED_CONFIG
                        : undefined,
            });
        },
        [activeScenario, setParkingConfig]
    );

    const handleAisleChange = useCallback(
        (direction: AisleDirection) => {
            if (!activeScenario) return;
            setParkingConfig(activeScenario.id, { aisleDirection: direction });
        },
        [activeScenario, setParkingConfig]
    );

    const handleStallAngleChange = useCallback(
        (angle: StallAngle) => {
            if (!activeScenario) return;
            // Auto-set circulation mode based on angle:
            // - 45° and 60° require ONE_WAY circulation
            // - 90° requires TWO_WAY circulation
            const aisleDirection: AisleDirection = angle === 90 ? "TWO_WAY" : "ONE_WAY";
            setParkingConfig(activeScenario.id, { stallAngle: angle, aisleDirection });
        },
        [activeScenario, setParkingConfig]
    );

    const handleSetbackChange = useCallback(
        (setback: number) => {
            if (!activeScenario) return;
            // When uniform, update both setback and all edges in setbacks
            const setbacks: Setbacks = {
                north: setback,
                south: setback,
                east: setback,
                west: setback,
            };
            setParkingConfig(activeScenario.id, { setback, setbacks });
        },
        [activeScenario, setParkingConfig]
    );

    const handleUniformToggle = useCallback(
        (uniform: boolean) => {
            if (!activeScenario) return;
            const currentSetbacks = activeScenario.parkingConfig.setbacks || DEFAULT_SETBACKS;
            if (uniform) {
                // When switching to uniform, use the max of all edges
                const maxVal = Math.max(
                    currentSetbacks.north,
                    currentSetbacks.south,
                    currentSetbacks.east,
                    currentSetbacks.west
                );
                setParkingConfig(activeScenario.id, {
                    uniformSetback: true,
                    setback: maxVal,
                    setbacks: { north: maxVal, south: maxVal, east: maxVal, west: maxVal },
                });
            } else {
                setParkingConfig(activeScenario.id, { uniformSetback: false });
            }
        },
        [activeScenario, setParkingConfig]
    );

    const handleEdgeSetbackChange = useCallback(
        (edge: keyof Setbacks, value: number) => {
            if (!activeScenario) return;
            const currentSetbacks = activeScenario.parkingConfig.setbacks || DEFAULT_SETBACKS;
            const newSetbacks: Setbacks = {
                ...currentSetbacks,
                [edge]: value,
            };
            // Also update legacy setback to max for backwards compatibility
            const maxSetback = Math.max(newSetbacks.north, newSetbacks.south, newSetbacks.east, newSetbacks.west);
            setParkingConfig(activeScenario.id, { setbacks: newSetbacks, setback: maxSetback });
        },
        [activeScenario, setParkingConfig]
    );

    const handleStructuredConfigChange = useCallback(
        (updates: Partial<StructuredConfig>) => {
            if (!activeScenario) return;
            const currentConfig =
                activeScenario.parkingConfig.structuredConfig ||
                DEFAULT_STRUCTURED_CONFIG;
            setParkingConfig(activeScenario.id, {
                structuredConfig: { ...currentConfig, ...updates },
            });
        },
        [activeScenario, setParkingConfig]
    );

    if (!activeScenario) {
        return (
            <div className="p-4 text-sm text-gray-500">
                Create a scenario to configure parking.
            </div>
        );
    }

    const { parkingConfig } = activeScenario;
    const isStructured = parkingConfig.parkingType === "structured";

    return (
        <div className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-gray-900">
                Parking Configuration
            </h3>

            {/* Parking Type Toggle */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-2">
                    Parking Type
                </label>
                <div className="flex border border-gray-200 rounded overflow-hidden">
                    <button
                        onClick={() => handleParkingTypeChange("surface")}
                        className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${!isStructured
                            ? "bg-blue-600 text-white"
                            : "bg-white text-gray-700 hover:bg-gray-50"
                            }`}
                    >
                        Surface
                    </button>
                    <button
                        disabled
                        className="flex-1 px-3 py-2 text-sm font-medium bg-gray-100 text-gray-400 cursor-not-allowed"
                        title="Structured parking coming soon"
                    >
                        Structured
                    </button>
                </div>
                {/* Structured Coming Soon Notice */}
                <div className="mt-2 bg-slate-50 border border-slate-200 rounded px-2.5 py-1.5">
                    <div className="flex items-center gap-1.5">
                        <span className="text-xs">🚧</span>
                        <p className="text-xs text-slate-600">
                            <span className="font-medium">Structured parking</span> — Coming next
                        </p>
                    </div>
                </div>
            </div>

            {/* Stall Angle */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-2">
                    Stall Angle
                </label>
                <div className="flex gap-2">
                    {STALL_ANGLE_OPTIONS.map((opt) => (
                        <button
                            key={opt.value}
                            onClick={() => handleStallAngleChange(opt.value)}
                            className={`flex-1 px-3 py-1.5 text-xs font-medium rounded border transition-colors ${parkingConfig.stallAngle === opt.value
                                ? "border-blue-600 bg-blue-50 text-blue-700"
                                : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                                }`}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Aisle Direction */}
            <div>
                <label className="block text-xs font-medium text-gray-600 mb-2">
                    Circulation Mode
                </label>
                <div className="flex gap-2">
                    {AISLE_OPTIONS.map((opt) => {
                        // Determine if this option is disabled based on stall angle
                        // 90° requires TWO_WAY, 45°/60° require ONE_WAY
                        const isDisabled =
                            (parkingConfig.stallAngle === 90 && opt.value === "ONE_WAY") ||
                            (parkingConfig.stallAngle !== 90 && opt.value === "TWO_WAY");

                        const tooltip = isDisabled
                            ? parkingConfig.stallAngle === 90
                                ? "90° parking requires two-way circulation"
                                : `${parkingConfig.stallAngle}° parking requires one-way circulation`
                            : undefined;

                        return (
                            <button
                                key={opt.value}
                                onClick={() => !isDisabled && handleAisleChange(opt.value)}
                                disabled={isDisabled}
                                title={tooltip}
                                className={`flex-1 px-3 py-1.5 text-xs font-medium rounded border transition-colors ${isDisabled
                                        ? "border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed"
                                        : parkingConfig.aisleDirection === opt.value
                                            ? "border-blue-600 bg-blue-50 text-blue-700"
                                            : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                                    }`}
                            >
                                {opt.label}
                            </button>
                        );
                    })}
                </div>
                {/* Circulation mode explanation */}
                <p className="text-[10px] text-gray-400 mt-1.5 leading-tight">
                    {parkingConfig.stallAngle === 90
                        ? "90° parking uses two-way aisles (24 ft width)"
                        : `${parkingConfig.stallAngle}° parking uses one-way aisles (15 ft width)`}
                </p>
            </div>

            {/* Setback */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-medium text-gray-600">
                        Setbacks (ft)
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={parkingConfig.uniformSetback !== false}
                            onChange={(e) => handleUniformToggle(e.target.checked)}
                            className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="text-xs text-gray-500">Same all sides</span>
                    </label>
                </div>

                {parkingConfig.uniformSetback !== false ? (
                    // Uniform setback - single input
                    <input
                        type="number"
                        value={parkingConfig.setback}
                        onChange={(e) =>
                            handleSetbackChange(parseFloat(e.target.value) || 0)
                        }
                        min="0"
                        max="50"
                        step="1"
                        className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                ) : (
                    // Per-edge setbacks - four inputs in a grid
                    <div className="space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                            {/* North */}
                            <div className="col-span-2 flex items-center gap-2">
                                <label className="w-12 text-xs text-gray-500 text-right">North</label>
                                <input
                                    type="number"
                                    value={(parkingConfig.setbacks || DEFAULT_SETBACKS).north}
                                    onChange={(e) =>
                                        handleEdgeSetbackChange("north", parseFloat(e.target.value) || 0)
                                    }
                                    min="0"
                                    max="50"
                                    step="1"
                                    className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>
                            {/* West and East side by side */}
                            <div className="flex items-center gap-2">
                                <label className="w-12 text-xs text-gray-500 text-right">West</label>
                                <input
                                    type="number"
                                    value={(parkingConfig.setbacks || DEFAULT_SETBACKS).west}
                                    onChange={(e) =>
                                        handleEdgeSetbackChange("west", parseFloat(e.target.value) || 0)
                                    }
                                    min="0"
                                    max="50"
                                    step="1"
                                    className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>
                            <div className="flex items-center gap-2">
                                <label className="w-12 text-xs text-gray-500 text-right">East</label>
                                <input
                                    type="number"
                                    value={(parkingConfig.setbacks || DEFAULT_SETBACKS).east}
                                    onChange={(e) =>
                                        handleEdgeSetbackChange("east", parseFloat(e.target.value) || 0)
                                    }
                                    min="0"
                                    max="50"
                                    step="1"
                                    className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>
                            {/* South */}
                            <div className="col-span-2 flex items-center gap-2">
                                <label className="w-12 text-xs text-gray-500 text-right">South</label>
                                <input
                                    type="number"
                                    value={(parkingConfig.setbacks || DEFAULT_SETBACKS).south}
                                    onChange={(e) =>
                                        handleEdgeSetbackChange("south", parseFloat(e.target.value) || 0)
                                    }
                                    min="0"
                                    max="50"
                                    step="1"
                                    className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>
                        </div>
                        {/* Orientation clarification */}
                        <p className="text-[10px] text-gray-400 mt-1.5 leading-tight">
                            ↑ Top of drawing = North. Directions refer to screen orientation, not true geographic north.
                        </p>
                    </div>
                )}
            </div>

            {/* Structured Options */}
            {isStructured && parkingConfig.structuredConfig && (
                <StructuredOptions
                    config={parkingConfig.structuredConfig}
                    onChange={handleStructuredConfigChange}
                />
            )}
        </div>
    );
}
