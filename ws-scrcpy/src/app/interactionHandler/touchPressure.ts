import MotionEvent from '../MotionEvent';

export function resolveTouchPressure(action: number, force?: number): number {
    if (action === MotionEvent.ACTION_UP) {
        return 0;
    }

    if (typeof force === 'number' && Number.isFinite(force) && force > 0) {
        return Math.min(force, 1);
    }

    return 1;
}
