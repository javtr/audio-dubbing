import customtkinter as ctk

class TopBar(ctk.CTkFrame):
    """Barra superior que contiene el selector de proyectos, estado de Pinokio y botón para liberar VRAM."""

    def __init__(self, master, on_project_changed, on_new_project, on_check_pinokio, on_free_vram, **kwargs):
        super().__init__(master, height=65, corner_radius=0, fg_color="#1e1e1e", **kwargs)
        self.on_project_changed = on_project_changed
        self.on_new_project = on_new_project
        self.on_check_pinokio = on_check_pinokio
        self.on_free_vram = on_free_vram

        self._build_ui()

    def _build_ui(self):
        # Título
        lbl_app = ctk.CTkLabel(self, text="Audio Dubbing Studio", font=("Arial", 18, "bold"), text_color="#3B8ED0")
        lbl_app.pack(side="left", padx=(20, 15), pady=15)

        # Selector de Proyecto
        ctk.CTkLabel(self, text="Proyecto:", font=("Arial", 12)).pack(side="left", padx=(10, 5))
        self.opt_project = ctk.CTkOptionMenu(
            self,
            values=["(Sin proyectos)"],
            width=220,
            command=self.on_project_changed
        )
        self.opt_project.pack(side="left", padx=5)

        btn_new_proj = ctk.CTkButton(
            self,
            text="➕ Nuevo",
            width=85,
            fg_color="#28a745",
            hover_color="#218838",
            command=self.on_new_project
        )
        btn_new_proj.pack(side="left", padx=5)

        # Estado de Pinokio y VRAM
        pinokio_frame = ctk.CTkFrame(self, fg_color="transparent")
        pinokio_frame.pack(side="right", padx=20)

        self.lbl_pinokio = ctk.CTkLabel(
            pinokio_frame,
            text="● Verificando Pinokio...",
            text_color="#aaaaaa",
            font=("Arial", 12)
        )
        self.lbl_pinokio.pack(side="left", padx=(0, 8))

        btn_check_pinokio = ctk.CTkButton(
            pinokio_frame,
            text="🔄",
            width=32,
            height=28,
            fg_color="#333333",
            command=self.on_check_pinokio
        )
        btn_check_pinokio.pack(side="left", padx=(0, 6))

        btn_free_vram = ctk.CTkButton(
            pinokio_frame,
            text="🧹 Liberar VRAM",
            width=105,
            height=28,
            fg_color="#37474f",
            hover_color="#263238",
            command=self.on_free_vram
        )
        btn_free_vram.pack(side="left")

    def update_project_list(self, projects, select_project=None):
        vals = projects if projects else ["(Sin proyectos)"]
        self.opt_project.configure(values=vals)
        target = select_project if select_project in vals else vals[0]
        self.opt_project.set(target)

    def set_pinokio_status(self, online):
        if online:
            self.lbl_pinokio.configure(text="● Pinokio Online", text_color="#28a745")
        else:
            self.lbl_pinokio.configure(text="● Pinokio Offline (127.0.0.1:7860)", text_color="#e57373")
