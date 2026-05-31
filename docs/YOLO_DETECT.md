# YOLO_DETECT

## Overview

YOLO_DETECT is a collection of utilities for testing, debugging and validating YOLO object detection models.

The tools included in this directory were developed to simplify model verification before integration into the main automation system.

Unlike COM_HID_CLIENT_PYTHON, these utilities do not control HID devices and are intended only for model development, visualization and diagnostics.

---

## Features

* Real-time screen detection
* Detection overlay rendering
* Confidence threshold adjustment
* Multi-monitor support
* CPU and CUDA execution
* Detection smoothing
* Detection screenshot saving
* Single image testing
* Model validation

---

## Installation

Create a virtual environment in the repository root:

```bash
python -m venv .venv
```

Activate environment:

### Windows

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Available Utilities

### screen_yolo_overlay.py

Real-time object detection from a selected monitor.

Displays bounding boxes directly on the screen using a transparent overlay window.

Main capabilities:

* Live screen capture
* YOLO inference
* Bounding box visualization
* Confidence display
* Detection screenshots
* Global stop hotkey

This version represents the original implementation.

---

### screen_yolo_overlay_v2.py

Improved overlay implementation.

Additional functionality:

* Detection smoothing
* IoU-based object matching
* Device selection
* Overlay refresh control
* Improved performance

Recommended version for regular use.

Run:

```bash
python YOLO_DETECT/screen_yolo_overlay_v2.py
```

---

### yolo_detect_from_img.py

Utility for testing YOLO models on individual images.

Features:

* Load custom model
* Open image file
* Configure confidence threshold
* Display detections
* Export processed image

Run:

```bash
python YOLO_DETECT/yolo_detect_from_img.py
```

---

## Configuration

Overlay applications automatically load settings from:

```text
yolo_screen_gui_config.json
```

Stored settings include:

* Model path
* Confidence threshold
* Monitor selection
* Device configuration
* Overlay options
* Screenshot settings
* Stop hotkey

Configuration is automatically updated when changed through the user interface.

---

## Typical Workflow

1. Train or obtain a YOLO model.
2. Open `screen_yolo_overlay_v2.py`.
3. Load the model.
4. Verify detections on the target application.
5. Adjust confidence threshold if required.
6. Validate class names and bounding boxes.
7. Integrate the model into COM_HID_CLIENT_PYTHON.

---

## Notes

Custom YOLO models are not included in this repository.

Training datasets are not included in this repository.

The examples included in the repository use generic YOLO models only for demonstration purposes.

The primary purpose of this directory is model validation and debugging before deployment.
