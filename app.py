import os
import math
import shutil
import tempfile
import threading
import traceback
import platform
from pathlib import Path
from ctypes import *

import customtkinter as ctk
from tkinter import filedialog, messagebox

# ── Resolve lib directory ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()

def _find_lib_dir() -> Path:
    candidates = [
        SCRIPT_DIR / "QRemeshify" / "lib",
        SCRIPT_DIR / "QRemeshify-main" / "QRemeshify" / "lib",
        SCRIPT_DIR.parent / "QRemeshify" / "lib",
        SCRIPT_DIR.parent / "QRemeshify-main" / "QRemeshify" / "lib",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return SCRIPT_DIR / "QRemeshify" / "lib"

LIB_DIR = _find_lib_dir()

# ── ctypes structs ────────────────────────────────────────────────────────────

class Parameters(Structure):
    _fields_ = [
        ('remesh',      c_bool),
        ('sharpAngle',  c_float),
        ('alpha',       c_float),
        ('scaleFact',   c_float),
        ('hasFeature',  c_bool),
        ('hasField',    c_bool),
    ]

class QRParameters(Structure):
    _fields_ = [
        ("useFlowSolver",                        c_bool),
        ("flow_config_filename",                 c_char_p),
        ("satsuma_config_filename",              c_char_p),
        ("initialRemeshing",                     c_bool),
        ("initialRemeshingEdgeFactor",           c_double),
        ("reproject",                            c_bool),
        ("splitConcaves",                        c_bool),
        ("finalSmoothing",                       c_bool),
        ("ilpMethod",                            c_int),
        ("alpha",                                c_double),
        ("isometry",                             c_bool),
        ("regularityQuadrilaterals",             c_bool),
        ("regularityNonQuadrilaterals",          c_bool),
        ("regularityNonQuadrilateralsWeight",    c_double),
        ("alignSingularities",                   c_bool),
        ("alignSingularitiesWeight",             c_double),
        ("repeatLosingConstraintsIterations",    c_bool),
        ("repeatLosingConstraintsQuads",         c_bool),
        ("repeatLosingConstraintsNonQuads",      c_bool),
        ("repeatLosingConstraintsAlign",         c_bool),
        ("feasibilityFix",                       c_bool),
        ("hardParityConstraint",                 c_bool),
        ("timeLimit",                            c_double),
        ("gapLimit",                             c_double),
        ("minimumGap",                           c_double),
        ("callbackTimeLimit",                    POINTER(c_float)),
        ("callbackGapLimit",                     POINTER(c_float)),
        ("chartSmoothingIterations",             c_int),
        ("quadrangulationFixedSmoothingIterations",    c_int),
        ("quadrangulationNonFixedSmoothingIterations", c_int),
        ("doubletRemoval",                       c_bool),
        ("resultSmoothingIterations",            c_int),
        ("resultSmoothingNRing",                 c_double),
        ("resultSmoothingLaplacianIterations",   c_int),
        ("resultSmoothingLaplacianNRing",        c_double),
    ]

ILP_METHODS = {"LEASTSQUARES": 1, "ABS": 2}

FLOW_CONFIGS = {
    "SIMPLE": "config/main_config/flow_virtual_simple.json",
    "HALF":   "config/main_config/flow_virtual_half.json",
}

SATSUMA_CONFIGS = {
    "DEFAULT":    "config/satsuma/default.json",
    "MST":        "config/satsuma/approx-mst.json",
    "ROUND2EVEN": "config/satsuma/approx-round2even.json",
    "SYMMDC":     "config/satsuma/approx-symmdc.json",
    "EDGETHRU":   "config/satsuma/edgethru.json",
    "LEMON":      "config/satsuma/lemon.json",
    "NODETHRU":   "config/satsuma/nodethru.json",
}

# ── STL → OBJ (triangulated, for QuadWild input) ─────────────────────────────

def stl_to_obj(stl_path: str, obj_path: str, sharp_path: str,
               enable_sharp: bool, sharp_angle_deg: float) -> None:
    """Convert STL → triangulated OBJ. STL has no quad faces so this is fine."""
    import trimesh
    mesh = trimesh.load(stl_path, force="mesh", process=True)
    verts  = mesh.vertices
    faces  = mesh.faces
    fnorms = mesh.face_normals

    lines = ["# OBJ file converted from STL"]
    for v in verts:
        lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    for n in fnorms:
        lines.append(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}")
    for fi, f in enumerate(faces):
        ni = fi + 1
        vs = " ".join(f"{v+1}//{ni}" for v in f)
        lines.append(f"f {vs}")

    with open(obj_path, "w") as fp:
        fp.write("\n".join(lines) + "\n")

    if enable_sharp and sharp_path:
        _write_sharp_features(faces, fnorms, sharp_angle_deg, sharp_path)


def _write_sharp_features(faces, fnorms, sharp_angle_deg: float, sharp_path: str) -> int:
    import numpy as np
    from collections import defaultdict

    thresh_rad = math.radians(sharp_angle_deg)
    edge_faces = defaultdict(list)
    for fi, face in enumerate(faces):
        for k in range(3):
            e = tuple(sorted((int(face[k]), int(face[(k+1) % 3]))))
            edge_faces[e].append(fi)

    sharp_edges_out = []
    for e, fids in edge_faces.items():
        if len(fids) == 1:
            fi = fids[0]
            face = faces[fi]
            for ei in range(3):
                a, b = int(face[ei]), int(face[(ei+1) % 3])
                if tuple(sorted((a, b))) == e:
                    sharp_edges_out.append(f"1,{fi},{ei}")
                    break
        elif len(fids) == 2:
            n0, n1 = fnorms[fids[0]], fnorms[fids[1]]
            cos_a = float(np.clip(n0 @ n1, -1.0, 1.0))
            if math.acos(cos_a) > thresh_rad:
                fi = fids[0]
                face = faces[fi]
                for ei in range(3):
                    a, b = int(face[ei]), int(face[(ei+1) % 3])
                    if tuple(sorted((a, b))) == e:
                        sharp_edges_out.append(f"{1 if cos_a > 0 else 0},{fi},{ei}")
                        break

    with open(sharp_path, "w") as fp:
        fp.write(f"{len(sharp_edges_out)}\n")
        for s in sharp_edges_out:
            fp.write(s + "\n")
    return len(sharp_edges_out)


# ── OBJ quad copy (preserves quads exactly as QuadWild wrote them) ────────────

def copy_obj_preserve_quads(src_obj: str, dst_obj: str) -> None:
    """
    Direct copy of the QuadWild output OBJ.
    QuadWild writes genuine quad faces (4 vertex indices per f-line).
    We just copy the file — no conversion, no triangulation.
    """
    shutil.copy2(src_obj, dst_obj)


def obj_to_stl_triangulated(obj_path: str, stl_path: str) -> None:
    """
    Fallback: convert OBJ → STL when the user explicitly chose .stl output.
    This WILL triangulate quads — warn the user before calling this.
    """
    import trimesh
    mesh = trimesh.load(obj_path, force="mesh", process=False)
    mesh.export(stl_path)


# ── QuadWild wrapper ──────────────────────────────────────────────────────────

class QWException(Exception):
    pass


class Quadwild:
    def __init__(self, mesh_path: str) -> None:
        system = platform.system()
        if system == "Windows":
            qw_lib = "lib_quadwild.dll"
            qp_lib = "lib_quadpatches.dll"
        elif system == "Darwin":
            qw_lib = "liblib_quadwild.dylib"
            qp_lib = "liblib_quadpatches.dylib"
        else:
            qw_lib = "liblib_quadwild.so"
            qp_lib = "liblib_quadpatches.so"

        qw_path = LIB_DIR / qw_lib
        qp_path = LIB_DIR / qp_lib

        if not qw_path.exists():
            raise QWException(
                f"QuadWild native library not found:\n{qw_path}\n\n"
                "The GitHub source ZIP does NOT include compiled binaries.\n"
                "Download the pre-built release ZIP from:\n"
                "  https://github.com/ksami/QRemeshify/releases\n"
                "  (or https://ksami.gumroad.com/l/QRemeshify)\n\n"
                f"Then copy {qw_lib} + {qp_lib}\ninto:\n  {LIB_DIR}"
            )
        if not qp_path.exists():
            raise QWException(
                f"QuadPatches library not found:\n{qp_path}\n\n"
                "Download the pre-built release from:\n"
                "  https://github.com/ksami/QRemeshify/releases\n"
                f"and copy {qp_lib} into:\n  {LIB_DIR}"
            )

        self.quadwild    = cdll.LoadLibrary(str(qw_path))
        self.quadpatches = cdll.LoadLibrary(str(qp_path))

        self.quadwild.remeshAndField2.argtypes = [POINTER(Parameters), c_char_p, c_char_p, c_char_p]
        self.quadwild.remeshAndField2.restype  = None
        self.quadwild.trace2.argtypes          = [c_char_p]
        self.quadwild.trace2.restype           = c_bool
        self.quadpatches.quadPatches.argtypes  = [c_char_p, POINTER(QRParameters), c_float, c_int, c_bool]
        self.quadpatches.quadPatches.restype   = c_int

        stem = str(Path(mesh_path).with_suffix(""))
        self.mesh_path            = mesh_path
        self.sharp_path           = f"{stem}_rem.sharp"
        self.field_path           = f"{stem}_rem.rosy"
        self.remeshed_path        = f"{stem}_rem.obj"
        self.traced_path          = f"{stem}_rem_p0.obj"
        self.output_path          = f"{stem}_rem_p0_0_quadrangulation.obj"
        self.output_smoothed_path = f"{stem}_rem_p0_0_quadrangulation_smooth.obj"

    def remesh_and_field(self, remesh: bool, enable_sharp: bool, sharp_angle: float) -> None:
        params = Parameters(
            remesh=remesh, sharpAngle=sharp_angle if enable_sharp else -1,
            hasFeature=enable_sharp, hasField=False, alpha=0.01, scaleFact=1,
        )
        try:
            self.quadwild.remeshAndField2(
                byref(params),
                self.mesh_path.encode(), self.sharp_path.encode(), self.field_path.encode(),
            )
        except Exception as e:
            raise QWException("remeshAndField failed") from e

    def trace(self) -> bool:
        prefix = str(Path(self.remeshed_path).with_suffix(""))
        try:
            return self.quadwild.trace2(prefix.encode())
        except Exception as e:
            raise QWException("trace failed") from e

    def quadrangulate(self, cfg: dict) -> int:
        cb_time = cfg["callbackTimeLimit"]
        cb_gap  = cfg["callbackGapLimit"]
        params  = QRParameters()

        params.useFlowSolver                        = True
        params.initialRemeshing                     = True
        params.initialRemeshingEdgeFactor           = 1.0
        params.reproject                            = True
        params.splitConcaves                        = False
        params.finalSmoothing                       = True
        params.doubletRemoval                       = True
        params.chartSmoothingIterations             = 0
        params.quadrangulationFixedSmoothingIterations    = 0
        params.quadrangulationNonFixedSmoothingIterations = 0
        params.feasibilityFix                       = False
        params.resultSmoothingIterations            = 5
        params.resultSmoothingNRing                 = 3.0
        params.resultSmoothingLaplacianIterations   = 2
        params.resultSmoothingLaplacianNRing        = 3.0

        params.alpha                             = cfg["alpha"]
        params.ilpMethod                         = ILP_METHODS[cfg["ilpMethod"]]
        params.timeLimit                         = cfg["timeLimit"]
        params.gapLimit                          = cfg["gapLimit"]
        params.minimumGap                        = cfg["minimumGap"]
        params.isometry                          = cfg["isometry"]
        params.regularityQuadrilaterals          = cfg["regularityQuadrilaterals"]
        params.regularityNonQuadrilaterals       = cfg["regularityNonQuadrilaterals"]
        params.regularityNonQuadrilateralsWeight = cfg["regularityNonQuadrilateralsWeight"]
        params.alignSingularities                = cfg["alignSingularities"]
        params.alignSingularitiesWeight          = cfg["alignSingularitiesWeight"]
        params.repeatLosingConstraintsIterations = cfg["repeatLosingConstraintsIterations"]
        params.repeatLosingConstraintsQuads      = cfg["repeatLosingConstraintsQuads"]
        params.repeatLosingConstraintsNonQuads   = cfg["repeatLosingConstraintsNonQuads"]
        params.repeatLosingConstraintsAlign      = cfg["repeatLosingConstraintsAlign"]
        params.hardParityConstraint              = cfg["hardParityConstraint"]

        params.flow_config_filename    = str(LIB_DIR / FLOW_CONFIGS[cfg["flowConfig"]]).encode()
        params.satsuma_config_filename = str(LIB_DIR / SATSUMA_CONFIGS[cfg["satsumaConfig"]]).encode()
        params.callbackTimeLimit = (c_float * len(cb_time))(*cb_time)
        params.callbackGapLimit  = (c_float * len(cb_gap))(*cb_gap)

        try:
            return self.quadpatches.quadPatches(
                self.traced_path.encode(),
                byref(params),
                c_float(cfg["scaleFact"]),
                c_int(cfg["fixedChartClusters"]),
                c_bool(cfg["enableSmoothing"]),
            )
        except Exception as e:
            raise QWException("quadPatches failed") from e


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_remesh(input_stl: str, output_path: str, cfg: dict,
               log_fn, done_fn, error_fn) -> None:
    """
    Full pipeline. Runs in a background thread.
    output_path should be .obj to preserve quads, or .stl (will triangulate).
    """
    try:
        work_dir = tempfile.mkdtemp(prefix="zelmesh_")
        log_fn(f"Work dir: {work_dir}")

        base     = Path(input_stl).stem
        obj_path = os.path.join(work_dir, f"{base}.obj")

        log_fn("Step 1/5 — Converting STL → OBJ …")
        stl_to_obj(input_stl, obj_path,
                   sharp_path=os.path.join(work_dir, f"{base}_rem.sharp"),
                   enable_sharp=cfg["enableSharp"],
                   sharp_angle_deg=cfg["sharpAngle"])

        log_fn("Step 2/5 — Loading QuadWild libraries …")
        qw = Quadwild(obj_path)

        log_fn("Step 3/5 — Remesh & cross-field calculation …")
        qw.remesh_and_field(
            remesh=cfg["enableRemesh"],
            enable_sharp=cfg["enableSharp"],
            sharp_angle=cfg["sharpAngle"],
        )

        log_fn("Step 4/5 — Tracing patches …")
        qw.trace()

        log_fn("Step 5/5 — Quadrangulating (ILP solver) … (this can take a while)")
        qw.quadrangulate(cfg)

        # QuadWild output is an OBJ with genuine quad faces
        final_obj = qw.output_smoothed_path if cfg["enableSmoothing"] else qw.output_path
        if not os.path.isfile(final_obj):
            raise QWException(f"Expected output not found: {final_obj}")

        # ── Output format decision ────────────────────────────────────────────
        out_ext = Path(output_path).suffix.lower()
        if out_ext == ".stl":
            log_fn("⚠ Converting to STL — quad faces will be triangulated.")
            log_fn("   (Use .obj output to keep your quad topology!)")
            obj_to_stl_triangulated(final_obj, output_path)
        else:
            # .obj — copy directly, zero triangulation
            log_fn("Saving quad OBJ (faces preserved exactly) …")
            copy_obj_preserve_quads(final_obj, output_path)

        shutil.rmtree(work_dir, ignore_errors=True)
        log_fn(f"✅ Done!  →  {output_path}")
        done_fn()

    except QWException as e:
        error_fn(str(e))
    except Exception:
        error_fn(traceback.format_exc())


# ── GUI ───────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT   = "#9b51e0"
HOVER_COLOR = "#8a2be2"
BG_DARK  = "#120d17"
BG_MID   = "#191622"
BG_CARD  = "#26212d"
TEXT_DIM = "#8b949e"
WARN     = "#e3b341"


class ZelMeshApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ZelMesh — Standalone")
        self.geometry("860x800")
        self.minsize(780, 700)
        self.configure(fg_color=BG_DARK)
        
        icon_path = SCRIPT_DIR / "icons" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass
                
        self.input_path      = ""
        self.output_path_val = ""
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="ZelMesh",
                     font=ctk.CTkFont("Segoe UI", 20, "bold"),
                     text_color="white").pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(hdr, text="Standalone • No Blender required",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_DIM).pack(side="left")

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                      scrollbar_button_color=BG_CARD)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Files card ────────────────────────────────────────────────────────
        io_card = self._card(body, "Files")
        self._file_row(io_card, "Input STL",  "Browse…", self._pick_input,  "input_label")
        self._file_row(io_card, "Output File","Browse…", self._pick_output, "output_label")

        # Output format tip
        tip_frame = ctk.CTkFrame(io_card, fg_color="#1a2233", corner_radius=6)
        tip_frame.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(
            tip_frame,
            text="💡  Save as .obj to keep quad faces.  Saving as .stl will triangulate them.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=WARN,
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=10, pady=6)

        # ── Basic settings ────────────────────────────────────────────────────
        basic = self._card(body, "Basic Settings")

        self.var_remesh = self._toggle(basic, "Preprocess",
            "Decimates, triangulates, fixes common geometry issues", True)
        self.var_smooth = self._toggle(basic, "Smoothing",
            "Smooths topology after quadrangulation", True)
        self.var_sharp  = self._toggle(basic, "Detect Sharp",
            "Detect sharp edges, seams, and angle threshold", True)

        self.var_angle = self._slider_row(basic, "Sharp Angle Threshold",
                                          0, 180, 35, " °", fmt=".0f")
        self.var_scale = self._slider_row(basic, "Scale Factor",
                                          0.1, 4.0, 1.0, "×", fmt=".2f",
                                          tip="<1 = more detail / quads,  >1 = fewer / larger quads")

        sym_row = ctk.CTkFrame(basic, fg_color="transparent")
        sym_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(sym_row, text="Symmetry", width=160, anchor="w",
                     text_color="white").pack(side="left")
        self.var_symX = ctk.BooleanVar(value=False)
        self.var_symY = ctk.BooleanVar(value=False)
        self.var_symZ = ctk.BooleanVar(value=False)
        for axis, var in [("X", self.var_symX), ("Y", self.var_symY), ("Z", self.var_symZ)]:
            ctk.CTkCheckBox(sym_row, text=axis, variable=var, width=56).pack(side="left", padx=6)

        # ── Advanced (collapsible) ────────────────────────────────────────────
        self._adv_open = False
        self._adv_btn = ctk.CTkButton(body, text="▶  Advanced Settings",
                                      fg_color=BG_CARD, hover_color=BG_MID,
                                      anchor="w", command=self._toggle_advanced,
                                      font=ctk.CTkFont("Segoe UI", 13, "bold"),
                                      corner_radius=8)
        self._adv_btn.pack(fill="x", pady=(4, 0))
        self._adv_frame = ctk.CTkFrame(body, fg_color=BG_CARD, corner_radius=8)
        self._build_advanced(self._adv_frame)

        # ── Log ───────────────────────────────────────────────────────────────
        log_card = self._card(body, "Log")
        self.log_box = ctk.CTkTextbox(log_card, height=150, fg_color=BG_DARK,
                                      font=ctk.CTkFont("Courier New", 11),
                                      state="disabled", corner_radius=6)
        self.log_box.pack(fill="both", expand=True)

        # ── Footer ────────────────────────────────────────────────────────────
        foot = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=62)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)

        self.progress = ctk.CTkProgressBar(foot, mode="indeterminate",
                                           progress_color=ACCENT)
        self.progress.pack(fill="x", padx=16, pady=(8, 4))
        self.progress.stop()
        self.progress.set(0)

        self.run_btn = ctk.CTkButton(foot, text="  ▶  Remesh",
                                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                                     fg_color=ACCENT, hover_color=HOVER_COLOR,
                                     height=36, corner_radius=8,
                                     command=self._run)
        self.run_btn.pack(side="right", padx=16, pady=4)

        self.status_lbl = ctk.CTkLabel(foot, text="Ready", text_color=TEXT_DIM,
                                       font=ctk.CTkFont("Segoe UI", 12))
        self.status_lbl.pack(side="left", padx=16)

    def _build_advanced(self, parent):
        self.var_ilp       = self._combo(parent, "ILP Method", list(ILP_METHODS.keys()), "LEASTSQUARES")
        self.var_timeLimit = self._int_entry(parent, "Time Limit (s)", 200)
        self.var_gapLimit  = self._float_entry(parent, "Gap Limit", 0.0)
        self.var_minGap    = self._float_entry(parent, "Minimum Gap", 0.4)
        self.var_alpha     = self._float_entry(parent, "Alpha (isometry↔regularity)", 0.005)
        self.var_fixedCC   = self._int_entry(parent, "Fixed Chart Clusters", 0)

        self.var_isometry    = self._toggle(parent, "Isometry",              "", True)
        self.var_regQuad     = self._toggle(parent, "Regularity Quads",      "", True)
        self.var_regNonQuad  = self._toggle(parent, "Regularity Non-Quads",  "", True)
        self.var_regNonQuadW = self._slider_row(parent, "Reg. Non-Quads Weight", 0, 1, 0.9)
        self.var_alignSing   = self._toggle(parent, "Align Singularities",   "", True)
        self.var_alignSingW  = self._slider_row(parent, "Singularity Align Weight", 0, 1, 0.1)

        self.var_rlcIter  = self._toggle(parent, "Repeat Losing Constraints (Iter)",  "", True)
        self.var_rlcQuad  = self._toggle(parent, "Repeat Losing Constraints (Quads)", "", False)
        self.var_rlcNQ    = self._toggle(parent, "Repeat Losing Constraints (Non-Q)", "", False)
        self.var_rlcAlign = self._toggle(parent, "Repeat Losing Constraints (Align)", "", True)
        self.var_hardPC   = self._toggle(parent, "Hard Parity Constraint",            "", True)

        self.var_flowCfg    = self._combo(parent, "Flow Config",    list(FLOW_CONFIGS.keys()),    "SIMPLE")
        self.var_satsumaCfg = self._combo(parent, "Satsuma Config", list(SATSUMA_CONFIGS.keys()), "DEFAULT")

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _card(self, parent, title):
        outer = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        outer.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont("Segoe UI", 13, "bold"),
                     text_color=ACCENT).pack(anchor="w", padx=14, pady=(10, 4))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(0, 10))
        return inner

    def _file_row(self, parent, label, btn_text, cmd, attr):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=110, anchor="w",
                     text_color="white").pack(side="left")
        lbl = ctk.CTkLabel(row, text="(none)", text_color=TEXT_DIM,
                            anchor="w", wraplength=480)
        lbl.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(row, text=btn_text, width=80, command=cmd,
                      fg_color=BG_MID, hover_color=BG_DARK,
                      corner_radius=6).pack(side="right")
        setattr(self, attr, lbl)

    def _toggle(self, parent, label, tip, default):
        var = ctk.BooleanVar(value=default)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkCheckBox(row, text=label, variable=var).pack(side="left")
        if tip:
            ctk.CTkLabel(row, text=tip, text_color=TEXT_DIM,
                         font=ctk.CTkFont("Segoe UI", 11)).pack(side="left", padx=12)
        return var

    def _slider_row(self, parent, label, lo, hi, default,
                    unit="", fmt=".2f", tip=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=240, anchor="w",
                     text_color="white").pack(side="left")
        var = ctk.DoubleVar(value=default)
        val_lbl = ctk.CTkLabel(row, text=f"{default:{fmt}}{unit}", width=60,
                               text_color=ACCENT)
        val_lbl.pack(side="right")
        def update(v): val_lbl.configure(text=f"{float(v):{fmt}}{unit}")
        ctk.CTkSlider(row, from_=lo, to=hi, variable=var,
                      command=update, width=220, progress_color=ACCENT,
                      button_color=ACCENT, button_hover_color=HOVER_COLOR).pack(side="right", padx=8)
        if tip:
            ctk.CTkLabel(row, text=tip, text_color=TEXT_DIM,
                         font=ctk.CTkFont("Segoe UI", 10)).pack(side="left", padx=6)
        return var

    def _combo(self, parent, label, values, default):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=240, anchor="w",
                     text_color="white").pack(side="left")
        var = ctk.StringVar(value=default)
        ctk.CTkOptionMenu(row, values=values, variable=var,
                          width=180, fg_color=BG_MID,
                          button_color=BG_DARK,
                          button_hover_color=HOVER_COLOR).pack(side="left", padx=8)
        return var

    def _int_entry(self, parent, label, default):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=240, anchor="w",
                     text_color="white").pack(side="left")
        var = ctk.IntVar(value=default)
        ctk.CTkEntry(row, textvariable=var, width=100).pack(side="left", padx=8)
        return var

    def _float_entry(self, parent, label, default):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=240, anchor="w",
                     text_color="white").pack(side="left")
        var = ctk.DoubleVar(value=default)
        ctk.CTkEntry(row, textvariable=var, width=100).pack(side="left", padx=8)
        return var

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_advanced(self):
        if self._adv_open:
            self._adv_frame.pack_forget()
            self._adv_btn.configure(text="▶  Advanced Settings")
        else:
            self._adv_frame.pack(fill="x", pady=(0, 10))
            self._adv_btn.configure(text="▼  Advanced Settings")
        self._adv_open = not self._adv_open

    def _pick_input(self):
        p = filedialog.askopenfilename(
            title="Select input STL",
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")])
        if not p:
            return
        self.input_path = p
        self.input_label.configure(text=p)
        if not self.output_path_val:
            stem = Path(p).stem
            # Default to .obj so quads are preserved
            auto = str(Path(p).parent / f"{stem}_remeshed.obj")
            self.output_path_val = auto
            self.output_label.configure(text=auto)

    def _pick_output(self):
        p = filedialog.asksaveasfilename(
            title="Save output (use .obj to preserve quads)",
            defaultextension=".obj",
            filetypes=[
                ("OBJ — preserves quads (recommended)", "*.obj"),
                ("STL — triangulates quads (legacy)",   "*.stl"),
            ])
        if not p:
            return
        self.output_path_val = p
        self.output_label.configure(text=p)
        # Warn immediately if user chose STL
        if Path(p).suffix.lower() == ".stl":
            messagebox.showwarning(
                "STL will triangulate quads",
                "You chose .stl output.\n\n"
                "STL format only supports triangles, so your quad faces will be "
                "split into triangles — defeating the purpose of quad remeshing.\n\n"
                "Choose .obj instead to keep the quad topology intact.\n"
                "You can import .obj into Blender, Maya, 3ds Max, ZBrush, etc."
            )

    def _collect_cfg(self) -> dict:
        return dict(
            enableRemesh    = self.var_remesh.get(),
            enableSmoothing = self.var_smooth.get(),
            enableSharp     = self.var_sharp.get(),
            sharpAngle      = float(self.var_angle.get()),
            scaleFact       = float(self.var_scale.get()),
            symmetryX       = self.var_symX.get(),
            symmetryY       = self.var_symY.get(),
            symmetryZ       = self.var_symZ.get(),
            alpha                             = float(self.var_alpha.get()),
            ilpMethod                         = self.var_ilp.get(),
            timeLimit                         = int(self.var_timeLimit.get()),
            gapLimit                          = float(self.var_gapLimit.get()),
            minimumGap                        = float(self.var_minGap.get()),
            fixedChartClusters                = int(self.var_fixedCC.get()),
            isometry                          = self.var_isometry.get(),
            regularityQuadrilaterals          = self.var_regQuad.get(),
            regularityNonQuadrilaterals       = self.var_regNonQuad.get(),
            regularityNonQuadrilateralsWeight = float(self.var_regNonQuadW.get()),
            alignSingularities                = self.var_alignSing.get(),
            alignSingularitiesWeight          = float(self.var_alignSingW.get()),
            repeatLosingConstraintsIterations = self.var_rlcIter.get(),
            repeatLosingConstraintsQuads      = self.var_rlcQuad.get(),
            repeatLosingConstraintsNonQuads   = self.var_rlcNQ.get(),
            repeatLosingConstraintsAlign      = self.var_rlcAlign.get(),
            hardParityConstraint              = self.var_hardPC.get(),
            flowConfig                        = self.var_flowCfg.get(),
            satsumaConfig                     = self.var_satsumaCfg.get(),
            callbackTimeLimit = [3.0, 5.0, 10.0, 20.0, 30.0, 60.0, 90.0, 120.0],
            callbackGapLimit  = [0.005, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.3],
        )

    def _run(self):
        if not self.input_path:
            messagebox.showerror("Error", "Please select an input STL file.")
            return
        if not self.output_path_val:
            messagebox.showerror("Error", "Please choose an output file path.")
            return

        cfg = self._collect_cfg()
        self.run_btn.configure(state="disabled", text="  ⏳  Running…")
        self.progress.start()
        self.status_lbl.configure(text="Processing…", text_color=WARN)
        self._log_clear()

        def log(msg):   self.after(0, lambda m=msg: self._log_append(m))
        def done():     self.after(0, self._on_done)
        def error(msg): self.after(0, lambda m=msg: self._on_error(m))

        threading.Thread(
            target=run_remesh,
            args=(self.input_path, self.output_path_val, cfg, log, done, error),
            daemon=True,
        ).start()

    def _on_done(self):
        self.run_btn.configure(state="normal", text="  ▶  Remesh")
        self.progress.stop(); self.progress.set(1)
        self.status_lbl.configure(text="✅ Complete", text_color="#3fb950")

    def _on_error(self, msg):
        self.run_btn.configure(state="normal", text="  ▶  Remesh")
        self.progress.stop(); self.progress.set(0)
        self.status_lbl.configure(text="❌ Error", text_color="#f85149")
        self._log_append(f"\n❌ ERROR:\n{msg}")
        messagebox.showerror("Remesh failed", msg[:800])

    def _log_append(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _log_clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


# ── Startup lib check ─────────────────────────────────────────────────────────

def _check_libs() -> str:
    system = platform.system()
    if system == "Windows":
        names = ["lib_quadwild.dll", "lib_quadpatches.dll"]
    elif system == "Darwin":
        names = ["liblib_quadwild.dylib", "liblib_quadpatches.dylib"]
    else:
        names = ["liblib_quadwild.so", "liblib_quadpatches.so"]

    missing = [n for n in names if not (LIB_DIR / n).exists()]
    if not missing:
        return ""
    return (
        f"Native library files not found in:\n  {LIB_DIR}\n\n"
        f"Missing: {', '.join(missing)}\n\n"
        "The GitHub source ZIP does NOT include compiled binaries.\n"
        "Download the pre-built release ZIP from:\n"
        "  https://github.com/ksami/QRemeshify/releases\n"
        "  (or https://ksami.gumroad.com/l/QRemeshify)\n\n"
        f"Copy the .dll / .so / .dylib files into:\n  {LIB_DIR}"
    )


if __name__ == "__main__":
    app = ZelMeshApp()
    lib_err = _check_libs()
    if lib_err:
        app.after(400, lambda: messagebox.showwarning("Missing Native Libraries", lib_err))
    app.mainloop()
