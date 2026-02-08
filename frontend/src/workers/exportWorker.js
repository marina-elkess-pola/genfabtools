// Worker: generate XLSX buffers using dynamic import of xlsx
// Worker: support two actions:
// - generateXLSX: receive rows (array of objects) -> returns { action: 'resultXLSX', buffer }
// - parseXLSX: receive an ArrayBuffer for an uploaded XLSX -> returns { action: 'parsedRows', rows }
self.onmessage = async (e) => {
    const { action } = e.data || {};
    try {
        // Lightweight ping to verify the worker is running without loading heavy libs
        if (action === 'ping') {
            postMessage({ action: 'pong' });
            return;
        }

        // lazy-load xlsx only when needed for heavy actions
        postMessage({ action: 'progress', pct: 2, msg: 'Initializing worker…' });
        const XLSX = await import('xlsx');
        postMessage({ action: 'progress', pct: 8, msg: 'xlsx loaded' });

        if (action === 'generateXLSX') {
            const { rows } = e.data || {};
            const headers = ["Room #", "Room Name", "Area (m²)", "Occupancy Type", "Occupant Load"];
            const normalized = (rows || []).map(r => ({
                "Room #": r["Room #"] ?? r["Room#"] ?? r.number ?? '',
                "Room Name": r["Room Name"] ?? r.name ?? '',
                "Area (m²)": r["Area (m²)"] ?? r.area ?? '',
                "Occupancy Type": r["Occupancy Type"] ?? r.type ?? '',
                "Occupant Load": r["Occupant Load"] ?? r.load ?? ''
            }));

            const ws = XLSX.utils.json_to_sheet(normalized, { header: headers });
            const wb = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(wb, ws, 'Occupancy');
            const buf = XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
            // buf is a Uint8Array; transfer its ArrayBuffer back to main thread
            postMessage({ action: 'progress', pct: 15, msg: 'Preparing sheet' });
            postMessage({ action: 'resultXLSX', buffer: buf.buffer }, [buf.buffer]);
            return;
        }

        if (action === 'parseXLSX') {
            // Expect an ArrayBuffer in `arrayBuffer` property
            const { arrayBuffer } = e.data || {};
            if (!arrayBuffer) {
                postMessage({ action: 'error', message: 'No ArrayBuffer provided to parseXLSX' });
                return;
            }
            try {
                // Parse from an ArrayBuffer - use type: 'array'
                const data = new Uint8Array(arrayBuffer);
                postMessage({ action: 'progress', pct: 20, msg: 'Parsing file' });
                const wb = XLSX.read(data, { type: 'array' });
                const ws = wb.Sheets[wb.SheetNames[0]];
                const rows = XLSX.utils.sheet_to_json(ws, { defval: '' }).map((row, i) => {
                    const number = row["Room #"] ?? row["Room Number"] ?? String(i + 1);
                    const name = row["Room Name"] ?? row["Name"] ?? `Space ${i + 1}`;
                    const area = row["Area (m²)"] ?? row["Area"] ?? '';
                    const tRaw = row["Occupancy Type"] ?? row["Type"];
                    return {
                        id: i + 1,
                        sel: false,
                        "Room #": String(number),
                        "Room Name": String(name),
                        "Area (m²)": area,
                        "Occupancy Type": tRaw ?? '',
                        "Occupant Load": 0
                    };
                });
                postMessage({ action: 'progress', pct: 55, msg: 'Extracting sheet' });
                postMessage({ action: 'parsedRows', rows });
                postMessage({ action: 'progress', pct: 100, msg: 'Parsed' });
                return;
            } catch (err) {
                postMessage({ action: 'error', message: String(err) });
                return;
            }
        }

        postMessage({ action: 'error', message: 'Unknown action: ' + String(action) });
    } catch (err) {
        postMessage({ action: 'error', message: String(err) });
    }
};
