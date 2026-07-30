#!/usr/bin/env python3
"""Atmos Binaural Converter - Complete GUI Application"""
import os, sys, subprocess, threading, tkinter as tk, math, json
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Defaults
QUALITY_PRESETS = {"Low (128k)": "128k", "Medium (192k)": "192k", "High (256k)": "256k", "Ultra (320k)": "320k"}
FILTERS = {
    "standard": "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5",
    "enhanced": "aresample=48000,pan=stereo|c0=c0+0.707*c2+0.707*c4|c1=c1+0.707*c2+0.707*c5,anequalizer=c0 f=80 w=200 g=4 t=1|c1 f=80 w=200 g=4 t=1,equalizer=f=2500:t=q:w=1:g=2,equalizer=f=8000:t=q:w=1:g=1",
    "spatial": "aresample=48000,aformat=channel_layouts=5.1,pan=stereo|c0=0.87*c0+0.707*c2+0.707*c4+0.25*c5|c1=0.87*c1+0.707*c2+0.707*c5+0.25*c4,anequalizer=c0 f=60 w=150 g=5 t=1|c1 f=60 w=150 g=5 t=1,equalizer=f=2000:t=q:w=1.5:g=3,equalizer=f=6000:t=q:w=1:g=2,equalizer=f=10000:t=q:w=1:g=1.5,volume=0.95"
}
METHOD_PRESETS = {"Standard Downmix": "standard", "Enhanced (Bass Boost)": "enhanced", "Spatial Binaural": "spatial", "HRTF (SOFA)": "hrtf", "Atmos IR Convolution": "atmos_ir", "Custom Speaker Layout": "custom"}
CODEC_PRESETS = {
    "AAC (M4A)": {"codec": "aac", "ext": ".m4a"}, "AAC (MP4)": {"codec": "aac", "ext": ".mp4"},
    "MP3": {"codec": "mp3", "ext": ".mp3"}, "FLAC": {"codec": "flac", "ext": ".flac"},
    "Opus (OGG)": {"codec": "opus", "ext": ".ogg"}, "WAV": {"codec": "pcm_s16le", "ext": ".wav"},
}
DEFAULT_POS_51 = {"FL": -30, "FR": 30, "FC": 0, "LFE": 0, "BL": -110, "BR": 110}
DEFAULT_POS_71 = {"FL": -30, "FR": 30, "FC": 0, "LFE": 0, "SL": -90, "SR": 90, "BL": -150, "BR": 150}

# Module imports with fallbacks
try:
    from convert_atmos import get_audio_info, get_channel_count
except ImportError:
    get_audio_info = lambda f: None
    get_channel_count = lambda f: 2

try:
    from speaker_shifter import SpeakerConfig, generate_binaural_filter, get_presets
except ImportError:
    class SpeakerConfig:
        def __init__(self, layout="5.1"):
            self.layout = layout
            self.labels = ["FL","FR","FC","LFE","BL","BR"] if layout=="5.1" else ["FL","FR","FC","LFE","SL","SR","BL","BR"]
            self.positions = dict(DEFAULT_POS_51 if layout=="5.1" else DEFAULT_POS_71)
            self.volumes = {l: 1.0 for l in self.labels}
            self.distances = {l: 0.0 for l in self.labels}
        def set_position(self, s, a, d=None):
            if s in self.positions and s != "LFE":
                self.positions[s] = max(-180, min(180, a))
                self.distances[s] = min(1.0, abs(a)/180.0) if d is None else d
                self.volumes[s] = max(0.1, 1.0/(1.0+self.distances[s]*2.0))
        def get_position(self, s): return self.positions.get(s, 0)
        def get_volume(self, s): return self.volumes.get(s, 1.0)
        def get_distance(self, s): return self.distances.get(s, 0.0)
        def reset(self):
            self.positions = dict(DEFAULT_POS_51 if self.layout=="5.1" else DEFAULT_POS_71)
            self.volumes = {l: 1.0 for l in self.labels}
            self.distances = {l: 0.0 for l in self.labels}
    def generate_binaural_filter(config): return FILTERS["enhanced"]
    def get_presets(): return {"Default 5.1": DEFAULT_POS_51}

try:
    from hrtf_generator import HRTFGenerator, HeadMeasurements, SofaFileReader
except ImportError:
    HRTFGenerator = HeadMeasurements = SofaFileReader = None

try:
    from head_model_parser import HeadModelParser
except ImportError:
    HeadModelParser = None

try:
    from foobar_convolver import FoobarConvolver, get_convolver
except ImportError:
    FoobarConvolver = get_convolver = None

try:
    from hesuvi_support import HeSuViManager, HeSuViConverter
except ImportError:
    HeSuViManager = HeSuViConverter = None

try:
    from volume_visualizer import VolumeVisualizerPanel
except ImportError:
    VolumeVisualizerPanel = None


class SpeakerCanvas(tk.Canvas):
    def __init__(self, parent, config, on_change=None, **kw):
        super().__init__(parent, **kw)
        self.config = config; self.on_change = on_change
        self.speakers = {}; self.dragging = None
        self.cx, self.cy, self.r = 150, 150, 100
        self.bind("<ButtonPress-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.draw()
    
    def draw(self):
        self.delete("all")
        self.create_oval(self.cx-20, self.cy-20, self.cx+20, self.cy+20, fill="#2d2d44", outline="#4a4a6a", width=2)
        self.create_oval(self.cx-self.r, self.cy-self.r, self.cx+self.r, self.cy+self.r, outline="#3a3a5a", dash=(5,5))
        self.create_text(self.cx, self.cy-self.r-15, text="FRONT", fill="#888", font=("Arial",8))
        self.speakers.clear()
        for label, angle in self.config.positions.items():
            if label == "LFE": continue
            rad = math.radians(angle - 90)
            x, y = self.cx + self.r*math.cos(rad), self.cy + self.r*math.sin(rad)
            vol = self.config.get_volume(label) if hasattr(self.config, 'get_volume') else 1.0
            self.create_line(self.cx, self.cy, x, y, fill="#3a3a5a", dash=(3,3))
            size = int(10 + vol * 8)
            color = "#4a9eff" if label.startswith("F") else "#ff6b6b" if label.startswith("B") else "#6bff6b"
            self.create_oval(x-size, y-size, x+size, y+size, fill=color, outline="white", width=2)
            self.create_text(x, y, text=label, fill="white", font=("Arial",9,"bold"))
            self.create_text(x, y+size+10, text=f"{int(vol*100)}%", fill="#aaa", font=("Arial",7))
            self.speakers[label] = (x, y, size)
    
    def press(self, e):
        for l, (x,y,s) in self.speakers.items():
            if abs(e.x-x)<s and abs(e.y-y)<s: self.dragging = l; break
    def drag(self, e):
        if self.dragging:
            dx, dy = e.x-self.cx, e.y-self.cy
            angle = math.degrees(math.atan2(dy, dx)) + 90
            if angle > 180: angle -= 360
            dist = min(1.0, math.sqrt(dx*dx+dy*dy) / self.r)
            self.config.set_position(self.dragging, angle, dist)
            self.draw()
            if self.on_change: self.on_change(self.dragging, angle)
    def release(self, e): self.dragging = None
    def update_config(self, c): self.config = c; self.draw()


class AtmosConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Atmos Binaural Converter v2.0")
        self.root.geometry("900x750")
        self.root.minsize(800, 650)
        
        self.input_files = []
        self.output_dir = tk.StringVar(value=str(Path.home()/"Music"))
        self.quality = tk.StringVar(value="High (256k)")
        self.method = tk.StringVar(value="Enhanced (Bass Boost)")
        self.codec_format = tk.StringVar(value="AAC (M4A)")
        self.sofa_file = tk.StringVar(value="")
        self.hesuvi_profile = tk.StringVar(value="")
        self.atmos_ir_profile = tk.StringVar(value="")
        self.head_model_file = tk.StringVar(value="")
        self.is_converting = False
        self.cancel_flag = False
        self.current_process = None
        self.process_lock = threading.Lock()
        
        self.speaker_config = SpeakerConfig("5.1")
        self.speaker_layout = tk.StringVar(value="5.1")
        
        # Convolver
        self.convolver = get_convolver() if get_convolver else None
        
        self.setup_styles()
        self.create_widgets()
        self.check_ffmpeg()
        self.load_settings()
    
    def setup_styles(self):
        s = ttk.Style(); s.theme_use('clam')
        s.configure('Convert.TButton', font=('Segoe UI', 11, 'bold'))
        s.configure('Cancel.TButton', font=('Segoe UI', 10))
        s.configure('Custom.Horizontal.TProgressbar', thickness=20)
    
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        main_tab = ttk.Frame(self.notebook, padding="15")
        speaker_tab = ttk.Frame(self.notebook, padding="15")
        ir_tab = ttk.Frame(self.notebook, padding="15")
        
        self.notebook.add(main_tab, text="  🎧 Converter  ")
        self.notebook.add(speaker_tab, text="  🔊 Speaker Shifter  ")
        self.notebook.add(ir_tab, text="  🎛️ Atmos IR  ")
        
        self.create_main_tab(main_tab)
        self.create_speaker_tab(speaker_tab)
        self.create_ir_tab(ir_tab)
    
    def create_main_tab(self, parent):
        ttk.Label(parent, text="🎧 Dolby 5.1 to Binaural Converter", font=('Segoe UI', 16, 'bold')).pack(pady=(0,5))
        ttk.Label(parent, text="Convert surround sound to stereo for TWS earbuds & headphones", font=('Segoe UI', 10), foreground='gray').pack(pady=(0,10))
        
        # Files
        ff = ttk.LabelFrame(parent, text="Input Files", padding="10")
        ff.pack(fill=tk.X, pady=(0,8))
        lf = ttk.Frame(ff); lf.pack(fill=tk.BOTH, expand=True)
        self.file_listbox = tk.Listbox(lf, height=4, selectmode=tk.EXTENDED, font=('Consolas',9))
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=sb.set)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        bf = ttk.Frame(ff); bf.pack(fill=tk.X, pady=(8,0))
        ttk.Button(bf, text="➕ Add Files", command=self.add_files).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(bf, text="📁 Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(bf, text="🗑️ Remove", command=self.remove_selected).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(bf, text="Clear", command=self.clear_files).pack(side=tk.LEFT)
        self.file_count = ttk.Label(bf, text="0 files")
        self.file_count.pack(side=tk.RIGHT)
        
        # Output
        of = ttk.LabelFrame(parent, text="Output Directory", padding="8")
        of.pack(fill=tk.X, pady=(0,8))
        oi = ttk.Frame(of); oi.pack(fill=tk.X)
        ttk.Entry(oi, textvariable=self.output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,8))
        ttk.Button(oi, text="Browse", command=lambda: self.browse_dir(self.output_dir)).pack(side=tk.RIGHT)
        
        # Settings
        sf = ttk.LabelFrame(parent, text="Settings", padding="8")
        sf.pack(fill=tk.X, pady=(0,8))
        
        r1 = ttk.Frame(sf); r1.pack(fill=tk.X, pady=(0,4))
        ttk.Label(r1, text="Quality:").pack(side=tk.LEFT, padx=(0,4))
        ttk.Combobox(r1, textvariable=self.quality, values=list(QUALITY_PRESETS.keys()), state="readonly", width=16).pack(side=tk.LEFT, padx=(0,15))
        ttk.Label(r1, text="Method:").pack(side=tk.LEFT, padx=(0,4))
        self.method_combo = ttk.Combobox(r1, textvariable=self.method, values=list(METHOD_PRESETS.keys()), state="readonly", width=20)
        self.method_combo.pack(side=tk.LEFT)
        self.method_combo.bind("<<ComboboxSelected>>", self.on_method_change)
        
        r2 = ttk.Frame(sf); r2.pack(fill=tk.X, pady=(4,0))
        ttk.Label(r2, text="Format:").pack(side=tk.LEFT, padx=(0,4))
        ttk.Combobox(r2, textvariable=self.codec_format, values=list(CODEC_PRESETS.keys()), state="readonly", width=16).pack(side=tk.LEFT, padx=(0,15))
        ttk.Label(r2, text="SOFA:").pack(side=tk.LEFT, padx=(0,4))
        ttk.Entry(r2, textvariable=self.sofa_file, width=22).pack(side=tk.LEFT, padx=(0,4))
        ttk.Button(r2, text="...", width=3, command=self.browse_sofa).pack(side=tk.LEFT)
        
        r3 = ttk.Frame(sf); r3.pack(fill=tk.X, pady=(4,0))
        ttk.Label(r3, text="Head Model:").pack(side=tk.LEFT, padx=(0,4))
        ttk.Entry(r3, textvariable=self.head_model_file, width=22).pack(side=tk.LEFT, padx=(0,4))
        ttk.Button(r3, text="Import STL/OBJ", command=self.import_head_model).pack(side=tk.LEFT, padx=(0,10))
        ttk.Label(r3, text="HeSuVi:").pack(side=tk.LEFT, padx=(0,4))
        self.hesuvi_combo = ttk.Combobox(r3, textvariable=self.hesuvi_profile, values=self.get_hesuvi_profiles(), state="readonly", width=18)
        self.hesuvi_combo.pack(side=tk.LEFT)
        ttk.Button(r3, text="↻", width=2, command=self.refresh_hesuvi).pack(side=tk.LEFT)
        
        # Progress
        pf = ttk.Frame(parent); pf.pack(fill=tk.X, pady=(8,4))
        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(pf, variable=self.progress_var, maximum=100, style='Custom.Horizontal.TProgressbar').pack(fill=tk.X, pady=(0,4))
        self.status_label = ttk.Label(pf, text="Ready", foreground='gray')
        self.status_label.pack(anchor=tk.W)
        
        # Buttons
        ab = ttk.Frame(parent); ab.pack(fill=tk.X, pady=(8,0))
        self.convert_btn = ttk.Button(ab, text="🔄 Convert to Binaural", command=self.start_conversion, style='Convert.TButton')
        self.convert_btn.pack(side=tk.LEFT, padx=(0,8))
        self.cancel_btn = ttk.Button(ab, text="❌ Cancel", command=self.cancel_conversion, style='Cancel.TButton', state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT)
    
    def create_speaker_tab(self, parent):
        ttk.Label(parent, text="🔊 Virtual Speaker Shifter", font=('Segoe UI', 16, 'bold')).pack(pady=(0,5))
        ttk.Label(parent, text="Drag speakers to adjust position & distance (volume drops with distance)", font=('Segoe UI', 10), foreground='gray').pack(pady=(0,10))
        
        content = ttk.Frame(parent); content.pack(fill=tk.BOTH, expand=True)
        
        viz = ttk.LabelFrame(content, text="Speaker Layout", padding="8")
        viz.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,8))
        
        lf = ttk.Frame(viz); lf.pack(fill=tk.X, pady=(0,8))
        ttk.Label(lf, text="Layout:").pack(side=tk.LEFT, padx=(0,4))
        lc = ttk.Combobox(lf, textvariable=self.speaker_layout, values=["5.1","7.1"], state="readonly", width=6)
        lc.pack(side=tk.LEFT, padx=(0,8))
        lc.bind("<<ComboboxSelected>>", self.on_layout_change)
        ttk.Button(lf, text="Reset", command=self.reset_speakers).pack(side=tk.LEFT)
        
        self.speaker_canvas = SpeakerCanvas(viz, self.speaker_config, on_change=self.on_speaker_change, width=300, height=300, bg="#1a1a2e", highlightthickness=0)
        self.speaker_canvas.pack(pady=8)
        
        self.speaker_controls_frame = ttk.LabelFrame(content, text="Controls", padding="8")
        self.speaker_controls_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ctrl = self.speaker_controls_frame
        
        ttk.Label(ctrl, text="Presets:", font=('Segoe UI',9,'bold')).pack(anchor=tk.W)
        self.preset_combo = ttk.Combobox(ctrl, values=list(get_presets().keys()), state="readonly", width=18)
        self.preset_combo.pack(fill=tk.X, pady=(0,8))
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_preset(self.preset_combo.get()))
        
        ttk.Label(ctrl, text="Angles:", font=('Segoe UI',9,'bold')).pack(anchor=tk.W)
        self.angle_vars = {}
        self.angle_displays = {}
        self.create_speaker_controls(ctrl)
        
        ttk.Label(ctrl, text="💡 Drag speakers closer/farther\nto adjust volume automatically", font=('Segoe UI',8), foreground='gray').pack(pady=(8,0), anchor=tk.W)
    
    def create_speaker_controls(self, parent):
        for w in parent.winfo_children():
            if hasattr(w, '_is_sp'): w.destroy()
        self.angle_vars.clear(); self.angle_displays.clear()
        for label in self.speaker_config.labels:
            if label == "LFE": continue
            f = ttk.Frame(parent); f._is_sp = True; f.pack(fill=tk.X, pady=1)
            ttk.Label(f, text=f"{label}:", width=4).pack(side=tk.LEFT)
            var = tk.DoubleVar(value=self.speaker_config.get_position(label))
            self.angle_vars[label] = var
            ttk.Scale(f, from_=-180, to=180, variable=var, orient=tk.HORIZONTAL, length=100,
                      command=lambda v, l=label: self.on_slider(l, float(v))).pack(side=tk.LEFT, padx=(2,4))
            d = ttk.Label(f, text=f"{var.get():.0f}°", width=5)
            d.pack(side=tk.LEFT)
            self.angle_displays[label] = d
    
    def create_ir_tab(self, parent):
        ttk.Label(parent, text="🎛️ Atmos IR Convolver & HeSuVi", font=('Segoe UI', 16, 'bold')).pack(pady=(0,5))
        ttk.Label(parent, text="Use Atmos 48kHz/44.1kHz impulse response files for convolution", font=('Segoe UI', 10), foreground='gray').pack(pady=(0,10))
        
        # IR Profiles
        irf = ttk.LabelFrame(parent, text="Atmos IR Profiles", padding="10")
        irf.pack(fill=tk.X, pady=(0,8))
        
        r1 = ttk.Frame(irf); r1.pack(fill=tk.X, pady=(0,8))
        ttk.Label(r1, text="Profile:").pack(side=tk.LEFT, padx=(0,4))
        self.ir_profile_combo = ttk.Combobox(r1, textvariable=self.atmos_ir_profile, values=self.get_ir_profiles(), state="readonly", width=25)
        self.ir_profile_combo.pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(r1, text="Refresh", command=self.refresh_ir_profiles).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(r1, text="Import IR File", command=self.import_ir_file).pack(side=tk.LEFT)
        
        # Info
        info = ttk.LabelFrame(parent, text="IR Directory Info", padding="10")
        info.pack(fill=tk.X, pady=(0,8))
        self.ir_info_label = ttk.Label(info, text="Place WAV files in impulse_responses/ folder", foreground='gray')
        self.ir_info_label.pack(anchor=tk.W)
        
        # HeSuVi
        hsf = ttk.LabelFrame(parent, text="HeSuVi Profile Management", padding="10")
        hsf.pack(fill=tk.X, pady=(0,8))
        
        r2 = ttk.Frame(hsf); r2.pack(fill=tk.X)
        ttk.Button(r2, text="Import SOFA → HeSuVi", command=self.import_sofa_to_hesuvi).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(r2, text="Export Speaker Layout → HeSuVi", command=self.export_to_hesuvi).pack(side=tk.LEFT)
        
        # 3D Model
        model_frame = ttk.LabelFrame(parent, text="3D Head Model", padding="10")
        model_frame.pack(fill=tk.X, pady=(0,8))
        r3 = ttk.Frame(model_frame); r3.pack(fill=tk.X)
        ttk.Label(r3, text="Import STL/OBJ head scan to generate personalized HRTF:").pack(anchor=tk.W)
        r4 = ttk.Frame(model_frame); r4.pack(fill=tk.X, pady=(4,0))
        ttk.Button(r4, text="Import 3D Model (STL/OBJ)", command=self.import_head_model).pack(side=tk.LEFT, padx=(0,8))
        self.model_info = ttk.Label(r4, text="No model loaded", foreground='gray')
        self.model_info.pack(side=tk.LEFT)
        
        self.refresh_ir_profiles()
    
    # === File Operations ===
    def add_files(self):
        files = filedialog.askopenfilenames(title="Select Audio", filetypes=[("Audio","*.m4a *.mp4 *.mkv *.mp3 *.flac *.wav *.aac *.ogg"),("All","*.*")])
        for f in files:
            if f not in self.input_files:
                self.input_files.append(f)
                self.file_listbox.insert(tk.END, os.path.basename(f))
        self.update_file_count()
    
    def add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            exts = {'.m4a','.mp4','.mkv','.mp3','.flac','.wav','.aac','.ogg'}
            for f in Path(folder).iterdir():
                if f.is_file() and f.suffix.lower() in exts and str(f) not in self.input_files:
                    self.input_files.append(str(f))
                    self.file_listbox.insert(tk.END, f.name)
            self.update_file_count()
    
    def remove_selected(self):
        for i in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(i); del self.input_files[i]
        self.update_file_count()
    
    def clear_files(self):
        self.file_listbox.delete(0, tk.END); self.input_files.clear(); self.update_file_count()
    
    def update_file_count(self):
        n = len(self.input_files)
        self.file_count.config(text=f"{n} file{'s' if n!=1 else ''}")
    
    def browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)
    
    def browse_sofa(self):
        f = filedialog.askopenfilename(title="Select SOFA", filetypes=[("SOFA","*.sofa"),("HRTF","*.hrtf.json"),("All","*.*")])
        if f: self.sofa_file.set(f)
    
    # === HesuVi ===
    def get_hesuvi_profiles(self):
        if HeSuViManager:
            try: return HeSuViManager().list_profiles()
            except: pass
        return []
    
    def refresh_hesuvi(self):
        self.hesuvi_combo['values'] = self.get_hesuvi_profiles()
    
    def import_sofa_to_hesuvi(self):
        sofa = self.sofa_file.get()
        if not sofa:
            messagebox.showwarning("No SOFA", "Select a SOFA file first"); return
        if not HeSuViConverter:
            messagebox.showerror("Error", "hesuvi_support module not found"); return
        try:
            conv = HeSuViConverter()
            name = Path(sofa).stem
            profile = conv.sofa_to_hesuvi(sofa, name)
            if profile:
                HeSuViManager().save_profile(profile)
                self.refresh_hesuvi()
                self.hesuvi_profile.set(name)
                messagebox.showinfo("Success", f"Imported as HeSuVi profile: {name}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def export_to_hesuvi(self):
        if not HeSuViManager:
            messagebox.showerror("Error", "hesuvi_support module not found"); return
        try:
            from hesuvi_support import export_hesuvi_from_speaker_config
            profile = export_hesuvi_from_speaker_config(self.speaker_config, "Custom Layout")
            if profile:
                HeSuViManager().save_profile(profile)
                messagebox.showinfo("Success", "Exported speaker layout to HeSuVi")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    # === Head Model ===
    def import_head_model(self):
        if not HeadModelParser:
            messagebox.showerror("Error", "head_model_parser module not found"); return
        f = filedialog.askopenfilename(title="Select Head Model", filetypes=[("3D Models","*.stl *.obj"),("All","*.*")])
        if f:
            try:
                parser = HeadModelParser()
                if parser.parse(f):
                    info = parser.get_info()
                    self.head_model_file.set(f)
                    self.model_info.config(text=f"Width: {info['head_width_cm']:.1f}cm, Circumference: {info['head_circumference_cm']:.1f}cm")
                    messagebox.showinfo("Success", f"Head model loaded!\nWidth: {info['head_width_cm']:.1f}cm\nCircumference: {info['head_circumference_cm']:.1f}cm")
                else:
                    messagebox.showerror("Error", "Failed to parse head model")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    # === IR Profiles ===
    def get_ir_profiles(self):
        if self.convolver:
            return self.convolver.get_available_profiles()
        return []
    
    def refresh_ir_profiles(self):
        self.ir_profile_combo['values'] = self.get_ir_profiles()
        if self.convolver:
            info = self.convolver.get_info()
            self.ir_info_label.config(text=f"IR Directory: {info['ir_directory']}\nFiles: {info['total_ir_files']}, Profiles: {len(info['profiles'])}")
    
    def import_ir_file(self):
        if not self.convolver:
            messagebox.showerror("Error", "foobar_convolver module not found"); return
        f = filedialog.askopenfilename(title="Select IR WAV", filetypes=[("WAV","*.wav"),("All","*.*")])
        if f:
            channels = ["FL","FR","FC","LFE","BL","BR","SL","SR"]
            ch = filedialog.askstring("Channel", f"Enter channel name ({'/'.join(channels)}):")
            if ch and ch.upper() in channels:
                profile = self.atmos_ir_profile.get() or None
                if self.convolver.import_atmos_ir(f, ch.upper(), profile):
                    self.refresh_ir_profiles()
                    messagebox.showinfo("Success", f"Imported {ch.upper()} IR")
    
    # === Speaker Controls ===
    def on_slider(self, label, value):
        self.speaker_config.set_position(label, value)
        if label in self.angle_displays:
            self.angle_displays[label].config(text=f"{value:.0f}°")
        self.speaker_canvas.draw()
    
    def on_speaker_change(self, label, angle):
        if label in self.angle_vars:
            self.angle_vars[label].set(angle)
        if label in self.angle_displays:
            self.angle_displays[label].config(text=f"{angle:.0f}°")
    
    def on_layout_change(self, e=None):
        self.speaker_config = SpeakerConfig(self.speaker_layout.get())
        self.speaker_canvas.update_config(self.speaker_config)
        self.create_speaker_controls(self.winfo_children()[0].winfo_children()[1].winfo_children()[2])
    
    def on_method_change(self, e=None):
        if self.method.get() == "Custom Speaker Layout":
            self.notebook.select(1)
        elif self.method.get() == "Atmos IR Convolution":
            self.notebook.select(2)
    
    def apply_preset(self, name):
        presets = get_presets()
        if name in presets:
            pos = presets[name]
            layout = "7.1" if len(pos) > 6 else "5.1"
            self.speaker_layout.set(layout)
            self.speaker_config = SpeakerConfig(layout)
            for l, a in pos.items():
                self.speaker_config.set_position(l, a)
            self.speaker_canvas.update_config(self.speaker_config)
            if hasattr(self, 'speaker_controls_frame'):
                self.create_speaker_controls(self.speaker_controls_frame)
    
    def reset_speakers(self):
        self.speaker_config.reset()
        self.speaker_canvas.draw()
        for l, v in self.angle_vars.items():
            v.set(self.speaker_config.get_position(l))
        for l, d in self.angle_displays.items():
            d.config(text=f"{self.speaker_config.get_position(l):.0f}°")
    
    # === Conversion ===
    def get_current_filter(self):
        method = METHOD_PRESETS.get(self.method.get(), "enhanced")
        if method == "custom":
            return generate_binaural_filter(self.speaker_config)
        elif method == "hrtf":
            sofa = self.sofa_file.get()
            if sofa and os.path.exists(sofa):
                escaped = sofa.replace("\\", "/").replace(":", "\\:")
                return f"sofalizer=sofa='{escaped}':radius=1.0"
            return FILTERS["enhanced"]
        return FILTERS.get(method, FILTERS["enhanced"])
    
    def get_output_ext(self):
        return CODEC_PRESETS.get(self.codec_format.get(), {"ext": ".m4a"})["ext"]
    
    def get_codec_args(self):
        codec = CODEC_PRESETS.get(self.codec_format.get(), {"codec": "aac"})["codec"]
        codec_map = {"aac":"aac","mp3":"libmp3lame","flac":"flac","opus":"libopus","pcm_s16le":"pcm_s16le"}
        args = ["-c:a", codec_map.get(codec, codec)]
        if codec in ["aac","mp3","opus"]:
            args.extend(["-b:a", QUALITY_PRESETS.get(self.quality.get(), "256k")])
        return args
    
    def convert_file(self, input_file, output_file):
        method = METHOD_PRESETS.get(self.method.get(), "enhanced")
        
        # Atmos IR convolution mode
        if method == "atmos_ir" and self.convolver:
            profile = self.atmos_ir_profile.get() or None
            layout = self.speaker_layout.get()
            return self.convolver.apply_convolution(input_file, output_file, layout, 48000, profile)
        
        filter_str = self.get_current_filter()
        channels = get_channel_count(input_file)
        codec_args = self.get_codec_args()
        
        if channels > 2:
            cmd = ["ffmpeg", "-i", input_file, "-af", filter_str] + codec_args + ["-ar", "48000", "-y", output_file]
        else:
            cmd = ["ffmpeg", "-i", input_file] + codec_args + ["-ar", "48000", "-y", output_file]
        
        with self.process_lock:
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.current_process.communicate()
            return self.current_process.returncode == 0
        except: return False
        finally:
            with self.process_lock: self.current_process = None
    
    def start_conversion(self):
        if not self.input_files:
            messagebox.showwarning("No Files", "Add files first"); return
        out = self.output_dir.get()
        if not out or not os.path.isdir(out):
            messagebox.showwarning("Invalid Output", "Select output directory"); return
        self.is_converting = True; self.cancel_flag = False
        self.convert_btn.config(state=tk.DISABLED); self.cancel_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        threading.Thread(target=self.run_conversion, daemon=True).start()
    
    def run_conversion(self):
        out = self.output_dir.get()
        total = len(self.input_files)
        success = fail = 0
        ext = self.get_output_ext()
        for i, f in enumerate(self.input_files):
            if self.cancel_flag: break
            name = os.path.basename(f)
            self.root.after(0, lambda n=n, idx=i: self.status_label.config(text=f"Converting {idx+1}/{total}: {n}"))
            out_file = os.path.join(out, f"{os.path.splitext(name)[0]}_binaural{ext}")
            try:
                if self.convert_file(f, out_file): success += 1
                else: fail += 1
            except: fail += 1
            self.root.after(0, lambda p=(i+1)/total*100: self.progress_var.set(p))
        self.root.after(0, self.conversion_done, success, fail)
    
    def conversion_done(self, success, fail):
        self.is_converting = False
        self.convert_btn.config(state=tk.NORMAL); self.cancel_btn.config(state=tk.DISABLED)
        self.status_label.config(text=f"Done: {success} ok, {fail} failed")
        if success > 0:
            messagebox.showinfo("Done", f"Converted {success} file(s)!\nOutput: {self.output_dir.get()}")
    
    def cancel_conversion(self):
        self.cancel_flag = True; self.status_label.config(text="Cancelling...")
        with self.process_lock:
            if self.current_process:
                try: self.current_process.kill()
                except: pass
    
    def check_ffmpeg(self):
        try:
            r = subprocess.run(["ffmpeg","-version"], capture_output=True, text=True)
            if r.returncode != 0: raise FileNotFoundError
        except: messagebox.showerror("FFmpeg Not Found", "Install FFmpeg and add to PATH")
    
    # === Settings ===
    def load_settings(self):
        try:
            sf = Path.home() / ".atmos_converter_settings.json"
            if sf.exists():
                s = json.loads(sf.read_text())
                if 'output_dir' in s and os.path.isdir(s['output_dir']): self.output_dir.set(s['output_dir'])
                if 'quality' in s: self.quality.set(s['quality'])
                if 'method' in s:
                    rm = {v:k for k,v in METHOD_PRESETS.items()}
                    if s['method'] in rm: self.method.set(rm[s['method']])
        except: pass
    
    def save_settings(self):
        try:
            s = {'output_dir': self.output_dir.get(), 'quality': self.quality.get(), 'method': METHOD_PRESETS.get(self.method.get(), 'enhanced')}
            (Path.home() / ".atmos_converter_settings.json").write_text(json.dumps(s, indent=2))
        except: pass
    
    def on_closing(self):
        if self.is_converting:
            if not messagebox.askyesno("Cancel?", "Conversion running. Exit?"): return
            self.cancel_conversion()
        self.save_settings(); self.root.destroy()


def main():
    root = tk.Tk()
    app = AtmosConverterGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
