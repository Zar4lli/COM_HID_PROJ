# YOLO_TRAIN

## Overview

YOLO_TRAIN is a graphical interface for training YOLO models using the Ultralytics framework.

The application provides a convenient way to configure training parameters without manually constructing command-line arguments.

The GUI internally generates and executes Ultralytics training commands.

---

## Features

* Dataset selection through `data.yaml`
* Model selection (`.pt` or `.yaml`)
* CPU and CUDA support
* Training parameter configuration
* Optimizer selection
* Real-time training log
* Training interruption support
* Command preview generation

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

## Running

Start the training utility:

```bash
python YOLO_TRAIN/train.py
```

---

## Dataset Preparation

Training requires a valid YOLO dataset configuration file:

```text
data.yaml
```

Typical structure:

```text
dataset/
├── images/
│   ├── train/
│   └── val/
│
├── labels/
│   ├── train/
│   └── val/
│
└── data.yaml
```

Example:

```yaml
train: images/train
val: images/val

nc: 2

names:
  - Fish
  - Worm
```

---

## Training Parameters

### Dataset

Path to the dataset configuration file:

```text
data.yaml
```

---

### Model

Training can start from:

* Pretrained weights (`.pt`)
* Model architecture definition (`.yaml`)

Examples:

```text
yolov8n.pt
yolov8s.pt
custom_model.pt
```

---

### Device

Available devices:

```text
cpu
cuda:0
cuda:1
mps
```

The application automatically detects supported hardware.

---

### Epochs

Number of training epochs.

Example:

```text
50
100
300
```

---

### Image Size

Input image resolution.

Typical values:

```text
640
960
1280
```

---

### Batch Size

Training batch size.

The optimal value depends on available GPU memory.

---

### Optimizer

Supported optimizers:

```text
auto
SGD
Adam
AdamW
RMSProp
```

---

## Training Workflow

1. Prepare and annotate dataset.
2. Create `data.yaml`.
3. Launch the training utility.
4. Select dataset and model.
5. Configure training parameters.
6. Start training.
7. Monitor training progress in the log window.
8. Export trained weights.

---

## Output Files

Training results are stored inside the selected project directory.

Typical structure:

```text
runs/
└── train/
    └── exp/
        ├── weights/
        │   ├── best.pt
        │   └── last.pt
        ├── results.png
        └── results.csv
```

---

## Integration

The resulting model can be used by:

* COM_HID_CLIENT_PYTHON
* YOLO_DETECT

by selecting the generated `best.pt` file.

---

## Notes

Datasets are not included in this repository.

Custom trained models are not included in this repository.

Training performance depends on available hardware and dataset size.
