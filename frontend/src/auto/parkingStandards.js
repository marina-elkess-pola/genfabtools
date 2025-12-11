/**
 * Parking Standards Resolver
 * 
 * Provides code-compliant circulation and stall parameters based on
 * the selected building code (IBC, UK ADB, Canada NBC, etc.)
 * 
 * All dimensions are in meters.
 */

import parkingStandardsData from '../parking_standards.json';

const DEFAULT_CODE = 'GENERIC';

/**
 * Get the list of available parking standard codes
 * @returns {Array<{code: string, label: string}>}
 */
export function getAvailableParkingCodes() {
    return Object.entries(parkingStandardsData).map(([code, data]) => ({
        code,
        label: data.label || code
    }));
}

/**
 * Get parking standards for a specific code
 * @param {string} codeSet - The code set identifier (e.g., 'IBC_2024', 'UK_ADB_2023')
 * @returns {Object} The parking standards object
 */
export function getParkingStandards(codeSet) {
    const standards = parkingStandardsData[codeSet] || parkingStandardsData[DEFAULT_CODE];
    if (!standards) {
        console.warn(`[parkingStandards] Code set '${codeSet}' not found, using GENERIC`);
        return parkingStandardsData[DEFAULT_CODE];
    }
    return standards;
}

/**
 * Resolve circulation widths based on code and aisle type
 * @param {string} codeSet - The code set identifier
 * @param {string} aisleType - 'one-way' | 'two-way'
 * @returns {Object} Circulation parameters in meters
 */
export function resolveCirculationParams(codeSet, aisleType = 'two-way') {
    const standards = getParkingStandards(codeSet);
    const circ = standards.circulation || {};

    const driveWidth = aisleType === 'one-way'
        ? (circ.driveAisleWidthOneWay || 3.5)
        : (circ.driveAisleWidthTwoWay || 6.0);

    return {
        driveWidth,
        fireLaneWidth: circ.fireLaneWidth || 6.0,
        accessLaneWidth: circ.accessLaneWidth || 3.5,
        turningRadiusMin: circ.turningRadiusMin || 6.0,
        entryLaneWidth: circ.entryLaneWidth || 3.5,
        exitLaneWidth: circ.exitLaneWidth || 3.5
    };
}

/**
 * Resolve stall dimensions based on code and stall type
 * @param {string} codeSet - The code set identifier
 * @param {string} stallType - 'standard' | 'compact' | 'accessible'
 * @returns {Object} Stall dimensions in meters
 */
export function resolveStallParams(codeSet, stallType = 'standard') {
    const standards = getParkingStandards(codeSet);
    const stalls = standards.stalls || {};

    let width, depth, aisleWidth;

    switch (stallType) {
        case 'compact':
            width = stalls.compactWidth || 2.3;
            depth = stalls.compactDepth || 4.5;
            aisleWidth = 0;
            break;
        case 'accessible':
            width = stalls.accessibleWidth || 3.5;
            depth = stalls.accessibleDepth || 5.0;
            aisleWidth = stalls.accessibleAisleWidth || 1.5;
            break;
        default: // standard
            width = stalls.standardWidth || 2.5;
            depth = stalls.standardDepth || 5.0;
            aisleWidth = 0;
    }

    return {
        width,
        depth,
        aisleWidth,
        accessibleRatio: stalls.accessibleRatio || 0.02
    };
}

/**
 * Get recommended stall angles for a code set
 * @param {string} codeSet - The code set identifier
 * @returns {number[]} Array of angles in degrees
 */
export function getRecommendedAngles(codeSet) {
    const standards = getParkingStandards(codeSet);
    return standards.angles || [90, 60, 45];
}

/**
 * Normalize generator parameters using code-based standards
 * This function merges user-provided params with code-based defaults
 * @param {Object} params - User-provided parameters
 * @returns {Object} Normalized parameters with code-based values
 */
export function normalizeWithCodeStandards(params) {
    const codeSet = params.codeSet || params.parkingCode || DEFAULT_CODE;
    const aisleType = params.aisleType || 'two-way';
    const stallType = params.stallType || 'standard';

    const circ = resolveCirculationParams(codeSet, aisleType);
    const stall = resolveStallParams(codeSet, stallType);
    const angles = getRecommendedAngles(codeSet);

    // Merge: user params override code-based defaults
    return {
        // Code-based circulation (can be overridden)
        driveWidth: params.driveWidth ?? circ.driveWidth,
        fireLaneWidth: params.fireLaneWidth ?? circ.fireLaneWidth,
        accessLaneWidth: params.accessLaneWidth ?? circ.accessLaneWidth,
        turningRadiusMin: params.turningRadiusMin ?? circ.turningRadiusMin,
        entryLaneWidth: params.entryLaneWidth ?? circ.entryLaneWidth,
        exitLaneWidth: params.exitLaneWidth ?? circ.exitLaneWidth,

        // Code-based stall dimensions (can be overridden)
        stallWidth: params.stallWidth ?? stall.width,
        stallDepth: params.stallDepth ?? stall.depth,
        accessibleAisleWidth: params.accessibleAisleWidth ?? stall.aisleWidth,
        accessibleRatio: params.accessibleRatio ?? stall.accessibleRatio,

        // Code-based angles (can be overridden)
        stallAngles: params.stallAngles ?? angles,

        // Pass through other params unchanged
        codeSet,
        aisleType,
        stallType,
        ...params
    };
}

export default {
    getAvailableParkingCodes,
    getParkingStandards,
    resolveCirculationParams,
    resolveStallParams,
    getRecommendedAngles,
    normalizeWithCodeStandards
};
