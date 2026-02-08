/**
 * GenFabTools Parking Engine - Zones Layer
 *
 * Renders parking zones for irregular layouts.
 * Read-only rendering - no editing.
 */

import React from "react";
import type { ParkingZone, ViewportState } from "../../types";
import { worldToScreen, ZONE_COLORS } from "../../utils";

interface ZonesLayerProps {
    zones: readonly ParkingZone[];
    viewport: ViewportState;
    canvasHeight: number;
}

export function ZonesLayer({
    zones,
    viewport,
    canvasHeight,
}: ZonesLayerProps) {
    if (zones.length === 0) {
        return null;
    }

    return (
        <g className="zones-layer">
            {zones.map((zone) => {
                const { geometry, zoneType, id } = zone;

                // Skip zones without geometry (e.g., v2 zones are metadata-only)
                if (!geometry?.points || geometry.points.length < 3) {
                    return null;
                }

                // Convert world coordinates to screen coordinates
                const screenPoints = geometry.points.map((p) =>
                    worldToScreen(p, viewport, canvasHeight)
                );

                // Create SVG path
                const pathData =
                    screenPoints
                        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
                        .join(" ") + " Z";

                const fillColor = ZONE_COLORS[zoneType];

                return (
                    <path
                        key={id}
                        d={pathData}
                        fill={fillColor}
                        stroke="none"
                    />
                );
            })}
        </g>
    );
}
