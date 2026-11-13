// The in-app guide and both Markdown guides share the same bilingual source.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(root, 'SetupHelp.js'), 'utf8').replace(/^\.pragma library\s*/, ''), context);
function render(language) {
  const help = context.guide(language);
  const lines = ['# '+help.title, '', help.intro, '', help.existing, '', help.privacy, ''];
  for (const [index, step] of help.steps.entries()) {
    lines.push('## '+(index+1)+'. '+step.title, '', ...step.paragraphs.flatMap(p=>[p, '']));
    if (step.location) lines.push('`'+step.location+'`', '');
    if (step.code) lines.push('```'+(step.code.startsWith('chmod')?'bash':'text'), step.code, '```', '');
    lines.push(...step.links.flatMap(link=>['['+link.label+']('+link.url+')', '']));
  }
  lines.push('## '+help.troubleshooting, '', ...help.problems.flatMap(p=>['- '+p, '']),
    ...help.supportLinks.flatMap(link=>['['+link.label+']('+link.url+')', '']));
  const recovery = context.guide(language, true);
  lines.push('## '+recovery.title, '');
  for (const [index, step] of recovery.steps.entries()) {
    lines.push('### '+(index+1)+'. '+step.title, '', ...step.paragraphs.flatMap(p=>[p, '']));
    if (step.location) lines.push('`'+step.location+'`', '');
    if (step.code) lines.push('```bash', step.code, '```', '');
  }
  return lines.join('\n');
}
if (require.main === module) {
  for (const language of ['en', 'es']) {
    const file = path.join(root, 'docs', 'OAUTH_SETUP.'+language+'.md');
    if (process.argv.includes('--check')) {
      if (fs.readFileSync(file, 'utf8') !== render(language)) throw new Error(file+' is out of date');
    } else fs.writeFileSync(file, render(language));
  }
}
module.exports = {render};
