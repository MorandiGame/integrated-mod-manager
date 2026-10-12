import fs from 'node:fs';
import sanitize from 'sanitize-filename';
const path = 'src/gameData.json';
const data = JSON.parse(fs.readFileSync(path, 'utf8'));
const game = JSON.parse(fs.readFileSync('tools/nte-game.json', 'utf8'));
const categories = JSON.parse(fs.readFileSync('tools/nte-categories.json', 'utf8'));
const normalize = c => ({...c, _sName: sanitize(c._sName, {replacement:'_'}), _sIconUrl: c._sIconUrl || '/who.jpg'});
data.NTE = {
  id: {categories:'37906', game:'23012'},
  categoryList: categories.map(normalize),
  generic: {
    categories: game._aModRootCategories.filter(c => c._idRow !== 37906).map(normalize),
    types: game._aModRootCategories.map(normalize),
  },
};
fs.writeFileSync(path, JSON.stringify(data, null, '\t') + '\n');
console.log(`Added ${categories.length} GameBanana NTE character categories`);
