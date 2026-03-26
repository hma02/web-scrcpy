require('ts-node/register');
const assert = require('assert');
const MotionEvent = require('../MotionEvent').default;
const { resolveTouchPressure } = require('./touchPressure');

assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_DOWN), 1);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_MOVE), 1);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_MOVE, 0), 1);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_MOVE, 0.6), 0.6);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_MOVE, 2), 1);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_UP, 0.8), 0);
assert.strictEqual(resolveTouchPressure(MotionEvent.ACTION_UP, 0), 0);

console.log('touchPressure tests passed');
