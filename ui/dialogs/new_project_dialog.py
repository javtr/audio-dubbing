import os
from tkinter import filedialog, messagebox
import customtkinter as ctk

class NewProjectDialog(ctk.CTkToplevel):
    """Diálogo modal para crear un nuevo proyecto."""
    def __init__(self, parent, on_create_callback):
        super().__init__(parent)
        self.title("Crear Nuevo Proyecto")
        self.geometry("520x335")
        self.resizable(False, False)
        self.on_create_callback = on_create_callback
        self.selected_file = None

        self.transient(parent)
        self.grab_set()

        # Nombre del proyecto
        lbl_name = ctk.CTkLabel(self, text="Nombre del Proyecto:", font=("Arial", 13, "bold"))
        lbl_name.pack(anchor="w", padx=25, pady=(15, 5))

        self.ent_name = ctk.CTkEntry(self, placeholder_text="Ej: Tutorial_Volume_Profile", width=470)
        self.ent_name.pack(padx=25, pady=(0, 12))

        # Archivo multimedia (Video o Audio)
        lbl_file = ctk.CTkLabel(self, text="Video (.mp4) o Audio de Entrada:", font=("Arial", 13, "bold"))
        lbl_file.pack(anchor="w", padx=25, pady=(0, 5))

        file_frame = ctk.CTkFrame(self, fg_color="transparent")
        file_frame.pack(fill="x", padx=25, pady=(0, 12))

        self.lbl_selected = ctk.CTkLabel(file_frame, text="Ningún archivo seleccionado", text_color="#aaaaaa", anchor="w")
        self.lbl_selected.pack(side="left", fill="x", expand=True)

        btn_browse = ctk.CTkButton(file_frame, text="Examinar...", width=110, command=self._browse_file)
        btn_browse.pack(side="right")

        # Idioma destino del doblaje
        lbl_lang = ctk.CTkLabel(self, text="Idioma de Doblaje:", font=("Arial", 13, "bold"))
        lbl_lang.pack(anchor="w", padx=25, pady=(0, 5))

        self.seg_lang = ctk.CTkSegmentedButton(
            self,
            values=["Inglés (EN)", "Portugués (PT)"],
            width=470
        )
        self.seg_lang.set("Inglés (EN)")
        self.seg_lang.pack(padx=25, pady=(0, 18))

        # Botones inferiores
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=25, pady=(0, 15))

        btn_cancel = ctk.CTkButton(btn_frame, text="Cancelar", fg_color="#555555", hover_color="#666666", width=120, command=self.destroy)
        btn_cancel.pack(side="left")

        self.btn_create = ctk.CTkButton(btn_frame, text="Crear Proyecto", fg_color="#28a745", hover_color="#218838", width=160, command=self._submit)
        self.btn_create.pack(side="right")

    def _browse_file(self):
        f = filedialog.askopenfilename(
            title="Seleccionar Video o Audio",
            filetypes=[
                ("Archivos Multimedia", "*.mp4 *.mkv *.mov *.avi *.webm *.wav *.mp3 *.m4a *.flac"),
                ("Videos", "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("Audios", "*.wav *.mp3 *.m4a *.flac")
            ]
        )
        if f:
            self.selected_file = f
            self.lbl_selected.configure(text=os.path.basename(f), text_color="#ffffff")
            if not self.ent_name.get().strip():
                base = os.path.splitext(os.path.basename(f))[0]
                self.ent_name.insert(0, base)

    def _submit(self):
        name = self.ent_name.get().strip()
        if not name:
            messagebox.showwarning("Atención", "Por favor ingresa un nombre para el proyecto.")
            return

        lang_code = "pt" if "pt" in str(self.seg_lang.get()).lower() else "en"
        self.btn_create.configure(state="disabled", text="Creando...")
        self.on_create_callback(name, self.selected_file, lang_code)
        self.destroy()
