const assert = require('assert');
const { classifySwipe, interpolateSwipePoints } = require('../static/js/input.js');

(() => {
    const swipeUp = classifySwipe({ x: 50, y: 200 }, { x: 48, y: 120 }, 12);
    assert.strictEqual(swipeUp.isSwipe, true);
    assert.strictEqual(swipeUp.direction, 'up');

    const swipeRight = classifySwipe({ x: 20, y: 20 }, { x: 120, y: 24 }, 12);
    assert.strictEqual(swipeRight.direction, 'right');

    const tap = classifySwipe({ x: 10, y: 10 }, { x: 13, y: 14 }, 12);
    assert.strictEqual(tap.isSwipe, false);
    assert.strictEqual(tap.direction, 'tap');

    const points = interpolateSwipePoints({ x: 0, y: 0 }, { x: 100, y: 0 }, 5);
    assert.strictEqual(points.length, 4);
    assert.ok(points[0].x > 0 && points[0].x < 100);
    assert.ok(points[3].x > points[0].x);
})();

console.log('input swipe helper tests passed');
