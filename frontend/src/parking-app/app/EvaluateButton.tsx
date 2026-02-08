/**
 * GenFabTools Parking Engine - Evaluate Button
 *
 * Triggers backend evaluation of the current scenario.
 * Auto-evaluates when site boundary is set or config changes.
 */

import React, { useCallback, useState, useEffect, useRef } from "react";
import { useScenario } from "../state";
import { evaluateParkingScenario, ParkingApiError } from "../api";
import { isDisplayablePolygon } from "../utils";

export function EvaluateButton() {
    const {
        activeScenario,
        setEvaluationResult,
        setScenarioStatus,
    } = useScenario();
    const [isEvaluating, setIsEvaluating] = useState(false);
    const abortControllerRef = useRef<AbortController | null>(null);

    const canEvaluate =
        activeScenario &&
        isDisplayablePolygon(activeScenario.siteBoundary) &&
        activeScenario.status !== "evaluating";

    const handleEvaluate = useCallback(async () => {
        if (!activeScenario || !activeScenario.siteBoundary) return;

        // Cancel any pending request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        setIsEvaluating(true);
        setScenarioStatus(activeScenario.id, "evaluating");

        try {
            const result = await evaluateParkingScenario(
                activeScenario.siteBoundary,
                activeScenario.parkingConfig,
                activeScenario.constraintsEnabled
                    ? activeScenario.constraints
                    : undefined
            );

            setEvaluationResult(activeScenario.id, result);
        } catch (err) {
            // Ignore abort errors
            if (err instanceof Error && err.name === 'AbortError') return;

            let message = "Evaluation failed";
            if (err instanceof ParkingApiError) {
                message = err.message;
            } else if (err instanceof Error) {
                message = err.message;
            }
            setScenarioStatus(activeScenario.id, "error", message);
        } finally {
            setIsEvaluating(false);
        }
    }, [activeScenario, setEvaluationResult, setScenarioStatus]);

    // Auto-evaluate when site or config changes
    useEffect(() => {
        if (!activeScenario?.siteBoundary) return;
        if (!isDisplayablePolygon(activeScenario.siteBoundary)) return;

        // Debounce auto-evaluation
        const timer = setTimeout(() => {
            handleEvaluate();
        }, 300);

        return () => clearTimeout(timer);
    }, [
        activeScenario?.siteBoundary,
        activeScenario?.parkingConfig.parkingType,
        activeScenario?.parkingConfig.aisleDirection,
        activeScenario?.parkingConfig.setback,
        activeScenario?.parkingConfig.structuredConfig?.levels,
        activeScenario?.constraintsEnabled,
    ]);

    return (
        <div className="px-4 py-3 border-t border-gray-200">
            <button
                onClick={handleEvaluate}
                disabled={!canEvaluate || isEvaluating}
                className={`w-full px-4 py-2.5 text-sm font-semibold rounded transition-colors ${canEvaluate && !isEvaluating
                    ? "bg-green-600 text-white hover:bg-green-700"
                    : "bg-gray-200 text-gray-500 cursor-not-allowed"
                    }`}
            >
                {isEvaluating ? (
                    <span className="flex items-center justify-center gap-2">
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
                        Evaluating...
                    </span>
                ) : (
                    "Evaluate Parking"
                )}
            </button>

            {!activeScenario?.siteBoundary && (
                <p className="text-xs text-gray-500 text-center mt-2">
                    Define a site boundary to evaluate
                </p>
            )}
        </div>
    );
}
