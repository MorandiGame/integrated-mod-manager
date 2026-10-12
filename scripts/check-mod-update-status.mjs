import assert from 'node:assert/strict';
import { latestModFileDate, modUpdateStatus } from '../src/utils/modUpdateStatus.ts';

const files = [{_tsDateAdded: 1700000000}]; // A page with one original file.
const latest = latestModFileDate(files);
const observed = {};
const imported = {updated: 0, viewed: 0, observationKey: 'NTE/imported/sourceA'};
assert.equal(modUpdateStatus(imported, latest, observed), 0, 'No installed version must not imply an update');
assert.equal(modUpdateStatus(imported, latest, observed), 0, 'Repeated checks of the same single file must stay clear');
assert.equal(modUpdateStatus(imported, latest + 1000, observed), 2, 'A genuinely newer file after observation is an update');
assert.equal(modUpdateStatus({...imported, viewed: latest + 1000}, latest + 1000, observed), 1);
assert.equal(modUpdateStatus({...imported, observationKey: 'NTE/imported/sourceB'}, latest + 1000, observed), 0, 'A changed source needs its own baseline');
assert.equal(modUpdateStatus({...imported, updated: latest}, latest, observed), 0);
assert.equal(modUpdateStatus({...imported, updated: latest - 1000}, latest, observed), 2, 'Known old installed versions still update, even if only one file is currently listed');
assert.equal(modUpdateStatus({...imported, updated: -1, observationKey: 'failed-download'}, latest, observed), 0);
assert.equal(modUpdateStatus(imported, 0, observed), 0);
assert.equal(latestModFileDate(undefined), 0);
assert.equal(latestModFileDate([{_tsDateModified: 'invalid'}]), 0);
assert.equal(latestModFileDate([{_tsDateModified: 1700000001}, ...files]), latest + 1000);
assert.equal(modUpdateStatus({...imported, updated: latest}, latestModFileDate(files), observed), 0, 'Page metadata changes do not change the file date');
console.log('Mod update checks passed: unknown imports, single files, actual new files, source isolation, and known versions.');
