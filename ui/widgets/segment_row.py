import customtkinter as ctk

class SegmentRow(ctk.CTkFrame):
    """Fila de ajuste fino para cada segmento en la Pestaña 3 (Estudio y Mezcla)."""

    def __init__(self, master, segment_data, ratio, on_play_callback, on_select_callback, on_adjust_callback, is_selected=False, **kwargs):
        border_w = 2 if is_selected else 0
        border_c = "#ffe600" if is_selected else "#3d3d3d"
        super().__init__(master, border_width=border_w, border_color=border_c, **kwargs)

        self.segment = segment_data
        self.ratio = ratio
        self.on_play_callback = on_play_callback
        self.on_select_callback = on_select_callback
        self.on_adjust_callback = on_adjust_callback

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(2, weight=1)

        # Botón de reproducción de fragmento
        self.btn_play = ctk.CTkButton(self, text="▶", width=30)
        self.btn_play.configure(command=lambda: self.on_play_callback(self.segment, self.btn_play))
        self.btn_play.grid(row=0, column=0, padx=5, pady=4)

        # Nombre de archivo (clic para seleccionar)
        self.lbl_file = ctk.CTkLabel(self, text=self.segment.get("filename", ""), width=95, anchor="w", cursor="hand2")
        self.lbl_file.grid(row=0, column=1, padx=4, pady=4)
        self.lbl_file.bind("<Button-1>", lambda e: self.on_select_callback(self.segment))

        # Texto traducido (clic para seleccionar)
        self.lbl_text = ctk.CTkLabel(self, text=self.segment.get("translated", ""), wraplength=400, justify="left", anchor="w", cursor="hand2")
        self.lbl_text.grid(row=0, column=2, padx=8, pady=4, sticky="ew")
        self.lbl_text.bind("<Button-1>", lambda e: self.on_select_callback(self.segment))

        # Controles numéricos
        ctrls = ctk.CTkFrame(self, fg_color="transparent")
        ctrls.grid(row=0, column=3, padx=5, pady=4, sticky="e")

        ctk.CTkLabel(ctrls, text="Inicio:").pack(side="left", padx=2)
        self.ent_start = ctk.CTkEntry(ctrls, width=70)
        self.ent_start.insert(0, str(self.segment.get("start_ms", 0)))
        self.ent_start.pack(side="left", padx=2)

        end_ms = self.segment.get('end_ms', 0)
        ctk.CTkLabel(ctrls, text=f"Fin: {end_ms}ms", text_color="#aaaaaa").pack(side="left", padx=6)

        ctk.CTkLabel(ctrls, text="Ratio:").pack(side="left", padx=2)
        self.ent_ratio = ctk.CTkEntry(ctrls, width=55)
        self.ent_ratio.insert(0, f"{self.ratio:.2f}")
        self.ent_ratio.pack(side="left", padx=2)

        btn_gen = ctk.CTkButton(
            ctrls,
            text="Ajustar",
            width=70,
            command=lambda: self.on_adjust_callback(self.segment, self.ent_ratio)
        )
        btn_gen.pack(side="left", padx=4)

    def get_start_ms(self):
        return int(self.ent_start.get().strip())

    def get_ratio(self):
        return float(self.ent_ratio.get().strip())

    def set_selected(self, is_selected):
        self.configure(
            border_width=2 if is_selected else 0,
            border_color="#ffe600" if is_selected else "#3d3d3d"
        )

    def set_playing(self, is_playing):
        self.btn_play.configure(text="⏹" if is_playing else "▶")
