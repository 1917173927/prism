import { build } from "esbuild";
await build({entryPoints: ["app/api/static/markdown.src.js"], bundle: true, minify: true, outfile: "app/api/static/markdown.js", legalComments: "linked"});
