import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.cwd();
const skillDir=process.env.PRESENTATION_SKILL_DIR ?? 'C:/Users/pc/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
const runtimePython=process.env.RUNTIME_PYTHON ?? 'C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
process.env.RUNTIME_NODE_MODULES ??= 'C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
process.env.RUNTIME_NODE ??= 'C:/Users/pc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';
process.env.RUNTIME_PYTHON ??= runtimePython;
const buildDir=path.join(root,'output/innovation-animation-20261007');
const finalPath=path.join(root,'docs/submission/technical-presentation/innovation-details-20261007/Prism技术机制拆分动画.pptx');
await fs.mkdir(path.dirname(finalPath),{recursive:true});
const {finalizePresentation}=await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({
 workspaceDir:root,candidatePath:path.join(buildDir,'animated-candidate-v2.pptx'),finalPath,
 pythonExecutable:runtimePython,
 integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:5,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:['Microsoft YaHei']},verifyArtifactToolImport:true,
 receiptPath:path.join(buildDir,'final.validation.json')
});
await fs.writeFile(path.join(buildDir,'finalization-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({finalPath}));
