function classifySwipe(startPoint, endPoint, threshold = 12) {
    const deltaX = endPoint.x - startPoint.x;
    const deltaY = endPoint.y - startPoint.y;
    const absX = Math.abs(deltaX);
    const absY = Math.abs(deltaY);
    const distance = Math.hypot(deltaX, deltaY);
    const isSwipe = distance >= threshold;
    let direction = 'tap';
    if (isSwipe) {
        if (absY >= absX) {
            direction = deltaY < 0 ? 'up' : 'down';
        } else {
            direction = deltaX < 0 ? 'left' : 'right';
        }
    }
    return { isSwipe, direction, deltaX, deltaY, distance };
}

function interpolateSwipePoints(startPoint, endPoint, segments = 8) {
    const points = [];
    const count = Math.max(2, segments);
    for (let i = 1; i < count; i++) {
        const ratio = i / count;
        points.push({
            x: startPoint.x + (endPoint.x - startPoint.x) * ratio,
            y: startPoint.y + (endPoint.y - startPoint.y) * ratio,
        });
    }
    return points;
}

class ScrcpyInput {
    constructor(callback, videoElement, width, height, debug = false) {
        this.callback = callback
        this.width = width
        this.height = height
        this.debug = debug
        let mouseX = null;
        let mouseY = null;
        let leftButtonIsPressed = false;
        let rightButtonIsPressed = false;
        let ignoreMouseEventsUntil = 0;
        let touchActive = false;
        let touchHasMove = false;
        let touchStart = null;
        let touchCurrent = null;

        videoElement.style.touchAction = 'none';

        const mapClientPointToDevicePoint = (clientX, clientY) => {
            const rect = videoElement.getBoundingClientRect();
            const relativeX = clientX - rect.left;
            const relativeY = clientY - rect.top;
            const normalizedX = Math.max(0, Math.min(rect.width, relativeX));
            const normalizedY = Math.max(0, Math.min(rect.height, relativeY));
            return {
                x: (normalizedX / rect.width) * this.width,
                y: (normalizedY / rect.height) * this.height,
            };
        };

        document.addEventListener('mousedown', (event) => {
            if (Date.now() < ignoreMouseEventsUntil) {
                return;
            }
            const rect = videoElement.getBoundingClientRect();
            const local_x = event.clientX - rect.left;
            const local_y = event.clientY - rect.top;

            if (videoElement.contains(event.target)) {
                if (event.button === 0) {
                    leftButtonIsPressed = true;

                    mouseX = (local_x / (rect.right - rect.left)) * this.width;
                    mouseY = (local_y / (rect.bottom - rect.top)) * this.height;

                    let data = this.createTouchProtocolData(0, mouseX, mouseY, this.width, this.height, 0, 0, 65535);
                    this.callback(data);
                } else if (event.button === 2) {
                    rightButtonIsPressed = true;

                    this.snedKeyCode(event, 0, 4);
                    event.preventDefault();
                }
            }
        });

        document.addEventListener('mouseup', (event) => {
            if (Date.now() < ignoreMouseEventsUntil) {
                return;
            }
            if (!leftButtonIsPressed) return;

            const rect = videoElement.getBoundingClientRect();
            const local_x = event.clientX - rect.left;
            const local_y = event.clientY - rect.top;

            if (event.button === 0) {
                leftButtonIsPressed = false;

                if (videoElement.contains(event.target)) {
                    mouseX = (local_x / (rect.right - rect.left)) * this.width;
                    mouseY = (local_y / (rect.bottom - rect.top)) * this.height;
                }
    
                let data = this.createTouchProtocolData(1, mouseX, mouseY, this.width, this.height, 0, 0, 0);
                this.callback(data);

            } else if (event.button === 2 && rightButtonIsPressed) {
                rightButtonIsPressed = false;

                this.snedKeyCode(event, 1, 4);
                event.preventDefault();
            }
        });

        document.addEventListener('mousemove', (event) => {
            if (Date.now() < ignoreMouseEventsUntil) {
                return;
            }
            if (!leftButtonIsPressed) return;

            const rect = videoElement.getBoundingClientRect();
            const local_x = event.clientX - rect.left;
            const local_y = event.clientY - rect.top;

            if (videoElement.contains(event.target)) {
                mouseX = (local_x / (rect.right - rect.left)) * this.width;
                mouseY = (local_y / (rect.bottom - rect.top)) * this.height;

                let data = this.createTouchProtocolData(2, mouseX, mouseY, this.width, this.height, 0, 0, 65535);
                this.callback(data);
            }
        });

        videoElement.addEventListener('touchstart', (event) => {
            if (!event.changedTouches || event.changedTouches.length === 0) return;
            const touch = event.changedTouches[0];
            const point = mapClientPointToDevicePoint(touch.clientX, touch.clientY);
            touchActive = true;
            touchHasMove = false;
            touchStart = point;
            touchCurrent = point;
            ignoreMouseEventsUntil = Date.now() + 700;
            const data = this.createTouchProtocolData(0, point.x, point.y, this.width, this.height, 0, 0, 65535);
            this.callback(data);
            event.preventDefault();
        }, { passive: false });

        videoElement.addEventListener('touchmove', (event) => {
            if (!touchActive || !event.changedTouches || event.changedTouches.length === 0) return;
            const touch = event.changedTouches[0];
            const point = mapClientPointToDevicePoint(touch.clientX, touch.clientY);
            touchCurrent = point;
            touchHasMove = true;
            const data = this.createTouchProtocolData(2, point.x, point.y, this.width, this.height, 0, 0, 65535);
            this.callback(data);
            event.preventDefault();
        }, { passive: false });

        videoElement.addEventListener('touchend', (event) => {
            if (!touchActive || !touchStart) return;
            const changedTouch = event.changedTouches && event.changedTouches.length > 0 ? event.changedTouches[0] : null;
            const endPoint = changedTouch
                ? mapClientPointToDevicePoint(changedTouch.clientX, changedTouch.clientY)
                : touchCurrent || touchStart;
            const swipe = classifySwipe(touchStart, endPoint);
            if (!touchHasMove && swipe.isSwipe) {
                const path = interpolateSwipePoints(touchStart, endPoint);
                path.forEach((point) => {
                    const moveData = this.createTouchProtocolData(2, point.x, point.y, this.width, this.height, 0, 0, 65535);
                    this.callback(moveData);
                });
            }
            const upData = this.createTouchProtocolData(1, endPoint.x, endPoint.y, this.width, this.height, 0, 0, 0);
            this.callback(upData);
            touchActive = false;
            touchHasMove = false;
            touchStart = null;
            touchCurrent = null;
            ignoreMouseEventsUntil = Date.now() + 700;
            event.preventDefault();
        }, { passive: false });

        videoElement.addEventListener('touchcancel', (event) => {
            if (!touchActive) return;
            const endPoint = touchCurrent || touchStart;
            if (endPoint) {
                const upData = this.createTouchProtocolData(1, endPoint.x, endPoint.y, this.width, this.height, 0, 0, 0);
                this.callback(upData);
            }
            touchActive = false;
            touchHasMove = false;
            touchStart = null;
            touchCurrent = null;
            ignoreMouseEventsUntil = Date.now() + 700;
            event.preventDefault();
        }, { passive: false });

        videoElement.addEventListener('contextmenu', (event) => {
            event.preventDefault();
        });

        videoElement.addEventListener('wheel', (event) => {
            const hScroll = event.deltaX;
            const vScroll = event.deltaY;
            const deltaMode = event.deltaMode;
            const deltaZ = event.deltaZ;
            const clientX = event.clientX;
            const clientY = event.clientY;
            const button = event.button;

            const rect = videoElement.getBoundingClientRect();
            const relativeX = clientX - rect.left;
            const relativeY = clientY - rect.top;
            const width = rect.right - rect.left;
            const height = rect.bottom - rect.top;

            // switch (deltaMode) {
            //     case WheelEvent.DOM_DELTA_PIXEL:
            //         deltaModeValue.textContent = 'pixel';
            //         break;
            //     case WheelEvent.DOM_DELTA_LINE:
            //         deltaModeValue.textContent = 'row';
            //         break;
            //     case WheelEvent.DOM_DELTA_PAGE:
            //         deltaModeValue.textContent = 'page';
            //         break;
            //     default:
            //         deltaModeValue.textContent = 'unknown';
            // }
            let data = this.createScrollProtocolData(relativeX, relativeY, width, height, hScroll, vScroll, button);
            this.callback(data);
        });

        videoElement.addEventListener('keydown', async (event) => {
            const androidKeyCode = this.mapToAndroidKeyCode(event);
            if (androidKeyCode !== null) {
                this.snedKeyCode(event, 0, androidKeyCode)
            } else {
                console.log(`key: ${event.code}, not mapped to android key code`);
            }

            if (event.ctrlKey && event.key === 'v') {
                try {
                    const clipboardData = await navigator.clipboard.readText();
                } catch (err) {
                    console.error('Failed to read clipboard contents: ', err);
                }
            }
        });

        videoElement.addEventListener('keyup', async (event) => {
            const androidKeyCode = this.mapToAndroidKeyCode(event);
            if (androidKeyCode !== null) {
                this.snedKeyCode(event, 1, androidKeyCode)
            } else {
                console.log(`key: ${event.code}, not mapped to android key code`);
            }
        });
    }

    resizeScreen(width, height) {
        this.width = width;
        this.height = height;
    }

    mapToAndroidKeyCode(event) {
        const codeToAndroidKeyCode = {
            'KeyA': 29,  // KEYCODE_A
            'KeyB': 30,  // KEYCODE_B
            'KeyC': 31,  // KEYCODE_C
            'KeyD': 32,  // KEYCODE_D
            'KeyE': 33,  // KEYCODE_E
            'KeyF': 34,  // KEYCODE_F
            'KeyG': 35,  // KEYCODE_G
            'KeyH': 36,  // KEYCODE_H
            'KeyI': 37,  // KEYCODE_I
            'KeyJ': 38,  // KEYCODE_J
            'KeyK': 39,  // KEYCODE_K
            'KeyL': 40,  // KEYCODE_L
            'KeyM': 41,  // KEYCODE_M
            'KeyN': 42,  // KEYCODE_N
            'KeyO': 43,  // KEYCODE_O
            'KeyP': 44,  // KEYCODE_P
            'KeyQ': 45,  // KEYCODE_Q
            'KeyR': 46,  // KEYCODE_R
            'KeyS': 47,  // KEYCODE_S
            'KeyT': 48,  // KEYCODE_T
            'KeyU': 49,  // KEYCODE_U
            'KeyV': 50,  // KEYCODE_V
            'KeyW': 51,  // KEYCODE_W
            'KeyX': 52,  // KEYCODE_X
            'KeyY': 53,  // KEYCODE_Y
            'KeyZ': 54,  // KEYCODE_Z

            'Digit0': 7,   // KEYCODE_0
            'Digit1': 8,   // KEYCODE_1
            'Digit2': 9,   // KEYCODE_2
            'Digit3': 10,  // KEYCODE_3
            'Digit4': 11,  // KEYCODE_4
            'Digit5': 12,  // KEYCODE_5
            'Digit6': 13,  // KEYCODE_6
            'Digit7': 14,  // KEYCODE_7
            'Digit8': 15,  // KEYCODE_8
            'Digit9': 16,  // KEYCODE_9

            'Enter': 66,       // KEYCODE_ENTER
            'Backspace': 67,   // KEYCODE_DEL
            'Tab': 61,         // KEYCODE_TAB
            'Space': 62,       // KEYCODE_SPACE
            'Escape': 111,     // KEYCODE_ESCAPE
            'CapsLock': 115,   // KEYCODE_CAPS_LOCK
            'NumLock': 143,    // KEYCODE_NUM_LOCK
            'ScrollLock': 116, // KEYCODE_SCROLL_LOCK

            'ArrowUp': 19,     // KEYCODE_DPAD_UP
            'ArrowDown': 20,   // KEYCODE_DPAD_DOWN
            'ArrowLeft': 21,   // KEYCODE_DPAD_LEFT
            'ArrowRight': 22,  // KEYCODE_DPAD_RIGHT

            'ShiftLeft': 59,   // KEYCODE_SHIFT_LEFT
            'ShiftRight': 60,  // KEYCODE_SHIFT_RIGHT
            'ControlLeft': 113,// KEYCODE_CTRL_LEFT
            'ControlRight': 114,// KEYCODE_CTRL_RIGHT
            'AltLeft': 57,     // KEYCODE_ALT_LEFT
            'AltRight': 58,    // KEYCODE_ALT_RIGHT
            'MetaLeft': 117,   // KEYCODE_META_LEFT
            'MetaRight': 118,  // KEYCODE_META_RIGHT

            'Numpad0': 144,    // KEYCODE_NUMPAD_0
            'Numpad1': 145,    // KEYCODE_NUMPAD_1
            'Numpad2': 146,    // KEYCODE_NUMPAD_2
            'Numpad3': 147,    // KEYCODE_NUMPAD_3
            'Numpad4': 148,    // KEYCODE_NUMPAD_4
            'Numpad5': 149,    // KEYCODE_NUMPAD_5
            'Numpad6': 150,    // KEYCODE_NUMPAD_6
            'Numpad7': 151,    // KEYCODE_NUMPAD_7
            'Numpad8': 152,    // KEYCODE_NUMPAD_8
            'Numpad9': 153,    // KEYCODE_NUMPAD_9
            'NumpadEnter': 160,// KEYCODE_NUMPAD_ENTER
            'NumpadAdd': 157,  // KEYCODE_NUMPAD_ADD
            'NumpadSubtract': 156, // KEYCODE_NUMPAD_SUBTRACT
            'NumpadMultiply': 155, // KEYCODE_NUMPAD_MULTIPLY
            'NumpadDivide': 154,   // KEYCODE_NUMPAD_DIVIDE

            'F1': 131,  // KEYCODE_F1
            'F2': 132,  // KEYCODE_F2
            'F3': 133,  // KEYCODE_F3
            'F4': 134,  // KEYCODE_F4
            'F5': 135,  // KEYCODE_F5
            'F6': 136,  // KEYCODE_F6
            'F7': 137,  // KEYCODE_F7
            'F8': 138,  // KEYCODE_F8
            'F9': 139,  // KEYCODE_F9
            'F10': 140, // KEYCODE_F10
            'F11': 141, // KEYCODE_F11
            'F12': 142, // KEYCODE_F12

            'Back': 4,    // KEYCODE_BACK
            'Home': 3,    // KEYCODE_HOME
            'Menu': 82,   // KEYCODE_MENU
        };

        const androidKeyCode = codeToAndroidKeyCode[event.code];
        return androidKeyCode !== undefined ? androidKeyCode : null;
    }

    snedKeyCode(keyevent, action, keycode) {
        const capsLockState = keyevent.getModifierState('CapsLock');
        const numLockState = keyevent.getModifierState('NumLock');
        const scrollLockState = keyevent.getModifierState('ScrollLock');

        let metakey = 0;
        if (keyevent.shiftKey) {
            metakey |= 0x40;
        }
        if (keyevent.ctrlKey) {
            metakey |= 0x2000;
        }
        if (keyevent.altKey) {
            metakey |= 0x10;
        }
        if (keyevent.metaKey) {
            metakey |= 0x20000;
        }
        if (capsLockState) {
            metakey |= 0x100000;
        }
        if (numLockState) {
            metakey |= 0x200000;
        }
        // if(scrollLockState)
        // {
        //     metakey |= 0x400000;
        // }
        let data = this.createKeyProtocolData(action, keycode, keyevent.repeat, metakey);
        this.callback(data);
    }

    createTouchProtocolData(action, x, y, width, height, actionButton, buttons, pressure) {
        const type = 2; // touch event

        const buffer = new ArrayBuffer(1 + 1 + 8 + 4 + 4 + 2 + 2 + 2 + 4 + 4);
        const view = new DataView(buffer);

        let offset = 0;

        view.setUint8(offset, type);
        offset += 1;

        view.setUint8(offset, action);
        offset += 1;

        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xff);
        offset += 1;
        view.setUint8(offset, 0xfd);
        offset += 1;

        view.setInt32(offset, x, false);
        offset += 4;
        view.setInt32(offset, y, false);
        offset += 4;
        view.setUint16(offset, width, false);
        offset += 2;
        view.setUint16(offset, height, false);
        offset += 2;

        view.setInt16(offset, pressure, false);
        offset += 2;

        view.setInt32(offset, actionButton, false);
        offset += 4;

        view.setInt32(offset, buttons, false);

        return buffer;
    }

    createKeyProtocolData(action, keycode, repeat, metaState) {
        const type = 0; // key event

        const buffer = new ArrayBuffer(1 + 1 + 4 + 4 + 4);
        const view = new DataView(buffer);

        let offset = 0;

        view.setUint8(offset, type);
        offset += 1;

        view.setUint8(offset, action);
        offset += 1;

        view.setInt32(offset, keycode, false);
        offset += 4;
        view.setInt32(offset, repeat, false);
        offset += 4;
        view.setInt32(offset, metaState, false);

        return buffer;
    }

    createScrollProtocolData(x, y, width, height, hScroll, vScroll, button) {
        const type = 3; // scroll event

        const buffer = new ArrayBuffer(1 + 4 + 4 + 2 + 2 + 2 + 2 + 4);
        const view = new DataView(buffer);

        let offset = 0;
        view.setUint8(offset, type);
        offset += 1;

        view.setInt32(offset, x, false);
        offset += 4;
        view.setInt32(offset, y, false);
        offset += 4;
        view.setUint16(offset, width, false);
        offset += 2;
        view.setUint16(offset, height, false);
        offset += 2;

        view.setInt16(offset, hScroll, false);
        offset += 2;
        view.setInt16(offset, vScroll, false);
        offset += 2;

        view.setInt32(offset, button, false);

        return buffer;
    }

    createScreenProtocolData(action) {
        const type = 4; // Screen off/on event

        const buffer = new ArrayBuffer(1 + 1);
        const view = new DataView(buffer);

        let offset = 0;
        view.setUint8(offset, type);
        offset += 1;

        view.setUint8(offset, action);

        return buffer;
    }

    createPowerProtocolData(action) {
        const type = 7; // Screen Power off/on event

        const buffer = new ArrayBuffer(1 + 1);
        const view = new DataView(buffer);

        let offset = 0;
        view.setUint8(offset, type);
        offset += 1;

        view.setUint8(offset, action);

        return buffer;
    }

    createSetScreenPowerModeProtocolData(screenPowerOn) {
        const type = 10; // TYPE_SET_SCREEN_POWER_MODE

        const buffer = new ArrayBuffer(1 + 1);
        const view = new DataView(buffer);
        let offset = 0;
        view.setUint8(offset, type);
        offset += 1;
        view.setUint8(offset, screenPowerOn ? 1 : 0);
        return buffer;
    }

    createTextControlMessage(text) {
        const type = 1; // TYPE_TEXT
        const encoder = new TextEncoder();
        const textBytes = encoder.encode(text || '');
        const buffer = new ArrayBuffer(1 + 4 + textBytes.length);
        const view = new DataView(buffer);
        view.setUint8(0, type);
        view.setInt32(1, textBytes.length, false);
        new Uint8Array(buffer, 5).set(textBytes);
        return buffer;
    }

    createGetClipboardControlMessage() {
        const type = 8; // TYPE_GET_CLIPBOARD
        const buffer = new ArrayBuffer(1);
        const view = new DataView(buffer);
        view.setUint8(0, type);
        return buffer;
    }

    createSetClipboardControlMessage(text, paste = false) {
        const type = 9; // TYPE_SET_CLIPBOARD
        const encoder = new TextEncoder();
        const textBytes = encoder.encode(text || '');
        const buffer = new ArrayBuffer(1 + 1 + 4 + textBytes.length);
        const view = new DataView(buffer);
        view.setUint8(0, type);
        view.setUint8(1, paste ? 1 : 0);
        view.setInt32(2, textBytes.length, false);
        new Uint8Array(buffer, 6).set(textBytes);
        return buffer;
    }

    add_debug_item(text) {
        const p = document.createElement('p');
        p.textContent = text;
        const span = document.createElement('span');
        span.textContent = '0';
        p.appendChild(span);
        document.body.appendChild(p);
        return span;
    }

    screen_on_off(action) {
        let data = null;
        data = this.createScreenProtocolData(action);
        this.callback(data)
    }

    set_screen_power_mode(screenPowerOn) {
        const data = this.createSetScreenPowerModeProtocolData(screenPowerOn);
        this.callback(data);
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        ScrcpyInput,
        classifySwipe,
        interpolateSwipePoints,
    };
}
