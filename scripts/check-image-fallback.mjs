import assert from 'node:assert/strict';
import { applyImageFallback } from '../src/utils/imageFallback.ts';

function missingImage(src) {
  let writes = 0;
  return {
    style: {}, classList: { remove() {} },
    getAttribute(name) { return name === 'src' ? src : null; },
    set src(value) { src = value; writes++; },
    get writes() { return writes; },
  };
}
const preview = missingImage('/missing-preview');
applyImageFallback(preview, '/NTELogo.png');
assert.equal(preview.getAttribute('src'), '/NTELogo.png');
// The fallback failing repeatedly must neither reassign src nor trigger reloads.
for (let i = 0; i < 10; i++) applyImageFallback(preview, '/NTELogo.png');
assert.equal(preview.writes, 1);
assert.equal(preview.style.opacity, '0');
const background = missingImage('/missing-preview');
applyImageFallback(background, '/WWmm.png', true);
assert.equal(background.style.opacity, '0');
assert.equal(background.getAttribute('src'), '/WWmm.png');
console.log('Image fallback checks passed: one attempt, no error loop, hidden background.');
