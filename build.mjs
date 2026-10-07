import {build} from 'esbuild';
import {execFileSync} from 'node:child_process';
import {copyFileSync,readFileSync,writeFileSync} from 'node:fs';
import {gzipSync} from 'node:zlib';
await build({entryPoints:['frontend/app.js'],external:['/static/mermaid.js'],bundle:true,minify:true,sourcemap:false,format:'esm',outfile:'looking_glass/static/app.js'});
const diagrams=await build({entryPoints:['frontend/diagrams.mjs'],bundle:true,minify:true,format:'esm',write:false,outfile:'mermaid.js'});
writeFileSync('looking_glass/static/mermaid.js.gz',gzipSync(diagrams.outputFiles[0].contents,{level:9}));
execFileSync('node',['node_modules/@tailwindcss/cli/dist/index.mjs','-i','frontend/style.css','-o','looking_glass/static/style.css','--minify'],{stdio:'inherit'});
copyFileSync('node_modules/htmx.org/dist/htmx.min.js','looking_glass/static/htmx.min.js');

// Bundle the fonts and license for offline installations.
for(const match of readFileSync('frontend/newsreader.css','utf8').matchAll(/url\(\/static\/([^)]*)\)/g)){
  copyFileSync('node_modules/@fontsource-variable/newsreader/files/'+match[1],'looking_glass/static/'+match[1]);
}
copyFileSync('node_modules/@fontsource-variable/newsreader/LICENSE','looking_glass/static/newsreader-license.txt');
