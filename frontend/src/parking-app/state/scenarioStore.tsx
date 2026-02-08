/**
 * GenFabTools Parking Engine - Scenario State Management
 *
 * Immutable scenario-based state management using React Context.
 * All user actions create new scenarios - no mutation of results.
 */

import React, {
    createContext,
    useContext,
    useReducer,
    useCallback,
    type ReactNode,
} from "react";
import type {
    Scenario,
    ScenarioStatus,
    Polygon,
    ParkingConfig,
    Setbacks,
    ImportedConstraint,
    EvaluationResult,
    CanvasState,
    ViewportState,
    LayerVisibility,
} from "../types";

// =============================================================================
// Default Values
// =============================================================================

const DEFAULT_SETBACKS: Setbacks = {
    north: 5.0,
    south: 5.0,
    east: 5.0,
    west: 5.0,
};

const DEFAULT_PARKING_CONFIG: ParkingConfig = {
    parkingType: "surface",
    aisleDirection: "TWO_WAY",
    stallAngle: 90,
    setback: 5.0,
    setbacks: DEFAULT_SETBACKS,
    uniformSetback: true,
};

const DEFAULT_VIEWPORT: ViewportState = {
    panX: 0,
    panY: 0,
    zoom: 1,
};

const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
    siteBoundary: true,
    constraints: true,
    stalls: true,
    aisles: true,
    ramps: true,
    cores: true,
    zones: true,
};

const DEFAULT_CANVAS_STATE: CanvasState = {
    viewport: DEFAULT_VIEWPORT,
    layerVisibility: DEFAULT_LAYER_VISIBILITY,
    selectedLevel: 0,
};

// =============================================================================
// State Types
// =============================================================================

interface ScenarioState {
    readonly scenarios: readonly Scenario[];
    readonly activeScenarioId: string | null;
    readonly comparisonScenarioId: string | null;
    readonly canvasState: CanvasState;
}

// =============================================================================
// Action Types
// =============================================================================

type ScenarioAction =
    | { type: "CREATE_SCENARIO"; payload: { name?: string } }
    | { type: "SET_ACTIVE_SCENARIO"; payload: { id: string } }
    | { type: "SET_COMPARISON_SCENARIO"; payload: { id: string | null } }
    | { type: "DELETE_SCENARIO"; payload: { id: string } }
    | { type: "DUPLICATE_SCENARIO"; payload: { id: string; name?: string } }
    | { type: "RENAME_SCENARIO"; payload: { id: string; name: string } }
    | {
        type: "SET_SITE_BOUNDARY";
        payload: { scenarioId: string; siteBoundary: Polygon | null };
    }
    | {
        type: "SET_PARKING_CONFIG";
        payload: { scenarioId: string; config: Partial<ParkingConfig> };
    }
    | {
        type: "SET_CONSTRAINTS";
        payload: {
            scenarioId: string;
            constraints: readonly ImportedConstraint[];
        };
    }
    | {
        type: "TOGGLE_CONSTRAINTS";
        payload: { scenarioId: string; enabled: boolean };
    }
    | {
        type: "SET_SCENARIO_STATUS";
        payload: { scenarioId: string; status: ScenarioStatus; error?: string };
    }
    | {
        type: "SET_EVALUATION_RESULT";
        payload: { scenarioId: string; result: EvaluationResult };
    }
    | { type: "SET_VIEWPORT"; payload: ViewportState }
    | { type: "SET_LAYER_VISIBILITY"; payload: Partial<LayerVisibility> }
    | { type: "SET_SELECTED_LEVEL"; payload: number }
    | { type: "RESET_VIEWPORT" };

// =============================================================================
// Helper Functions
// =============================================================================

function generateId(): string {
    return `scenario_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Generate a stable scenario letter (A, B, C, ..., Z, AA, AB, ...)
 * based on a counter value, not array position.
 */
function getScenarioLetter(index: number): string {
    let result = '';
    let n = index;
    while (n >= 0) {
        result = String.fromCharCode(65 + (n % 26)) + result;
        n = Math.floor(n / 26) - 1;
    }
    return result;
}

/**
 * Find the next available scenario letter that doesn't conflict with existing names.
 * This ensures stable naming even after deletions.
 */
function getNextScenarioName(scenarios: readonly Scenario[]): string {
    const existingNames = new Set(scenarios.map(s => s.name));
    let counter = 0;
    while (true) {
        const candidateName = `Scenario ${getScenarioLetter(counter)}`;
        if (!existingNames.has(candidateName)) {
            return candidateName;
        }
        counter++;
        // Safety: prevent infinite loop (26^2 = 676 scenarios should be enough)
        if (counter > 702) {
            return `Scenario ${Date.now()}`;
        }
    }
}

function createNewScenario(name: string): Scenario {
    return {
        id: generateId(),
        name,
        createdAt: new Date().toISOString(),
        status: "draft",
        siteBoundary: null,
        parkingConfig: DEFAULT_PARKING_CONFIG,
        constraintsEnabled: false,
        constraints: [],
    };
}

function updateScenario(
    scenarios: readonly Scenario[],
    scenarioId: string,
    updates: Partial<Scenario>
): readonly Scenario[] {
    return scenarios.map((s) =>
        s.id === scenarioId ? { ...s, ...updates } : s
    );
}

// =============================================================================
// Reducer
// =============================================================================

function scenarioReducer(
    state: ScenarioState,
    action: ScenarioAction
): ScenarioState {
    switch (action.type) {
        case "CREATE_SCENARIO": {
            const scenarioName = action.payload.name || getNextScenarioName(state.scenarios);
            const newScenario = createNewScenario(scenarioName);
            return {
                ...state,
                scenarios: [...state.scenarios, newScenario],
                activeScenarioId: newScenario.id,
            };
        }

        case "SET_ACTIVE_SCENARIO": {
            return {
                ...state,
                activeScenarioId: action.payload.id,
            };
        }

        case "SET_COMPARISON_SCENARIO": {
            return {
                ...state,
                comparisonScenarioId: action.payload.id,
            };
        }

        case "DELETE_SCENARIO": {
            const filtered = state.scenarios.filter(
                (s) => s.id !== action.payload.id
            );
            return {
                ...state,
                scenarios: filtered,
                activeScenarioId:
                    state.activeScenarioId === action.payload.id
                        ? filtered[0]?.id || null
                        : state.activeScenarioId,
                comparisonScenarioId:
                    state.comparisonScenarioId === action.payload.id
                        ? null
                        : state.comparisonScenarioId,
            };
        }

        case "DUPLICATE_SCENARIO": {
            const source = state.scenarios.find((s) => s.id === action.payload.id);
            if (!source) return state;
            const duplicate: Scenario = {
                ...source,
                id: generateId(),
                name: action.payload.name || `${source.name} (Copy)`,
                createdAt: new Date().toISOString(),
                status: "draft",
                result: undefined,
                error: undefined,
            };
            return {
                ...state,
                scenarios: [...state.scenarios, duplicate],
                activeScenarioId: duplicate.id,
            };
        }

        case "RENAME_SCENARIO": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.id,
                    { name: action.payload.name }
                ),
            };
        }

        case "SET_SITE_BOUNDARY": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        siteBoundary: action.payload.siteBoundary,
                        status: "draft",
                        result: undefined,
                    }
                ),
            };
        }

        case "SET_PARKING_CONFIG": {
            const scenario = state.scenarios.find(
                (s) => s.id === action.payload.scenarioId
            );
            if (!scenario) return state;
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        parkingConfig: {
                            ...scenario.parkingConfig,
                            ...action.payload.config,
                        },
                        status: "draft",
                        result: undefined,
                    }
                ),
            };
        }

        case "SET_CONSTRAINTS": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        constraints: action.payload.constraints,
                        status: "draft",
                        result: undefined,
                    }
                ),
            };
        }

        case "TOGGLE_CONSTRAINTS": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        constraintsEnabled: action.payload.enabled,
                        status: "draft",
                        result: undefined,
                    }
                ),
            };
        }

        case "SET_SCENARIO_STATUS": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        status: action.payload.status,
                        error: action.payload.error,
                    }
                ),
            };
        }

        case "SET_EVALUATION_RESULT": {
            return {
                ...state,
                scenarios: updateScenario(
                    state.scenarios,
                    action.payload.scenarioId,
                    {
                        result: action.payload.result,
                        status: "complete",
                        error: undefined,
                    }
                ),
            };
        }

        case "SET_VIEWPORT": {
            return {
                ...state,
                canvasState: {
                    ...state.canvasState,
                    viewport: action.payload,
                },
            };
        }

        case "SET_LAYER_VISIBILITY": {
            return {
                ...state,
                canvasState: {
                    ...state.canvasState,
                    layerVisibility: {
                        ...state.canvasState.layerVisibility,
                        ...action.payload,
                    },
                },
            };
        }

        case "SET_SELECTED_LEVEL": {
            return {
                ...state,
                canvasState: {
                    ...state.canvasState,
                    selectedLevel: action.payload,
                },
            };
        }

        case "RESET_VIEWPORT": {
            return {
                ...state,
                canvasState: {
                    ...state.canvasState,
                    viewport: DEFAULT_VIEWPORT,
                },
            };
        }

        default:
            return state;
    }
}

// =============================================================================
// Context
// =============================================================================

interface ScenarioContextValue {
    state: ScenarioState;
    dispatch: React.Dispatch<ScenarioAction>;
    // Convenience getters
    activeScenario: Scenario | null;
    comparisonScenario: Scenario | null;
    // Convenience actions
    createScenario: (name?: string) => void;
    setActiveScenario: (id: string) => void;
    deleteScenario: (id: string) => void;
    duplicateScenario: (id: string, name?: string) => void;
    renameScenario: (id: string, name: string) => void;
    setSiteBoundary: (scenarioId: string, boundary: Polygon | null) => void;
    setParkingConfig: (
        scenarioId: string,
        config: Partial<ParkingConfig>
    ) => void;
    setConstraints: (
        scenarioId: string,
        constraints: readonly ImportedConstraint[]
    ) => void;
    toggleConstraints: (scenarioId: string, enabled: boolean) => void;
    setEvaluationResult: (
        scenarioId: string,
        result: EvaluationResult
    ) => void;
    setScenarioStatus: (
        scenarioId: string,
        status: ScenarioStatus,
        error?: string
    ) => void;
}

const ScenarioContext = createContext<ScenarioContextValue | null>(null);

// =============================================================================
// Provider
// =============================================================================

interface ScenarioProviderProps {
    children: ReactNode;
}

const initialState: ScenarioState = {
    scenarios: [],
    activeScenarioId: null,
    comparisonScenarioId: null,
    canvasState: DEFAULT_CANVAS_STATE,
};

export function ScenarioProvider({ children }: ScenarioProviderProps) {
    const [state, dispatch] = useReducer(scenarioReducer, initialState);

    const activeScenario =
        state.scenarios.find((s) => s.id === state.activeScenarioId) || null;
    const comparisonScenario =
        state.scenarios.find((s) => s.id === state.comparisonScenarioId) || null;

    const createScenario = useCallback((name?: string) => {
        dispatch({ type: "CREATE_SCENARIO", payload: { name } });
    }, []);

    const setActiveScenario = useCallback((id: string) => {
        dispatch({ type: "SET_ACTIVE_SCENARIO", payload: { id } });
    }, []);

    const deleteScenario = useCallback((id: string) => {
        dispatch({ type: "DELETE_SCENARIO", payload: { id } });
    }, []);

    const duplicateScenario = useCallback((id: string, name?: string) => {
        dispatch({ type: "DUPLICATE_SCENARIO", payload: { id, name } });
    }, []);

    const renameScenario = useCallback((id: string, name: string) => {
        dispatch({ type: "RENAME_SCENARIO", payload: { id, name } });
    }, []);

    const setSiteBoundary = useCallback(
        (scenarioId: string, siteBoundary: Polygon | null) => {
            dispatch({
                type: "SET_SITE_BOUNDARY",
                payload: { scenarioId, siteBoundary },
            });
        },
        []
    );

    const setParkingConfig = useCallback(
        (scenarioId: string, config: Partial<ParkingConfig>) => {
            dispatch({
                type: "SET_PARKING_CONFIG",
                payload: { scenarioId, config },
            });
        },
        []
    );

    const setConstraints = useCallback(
        (scenarioId: string, constraints: readonly ImportedConstraint[]) => {
            dispatch({
                type: "SET_CONSTRAINTS",
                payload: { scenarioId, constraints },
            });
        },
        []
    );

    const toggleConstraints = useCallback(
        (scenarioId: string, enabled: boolean) => {
            dispatch({
                type: "TOGGLE_CONSTRAINTS",
                payload: { scenarioId, enabled },
            });
        },
        []
    );

    const setEvaluationResult = useCallback(
        (scenarioId: string, result: EvaluationResult) => {
            dispatch({
                type: "SET_EVALUATION_RESULT",
                payload: { scenarioId, result },
            });
        },
        []
    );

    const setScenarioStatus = useCallback(
        (scenarioId: string, status: ScenarioStatus, error?: string) => {
            dispatch({
                type: "SET_SCENARIO_STATUS",
                payload: { scenarioId, status, error },
            });
        },
        []
    );

    const value: ScenarioContextValue = {
        state,
        dispatch,
        activeScenario,
        comparisonScenario,
        createScenario,
        setActiveScenario,
        deleteScenario,
        duplicateScenario,
        renameScenario,
        setSiteBoundary,
        setParkingConfig,
        setConstraints,
        toggleConstraints,
        setEvaluationResult,
        setScenarioStatus,
    };

    return (
        <ScenarioContext.Provider value={value}>
            {children}
        </ScenarioContext.Provider>
    );
}

// =============================================================================
// Hook
// =============================================================================

export function useScenario(): ScenarioContextValue {
    const context = useContext(ScenarioContext);
    if (!context) {
        throw new Error("useScenario must be used within a ScenarioProvider");
    }
    return context;
}

// =============================================================================
// Exports
// =============================================================================

export { DEFAULT_PARKING_CONFIG, DEFAULT_CANVAS_STATE };
export type { ScenarioState, ScenarioAction, ScenarioContextValue };
