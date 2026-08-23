#!/usr/bin/env node
// Live preview server — see docs/design/previews.md
//
//   node viewer/server.mjs [source.scad] [--format stl|3mf] [--port 5173]
//
// Watches sources, re-renders through bin/openscad, and PUSHES a reload signal
// once the render is complete. Nothing watches the output file: that is the
// point. The browser holds one three.js scene for its whole lifetime and only
// swaps geometry, so the camera survives every reload.
//
// No dependencies — node: builtins only, so there is nothing to install.

import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { watch, promises as fsp, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const execFileP = promisify(execFile);

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(REPO);                 // bin/openscad mounts $PWD; must be repo root

// ------------------------------------------------------------------ args ---
const argv = process.argv.slice(2);
const opt = (name, def) => {
  const i = argv.indexOf('--' + name);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : def;
};
const positional = argv.filter((a, i) =>
  !a.startsWith('--') && !(i > 0 && argv[i - 1].startsWith('--')));

const SOURCE = positional[0] ?? 'scad/bases/one_inch.scad';
// 3mf is the default: it is the primary format in initial-design.md, three.js
// parses it without special handling (verified), and it is far smaller on the
// wire — 10KB vs 191KB for the same part, which matters on every reload.
const FORMAT = opt('format', '3mf');
const PORT   = Number(opt('port', 5173));
const WATCH  = opt('watch', 'scad');

if (!existsSync(SOURCE)) {
  console.error(`source not found: ${SOURCE}`);
  process.exit(1);
}
if (!['stl', '3mf'].includes(FORMAT)) {
  console.error(`--format must be stl or 3mf (got ${FORMAT})`);
  process.exit(1);
}

const CACHE = path.join(REPO, 'viewer', '.cache');
const OUT   = path.join(CACHE, `model.${FORMAT}`);
// Temp name keeps a format-valid suffix: OpenSCAD infers the exporter from the
// extension and hard-errors on anything else (see docs/design/previews.md).
const TMP   = path.join(CACHE, `.tmp-model.${FORMAT}`);

await fsp.mkdir(CACHE, { recursive: true });

// ------------------------------------------------------------------ SSE ----
const clients = new Set();
function push(event, data = '') {
  const payload = `event: ${event}\ndata: ${String(data).replace(/\n/g, '\\n')}\n\n`;
  for (const res of clients) res.write(payload);
}

// --------------------------------------------------------------- render ----
let lastError = null;
let rendering = false;
let queued = false;

async function render(reason) {
  if (rendering) { queued = true; return; }
  rendering = true;
  push('rendering');
  const started = Date.now();
  try {
    await execFileP('./bin/openscad', [
      '--backend=manifold',
      '--hardwarnings',
      '-o', path.relative(REPO, TMP),
      SOURCE,
    ], { cwd: REPO });

    // Atomic swap: a concurrent GET /model can never observe a partial mesh.
    await fsp.rename(TMP, OUT);

    lastError = null;
    const ms = Date.now() - started;
    console.log(`  rendered ${SOURCE} -> ${path.relative(REPO, OUT)} (${ms}ms, ${reason})`);
    push('rendered');
  } catch (err) {
    lastError = (err.stderr || err.message || String(err)).trim();
    console.error(`  render FAILED: ${lastError.split('\n')[0]}`);
    push('failed', lastError);
    await fsp.rm(TMP, { force: true });
  } finally {
    rendering = false;
    if (queued) { queued = false; render('queued'); }
  }
}

// -------------------------------------------------------------- watcher ----
// Watches SOURCES only. Debounced, because one editor save emits several
// inotify events (verified: an atomic-rename save produced two).
let timer = null;
function onChange(file) {
  clearTimeout(timer);
  timer = setTimeout(() => render(`changed: ${file}`), 150);
}

if (existsSync(WATCH)) {
  watch(WATCH, { recursive: true }, (_type, name) => {
    if (name && name.endsWith('.scad')) onChange(name);
  });
  console.log(`watching ${WATCH}/**/*.scad`);
}

// --------------------------------------------------------------- server ----
const TYPES = { stl: 'model/stl', '3mf': 'model/3mf' };

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');

  if (url.pathname === '/events') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.write('retry: 1000\n\n');
    clients.add(res);
    const beat = setInterval(() => res.write(': ping\n\n'), 25000);
    req.on('close', () => { clearInterval(beat); clients.delete(res); });
    return;
  }

  if (url.pathname === '/info') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ source: SOURCE, format: FORMAT, error: lastError }));
    return;
  }

  if (url.pathname === '/model') {
    try {
      const buf = await fsp.readFile(OUT);
      res.writeHead(200, {
        'Content-Type': TYPES[FORMAT],
        'Content-Length': buf.length,
        'Cache-Control': 'no-store, must-revalidate',
      });
      res.end(buf);
    } catch {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('no model rendered yet');
    }
    return;
  }

  if (url.pathname === '/' || url.pathname === '/index.html') {
    const buf = await fsp.readFile(path.join(REPO, 'viewer', 'index.html'));
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(buf);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('not found');
});

server.listen(PORT, '0.0.0.0', async () => {
  console.log(`\n  source  ${SOURCE}`);
  console.log(`  format  ${FORMAT}`);
  console.log(`  url     http://localhost:${PORT}\n`);
  await render('startup');
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => { console.log('\nstopping'); server.close(); process.exit(0); });
}
