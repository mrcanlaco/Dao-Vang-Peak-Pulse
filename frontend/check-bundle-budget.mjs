import { readdir, readFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';

const assetsDirectory = new URL('./dist/assets/', import.meta.url);
const budgets = {
  javascript: {
    raw: 500 * 1024,
    gzip: 170 * 1024,
  },
  stylesheet: {
    raw: 180 * 1024,
    gzip: 25 * 1024,
  },
};

const formatKiB = (bytes) => `${(bytes / 1024).toFixed(1)} KiB`;
const assetNames = (await readdir(assetsDirectory))
  .filter((name) => name.endsWith('.js') || name.endsWith('.css'))
  .sort();

if (assetNames.length === 0) {
  throw new Error('No built JavaScript or CSS assets found. Run the frontend build first.');
}

const violations = [];
const rows = [];

for (const name of assetNames) {
  const contents = await readFile(new URL(name, assetsDirectory));
  const rawBytes = contents.byteLength;
  const gzipBytes = gzipSync(contents, { level: 9 }).byteLength;
  const budget = name.endsWith('.js') ? budgets.javascript : budgets.stylesheet;

  rows.push({
    asset: name,
    raw: formatKiB(rawBytes),
    gzip: formatKiB(gzipBytes),
  });

  if (rawBytes > budget.raw) {
    violations.push(
      `${name}: raw size ${formatKiB(rawBytes)} exceeds ${formatKiB(budget.raw)}`,
    );
  }
  if (gzipBytes > budget.gzip) {
    violations.push(
      `${name}: gzip size ${formatKiB(gzipBytes)} exceeds ${formatKiB(budget.gzip)}`,
    );
  }
}

console.table(rows);

if (violations.length > 0) {
  console.error('Bundle budget exceeded:');
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exitCode = 1;
} else {
  console.log('Bundle budgets passed.');
}
