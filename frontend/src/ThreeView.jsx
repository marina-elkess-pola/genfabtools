import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

// Simple Three.js perspective viewer for ParkCore geometry
export default function ThreeView({ points = [], levels = [], currentLevelIndex = 0, unitsPerMeter = 1, cplaneOrigin = { x: 0, y: 0 }, cplaneXDir = { x: 1, y: 0 }, onPointsChange = null, onPointsDragEnd = null }) {
    const mountRef = useRef(null);
    const sceneRef = useRef(null);
    const cameraRef = useRef(null);
    const rendererRef = useRef(null);
    const controlsRef = useRef(null);
    const polyGroupRef = useRef(null);
    const stallsGroupRef = useRef(null);
    const pointsRef = useRef(points);
    const cplaneOriginRef = useRef(cplaneOrigin);
    const cplaneXDirRef = useRef(cplaneXDir);

    // keep pointsRef up to date so event handlers use latest values without re-creating scene
    useEffect(() => { pointsRef.current = points; }, [points]);
    // keep cplane refs current so drag handlers use latest CPlane without recreating scene
    useEffect(() => { cplaneOriginRef.current = cplaneOrigin; cplaneXDirRef.current = cplaneXDir; }, [cplaneOrigin, cplaneXDir]);

    useEffect(() => {
        const mount = mountRef.current;
        if (!mount) return;

        const width = mount.clientWidth || 800;
        const height = mount.clientHeight || 480;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf8fafc);
        sceneRef.current = scene;

        const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100000);
        camera.position.set(0, -Math.max(width, height) * 0.8, Math.max(width, height) * 0.7);
        camera.up.set(0, 0, 1); // Z up
        cameraRef.current = camera;

        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(width, height);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        mount.appendChild(renderer.domElement);
        rendererRef.current = renderer;

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.target.set(0, 0, 0);
        controls.enableDamping = true;
        controlsRef.current = controls;

        // lights
        const ambient = new THREE.AmbientLight(0xffffff, 0.8);
        scene.add(ambient);
        const dir = new THREE.DirectionalLight(0xffffff, 0.6);
        dir.position.set(100, -200, 300);
        scene.add(dir);

        // helper: grid on CPlane
        const gridSize = 1000;
        const gridDivisions = 40;
        const gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x10b981, 0xe6eef6);
        gridHelper.rotation.x = Math.PI / 2; // lie on X-Y
        scene.add(gridHelper);

        // create polyGroup for lines and point markers
        const polyGroup = new THREE.Group();
        polyGroupRef.current = polyGroup;
        scene.add(polyGroup);

        // create a group for stalls (updated separately when `levels` changes)
        const stallsGroup = new THREE.Group();
        stallsGroupRef.current = stallsGroup;
        scene.add(stallsGroup);

        // show CPlane axes
        const axisLen = Math.max(width, height) * 0.6;
        const xDir = new THREE.Vector3(cplaneXDir.x, -cplaneXDir.y, 0).normalize();
        const yDir = new THREE.Vector3(-cplaneXDir.y, -cplaneXDir.x, 0).normalize();
        const origin = new THREE.Vector3(cplaneOrigin.x, -cplaneOrigin.y, 0);

        const lineGeom = (dirVec) => {
            const pts = [origin.clone().addScaledVector(dirVec, -axisLen * 0.6), origin.clone().addScaledVector(dirVec, axisLen * 0.6)];
            return new THREE.BufferGeometry().setFromPoints(pts);
        };
        const xLine = new THREE.Line(lineGeom(xDir), new THREE.LineBasicMaterial({ color: 0xef4444 }));
        const yLine = new THREE.Line(lineGeom(yDir), new THREE.LineBasicMaterial({ color: 0x10b981 }));
        scene.add(xLine); scene.add(yLine);
        // arrow helpers for clearer direction indicators (X=red, Y=green, Z=gray)
        try {
            // make arrowheads subtle (smaller multipliers so arrows don't dominate the scene)
            const arrowLen = axisLen * 0.45;
            const arrowHead = Math.max(3, arrowLen * 0.03);
            const arrowWidth = Math.max(1.5, arrowLen * 0.015);
            const arrowX = new THREE.ArrowHelper(xDir.clone(), origin.clone(), arrowLen, 0xef4444, arrowHead, arrowWidth);
            const arrowY = new THREE.ArrowHelper(yDir.clone(), origin.clone(), arrowLen, 0x10b981, arrowHead, arrowWidth);
            const zDir = new THREE.Vector3(0, 0, 1);
            const arrowZ = new THREE.ArrowHelper(zDir, origin.clone(), arrowLen * 0.6, 0x6b7280, arrowHead * 0.8, arrowWidth * 0.8);
            scene.add(arrowX); scene.add(arrowY); scene.add(arrowZ);
        } catch (e) {
            // ArrowHelper may not be available in some minimal builds; ignore on failure
        }

        // auto-fit camera to content
        const box = new THREE.Box3().setFromObject(scene);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        controls.target.copy(center);
        camera.position.set(center.x - size.x * 0.8, center.y - size.y * 0.8, Math.max(size.x, size.y, 200));
        camera.lookAt(center);

        // handle resize
        const onResize = () => {
            const w = mount.clientWidth || 800; const h = mount.clientHeight || 480;
            camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
        };
        window.addEventListener('resize', onResize);

        // interaction: raycast to select/drag points on the user CPlane
        const raycaster = new THREE.Raycaster();
        const pointer = new THREE.Vector2();
        let draggingIndex = -1;
        // drag state in CPlane coordinates
        let dragOffsetLocal = new THREE.Vector2(0, 0);
        let basisX = new THREE.Vector3(1, 0, 0);
        let basisY = new THREE.Vector3(0, 1, 0);
        let originVec = new THREE.Vector3(0, 0, 0);

        const findNearestPoint = (mouseNDC, threshold = 12) => {
            raycaster.setFromCamera(mouseNDC, camera);
            const tempV = new THREE.Vector3();
            let best = { idx: -1, dist: Infinity };
            const canvas = renderer.domElement;
            const rect = canvas.getBoundingClientRect();
            const pts = pointsRef.current || [];
            for (let i = 0; i < pts.length; i++) {
                tempV.set(pts[i].x, -pts[i].y, 0);
                tempV.project(camera);
                const sx = (tempV.x * 0.5 + 0.5) * rect.width;
                const sy = (- tempV.y * 0.5 + 0.5) * rect.height;
                const mx = (mouseNDC.x * 0.5 + 0.5) * rect.width;
                const my = (- mouseNDC.y * 0.5 + 0.5) * rect.height;
                const d = Math.hypot(sx - mx, sy - my);
                if (d < best.dist) { best = { idx: i, dist: d } }
            }
            if (best.dist <= threshold) return best.idx;
            return -1;
        };

        const onPointerDown = (ev) => {
            const rect = renderer.domElement.getBoundingClientRect();
            pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
            pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
            const idx = findNearestPoint(pointer, 10);
            if (idx >= 0) {
                draggingIndex = idx;
                // compute CPlane basis and origin from latest refs
                originVec = new THREE.Vector3(cplaneOriginRef.current.x, -cplaneOriginRef.current.y, 0);
                basisX = new THREE.Vector3(cplaneXDirRef.current.x, -cplaneXDirRef.current.y, 0).normalize();
                basisY = new THREE.Vector3(-cplaneXDirRef.current.y, -cplaneXDirRef.current.x, 0).normalize();
                // build world plane from basis (normal may still be Z for typical CPlane)
                const normal = new THREE.Vector3().crossVectors(basisX, basisY).normalize();
                const worldPlane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, originVec);
                raycaster.setFromCamera(pointer, camera);
                const hit = raycaster.ray.intersectPlane(worldPlane, new THREE.Vector3());
                if (hit) {
                    const pts = pointsRef.current || [];
                    const ptWorld = new THREE.Vector3(pts[idx].x, -pts[idx].y, 0);
                    // project hit and point into CPlane local coords
                    const hitLocalX = hit.clone().sub(originVec).dot(basisX);
                    const hitLocalY = hit.clone().sub(originVec).dot(basisY);
                    const ptLocalX = ptWorld.clone().sub(originVec).dot(basisX);
                    const ptLocalY = ptWorld.clone().sub(originVec).dot(basisY);
                    dragOffsetLocal.set(hitLocalX - ptLocalX, hitLocalY - ptLocalY);
                } else {
                    dragOffsetLocal.set(0, 0);
                }
                // disable orbit controls while dragging to avoid camera interaction
                if (controlsRef.current) controlsRef.current.enabled = false;
                try { renderer.domElement.style.cursor = 'grabbing'; } catch (e) { }
                // ensure other handlers don't act
                ev.preventDefault();
                ev.stopPropagation();
            }
        };

        const onPointerMove = (ev) => {
            if (draggingIndex < 0) return;
            const rect = renderer.domElement.getBoundingClientRect();
            pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
            pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
            // recompute plane & basis from latest CPlane refs (in case user changed during interaction)
            originVec = new THREE.Vector3(cplaneOriginRef.current.x, -cplaneOriginRef.current.y, 0);
            basisX = new THREE.Vector3(cplaneXDirRef.current.x, -cplaneXDirRef.current.y, 0).normalize();
            basisY = new THREE.Vector3(-cplaneXDirRef.current.y, -cplaneXDirRef.current.x, 0).normalize();
            const normal = new THREE.Vector3().crossVectors(basisX, basisY).normalize();
            const worldPlane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, originVec);
            raycaster.setFromCamera(pointer, camera);
            const hit = raycaster.ray.intersectPlane(worldPlane, new THREE.Vector3());
            if (hit) {
                // compute hit in CPlane local coords
                const hitLocalX = hit.clone().sub(originVec).dot(basisX);
                const hitLocalY = hit.clone().sub(originVec).dot(basisY);
                // subtract the local drag offset to get new local coordinates for the dragged point
                const newLocalX = hitLocalX - dragOffsetLocal.x;
                const newLocalY = hitLocalY - dragOffsetLocal.y;
                // convert back to world coords
                const newWorld = originVec.clone().add(basisX.clone().multiplyScalar(newLocalX)).add(basisY.clone().multiplyScalar(newLocalY));
                const newX = newWorld.x;
                const newY = -newWorld.y;
                const pts = pointsRef.current || [];
                const updated = pts.map((p, i) => i === draggingIndex ? { x: newX, y: newY } : { x: p.x, y: p.y });
                // update local ref immediately so pointerup/readers get fresh data
                pointsRef.current = updated;
                if (typeof onPointsChange === 'function') onPointsChange(updated);
                ev.preventDefault();
                ev.stopPropagation();
            }
        };

        const onPointerUp = (ev) => {
            if (draggingIndex >= 0 && typeof onPointsDragEnd === 'function') {
                const pts = pointsRef.current || [];
                onPointsDragEnd(pts.map(p => ({ x: p.x, y: p.y })));
            }
            draggingIndex = -1;
            if (controlsRef.current) controlsRef.current.enabled = true;
            try { renderer.domElement.style.cursor = 'default'; } catch (e) { }
            if (ev) { ev.preventDefault(); ev.stopPropagation(); }
        };
        renderer.domElement.addEventListener('pointerdown', onPointerDown);
        window.addEventListener('pointermove', onPointerMove);
        window.addEventListener('pointerup', onPointerUp);

        let rafId;
        const animate = () => {
            controls.update();
            // update visuals from latest pointsRef
            const ptsNow = pointsRef.current || [];
            if (polyGroupRef.current) {
                const g = polyGroupRef.current;
                while (g.children.length) g.remove(g.children[0]);
                if (ptsNow.length > 0) {
                    const ptsV = ptsNow.map(p => new THREE.Vector3(p.x, -p.y, 0));
                    const closed = ptsNow.length >= 3 && (ptsNow[0].x !== ptsNow[ptsNow.length - 1].x || ptsNow[0].y !== ptsNow[ptsNow.length - 1].y);
                    const linePts = closed ? ptsV.concat([ptsV[0]]) : ptsV;
                    if (linePts.length >= 2) {
                        const lineGeom = new THREE.BufferGeometry().setFromPoints(linePts);
                        const lineMat = new THREE.LineBasicMaterial({ color: 0x333333, linewidth: 1 });
                        const line = new THREE.Line(lineGeom, lineMat);
                        g.add(line);
                    }
                    const sphGeo = new THREE.SphereGeometry(Math.max(3, Math.min(12, Math.max(window.innerWidth, window.innerHeight) * 0.002)), 12, 8);
                    ptsNow.forEach((p, i) => {
                        const m = new THREE.Mesh(sphGeo, new THREE.MeshStandardMaterial({ color: 0x111111 }));
                        m.position.set(p.x, -p.y, 0.02);
                        m.userData = { pointIndex: i };
                        g.add(m);
                    });
                }
            }
            const renderer = rendererRef.current; const camera = cameraRef.current;
            renderer.render(scene, camera);
            rafId = requestAnimationFrame(animate);
        };
        animate();

        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener('resize', onResize);
            renderer.domElement.removeEventListener('pointerdown', onPointerDown);
            window.removeEventListener('pointermove', onPointerMove);
            window.removeEventListener('pointerup', onPointerUp);
            controls.dispose();
            renderer.dispose();
            mount.removeChild(renderer.domElement);
        };
    }, []);

    // When points prop changes, update the ref; visuals are read from ref in animation loop
    useEffect(() => { pointsRef.current = points; }, [points]);

    // Update stalls meshes when levels change so 3D reflects additions/deletions
    useEffect(() => {
        const scene = sceneRef.current; const stallsGroup = stallsGroupRef.current;
        if (!scene || !stallsGroup) return;
        // clear existing stalls
        while (stallsGroup.children.length) stallsGroup.remove(stallsGroup.children[0]);
        // add stalls from levels
        levels.forEach((lvl, li) => {
            (lvl.stallsPreview || []).forEach((s, i) => {
                const hw = s.hw || 0.5; const hd = s.hd || 1;
                const x = s.x; const y = -s.y; const z = (Number(lvl.elevation) || 0);
                const type = s.type || 'stall';
                if (type === 'stall') {
                    const geom = new THREE.BoxGeometry(hw * 2, hd * 2, 0.1);
                    const mat = new THREE.MeshStandardMaterial({ color: 0x1e64c8, opacity: li === currentLevelIndex ? 0.32 : 0.12, transparent: true });
                    const mesh = new THREE.Mesh(geom, mat);
                    mesh.position.set(x, y, z + 0.05);
                    mesh.userData = { levelIndex: li, stallIndex: i, type };
                    stallsGroup.add(mesh);
                    return;
                }
                if (type === 'aisle') {
                    const geom = new THREE.BoxGeometry(hw * 2, hd * 2, 0.06);
                    const mat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, opacity: 0.22, transparent: true });
                    const mesh = new THREE.Mesh(geom, mat);
                    mesh.position.set(x, y, z + 0.03);
                    mesh.userData = { levelIndex: li, featureIndex: i, type };
                    stallsGroup.add(mesh);
                    return;
                }
                if (type === 'street' || type === 'perimeter') {
                    const geom = new THREE.BoxGeometry(hw * 2, hd * 2, 0.12);
                    const mat = new THREE.MeshStandardMaterial({ color: 0x0b1723, opacity: 0.22, transparent: true });
                    const mesh = new THREE.Mesh(geom, mat);
                    mesh.position.set(x, y, z + 0.06);
                    mesh.userData = { levelIndex: li, featureIndex: i, type };
                    stallsGroup.add(mesh);
                    return;
                }
                if (type === 'ramp') {
                    // simple ramp representation: a slightly taller orange block; ramps can include from/to metadata
                    const rampHeight = Math.max(0.1, Math.abs((levels[s.to]?.elevation || 0) - (levels[s.from]?.elevation || 0)) || 0.3);
                    const geom = new THREE.BoxGeometry(hw * 2, hd * 2, rampHeight);
                    const mat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, opacity: 0.36, transparent: true });
                    const mesh = new THREE.Mesh(geom, mat);
                    // place ramp base at the lower elevation so it visually spans up
                    const baseZ = Math.min(Number(levels[s.from]?.elevation || 0), Number(levels[s.to]?.elevation || 0));
                    mesh.position.set(x, y, baseZ + (rampHeight / 2));
                    mesh.userData = { levelIndex: li, featureIndex: i, type, from: s.from, to: s.to };
                    stallsGroup.add(mesh);
                    return;
                }
                // default fallback
                const geom = new THREE.BoxGeometry(hw * 2, hd * 2, 0.05);
                const mat = new THREE.MeshStandardMaterial({ color: 0x999999, opacity: 0.12, transparent: true });
                const mesh = new THREE.Mesh(geom, mat);
                mesh.position.set(x, y, z + 0.02);
                mesh.userData = { levelIndex: li, featureIndex: i, type };
                stallsGroup.add(mesh);
            });
        });
    }, [levels, currentLevelIndex]);

    return <div ref={mountRef} style={{ width: '100%', height: 480 }} />;
}
