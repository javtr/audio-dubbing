import customtkinter as ctk

class DubbingPromptDialog(ctk.CTkToplevel):
    """Diálogo modal para decidir entre generar solo faltantes o reemplazar todos."""

    def __init__(self, parent, existing_count, missing_count, total_count):
        super().__init__(parent)
        self.title("Segmentos Existentes Detectados")
        self.geometry("520x300")
        self.resizable(False, False)
        self.result = None

        self.transient(parent)
        self.grab_set()

        # Centrar sobre el padre si es posible
        try:
            parent.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = px + max(0, (pw - 520) // 2)
            y = py + max(0, (ph - 300) // 2)
            self.geometry(f"520x300+{x}+{y}")
        except Exception:
            pass

        # Encabezado con ícono
        lbl_title = ctk.CTkLabel(
            self,
            text="🎙️ Audios Existentes Detectados",
            font=("Arial", 16, "bold"),
            text_color="#38bdf8"
        )
        lbl_title.pack(pady=(20, 8))

        # Mensaje informativo
        msg = (
            f"Se encontraron {existing_count} segmentos ya generados en este proyecto.\n"
            f"Quedan {missing_count} segmentos pendientes de generar (Total: {total_count}).\n\n"
            "¿Cómo deseas proceder con la generación en Pinokio?"
        )
        lbl_msg = ctk.CTkLabel(
            self,
            text=msg,
            font=("Arial", 13),
            justify="center"
        )
        lbl_msg.pack(padx=25, pady=(0, 20))

        # Botones de Acción
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=35, pady=0)

        # 1. Solo Faltantes (Opción recomendada)
        btn_missing = ctk.CTkButton(
            btn_frame,
            text=f"⚡ Solo los que faltan ({missing_count})",
            font=("Arial", 13, "bold"),
            fg_color="#28a745",
            hover_color="#218838",
            height=38,
            command=self._on_missing
        )
        btn_missing.pack(fill="x", pady=4)

        # 2. Reemplazar Todos
        btn_all = ctk.CTkButton(
            btn_frame,
            text=f"🔄 Reemplazar todos ({total_count})",
            font=("Arial", 13, "bold"),
            fg_color="#d97706",
            hover_color="#b45309",
            height=38,
            command=self._on_all
        )
        btn_all.pack(fill="x", pady=4)

        # 3. Cancelar
        btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Cancelar",
            font=("Arial", 12),
            fg_color="#475569",
            hover_color="#334155",
            height=32,
            command=self._on_cancel
        )
        btn_cancel.pack(fill="x", pady=(4, 15))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_missing(self):
        self.result = "missing"
        self.destroy()

    def _on_all(self):
        self.result = "all"
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        """Bloquea hasta que el usuario elija una opción y retorna el resultado."""
        self.wait_window(self)
        return self.result
