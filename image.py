import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
from PIL import Image
import csv
import math
import time
import json
import threading
import pyautogui
import pyperclip
import os
import re
import sys

pyautogui.FAILSAFE = True 

# === FIX: Auto-detect script location ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, 'blocks.csv')

# Optional: Print debug info (remove after testing)
print(f"Script location: {SCRIPT_DIR}")
print(f"CSV file path: {CSV_FILE}")
print(f"CSV exists: {os.path.exists(CSV_FILE)}")

COMMANDS_PER_FILE = 500
FILES_PER_BATCH = 5

# ⛔ BLOCK BLACKLIST - These blocks will NEVER be used
BLOCK_BLACKLIST = {
    'minecraft:tnt', 'minecraft:redstone_ore', 'minecraft:deepslate_redstone_ore',
    'minecraft:redstone_block', 'minecraft:redstone_torch', 'minecraft:redstone_lamp',
    'minecraft:redstone_wire', 'minecraft:repeater', 'minecraft:comparator',
    'minecraft:observer', 'minecraft:piston', 'minecraft:sticky_piston',
    'minecraft:fire', 'minecraft:soul_fire', 'minecraft:lava', 'minecraft:flowing_lava',
    'minecraft:water', 'minecraft:flowing_water', 'minecraft:bedrock',
    'minecraft:command_block', 'minecraft:repeating_command_block',
    'minecraft:chain_command_block', 'minecraft:structure_block',
    'minecraft:barrier', 'minecraft:spawner', 'minecraft:end_portal_frame',
    'minecraft:end_portal', 'minecraft:nether_portal',
}

class BlockColorMatcher:
    def __init__(self, csv_path):
        self.blocks = []
        self.color_cache = {}
        self.load_csv(csv_path)

    def load_csv(self, csv_path):
        """Load blocks from CSV with min/max color ranges"""
        try:
            with open(csv_path, mode='r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row['block_name']
                    
                    # Skip blacklisted blocks
                    if name in BLOCK_BLACKLIST:
                        continue
                    
                    min_c = tuple(int(row['min_hex'][i:i+2], 16) for i in (0, 2, 4))
                    max_c = tuple(int(row['max_hex'][i:i+2], 16) for i in (0, 2, 4))
                    
                    # Use average of min and max as the block's color
                    avg_c = tuple((min_c[i] + max_c[i]) // 2 for i in range(3))
                    
                    self.blocks.append({
                        'name': name,
                        'color': avg_c,
                        'min': min_c,
                        'max': max_c,
                        'is_falling': name in ['minecraft:sand', 'minecraft:red_sand', 'minecraft:gravel', 
                            'minecraft:suspicious_sand', 'minecraft:suspicious_gravel', 
                            'minecraft:powder_snow', 'minecraft:anvil', 'minecraft:chipped_anvil', 
                            'minecraft:damaged_anvil', 'minecraft:dragon_egg', 'minecraft:pointed_dripstone',
                            'minecraft:white_concrete_powder', 'minecraft:orange_concrete_powder',
                            'minecraft:magenta_concrete_powder', 'minecraft:light_blue_concrete_powder',
                            'minecraft:yellow_concrete_powder', 'minecraft:lime_concrete_powder',
                            'minecraft:pink_concrete_powder', 'minecraft:gray_concrete_powder',
                            'minecraft:light_gray_concrete_powder', 'minecraft:cyan_concrete_powder',
                            'minecraft:purple_concrete_powder', 'minecraft:blue_concrete_powder',
                            'minecraft:brown_concrete_powder', 'minecraft:green_concrete_powder',
                            'minecraft:red_concrete_powder', 'minecraft:black_concrete_powder']
                    })
            
            print(f"✅ Loaded {len(self.blocks)} blocks from CSV")
            
            # If no blocks loaded, use fallback
            if not self.blocks:
                self.load_fallback_colors()
                
        except Exception as e:
            print(f"Error loading CSV: {e}")
            self.load_fallback_colors()

    def load_fallback_colors(self):
        """Fallback colors if CSV fails"""
        fallback_blocks = [
            ('minecraft:white_concrete', '#CFD5D6'),
            ('minecraft:black_concrete', '#121212'),
            ('minecraft:red_concrete', '#8A3030'),
            ('minecraft:blue_concrete', '#303A8A'),
            ('minecraft:green_concrete', '#3A4E26'),
            ('minecraft:yellow_concrete', '#C4B230'),
        ]
        
        for name, hex_color in fallback_blocks:
            if name not in BLOCK_BLACKLIST:
                hex_color_clean = hex_color.lstrip('#')
                color = tuple(int(hex_color_clean[i:i+2], 16) for i in (0, 2, 4))
                self.blocks.append({
                    'name': name,
                    'color': color,
                    'min': color,
                    'max': color,
                    'is_falling': False
                })
        
        print(f"Loaded {len(self.blocks)} fallback blocks")

    def color_distance(self, color1, color2):
        """Calculate Euclidean distance between two colors"""
        return (color1[0] - color2[0])**2 + (color1[1] - color2[1])**2 + (color1[2] - color2[2])**2

    def get_best_block(self, pixel_rgb):
        """Find the closest matching block"""
        if pixel_rgb in self.color_cache:
            return self.color_cache[pixel_rgb]
        
        best_block = self.blocks[0]
        best_distance = float('inf')
        
        for block in self.blocks:
            dist = self.color_distance(pixel_rgb, block['color'])
            if dist < best_distance:
                best_distance = dist
                best_block = block
        
        self.color_cache[pixel_rgb] = best_block['name']
        return best_block['name']

class MinecraftPixelArtApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Art Builder - Pixel-by-Pixel Accuracy")
        self.root.geometry("700x1000")
        
        self.matcher = BlockColorMatcher(CSV_FILE)
        self.img = None
        self.block_grid = None
        self.grid_width = 0
        self.grid_height = 0
        self.is_building = False
        
        self.build_gui()

    def build_gui(self):
        # --- Image & JSON ---
        frm_io = ttk.LabelFrame(self.root, text="1. Image & Map Data")
        frm_io.pack(pady=5, padx=10, fill='x')
        
        self.btn_upload = ttk.Button(frm_io, text="Upload Image", command=self.upload_image)
        self.btn_upload.grid(row=0, column=0, padx=5, pady=5)
        self.btn_preview = ttk.Button(frm_io, text="Preview", command=self.preview_image, state='disabled')
        self.btn_preview.grid(row=0, column=1, padx=5, pady=5)
        self.btn_report = ttk.Button(frm_io, text="Color Report", command=self.color_report, state='disabled')
        self.btn_report.grid(row=0, column=2, padx=5, pady=5)
        self.btn_save = ttk.Button(frm_io, text="Save JSON", command=self.save_json, state='disabled')
        self.btn_save.grid(row=0, column=3, padx=5, pady=5)
        self.btn_load = ttk.Button(frm_io, text="Load JSON", command=self.load_json)
        self.btn_load.grid(row=0, column=4, padx=5, pady=5)
        
        self.lbl_img_status = ttk.Label(frm_io, text="No data loaded")
        self.lbl_img_status.grid(row=1, column=0, columnspan=5, padx=5)

        # --- Resolution ---
        frm_res = ttk.LabelFrame(self.root, text="2. Resolution (Width x Height)")
        frm_res.pack(pady=5, padx=10, fill='x')
        
        ttk.Label(frm_res, text="Width:").pack(side='left', padx=5)
        self.var_width = tk.IntVar(value=64)
        ttk.Spinbox(frm_res, from_=8, to=2048, textvariable=self.var_width, width=6).pack(side='left', padx=5)
        
        ttk.Label(frm_res, text="Height:").pack(side='left', padx=5)
        self.var_height = tk.IntVar(value=64)
        ttk.Spinbox(frm_res, from_=8, to=2048, textvariable=self.var_height, width=6).pack(side='left', padx=5)
        
        self.lbl_total_blocks = ttk.Label(frm_res, text="Total: --")
        self.lbl_total_blocks.pack(side='left', padx=15)

        # --- Position ---
        frm_pos = ttk.LabelFrame(self.root, text="3. Wall Position (Bottom-Left Corner)")
        frm_pos.pack(pady=5, padx=10, fill='x')
        frm_coords = ttk.Frame(frm_pos)
        frm_coords.pack(pady=5)
        
        ttk.Label(frm_coords, text="Start X:").grid(row=0, column=0, padx=2)
        self.var_x = tk.IntVar(value=0)
        ttk.Entry(frm_coords, textvariable=self.var_x, width=8).grid(row=0, column=1, padx=2)
        
        ttk.Label(frm_coords, text="Bottom Y:").grid(row=0, column=2, padx=2)
        self.var_y = tk.IntVar(value=100)
        ttk.Entry(frm_coords, textvariable=self.var_y, width=8).grid(row=0, column=3, padx=2)
        
        ttk.Label(frm_coords, text="Start Z:").grid(row=0, column=4, padx=2)
        self.var_z = tk.IntVar(value=0)
        ttk.Entry(frm_coords, textvariable=self.var_z, width=8).grid(row=0, column=5, padx=2)
        
        ttk.Label(frm_coords, text="Facing:").grid(row=1, column=0, padx=2, pady=5)
        self.var_facing = tk.StringVar(value="South")
        ttk.Combobox(frm_coords, textvariable=self.var_facing, 
                    values=["South", "North", "East", "West"], width=10).grid(row=1, column=1, padx=2)

        # --- Build Strategy ---
        frm_strategy = ttk.LabelFrame(self.root, text="4. Build Strategy")
        frm_strategy.pack(pady=5, padx=10, fill='x')
        
        self.var_use_fill = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm_strategy, text="Use /fill for horizontal runs (faster)", 
                       variable=self.var_use_fill).pack(anchor='w', padx=5)
        
        ttk.Label(frm_strategy, text="Background Color:").pack(anchor='w', padx=5)
        self.var_background = tk.StringVar(value="minecraft:black_concrete")
        bg_colors = [
            "minecraft:black_concrete", "minecraft:white_concrete",
            "minecraft:gray_concrete", "minecraft:stone", "minecraft:blackstone"
        ]
        ttk.Combobox(frm_strategy, textvariable=self.var_background, 
                    values=bg_colors, width=30).pack(anchor='w', padx=5)

        # --- Execution Method ---
        frm_exec = ttk.LabelFrame(self.root, text="5. Execution Method")
        frm_exec.pack(pady=5, padx=10, fill='x')
        
        self.var_method = tk.StringVar(value="datapack")
        methods = [
            ("🚀 Generate Datapack (Recommended)", "datapack"),
            ("📋 Copy to Clipboard", "clipboard"),
            ("💾 Export Commands File (.txt)", "file")
        ]
        
        for text, value in methods:
            ttk.Radiobutton(frm_exec, text=text, variable=self.var_method, 
                          value=value).pack(anchor='w', padx=5)

        # --- Progress ---
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.pack(pady=5)

        # --- Countdown ---
        self.lbl_countdown = tk.Label(self.root, text="", font=("Helvetica", 24, "bold"), fg="red")
        self.lbl_countdown.pack(pady=2)

        # --- Controls ---
        frm_ctrl = ttk.Frame(self.root)
        frm_ctrl.pack(pady=5)
        self.btn_start = ttk.Button(frm_ctrl, text="Start Building", command=self.start_building)
        self.btn_start.pack(side='left', padx=10)
        self.btn_stop = ttk.Button(frm_ctrl, text="STOP", command=self.stop_building, state='disabled')
        self.btn_stop.pack(side='left', padx=10)
        self.btn_export = ttk.Button(frm_ctrl, text="Export Commands", command=self.export_commands, state='disabled')
        self.btn_export.pack(side='left', padx=10)

        # --- Log ---
        self.txt_log = scrolledtext.ScrolledText(self.root, height=10, state='disabled')
        self.txt_log.pack(pady=5, padx=10, fill='both', expand=True)

    def log(self, message):
        self.txt_log.config(state='normal')
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state='disabled')

    def sanitize_namespace(self, name):
        name = name.lower()
        name = name.replace(" ", "_")
        name = re.sub(r'[^a-z0-9_]', '', name)
        if not name:
            name = "pixel_art"
        return name

    def upload_image(self):
        path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if path:
            self.log(f"Loading image: {path.split('/')[-1]}")
            self.img = Image.open(path).convert("RGB")
            self.block_grid = None
            self.lbl_img_status.config(text=path.split('/')[-1])
            self.process_image()

    def process_image(self):
        if not self.img: return
        w = self.var_width.get()
        h = self.var_height.get()
        
        total = w * h
        self.log(f"Processing {w}x{h} = {total:,} blocks...")
        
        if total > 1000000:
            self.log("⚠️ Large image, may take a moment...")
        
        resized_img = self.img.resize((w, h), Image.NEAREST)
        pixels = resized_img.load()
        
        self.block_grid = []
        for y in range(h):
            row = []
            for x in range(w):
                pixel_rgb = pixels[x, y]
                block = self.matcher.get_best_block(pixel_rgb)
                row.append(block)
            self.block_grid.append(row)
            
        self.grid_width = w
        self.grid_height = h
        self.lbl_total_blocks.config(text=f"Total: {total:,}")
        self.log(f"✅ Calculation complete: {w}x{h} = {total:,} blocks")
        self.btn_save.config(state='normal')
        self.btn_preview.config(state='normal')
        self.btn_report.config(state='normal')
        self.btn_export.config(state='normal')

    def generate_pixel_by_pixel_commands(self):
        """Generate commands pixel by pixel for 100% accuracy"""
        self.log("Generating pixel-by-pixel commands...")
        commands = []
        h = self.grid_height
        w = self.grid_width
        x0 = self.var_x.get()
        y0 = self.var_y.get()
        z0 = self.var_z.get()
        facing = self.var_facing.get()
        use_fill = self.var_use_fill.get()
        background = self.var_background.get()
        
        # Add background wall
        if facing == "South":
            x1, z1 = x0, z0
            x2, z2 = x0 + w - 1, z0
            y1, y2 = y0, y0 + h - 1
        elif facing == "North":
            x1, z1 = x0, z0 - 1
            x2, z2 = x0 + w - 1, z0 - 1
            y1, y2 = y0, y0 + h - 1
        elif facing == "East":
            x1, z1 = x0 + 1, z0
            x2, z2 = x0 + 1, z0 + h - 1
            y1, y2 = y0, y0 + w - 1
        else:  # West
            x1, z1 = x0 - 1, z0
            x2, z2 = x0 - 1, z0 + h - 1
            y1, y2 = y0, y0 + w - 1
        
        commands.append(f"/fill {x1} {y1} {z1} {x2} {y2} {z2} {background}")
        
        # Process each row pixel by pixel
        total_blocks = 0
        fill_count = 0
        setblock_count = 0
        
        for row in range(h):
            if not self.is_building:
                break
            
            # Flip Y (image loads top-down, Minecraft Y goes up)
            mc_y = y0 + (h - 1 - row)
            
            col = 0
            while col < w:
                block = self.block_grid[row][col]
                
                # Skip background blocks
                if block == background:
                    col += 1
                    continue
                
                # Find horizontal run of same block
                run_start = col
                run_end = col
                while run_end + 1 < w and self.block_grid[row][run_end + 1] == block:
                    run_end += 1
                
                run_length = run_end - run_start + 1
                
                # Place commands based on facing
                if facing == "South":
                    mc_x_start = x0 + run_start
                    mc_x_end = x0 + run_end
                    mc_z = z0
                    
                    if use_fill and run_length > 1:
                        commands.append(f"/fill {mc_x_start} {mc_y} {mc_z} {mc_x_end} {mc_y} {mc_z} {block}")
                        fill_count += 1
                    else:
                        for x in range(run_start, run_end + 1):
                            commands.append(f"/setblock {x0 + x} {mc_y} {mc_z} {block}")
                            setblock_count += 1
                
                elif facing == "North":
                    mc_x_start = x0 + run_start
                    mc_x_end = x0 + run_end
                    mc_z = z0 - 1
                    
                    if use_fill and run_length > 1:
                        commands.append(f"/fill {mc_x_start} {mc_y} {mc_z} {mc_x_end} {mc_y} {mc_z} {block}")
                        fill_count += 1
                    else:
                        for x in range(run_start, run_end + 1):
                            commands.append(f"/setblock {x0 + x} {mc_y} {mc_z} {block}")
                            setblock_count += 1
                
                elif facing == "East":
                    mc_x = x0 + 1
                    
                    if use_fill and run_length > 1:
                        commands.append(f"/fill {mc_x} {y0 + run_start} {z0 + row} {mc_x} {y0 + run_end} {z0 + row} {block}")
                        fill_count += 1
                    else:
                        for x in range(run_start, run_end + 1):
                            commands.append(f"/setblock {mc_x} {y0 + x} {z0 + row} {block}")
                            setblock_count += 1
                
                else:  # West
                    mc_x = x0 - 1
                    
                    if use_fill and run_length > 1:
                        commands.append(f"/fill {mc_x} {y0 + run_start} {z0 + row} {mc_x} {y0 + run_end} {z0 + row} {block}")
                        fill_count += 1
                    else:
                        for x in range(run_start, run_end + 1):
                            commands.append(f"/setblock {mc_x} {y0 + x} {z0 + row} {block}")
                            setblock_count += 1
                
                total_blocks += run_length
                col = run_end + 1
            
            # Progress update
            if row % 10 == 0:
                self.log(f"Progress: row {row+1}/{h}")
        
        self.log(f"Generated {len(commands)} commands for {total_blocks} blocks")
        self.log(f"  /fill commands: {fill_count}, /setblock commands: {setblock_count}")
        return commands

    def preview_image(self):
        if not self.block_grid: 
            return
        
        preview = tk.Toplevel(self.root)
        preview.title("Block Preview - Mouse Wheel Zoom")
        preview.geometry("800x800")
        
        frame = ttk.Frame(preview)
        frame.pack(fill='both', expand=True)
        
        canvas = tk.Canvas(frame, bg='white')
        h_scroll = ttk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
        v_scroll = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
        
        canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        h_scroll.pack(side='bottom', fill='x')
        v_scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        
        # Build color map
        color_map = {}
        for block in self.matcher.blocks:
            hex_color = f"#{block['color'][0]:02x}{block['color'][1]:02x}{block['color'][2]:02x}"
            color_map[block['name']] = hex_color
        
        scale = min(700 / self.grid_width, 700 / self.grid_height, 10)
        scale = max(scale, 1)
        
        def draw_preview(scale_factor):
            canvas.delete('all')
            canvas.config(scrollregion=(0, 0, self.grid_width * scale_factor, self.grid_height * scale_factor))
            
            for y in range(self.grid_height):
                for x in range(self.grid_width):
                    block = self.block_grid[y][x]
                    color = color_map.get(block, '#FF00FF')
                    x1 = x * scale_factor
                    y1 = y * scale_factor
                    x2 = x1 + scale_factor
                    y2 = y1 + scale_factor
                    canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline='')
        
        draw_preview(scale)
        
        def on_mousewheel(event):
            nonlocal scale
            if event.delta > 0:
                scale = min(scale * 1.2, 50)
            else:
                scale = max(scale / 1.2, 1)
            draw_preview(scale)
        
        canvas.bind('<MouseWheel>', on_mousewheel)
        
        info_label = ttk.Label(preview, text=f"{self.grid_width}×{self.grid_height} | {self.grid_width*self.grid_height:,} blocks")
        info_label.pack()

    def color_report(self):
        if not self.block_grid:
            return
        
        block_count = {}
        for row in self.block_grid:
            for block in row:
                block_count[block] = block_count.get(block, 0) + 1
        
        report = tk.Toplevel(self.root)
        report.title("Block Usage Report")
        report.geometry("700x800")
        
        text_widget = scrolledtext.ScrolledText(report, width=80, height=45)
        text_widget.pack(padx=10, pady=10, fill='both', expand=True)
        
        total = self.grid_width * self.grid_height
        text_widget.insert(tk.END, "=" * 70 + "\n")
        text_widget.insert(tk.END, "         MINECRAFT BLOCK USAGE REPORT\n")
        text_widget.insert(tk.END, "=" * 70 + "\n\n")
        text_widget.insert(tk.END, f"Image Resolution: {self.grid_width} × {self.grid_height}\n")
        text_widget.insert(tk.END, f"Total Blocks: {total:,}\n")
        text_widget.insert(tk.END, f"Unique Block Types: {len(block_count)}\n\n")
        
        text_widget.insert(tk.END, "-" * 70 + "\n")
        text_widget.insert(tk.END, f"{'Block Name':<40} {'Count':>12} {'%':>8} {'Visual'}\n")
        text_widget.insert(tk.END, "-" * 70 + "\n")
        
        for block, count in sorted(block_count.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total) * 100
            short_name = block.replace('minecraft:', '')
            bar_length = int(percentage / 2)
            bar = '█' * bar_length + '░' * (50 - bar_length)
            text_widget.insert(tk.END, f"{short_name:<40} {count:>12,} {percentage:>7.1f}% {bar[:35]}\n")
        
        text_widget.config(state='disabled')

    def export_commands(self):
        commands = self.generate_pixel_by_pixel_commands()
        
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("MCFunction Files", "*.mcfunction"),
                ("All Files", "*.*")
            ]
        )
        if not path:
            return
        
        with open(path, 'w') as f:
            f.write("# Minecraft Pixel Art Commands\n")
            f.write(f"# Size: {self.grid_width}x{self.grid_height}\n")
            f.write(f"# Total Blocks: {self.grid_width * self.grid_height:,}\n")
            f.write(f"# Commands: {len(commands):,}\n")
            f.write(f"# Position: {self.var_x.get()}, {self.var_y.get()}, {self.var_z.get()}\n")
            f.write(f"# Facing: {self.var_facing.get()}\n\n")
            f.write("\n".join(commands))
        
        self.log(f"✅ Exported {len(commands):,} commands to {path.split('/')[-1]}")

    def save_json(self):
        if not self.block_grid: 
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, 'w') as f:
                json.dump({
                    'width': self.grid_width, 
                    'height': self.grid_height, 
                    'block_grid': self.block_grid
                }, f)
            self.log(f"✅ Saved to {path.split('/')[-1]}")

    def load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            with open(path, 'r') as f: 
                data = json.load(f)
            self.grid_width = data['width']
            self.grid_height = data['height']
            self.block_grid = data['block_grid']
            self.var_width.set(self.grid_width)
            self.var_height.set(self.grid_height)
            self.lbl_total_blocks.config(text=f"Total: {self.grid_width * self.grid_height:,}")
            self.lbl_img_status.config(text=f"Loaded: {path.split('/')[-1]}")
            self.img = None
            self.btn_save.config(state='normal')
            self.btn_preview.config(state='normal')
            self.btn_report.config(state='normal')
            self.btn_export.config(state='normal')
            self.log(f"✅ Loaded JSON: {self.grid_width}x{self.grid_height}")

    def split_commands_into_files(self, commands, max_per_file=500):
        files = []
        total = len(commands)
        num_files = math.ceil(total / max_per_file)
        
        for i in range(num_files):
            start = i * max_per_file
            end = min(start + max_per_file, total)
            chunk = commands[start:end]
            files.append({
                'name': f'build_{i}',
                'commands': chunk,
                'count': len(chunk)
            })
        
        return files

    def create_datapack(self, commands):
        """Create a split datapack with batched execution"""
        name_window = tk.Toplevel(self.root)
        name_window.title("Datapack Name")
        name_window.geometry("450x200")
        
        ttk.Label(name_window, text="Datapack Name (lowercase, no spaces):").pack(pady=10)
        ttk.Label(name_window, text="Example: pixel_art, my_build, castle", foreground="gray").pack()
        
        name_var = tk.StringVar(value="pixel_art")
        name_entry = ttk.Entry(name_window, textvariable=name_var, width=30)
        name_entry.pack(pady=5)
        
        preview_label = ttk.Label(name_window, text="Will be: pixel_art", foreground="green")
        preview_label.pack(pady=5)
        
        def update_preview(*args):
            sanitized = self.sanitize_namespace(name_var.get())
            if sanitized != name_var.get():
                preview_label.config(text=f"⚠️ Will be sanitized to: {sanitized}", foreground="orange")
            else:
                preview_label.config(text=f"✅ Valid: {sanitized}", foreground="green")
        
        name_var.trace_add('write', update_preview)
        
        result = {"name": None}
        
        def confirm():
            raw_name = name_var.get()
            sanitized = self.sanitize_namespace(raw_name)
            if sanitized != raw_name:
                self.log(f"⚠️ Sanitized '{raw_name}' → '{sanitized}'")
            result["name"] = sanitized
            name_window.destroy()
        
        ttk.Button(name_window, text="Create Datapack", command=confirm).pack(pady=10)
        name_window.transient(self.root)
        name_window.grab_set()
        self.root.wait_window(name_window)
        
        if not result["name"]:
            return
        
        folder = filedialog.askdirectory(title="Select Minecraft 'datapacks' folder")
        if not folder:
            return
        
        datapack_name = result["name"]
        datapack_path = f"{folder}/{datapack_name}"
        
        os.makedirs(f"{datapack_path}/data/{datapack_name}/function", exist_ok=True)
        
        # Create pack.mcmeta
        pack_mcmeta = {
            "pack": {
                "pack_format": 105,
                "description": f"Pixel Art Build - {datapack_name}"
            }
        }
        with open(f"{datapack_path}/pack.mcmeta", 'w') as f:
            json.dump(pack_mcmeta, f, indent=2)
        
        # Clean commands (remove /)
        clean_commands = []
        for cmd in commands:
            if cmd.startswith('/'):
                clean_commands.append(cmd[1:])
            else:
                clean_commands.append(cmd)
        
        # Split into multiple files
        files = self.split_commands_into_files(clean_commands, COMMANDS_PER_FILE)
        
        self.log(f"Splitting {len(clean_commands):,} commands into {len(files)} files...")
        
        # Create BATCH functions
        num_files = len(files)
        num_batches = math.ceil(num_files / FILES_PER_BATCH)
        
        for batch_num in range(num_batches):
            start_idx = batch_num * FILES_PER_BATCH
            end_idx = min(start_idx + FILES_PER_BATCH, num_files)
            batch_files = files[start_idx:end_idx]
            
            batch_name = f'batch_{batch_num}'
            batch_path = f"{datapack_path}/data/{datapack_name}/function/{batch_name}.mcfunction"
            
            with open(batch_path, 'w') as f:
                f.write(f"# Batch {batch_num}\n")
                for file_info in batch_files:
                    f.write(f"function {datapack_name}:{file_info['name']}\n")
                if batch_num < num_batches - 1:
                    f.write(f"function {datapack_name}:batch_{batch_num + 1}\n")
        
        # Create individual function files
        for file_info in files:
            file_path = f"{datapack_path}/data/{datapack_name}/function/{file_info['name']}.mcfunction"
            with open(file_path, 'w') as f:
                f.write("\n".join(file_info['commands']))
        
        # Create main function
        main_path = f"{datapack_path}/data/{datapack_name}/function/build.mcfunction"
        with open(main_path, 'w') as f:
            f.write(f"function {datapack_name}:batch_0\n")
        
        self.log("=" * 70)
        self.log("✅ DATAPACK CREATED!")
        self.log(f"📁 Location: {datapack_path}")
        self.log(f"📄 Total Commands: {len(clean_commands):,}")
        self.log(f"📄 Split into {num_files} files, {num_batches} batches")
        self.log("")
        self.log("📋 INSTRUCTIONS:")
        self.log(f"1. In Minecraft: /reload")
        self.log(f"2. Run: /function {datapack_name}:build")
        self.log("=" * 70)

    def start_building(self):
        if not self.block_grid: 
            self.log("❌ ERROR: Load/Upload data first!")
            return
        
        self.is_building = True
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        
        # Generate commands
        commands = self.generate_pixel_by_pixel_commands()
        
        method = self.var_method.get()
        
        if method == "datapack":
            self.create_datapack(commands)
        elif method == "clipboard":
            self.copy_to_clipboard(commands)
        elif method == "file":
            self.save_to_file(commands)
        
        self.is_building = False
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')

    def copy_to_clipboard(self, commands):
        full_text = "\n".join(commands)
        pyperclip.copy(full_text)
        
        self.log("=" * 70)
        self.log("✅ COMMANDS COPIED TO CLIPBOARD!")
        self.log(f"Total: {len(commands):,} commands")
        self.log("")
        self.log("📋 Go to Minecraft, open chat, paste, and press Enter!")
        self.log("=" * 70)

    def save_to_file(self, commands):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")]
        )
        if path:
            with open(path, 'w') as f:
                f.write("\n".join(commands))
            self.log(f"✅ Saved {len(commands):,} commands to {path.split('/')[-1]}")

    def stop_building(self):
        self.is_building = False

if __name__ == "__main__":
    root = tk.Tk()
    app = MinecraftPixelArtApp(root)
    root.mainloop()
