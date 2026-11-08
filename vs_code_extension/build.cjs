const {buildSync} = require('esbuild');
buildSync({entryPoints:['src/extension.cjs'],outfile:'dist/extension.cjs',bundle:true,platform:'node',target:'node20',external:['vscode'],format:'cjs',legalComments:'none'});
