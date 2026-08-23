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
import { execFile, execFileSync } from 'node:child_process';
import os from 'node:os';
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

const PART = positional[0] ?? '';
// 3mf is the default: it is the primary format in initial-design.md, three.js
// parses it without special handling (verified), and it is far smaller on the
// wire — 10KB vs 191KB for the same part, which matters on every reload.
const FORMAT = opt('format', '3mf');
const PORT   = Number(opt('port', 5173));
if (!['stl', '3mf'].includes(FORMAT)) {
  console.error(`--format must be stl or 3mf (got ${FORMAT})`);
  process.exit(1);
}

// Ask the catalog what exists rather than globbing: a part's path cannot be
// constructed from its name, since categories are not part of the name.
function catalog() {
  const out = execFileSync('./bin/python3', ['tools/catalog.py', '--json'],
                           { cwd: REPO, encoding: 'utf8' });
  return JSON.parse(out);
}

let PARTS;
try {
  PARTS = catalog();
} catch (err) {
  console.error('could not read the catalog (is the toolchain image available?)');
  console.error(String(err.stderr || err.message));
  process.exit(1);
}

const part = PARTS.find(p => p.name === PART);
if (!part) {
  console.error(PART ? `no part named '${PART}'` : 'no part given');
  console.error(`\navailable parts:\n  ${PARTS.map(p => p.name).join('\n  ')}`);
  console.error(`\nusage: node viewer/server.mjs <part-name> [--format stl|3mf]`);
  process.exit(1);
}

// The preview serves the same artifact `make` builds, out of the same tree --
// so previewing and building are one code path, not two that can disagree.
const variant = part.variants[0];
const stem = `${part.name}-v${part.version}` +
             (variant.param_set !== null ? `-${variant.name}` : '');
const OUT = path.join(REPO, 'out', part.name, `${stem}.${FORMAT}`);

// Watch sources, not output. entry.yaml and params.json are included because
// `openscad -d` does not record either, so make cannot infer them.
const WATCH_DIRS = ['parts', 'lib'].filter(d => existsSync(path.join(REPO, d)));

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
    // make decides what actually needs rebuilding, including the case where a
    // lib/ edit moves several parts at once. It also handles the temp-then-
    // atomic-rename discipline, so a concurrent GET /model can never observe a
    // partial mesh.
    await execFileP('make', ['-j' + (os.cpus().length || 2)], { cwd: REPO });

    lastError = null;
    const ms = Date.now() - started;
    console.log(`  built (${ms}ms, ${reason})`);
    push('rendered');
  } catch (err) {
    lastError = [err.stdout, err.stderr, err.message]
      .filter(Boolean).join('\n').trim();
    console.error(`  BUILD FAILED (${reason})`);
    console.error(lastError.split('\n').slice(-6).join('\n'));
    // The last good model stays on the served path, so the preview degrades to
    // stale rather than to blank.
    push('failed', lastError.split('\n').slice(-6).join('\n'));
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

for (const dir of WATCH_DIRS) {
  watch(dir, { recursive: true }, (_type, name) => {
    if (!name) return;
    if (/\.(scad|ya?ml|json)$/.test(name)) onChange(`${dir}/${name}`);
  });
}
console.log(`watching ${WATCH_DIRS.join(', ')} for .scad/.yaml/.json changes`);

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
    res.end(JSON.stringify({
      source: `${part.name} v${part.version}`, format: FORMAT, error: lastError }));
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
  console.log(`\n  part    ${part.name} v${part.version}  (${part.path})`);
  console.log(`  serving ${path.relative(REPO, OUT)}`);
  console.log(`  format  ${FORMAT}`);
  console.log(`  url     http://localhost:${PORT}\n`);
  await render('startup');
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => { console.log('\nstopping'); server.close(); process.exit(0); });
}
