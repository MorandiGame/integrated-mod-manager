// Run the actual Page1 effect with controlled hooks/timers, without a desktop UI.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { transform } from 'esbuild';

const source = fs.readFileSync('src/_Checklist/pages/Page1.tsx', 'utf8');
const { code } = await transform(source, { loader: 'tsx', format: 'cjs', jsx: 'automatic' });

function mount(game) {
  const effects = [];
  const timers = new Map();
  const pages = [];
  let nextId = 0;
  const hooks = {
    useEffect: callback => effects.push(callback),
    useState: initial => [initial, () => {}],
    useRef: initial => ({current: initial}),
  };
  const imports = {
    react: hooks,
    'react/jsx-runtime': { jsx: () => null, jsxs: () => null },
    jotai: {
      useAtomValue: atom => atom === 'GAME' ? game : 'fin',
      useAtom: () => ['cn', () => {}],
    },
    'motion/react': { AnimatePresence: () => null, motion: {div: () => null} },
    '@/components/ui/button': { Button: () => null },
    '@/utils/consts': { LANG_LIST: [] },
    '@/utils/filesys': { resetWithBackup() {} },
    '@/textData.json': { default: {} },
    '@/utils/vars': { GAME: 'GAME', MAIN_FUNC_STATUS: 'STATUS', SAVED_LANG: 'LANG' },
  };
  const module = {exports: {}};
  const createTimer = callback => { const id = ++nextId; timers.set(id, callback); return id; };
  new Function('require', 'module', 'exports', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', code)(
    name => { assert.ok(name in imports, `Unexpected import: ${name}`); return imports[name]; },
    module, module.exports, createTimer, id => timers.delete(id), () => ++nextId, () => {},
  );
  module.exports.default({setPage: page => pages.push(page)});
  const cleanup = effects[0]();
  return {pages, cleanup, advance: () => { const pending = [...timers.values()]; timers.clear(); pending.forEach(callback => callback()); }};
}
const selected = mount('NTE');
selected.advance();
assert.deepEqual(selected.pages, [2], 'A selected game must advance to directory verification');
const firstSetup = mount('');
firstSetup.advance();
assert.deepEqual(firstSetup.pages, [1], 'First setup still asks the user to select a game');
const abandoned = mount('');
abandoned.cleanup();
abandoned.advance();
assert.deepEqual(abandoned.pages, [], 'An unmounted splash must not return to the game selector');
console.log('Checklist checks passed: selected game advances, first setup selects, stale timer is cancelled.');
