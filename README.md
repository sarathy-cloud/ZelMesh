# QRemeshify Standalone GUI

A standalone, lightweight Python GUI for **QRemeshify** (QuadWild / QuadPatches) that runs high-quality quad-remeshing **without needing Blender**. 

**Why a Standalone Version?** Normally, the QRemeshify extension runs inside Blender's internal Python environment. However, the heavy ILP solvers often cause Blender to hang or crash due to memory constraints, GIL contention, and threading issues. This standalone app built with [CustomTkinter](https://customtkinter.tomschimansky.com/) directly wraps the native C++ libraries using `ctypes` and runs in your **system Python environment**, making it vastly more stable and completely preventing Blender from hanging.

---

## ✨ Features
- **No Blender Required:** Runs entirely standalone as a desktop application.
- **Direct Library Access:** Calls `lib_quadwild` and `lib_quadpatches` directly for maximum performance and stability.
- **Advanced Parameter Control:** Exposes all advanced ILP quadrangulation settings (Time Limit, Gap Limit, Regulators, Weights, Isometry, etc.).
- **Quad Preservation:** Saves output directly to `.obj` to maintain genuine quad faces (unlike `.stl` which forcibly triangulates them).
- **Asynchronous Execution:** Runs the heavy remeshing pipeline in a background thread, keeping the GUI responsive and providing progress logs.

---

## ⚙️ Requirements & Installation

**⚠️ IMPORTANT: Do NOT download the source code from the `main` branch.** The raw source code on `main` does not contain the compiled C++ binaries. 

Instead, you must download the pre-packaged release ZIP for your specific Operating System.

### Step 1: Download the Release ZIP
Download the correct release file for your OS (e.g., `QRemeshify-1.1.0-windows.zip`, `...linux.zip`, or `...mac.zip`) from:
- [GitHub Releases](https://github.com/ksami/QRemeshify/releases)
- or [Gumroad](https://ksami.gumroad.com/l/QRemeshify)

### Step 2: Extract the Files
Extract the downloaded ZIP. Inside, you will find the `app.py` script alongside the pre-compiled native binaries (`lib_quadwild` and `lib_quadpatches`) already placed correctly in the `QRemeshify/lib/` folder.

Your extracted folder structure will look roughly like this:

```text
QRemeshify-1.1.0-windows/
├── app.py                      ← The main GUI script
├── QRemeshify/
│   └── lib/
│       ├── lib_quadwild.dll    ← Native binary (already included!)
│       ├── lib_quadpatches.dll ← Native binary (already included!)
│       └── config/             ← Required config folders
│           ├── main_config/
│           └── satsuma/
└── README.md
```

### Step 3: Install Python Dependencies
Ensure you have Python 3.8+ installed. Open a terminal or command prompt in the extracted folder and install the required Python packages:
```bash
pip install customtkinter trimesh scipy
```

---

## 🚀 Usage

Run the GUI via command line:
```bash
python app.py
```

### Pipeline Overview
When you click **Remesh**, the app runs the following pipeline behind the scenes:
1. **Conversion:** STL → Triangulated OBJ conversion (via `trimesh`).
2. **QuadWild:** Initial remeshing and cross-field calculation.
3. **QuadWild:** Patch tracing.
4. **QuadPatches:** Quadrangulation using the ILP solver.
5. **Output:** Saving the result as a quad-preserving `.obj` (or `.stl` if you choose).

### ⚠️ Output Format Warning
Always save your output as **`.obj`**. 
QuadWild produces genuine quad polygons. The `.stl` file format **does not support quads** and will split them all into triangles, completely defeating the purpose of quad-remeshing. 

---

## 🎛️ Settings & Tips

### Basic Settings
- **Preprocess:** Decimates, triangulates, and cleans up common geometry issues before the heavy processing begins. Recommended for raw scans.
- **Scale Factor:** Controls the target quad size. 
  - `< 1.0` = More detail, smaller quads.
  - `> 1.0` = Fewer, larger quads (Much faster to compute).
- **Symmetry (X/Y/Z):** If your model is perfectly symmetric, enabling this literally halves the computational work.
- **Detect Sharp:** Preserves hard edges based on the "Sharp Angle Threshold". Great for hard-surface models.

### Advanced Settings (ILP Solver)
The ILP (Integer Linear Programming) solver handles the most complex part of quadrangulation. 
- **Time Limit (s):** Caps how long the solver is allowed to run. If the remesher hangs forever on complex meshes, lower this limit.
- **ILP Method:** `LEASTSQUARES` is usually stable, but you can toggle this if the solver fails to converge.
- **Regularity Weights:** Adjusts how much the solver prioritizes perfectly square quads versus following the geometry flow.

### Handling Large Meshes
If the app seems to freeze or takes too long to solve:
1. Decimate your mesh to **under 100k triangles** before remeshing.
2. Increase the **Scale Factor** to generate fewer quads.
3. Reduce the **Time Limit** in Advanced Settings to cap the maximum time spent trying to find the perfect quad layout.

---

## 🤔 FAQ: Why not GPU / CUDA?

The ILP quadrangulation solver is fundamentally a sequential graph-optimization problem. Unlike rendering or deep learning, it **does not parallelize onto a GPU**. 

The main reason for building this standalone app was that running these heavy C++ solvers inside Blender's Python environment caused memory pressure, GIL (Global Interpreter Lock) contention, and frequent crashes. Running it entirely standalone in your system Python resolves those stability issues.

---

## 👏 Credits & Acknowledgements

All core algorithmic work and the original Blender extension were created by the original authors of **QRemeshify** (QuadWild and QuadPatches). 
- **QRemeshify Extension:** [ksami](https://github.com/ksami)
- **QuadWild / QuadPatches Algorithms:** The respective academic authors and researchers behind the original C++ implementations.

This GUI is simply a standalone wrapper to improve stability by running the solvers in system Python instead of Blender.
