# COM_HID_DEVICE

## Overview

COM_HID_DEVICE is Arduino firmware that acts as a USB HID bridge.

The device receives commands through a serial connection and emulates:

* Keyboard input
* Mouse movement
* Mouse buttons
* Mouse wheel scrolling
* Hotkeys

The firmware is intended to be used together with COM_HID_CLIENT_PYTHON.

---

## Supported Boards

This firmware requires an Arduino board with native USB HID support.

Examples:

* Arduino Leonardo
* Arduino Micro
* Arduino Pro Micro (ATmega32U4)

Standard Arduino Uno and Nano boards are not supported because they cannot emulate USB HID devices using the standard Keyboard and Mouse libraries.

---

## Required Libraries

The firmware uses Arduino built-in libraries:

```cpp
#include <Keyboard.h>
#include <Mouse.h>
```

These libraries are included with the Arduino IDE for supported boards and normally do not require separate installation.

---

## Installation

1. Install Arduino IDE.
2. Open:

```text
COM_HID_DEVICE/code_v3.ino
```

3. Select your board.
4. Select the correct COM port.
5. Compile and upload the firmware.

---

## Serial Configuration

Default serial settings:

```text
Baudrate: 9600
```

The firmware identifies itself as:

```text
HID_BRIDGE 2.1
```

---

## Connection Test

Verify communication:

```text
PING
```

Expected response:

```text
PONG
```

Check firmware version:

```text
VERSION
```

Example response:

```text
HID_BRIDGE 2.1
```

---

## Keyboard Commands

Press and hold a key:

```text
KEY_DOWN CTRL
```

Release a key:

```text
KEY_UP CTRL
```

Press and release a key:

```text
KEY_PRESS ENTER
```

Send a keyboard shortcut:

```text
HOTKEY CTRL C
```

Type text:

```text
TYPE_TEXT Hello World
```

Release all currently pressed keys:

```text
RELEASE_ALL
```

---

## Mouse Commands

Move mouse relative to current position:

```text
MOUSE_MOVE 10 -5
```

Left click:

```text
MOUSE_CLICK LEFT
```

Right click:

```text
MOUSE_CLICK RIGHT
```

Hold button:

```text
MOUSE_PRESS LEFT
```

Release button:

```text
MOUSE_RELEASE LEFT
```

Scroll wheel:

```text
MOUSE_SCROLL -3
```

---

## Responses

Successful command:

```text
OK
```

Error examples:

```text
ERROR BAD_ARGS
ERROR BAD_KEY
ERROR BAD_BUTTON
ERROR UNKNOWN_COMMAND
```

---

## Integration

The firmware is designed to work together with:

* COM_HID_CLIENT_PYTHON
* Macro execution system
* YOLO-assisted automation workflows

The Python client sends serial commands while the Arduino performs the actual HID actions on the host computer.

---

## Notes

This firmware intentionally performs only low-level HID operations.

High-level automation logic, object detection and macro execution are implemented in COM_HID_CLIENT_PYTHON.
