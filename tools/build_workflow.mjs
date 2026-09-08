import {build} from 'esbuild';
import {readFile, readdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

const output = 'app/api/static/workflow-editor.js';
const result = await build({entryPoints:['app/api/static/workflow-editor.src.js'], bundle:true,
  minify:true, format:'iife', target:'es2022', legalComments:'linked', outfile:output, metafile:true});
const packages = new Set(Object.keys(result.metafile.inputs).flatMap(file => {
  const match = file.replaceAll('\\','/').match(/node_modules\/(@[^/]+\/[^/]+|[^/]+)\//);
  return match ? [match[1]] : [];
}));
const licenses = [];
for (const name of [...packages].sort()) {
  const directory = path.join('node_modules', name);
  const metadata = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
  const files = (await readdir(directory)).filter(file => /^(license|copying|notice)(\.|$)/i.test(file));
  if (!files.length) throw Error(`Missing dependency license: ${name}`);
  for (const file of files) licenses.push(`${name}@${metadata.version} — ${file}\n${await readFile(path.join(directory,file),'utf8')}`);
}
await writeFile('app/api/static/workflow-licenses.txt', licenses.join('\n\n'), 'utf8');
console.log(`Built ${output}; retained licenses for ${packages.size} bundled packages.`);
