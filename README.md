# ZelMesh Standalone GUI

ksami built the QRemeshify Blender extension, which wraps the QuadWild and QuadPatches algorithms from the original academic researchers into something usable inside Blender. It's genuinely good work. This app is just a wrapper around that same pipeline — the credit for anything that actually matters belongs to them.

So — if you've been using that extension and Blender keeps hanging, freezing, or dying mid-remesh, that's exactly why this exists.

### Why not just use the Blender extension?
The extension works fine for simple meshes, but the ILP solver it uses is a heavy C++ process. When you run that inside Blender's Python environment, you're fighting against Blender's memory management, the GIL, and threading constraints all at once. On anything moderately complex, Blender just gives up.

Running it standalone in your system Python sidesteps all of that. Same algorithm, same output quality — just actually stable.

---

## ⚠️ Before you download
**Don't clone the repo.** The source code on main doesn't include the compiled C++ binaries, so it won't run. You need to grab the pre-packaged release ZIP for your OS from GitHub Releases or Gumroad.

---

## 🚀 Getting started

### 1. Download the right ZIP for your OS
Look for something like `QRemeshify-1.1.0-windows.zip` (or `-linux`, `-mac`).

### 2. Extract it
The folder structure inside will look like this:
```text
QRemeshify-1.1.0-windows/
├── app.py
├── QRemeshify/
│   └── lib/
│       ├── lib_quadwild.dll
│       ├── lib_quadpatches.dll
│       └── config/
│           ├── main_config/
│           └── satsuma/
└── README.md
```
The `.dll` files (or `.so` on Linux) are already there — you don't need to build anything.

### 3. Install the Python dependencies
You'll need Python 3.8 or newer. Then, in the extracted folder:
```bash
pip install customtkinter trimesh scipy
```

### 4. Run it
```bash
python app.py
```

---

## ⚙️ What happens when you hit Remesh
The app runs through a pipeline in the background so the UI stays responsive:
1. Converts your STL to a triangulated OBJ
2. Runs QuadWild for cross-field calculation
3. Runs QuadWild again for patch tracing
4. Hands off to QuadPatches for the actual ILP-based quadrangulation
5. Saves the result

> **Save as `.obj`, not `.stl`.** The STL format doesn't support quad faces — it'll split every quad into two triangles, which completely defeats the point. The default output is `.obj` for exactly this reason.

---

## 🎛️ Settings worth knowing about
- **Scale Factor** — controls how big your quads are. Below 1.0 gives you more detail and smaller quads; above 1.0 gives you bigger, coarser quads that compute much faster. If you're just testing, start with something like 1.5.
- **Preprocess** — decimates and cleans up your mesh before processing. Leave this on if you're working with raw scans or messy geometry.
- **Symmetry (X/Y/Z)** — if your model is actually symmetric, enabling the right axis cuts the solver work roughly in half.
- **Detect Sharp** — preserves hard edges. Great for mechanical or hard-surface models.
- **Time Limit (Advanced)** — the ILP solver can run a very long time on complex meshes. This caps it. If your remesh is hanging for 10+ minutes, this is the setting to lower.

---

The ILP solver is fundamentally sequential — it's a graph optimization problem, not something you can throw GPU cores at. This isn't a bug, it's just the nature of the algorithm.

---

## 🔮 Future Architecture
Future versions of ZelMesh will transition away from acting as a simple wrapper. The long-term goal is to use the core QuadWild and QuadPatches binaries as the engine for a fully separate, standalone application with its own native architecture and dedicated workflows.
