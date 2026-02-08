/**
 * GenFabTools Parking Engine - Metrics Panel
 *
 * Displays parking layout metrics and constraint impact.
 * All values are read-only from backend results.
 *
 * This panel does NOT compute anything - it displays backend results.
 */

import React, { useState, useCallback } from "react";
import { useScenario } from "../state";
import { exportParkingDxf, ParkingApiError } from "../api";
import { exportToExcel } from "../utils/excelExport";
import {
    formatNumber,
    formatArea,
    formatEfficiency,
    formatPercent,
    CONSTRAINT_COLORS,
    CONSTRAINT_LABELS,
    calculateBounds,
} from "../utils";
import type {
    SurfaceParkingResult,
    StructuredParkingResult,
    ConstraintImpact,
    ConstraintType,
    Polygon,
    ParkingConfig,
    Scenario,
} from "../types";

// =============================================================================
// Info Tooltip Component (v1.1: Standardized tooltip styling)
// =============================================================================

interface InfoTooltipProps {
    /** Short definition - max 2-3 lines, no paragraphs */
    text: string;
    /** Optional formula or range (shown on second line) */
    formula?: string;
}

function InfoTooltip({ text, formula }: InfoTooltipProps) {
    const [isVisible, setIsVisible] = React.useState(false);
    const [flipUp, setFlipUp] = React.useState(true);
    const buttonRef = React.useRef<HTMLButtonElement>(null);

    // Auto-flip tooltip if near bottom of viewport
    const handleMouseEnter = () => {
        if (buttonRef.current) {
            const rect = buttonRef.current.getBoundingClientRect();
            const spaceAbove = rect.top;
            const spaceBelow = window.innerHeight - rect.bottom;
            setFlipUp(spaceAbove > 80 || spaceAbove > spaceBelow);
        }
        setIsVisible(true);
    };

    return (
        <span className="relative inline-flex ml-1">
            <button
                ref={buttonRef}
                type="button"
                onMouseEnter={handleMouseEnter}
                onMouseLeave={() => setIsVisible(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors cursor-help"
                aria-label="More info"
            >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            </button>
            {isVisible && (
                <div
                    className={`absolute z-50 left-1/2 -translate-x-1/2 px-2.5 py-1.5 text-[11px] leading-tight text-white bg-gray-800 rounded shadow-lg ${flipUp ? "bottom-full mb-1.5" : "top-full mt-1.5"
                        }`}
                    style={{ width: "240px", maxWidth: "240px" }}
                >
                    <div className="text-gray-100">{text}</div>
                    {formula && (
                        <div className="text-gray-400 mt-0.5 font-mono text-[10px]">{formula}</div>
                    )}
                    {/* Arrow pointer */}
                    <div
                        className={`absolute left-1/2 -translate-x-1/2 border-4 border-transparent ${flipUp
                            ? "top-full border-t-gray-800"
                            : "bottom-full border-b-gray-800"
                            }`}
                    />
                </div>
            )}
        </span>
    );
}

// =============================================================================
// Metric Explanations (v1.1: Short, scannable definitions)
// =============================================================================

const METRIC_EXPLANATIONS: Record<string, { text: string; formula?: string }> = {
    // Surface parking metrics
    totalStalls: {
        text: "Total parking spaces that fit the site",
        formula: "Standard + ADA stalls",
    },
    standardStalls: {
        text: "Regular parking spaces",
        formula: "9' × 18' each",
    },
    adaStalls: {
        text: "Accessible spaces with access aisles",
        formula: "11' stall + 5' or 8' aisle",
    },
    totalArea: {
        text: "Gross site boundary area",
        formula: "Before setbacks",
    },
    parkableArea: {
        text: "Net area available for parking",
        formula: "Total − setbacks − constraints",
    },
    usabilityRatio: {
        text: "Parkable area as percentage of total",
        formula: "Parkable ÷ Total × 100",
    },
    efficiency: {
        text: "Site area per stall",
        formula: "Total SF ÷ Stalls • Typical: 300–350 SF",
    },
    areaLostToGeometry: {
        text: "Area lost to site shape or remnants",
        formula: "Unusable gaps between modules",
    },
    // Structured parking metrics
    levels: {
        text: "Number of parking levels",
        formula: "Ground + upper floors",
    },
    grossArea: {
        text: "Total floor area across all levels",
        formula: "Footprint × Levels",
    },
    netParkable: {
        text: "Usable parking area after cores/ramps",
        formula: "Gross − circulation − cores",
    },
    totalHeight: {
        text: "Building height from ground to roof",
        formula: "Level height × Levels",
    },
    stallsLostToRamps: {
        text: "Stalls displaced by ramp footprint",
    },
    stallsLostToCores: {
        text: "Stalls displaced by elevator/stair cores",
    },
    stallsLostToConstraints: {
        text: "Stalls blocked by site constraints",
    },
};

// =============================================================================
// Metric Row Component (v1.1: Standardized tooltip)
// =============================================================================

interface MetricRowProps {
    label: string;
    value: string | number;
    sublabel?: string;
    /** Key into METRIC_EXPLANATIONS */
    infoKey?: keyof typeof METRIC_EXPLANATIONS;
}

function MetricRow({ label, value, sublabel, infoKey }: MetricRowProps) {
    const info = infoKey ? METRIC_EXPLANATIONS[infoKey] : undefined;

    return (
        <div className="flex justify-between items-baseline py-1.5 hover:bg-gray-50 -mx-1 px-1 rounded transition-colors">
            <div className="flex items-center">
                <span className="text-sm text-gray-600">{label}</span>
                {info && <InfoTooltip text={info.text} formula={info.formula} />}
                {sublabel && (
                    <span className="text-xs text-gray-400 ml-1">
                        ({sublabel})
                    </span>
                )}
            </div>
            <span className="text-sm font-medium text-gray-800 tabular-nums">{value}</span>
        </div>
    );
}

// =============================================================================
// Section Header Component
// =============================================================================

interface SectionHeaderProps {
    title: string;
}

function SectionHeader({ title }: SectionHeaderProps) {
    return (
        <h4 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2 mt-4 first:mt-0 pb-1 border-b border-gray-100">
            {title}
        </h4>
    );
}

// =============================================================================
// "How This Result Was Generated" Panel
// =============================================================================

const MODULE_DEPTH_TWO_WAY = 60; // ft: 18ft stall + 24ft aisle + 18ft stall
const MODULE_DEPTH_ONE_WAY = 51; // ft: 18ft stall + 15ft aisle + 18ft stall

// Fixed stall and aisle dimensions used by the parking engine
// ADA stalls include access aisle space in their total width
const STALL_DIMENSIONS = {
    standardWidth: 9,          // ft
    standardLength: 18,        // ft
    // ADA accessible: 11 ft stall + 5 ft access aisle = 16 ft total width
    adaStallWidth: 11,         // ft (parking stall only)
    adaAccessAisle: 5,         // ft (adjacent access aisle)
    adaTotalWidth: 16,         // ft (stall + access aisle combined)
    // Van-accessible: 11 ft stall + 8 ft access aisle = 19 ft total width
    adaVanAccessAisle: 8,      // ft (wider access for van ramp)
    adaVanTotalWidth: 19,      // ft (stall + access aisle combined)
    adaLength: 18,             // ft
    aisleWidthOneWay: 15,      // ft (minimum for one-way 90° parking)
    aisleWidthTwoWay: 24,      // ft (minimum for two-way 90° parking)
} as const;

interface HowGeneratedPanelProps {
    siteBoundary: Polygon | null;
    parkingConfig: ParkingConfig;
    result: SurfaceParkingResult;
}

function HowGeneratedPanel({ siteBoundary, parkingConfig, result }: HowGeneratedPanelProps) {
    if (!siteBoundary) return null;

    const bounds = calculateBounds(siteBoundary);
    const width = bounds.maxX - bounds.minX;
    const height = bounds.maxY - bounds.minY;
    const area = width * height;
    const { metrics } = result;

    // Determine module depth based on aisle direction
    const isTwoWay = parkingConfig.aisleDirection === "TWO_WAY";
    const moduleDepth = isTwoWay ? MODULE_DEPTH_TWO_WAY : MODULE_DEPTH_ONE_WAY;
    const aisleWidth = isTwoWay ? 24 : 15;

    // Calculate how many modules fit and remaining depth
    const effectiveDepth = height - (parkingConfig.setback * 2);
    const modulesThatFit = Math.floor(effectiveDepth / moduleDepth);
    const remainingDepth = effectiveDepth - (modulesThatFit * moduleDepth);

    return (
        <div className="bg-slate-50 border border-slate-200 rounded p-3 mt-4">
            <div className="flex items-center gap-2 mb-3">
                <span className="text-base">🧠</span>
                <h4 className="text-xs font-semibold text-slate-700">
                    How this result was generated
                </h4>
            </div>

            <div className="space-y-3 text-xs text-slate-600">
                {/* Site */}
                <div>
                    <p className="font-medium text-slate-700 mb-1">Site</p>
                    <ul className="list-disc list-inside space-y-0.5 pl-1">
                        <li>Area: {formatArea(area)}</li>
                        <li>Dimensions: {formatNumber(width, 0)}' × {formatNumber(height, 0)}'</li>
                        <li>Shape: Rectangular</li>
                    </ul>
                </div>

                {/* Parking Logic */}
                <div>
                    <p className="font-medium text-slate-700 mb-1">Parking logic</p>
                    <ul className="list-disc list-inside space-y-0.5 pl-1">
                        <li>Parking type: Surface</li>
                        <li>Stall angle: 90°</li>
                        <li>Aisle type: {isTwoWay ? 'Two-way' : 'One-way'} ({aisleWidth} ft)</li>
                        {parkingConfig.uniformSetback !== false ? (
                            <li>Setback: {parkingConfig.setback} ft (all edges)</li>
                        ) : parkingConfig.setbacks ? (
                            <>
                                <li>Setbacks applied:</li>
                                <ul className="list-none pl-3 space-y-0">
                                    <li>North: {parkingConfig.setbacks.north} ft</li>
                                    <li>South: {parkingConfig.setbacks.south} ft</li>
                                    <li>East: {parkingConfig.setbacks.east} ft</li>
                                    <li>West: {parkingConfig.setbacks.west} ft</li>
                                </ul>
                            </>
                        ) : (
                            <li>Setback: {parkingConfig.setback} ft</li>
                        )}
                    </ul>
                </div>

                {/* Fit Analysis */}
                <div>
                    <p className="font-medium text-slate-700 mb-1">Fit analysis</p>
                    <ul className="list-disc list-inside space-y-0.5 pl-1">
                        <li>Standard module depth: {moduleDepth} ft</li>
                        <li>Full modules that fit: {modulesThatFit}</li>
                        <li>Remaining depth: ~{formatNumber(remainingDepth, 0)} ft {remainingDepth < 60 ? '(cannot fit another module)' : ''}</li>
                    </ul>
                </div>

                {/* Result */}
                <div>
                    <p className="font-medium text-slate-700 mb-1">Result</p>
                    <ul className="list-disc list-inside space-y-0.5 pl-1">
                        <li>Total stalls: {formatNumber(metrics.totalStalls)}</li>
                        <li>Area lost to geometry: {formatPercent(metrics.areaLostToGeometryPct)}</li>
                    </ul>
                </div>

                {/* Stall and Aisle Assumptions */}
                <div className="pt-2 border-t border-slate-200">
                    <p className="font-medium text-slate-700 mb-1">Stall and aisle assumptions</p>
                    <p className="text-[10px] text-slate-500 mb-2 italic">
                        Fixed values used for all calculations
                    </p>
                    <div className="space-y-1.5 pl-1">
                        {/* Standard Stall */}
                        <div className="flex justify-between">
                            <span className="text-slate-500">Standard stall:</span>
                            <span className="font-mono text-slate-700">{STALL_DIMENSIONS.standardWidth}' × {STALL_DIMENSIONS.standardLength}'</span>
                        </div>

                        {/* ADA Accessible - Full breakdown */}
                        <div className="bg-blue-50 rounded px-2 py-1.5 -mx-1">
                            <div className="flex justify-between mb-1">
                                <span className="text-slate-600 font-medium">ADA accessible:</span>
                                <span className="font-mono text-blue-700 font-medium">{STALL_DIMENSIONS.adaTotalWidth}' total width</span>
                            </div>
                            <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-slate-500">
                                <span>Stall width:</span>
                                <span className="font-mono text-slate-600">{STALL_DIMENSIONS.adaStallWidth}'</span>
                                <span>Stall length:</span>
                                <span className="font-mono text-slate-600">{STALL_DIMENSIONS.adaLength}'</span>
                                <span>Access aisle:</span>
                                <span className="font-mono text-slate-600">{STALL_DIMENSIONS.adaAccessAisle}' wide × {STALL_DIMENSIONS.adaLength}' deep</span>
                            </div>
                            <p className="text-[10px] text-blue-600 mt-1.5 border-t border-blue-100 pt-1">
                                Van-accessible: {STALL_DIMENSIONS.adaStallWidth}' + {STALL_DIMENSIONS.adaVanAccessAisle}' = {STALL_DIMENSIONS.adaVanTotalWidth}' total
                            </p>
                        </div>

                        {/* Drive Aisles */}
                        <div className="flex justify-between">
                            <span className="text-slate-500">One-way aisle:</span>
                            <span className="font-mono text-slate-700">{STALL_DIMENSIONS.aisleWidthOneWay}'</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-500">Two-way aisle:</span>
                            <span className="font-mono text-slate-700">{STALL_DIMENSIONS.aisleWidthTwoWay}'</span>
                        </div>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-2">
                        ADA dimensions follow generic U.S. standards. Each ADA stall replaces ~2 standard stalls.
                    </p>
                </div>
            </div>
        </div>
    );
}

// =============================================================================
// "Why Not More Stalls?" Hint
// =============================================================================

interface WhyNotMoreStallsProps {
    parkingConfig: ParkingConfig;
    metrics: SurfaceParkingResult['metrics'];
    siteBoundary: Polygon | null;
}

function WhyNotMoreStalls({ parkingConfig, metrics, siteBoundary }: WhyNotMoreStallsProps) {
    const reasons: string[] = [];

    // Two-way aisle explanation
    if (parkingConfig.aisleDirection === "TWO_WAY") {
        reasons.push("Two-way aisles require wider drive lanes (24 ft vs 15 ft)");
    }

    // Site depth limitation
    if (siteBoundary) {
        const bounds = calculateBounds(siteBoundary);
        const height = bounds.maxY - bounds.minY;
        const moduleDepth = parkingConfig.aisleDirection === "TWO_WAY" ? 60 : 51;
        const effectiveDepth = height - (parkingConfig.setback * 2);
        const remainingDepth = effectiveDepth % moduleDepth;

        if (remainingDepth > 0 && remainingDepth < moduleDepth) {
            reasons.push("Site depth limits additional parking rows");
        }
        if (remainingDepth < moduleDepth) {
            reasons.push("Remaining geometry cannot fit a full parking module");
        }
    }

    // Setback impact
    const setbacks = parkingConfig.setbacks;
    if (setbacks) {
        const totalSetback = setbacks.north + setbacks.south + setbacks.east + setbacks.west;
        if (totalSetback > 0) {
            if (parkingConfig.uniformSetback !== false) {
                reasons.push(`${parkingConfig.setback} ft setback reduces usable area`);
            } else {
                reasons.push(`Per-edge setbacks reduce usable area`);
            }
        }
    } else if (parkingConfig.setback > 0) {
        reasons.push(`${parkingConfig.setback} ft setback reduces usable area`);
    }

    // Geometry loss
    if (metrics.areaLostToGeometryPct > 5) {
        reasons.push(`${formatPercent(metrics.areaLostToGeometryPct)} of area lost to geometry`);
    }

    if (reasons.length === 0) return null;

    return (
        <div className="bg-amber-50 border border-amber-100 rounded px-3 py-2 mt-2">
            <div className="flex items-start gap-2">
                <span className="text-sm">💡</span>
                <div>
                    <p className="text-xs font-medium text-amber-800 mb-1">
                        Why not more stalls?
                    </p>
                    <ul className="text-xs text-amber-700 space-y-0.5">
                        {reasons.slice(0, 3).map((reason, i) => (
                            <li key={i}>• {reason}</li>
                        ))}
                    </ul>
                </div>
            </div>
        </div>
    );
}

// =============================================================================
// Surface Metrics Component
// =============================================================================

interface SurfaceMetricsProps {
    result: SurfaceParkingResult;
    siteBoundary: Polygon | null;
    parkingConfig: ParkingConfig;
}

/**
 * Zero Stalls Warning Component
 * Displays when the site produces 0 parking stalls.
 */
function ZeroStallsWarning({ siteBoundary, parkingConfig }: { siteBoundary: Polygon | null; parkingConfig: ParkingConfig }) {
    return (
        <div className="bg-amber-50 border border-amber-200 rounded p-4 mb-3">
            <div className="flex items-start gap-3">
                <svg
                    className="w-6 h-6 text-amber-500 flex-shrink-0 mt-0.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                </svg>
                <div>
                    <p className="text-sm font-semibold text-amber-800">
                        No parking stalls fit this site
                    </p>
                    <p className="text-xs text-amber-700 mt-1">
                        The site may be too narrow, too small, or constraints may be blocking available space.
                    </p>
                    <div className="mt-2 text-xs text-amber-600">
                        <p className="font-medium mb-1">Try adjusting:</p>
                        <ul className="list-disc list-inside space-y-0.5">
                            <li>Increase site dimensions</li>
                            <li>Reduce setbacks {parkingConfig.uniformSetback !== false ? `(currently ${parkingConfig.setback} ft)` : "(currently per-edge)"}</li>
                            <li>Remove or reduce constraints</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
}

function SurfaceMetrics({ result, siteBoundary, parkingConfig }: SurfaceMetricsProps) {
    const { metrics } = result;
    const isZeroStalls = metrics.totalStalls === 0;

    // Show zero stalls warning instead of normal display
    if (isZeroStalls) {
        return (
            <div>
                <ZeroStallsWarning siteBoundary={siteBoundary} parkingConfig={parkingConfig} />

                {/* Still show area info for context */}
                <div className="divide-y divide-gray-100 mt-4">
                    <div className="py-3">
                        <SectionHeader title="Site Analysis" />
                        <MetricRow
                            label="Total Site Area"
                            value={formatArea(metrics.totalArea)}
                            infoKey="totalArea"
                        />
                        <MetricRow
                            label="Parkable Area"
                            value={formatArea(metrics.parkableArea)}
                            infoKey="parkableArea"
                        />
                        <MetricRow
                            label="Usability Ratio"
                            value={formatPercent(metrics.usabilityRatio * 100)}
                            infoKey="usabilityRatio"
                        />
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div>
            {/* Primary Result - Stall Count */}
            <div className="bg-gradient-to-b from-green-50 to-green-100/50 border border-green-200 rounded-lg p-4 mb-3">
                <div className="text-center">
                    <p className="text-4xl font-bold text-green-800 tracking-tight">
                        {formatNumber(metrics.totalStalls)}
                    </p>
                    <p className="text-sm text-green-700 font-medium flex items-center justify-center gap-1 mt-1">
                        Total Stalls
                        <InfoTooltip text={METRIC_EXPLANATIONS.totalStalls.text} formula={METRIC_EXPLANATIONS.totalStalls.formula} />
                    </p>
                </div>
                <div className="flex justify-center gap-4 mt-3 text-xs text-green-600 border-t border-green-200/50 pt-2">
                    <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-sm bg-green-500"></span>
                        {formatNumber(metrics.standardStalls)} standard
                    </span>
                    <span className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-sm bg-blue-500"></span>
                        {formatNumber(metrics.adaStalls)} ADA
                    </span>
                </div>
            </div>

            {/* Why Not More Stalls */}
            <WhyNotMoreStalls
                parkingConfig={parkingConfig}
                metrics={metrics}
                siteBoundary={siteBoundary}
            />

            <div className="divide-y divide-gray-100 mt-4">
                <div className="py-3">
                    <SectionHeader title="Area" />
                    <MetricRow
                        label="Total Site Area"
                        value={formatArea(metrics.totalArea)}
                        infoKey="totalArea"
                    />
                    <MetricRow
                        label="Parkable Area"
                        value={formatArea(metrics.parkableArea)}
                        infoKey="parkableArea"
                    />
                    <MetricRow
                        label="Usability Ratio"
                        value={formatPercent(metrics.usabilityRatio * 100)}
                        infoKey="usabilityRatio"
                    />
                </div>

                <div className="py-3">
                    <SectionHeader title="Efficiency" />
                    <MetricRow
                        label="Efficiency"
                        value={formatEfficiency(metrics.efficiencySfPerStall)}
                        infoKey="efficiency"
                    />
                    <MetricRow
                        label="Area Lost to Geometry"
                        value={formatPercent(metrics.areaLostToGeometryPct)}
                        infoKey="areaLostToGeometry"
                    />
                </div>
            </div>

            {/* How This Result Was Generated */}
            <HowGeneratedPanel
                siteBoundary={siteBoundary}
                parkingConfig={parkingConfig}
                result={result}
            />
        </div>
    );
}

// =============================================================================
// Structured Metrics Component
// =============================================================================

interface StructuredMetricsProps {
    result: StructuredParkingResult;
}

function StructuredMetrics({ result }: StructuredMetricsProps) {
    const { metrics } = result;

    return (
        <div className="divide-y divide-gray-100">
            <div className="pb-3">
                <SectionHeader title="Stall Count" />
                <MetricRow
                    label="Total Stalls"
                    value={formatNumber(metrics.totalStalls)}
                    infoKey="totalStalls"
                />
                <MetricRow
                    label="Levels"
                    value={formatNumber(metrics.levelCount)}
                    infoKey="levels"
                />
            </div>

            <div className="py-3">
                <SectionHeader title="Stalls by Level" />
                {metrics.stallsPerLevel.map((count, index) => (
                    <MetricRow
                        key={index}
                        label={`Level ${index + 1}`}
                        value={formatNumber(count)}
                    />
                ))}
            </div>

            <div className="py-3">
                <SectionHeader title="Area" />
                <MetricRow
                    label="Gross Area"
                    value={formatArea(metrics.grossArea)}
                    infoKey="grossArea"
                />
                <MetricRow
                    label="Net Parkable"
                    value={formatArea(metrics.netParkableArea)}
                    infoKey="netParkable"
                />
                <MetricRow
                    label="Total Height"
                    value={`${formatNumber(metrics.totalHeight, 1)}'`}
                    infoKey="totalHeight"
                />
            </div>

            <div className="py-3">
                <SectionHeader title="Efficiency" />
                <MetricRow
                    label="Efficiency"
                    value={formatEfficiency(metrics.efficiencySfPerStall)}
                    infoKey="efficiency"
                />
            </div>

            <div className="py-3">
                <SectionHeader title="Stalls Lost" />
                <MetricRow
                    label="To Ramps"
                    value={formatNumber(metrics.stallsLostToRamps)}
                    infoKey="stallsLostToRamps"
                />
                <MetricRow
                    label="To Cores"
                    value={formatNumber(metrics.stallsLostToCores)}
                    infoKey="stallsLostToCores"
                />
                <MetricRow
                    label="To Constraints"
                    value={formatNumber(metrics.stallsLostToConstraints)}
                    infoKey="stallsLostToConstraints"
                />
            </div>
        </div>
    );
}

// =============================================================================
// Constraint Impact Component
// =============================================================================

interface ConstraintImpactDisplayProps {
    impact: ConstraintImpact;
}

function ConstraintImpactDisplay({ impact }: ConstraintImpactDisplayProps) {
    const entries = Object.entries(impact.impactByType) as [
        ConstraintType,
        number
    ][];
    const nonZeroEntries = entries.filter(([, count]) => count > 0);

    if (nonZeroEntries.length === 0) {
        return null;
    }

    return (
        <div className="bg-amber-50 border border-amber-200 rounded p-3 mt-4">
            <h4 className="text-xs font-semibold text-amber-800 mb-2">
                Constraint Impact
            </h4>
            <div className="space-y-1">
                {nonZeroEntries.map(([type, count]) => (
                    <div
                        key={type}
                        className="flex items-center justify-between text-xs"
                    >
                        <div className="flex items-center gap-2">
                            <div
                                className="w-2 h-2 rounded-full"
                                style={{
                                    backgroundColor: CONSTRAINT_COLORS[type],
                                }}
                            />
                            <span className="text-amber-700">
                                {CONSTRAINT_LABELS[type]}
                            </span>
                        </div>
                        <span className="font-medium text-amber-900">
                            -{count} stalls
                        </span>
                    </div>
                ))}
            </div>
            <div className="border-t border-amber-200 mt-2 pt-2">
                <div className="flex justify-between text-xs">
                    <span className="text-amber-700">Total Stalls Removed</span>
                    <span className="font-semibold text-amber-900">
                        {impact.totalStallsRemoved}
                    </span>
                </div>
                <div className="flex justify-between text-xs mt-1">
                    <span className="text-amber-700">Area Lost</span>
                    <span className="font-medium text-amber-900">
                        {formatArea(impact.totalAreaLost)}
                    </span>
                </div>
                <div className="flex justify-between text-xs mt-1">
                    <span className="text-amber-700">Efficiency Impact</span>
                    <span className="font-medium text-amber-900">
                        -{formatPercent(impact.efficiencyLossPct)}
                    </span>
                </div>
            </div>
        </div>
    );
}

// =============================================================================
// No Results State
// =============================================================================

function NoResults() {
    return (
        <div className="text-center py-8 text-gray-500">
            <svg
                className="w-12 h-12 mx-auto mb-3 text-gray-300"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1}
                    d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
            </svg>
            <p className="text-sm font-medium text-gray-600">Ready to evaluate</p>
            <p className="text-xs mt-1">
                Enter site dimensions in the left panel, then results will appear here.
            </p>
        </div>
    );
}

// =============================================================================
// Loading State
// =============================================================================

function Loading() {
    return (
        <div className="text-center py-8 text-gray-500">
            <svg
                className="animate-spin w-8 h-8 mx-auto mb-3 text-blue-500"
                fill="none"
                viewBox="0 0 24 24"
            >
                <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                />
                <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
            </svg>
            <p className="text-sm">Evaluating...</p>
        </div>
    );
}

// =============================================================================
// Error State
// =============================================================================

interface ErrorDisplayProps {
    message: string;
}

/**
 * Maps technical error messages to user-friendly explanations.
 */
function getFriendlyErrorMessage(message: string): { title: string; detail: string } {
    const lower = message.toLowerCase();

    if (lower.includes('fetch') || lower.includes('network') || lower.includes('failed to fetch')) {
        return {
            title: "Unable to connect",
            detail: "The parking engine is temporarily unavailable. Please try again in a moment."
        };
    }
    if (lower.includes('timeout') || lower.includes('timed out')) {
        return {
            title: "Request timed out",
            detail: "The calculation took too long. Try a smaller site or fewer constraints."
        };
    }
    if (lower.includes('too small') || lower.includes('minimum')) {
        return {
            title: "Site too small",
            detail: "The site dimensions are below the minimum required for parking. Try a larger area (at least 50' × 50')."
        };
    }
    if (lower.includes('invalid') || lower.includes('polygon')) {
        return {
            title: "Invalid site shape",
            detail: "The site boundary couldn't be processed. Try a simpler rectangular shape."
        };
    }

    // Default fallback
    return {
        title: "Evaluation couldn't complete",
        detail: "Something went wrong. Please check your inputs and try again."
    };
}

function ErrorDisplay({ message }: ErrorDisplayProps) {
    const friendly = getFriendlyErrorMessage(message);

    return (
        <div className="bg-red-50 border border-red-200 rounded p-3">
            <div className="flex items-start gap-2">
                <svg
                    className="w-5 h-5 text-red-500 flex-shrink-0"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                </svg>
                <div>
                    <p className="text-sm font-medium text-red-800">
                        {friendly.title}
                    </p>
                    <p className="text-xs text-red-600 mt-1">{friendly.detail}</p>
                </div>
            </div>
        </div>
    );
}

// =============================================================================
// Export DXF Button
// =============================================================================

interface ExportDxfButtonProps {
    siteBoundary: Polygon;
    parkingConfig: ParkingConfig;
    disabled?: boolean;
}

function ExportDxfButton({ siteBoundary, parkingConfig, disabled }: ExportDxfButtonProps) {
    const [isExporting, setIsExporting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleExport = useCallback(async () => {
        setIsExporting(true);
        setError(null);

        try {
            const blob = await exportParkingDxf(siteBoundary, parkingConfig);

            // Create download link
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "parking_layout.dxf";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (err) {
            const message = err instanceof ParkingApiError
                ? err.message
                : "Export failed";
            setError(message);
        } finally {
            setIsExporting(false);
        }
    }, [siteBoundary, parkingConfig]);

    return (
        <div className="mt-4">
            <button
                onClick={handleExport}
                disabled={disabled || isExporting}
                className={`
                    w-full py-2 px-4 rounded font-medium text-sm
                    flex items-center justify-center gap-2
                    transition-colors
                    ${disabled || isExporting
                        ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                        : "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800"
                    }
                `}
            >
                {isExporting ? (
                    <>
                        <svg
                            className="animate-spin w-4 h-4"
                            fill="none"
                            viewBox="0 0 24 24"
                        >
                            <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                            />
                            <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            />
                        </svg>
                        Exporting...
                    </>
                ) : (
                    <>
                        <svg
                            className="w-4 h-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                            />
                        </svg>
                        Export DXF
                    </>
                )}
            </button>
            {error && (
                <p className="text-xs text-red-600 mt-1 text-center">{error}</p>
            )}
        </div>
    );
}

// =============================================================================
// Export Excel Button
// =============================================================================

interface ExportExcelButtonProps {
    activeScenario: Scenario;
    allScenarios: readonly Scenario[];
    disabled?: boolean;
}

function ExportExcelButton({ activeScenario, allScenarios, disabled }: ExportExcelButtonProps) {
    const handleExport = useCallback(() => {
        try {
            exportToExcel({
                activeScenario,
                allScenarios,
            });
        } catch (err) {
            console.error("Excel export failed:", err);
        }
    }, [activeScenario, allScenarios]);

    return (
        <button
            onClick={handleExport}
            disabled={disabled}
            className={`
                w-full py-2 px-4 rounded font-medium text-sm
                flex items-center justify-center gap-2
                transition-colors
                ${disabled
                    ? "bg-gray-200 text-gray-500 cursor-not-allowed"
                    : "bg-emerald-600 text-white hover:bg-emerald-700 active:bg-emerald-800"
                }
            `}
        >
            <svg
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
            </svg>
            Export Excel
        </button>
    );
}

// =============================================================================
// Main Component
// =============================================================================

export function MetricsPanel() {
    const { activeScenario, state } = useScenario();

    if (!activeScenario) {
        return (
            <div className="p-4 text-sm text-gray-500">
                Create a scenario to see metrics.
            </div>
        );
    }

    const { status, result, error } = activeScenario;

    return (
        <div className="p-4">
            <h3 className="text-sm font-semibold text-gray-900 mb-4">
                Results & Metrics
            </h3>

            {/* Disclaimer */}
            <div className="bg-blue-50 border border-blue-200 rounded px-3 py-2 mb-4">
                <p className="text-xs text-blue-700">
                    Conceptual, rule-based estimate for early feasibility only.
                </p>
            </div>

            {/* Content based on status */}
            {status === "evaluating" && <Loading />}

            {status === "error" && error && <ErrorDisplay message={error} />}

            {status === "draft" && !result && <NoResults />}

            {result && (
                <>
                    {result.parkingResult.type === "surface" ? (
                        <SurfaceMetrics
                            result={result.parkingResult}
                            siteBoundary={activeScenario.siteBoundary}
                            parkingConfig={activeScenario.parkingConfig}
                        />
                    ) : (
                        <StructuredMetrics result={result.parkingResult} />
                    )}

                    {result.constraintImpact && (
                        <ConstraintImpactDisplay
                            impact={result.constraintImpact}
                        />
                    )}

                    {/* Warnings */}
                    {result.warnings.length > 0 && (
                        <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded p-3">
                            <p className="text-xs font-medium text-yellow-800 mb-1">
                                Warnings
                            </p>
                            <ul className="text-xs text-yellow-700 list-disc list-inside">
                                {result.warnings.map((w, i) => (
                                    <li key={i}>{w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Export Buttons */}
                    <div className="mt-4 space-y-2">
                        {/* Export DXF Button - only for surface parking with results */}
                        {result.parkingResult.type === "surface" &&
                            result.parkingResult.metrics.totalStalls > 0 &&
                            activeScenario.siteBoundary && (
                                <ExportDxfButton
                                    siteBoundary={activeScenario.siteBoundary}
                                    parkingConfig={activeScenario.parkingConfig}
                                />
                            )}

                        {/* Export Excel Button - available for all evaluated scenarios */}
                        <ExportExcelButton
                            activeScenario={activeScenario}
                            allScenarios={state.scenarios}
                        />
                    </div>

                    {/* Timestamp */}
                    <p className="text-xs text-gray-400 mt-4">
                        Generated:{" "}
                        {new Date(result.timestamp).toLocaleString()}
                    </p>
                </>
            )}
        </div>
    );
}
