import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import readline from 'readline';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Helper to detect Python executable path
function getPythonPath() {
  const isWin = process.platform === 'win32';
  const venvPath = path.join(__dirname, '.venv');

  if (fs.existsSync(venvPath)) {
    const winPython = path.join(venvPath, 'Scripts', 'python.exe');
    const winPythonNoExe = path.join(venvPath, 'Scripts', 'python');
    const unixPython = path.join(venvPath, 'bin', 'python');
    const unixPython3 = path.join(venvPath, 'bin', 'python3');

    if (isWin) {
      if (fs.existsSync(winPython)) return winPython;
      if (fs.existsSync(winPythonNoExe)) return winPythonNoExe;
    } else {
      if (fs.existsSync(unixPython)) return unixPython;
      if (fs.existsSync(unixPython3)) return unixPython3;
    }
  }

  // Fallback to system Python
  return isWin ? 'python' : 'python3';
}

const pythonPath = getPythonPath();
const backendCwd = path.join(__dirname, 'backend');

console.log(`\x1b[35m[System] Starting development environments...\x1b[0m`);
console.log(`\x1b[35m[System] Python Path: ${pythonPath}\x1b[0m`);

// Start backend
const backend = spawn(pythonPath, ['main.py'], {
  cwd: backendCwd,
  stdio: 'pipe'
});

// Start frontend
const vitePath = path.join(__dirname, 'node_modules', 'vite', 'bin', 'vite.js');
let frontend;

if (fs.existsSync(vitePath)) {
  frontend = spawn(process.execPath, [vitePath], {
    cwd: __dirname,
    stdio: 'pipe'
  });
} else {
  // Fallback if vite is not found in standard node_modules
  frontend = spawn('npx', ['vite'], {
    cwd: __dirname,
    stdio: 'pipe',
    shell: true
  });
}

// Prefix and log helper
function setupLogging(proc, prefix, colorCode) {
  if (!proc.stdout || !proc.stderr) return;

  const rlOut = readline.createInterface({
    input: proc.stdout,
    terminal: false
  });
  rlOut.on('line', (line) => {
    console.log(`\x1b[${colorCode}m[${prefix}]\x1b[0m ${line}`);
  });

  const rlErr = readline.createInterface({
    input: proc.stderr,
    terminal: false
  });
  rlErr.on('line', (line) => {
    console.error(`\x1b[${colorCode}m[${prefix}]\x1b[0m ${line}`);
  });
}

// 36 is Cyan, 32 is Green
setupLogging(backend, 'Backend', '36');
setupLogging(frontend, 'Frontend', '32');

// Clean up processes on exit
let isCleaningUp = false;
const cleanup = (code = 0) => {
  if (isCleaningUp) return;
  isCleaningUp = true;
  console.log(`\n\x1b[35m[System] Shutting down development servers...\x1b[0m`);
  try {
    backend.kill('SIGTERM');
  } catch (e) {}
  try {
    frontend.kill('SIGTERM');
  } catch (e) {}
  process.exit(code);
};

backend.on('error', (err) => {
  console.error(`\x1b[31m[System] Backend error: ${err.message}\x1b[0m`);
  cleanup(1);
});

frontend.on('error', (err) => {
  console.error(`\x1b[31m[System] Frontend error: ${err.message}\x1b[0m`);
  cleanup(1);
});

backend.on('exit', (code) => {
  console.log(`\x1b[35m[System] Backend exited with code ${code}\x1b[0m`);
  cleanup(code || 0);
});

frontend.on('exit', (code) => {
  console.log(`\x1b[35m[System] Frontend exited with code ${code}\x1b[0m`);
  cleanup(code || 0);
});

process.on('SIGINT', () => cleanup(0));
process.on('SIGTERM', () => cleanup(0));
process.on('uncaughtException', (err) => {
  console.error(`\x1b[31m[System] Uncaught exception: ${err.message}\x1b[0m`);
  cleanup(1);
});
