// Exercise the shipped Task Builder functions without opening Roblox.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8');
new vm.Script(source);
function extract(name) {
  const start = source.indexOf('function ' + name + '(');
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(start, i+1);
  }
  throw Error('Missing ' + name);
}
const context = vm.createContext({assert, console});
const taskData = source.slice(source.indexOf('const TASK_DATA ='), source.indexOf('let mapSetups ='));
vm.runInContext(String.raw`
  ${taskData}
  const DEFAULT_INFINITE_WAVE_LIMIT = 20;
  const MAX_EXTRACT_AFTER = 9999;
  const selectedTaskId = 'test';
  const taskTemplates = ['Bossrush units'];
  let task, saved;
  const builder = {innerHTML: ''};
  const document = {getElementById: id => id === 'task-builder' ? builder : null};
  const escapeHtml = x => String(x);
  const newTaskId = () => 'test';
  const findTask = () => task;
  const updateQueueRowInPlace = () => {};
  const saveTaskQueue = () => {saved = JSON.parse(JSON.stringify(task));};
  ${['defaultTask', 'setTaskProp', 'taskOpts', 'taskSummary', 'renderTaskBuilder'].map(extract).join('\n')}
  task = defaultTask();
  setTaskProp(task.id, 'mode', 'bossrush');
  assert.equal(task.map, 'District 7');
  assert.equal(task.bossrush_gates, 2);
  assert.equal(task.bossrush_card, 'random');
  assert.equal(task.macro, '');
  assert.match(builder.innerHTML, /Gates before boss/);
  assert.match(builder.innerHTML, /value="6"/);
  assert.match(builder.innerHTML, /Buff cards/);
  assert.match(builder.innerHTML, /Matchmaking/);
  assert.match(builder.innerHTML, /Runs before returning to lobby/);
  assert.match(builder.innerHTML, /Bossrush units/);
  setTaskProp(task.id, 'bossrush_gates', '6');
  setTaskProp(task.id, 'bossrush_card', 'light');
  setTaskProp(task.id, 'play_mode', 'matchmaking');
  setTaskProp(task.id, 'macro', 'Bossrush units');
  assert.equal(saved.bossrush_gates, 6);
  assert.equal(saved.bossrush_card, 'light');
  assert.equal(saved.play_mode, 'matchmaking');
  task = JSON.parse(JSON.stringify(saved));
  renderTaskBuilder();
  assert.match(builder.innerHTML, /value="6" selected/);
  assert.match(builder.innerHTML, /value="light" selected/);
  assert.match(taskSummary(task).title, /District 7/);
  assert.match(taskSummary(task).meta, /6 gates \/ light cards/);
  assert.match(taskSummary(task).meta, /Matchmaking/);
  assert.equal(TASK_DATA.story.label, 'Story');
  assert.equal(TASK_DATA.raid.label, 'Raid');
`, context);
console.log('Bossrush Task Builder: defaults, controls, save/restore, custom macro and matchmaking passed.');
