# COM_HID_CLIENT_PYTHON

## Overview

COM_HID_CLIENT_PYTHON is the main desktop client of the project.

The client connects to an Arduino HID device through a COM port and controls it using text commands. It also integrates YOLO object detection, macro execution and user scenario management.

The Arduino device performs low-level HID actions, while the Python client handles the high-level automation logic.

---

## Main Features

* COM port connection
* HID mouse and keyboard control
* Macro editor
* JSON scenario import and export
* User script queue
* YOLO model integration
* Screen object detection
* Detection-based cursor movement
* Hotkey support
* Execution log window

---

## Installation

Create a virtual environment in the repository root:

```bash
python -m venv .venv
```

Activate the environment:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Running

From the repository root:

```bash
python COM_HID_CLIENT_PYTHON/main.py
```

---

## Requirements

* Windows 10 / 11
* Python 3.11+
* Arduino HID device with uploaded COM_HID_DEVICE firmware
* Available COM port
* YOLO model file (`.pt`) for detection-based actions

---

## Basic Workflow

1. Connect the Arduino HID device to the PC.
2. Start the Python client.
3. Select the COM port.
4. Click **Connect**.
5. Check connection using **PING**.
6. Select a YOLO model if detection is required.
7. Configure macro steps.
8. Run the macro.

---

## Interface Sections

### Connection

Used to select and open the COM port.

Main controls:

* COM port selector
* Baudrate field
* Connect / Disconnect button
* PING button
* Log window
* Help window

Default baudrate:

```text
9600
```

---

### Macro Editor

The macro editor stores a list of actions that will be executed in order.

Each step contains:

* Command
* Delay after command
* Response waiting option

Supported operations:

* Add step
* Edit step
* Delete step
* Move step up
* Move step down
* Clear all steps
* Import JSON
* Export JSON

---

### YOLO Tab

Used to configure object detection.

Main settings:

* Model path
* Confidence threshold
* Monitor index
* Device selection
* Capture width
* Target class
* Detection action
* Detection region
* Offset from detected object center

Detection can be used to move the cursor or click on detected objects.

---

### Execution Tab

Used to run macros.

Main settings:

* Number of cycles
* Start button
* Stop button
* Hotkey configuration
* Quick command field
* Progress bar
* Execution status

---

### Cursor Tab

Used to create cursor-related commands.

Supported actions:

* Move cursor to absolute coordinates
* Left click
* Right click
* Hold mouse button
* Release mouse button

The current cursor position is displayed in real time.

---

## Command Types

The client supports two types of commands:

1. Device commands
2. Client-side commands

---

## Device Commands

Device commands are sent directly to the Arduino firmware.

Examples:

```text
PING
VERSION
RELEASE_ALL
KEY_DOWN CTRL
KEY_UP CTRL
KEY_PRESS ENTER
MOUSE_MOVE 10 -5
MOUSE_CLICK LEFT
MOUSE_PRESS LEFT
MOUSE_RELEASE LEFT
MOUSE_SCROLL -3
```

These commands are processed by COM_HID_DEVICE.

---

## Client-Side Commands

Client-side commands are processed by the Python application.

They may call YOLO detection, calculate cursor movement, and then send low-level commands to the Arduino device.

---

### MOVE_TO

Move the cursor to absolute screen coordinates.

```text
MOVE_TO 500 300
```

Unlike `MOUSE_MOVE`, this command uses absolute screen coordinates.

The client implements it by sending multiple relative `MOUSE_MOVE` commands to the device.

---

## YOLO Commands

### DETECT_LIST

Display currently detected objects in the log window.

```text
DETECT_LIST
```

With region:

```text
DETECT_LIST 100 100 900 700
```

---

### DETECT_MOVE

Find an object and move the cursor to the center of its bounding box.

```text
DETECT_MOVE Fish
```

With region:

```text
DETECT_MOVE Fish 100 100 900 700
```

---

### DETECT_CLICK

Find an object, move the cursor to it and perform a left click.

```text
DETECT_CLICK Fish
```

---

### DETECT_DOUBLE_CLICK

Find an object and perform a double click.

```text
DETECT_DOUBLE_CLICK Fish
```

---

### DETECT_NEAREST_CURSOR

Find the object closest to the current cursor position.

```text
DETECT_NEAREST_CURSOR Fish
```

---

### DETECT_NEAREST_SCREEN

Find the object closest to the center of the screen or selected region.

```text
DETECT_NEAREST_SCREEN Fish
```

---

### DETECT_MOVE_OFFSET

Find an object and move the cursor with an offset from the object center.

```text
DETECT_MOVE_OFFSET Fish 10 -5
```

---

### DETECT_CLICK_OFFSET

Find an object and click with an offset from the object center.

```text
DETECT_CLICK_OFFSET Fish 0 12
```

---

## Detection Region

Most YOLO commands support optional region filtering.

Format:

```text
X1 Y1 X2 Y2
```

Example:

```text
DETECT_CLICK Fish 100 100 900 700
```

The region works as a filter. The detector first searches the selected monitor, then the client keeps only objects whose center is inside the specified region.

---

## JSON Scenarios

Macro steps can be imported from and exported to JSON files.

A scenario contains:

* Macro steps
* Delay values
* Response waiting options
* YOLO settings
* Hotkey settings

User scenarios are not included in this repository.

---

## Script Queue

The client can load multiple JSON scenarios from a selected folder.

Queue options:

* Enable folder queue
* Automatically run next script
* Repeat folder for selected number of cycles

This is useful when several automation scenarios need to be executed one after another.

---

## Hotkeys

The client supports global hotkeys on Windows.

Hotkeys can be used to start or stop macro execution without focusing the application window.

Example:

```text
ALT+HOME
```

---

## Notes

Custom YOLO models are not included in this repository.

User scenarios are not included in this repository.

The project is intended as an automation framework. Specific models, datasets and scenarios should be created separately for each use case.

---

## Troubleshooting

### COM port is not available

Check that the device is connected and not used by another application.

Close Arduino Serial Monitor if it is open.

---

### YOLO model does not load

Check that the selected `.pt` file exists and is compatible with Ultralytics YOLO.

---

### Object class is not found

Use the **Model classes** button to display available class names.

The class name in the command must match one of the model classes.

---

### Cursor does not reach target position

The client moves the cursor using relative HID mouse movement.

If positioning is inaccurate, try disabling mouse acceleration in Windows.

---

### Hotkey does not work

Hotkeys are supported only on Windows.

Some combinations may be reserved by the operating system or another application.
