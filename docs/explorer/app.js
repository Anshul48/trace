// TRACE Research Explorer (Vanilla JS, Zero External Dependencies)
// Authentic Overlapping DAG Visualizer & 10M Qualification Analysis
(function() {
  'use strict';

  // Shipped-file descriptors (earlier-freeze bytes still staged under docs/explorer/;
  // required fail-closed so the canvas keeps rendering. Displayed statistics site-wide
  // are the latest measured run seam12a (o94-scale10m) — see SEAM12A_* below.
  const VERIFIED_SOURCEFREEZE = '38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54';
  const VERIFIED_10M_PIN = 'e8334c07-731d-4ff9-a292-8329b89c41b9:0:166457';
  const EXPECTED_10M_GZIP_BYTES = 7254185;
  const EXPECTED_10M_GZIP_SHA256 = '15d2b2ebde19b5f183a3a40da7f1057601d2503ba15259627d7296de57344089';
  const EXPECTED_10M_PLAIN_BYTES = 21695279;
  const EXPECTED_10M_PLAIN_SHA256 = '4dfc96ed7276eb5cbe42f4bed40808adb00811c7d55a8b7a1b6711b9a76a96b0';
  const MAX_PAYLOAD_BYTES = 32 * 1024 * 1024; // 32 MiB response/decompression bound

  // State
  let local20kData = null;
  let graph10mData = null;
  let qualificationData = null;
  let probeList = [];
  let currentDataset = '20k'; // '10m' or '20k' — tour defaults to the small graph
  let currentClusterFocus = 'overview';
  let currentProbeIndex = 0;
  let currentStep = 1;
  let selectedLso = false;
  let datasetErrors = {
    '10m': null,
    '20k': null
  };

  // Canvas State
  let zoomLevel = 1.0;
  let panX = 0;
  let panY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let hoveredNode = null;
  let selectedNode = null;
  let nodesToRender = [];
  let edgesToRender = [];

  // Animation State
  let isPlaying = false;
  let playTimer = null;
  let playSpeed = 1;

  // DOM Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  const phaseBar = document.getElementById('phase-timeline-bar');
  const phaseLegend = document.getElementById('phase-legend');
  const querySelect = document.getElementById('query-select');
  const modeRadios = document.querySelectorAll('input[name="lso-mode"]');
  const stepCards = document.querySelectorAll('.step-card');
  const stepDetailPanel = document.getElementById('step-detail-panel');
  const canvas = document.getElementById('topology-canvas');
  const ctx = canvas ? canvas.getContext('2d') : null;
  const treeLevelSelect = document.getElementById('tree-level-select');
  const datasetSelect = document.getElementById('topology-dataset-select');
  const clusterSelect = document.getElementById('cluster-focus-select');
  const searchInput = document.getElementById('node-search-input');
  const btnZoomIn = document.getElementById('btn-zoom-in');
  const btnZoomOut = document.getElementById('btn-zoom-out');
  const btnResetZoom = document.getElementById('btn-reset-zoom');
  const canvasTooltip = document.getElementById('canvas-tooltip');
  const nodeInspectorContent = document.getElementById('node-inspector-content');
  const statusBanner = document.getElementById('topology-status-banner');
  const btnStepPrev = document.getElementById('btn-step-prev');
  const btnStepNext = document.getElementById('btn-step-next');
  const btnPlayPause = document.getElementById('btn-play-pause');
  const speedSelect = document.getElementById('replay-speed');

  // Hero CTA Buttons
  const ctaTourStart = document.getElementById('cta-tour-start');
  const ctaExplore10m = document.getElementById('cta-explore-10m');
  const ctaExplore20k = document.getElementById('cta-explore-20k');
  const ctaQueryReplay = document.getElementById('cta-query-replay');

  // Latest measured run seam12a (o94-scale10m): observed phase walls (s).
  // The staged qualification_10m.json still carries the earlier freeze, so the
  // timeline renders these measured constants and says so in the caption.
  const SEAM12A_WALLS_S = {
    ingest_visible_prepare: 586.9,
    initial_drain_prepare: 999.4,
    append_ingest_readers: 1163.2,
    source_capacity_rejection: 1.83,
    prepare_rejection_fresh: 170.3,
    writer_kill_restart: 516.5,
    remaining_drain_readers: 4654.4,
    repair_to_zero: 1162.1
  };
  const SEAM12A_TOTAL_WALL_S = 9494.9;

  const phaseColors = {
    ingest_visible_prepare: '#38bdf8',
    initial_drain_prepare: '#22d3ee',
    append_ingest_readers: '#34d399',
    source_capacity_rejection: '#f43f5e',
    prepare_rejection_fresh: '#fbbf24',
    writer_kill_restart: '#f97316',
    remaining_drain_readers: '#2dd4bf',
    repair_to_zero: '#ec4899'
  };

  const phaseNames = {
    ingest_visible_prepare: 'Ingest (visible + prepare)',
    initial_drain_prepare: 'Initial drain + prepare',
    append_ingest_readers: 'Append ingest + readers',
    source_capacity_rejection: 'Source-capacity rejection',
    prepare_rejection_fresh: 'Prepare rejection (fresh frontier)',
    writer_kill_restart: 'Writer kill + restart',
    remaining_drain_readers: 'Remaining drain + readers',
    repair_to_zero: 'Repair to zero (6 iters, 5,847 to 0)'
  };

  // Init Tabs & Hero CTAs
  function initTabs() {
    tabButtons.forEach((btn, idx) => {
      btn.addEventListener('click', () => switchTab(btn));
      btn.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight') {
          const next = tabButtons[(idx + 1) % tabButtons.length];
          next.focus();
          switchTab(next);
        } else if (e.key === 'ArrowLeft') {
          const prev = tabButtons[(idx - 1 + tabButtons.length) % tabButtons.length];
          prev.focus();
          switchTab(prev);
        }
      });
    });

    if (ctaExplore10m) {
      ctaExplore10m.addEventListener('click', () => {
        const topTab = document.getElementById('tab-btn-topology');
        if (topTab) switchTab(topTab);
        if (datasetSelect) {
          datasetSelect.value = '10m';
          currentDataset = '10m';
          resetView();
          populateClusterSelector();
          updateStatusBanner();
          layoutAndDrawTopology();
        }
      });
    }

    if (ctaExplore20k) {
      ctaExplore20k.addEventListener('click', () => {
        const topTab = document.getElementById('tab-btn-topology');
        if (topTab) switchTab(topTab);
        if (datasetSelect) {
          datasetSelect.value = '20k';
          currentDataset = '20k';
          resetView();
          populateClusterSelector();
          updateStatusBanner();
          layoutAndDrawTopology();
        }
      });
    }

    if (ctaQueryReplay) {
      ctaQueryReplay.addEventListener('click', () => {
        const queryTab = document.getElementById('tab-btn-queries');
        if (queryTab) switchTab(queryTab);
      });
    }

    if (ctaTourStart) {
      ctaTourStart.addEventListener('click', () => {
        startTour(1);
      });
    }
  }

  function switchTab(btn) {
    tabButtons.forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    tabPanels.forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    const target = document.getElementById(btn.getAttribute('data-tab'));
    if (target) {
      target.classList.add('active');
      if (btn.getAttribute('data-tab') === 'tab-topology') {
        layoutAndDrawTopology();
      }
    }
  }

  // Web Crypto SHA-256 Buffer Hasher
  async function computeSha256Hex(buffer) {
    if (!window.crypto || !window.crypto.subtle || typeof window.crypto.subtle.digest !== 'function') {
      throw new Error('Web Cryptography API (window.crypto.subtle.digest) is required for SHA-256 validation');
    }
    const digest = await window.crypto.subtle.digest('SHA-256', buffer);
    const bytes = new Uint8Array(digest);
    let hex = '';
    for (let i = 0; i < bytes.length; i++) {
      hex += bytes[i].toString(16).padStart(2, '0');
    }
    return hex;
  }

  // DecompressionStream Gzip Loader with Plain JSON Fallback & Pre-JSON SHA-256 Verification
  async function loadGzipOrJson(gzPath, jsonPath, options = {}) {
    const expectedGzBytes = options.expectedGzBytes || EXPECTED_10M_GZIP_BYTES;
    const expectedGzSha = options.expectedGzSha || EXPECTED_10M_GZIP_SHA256;
    const expectedPlainBytes = options.expectedPlainBytes || EXPECTED_10M_PLAIN_BYTES;
    const expectedPlainSha = options.expectedPlainSha || EXPECTED_10M_PLAIN_SHA256;
    const maxBytes = options.maxBytes || MAX_PAYLOAD_BYTES;

    const hasDS = typeof DecompressionStream !== 'undefined';

    if (hasDS) {
      let gzResp = null;
      try {
        gzResp = await fetch(gzPath);
      } catch (e) {
        console.warn(`Gzip fetch failed for ${gzPath}, checking plain fallback:`, e);
      }

      if (gzResp && gzResp.ok) {
        // Read verified byte buffer
        const gzBuffer = await gzResp.arrayBuffer();
        if (gzBuffer.byteLength > maxBytes) {
          throw new Error(`10M gzip payload exceeds 32MiB bound: ${gzBuffer.byteLength} bytes`);
        }
        if (gzBuffer.byteLength !== expectedGzBytes) {
          throw new Error(`10M gzip byte length mismatch: got ${gzBuffer.byteLength}, expected ${expectedGzBytes}`);
        }

        // Crypto Subtle SHA-256 check BEFORE any JSON use
        const gzSha = await computeSha256Hex(gzBuffer);
        if (gzSha !== expectedGzSha) {
          throw new Error(`10M gzip SHA-256 mismatch: got ${gzSha}, expected ${expectedGzSha}`);
        }

        // Real browser DecompressionStream decompression
        const ds = new DecompressionStream('gzip');
        const writer = ds.writable.getWriter();
        writer.write(new Uint8Array(gzBuffer));
        writer.close();

        const reader = ds.readable.getReader();
        const chunks = [];
        let totalDecompressed = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          totalDecompressed += value.byteLength;
          if (totalDecompressed > maxBytes) {
            throw new Error(`10M decompressed payload exceeds 32MiB bound: ${totalDecompressed} bytes`);
          }
          chunks.push(value);
        }

        const plainBuffer = new Uint8Array(totalDecompressed);
        let offset = 0;
        for (const chunk of chunks) {
          plainBuffer.set(chunk, offset);
          offset += chunk.byteLength;
        }

        if (plainBuffer.byteLength !== expectedPlainBytes) {
          throw new Error(`10M decompressed byte length mismatch: got ${plainBuffer.byteLength}, expected ${expectedPlainBytes}`);
        }

        // Validate plain hash after decompression
        const plainSha = await computeSha256Hex(plainBuffer.buffer);
        if (plainSha !== expectedPlainSha) {
          throw new Error(`10M decompressed plain SHA-256 mismatch: got ${plainSha}, expected ${expectedPlainSha}`);
        }

        const text = new TextDecoder('utf-8').decode(plainBuffer);
        return JSON.parse(text);
      }
    }

    // Fallback: fetch plain JSON (only when DS absent or gzip fetch returns !ok)
    const plainResp = await fetch(jsonPath);
    if (!plainResp.ok) {
      throw new Error(`Failed to load ${jsonPath}: HTTP ${plainResp.status}`);
    }
    const plainBuffer = await plainResp.arrayBuffer();
    if (plainBuffer.byteLength > maxBytes) {
      throw new Error(`Plain payload exceeds 32MiB bound: ${plainBuffer.byteLength} bytes`);
    }
    if (plainBuffer.byteLength !== expectedPlainBytes) {
      throw new Error(`Plain payload byte length mismatch: got ${plainBuffer.byteLength}, expected ${expectedPlainBytes}`);
    }
    const plainSha = await computeSha256Hex(plainBuffer);
    if (plainSha !== expectedPlainSha) {
      throw new Error(`Plain payload SHA-256 mismatch: got ${plainSha}, expected ${expectedPlainSha}`);
    }
    const text = new TextDecoder('utf-8').decode(plainBuffer);
    return JSON.parse(text);
  }

  // Linear O(V + E) Referential Integrity & Overlap Validator (Maps/Sets)
  // Derived UI root is excluded from validation.
  function validateGraphIntegrity(data, scopePrefix, expectedCounts = {}) {
    if (!data || typeof data !== 'object') {
      throw new Error(`${scopePrefix} data must be an object`);
    }
    if (!Array.isArray(data.parents) || data.parents.length === 0) {
      throw new Error(`${scopePrefix} parents must be a non-empty array`);
    }
    if (!Array.isArray(data.leaves) || data.leaves.length === 0) {
      throw new Error(`${scopePrefix} leaves must be a non-empty array`);
    }
    if (!Array.isArray(data.atoms) || data.atoms.length === 0) {
      throw new Error(`${scopePrefix} atoms must be a non-empty array`);
    }

    if (expectedCounts.parents !== undefined && data.parents.length !== expectedCounts.parents) {
      throw new Error(`${scopePrefix} parents length mismatch: got ${data.parents.length}, expected ${expectedCounts.parents}`);
    }
    if (expectedCounts.leaves !== undefined && data.leaves.length !== expectedCounts.leaves) {
      throw new Error(`${scopePrefix} leaves length mismatch: got ${data.leaves.length}, expected ${expectedCounts.leaves}`);
    }
    if (expectedCounts.atoms !== undefined && data.atoms.length !== expectedCounts.atoms) {
      throw new Error(`${scopePrefix} atoms length mismatch: got ${data.atoms.length}, expected ${expectedCounts.atoms}`);
    }

    const parentIdSet = new Set();
    const parentChildSet = new Set();
    let totalParentChildEdges = 0;

    for (let i = 0; i < data.parents.length; i++) {
      const p = data.parents[i];
      if (!p || typeof p.id !== 'string' || !p.id) {
        throw new Error(`${scopePrefix} parent at index ${i} has invalid or missing id`);
      }
      if (parentIdSet.has(p.id)) {
        throw new Error(`${scopePrefix} duplicate parent id: ${p.id}`);
      }
      parentIdSet.add(p.id);

      if (!Array.isArray(p.children)) {
        throw new Error(`${scopePrefix} parent ${p.id} children must be an array`);
      }
      if (!Number.isFinite(p.atom_count) || p.atom_count < 0) {
        throw new Error(`${scopePrefix} parent ${p.id} atom_count must be a non-negative finite number`);
      }

      for (let j = 0; j < p.children.length; j++) {
        const cid = p.children[j];
        if (typeof cid !== 'string' || !cid) {
          throw new Error(`${scopePrefix} parent ${p.id} has invalid child leaf id at index ${j}`);
        }
        parentChildSet.add(p.id + '\0' + cid);
      }
      totalParentChildEdges += p.children.length;
    }

    if (expectedCounts.parentChildEdges !== undefined && totalParentChildEdges !== expectedCounts.parentChildEdges) {
      throw new Error(`${scopePrefix} parent->child edge count mismatch: got ${totalParentChildEdges}, expected ${expectedCounts.parentChildEdges}`);
    }
    if (parentChildSet.size !== totalParentChildEdges) {
      throw new Error(`${scopePrefix} duplicate parent->child edges detected: unique ${parentChildSet.size} vs total ${totalParentChildEdges}`);
    }

    const leafIdSet = new Set();
    const leafAtomSet = new Set();
    let totalLeafParentEdges = 0;
    let totalLeafAtomEdges = 0;
    let overlappingLeavesCount = 0;

    for (let i = 0; i < data.leaves.length; i++) {
      const l = data.leaves[i];
      if (!l || typeof l.id !== 'string' || !l.id) {
        throw new Error(`${scopePrefix} leaf at index ${i} has invalid or missing id`);
      }
      if (leafIdSet.has(l.id)) {
        throw new Error(`${scopePrefix} duplicate leaf id: ${l.id}`);
      }
      leafIdSet.add(l.id);

      if (!Array.isArray(l.parent_ids)) {
        throw new Error(`${scopePrefix} leaf ${l.id} parent_ids must be an array`);
      }
      if (l.parent_ids.length === 0) {
        throw new Error(`${scopePrefix} orphan leaf detected: ${l.id} has 0 parents`);
      }
      if (l.parent_ids.length > 1) {
        overlappingLeavesCount++;
      }
      totalLeafParentEdges += l.parent_ids.length;

      for (let j = 0; j < l.parent_ids.length; j++) {
        const pid = l.parent_ids[j];
        if (!parentIdSet.has(pid)) {
          throw new Error(`${scopePrefix} leaf ${l.id} references non-existent parent: ${pid}`);
        }
        const key = pid + '\0' + l.id;
        if (!parentChildSet.has(key)) {
          throw new Error(`${scopePrefix} forward/reverse parent-child mismatch: leaf ${l.id} lists parent ${pid}, but parent does not list leaf`);
        }
      }

      if (!Array.isArray(l.atom_ids)) {
        throw new Error(`${scopePrefix} leaf ${l.id} atom_ids must be an array`);
      }
      for (let j = 0; j < l.atom_ids.length; j++) {
        const aid = l.atom_ids[j];
        if (typeof aid !== 'string' || !aid) {
          throw new Error(`${scopePrefix} leaf ${l.id} has invalid atom id at index ${j}`);
        }
        leafAtomSet.add(l.id + '\0' + aid);
      }
      totalLeafAtomEdges += l.atom_ids.length;

      if (!Array.isArray(l.doc_ids)) {
        throw new Error(`${scopePrefix} leaf ${l.id} doc_ids must be an array`);
      }
    }

    if (totalLeafParentEdges !== totalParentChildEdges) {
      throw new Error(`${scopePrefix} reverse leaf->parent edge count (${totalLeafParentEdges}) mismatch with parent->child edge count (${totalParentChildEdges})`);
    }
    if (expectedCounts.overlappingLeaves !== undefined && overlappingLeavesCount !== expectedCounts.overlappingLeaves) {
      throw new Error(`${scopePrefix} overlapping leaves count mismatch: got ${overlappingLeavesCount}, expected ${expectedCounts.overlappingLeaves}`);
    }
    if (expectedCounts.leafAtomEdges !== undefined && totalLeafAtomEdges !== expectedCounts.leafAtomEdges) {
      throw new Error(`${scopePrefix} leaf->atom edge count mismatch: got ${totalLeafAtomEdges}, expected ${expectedCounts.leafAtomEdges}`);
    }
    if (leafAtomSet.size !== totalLeafAtomEdges) {
      throw new Error(`${scopePrefix} duplicate leaf->atom edges detected: unique ${leafAtomSet.size} vs total ${totalLeafAtomEdges}`);
    }

    const atomIdSet = new Set();
    let totalAtomLeafEdges = 0;
    let overlappingAtomsCount = 0;

    for (let i = 0; i < data.atoms.length; i++) {
      const a = data.atoms[i];
      if (!a || typeof a.id !== 'string' || !a.id) {
        throw new Error(`${scopePrefix} atom at index ${i} has invalid or missing id`);
      }
      if (atomIdSet.has(a.id)) {
        throw new Error(`${scopePrefix} duplicate atom id: ${a.id}`);
      }
      atomIdSet.add(a.id);

      if (typeof a.doc_id !== 'string') {
        throw new Error(`${scopePrefix} atom ${a.id} doc_id must be a string`);
      }
      if (!Array.isArray(a.leaf_ids)) {
        throw new Error(`${scopePrefix} atom ${a.id} leaf_ids must be an array`);
      }
      if (a.leaf_ids.length === 0) {
        throw new Error(`${scopePrefix} orphan atom detected: ${a.id} has 0 leaves`);
      }
      if (a.leaf_ids.length > 1) {
        overlappingAtomsCount++;
      }
      totalAtomLeafEdges += a.leaf_ids.length;

      for (let j = 0; j < a.leaf_ids.length; j++) {
        const lid = a.leaf_ids[j];
        if (!leafIdSet.has(lid)) {
          throw new Error(`${scopePrefix} atom ${a.id} references non-existent leaf: ${lid}`);
        }
        const key = lid + '\0' + a.id;
        if (!leafAtomSet.has(key)) {
          throw new Error(`${scopePrefix} forward/reverse leaf-atom mismatch: atom ${a.id} lists leaf ${lid}, but leaf does not list atom`);
        }
      }

      if (!Number.isFinite(a.chunk_ix)) {
        throw new Error(`${scopePrefix} atom ${a.id} chunk_ix must be a finite number`);
      }
      if (!Array.isArray(a.span) || a.span.length !== 2) {
        throw new Error(`${scopePrefix} atom ${a.id} span must be a 2-tuple`);
      }
      if (!Array.isArray(a.byte_span) || a.byte_span.length !== 2) {
        throw new Error(`${scopePrefix} atom ${a.id} byte_span must be a 2-tuple`);
      }
      if (!Number.isFinite(a.seq)) {
        throw new Error(`${scopePrefix} atom ${a.id} seq must be a finite number`);
      }
    }

    if (totalAtomLeafEdges !== totalLeafAtomEdges) {
      throw new Error(`${scopePrefix} reverse atom->leaf edge count (${totalAtomLeafEdges}) mismatch with leaf->atom edge count (${totalLeafAtomEdges})`);
    }
    if (expectedCounts.overlappingAtoms !== undefined && overlappingAtomsCount !== expectedCounts.overlappingAtoms) {
      throw new Error(`${scopePrefix} overlapping atoms count mismatch: got ${overlappingAtomsCount}, expected ${expectedCounts.overlappingAtoms}`);
    }

    return {
      parentsCount: parentIdSet.size,
      leavesCount: leafIdSet.size,
      atomsCount: atomIdSet.size,
      parentChildEdges: totalParentChildEdges,
      leafAtomEdges: totalLeafAtomEdges,
      overlappingLeaves: overlappingLeavesCount,
      overlappingAtoms: overlappingAtomsCount
    };
  }

  // 10M Qualification Topology Validator
  function validate10mData(data) {
    if (!data || typeof data !== 'object') throw new Error('Missing or invalid 10M data object');
    if (!data.manifest || typeof data.manifest !== 'object') throw new Error('Missing 10M manifest');
    const m = data.manifest;

    if (m.source_freeze_sha256 !== VERIFIED_SOURCEFREEZE) {
      throw new Error(`10M Source freeze mismatch: ${m.source_freeze_sha256}`);
    }
    if (m.store_pin !== VERIFIED_10M_PIN) {
      throw new Error(`10M Store pin mismatch: ${m.store_pin}`);
    }
    if (m.total_parents !== 3711 || m.total_leaves !== 9177 || m.total_atoms !== 63441) {
      throw new Error(`10M count mismatch: ${m.total_parents}/${m.total_leaves}/${m.total_atoms}`);
    }

    validateGraphIntegrity(data, '10M', {
      parents: 3711,
      leaves: 9177,
      atoms: 63441,
      parentChildEdges: 13547,
      leafAtomEdges: 72981,
      overlappingLeaves: 4370,
      overlappingAtoms: 9540
    });
  }

  // Fresh Local 20k Contract & Dynamic Graph Validator
  function validate20kData(data) {
    if (!data || typeof data !== 'object') throw new Error('Missing or invalid 20k data object');
    if (!data.manifest || typeof data.manifest !== 'object') throw new Error('Missing 20k manifest');
    const m = data.manifest;

    // 1. manifest.scope
    if (typeof m.scope !== 'string' || !m.scope.trim()) {
      throw new Error('Unsupported 20k recording: manifest.scope must be a non-empty string');
    }

    // 2. manifest.source_freeze_sha256
    if (m.source_freeze_sha256 !== VERIFIED_SOURCEFREEZE) {
      throw new Error(`20k Source freeze mismatch: ${m.source_freeze_sha256}`);
    }

    // 3. run_uuid (UUID)
    const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!m.run_uuid || typeof m.run_uuid !== 'string' || !UUID_REGEX.test(m.run_uuid)) {
      throw new Error('Unsupported 20k recording: manifest.run_uuid missing or invalid UUID (fresh contract required)');
    }

    // 4. result_sha256 (hex64)
    const HEX64_REGEX = /^[0-9a-f]{64}$/i;
    if (!m.result_sha256 || typeof m.result_sha256 !== 'string' || !HEX64_REGEX.test(m.result_sha256)) {
      throw new Error('Unsupported 20k recording: manifest.result_sha256 missing or invalid hex64 (fresh contract required)');
    }

    // 5. store_head_pin: [uuid, 0, 645, uuid+':0:645'] (numbers may vary legit fresh; no hardcoded pin triple)
    if (!Array.isArray(m.store_head_pin) || m.store_head_pin.length !== 4) {
      throw new Error('Unsupported 20k recording: manifest.store_head_pin must be a 4-element tuple');
    }
    const [pinUuid, pinOffset, pinGen, pinTriple] = m.store_head_pin;
    if (typeof pinUuid !== 'string' || !UUID_REGEX.test(pinUuid)) {
      throw new Error(`20k store_head_pin[0] must be a valid UUID: ${pinUuid}`);
    }
    if (!Number.isInteger(pinOffset) || pinOffset < 0) {
      throw new Error(`20k store_head_pin[1] must be a non-negative integer: ${pinOffset}`);
    }
    if (!Number.isInteger(pinGen) || pinGen < 0) {
      throw new Error(`20k store_head_pin[2] must be a non-negative integer: ${pinGen}`);
    }
    const expectedPinTriple = `${pinUuid}:${pinOffset}:${pinGen}`;
    if (pinTriple !== expectedPinTriple) {
      throw new Error(`20k store_head_pin tuple internal inconsistency: pin[3] "${pinTriple}" does not match "${expectedPinTriple}"`);
    }

    // 6. actual_tokens: 20030
    if (m.actual_tokens !== 20030) {
      throw new Error(`20k manifest.actual_tokens mismatch: got ${m.actual_tokens}, expected 20030`);
    }

    // 7. complete_documents: 88
    if (m.complete_documents !== 88) {
      throw new Error(`20k manifest.complete_documents mismatch: got ${m.complete_documents}, expected 88`);
    }

    // 8. status: PASS
    if (m.status !== 'PASS') {
      throw new Error(`20k manifest.status mismatch: got ${m.status}, expected PASS`);
    }

    // 9. evaluation_queries: full original 240 query dicts
    if (!Array.isArray(data.evaluation_queries) || data.evaluation_queries.length !== 240) {
      throw new Error(`Unsupported 20k recording: evaluation_queries must contain full original 240 query dicts (got ${data.evaluation_queries ? data.evaluation_queries.length : 'none'})`);
    }

    // 10. phase_telemetry
    if (!data.phase_telemetry || typeof data.phase_telemetry !== 'object') {
      throw new Error('Unsupported 20k recording: phase_telemetry missing');
    }

    // 11. Dynamic graph referential integrity & counts
    const expectedParents = m.parents_count !== undefined ? m.parents_count : m.total_parents;
    const expectedLeaves = m.leaves_count !== undefined ? m.leaves_count : m.total_leaves;
    const expectedAtoms = m.atoms_count !== undefined ? m.atoms_count : m.total_atoms;
    const expectedParentChildEdges = m.parent_child_edges;
    const expectedLeafAtomEdges = m.leaf_atom_edges;
    const expectedOverlappingLeaves = m.multi_parent_leaves !== undefined ? m.multi_parent_leaves : m.overlapping_leaves;
    const expectedOverlappingAtoms = m.multi_leaf_atoms !== undefined ? m.multi_leaf_atoms : m.overlapping_atoms;

    validateGraphIntegrity(data, '20k', {
      parents: expectedParents,
      leaves: expectedLeaves,
      atoms: expectedAtoms,
      parentChildEdges: expectedParentChildEdges,
      leafAtomEdges: expectedLeafAtomEdges,
      overlappingLeaves: expectedOverlappingLeaves,
      overlappingAtoms: expectedOverlappingAtoms
    });
  }

  function showStatus(msg, isError) {
    if (!statusBanner) return;
    statusBanner.style.display = 'block';
    statusBanner.style.backgroundColor = isError ? 'rgba(244, 63, 94, 0.15)' : 'rgba(56, 189, 248, 0.12)';
    statusBanner.style.borderColor = isError ? 'var(--accent-rose, #f43f5e)' : 'var(--accent-cyan, #38bdf8)';
    statusBanner.style.color = isError ? '#fecdd3' : '#e0f2fe';
    statusBanner.textContent = msg;
  }

  function hideStatus() {
    if (statusBanner) statusBanner.style.display = 'none';
  }

  function updateStatusBanner() {
    const err = datasetErrors[currentDataset];
    if (err) {
      showStatus(`${currentDataset.toUpperCase()} Dataset Unavailable: ${err}`, true);
    } else if (datasetErrors['10m'] && currentDataset === '20k') {
      showStatus(`Viewing verified 20k dataset (10M dataset is unavailable: ${datasetErrors['10m']}).`, false);
    } else {
      hideStatus();
    }
  }

  // Load All Artifacts (Fail-Closed)
  async function loadData() {
    showStatus('Loading verified DAG topology datasets (10M / 20k)...', false);

    datasetErrors['10m'] = null;
    datasetErrors['20k'] = null;

    // 1. Qualification Telemetry
    try {
      const resResp = await fetch('qualification_10m.json');
      if (resResp.ok) {
        qualificationData = await resResp.json();
      } else {
        console.warn(`qualification_10m.json fetch failed: HTTP ${resResp.status}`);
      }
    } catch (err) {
      console.warn('qualification_10m.json load error:', err);
    }

    // 2. Probes Summary
    try {
      const probesResp = await fetch('probes_summary.json');
      if (probesResp.ok) {
        probeList = await probesResp.json();
      }
    } catch (err) {
      console.warn('probes_summary.json load error:', err);
    }

    // 3. Local 20k Dataset (Fail-Closed: assign only after validated)
    try {
      const localResp = await fetch('local_20k_data.json');
      if (!localResp.ok) {
        throw new Error(`Failed to load local_20k_data.json: HTTP ${localResp.status}`);
      }
      const raw20k = await localResp.json();
      validate20kData(raw20k);
      local20kData = raw20k; // Assigned only after validated
      datasetErrors['20k'] = null;
    } catch (err) {
      local20kData = null; // Clear invalid data on error (fail-closed)
      datasetErrors['20k'] = err.message;
      console.warn('20k validation error (fail-closed):', err.message);
    }

    // 4. 10M Dataset (Fail-Closed: assign only after validated)
    try {
      const g10m = await loadGzipOrJson('graph_10m.json.gz', 'graph_10m.json');
      validate10mData(g10m);
      graph10mData = g10m; // Assigned only after validated
      datasetErrors['10m'] = null;
    } catch (err) {
      graph10mData = null; // Clear invalid data on error (fail-closed)
      datasetErrors['10m'] = err.message;
      console.warn('10M load/validation error (fail-closed):', err.message);
    }

    updateStatusBanner();
    renderPhaseTimeline();
    populateQuerySelector();
    populateClusterSelector();
    layoutAndDrawTopology();
    renderStepDetail();
    // Re-run the default tour step now that datasets are validated and drawable.
    if (typeof applyTourStep === 'function' && tourMode && tourStep === 1) applyTourStep(1);
  }

  // Render Phase Timeline Bar (latest measured run seam12a — see SEAM12A_WALLS_S)
  function renderPhaseTimeline() {
    if (!phaseBar) return;
    const walls = SEAM12A_WALLS_S;
    const totalWall = SEAM12A_TOTAL_WALL_S;

    phaseBar.innerHTML = '';
    if (phaseLegend) phaseLegend.innerHTML = '';

    for (const [key, duration] of Object.entries(walls)) {
      const pct = (duration / totalWall) * 100;
      const color = phaseColors[key] || '#94a3b8';
      const name = phaseNames[key] || key;

      const seg = document.createElement('div');
      seg.className = 'phase-seg';
      seg.style.width = `${pct}%`;
      seg.style.backgroundColor = color;
      seg.title = `${name}: ${Math.round(duration)} s (${pct.toFixed(1)}%)`;
      phaseBar.appendChild(seg);

      if (phaseLegend) {
        const leg = document.createElement('div');
        leg.className = 'legend-item';
        leg.innerHTML = `<span class="legend-dot" style="background-color: ${color}"></span><span>${name} (<strong>${Math.round(duration)}s</strong>)</span>`;
        phaseLegend.appendChild(leg);
      }
    }
  }

  // Populate Cluster Selector for 10M & 20k
  function populateClusterSelector() {
    if (!clusterSelect) return;
    const activeData = (currentDataset === '10m') ? graph10mData : local20kData;
    if (!activeData || !activeData.parents) {
      clusterSelect.innerHTML = '<option value="overview">Overview of all real groups (structural preview)</option>';
      return;
    }

    const totalCount = activeData.parents.length.toLocaleString();
    const renderedCount = (currentDataset === '10m') ? Math.min(activeData.parents.length, 64) : activeData.parents.length;
    clusterSelect.innerHTML = `<option value="overview">Overview: ${renderedCount} of ${totalCount} real groups (structural preview)</option>`;

    // List top 40 parents by atom count or order
    const sortedParents = [...activeData.parents].sort((a, b) => (b.atom_count || 0) - (a.atom_count || 0));
    const sample = sortedParents.slice(0, 40);

    sample.forEach((p, idx) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      const kidCount = p.children ? p.children.length : (p.leaf_ids ? p.leaf_ids.length : 0);
      opt.textContent = `Focus: ${p.id} (${p.atom_count || 0} atoms, ${kidCount} leaves)`;
      clusterSelect.appendChild(opt);
    });

    clusterSelect.addEventListener('change', (e) => {
      currentClusterFocus = e.target.value;
      if (currentClusterFocus !== 'overview') {
        const targetParent = activeData.parents.find(p => p.id === currentClusterFocus);
        if (targetParent) {
          inspectNode({
            type: 'parent',
            id: targetParent.id,
            raw: targetParent
          });
        }
      } else {
        selectedNode = null;
        inspectNode(null);
      }
      layoutAndDrawTopology();
    });
  }

  // Populate Query Selector
  function populateQuerySelector() {
    if (!querySelect) return;
    querySelect.innerHTML = '';

    const probes = probeList.length ? probeList : (local20kData ? local20kData.atoms.slice(0, 30) : []);
    const count = probes.length || 30;

    for (let i = 0; i < Math.min(count, 40); i++) {
      const p = probes[i] || {};
      const family = p.family || (i < 13 ? 'chunk' : (i < 26 ? 'noisy' : 'cross'));
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = `Probe #${i} [${family}] — Target Doc ${p.sources ? p.sources[0] : (p.doc_id || i)}`;
      querySelect.appendChild(opt);
    }

    querySelect.addEventListener('change', (e) => {
      currentProbeIndex = parseInt(e.target.value, 10);
      renderStepDetail();
    });
  }

  // Stepper Interaction
  function initStepper() {
    stepCards.forEach(card => {
      card.addEventListener('click', () => {
        const step = parseInt(card.getAttribute('data-step'), 10);
        goToStep(step);
      });
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const step = parseInt(card.getAttribute('data-step'), 10);
          goToStep(step);
        }
      });
    });

    modeRadios.forEach(radio => {
      radio.addEventListener('change', (e) => {
        selectedLso = (e.target.value === 'true');
        renderStepDetail();
      });
    });

    if (btnStepPrev) {
      btnStepPrev.addEventListener('click', () => goToStep(Math.max(1, currentStep - 1)));
    }
    if (btnStepNext) {
      btnStepNext.addEventListener('click', () => goToStep(Math.min(5, currentStep + 1)));
    }
    if (btnPlayPause) {
      btnPlayPause.addEventListener('click', togglePlay);
    }
    if (speedSelect) {
      speedSelect.addEventListener('change', (e) => {
        playSpeed = parseFloat(e.target.value) || 1;
        if (isPlaying) {
          stopPlay();
          startPlay();
        }
      });
    }
  }

  function goToStep(step) {
    currentStep = step;
    stepCards.forEach(c => {
      const s = parseInt(c.getAttribute('data-step'), 10);
      if (s === currentStep) {
        c.classList.add('active');
        c.setAttribute('aria-selected', 'true');
      } else {
        c.classList.remove('active');
        c.setAttribute('aria-selected', 'false');
      }
    });
    renderStepDetail();
  }

  function togglePlay() {
    if (isPlaying) stopPlay();
    else startPlay();
  }

  function startPlay() {
    isPlaying = true;
    if (btnPlayPause) btnPlayPause.innerHTML = '&#10074;&#10074; Pause';
    const interval = Math.max(400, 1600 / playSpeed);
    playTimer = setInterval(() => {
      if (currentStep < 5) goToStep(currentStep + 1);
      else goToStep(1);
    }, interval);
  }

  function stopPlay() {
    isPlaying = false;
    if (btnPlayPause) btnPlayPause.innerHTML = '&#9654; Play';
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
  }

  // Render Step Details
  function renderStepDetail() {
    if (!stepDetailPanel) return;

    const probe = probeList[currentProbeIndex] || {};
    const probeId = (typeof probe.id === 'number') ? probe.id : currentProbeIndex;
    const modeLabel = selectedLso ? 'LSO On (Leave Source Out)' : 'LSO Off (All Sources)';

    // Lookup recorded historical query row from qualificationData.queries (240 rows)
    const queryRow = (qualificationData && Array.isArray(qualificationData.queries))
      ? qualificationData.queries.find(q => q.probe === probeId && q.leave_source_out === selectedLso)
      : null;

    if (!queryRow) {
      stepDetailPanel.innerHTML = `
        <div style="padding: 1.5rem; border: 1px solid var(--accent-rose, #f43f5e); background: rgba(244, 63, 94, 0.08); border-radius: 8px;">
          <h3 style="color: var(--accent-rose, #f43f5e); margin-top: 0;">Recorded Query Row Unavailable</h3>
          <p>No recorded historical telemetry row found for <strong>Probe #${probeId}</strong> with <strong>${modeLabel}</strong>.</p>
          <p class="footnote" style="margin-top: 1rem; color: #94a3b8;">
            Telemetry is retrieved directly from <code>qualificationData.queries</code> (240 recorded benchmark rows).
            Global averages or default zeros are strictly not substituted when a row is unavailable.
          </p>
        </div>
      `;
      return;
    }

    // Strict required finite field guard and explicit record unavailable/error if missing
    const missingFields = [];
    if (!queryRow.work || typeof queryRow.work !== 'object') {
      missingFields.push('work (object)');
    } else {
      if (!Number.isFinite(queryRow.work.parents_scored)) missingFields.push('work.parents_scored');
      if (!Number.isFinite(queryRow.work.children_scored)) missingFields.push('work.children_scored');
      if (!Number.isFinite(queryRow.work.atoms_scored)) missingFields.push('work.atoms_scored');
      if (!Number.isFinite(queryRow.work.member_visits)) missingFields.push('work.member_visits');
    }
    if (!Number.isFinite(queryRow.guided_recall10)) missingFields.push('guided_recall10');
    if (!Number.isFinite(queryRow.flat_recall10)) missingFields.push('flat_recall10');
    if (!Number.isFinite(queryRow.guided_wall_s)) missingFields.push('guided_wall_s');
    if (!Number.isFinite(queryRow.guided_scoring_rows)) missingFields.push('guided_scoring_rows');
    if (!Number.isFinite(queryRow.flat_scoring_rows)) missingFields.push('flat_scoring_rows');
    if (typeof queryRow.matched_work !== 'boolean') missingFields.push('matched_work');
    if (typeof queryRow.family !== 'string' || !queryRow.family.trim()) missingFields.push('family');
    if (!Number.isFinite(queryRow.eligible_atoms)) missingFields.push('eligible_atoms');
    if (!Number.isFinite(queryRow.guided_distinct_returned)) missingFields.push('guided_distinct_returned');

    if (missingFields.length > 0) {
      stepDetailPanel.innerHTML = `
        <div style="padding: 1.5rem; border: 1px solid var(--accent-rose, #f43f5e); background: rgba(244, 63, 94, 0.08); border-radius: 8px;">
          <h3 style="color: var(--accent-rose, #f43f5e); margin-top: 0;">Recorded Query Row Incomplete</h3>
          <p>Recorded historical telemetry row for <strong>Probe #${probeId}</strong> with <strong>${modeLabel}</strong> is missing required finite fields:</p>
          <ul style="color: var(--accent-rose, #f43f5e); margin: 0.5rem 0 1rem 1.5rem;">
            ${missingFields.map(f => `<li><code>${f}</code></li>`).join('')}
          </ul>
          <p class="footnote" style="margin-top: 1rem; color: #94a3b8;">
            Telemetry is retrieved strictly from authentic recorded benchmark rows.
            Global means, default zeros, or fallback values are never substituted.
          </p>
        </div>
      `;
      return;
    }

    const work = queryRow.work;
    const parentsScored = work.parents_scored;
    const childrenScored = work.children_scored;
    const atomsScored = work.atoms_scored;
    const memberVisits = work.member_visits;
    const guidedRows = queryRow.guided_scoring_rows;
    const flatRows = queryRow.flat_scoring_rows;
    const guidedRecallPct = (queryRow.guided_recall10 * 100).toFixed(1);
    const flatRecallPct = (queryRow.flat_recall10 * 100).toFixed(1);
    const wallMs = (queryRow.guided_wall_s * 1000).toFixed(2);
    const family = queryRow.family;
    const eligibleAtoms = queryRow.eligible_atoms;
    const guidedDistinctReturned = queryRow.guided_distinct_returned;

    let html = '';
    switch (currentStep) {
      case 1:
        html = `
          <h3>Stage 1: Parent Scoring (Phase 1 Routing)</h3>
          <p>The query vector is scored against all <strong>${parentsScored.toLocaleString()} seg_parent centroids</strong> in storage via dense dot product. Parent scoring is fixed across all queries.</p>
          <div class="stats-grid" style="margin: 1rem 0;">
            <div class="stat-card">
              <div class="stat-label">Parents Scored (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-cyan);">${parentsScored.toLocaleString()}</div>
              <div class="stat-sub">Full scan across all parent holons</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Evaluation Identity</div>
              <div class="stat-value" style="font-size: 1.1rem; color: #f8fafc;">Probe #${probeId} [${family}]</div>
              <div class="stat-sub">${modeLabel}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Parent Budget</div>
              <div class="stat-value" style="color: var(--accent-emerald);">Full Scan</div>
              <div class="stat-sub">Scans all ${parentsScored.toLocaleString()} seg_parents in 10M store</div>
            </div>
          </div>
          <p class="footnote">Verification Note: Query router scans all 3,711 seg_parents in the storage pin (hierarchy supports recursive child edges). Recorded query telemetry confirms ${parentsScored.toLocaleString()} parents evaluated.</p>
        `;
        break;
      case 2:
        html = `
          <h3>Stage 2: Top Parent Selection (Phase 2 Branch Filter)</h3>
          <p>The router ranks all scored parents and selects the top-scoring branches (budget: top_parents = 4) for recursive child descent.</p>
          <div class="stats-grid" style="margin: 1rem 0;">
            <div class="stat-card">
              <div class="stat-label">Top Parents Budget</div>
              <div class="stat-value" style="color: var(--accent-cyan);">4</div>
              <div class="stat-sub">top_parents parameter</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Traversed Branch IDs</div>
              <div class="stat-value" style="font-size: 1rem; color: var(--accent-amber, #fbbf24);">Not Persisted</div>
              <div class="stat-sub">Query path IDs were not recorded in telemetry</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Expansion Mechanism</div>
              <div class="stat-value" style="font-size: 1rem; color: #f8fafc;">DFS Stack</div>
              <div class="stat-sub">Top 4 parents push child edges onto stack</div>
            </div>
          </div>
          <p class="footnote">Notice: Specific query traversal branch IDs were not recorded in the benchmark run. Stages explain the routing algorithm only; authentic 10M graph membership navigation remains available separately in the DAG Topology tab.</p>
        `;
        break;
      case 3:
        html = `
          <h3>Stage 3: Child Descent &amp; Leaf Scoring</h3>
          <p>Traverses candidate child edges from selected parents, evaluating candidate leaves. Because leaves can belong to multiple parents (4,370 overlapping leaves in 10M), the router deduplicates visited leaves.</p>
          <div class="stats-grid" style="margin: 1rem 0;">
            <div class="stat-card">
              <div class="stat-label">Children Scored (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-cyan);">${childrenScored}</div>
              <div class="stat-sub">Probe #${probeId} actual recorded work</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Top Children Budget</div>
              <div class="stat-value" style="color: var(--accent-emerald);">8</div>
              <div class="stat-sub">top_children parameter limit</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Recorded Range Context</div>
              <div class="stat-value" style="font-size: 1.1rem; color: #f8fafc;">6 &ndash; 54 (mean 25.5)</div>
              <div class="stat-sub">Recorded range across staged 240 rows</div>
            </div>
          </div>
          <p class="footnote">Overlapping DAG traversal: 4,370 multi-parent leaves ensure multi-faceted document clusters are reachable via alternate descent paths. Candidate leaves are dynamically deduplicated.</p>
        `;
        break;
      case 4:
        html = `
          <h3>Stage 4: Leaf Member Ranking (Atom Scoring)</h3>
          <p>Selected top leaves yield candidate atom vectors. The router evaluates candidate atoms against the query, deduplicating atoms across leaves (9,540 multi-leaf atoms in 10M).</p>
          <div class="stats-grid" style="margin: 1rem 0;">
            <div class="stat-card">
              <div class="stat-label">Atoms Scored (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-cyan);">${atomsScored}</div>
              <div class="stat-sub">Probe #${probeId} recorded atom evaluations</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Member Visits (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-emerald);">${memberVisits}</div>
              <div class="stat-sub">Probe #${probeId} leaf member visits</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Total Scoring Rows (Recorded)</div>
              <div class="stat-value" style="color: #f8fafc;">${guidedRows.toLocaleString()}</div>
              <div class="stat-sub">${parentsScored.toLocaleString()} parents + ${childrenScored} leaves + ${atomsScored} atoms</div>
            </div>
          </div>
          <p class="footnote">Compute concentration: This recorded query evaluated only ${atomsScored} atoms out of ${eligibleAtoms.toLocaleString()} eligible atoms (${((atomsScored / eligibleAtoms) * 100).toFixed(2)}%). (240-query benchmark context: atoms 8&ndash;197, mean 114.5; visits 9&ndash;197, mean 129.3).</p>
        `;
        break;
      case 5:
        const recallAdvantage = (queryRow.flat_recall10 > 0)
          ? `${(queryRow.guided_recall10 / queryRow.flat_recall10).toFixed(1)}&times;`
          : (queryRow.guided_recall10 > 0 ? '&gt; Flat (Flat=0%)' : 'N/A');
        // Recorded means of the staged 240 rows (earlier freeze). Latest measured
        // aggregates (seam12a): 73.7% / 48.8% guided, shown on the overview tab.
        const aggMeanGuided = selectedLso ? '47.6%' : '73.0%';
        const aggMeanFlat = selectedLso ? '4.8%' : '5.6%';

        html = `
          <h3>Stage 5: Retrieval Accuracy (Matched Work Benchmark)</h3>
          <p>Top-10 ranked results evaluated against the oracle top-10 ground truth under matched compute budgets.</p>
          <div class="stats-grid" style="margin: 1rem 0;">
            <div class="stat-card">
              <div class="stat-label">Guided Recall@10 (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-emerald);">${guidedRecallPct}%</div>
              <div class="stat-sub">Scored ${guidedRows.toLocaleString()} rows (${guidedDistinctReturned}/10 returned)</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Matched-Flat Recall@10 (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-rose);">${flatRecallPct}%</div>
              <div class="stat-sub">Constrained to identical ${flatRows.toLocaleString()} rows</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Recall Advantage (Recorded)</div>
              <div class="stat-value" style="color: var(--accent-cyan);">${recallAdvantage}</div>
              <div class="stat-sub">Wall: ${wallMs} ms &bull; Matched: ${queryRow.matched_work ? 'Yes' : 'No'}</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">Recorded 240-Row Mean</div>
              <div class="stat-value" style="font-size: 1.1rem; color: #f8fafc;">${aggMeanGuided} vs ${aggMeanFlat}</div>
              <div class="stat-sub">Earlier-freeze recording (${modeLabel}); latest: 73.7% / 48.8%</div>
            </div>
          </div>
          <p class="footnote">Benchmark Note: Evaluated against brute-force oracle over ${eligibleAtoms.toLocaleString()} atoms under matched row compute budget (${guidedRows.toLocaleString()} rows). Probe #${probeId} [${family}] (${modeLabel}) recorded ${(queryRow.guided_wall_s).toFixed(4)}s wall time.</p>
        `;
        break;
    }

    stepDetailPanel.innerHTML = html;
  }

  // Topology Layout & Progressive Canvas Drawing
  function layoutAndDrawTopology() {
    if (!ctx || !canvas) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Apply Zoom & Pan Transform
    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoomLevel, zoomLevel);

    const tier = treeLevelSelect ? treeLevelSelect.value : 'all';
    nodesToRender = [];
    edgesToRender = [];

    const activeData = (currentDataset === '10m') ? graph10mData : local20kData;

    if (!activeData || !activeData.parents) {
      ctx.restore();
      const err = datasetErrors[currentDataset];
      if (err) {
        ctx.fillStyle = '#f43f5e';
        ctx.font = '14px ' + getComputedStyle(document.body).fontFamily;
        ctx.textAlign = 'center';
        ctx.fillText(`${currentDataset.toUpperCase()} Dataset Unavailable: ${err}`, w / 2, h / 2);
      } else {
        ctx.fillStyle = '#94a3b8';
        ctx.font = '14px ' + getComputedStyle(document.body).fontFamily;
        ctx.textAlign = 'center';
        ctx.fillText(`Loading verified ${currentDataset.toUpperCase()} dataset...`, w / 2, h / 2);
      }
      return;
    }

    // Root Node (Virtual UI Entry Point)
    const rootX = w / 2;
    const rootY = 50;
    const rootNode = {
      type: 'root',
      id: 'VIRTUAL_UI_ROOT',
      x: rootX,
      y: rootY,
      radius: 10,
      color: '#38bdf8',
      label: currentDataset === '20k'
        ? `Unified Entry (Virtual Root — ${activeData.parents.length} seg_parents)`
        : `Unified Entry (Virtual Root — ${activeData.parents.length.toLocaleString()} seg_parents)`
    };
    nodesToRender.push(rootNode);

    const parents = activeData.parents;
    const leaves = activeData.leaves;
    const atoms = activeData.atoms;

    if (currentClusterFocus !== 'overview') {
      // Focused Single Cluster Layout
      layoutFocusedCluster(rootNode, activeData, currentClusterFocus, tier);
    } else if (currentDataset === '20k') {
      // 20k Full Layout (All 51 parents, 81 leaves, 144 atoms)
      layout20kFull(rootNode, parents, leaves, atoms, tier);
    } else {
      // 10M Overview Ring Layout (Authentic 3,711 parents orbital macro view)
      layout10mOverview(rootNode, parents, leaves, atoms, tier);
    }

    // Draw Edges
    edgesToRender.forEach(edge => {
      ctx.strokeStyle = edge.color;
      ctx.lineWidth = edge.width || 1;
      if (edge.dashed) ctx.setLineDash([3, 3]);
      else ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(edge.x1, edge.y1);
      ctx.lineTo(edge.x2, edge.y2);
      ctx.stroke();
    });
    ctx.setLineDash([]);

    // Draw Nodes
    nodesToRender.forEach(node => {
      ctx.fillStyle = node.color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();

      if (node === selectedNode || (selectedNode && selectedNode.id === node.id)) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 3, 0, Math.PI * 2);
        ctx.stroke();
      }
    });

    // Label Root
    ctx.fillStyle = '#f8fafc';
    ctx.font = '12px ' + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = 'center';
    ctx.fillText(rootNode.label, rootX, rootY - 16);

    ctx.restore();

    // Canvas Status Caption
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '12px ' + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = 'center';
    const statusText = (currentDataset === '20k')
      ? `Small graph: ${parents.length} groups, ${leaves.length} bundles, ${atoms.length} passages — click any dot to inspect`
      : (currentClusterFocus === 'overview')
        ? '10M graph (earlier freeze, counts match): 3,711 groups, 9,177 bundles, 63,441 atoms — click any dot'
        : `10M focus group: ${currentClusterFocus} — child bundles and member passages`;
    ctx.fillText(statusText, w / 2, h - 14);
  }

  // 20k Full Layout (All 51 parents, 81 leaves, 144 atoms)
  function layout20kFull(rootNode, parents, leaves, atoms, tier) {
    const rootX = rootNode.x;
    const rootY = rootNode.y;
    const pCount = parents.length;
    const radX = 390;
    const radY = 90;
    const parentNodes = new Map();

    // 1. Parents layer (ellipse)
    parents.forEach((p, idx) => {
      const angle = (idx / pCount) * Math.PI * 2;
      const px = rootX + Math.cos(angle) * radX;
      const py = 160 + Math.sin(angle) * radY;
      const pnode = {
        type: 'parent',
        id: p.id,
        raw: p,
        x: px,
        y: py,
        radius: 5,
        color: '#818cf8',
        label: p.id
      };
      parentNodes.set(p.id, pnode);
      nodesToRender.push(pnode);

      if (tier === 'all' || tier === 'parents') {
        edgesToRender.push({
          x1: rootX, y1: rootY,
          x2: px, y2: py,
          color: 'rgba(56, 189, 248, 0.15)'
        });
      }
    });

    if (tier === 'all' || tier === 'leaves') {
      const leafNodes = new Map();

      // 2. Leaves layer (placed beneath parents preserving all authentic connections)
      leaves.forEach((l, lIdx) => {
        const pids = l.parent_ids || (l.parent_id ? [l.parent_id] : []);
        const primaryParentNode = pids.length ? parentNodes.get(pids[0]) : null;
        if (!primaryParentNode) return; // Strict validation: no fallback

        const offsetAngle = ((lIdx % 5) - 2) * 0.35;
        const lx = primaryParentNode.x + Math.sin(offsetAngle) * 45;
        const ly = primaryParentNode.y + 70 + Math.cos(offsetAngle) * 20;

        const lnode = {
          type: 'leaf',
          id: l.id,
          raw: l,
          parentIds: pids,
          x: lx,
          y: ly,
          radius: 4,
          color: pids.length > 1 ? '#ec4899' : '#34d399', // Highlight multi-parent leaves
          label: l.id
        };
        leafNodes.set(l.id, lnode);
        nodesToRender.push(lnode);

        // Draw edges to ALL parents (preserving multi-parent DAG overlap)
        pids.forEach((pid, pidx) => {
          const pn = parentNodes.get(pid);
          if (pn) {
            edgesToRender.push({
              x1: pn.x, y1: pn.y,
              x2: lx, y2: ly,
              color: pidx > 0 ? 'rgba(236, 72, 153, 0.45)' : 'rgba(129, 140, 248, 0.22)',
              dashed: pidx > 0,
              width: pidx > 0 ? 1.5 : 1
            });
          }
        });
      });

      // 3. Atoms layer (sample 100 atoms)
      if (tier === 'all') {
        atoms.slice(0, 100).forEach((a, aIdx) => {
          const lids = a.leaf_ids || [];
          const primaryLeafNode = lids.length ? leafNodes.get(lids[0]) : null;
          if (!primaryLeafNode) return;

          const ax = primaryLeafNode.x + ((aIdx % 3) - 1) * 16;
          const ay = primaryLeafNode.y + 35 + ((aIdx % 2) * 12);

          const anode = {
            type: 'atom',
            id: a.id,
            raw: a,
            leafIds: lids,
            x: ax,
            y: ay,
            radius: 3,
            color: '#fbbf24',
            label: a.id
          };
          nodesToRender.push(anode);

          lids.forEach((lid, lidx) => {
            const ln = leafNodes.get(lid);
            if (ln) {
              edgesToRender.push({
                x1: ln.x, y1: ln.y,
                x2: ax, y2: ay,
                color: lidx > 0 ? 'rgba(236, 72, 153, 0.35)' : 'rgba(52, 211, 153, 0.18)',
                dashed: lidx > 0
              });
            }
          });
        });
      }
    }
  }

  // 10M Overview Ring Layout
  function layout10mOverview(rootNode, parents, leaves, atoms, tier) {
    const rootX = rootNode.x;
    const rootY = rootNode.y;
    const parentCount = Math.min(parents.length, 64); // Show 64 representative parent clusters
    const parentNodes = new Map();

    for (let i = 0; i < parentCount; i++) {
      const p = parents[i];
      const angle = (i / parentCount) * Math.PI * 2;
      const px = rootX + Math.cos(angle) * 380;
      const py = 260 + Math.sin(angle) * 150;

      const pnode = {
        type: 'parent',
        id: p.id,
        raw: p,
        x: px,
        y: py,
        radius: 5,
        color: '#818cf8',
        label: p.id
      };
      parentNodes.set(p.id, pnode);
      nodesToRender.push(pnode);

      edgesToRender.push({
        x1: rootX, y1: rootY,
        x2: px, y2: py,
        color: 'rgba(56, 189, 248, 0.12)'
      });
    }
  }

  // Focused Single Cluster Layout (Expand child leaves & member atoms)
  function layoutFocusedCluster(rootNode, activeData, parentId, tier) {
    const rootX = rootNode.x;
    const rootY = rootNode.y;

    const parent = activeData.parents.find(p => p.id === parentId);
    if (!parent) return;

    // Parent Node at Center Top
    const px = rootX;
    const py = 140;
    const pnode = {
      type: 'parent',
      id: parent.id,
      raw: parent,
      x: px,
      y: py,
      radius: 8,
      color: '#818cf8',
      label: parent.id
    };
    nodesToRender.push(pnode);
    edgesToRender.push({
      x1: rootX, y1: rootY,
      x2: px, y2: py,
      color: 'rgba(56, 189, 248, 0.3)'
    });

    const childIds = parent.children || parent.leaf_ids || [];
    const childLeaves = activeData.leaves.filter(l => childIds.includes(l.id));

    const leafNodes = new Map();
    const lCount = childLeaves.length || 1;
    const spreadX = Math.min(800, lCount * 80);
    const startX = rootX - spreadX / 2;

    childLeaves.forEach((l, lIdx) => {
      const pids = l.parent_ids || (l.parent_id ? [l.parent_id] : []);
      const lx = lCount > 1 ? startX + (lIdx / (lCount - 1)) * spreadX : rootX;
      const ly = 240 + (lIdx % 2) * 20;

      const lnode = {
        type: 'leaf',
        id: l.id,
        raw: l,
        parentIds: pids,
        x: lx,
        y: ly,
        radius: 6,
        color: pids.length > 1 ? '#ec4899' : '#34d399',
        label: l.id
      };
      leafNodes.set(l.id, lnode);
      nodesToRender.push(lnode);

      edgesToRender.push({
        x1: px, y1: py,
        x2: lx, y2: ly,
        color: pids.length > 1 ? 'rgba(236, 72, 153, 0.5)' : 'rgba(129, 140, 248, 0.35)',
        width: pids.length > 1 ? 1.5 : 1
      });

      // Expand member atoms
      if (tier === 'all') {
        const atomIds = l.atom_ids || l.members || [];
        const memberAtoms = activeData.atoms.filter(a => atomIds.includes(a.id)).slice(0, 12);
        const aCount = memberAtoms.length;
        const aSpread = Math.min(60, aCount * 14);
        const aStartX = lx - aSpread / 2;

        memberAtoms.forEach((a, aIdx) => {
          const ax = aCount > 1 ? aStartX + (aIdx / (aCount - 1)) * aSpread : lx;
          const ay = ly + 70 + (aIdx % 3) * 15;

          const anode = {
            type: 'atom',
            id: a.id,
            raw: a,
            leafIds: a.leaf_ids || [],
            x: ax,
            y: ay,
            radius: 4,
            color: '#fbbf24',
            label: a.id
          };
          nodesToRender.push(anode);

          edgesToRender.push({
            x1: lx, y1: ly,
            x2: ax, y2: ay,
            color: 'rgba(52, 211, 153, 0.25)'
          });
        });
      }
    });
  }

  // Node Inspector
  function inspectNode(node) {
    selectedNode = node;
    layoutAndDrawTopology();

    if (!nodeInspectorContent) return;

    if (!node) {
      nodeInspectorContent.innerHTML = '<p class="text-muted">Click a topic group, document bundle, or passage on the canvas. You will get a plain-language explanation plus its counts, children, and sample text when the data has it.</p>';
      return;
    }

    let html = '';
    if (node.type === 'root') {
      html = `
        <div class="inspector-badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 700;">MAP ENTRY POINT</div>
        <p class="what-is"><strong>What this is:</strong> the entry point of the map — every topic group hangs below it.</p>
        <p><strong>Corpus size:</strong> ${currentDataset === '20k' ? '20,030 tokens (88 complete documents)' : '10,003,381 tokens (13,081 complete documents)'}</p>
        <p><strong>Graph contents:</strong> ${currentDataset === '20k' ? `${(local20kData && local20kData.parents ? local20kData.parents.length : 'N/A')} groups, ${(local20kData && local20kData.leaves ? local20kData.leaves.length : 'N/A')} bundles, ${(local20kData && local20kData.atoms ? local20kData.atoms.length : 'N/A')} passages` : '3,711 groups, 9,177 bundles, 63,441 passages'}</p>
      `;
    } else if (node.type === 'parent') {
      const p = node.raw || {};
      const children = p.children || p.leaf_ids || [];
      const childrenLinks = children.slice(0, 10).map(cid => `<button class="node-link" data-id="${cid}" data-type="leaf">${cid}</button>`).join(', ');

      html = `
        <div class="inspector-badge" style="background: rgba(45, 212, 191, 0.15); color: #2dd4bf; font-weight: 700;">TOPIC GROUP</div>
        <p class="what-is"><strong>What this is:</strong> a topic group — documents with similar content gathered under one centroid.</p>
        <p><strong>ID:</strong> <code>${node.id}</code></p>
        <p><strong>Child bundles:</strong> ${children.length}</p>
        <p><strong>Total member passages:</strong> ${p.atom_count || 'N/A'}</p>
        <p><strong>Child bundles (sample):</strong> ${childrenLinks || 'None'}${children.length > 10 ? ` ... (+${children.length - 10} more)` : ''}</p>
        <div style="margin-top: 0.5rem;">
          <button class="btn btn-secondary btn-sm" id="btn-focus-this-parent" data-id="${node.id}">Focus &amp; Expand This Group</button>
        </div>
      `;
    } else if (node.type === 'leaf') {
      const l = node.raw || {};
      const pids = l.parent_ids || (l.parent_id ? [l.parent_id] : []);
      const parentLinks = pids.map(pid => `<button class="node-link" data-id="${pid}" data-type="parent">${pid}</button>`).join(', ');
      const atomIds = l.atom_ids || l.members || [];
      const atomLinks = atomIds.slice(0, 8).map(aid => `<button class="node-link" data-id="${aid}" data-type="atom">${aid.slice(0, 16)}...</button>`).join(', ');

      html = `
        <div class="inspector-badge" style="background: rgba(52, 211, 153, 0.15); color: #34d399; font-weight: 700;">DOCUMENT BUNDLE</div>
        <p class="what-is"><strong>What this is:</strong> a document bundle — the posting list where passages live.</p>
        <p><strong>ID:</strong> <code>${node.id}</code></p>
        ${pids.length > 1 ? `<div class="overlap-badge">Shared member: belongs to ${pids.length} topic groups</div>` : ''}
        <p><strong>Topic groups:</strong> ${parentLinks || 'None'}</p>
        <p><strong>Member passages:</strong> ${atomIds.length}</p>
        <p><strong>Document IDs:</strong> ${(l.doc_ids || []).slice(0, 6).join(', ') || 'N/A'}</p>
        <p><strong>Member passages (sample):</strong> ${atomLinks || 'None'}${atomIds.length > 8 ? ` ... (+${atomIds.length - 8} more)` : ''}</p>
      `;
    } else if (node.type === 'atom') {
      const a = node.raw || {};
      const lids = a.leaf_ids || [];
      const leafLinks = lids.map(lid => `<button class="node-link" data-id="${lid}" data-type="leaf">${lid}</button>`).join(', ');

      html = `
        <div class="inspector-badge" style="background: rgba(251, 191, 36, 0.15); color: #fbbf24; font-weight: 700;">TEXT PASSAGE</div>
        <p class="what-is"><strong>What this is:</strong> a text passage (atom) — a chunk cut from a real document.</p>
        <p><strong>Atom ID:</strong> <code>${node.id}</code></p>
        ${lids.length > 1 ? `<div class="overlap-badge">Shared member of ${lids.length} bundles</div>` : ''}
        <p><strong>Bundles:</strong> ${leafLinks || 'None'}</p>
        <p><strong>Source document:</strong> <code>${a.doc_id || 'N/A'}</code></p>
        ${a.chunk_ix !== undefined ? `<p><strong>Chunk index:</strong> ${a.chunk_ix}</p>` : ''}
        ${a.span ? `<p><strong>Token span:</strong> [${a.span[0]}, ${a.span[1]}]</p>` : ''}
        ${a.title ? `<p><strong>Document title:</strong> ${a.title}</p>` : ''}
        ${a.snippet ? `<blockquote style="background: rgba(255,255,255,0.05); padding: 0.5rem; border-left: 3px solid #fbbf24; margin-top: 0.5rem; font-size: 0.9rem; color: #f8fafc;">${a.snippet}</blockquote>` : ''}
      `;
    }

    nodeInspectorContent.innerHTML = html;

    // Attach click handlers to links inside inspector
    nodeInspectorContent.querySelectorAll('.node-link').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const id = btn.getAttribute('data-id');
        findAndInspectById(id);
      });
    });

    const focusBtn = nodeInspectorContent.querySelector('#btn-focus-this-parent');
    if (focusBtn) {
      focusBtn.addEventListener('click', () => {
        const id = focusBtn.getAttribute('data-id');
        currentClusterFocus = id;
        if (clusterSelect) clusterSelect.value = id;
        layoutAndDrawTopology();
      });
    }
  }

  // Find & Inspect by ID
  function findAndInspectById(id) {
    const activeData = (currentDataset === '10m') ? graph10mData : local20kData;
    if (!activeData) return;

    // Check parents
    const p = (activeData.parents || []).find(x => x.id === id);
    if (p) {
      inspectNode({ type: 'parent', id: p.id, raw: p });
      return;
    }

    // Check leaves
    const l = (activeData.leaves || []).find(x => x.id === id);
    if (l) {
      inspectNode({ type: 'leaf', id: l.id, raw: l });
      return;
    }

    // Check atoms
    const a = (activeData.atoms || []).find(x => x.id === id);
    if (a) {
      inspectNode({ type: 'atom', id: a.id, raw: a });
      return;
    }

    // Check by doc_id
    const aByDoc = (activeData.atoms || []).find(x => x.doc_id === id);
    if (aByDoc) {
      inspectNode({ type: 'atom', id: aByDoc.id, raw: aByDoc });
    }
  }

  function resetView() {
    zoomLevel = 1.0;
    panX = 0;
    panY = 0;
    selectedNode = null;
    currentClusterFocus = 'overview';
    if (clusterSelect) clusterSelect.value = 'overview';
    inspectNode(null);
  }

  // Canvas Interactions: Zoom, Pan, Click, Search
  function initCanvasInteractions() {
    if (!canvas) return;

    if (datasetSelect) {
      datasetSelect.addEventListener('change', (e) => {
        currentDataset = e.target.value;
        resetView();
        populateClusterSelector();
        updateStatusBanner();
        layoutAndDrawTopology();
      });
    }

    if (treeLevelSelect) {
      treeLevelSelect.addEventListener('change', () => {
        layoutAndDrawTopology();
      });
    }

    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        if (query.length > 2) {
          findAndInspectById(query);
        }
      });
    }

    if (btnZoomIn) {
      btnZoomIn.addEventListener('click', () => {
        zoomLevel = Math.min(zoomLevel * 1.25, 4.0);
        layoutAndDrawTopology();
      });
    }

    if (btnZoomOut) {
      btnZoomOut.addEventListener('click', () => {
        zoomLevel = Math.max(zoomLevel / 1.25, 0.4);
        layoutAndDrawTopology();
      });
    }

    if (btnResetZoom) {
      btnResetZoom.addEventListener('click', () => {
        resetView();
        layoutAndDrawTopology();
      });
    }

    // Pan via Drag
    canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      dragStartX = (e.clientX - rect.left) * scaleX - panX;
      dragStartY = (e.clientY - rect.top) * scaleY - panY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      panX = (e.clientX - rect.left) * scaleX - dragStartX;
      panY = (e.clientY - rect.top) * scaleY - dragStartY;
      layoutAndDrawTopology();
    });

    window.addEventListener('mouseup', () => {
      isDragging = false;
    });

    // Wheel Zoom
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      zoomLevel = Math.max(0.4, Math.min(zoomLevel * zoomFactor, 4.0));
      layoutAndDrawTopology();
    }, { passive: false });

    // Click to Inspect Node
    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const mouseX = ((e.clientX - rect.left) * scaleX - panX) / zoomLevel;
      const mouseY = ((e.clientY - rect.top) * scaleY - panY) / zoomLevel;

      let hit = null;
      for (let i = nodesToRender.length - 1; i >= 0; i--) {
        const n = nodesToRender[i];
        const dist = Math.hypot(n.x - mouseX, n.y - mouseY);
        if (dist <= n.radius + 10) {
          hit = n;
          break;
        }
      }
      inspectNode(hit);
    });

    // Keyboard Pan / Zoom on Canvas focus
    canvas.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowUp') { panY += 20; layoutAndDrawTopology(); }
      else if (e.key === 'ArrowDown') { panY -= 20; layoutAndDrawTopology(); }
      else if (e.key === 'ArrowLeft') { panX += 20; layoutAndDrawTopology(); }
      else if (e.key === 'ArrowRight') { panX -= 20; layoutAndDrawTopology(); }
      else if (e.key === '+' || e.key === '=') { zoomLevel = Math.min(zoomLevel * 1.2, 4.0); layoutAndDrawTopology(); }
      else if (e.key === '-' || e.key === '_') { zoomLevel = Math.max(zoomLevel / 1.2, 0.4); layoutAndDrawTopology(); }
      else if (e.key === 'Escape') { inspectNode(null); }
    });
  }

  // Guided tour (default): 5-step story driving the canvas via existing engine
  // hooks only (switchTab, dataset/cluster/tier controls, findAndInspectById,
  // inspectNode, resetView, goToStep). Programmatic zoom is closure-private, so
  // zoom beats are overlay annotations, not renderer changes.
  const TOUR_TOTAL = 5;
  let tourMode = true;
  let tourStep = 1;

  const TOUR_COPY = {
    1: {
      title: 'Step 1 of 5: Feed documents in',
      body: 'TRACE starts with ordinary documents streaming into the engine. You are on the small graph: 88 complete abstracts, 20,030 tokens. Every dot on the canvas comes from those arrivals.',
      annotation: 'Small graph: 88 documents in, 144 passages out.'
    },
    2: {
      title: 'Step 2 of 5: Broken into atoms',
      body: 'Each document is cut into content-addressed passages called atoms — the unit everything else points at. One real passage is open in the inspector, with its title and text.',
      annotation: 'Annotated zoom: the passage open in the inspector is one real atom.'
    },
    3: {
      title: 'Step 3 of 5: Self-organizes into schemas',
      body: 'Atoms attach to document bundles, bundles gather under topic groups — with no global rebuild. Pink links are shared members: 8 bundles here belong to more than one group (4,370 shared leaves in the 10M graph file).',
      annotation: 'Pink links = shared members. No rebuild: groups form as arrivals land.'
    },
    4: {
      title: 'Step 4 of 5: Ask a question',
      body: 'A question scores all 3,711 group centroids, keeps the top branches, and descends — scoring thousands of rows instead of everything. Measured: guided recall@10 0.7367 all-sources / 0.4883 leave-source-out. The replay below is the recorded mechanism.',
      annotation: 'Retrieval: score groups, keep top branches, descend, rank.'
    },
    5: {
      title: 'Step 5 of 5: Repairs itself',
      body: 'Background repair rebalances the graph until residual debt hits exactly zero: 6 iterations, 5,847 to 0, inside a 9,494.9 s run peaking at about 8.5 GB. Full measured card below — or jump to the 10M scale.',
      annotation: 'Repair converges: 6 iterations, debt 5,847 to exactly 0.'
    }
  };

  function setDatasetAndRedraw(v) {
    if (datasetSelect) datasetSelect.value = v;
    currentDataset = v;
    resetView();
    populateClusterSelector();
    updateStatusBanner();
    layoutAndDrawTopology();
  }

  function focusTourAtom() {
    setDatasetAndRedraw('20k');
    if (!local20kData || !local20kData.parents || !local20kData.parents.length) return;
    const sorted = [...local20kData.parents].sort((a, b) => (b.atom_count || 0) - (a.atom_count || 0));
    const p = sorted[0];
    if (!p) return;
    currentClusterFocus = p.id;
    if (clusterSelect) clusterSelect.value = p.id;
    const atom = (local20kData.atoms || []).find(a => a.snippet) || local20kData.atoms[0];
    if (atom) findAndInspectById(atom.id);
    else inspectNode({ type: 'parent', id: p.id, raw: p });
    layoutAndDrawTopology();
  }

  function renderTourAnnotation(text) {
    const panelNote = document.getElementById('tour-annotation');
    if (panelNote) panelNote.textContent = tourMode ? (text || '') : '';
    let note = document.getElementById('tour-canvas-note');
    if (!note) {
      const wrap = document.querySelector('.canvas-wrapper');
      if (wrap) {
        note = document.createElement('div');
        note.id = 'tour-canvas-note';
        note.className = 'tour-canvas-note';
        wrap.appendChild(note);
      }
    }
    if (note) {
      const topoActive = document.getElementById('tab-topology') &&
        document.getElementById('tab-topology').classList.contains('active');
      if (tourMode && topoActive && text) {
        note.textContent = text;
        note.hidden = false;
      } else {
        note.hidden = true;
      }
    }
  }

  function paintTourChrome() {
    const titleEl = document.getElementById('tour-title');
    const bodyEl = document.getElementById('tour-body');
    const cardEl = document.getElementById('tour-measured-card');
    const prevEl = document.getElementById('tour-prev');
    const nextEl = document.getElementById('tour-next');
    const toggleEl = document.getElementById('tour-toggle');
    const sectionEl = document.getElementById('guided-tour');
    const copy = TOUR_COPY[tourStep] || TOUR_COPY[1];
    if (titleEl) titleEl.textContent = tourMode ? copy.title : 'Guided tour (off — free explore mode)';
    if (bodyEl) bodyEl.textContent = tourMode ? copy.body : 'Tour hidden. The full graph, search, filters, and inspector are yours — one click restarts the 60-second story.';
    document.querySelectorAll('.tour-dot').forEach(d => {
      const s = parseInt(d.getAttribute('data-tour-step'), 10);
      const on = tourMode && s === tourStep;
      d.classList.toggle('active', on);
      if (on) d.setAttribute('aria-current', 'step');
      else d.removeAttribute('aria-current');
    });
    if (cardEl) cardEl.hidden = !(tourMode && tourStep === 5);
    if (prevEl) prevEl.disabled = !tourMode || tourStep === 1;
    if (nextEl) nextEl.disabled = !tourMode || tourStep === TOUR_TOTAL;
    if (toggleEl) {
      toggleEl.textContent = tourMode ? 'Exit tour · free explore' : 'Restart the 60-second tour';
      toggleEl.setAttribute('aria-pressed', tourMode ? 'true' : 'false');
    }
    if (sectionEl) sectionEl.classList.toggle('tour-off', !tourMode);
  }

  function applyTourStep(n) {
    if (!tourMode) { paintTourChrome(); renderTourAnnotation(''); return; }
    tourStep = Math.min(TOUR_TOTAL, Math.max(1, n));
    const copy = TOUR_COPY[tourStep];
    const topBtn = document.getElementById('tab-btn-topology');
    const queryBtn = document.getElementById('tab-btn-queries');
    if (tourStep === 4) {
      if (queryBtn) switchTab(queryBtn);
      goToStep(1);
    } else {
      if (topBtn) switchTab(topBtn);
      if (tourStep === 2) focusTourAtom();
      else setDatasetAndRedraw('20k');
    }
    paintTourChrome();
    renderTourAnnotation(copy.annotation);
  }

  function startTour(n) {
    tourMode = true;
    applyTourStep(n || 1);
  }

  function exitTour() {
    tourMode = false;
    resetView();
    layoutAndDrawTopology();
    paintTourChrome();
    renderTourAnnotation('');
  }

  function initTour() {
    const prevEl = document.getElementById('tour-prev');
    const nextEl = document.getElementById('tour-next');
    const scaleEl = document.getElementById('tour-scale');
    const toggleEl = document.getElementById('tour-toggle');
    if (prevEl) prevEl.addEventListener('click', () => applyTourStep(tourStep - 1));
    if (nextEl) nextEl.addEventListener('click', () => applyTourStep(tourStep + 1));
    if (scaleEl) scaleEl.addEventListener('click', () => {
      const topBtn = document.getElementById('tab-btn-topology');
      if (topBtn) switchTab(topBtn);
      setDatasetAndRedraw('10m');
      renderTourAnnotation('10M scale: 3,711 groups, 9,177 bundles, 63,441 passages (earlier freeze, counts match).');
    });
    if (toggleEl) toggleEl.addEventListener('click', () => {
      if (tourMode) exitTour();
      else startTour(tourStep);
    });
    document.querySelectorAll('.tour-dot').forEach(d => {
      d.addEventListener('click', () => {
        tourMode = true;
        applyTourStep(parseInt(d.getAttribute('data-tour-step'), 10));
      });
    });
    // Keep the canvas overlay annotation truthful when the user switches tabs manually.
    tabButtons.forEach(b => b.addEventListener('click', () => {
      if (tourMode) renderTourAnnotation((TOUR_COPY[tourStep] || {}).annotation);
    }));
    paintTourChrome();
  }

  // Lifecycle Init
  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initStepper();
    initCanvasInteractions();
    initTour();
    loadData();
    applyTourStep(1);
  });

  // Read-only QA Test & Pure Validation API (pure functions / getters, non-mutating)
  if (typeof window !== 'undefined') {
    window.TRACE_VALIDATION = Object.freeze({
      validate10mData,
      validate20kData,
      validateGraphIntegrity,
      computeSha256Hex,
      loadGzipOrJson,
      getDatasetErrors: () => ({ ...datasetErrors }),
      getLocal20kData: () => local20kData,
      getGraph10mData: () => graph10mData,
      getQualificationData: () => qualificationData,
      VERIFIED_SOURCEFREEZE,
      VERIFIED_10M_PIN,
      EXPECTED_10M_GZIP_BYTES,
      EXPECTED_10M_GZIP_SHA256,
      EXPECTED_10M_PLAIN_BYTES,
      EXPECTED_10M_PLAIN_SHA256,
      MAX_PAYLOAD_BYTES,
      SEAM12A_WALLS_S,
      SEAM12A_TOTAL_WALL_S
    });
    window.TRACE_TOUR = Object.freeze({
      go: applyTourStep,
      start: startTour,
      exit: exitTour,
      state: () => ({ tourMode, tourStep, total: TOUR_TOTAL })
    });
  }

})();
