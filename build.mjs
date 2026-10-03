import {build} from 'esbuild';
import {execFileSync} from 'node:child_process';
import {copyFileSync} from 'node:fs';
await build({entryPoints:['frontend/app.js'],bundle:true,minify:true,sourcemap:false,format:'esm',outfile:'looking_glass/static/app.js'});
execFileSync('node',['node_modules/@tailwindcss/cli/dist/index.mjs','-i','frontend/style.css','-o','looking_glass/static/style.css','--minify'],{stdio:'inherit'});
copyFileSync('node_modules/htmx.org/dist/htmx.min.js','looking_glass/static/htmx.min.js');
