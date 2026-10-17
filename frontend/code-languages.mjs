import {StreamLanguage} from '@codemirror/language';
import {python} from '@codemirror/lang-python';
import {html} from '@codemirror/lang-html';
import {json} from '@codemirror/lang-json';
import {shell} from '@codemirror/legacy-modes/mode/shell';
import {yaml} from '@codemirror/legacy-modes/mode/yaml';
import {toml} from '@codemirror/legacy-modes/mode/toml';

export const shellLanguage=StreamLanguage.define(shell);
const yamlLanguage=StreamLanguage.define(yaml),tomlLanguage=StreamLanguage.define(toml);

// Share the same parser between file editors and Markdown fence rendering.
export function codeLanguage(info){switch(info.trim().split(/\s+/)[0].toLowerCase()){
  case 'py':case 'python':return python().language;
  case 'sh':case 'bash':case 'shell':return shellLanguage;
  case 'json':return json().language;
  case 'html':case 'htm':return html().language;
  case 'yaml':case 'yml':return yamlLanguage;
  case 'toml':return tomlLanguage;
  default:return null;
}}
