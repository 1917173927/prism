import path from 'node:path';
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const skill = process.env.PRESENTATION_SKILL_DIR;
const root = process.cwd();
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const result = await finalizePresentation({
  workspaceDir: root,
  candidatePath: path.join(root, 'output/technical-presentation/animated-candidate-v2.pptx'),
  finalPath: path.join(root, 'docs/submission/technical-presentation/Prism核心技术与创新机制.pptx'),
  pythonExecutable: process.env.RUNTIME_PYTHON,
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit', ...[13, 14, 17, 22, 25].flatMap(slide => ['--require-native-table-slide', String(slide)])],
  explicitTotalSlideCount: 25,
  requiredNativeTableOwnerSlides: [13, 14, 17, 22, 25],
  requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: 'design', families: ['Microsoft YaHei'] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(root, 'output/technical-presentation/final.validation.json'),
});
await fs.writeFile(path.join(root, 'output/technical-presentation/finalization-result.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify({ final: 'docs/submission/technical-presentation/Prism核心技术与创新机制.pptx' }));
