import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repositoryRoot = fileURLToPath(new URL('../', import.meta.url));
const virtualEnvironmentPython =
	process.platform === 'win32'
		? path.join(repositoryRoot, '.venv', 'Scripts', 'python.exe')
		: path.join(repositoryRoot, '.venv', 'bin', 'python');
const executable =
	process.env.F1_PYTHON ??
	(existsSync(virtualEnvironmentPython)
		? virtualEnvironmentPython
		: process.platform === 'win32'
			? 'python'
			: 'python3');

const result = spawnSync(executable, process.argv.slice(2), {
	cwd: repositoryRoot,
	stdio: 'inherit'
});

if (result.error) {
	console.error(`Unable to run Python with ${executable}: ${result.error.message}`);
	process.exit(1);
}

process.exit(result.status ?? 1);
