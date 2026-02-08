// Authoritative restored component (from occupancy-calculator/src/OccuCalcTools.js)
import React, { useEffect, useMemo, useRef, useState } from "react";
import CODE_SETS_DEFAULT from "./code_sets.json";
// Heavy libraries (xlsx, file-saver, jspdf) are loaded dynamically inside the
// functions that need them to avoid inflating the initial JS bundle.

/* Code sets are loaded from `frontend/src/code_sets.json` (seed) and can be edited from the UI. */

// localStorage keys
const LS_OVERRIDES_KEY = "occuCalc.codeOverrides.v1";
const LS_CODE_SETS_KEY = "occuCalc.codeSets.v1";
const LS_DATA_MANUAL = "occuCalc.data.manual.v1";
const LS_DATA_UPLOAD = "occuCalc.data.upload.v1";
const LS_UI_PREFS = "occuCalc.ui.prefs.v1";

// -------------- helpers
const normalizeType = (t, list) => {
    const v = (t || "").toString().trim();
    return list.includes(v) ? v : (list[0] || "Retail");
};
const toNumber = (x) => {
    const n = Number(x);
    return Number.isFinite(n) ? n : 0;
};
const ceilDivide = (area, factor) => {
    const a = Number(area);
    const f = Number(factor) > 0 ? Number(factor) : 1;
    if (!Number.isFinite(a) || a <= 0) return 0;
    return Math.ceil(a / f);
};

// =========================================================
// Component
// =========================================================
export default function OccuCalcTools() {
    // Mode and active code-set
    const [mode, setMode] = useState("manual"); // "manual" | "upload"
    const [codeId, setCodeId] = useState("IBC_2024");

    // code sets (seeded from JSON, persisted edits in localStorage)
    const [codeSets, setCodeSets] = useState(() => {
        try {
            const raw = localStorage.getItem(LS_CODE_SETS_KEY);
            return raw ? JSON.parse(raw) : CODE_SETS_DEFAULT;
        } catch (e) {
            return CODE_SETS_DEFAULT;
        }
    });

    // overrides per code (allow edits)
    const [overrides, setOverrides] = useState({});
    useEffect(() => {
        try {
            const raw = localStorage.getItem(LS_OVERRIDES_KEY);
            if (raw) setOverrides(JSON.parse(raw));
        } catch { }
    }, []);

    // Manageable code sets UI state
    const [showManageCodes, setShowManageCodes] = useState(false);
    const [manageText, setManageText] = useState("");
    useEffect(() => {
        try {
            localStorage.setItem(LS_OVERRIDES_KEY, JSON.stringify(overrides));
        } catch { }
    }, [overrides]);

    // current factors/type list
    const baseFactors = codeSets[codeId]?.factors || codeSets.GENERIC.factors;
    const currentFactors = useMemo(
        () => ({ ...baseFactors, ...(overrides[codeId] || {}) }),
        [baseFactors, overrides, codeId]
    );
    const typeList = useMemo(() => Object.keys(currentFactors), [currentFactors]);

    // -------------------- data (manual + upload) with autosave
    const [manualRows, setManualRows] = useState(() => {
        const saved = localStorage.getItem(LS_DATA_MANUAL);
        return saved
            ? JSON.parse(saved)
            : [{ id: 1, sel: false, number: "1", name: "Space 1", area: "", type: normalizeType("Retail", typeList) }];
    });
    const [gridRows, setGridRows] = useState(() => {
        const saved = localStorage.getItem(LS_DATA_UPLOAD);
        return saved ? JSON.parse(saved) : [];
    });

    useEffect(() => {
        localStorage.setItem(LS_DATA_MANUAL, JSON.stringify(manualRows));
    }, [manualRows]);
    useEffect(() => {
        localStorage.setItem(LS_DATA_UPLOAD, JSON.stringify(gridRows));
    }, [gridRows]);

    // Adjust existing rows if type list changes
    useEffect(() => {
        setManualRows((prev) => prev.map((r) => ({ ...r, type: normalizeType(r.type, typeList) })));
        setGridRows((prev) =>
            prev.map((r) => {
                const t = normalizeType(r["Occupancy Type"], typeList);
                return {
                    ...r,
                    "Occupancy Type": t,
                    "Occupant Load": ceilDivide(r["Area (m²)"], currentFactors[t])
                };
            })
        );
    }, [typeList, currentFactors]);

    // -------------------- UI state: search/filter/sort & prefs
    const [search, setSearch] = useState("");
    const [filterType, setFilterType] = useState("All");
    const [sortKey, setSortKey] = useState("number"); // or "name" | "area" | "type" | "load"
    const [sortDir, setSortDir] = useState("asc");    // "asc" | "desc"
    const [showEditor, setShowEditor] = useState(false);
    // UI state for export/loading feedback ('""' = idle, 'excel'|'pdfSummary'|'pdfDetailed'|'template')
    const [exportLoading, setExportLoading] = useState("");
    // progress indicator { pct: number, msg: string }
    const [exportProgress, setExportProgress] = useState({ pct: 0, msg: '' });
    // ref to the cancel button in the export dialog for focus management
    const exportCancelRef = useRef(null);
    const exportDialogRef = useRef(null);
    // refs to manage in-flight worker/file operations so we can cancel
    const activeWorkerRef = useRef(null);
    const activeReaderRef = useRef(null);
    const isAbortedRef = useRef(false);
    // transient toast { msg, type: 'success'|'error'|'info' }
    const [toast, setToast] = useState(null);
    const showToast = (msg, type = 'info') => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    // Export menu state for compact control bar
    const [exportMenuOpen, setExportMenuOpen] = useState(false);
    const exportMenuRef = useRef(null);
    // refs for Manage Codes modal focus handling
    const manageModalRef = useRef(null);
    const manageTextareaRef = useRef(null);
    // Add menu (grouped Add actions) state
    const [addMenuOpen, setAddMenuOpen] = useState(false);
    const addMenuRef = useRef(null);

    // Close export menu when clicking outside any export-menu element
    useEffect(() => {
        const onDoc = (e) => {
            try {
                const nodes = Array.from(document.querySelectorAll('.export-menu'));
                const inside = nodes.some((n) => n && n.contains(e.target));
                if (!inside) setExportMenuOpen(false);
            } catch (err) {
                // ignore
            }
        };
        document.addEventListener('click', onDoc);
        const onEsc = (e) => { if (e.key === 'Escape') setExportMenuOpen(false); };
        document.addEventListener('keydown', onEsc);
        return () => {
            document.removeEventListener('click', onDoc);
            document.removeEventListener('keydown', onEsc);
        };
    }, []);

    // Close add menu when clicking outside
    useEffect(() => {
        if (!addMenuRef.current) return;
        const onDoc = (e) => {
            if (!addMenuRef.current.contains(e.target)) setAddMenuOpen(false);
        };
        document.addEventListener('click', onDoc);
        const onEsc = (e) => { if (e.key === 'Escape') setAddMenuOpen(false); };
        document.addEventListener('keydown', onEsc);
        return () => {
            document.removeEventListener('click', onDoc);
            document.removeEventListener('keydown', onEsc);
        };
    }, [addMenuRef.current]);

    // NOTE: keyboard shortcut effect moved lower in the file so it references
    // functions that are already initialized (see after CRUD functions).

    // focus the cancel button when export dialog opens for accessibility
    useEffect(() => {
        if (exportLoading && exportCancelRef.current) {
            // delay briefly to ensure the element is in the DOM
            setTimeout(() => {
                try { exportCancelRef.current.focus(); } catch (e) { }
            }, 50);
        }
    }, [exportLoading]);

    // Manage Codes modal: focus textarea on open and close on Escape
    useEffect(() => {
        if (!showManageCodes) return;
        // focus textarea
        setTimeout(() => {
            try { manageTextareaRef.current && manageTextareaRef.current.focus(); } catch (e) { }
        }, 30);

        const onKey = (e) => {
            if (e.key === 'Escape') setShowManageCodes(false);
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [showManageCodes]);

    // Focus trap for the export dialog: keep Tab within the dialog while open
    useEffect(() => {
        if (!exportLoading || !exportDialogRef.current) return;
        const root = exportDialogRef.current;
        const focusableSelector = 'a[href], area[href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])';

        const keyHandler = (e) => {
            if (e.key !== 'Tab') return;
            const nodes = Array.from(root.querySelectorAll(focusableSelector)).filter((n) => n.offsetParent !== null || n === document.activeElement);
            if (nodes.length === 0) {
                e.preventDefault();
                return;
            }
            const first = nodes[0];
            const last = nodes[nodes.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first || document.activeElement === root) {
                    e.preventDefault();
                    try { last.focus(); } catch (err) { }
                }
            } else {
                if (document.activeElement === last) {
                    e.preventDefault();
                    try { first.focus(); } catch (err) { }
                }
            }
        };

        document.addEventListener('keydown', keyHandler);
        return () => document.removeEventListener('keydown', keyHandler);
    }, [exportLoading]);

    useEffect(() => {
        const saved = localStorage.getItem(LS_UI_PREFS);
        if (saved) {
            try {
                const prefs = JSON.parse(saved);
                if (prefs.mode) setMode(prefs.mode);
                if (prefs.codeId) setCodeId(prefs.codeId);
                if (prefs.filterType) setFilterType(prefs.filterType);
            } catch { }
        }
    }, []);
    useEffect(() => {
        localStorage.setItem(
            LS_UI_PREFS,
            JSON.stringify({ mode, codeId, filterType })
        );
    }, [mode, codeId, filterType]);

    // -------------------- derived rows (filter/search/sort)
    const displayedManual = useMemo(() => {
        let rows = manualRows.map((r) => ({
            ...r,
            load: ceilDivide(r.area, currentFactors[r.type])
        }));
        if (filterType !== "All") rows = rows.filter((r) => r.type === filterType);
        if (search.trim()) {
            const q = search.toLowerCase();
            rows = rows.filter(
                (r) =>
                    String(r.number).toLowerCase().includes(q) ||
                    String(r.name).toLowerCase().includes(q)
            );
        }
        rows.sort((a, b) => {
            const dir = sortDir === "asc" ? 1 : -1;
            const val = (k, x) =>
                k === "area" || k === "load" ? toNumber(x[k]) : String(x[k] || "");
            const va = val(sortKey, a);
            const vb = val(sortKey, b);
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
        return rows;
    }, [manualRows, filterType, search, sortKey, sortDir, currentFactors]);

    const displayedGrid = useMemo(() => {
        let rows = gridRows.map((r) => ({
            ...r,
            "Occupant Load": ceilDivide(
                r["Area (m²)"],
                currentFactors[r["Occupancy Type"]]
            )
        }));
        if (filterType !== "All")
            rows = rows.filter((r) => r["Occupancy Type"] === filterType);
        if (search.trim()) {
            const q = search.toLowerCase();
            rows = rows.filter(
                (r) =>
                    String(r["Room #"]).toLowerCase().includes(q) ||
                    String(r["Room Name"]).toLowerCase().includes(q)
            );
        }
        rows.sort((a, b) => {
            const dir = sortDir === "asc" ? 1 : -1;
            const keyMap = {
                number: "Room #",
                name: "Room Name",
                area: "Area (m²)",
                type: "Occupancy Type",
                load: "Occupant Load"
            };
            const col = keyMap[sortKey] || "Room #";
            const va = col === "Area (m²)" || col === "Occupant Load" ? toNumber(a[col]) : String(a[col] || "");
            const vb = col === "Area (m²)" || col === "Occupant Load" ? toNumber(b[col]) : String(b[col] || "");
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
        return rows;
    }, [gridRows, filterType, search, sortKey, sortDir, currentFactors]);

    // -------------------- selection (bulk actions)
    const selCount = useMemo(() => {
        return (mode === "manual" ? manualRows : gridRows).filter((r) => r.sel).length;
    }, [mode, manualRows, gridRows]);

    const setAllSelected = (checked) => {
        if (mode === "manual") {
            setManualRows((prev) => prev.map((r) => ({ ...r, sel: checked })));
        } else {
            setGridRows((prev) => prev.map((r) => ({ ...r, sel: checked })));
        }
    };

    const applyTypeToSelected = (type) => {
        if (!type) return;
        if (mode === "manual") {
            setManualRows((prev) =>
                prev.map((r) =>
                    r.sel ? { ...r, type: normalizeType(type, typeList) } : r
                )
            );
        } else {
            setGridRows((prev) =>
                prev.map((r) =>
                    r.sel
                        ? {
                            ...r,
                            "Occupancy Type": normalizeType(type, typeList),
                            "Occupant Load": ceilDivide(
                                r["Area (m²)"],
                                currentFactors[normalizeType(type, typeList)]
                            )
                        }
                        : r
                )
            );
        }
    };

    const deleteSelected = () => {
        if (mode === "manual") {
            setManualRows((prev) => prev.filter((r) => !r.sel));
        } else {
            setGridRows((prev) => prev.filter((r) => !r.sel));
        }
    };

    const duplicateSelected = () => {
        if (mode === "manual") {
            setManualRows((prev) => {
                const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
                let nextId = maxId + 1;
                const dups = prev
                    .filter((r) => r.sel)
                    .map((r) => ({ ...r, id: nextId++, number: String(nextId - 1), sel: false }));
                return [...prev, ...dups];
            });
        } else {
            setGridRows((prev) => {
                const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
                let nextId = maxId + 1;
                const dups = prev
                    .filter((r) => r.sel)
                    .map((r) => ({ ...r, id: nextId++, sel: false }));
                return [...prev, ...dups];
            });
        }
    };

    // -------------------- CRUD (manual)
    const addManualRow = (qty = 1) => {
        setManualRows((prev) => {
            const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
            const rows = [];
            for (let i = 0; i < qty; i++) {
                const id = maxId + 1 + i;
                rows.push({
                    id,
                    sel: false,
                    number: String(id),
                    name: `Space ${id}`,
                    area: "",
                    type: normalizeType(typeList[0], typeList)
                });
            }
            return [...prev, ...rows];
        });
    };
    const addManualAllTypes = () => {
        setManualRows((prev) => {
            const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
            let nextId = maxId + 1;
            const rows = typeList.map((t) => ({
                id: nextId,
                sel: false,
                number: String(nextId++),
                name: t,
                area: "",
                type: t
            }));
            return [...prev, ...rows];
        });
    };
    // Load a small example dataset to help preview the tool quickly
    const loadExample = () => {
        if (mode === 'manual') {
            const examples = [
                { id: 1, sel: false, number: '101', name: 'Open Office', area: '186', type: normalizeType('Business/Office', typeList) },
                { id: 2, sel: false, number: '102', name: 'Sales Floor', area: '140', type: normalizeType('Retail / Mercantile – sales floor', typeList) },
                { id: 3, sel: false, number: '103', name: 'Lab 1', area: '56', type: normalizeType('Laboratory', typeList) }
            ];
            setManualRows(examples);
        } else {
            const examples = [
                { id: 1, sel: false, 'Room #': '101', 'Room Name': 'Open Office', 'Area (m²)': 186, 'Occupancy Type': normalizeType('Business/Office', typeList), 'Occupant Load': ceilDivide(186, currentFactors[normalizeType('Business/Office', typeList)]) },
                { id: 2, sel: false, 'Room #': '102', 'Room Name': 'Sales Floor', 'Area (m²)': 140, 'Occupancy Type': normalizeType('Retail / Mercantile – sales floor', typeList), 'Occupant Load': ceilDivide(140, currentFactors[normalizeType('Retail / Mercantile – sales floor', typeList)]) },
                { id: 3, sel: false, 'Room #': '103', 'Room Name': 'Lab 1', 'Area (m²)': 56, 'Occupancy Type': normalizeType('Laboratory', typeList), 'Occupant Load': ceilDivide(56, currentFactors[normalizeType('Laboratory', typeList)]) }
            ];
            setGridRows(examples);
        }
        showToast('Example dataset loaded', 'success');
    };
    const updateManual = (id, key, value) => {
        setManualRows((prev) =>
            prev.map((r) => {
                if (r.id !== id) return r;
                if (key === "type") return { ...r, type: normalizeType(value, typeList) };
                return { ...r, [key]: value };
            })
        );
    };
    const removeManualRow = (id) =>
        setManualRows((prev) => prev.filter((r) => r.id !== id));
    const clearManual = () =>
        setManualRows([{ id: 1, sel: false, number: "1", name: "Space 1", area: "", type: normalizeType("Retail", typeList) }]);

    // -------------------- Upload grid
    const fileInputRef = useRef(null);

    const handleUpload = (file) => {
        if (!file) return;

        // If module workers are available, try parsing the uploaded XLSX in the worker
        if (typeof window !== 'undefined' && typeof window.Worker === 'function') {
            try {
                const worker = new Worker(new URL('./workers/exportWorker.js', import.meta.url), { type: 'module' });
                // track active worker for cancellation
                activeWorkerRef.current = worker;
                isAbortedRef.current = false;

                worker.onmessage = (e) => {
                    const data = e.data || {};
                    if (data.action === 'progress') {
                        setExportProgress({ pct: Number(data.pct) || 0, msg: data.msg || '' });
                        return;
                    }
                    if (data.action === 'parsedRows') {
                        // Normalize occupancy type and occupant load on main thread
                        const rows = (data.rows || []).map((r) => {
                            const t = normalizeType(r["Occupancy Type"], typeList);
                            return {
                                ...r,
                                "Occupancy Type": t,
                                "Occupant Load": ceilDivide(r["Area (m²)"], currentFactors[t])
                            };
                        });
                        setGridRows(rows);
                        setExportProgress({ pct: 0, msg: '' });
                    } else if (data.action === 'error') {
                        console.error('Worker parse error:', data.message);
                    }
                    try { worker.terminate(); } catch (e) { }
                    activeWorkerRef.current = null;
                    isAbortedRef.current = false;
                };
                worker.onerror = (err) => {
                    console.error('Worker uncaught error:', err);
                    try { worker.terminate(); } catch (e) { }
                };

                const reader = new FileReader();
                reader.onload = (evt) => {
                    const arrayBuffer = evt.target.result;
                    // Transfer the ArrayBuffer to the worker for parsing
                    worker.postMessage({ action: 'parseXLSX', arrayBuffer }, [arrayBuffer]);
                };
                reader.readAsArrayBuffer(file);
                if (fileInputRef.current) fileInputRef.current.value = null;
                return;
            } catch (err) {
                console.warn('Worker parse failed, falling back to in-thread parsing:', err);
                // fall through to in-thread parsing fallback
            }
        }

        // Fallback: parse in main thread via dynamic import
        const reader = new FileReader();
        reader.onload = async (evt) => {
            try {
                const XLSX = await import(/* webpackChunkName: "vendor_xlsx" */ "xlsx");
                const wb = XLSX.read(evt.target.result, { type: "binary" });
                const ws = wb.Sheets[wb.SheetNames[0]];
                const rows = XLSX.utils.sheet_to_json(ws, { defval: "" }).map((row, i) => {
                    const number = row["Room #"] ?? row["Room Number"] ?? String(i + 1);
                    const name = row["Room Name"] ?? row["Name"] ?? `Space ${i + 1}`;
                    const area = row["Area (m²)"] ?? row["Area"] ?? "";
                    const tRaw = row["Occupancy Type"] ?? row["Type"];
                    const t = normalizeType(tRaw, typeList);
                    return {
                        id: i + 1,
                        sel: false,
                        "Room #": String(number),
                        "Room Name": String(name),
                        "Area (m²)": area,
                        "Occupancy Type": t,
                        "Occupant Load": ceilDivide(area, currentFactors[t])
                    };
                });
                setGridRows(rows);
            } catch (err) {
                console.error("Failed to parse uploaded file:", err);
            } finally {
                if (fileInputRef.current) fileInputRef.current.value = null;
            }
        };
        // For legacy fallback keep binary string path
        reader.readAsBinaryString(file);
    };

    const onFileInput = (e) => {
        handleUpload(e.target.files?.[0]);
        if (fileInputRef.current) fileInputRef.current.value = null;
    };

    // Drag & drop
    const [isDragging, setIsDragging] = useState(false);
    const onDropZone = (e) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file && /(\.xlsx|\.xls)$/i.test(file.name)) handleUpload(file);
    };
    const onDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };
    const onDragLeave = () => setIsDragging(false);

    const updateGrid = (id, key, value) => {
        setGridRows((prev) =>
            prev.map((r) => {
                if (r.id !== id) return r;
                const next = { ...r, [key]: value };
                const t = normalizeType(next["Occupancy Type"], typeList);
                next["Occupancy Type"] = t;
                next["Occupant Load"] = ceilDivide(next["Area (m²)"], currentFactors[t]);
                return next;
            })
        );
    };
    const addGridRow = (qty = 1) => {
        setGridRows((prev) => {
            const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
            const rows = [];
            for (let i = 0; i < qty; i++) {
                const id = maxId + 1 + i;
                rows.push({
                    id,
                    sel: false,
                    "Room #": String(id),
                    "Room Name": `Space ${id}`,
                    "Area (m²)": "",
                    "Occupancy Type": normalizeType(typeList[0], typeList),
                    "Occupant Load": 0
                });
            }
            return [...prev, ...rows];
        });
    };
    const addGridAllTypes = () => {
        setGridRows((prev) => {
            const maxId = prev.reduce((m, r) => Math.max(m, r.id), 0);
            let nextId = maxId + 1;
            const rows = typeList.map((t) => ({
                id: nextId,
                sel: false,
                "Room #": String(nextId++),
                "Room Name": t,
                "Area (m²)": "",
                "Occupancy Type": t,
                "Occupant Load": 0
            }));
            return [...prev, ...rows];
        });
    };
    // Keyboard shortcut: Ctrl+Shift+A -> add 1 row (quick action)
    useEffect(() => {
        const handler = (e) => {
            if (e.ctrlKey && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
                e.preventDefault();
                if (mode === 'manual') {
                    addManualRow(1);
                    showToast('Added 1 row (shortcut)', 'success');
                } else {
                    addGridRow(1);
                    showToast('Added 1 row (shortcut)', 'success');
                }
            }
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [mode, addManualRow, addGridRow]);
    const removeGridRow = (id) =>
        setGridRows((prev) => prev.filter((r) => r.id !== id));
    const clearGrid = () => setGridRows([]);

    // -------------------- Exports & template
    const rowsForExport = () => {
        return mode === "manual"
            ? manualRows.map((r) => ({
                "Room #": r.number,
                "Room Name": r.name,
                "Area (m²)": r.area,
                "Occupancy Type": r.type,
                "Occupant Load": ceilDivide(r.area, currentFactors[r.type])
            }))
            : gridRows.map((r) => ({
                "Room #": r["Room #"],
                "Room Name": r["Room Name"],
                "Area (m²)": r["Area (m²)"],
                "Occupancy Type": r["Occupancy Type"],
                "Occupant Load": ceilDivide(r["Area (m²)"], currentFactors[r["Occupancy Type"]])
            }));
    };

    // Lightweight CSV export (no heavy libraries required)
    const exportCSV = () => {
        setExportLoading("csv");
        try {
            const rows = rowsForExport();
            const headers = ["Room #", "Room Name", "Area (m²)", "Occupancy Type", "Occupant Load"];
            const escapeCell = (v) => {
                if (v === null || v === undefined) return "";
                const s = String(v);
                if (/[,"\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
                return s;
            };
            const lines = [headers.join(',')].concat(
                rows.map((r) => headers.map((h) => escapeCell(r[h] ?? "")).join(','))
            );
            const csv = lines.join('\r\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'occupancy_data.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showToast('CSV exported', 'success');
        } catch (err) {
            console.error('Failed to export CSV:', err);
            showToast('CSV export failed', 'error');
        } finally {
            setExportLoading("");
        }
    };

    // Attempt to open a Revit protocol handler with the CSV payload.
    // This is a best-effort prototype: many browsers limit URL length or block custom protocols.
    // For large payloads we fall back to downloading the CSV so the user can import manually.
    const openInRevit = () => {
        try {
            const rows = rowsForExport();
            const headers = ['Room Number', 'Room Name', 'Area_m2', 'Occupancy Type', 'Occupant Load'];
            const escapeCell = (v) => {
                if (v === null || v === undefined) return '';
                const s = String(v);
                if (/[,"\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
                return s;
            };
            const lines = [headers.join(',')];
            rows.forEach((r) => {
                const num = r['Room #'] ?? r['#'] ?? '';
                const name = r['Room Name'] ?? r['Name'] ?? '';
                const area = r['Area (m²)'] ?? r['Area_m2'] ?? r['Area'] ?? '';
                const type = r['Occupancy Type'] ?? r['Type'] ?? '';
                const load = r['Occupant Load'] ?? r['Load'] ?? '';
                lines.push([num, name, area, type, load].map(escapeCell).join(','));
            });
            const csv = lines.join('\r\n');

            // If the payload is large, prefer download fallback (protocol URLs have practical limits).
            if (csv.length > 2000) {
                showToast('CSV too large for one-click protocol; downloading file instead', 'info');
                exportForRevit();
                return;
            }

            const encoded = encodeURIComponent(csv);
            const proto = `occucalc-revit://import?csv=${encoded}`;

            // Try to open the protocol handler via a hidden iframe (common pattern).
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            document.body.appendChild(iframe);
            try {
                iframe.src = proto;
            } catch (e) {
                // Some browsers will throw; try location fallback
                try { window.location.href = proto; } catch (ex) { }
            }

            setTimeout(() => {
                try { document.body.removeChild(iframe); } catch (e) { }
                showToast("Tried opening Revit via protocol handler. If Revit didn't open, use 'Export for Revit (CSV)' to import manually.", 'info');
            }, 1400);
        } catch (err) {
            console.error('Open in Revit failed:', err);
            showToast('Open in Revit failed', 'error');
        }
    };

    // Export CSV formatted for Revit/Dynamo import (stable schema)
    const exportForRevit = () => {
        setExportLoading('csv');
        try {
            const rows = rowsForExport();
            const headers = ['Room Number', 'Room Name', 'Area_m2', 'Occupancy Type', 'Occupant Load'];
            const escapeCell = (v) => {
                if (v === null || v === undefined) return '';
                const s = String(v);
                if (/[,"\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
                return s;
            };
            const lines = [headers.join(',')];
            rows.forEach((r) => {
                const num = r['Room #'] ?? r['#'] ?? '';
                const name = r['Room Name'] ?? r['Name'] ?? '';
                const area = r['Area (m²)'] ?? r['Area_m2'] ?? r['Area'] ?? '';
                const type = r['Occupancy Type'] ?? r['Type'] ?? '';
                const load = r['Occupant Load'] ?? r['Load'] ?? '';
                lines.push([num, name, area, type, load].map(escapeCell).join(','));
            });
            const csv = lines.join('\r\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `occucalc_for_revit_${(new Date()).toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showToast('Export for Revit (CSV) downloaded', 'success');
        } catch (err) {
            console.error('Failed to export for Revit:', err);
            showToast('Export for Revit failed', 'error');
        } finally {
            setExportLoading("");
        }
    };

    const exportExcel = async () => {
        setExportLoading("excel");
        // Prefer a module Web Worker so heavy XLSX code runs off the main thread.
        if (typeof window !== 'undefined' && typeof window.Worker === 'function') {
            try {
                const worker = new Worker(new URL('./workers/exportWorker.js', import.meta.url), { type: 'module' });
                worker.onmessage = (e) => {
                    const data = e.data || {};
                    if (data.action === 'progress') {
                        setExportProgress({ pct: Number(data.pct) || 0, msg: data.msg || '' });
                        return;
                    }
                    if (data.action === 'resultXLSX') {
                        try {
                            const ab = data.buffer;
                            const blob = new Blob([ab], { type: 'application/octet-stream' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'occupancy_data.xlsx';
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                            URL.revokeObjectURL(url);
                            showToast('Excel exported', 'success');
                        } catch (err) {
                            console.error('Failed to save XLSX from worker:', err);
                            showToast('Excel export failed', 'error');
                        }
                        setExportProgress({ pct: 100, msg: 'Done' });
                    } else if (data.action === 'error') {
                        console.error('Worker error:', data.message);
                        showToast('Excel export failed', 'error');
                    }
                    try { worker.terminate(); } catch (e) { }
                    activeWorkerRef.current = null;
                    isAbortedRef.current = false;
                    setExportProgress({ pct: 0, msg: '' });
                    setExportLoading("");
                };
                worker.onerror = (err) => {
                    console.error('Worker uncaught error:', err);
                    showToast('Excel export failed', 'error');
                    try { worker.terminate(); } catch (e) { }
                    activeWorkerRef.current = null;
                    isAbortedRef.current = false;
                    setExportProgress({ pct: 0, msg: '' });
                    setExportLoading("");
                };
                // Send rows; worker will import xlsx and build the buffer
                worker.postMessage({ action: 'generateXLSX', rows: rowsForExport() });
                return;
            } catch (err) {
                console.warn('Worker failed, falling back to in-thread export:', err);
                // fall through to dynamic-import fallback
            }
        }

        // Fallback: in-thread dynamic import (will download the library into the main bundle)
        try {
            isAbortedRef.current = false;
            setExportProgress({ pct: 5, msg: 'Loading xlsx…' });
            const XLSX = await import(/* webpackChunkName: "vendor_xlsx" */ "xlsx");
            if (isAbortedRef.current) {
                showToast('Export cancelled', 'info');
                setExportProgress({ pct: 0, msg: '' });
                setExportLoading("");
                return;
            }
            setExportProgress({ pct: 40, msg: 'Converting data…' });
            const ws = XLSX.utils.json_to_sheet(rowsForExport(), {
                header: ["Room #", "Room Name", "Area (m²)", "Occupancy Type", "Occupant Load"]
            });
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, "Occupancy");
            setExportProgress({ pct: 75, msg: 'Writing workbook…' });
            const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
            if (isAbortedRef.current) {
                showToast('Export cancelled', 'info');
                setExportProgress({ pct: 0, msg: '' });
                setExportLoading("");
                return;
            }
            const blob = new Blob([buf], { type: 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'occupancy_data.xlsx';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setExportProgress({ pct: 100, msg: 'Done' });
            showToast('Excel exported', 'success');
        } catch (err) {
            console.error("Failed to export Excel:", err);
            showToast('Excel export failed', 'error');
        } finally {
            // small delay to let UI show 100% briefly then clear
            setTimeout(() => setExportProgress({ pct: 0, msg: '' }), 400);
            setExportLoading("");
        }
    };

    const exportPDFSummary = async () => {
        const totals = {};
        let total = 0;
        rowsForExport().forEach((r) => {
            const t = r["Occupancy Type"];
            const l = toNumber(r["Occupant Load"]);
            totals[t] = (totals[t] || 0) + l;
            total += l;
        });
        setExportLoading("pdfSummary");
        try {
            const jsPDFModule = await import(/* webpackChunkName: "vendor_jspdf" */ "jspdf");
            const jsPDF = jsPDFModule.default || jsPDFModule;
            const doc = new jsPDF({ unit: "pt", format: "a4" });
            let y = 64;
            doc.setFontSize(18);
            doc.text(`Occupancy Summary – ${codeSets[codeId]?.label || codeId}`, 40, y);
            y += 24;

            doc.setFontSize(12);
            Object.entries(totals).forEach(([k, v]) => {
                doc.text(`${k}: ${v} occupants`, 40, y);
                y += 16;
            });

            y += 10;
            doc.setFontSize(14);
            doc.text(`Grand Total: ${total} occupants`, 40, y);
            doc.save("occupancy_summary.pdf");
            showToast('PDF summary exported', 'success');
        } catch (err) {
            console.error("Failed to generate PDF summary:", err);
            showToast('PDF summary failed', 'error');
        } finally {
            setExportLoading("");
        }
    };

    const exportPDFDetailed = async () => {
        try {
            const rows = rowsForExport();
            setExportLoading("pdfDetailed");
            const jsPDFModule = await import(/* webpackChunkName: "vendor_jspdf" */ "jspdf");
            const jsPDF = jsPDFModule.default || jsPDFModule;
            const doc = new jsPDF({ unit: "pt", format: "a4" });
            let y = 64;

            doc.setFontSize(18);
            doc.text(`Occupancy Detailed Report – ${codeSets[codeId]?.label || codeId}`, 40, y);
            y += 24;

            doc.setFontSize(10);
            doc.text("Room #", 40, y);
            doc.text("Room Name", 110, y);
            doc.text("Area (m²)", 280, y);
            doc.text("Type", 360, y);
            doc.text("Load", 460, y);
            y += 12;
            doc.line(40, y, 520, y);
            y += 12;

            rows.forEach((r) => {
                if (y > 760) {
                    doc.addPage();
                    y = 64;
                }
                doc.text(String(r["Room #"]), 40, y);
                doc.text(String(r["Room Name"]), 110, y);
                doc.text(String(r["Area (m²)"]), 280, y);
                doc.text(String(r["Occupancy Type"]), 360, y);
                doc.text(String(r["Occupant Load"]), 460, y);
                y += 14;
            });

            y += 12;
            doc.setFontSize(12);
            const grand = rows.reduce((s, r) => s + toNumber(r["Occupant Load"]), 0);
            doc.text(`Grand Total: ${grand} occupants`, 40, y);
            doc.save("occupancy_detailed.pdf");
            showToast('Detailed PDF exported', 'success');
        } catch (err) {
            console.error("Failed to generate detailed PDF:", err);
            showToast('Detailed PDF failed', 'error');
        } finally {
            setExportLoading("");
        }
    };

    const downloadTemplate = async () => {
        const example = [
            { "Room #": "101", "Room Name": "Open Office", "Area (m²)": 186, "Occupancy Type": "Business/Office" },
            { "Room #": "102", "Room Name": "Sales Floor", "Area (m²)": 140, "Occupancy Type": "Retail / Mercantile – sales floor" },
            { "Room #": "103", "Room Name": "Lab 1", "Area (m²)": 56, "Occupancy Type": "Laboratory" }
        ];
        setExportLoading("template");
        try {
            const XLSX = await import(/* webpackChunkName: "vendor_xlsx" */ "xlsx");
            const fileSaver = await import(/* webpackChunkName: "vendor_file-saver" */ "file-saver");
            const ws = XLSX.utils.json_to_sheet(example, {
                header: ["Room #", "Room Name", "Area (m²)", "Occupancy Type"]
            });
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, "Template");
            const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
            fileSaver.saveAs(new Blob([buf], { type: "application/octet-stream" }), "OccuCalc_template.xlsx");
        } catch (err) {
            console.error("Failed to download template:", err);
        } finally {
            setExportLoading("");
        }
    };

    // -------------------- factor editing
    const [newTypeName, setNewTypeName] = useState("");
    const setFactorFor = (type, value) => {
        const v = Number(value);
        if (!Number.isFinite(v) || v <= 0) return;
        setOverrides((prev) => ({
            ...prev,
            [codeId]: { ...(prev[codeId] || {}), [type]: v }
        }));
    };
    const addNewType = () => {
        const n = newTypeName.trim();
        if (!n || typeList.includes(n)) return;
        setOverrides((prev) => ({
            ...prev,
            [codeId]: { ...(prev[codeId] || {}), [n]: 10 }
        }));
        setNewTypeName("");
    };
    const deleteType = (type) => {
        if (Object.prototype.hasOwnProperty.call(baseFactors, type)) return; // base types cannot be deleted here
        setOverrides((prev) => {
            const curr = { ...(prev[codeId] || {}) };
            delete curr[type];
            return { ...prev, [codeId]: curr };
        });
    };
    const resetCodeToDefaults = () =>
        setOverrides((prev) => {
            const next = { ...prev };
            delete next[codeId];
            return next;
        });

    // -------------------- UI
    const isManual = mode === "manual";
    const visibleRows = isManual ? displayedManual : displayedGrid;

    const toggleSort = (key) => {
        if (sortKey !== key) {
            setSortKey(key);
            setSortDir("asc");
        } else {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        }
    };

    return (
        <div className="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 p-6 rounded-lg font-sans w-full mx-auto">
            <h1 className="sr-only">OccuCalc</h1>
            <p className="text-slate-600 dark:text-slate-300 mt-1">
                Calculate occupant loads with search, filters, bulk actions, and exports. Factors are editable per code set.
            </p>

            {/* Control bar */}
            <div className="bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-3 rounded-lg shadow mb-6 sticky top-20 z-20 border border-slate-100 dark:border-slate-800">
                <div className="flex flex-col sm:flex-row sm:items-end sm:flex-wrap gap-2">
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                        <div className="flex flex-col">
                            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Mode</label>
                            <select aria-label="Mode" value={mode} onChange={(e) => setMode(e.target.value)} className="mt-1 block w-full sm:w-40 px-3 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800 text-sm h-10 text-slate-900 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-600">
                                <option value="manual">Manual entry</option>
                                <option value="upload">Upload Excel</option>
                            </select>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                        <div className="flex flex-col">
                            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Code</label>
                            <div className="flex items-center gap-2">
                                <select aria-label="Code set" value={codeId} onChange={(e) => setCodeId(e.target.value)} className="mt-1 block w-full sm:w-80 px-3 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800 text-sm h-10 text-slate-900 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-600">
                                    {Object.entries(codeSets).map(([id, cfg]) => (
                                        <option key={id} value={id}>{cfg.label}</option>
                                    ))}
                                </select>
                                <button onClick={() => { setManageText(JSON.stringify(codeSets, null, 2)); setShowManageCodes(true); }} title="Manage code sets" className="mt-1 inline-flex items-center px-3 h-10 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-slate-100 shadow-sm hover:bg-slate-50">Manage codes</button>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                        <div className="flex flex-col">
                            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Factors</label>
                            <button aria-controls="factor-editor" aria-expanded={showEditor} onClick={() => setShowEditor((s) => !s)} className="mt-1 inline-flex items-center justify-center h-10 px-3 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm font-medium text-slate-900 dark:text-slate-300 shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-600">
                                {showEditor ? "Hide factors" : "Edit factors"}
                            </button>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                        <div className="flex flex-col">
                            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Type</label>
                            <select aria-label="Type filter" value={filterType} onChange={(e) => setFilterType(e.target.value)} className="mt-1 block w-full sm:w-48 px-3 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800 text-sm h-10 text-slate-900 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-600">
                                <option>All</option>
                                {typeList.map((t) => <option key={t}>{t}</option>)}
                            </select>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 w-full sm:w-auto">
                        <input
                            aria-label="Search rooms"
                            placeholder="Search room # / name…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full sm:w-56 px-3 border border-slate-200 rounded-md text-sm h-10 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-300"
                        />
                    </div>

                    <div className="flex flex-wrap gap-2 w-full sm:w-auto items-center">
                        {isManual ? (
                            <div className="flex flex-col">
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-300 invisible">Actions</label>
                                <div className="mt-1 flex gap-2 items-center">
                                    <div className="relative inline-block text-left" ref={addMenuRef}>
                                        <div>
                                            <button
                                                type="button"
                                                aria-haspopup="true"
                                                aria-expanded={addMenuOpen}
                                                onClick={() => setAddMenuOpen((s) => !s)}
                                                className="inline-flex items-center justify-center w-full rounded-md border border-transparent bg-slate-900 hover:bg-slate-800 px-4 py-2 h-10 text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-slate-300 shadow-sm"
                                            >
                                                <span className="select-none">Add</span>
                                                <svg className="ml-2 -mr-1 h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                                    <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.24a.75.75 0 01-1.06 0L5.25 8.29a.75.75 0 01-.02-1.08z" clipRule="evenodd" />
                                                </svg>
                                            </button>
                                        </div>
                                        {addMenuOpen && (
                                            <div className="absolute right-0 mt-1 w-44 origin-top-right rounded-md bg-white dark:bg-slate-800 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none z-40" role="menu" aria-label="Add rows menu">
                                                <div className="py-1">
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addManualRow(1); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add 1</button>
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addManualRow(10); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add 10</button>
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addManualAllTypes(); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add per type</button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <button onClick={loadExample} className="h-10 inline-flex items-center px-4 rounded-md bg-white dark:bg-transparent border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300">Load example</button>
                                    <button onClick={clearManual} className="h-10 inline-flex items-center px-4 rounded-md bg-white dark:bg-transparent border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300">Clear</button>
                                    {/* Export button placed here so it sits next to Clear */}
                                    <div className="relative inline-block export-menu text-slate-900 dark:text-slate-100" ref={exportMenuRef}>
                                        <button id="export-btn-compact" aria-controls="export-menu-compact" aria-haspopup="true" aria-expanded={exportMenuOpen} onClick={() => setExportMenuOpen((s) => !s)} disabled={!!exportLoading} className="inline-flex items-center justify-center rounded-md border border-transparent bg-slate-900 hover:bg-slate-800 px-4 py-2 h-10 text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-slate-300 shadow-sm">
                                            {exportLoading ? (exportLoading === 'csv' ? 'Exporting…' : 'Exporting…') : 'Export ▾'}
                                        </button>
                                        {exportMenuOpen && !exportLoading && (
                                            <div id="export-menu-compact" role="menu" aria-label="Export options" className="absolute right-0 mt-2 w-44 bg-white text-slate-900 dark:text-slate-100 border rounded shadow-lg z-40">
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportCSV(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export CSV</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportForRevit(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export for Revit (CSV)</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); openInRevit(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Open in Revit (one-click)</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportExcel(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export Excel</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFSummary(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Summary</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFDetailed(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Detailed</button>
                                            </div>
                                        )}
                                    </div>

                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col">
                                <label className="text-xs font-medium text-slate-600 dark:text-slate-300 invisible">Actions</label>
                                <div className="mt-1 flex gap-2 items-center">
                                    <input aria-label="Upload Excel file" ref={fileInputRef} type="file" accept=".xlsx,.xls" onChange={onFileInput} title="Upload Excel" className="text-sm text-slate-900 dark:text-slate-100" />
                                    <div className="relative inline-block text-left" ref={addMenuRef}>
                                        <div>
                                            <button
                                                type="button"
                                                aria-haspopup="true"
                                                aria-expanded={addMenuOpen}
                                                onClick={() => setAddMenuOpen((s) => !s)}
                                                className="inline-flex items-center justify-center w-full rounded-md border border-transparent bg-slate-900 hover:bg-slate-800 px-4 py-2 h-10 text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-slate-300 shadow-sm"
                                            >
                                                <span className="select-none">Add</span>
                                                <svg className="ml-2 -mr-1 h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                                    <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.24a.75.75 0 01-1.06 0L5.25 8.29a.75.75 0 01-.02-1.08z" clipRule="evenodd" />
                                                </svg>
                                            </button>
                                        </div>
                                        {addMenuOpen && (
                                            <div className="absolute right-0 mt-2 w-44 origin-top-right rounded-md bg-white dark:bg-slate-800 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none z-40" role="menu" aria-label="Add rows menu">
                                                <div className="py-1">
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addGridRow(1); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add 1</button>
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addGridRow(10); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add 10</button>
                                                    <button role="menuitem" onClick={() => { setAddMenuOpen(false); addGridAllTypes(); }} className="w-full text-left px-4 py-2 text-sm text-slate-900 dark:text-slate-100 hover:bg-gray-100 dark:hover:bg-gray-700">Add per type</button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <button onClick={loadExample} className="h-10 inline-flex items-center px-4 rounded-md bg-white dark:bg-transparent border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300">Load example</button>
                                    <button onClick={clearGrid} className="h-10 inline-flex items-center px-4 rounded-md bg-white dark:bg-transparent border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300">Clear</button>
                                    {/* Export button placed here so it sits next to Clear (single instance) */}
                                    <div className="relative inline-block text-slate-900 dark:text-slate-100" ref={exportMenuRef}>
                                        <button aria-haspopup="true" aria-expanded={exportMenuOpen} onClick={() => setExportMenuOpen((s) => !s)} disabled={!!exportLoading} className="inline-flex items-center justify-center rounded-md border border-transparent bg-slate-900 hover:bg-slate-800 px-4 py-2 h-10 text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-slate-300 shadow-sm">
                                            {exportLoading ? 'Exporting…' : 'Export ▾'}
                                        </button>
                                        {exportMenuOpen && !exportLoading && (
                                            <div role="menu" aria-label="Export options" className="absolute right-0 mt-2 w-44 bg-white text-slate-900 dark:text-slate-100 border rounded shadow-lg z-40">
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportCSV(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export CSV</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); openInRevit(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Open in Revit (one-click)</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportExcel(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export Excel</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFSummary(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Summary</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFDetailed(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Detailed</button>
                                            </div>
                                        )}
                                    </div>
                                    <button onClick={downloadTemplate} className="px-3 h-10 inline-flex items-center bg-white dark:bg-transparent text-slate-900 dark:text-gray-100 border border-slate-200 dark:border-slate-700 rounded-md text-sm">Template</button>
                                    <div className="relative inline-block export-menu text-slate-900 dark:text-slate-100" ref={exportMenuRef}>
                                        <button id="export-btn-main" aria-controls="export-menu-main" aria-haspopup="true" aria-expanded={exportMenuOpen} onClick={() => setExportMenuOpen((s) => !s)} disabled={!!exportLoading} className="px-3 h-10 inline-flex items-center bg-slate-800 text-white rounded-md hover:bg-slate-700 transition-transform transform hover:scale-105 duration-150 disabled:opacity-60 shadow-sm dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
                                            {exportLoading ? (exportLoading === 'csv' ? 'Exporting…' : 'Exporting…') : 'Export ▾'}
                                        </button>
                                        {exportMenuOpen && !exportLoading && (
                                            <div id="export-menu-main" role="menu" aria-label="Export options" className="absolute right-0 mt-2 w-44 bg-white text-slate-900 dark:text-slate-100 border rounded shadow-lg z-40">
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportCSV(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export CSV</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); openInRevit(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Open in Revit (one-click)</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportExcel(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">Export Excel</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFSummary(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Summary</button>
                                                <button role="menuitem" onClick={() => { setExportMenuOpen(false); exportPDFDetailed(); }} className="w-full text-left px-3 py-2 text-slate-900 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 focus:outline-none focus:bg-slate-100 dark:focus:bg-slate-700">PDF Detailed</button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

            </div>

            {/* Factor editor */}
            {showEditor && (
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 mt-3">
                    <div className="flex justify-between items-center gap-2">
                        <strong>Factors for: {codeSets[codeId]?.label || codeId}</strong>
                        <button onClick={resetCodeToDefaults} className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700">Reset to defaults</button>
                    </div>
                    <div className="overflow-x-auto mt-4">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 table-auto">
                            <thead className="bg-gray-50 dark:bg-gray-800">
                                <tr>
                                    <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Occupancy Type</th>
                                    <th className="px-4 py-2 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">Factor (m²/person)</th>
                                    <th className="px-4 py-2"></th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800">
                                {typeList.map((t) => (
                                    <tr key={t}>
                                        <td className="px-4 py-2 whitespace-nowrap">{t}</td>
                                        <td className="px-4 py-2 whitespace-nowrap">
                                            <input
                                                type="number"
                                                min="0.01"
                                                step="0.01"
                                                value={currentFactors[t]}
                                                onChange={(e) => setFactorFor(t, e.target.value)}
                                                className="w-20 px-2 py-1 border rounded"
                                            />
                                        </td>
                                        <td className="px-4 py-2 whitespace-nowrap">
                                            {!Object.prototype.hasOwnProperty.call(baseFactors, t) && (
                                                <button className="px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700" onClick={() => deleteType(t)}>Delete</button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                                <tr>
                                    <td className="px-4 py-2 whitespace-nowrap">
                                        <input
                                            placeholder="Add new type (e.g., Assembly – exhibition)"
                                            value={newTypeName}
                                            onChange={(e) => setNewTypeName(e.target.value)}
                                            className="w-72 px-2 py-1 border rounded"
                                        />
                                    </td>
                                    <td className="px-4 py-2 whitespace-nowrap">
                                        <em className="text-gray-500">Default 10 m²/person (edit after adding)</em>
                                    </td>
                                    <td className="px-4 py-2 whitespace-nowrap">
                                        <button className="px-3 py-1 bg-slate-700 text-white rounded hover:bg-slate-600" onClick={addNewType}>Add type</button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <p style={{ color: "#888", marginTop: 8 }}>
                        These are convenience defaults. Always verify against the official code adopted in your project’s jurisdiction.
                    </p>
                </div>
            )}

            {/* Manage Codes modal */}
            {showManageCodes && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
                    <div ref={manageModalRef} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 p-4 rounded w-11/12 max-w-2xl">
                        <div className="flex items-center justify-between mb-2">
                            <h3 className="text-lg font-semibold">Manage Code Sets</h3>
                            <button aria-label="Close manage code sets" onClick={() => setShowManageCodes(false)} className="text-sm px-2 py-1 bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded">Close</button>
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">Edit or paste JSON for code sets. Use Import to replace, Merge to merge with existing.</p>
                        <textarea ref={manageTextareaRef} value={manageText} onChange={(e) => setManageText(e.target.value)} placeholder='Paste JSON here' className="w-full h-64 p-2 border rounded bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-slate-100" />
                        <div className="mt-3 flex gap-2">
                            <button onClick={() => {
                                try {
                                    const parsed = JSON.parse(manageText);
                                    setCodeSets(parsed);
                                    localStorage.setItem(LS_CODE_SETS_KEY, JSON.stringify(parsed));
                                    showToast('Imported code sets', 'success');
                                    setShowManageCodes(false);
                                } catch (e) {
                                    showToast('Invalid JSON', 'error');
                                }
                            }} className="px-3 py-2 bg-slate-900 text-white rounded">Import &amp; apply</button>
                            <button onClick={() => {
                                try {
                                    const parsed = JSON.parse(manageText);
                                    const merged = { ...codeSets, ...parsed };
                                    setCodeSets(merged);
                                    localStorage.setItem(LS_CODE_SETS_KEY, JSON.stringify(merged));
                                    showToast('Merged code sets', 'success');
                                    setShowManageCodes(false);
                                } catch (e) {
                                    showToast('Invalid JSON', 'error');
                                }
                            }} className="px-3 py-2 bg-white dark:bg-slate-800 border rounded">Merge</button>
                            <button onClick={() => { navigator.clipboard?.writeText(JSON.stringify(codeSets, null, 2)); showToast('Code sets copied to clipboard', 'success'); }} className="px-3 py-2 bg-white dark:bg-slate-800 border rounded">Copy JSON</button>
                            <button onClick={() => { localStorage.removeItem(LS_CODE_SETS_KEY); setCodeSets(CODE_SETS_DEFAULT); showToast('Reset to defaults', 'success'); setShowManageCodes(false); }} className="px-3 py-2 bg-red-600 text-white rounded">Reset defaults</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Drag & drop zone for upload mode */}
            {!isManual && (
                <div
                    onDrop={onDropZone}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    className={`mt-3 p-4 border-2 border-dashed rounded-lg text-center ${isDragging ? 'bg-slate-50 border-slate-200' : 'bg-slate-50 dark:bg-slate-800 border-slate-200'}`}>
                    Drag & drop an Excel file (.xlsx / .xls) here, or use the file picker above.
                </div>
            )}

            {/* Grid + Summary (responsive) */}
            <div className="flex flex-col lg:flex-row gap-4 mt-4">
                <div className="flex-1 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                    <div className="p-2.5 bg-gray-100 dark:bg-gray-800 flex items-center gap-2.5">
                        <strong>{isManual ? "Manual Entry" : "Uploaded / Editable Grid"}</strong>
                        <div className="ml-auto flex gap-2">
                            <label className="flex items-center gap-1.5">
                                <input
                                    type="checkbox"
                                    checked={visibleRows.length > 0 && visibleRows.every((r) => r.sel)}
                                    onChange={(e) => setAllSelected(e.target.checked)}
                                />
                                Select all ({selCount})
                            </label>

                            {/* Bulk actions */}
                            <select
                                onChange={(e) => {
                                    if (e.target.value === "__") return;
                                    applyTypeToSelected(e.target.value);
                                    e.target.value = "__";
                                }}
                                defaultValue="__"
                                title="Apply type to selected rows"
                                aria-label="Apply type to selected rows"
                                className="mt-1 block w-48 sm:w-56 px-2 py-1 border rounded text-sm"
                            >
                                <option value="__" disabled>Apply type to selected…</option>
                                {typeList.map((t) => <option key={t}>{t}</option>)}
                            </select>
                            <button aria-label="Duplicate selected rows" onClick={duplicateSelected} disabled={selCount === 0} className="px-3 py-1 bg-white text-black border rounded text-sm">Duplicate</button>
                            <button aria-label="Delete selected rows" onClick={deleteSelected} disabled={selCount === 0} className="px-3 py-1 bg-red-600 text-white rounded text-sm">Delete</button>
                        </div>
                    </div>

                    <div className="overflow-x-auto text-slate-900 dark:text-gray-100">
                        {isManual ? (
                            <>
                                {/* Desktop table */}
                                <div className="hidden sm:block">
                                    <table style={table()}>
                                        <thead>
                                            <tr>
                                                <th style={th(40)}></th>
                                                <Th label="#" onClick={() => toggleSort("number")} active={sortKey === "number"} dir={sortDir} />
                                                <Th label="Room Name" onClick={() => toggleSort("name")} active={sortKey === "name"} dir={sortDir} />
                                                <Th label="Area (m²)" width={120} onClick={() => toggleSort("area")} active={sortKey === "area"} dir={sortDir} />
                                                <Th label="Occupancy Type" width={240} onClick={() => toggleSort("type")} active={sortKey === "type"} dir={sortDir} />
                                                <Th label="Load" width={100} onClick={() => toggleSort("load")} active={sortKey === "load"} dir={sortDir} />
                                                <th style={th(60)}></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {displayedManual.map((r) => (
                                                <tr key={r.id}>
                                                    <td style={td(40)}>
                                                        <input
                                                            type="checkbox"
                                                            checked={!!r.sel}
                                                            onChange={(e) =>
                                                                setManualRows((prev) => prev.map((x) => x.id === r.id ? { ...x, sel: e.target.checked } : x))
                                                            }
                                                        />
                                                    </td>
                                                    <td style={td(80)}>
                                                        <input value={r.number} onChange={(e) => updateManual(r.id, "number", e.target.value)} style={input(70)} className="w-full sm:w-20" />
                                                    </td>
                                                    <td style={td()}>
                                                        <input value={r.name} onChange={(e) => updateManual(r.id, "name", e.target.value)} style={input()} className="w-full" />
                                                    </td>
                                                    <td style={td(120)}>
                                                        <input
                                                            value={r.area}
                                                            onChange={(e) => updateManual(r.id, "area", e.target.value)}
                                                            style={input(100)}
                                                            inputMode="decimal"
                                                            placeholder="0"
                                                            className="w-full sm:w-24"
                                                        />
                                                    </td>
                                                    <td style={td(240)}>
                                                        <select
                                                            value={r.type}
                                                            onChange={(e) => updateManual(r.id, "type", e.target.value)}
                                                            style={select(220)}
                                                            className="w-full sm:w-56"
                                                        >
                                                            {typeList.map((t) => <option key={t} value={t}>{t}</option>)}
                                                        </select>
                                                    </td>
                                                    <td style={td(100)}><span style={pill()}>{r.load}</span></td>
                                                    <td style={td(60)}>
                                                        <button onClick={() => removeManualRow(r.id)} style={btn("danger")}>×</button>
                                                    </td>
                                                </tr>
                                            ))}
                                            {displayedManual.length === 0 && (
                                                <tr>
                                                    <td colSpan={7} style={{ padding: 16, textAlign: "center", color: "#666" }}>
                                                        No rows match your filters. Try clearing search/type filter.
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>

                                {/* Mobile cards */}
                                <div className="sm:hidden space-y-3">
                                    {displayedManual.length === 0 && (
                                        <div className="text-center text-slate-600">No rows match your filters. Try clearing search/type filter.</div>
                                    )}
                                    {displayedManual.map((r) => (
                                        <div key={r.id} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-gray-100 border border-slate-100 dark:border-slate-800 rounded-lg p-3">
                                            <div className="flex items-start gap-3">
                                                <input
                                                    type="checkbox"
                                                    checked={!!r.sel}
                                                    onChange={(e) => setManualRows((prev) => prev.map((x) => x.id === r.id ? { ...x, sel: e.target.checked } : x))}
                                                    className="mt-1"
                                                />
                                                <div className="flex-1">
                                                    <div className="flex justify-between">
                                                        <div>
                                                            <div className="text-sm font-semibold">{r.number}. {r.name}</div>
                                                            <div className="text-xs text-gray-500">{r.type}</div>
                                                        </div>
                                                        <div><span className="inline-block bg-gray-900 text-white rounded-full px-2 py-1 text-sm">{r.load}</span></div>
                                                    </div>
                                                    <div className="mt-2 grid grid-cols-2 gap-2">
                                                        <input value={r.number} onChange={(e) => updateManual(r.id, "number", e.target.value)} className="w-full px-2 py-1 border rounded" />
                                                        <input value={r.name} onChange={(e) => updateManual(r.id, "name", e.target.value)} className="w-full px-2 py-1 border rounded" />
                                                        <input value={r.area} onChange={(e) => updateManual(r.id, "area", e.target.value)} inputMode="decimal" placeholder="0" className="w-full px-2 py-1 border rounded" />
                                                        <select value={r.type} onChange={(e) => updateManual(r.id, "type", e.target.value)} className="w-full px-2 py-1 border rounded">
                                                            {typeList.map((t) => <option key={t} value={t}>{t}</option>)}
                                                        </select>
                                                    </div>
                                                </div>
                                                <button onClick={() => removeManualRow(r.id)} className="ml-2 text-red-600">×</button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        ) : (
                            <>
                                {/* Desktop table */}
                                <div className="hidden sm:block">
                                    <table style={table()}>
                                        <thead>
                                            <tr>
                                                <th style={th(40)}></th>
                                                <Th label="Room #" width={100} onClick={() => toggleSort("number")} active={sortKey === "number"} dir={sortDir} />
                                                <Th label="Room Name" onClick={() => toggleSort("name")} active={sortKey === "name"} dir={sortDir} />
                                                <Th label="Area (m²)" width={120} onClick={() => toggleSort("area")} active={sortKey === "area"} dir={sortDir} />
                                                <Th label="Occupancy Type" width={260} onClick={() => toggleSort("type")} active={sortKey === "type"} dir={sortDir} />
                                                <Th label="Load" width={100} onClick={() => toggleSort("load")} active={sortKey === "load"} dir={sortDir} />
                                                <th style={th(60)}></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {displayedGrid.map((r) => (
                                                <tr key={r.id}>
                                                    <td style={td(40)}>
                                                        <input
                                                            type="checkbox"
                                                            checked={!!r.sel}
                                                            onChange={(e) =>
                                                                setGridRows((prev) => prev.map((x) => x.id === r.id ? { ...x, sel: e.target.checked } : x))
                                                            }
                                                        />
                                                    </td>
                                                    <td style={td(100)}>
                                                        <input value={r["Room #"]} onChange={(e) => updateGrid(r.id, "Room #", e.target.value)} style={input(90)} className="w-full sm:w-20" />
                                                    </td>
                                                    <td style={td()}>
                                                        <input value={r["Room Name"]} onChange={(e) => updateGrid(r.id, "Room Name", e.target.value)} style={input()} className="w-full" />
                                                    </td>
                                                    <td style={td(120)}>
                                                        <input
                                                            value={r["Area (m²)"]}
                                                            onChange={(e) => updateGrid(r.id, "Area (m²)", e.target.value)}
                                                            style={input(100)}
                                                            inputMode="decimal"
                                                            placeholder="0"
                                                            className="w-full sm:w-24"
                                                        />
                                                    </td>
                                                    <td style={td(260)}>
                                                        <select
                                                            value={r["Occupancy Type"]}
                                                            onChange={(e) => updateGrid(r.id, "Occupancy Type", e.target.value)}
                                                            style={select(240)}
                                                            className="w-full sm:w-56"
                                                        >
                                                            {typeList.map((t) => <option key={t} value={t}>{t}</option>)}
                                                        </select>
                                                    </td>
                                                    <td style={td(100)}><span style={pill()}>{r["Occupant Load"]}</span></td>
                                                    <td style={td(60)}>
                                                        <button onClick={() => removeGridRow(r.id)} style={btn("danger")}>×</button>
                                                    </td>
                                                </tr>
                                            ))}
                                            {displayedGrid.length === 0 && (
                                                <tr>
                                                    <td colSpan={7} style={{ padding: 16, textAlign: "center", color: "#666" }}>
                                                        No rows match your filters. Try clearing search/type filter.
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>

                                {/* Mobile cards */}
                                <div className="sm:hidden space-y-3">
                                    {displayedGrid.length === 0 && (
                                        <div className="text-center text-slate-600">No rows match your filters. Try clearing search/type filter.</div>
                                    )}
                                    {displayedGrid.map((r) => (
                                        <div key={r.id} className="bg-white dark:bg-slate-900 text-slate-900 dark:text-gray-100 border border-slate-100 dark:border-slate-800 rounded-lg p-3">
                                            <div className="flex items-start gap-3">
                                                <input
                                                    type="checkbox"
                                                    checked={!!r.sel}
                                                    onChange={(e) => setGridRows((prev) => prev.map((x) => x.id === r.id ? { ...x, sel: e.target.checked } : x))}
                                                    className="mt-1"
                                                />
                                                <div className="flex-1">
                                                    <div className="flex justify-between">
                                                        <div>
                                                            <div className="text-sm font-semibold">{r["Room #"]}. {r["Room Name"]}</div>
                                                            <div className="text-xs text-gray-500">{r["Occupancy Type"]}</div>
                                                        </div>
                                                        <div><span className="inline-block bg-gray-900 text-white rounded-full px-2 py-1 text-sm">{r["Occupant Load"]}</span></div>
                                                    </div>
                                                    <div className="mt-2 grid grid-cols-2 gap-2">
                                                        <input value={r["Room #"]} onChange={(e) => updateGrid(r.id, "Room #", e.target.value)} className="w-full px-2 py-1 border rounded" />
                                                        <input value={r["Room Name"]} onChange={(e) => updateGrid(r.id, "Room Name", e.target.value)} className="w-full px-2 py-1 border rounded" />
                                                        <input value={r["Area (m²)"]} onChange={(e) => updateGrid(r.id, "Area (m²)", e.target.value)} inputMode="decimal" placeholder="0" className="w-full px-2 py-1 border rounded" />
                                                        <select value={r["Occupancy Type"]} onChange={(e) => updateGrid(r.id, "Occupancy Type", e.target.value)} className="w-full px-2 py-1 border rounded">
                                                            {typeList.map((t) => <option key={t} value={t}>{t}</option>)}
                                                        </select>
                                                    </div>
                                                </div>
                                                <button onClick={() => removeGridRow(r.id)} className="ml-2 text-red-600">×</button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>

                {/* Export / library loading overlay */}
                {exportLoading && (
                    <div ref={exportDialogRef} role="dialog" aria-modal="true" aria-label={`Exporting ${exportLoading}`} onKeyDown={(e) => {
                        // Allow Escape to cancel export and close the dialog
                        if (e.key === 'Escape') {
                            try {
                                if (activeWorkerRef.current) {
                                    try { activeWorkerRef.current.terminate(); } catch (ex) { }
                                    activeWorkerRef.current = null;
                                }
                                isAbortedRef.current = true;
                            } catch (ex) { }
                            setExportProgress({ pct: 0, msg: '' });
                            setTimeout(() => setExportLoading(""), 0);
                            showToast('Export cancelled', 'info');
                        }
                    }} className="fixed inset-0 flex items-center justify-center bg-black/40 z-50">
                        <div role="status" aria-live="polite" aria-busy="true" aria-describedby="export-progress-msg" className="bg-white p-5 rounded-lg min-w-[260px] shadow-2xl text-center text-slate-900 dark:text-slate-100">
                            <div className="mb-3">
                                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="mx-auto animate-spin">
                                    <circle cx="12" cy="12" r="10" stroke="#3b82f6" strokeWidth="4" strokeOpacity="0.25" />
                                    <path d="M22 12a10 10 0 0 1-10 10" stroke="#3b82f6" strokeWidth="4" strokeLinecap="round" />
                                </svg>
                            </div>
                            <div className="text-lg font-semibold mb-1">
                                {exportLoading === 'excel' && 'Preparing Excel file…'}
                                {exportLoading === 'pdfSummary' && 'Preparing PDF summary…'}
                                {exportLoading === 'pdfDetailed' && 'Preparing detailed PDF…'}
                                {exportLoading === 'template' && 'Preparing template…'}
                            </div>
                            <div className="text-sm text-slate-700 dark:text-slate-300 mb-3">This may take a few seconds while the export library downloads.</div>
                            {exportProgress && exportProgress.pct > 0 && (
                                <div className="mt-3 text-left">
                                    <div className="h-2 bg-slate-50 rounded overflow-hidden">
                                        <div className="h-full bg-slate-700" style={{ width: `${Math.min(100, exportProgress.pct)}%`, transition: 'width 240ms linear' }} />
                                    </div>
                                    <div id="export-progress-msg" className="text-xs text-slate-700 dark:text-slate-300 mt-1">{exportProgress.msg || `${exportProgress.pct}%`}</div>
                                </div>
                            )}
                            {(activeWorkerRef.current || exportProgress.pct > 0) && (
                                <div className="mt-3">
                                    <button ref={exportCancelRef} onClick={() => {
                                        try {
                                            if (activeWorkerRef.current) {
                                                try { activeWorkerRef.current.terminate(); } catch (e) { }
                                                activeWorkerRef.current = null;
                                            }
                                            isAbortedRef.current = true;
                                        } catch (e) { }
                                        setExportProgress({ pct: 0, msg: '' });
                                        setExportLoading("");
                                        showToast('Export cancelled', 'info');
                                    }} className="mt-2 px-3 py-1 bg-red-600 text-white rounded">Cancel</button>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Toast */}
                {toast && (
                    <div aria-live="polite" className="fixed right-5 bottom-5 z-50">
                        <div className={`min-w-[220px] px-4 py-2 rounded shadow-lg text-white ${toast.type === 'success' ? 'bg-green-600' : toast.type === 'error' ? 'bg-red-600' : 'bg-gray-700'}`}>
                            <div className="text-sm font-semibold">{toast.msg}</div>
                        </div>
                    </div>
                )}

                {/* Totals */}
                <aside className="w-full lg:w-80 border border-gray-200 dark:border-gray-700 rounded-lg p-4 h-fit">
                    <h3 className="mt-0">Totals</h3>
                    <div className="mb-2 text-sm text-gray-600 dark:text-gray-400">Code: {codeSets[codeId]?.label || codeId}</div>
                    <TotalsPanel rows={rowsForExport()} />
                </aside>
            </div>
        </div>
    );
}

/* ===================== small pieces ===================== */
function TotalsPanel({ rows }) {
    const grouped = useMemo(() => {
        const out = {};
        let grand = 0;
        rows.forEach((r) => {
            const t = r["Occupancy Type"];
            const l = toNumber(r["Occupant Load"]);
            out[t] = (out[t] || 0) + l;
            grand += l;
        });
        return { out, grand };
    }, [rows]);

    return (
        <>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {Object.entries(grouped.out).map(([t, v]) => (
                    <li key={t} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0" }}>
                        <span>{t}</span>
                        <strong>{v}</strong>
                    </li>
                ))}
            </ul>
            <hr style={{ margin: "12px 0" }} />
            <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Grand Total</span>
                <strong>{grouped.grand}</strong>
            </div>
        </>
    );
}

function Th({ label, onClick, active, dir, width }) {
    return (
        <th scope="col" style={th(width)} onClick={onClick} role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined} onKeyDown={onClick ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
            }
        } : undefined}>
            <span style={{ cursor: onClick ? "pointer" : "default", userSelect: "none" }}>
                {label} {active ? (dir === "asc" ? "▲" : "▼") : ""}
            </span>
        </th>
    );
}

/* ===================== styles ===================== */
const _bar = () => ({
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    border: "1px solid #e5e7eb",
    borderRadius: 10,
    padding: 12,
    marginTop: 12
});
const table = () => ({ width: "100%", borderCollapse: "separate", borderSpacing: 0 });
const th = (w) => ({
    textAlign: "left",
    background: "#f8fafc",
    padding: "10px 12px",
    borderBottom: "1px solid #e5e7eb",
    width: w,
    whiteSpace: "nowrap",
    fontWeight: 700,
    fontSize: 13
});
const td = (w) => ({
    padding: "8px 12px",
    borderBottom: "1px solid #f1f5f9",
    width: w,
    verticalAlign: "middle"
});
const input = (w) => ({
    width: w || "100%",
    padding: "6px 8px",
    borderRadius: 8,
    border: "1px solid #e5e7eb",
    fontSize: 14
});
const select = (w) => ({
    width: w || "100%",
    padding: "6px 8px",
    borderRadius: 8,
    border: "1px solid #e5e7eb",
    fontSize: 14,
    background: "#fff"
});
const btn = (variant = "primary") => {
    const base =
        variant === "danger"
            ? { background: "#ef4444", color: "#fff", border: "1px solid #dc2626" }
            : variant === "ghost"
                ? { background: "#fff", color: "#111", border: "1px solid #e5e7eb" }
                : { background: "#2563eb", color: "#fff", border: "1px solid #1d4ed8" };
    return { ...base, borderRadius: 8, padding: "8px 12px", fontSize: 14, cursor: "pointer" };
};
const pill = () => ({
    display: "inline-block",
    padding: "4px 10px",
    borderRadius: 999,
    background: "#111827",
    color: "#fff",
    fontSize: 13,
    lineHeight: 1.4
});
