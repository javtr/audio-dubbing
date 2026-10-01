import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class TimelineCanvas:
    """Componente que encapsula el lienzo de Matplotlib para renderizar una pista de audio (forma de onda)."""

    def __init__(self, master_frame, is_dubbed=False):
        self.master_frame = master_frame
        self.is_dubbed = is_dubbed

        self.fig = None
        self.ax = None
        self.canvas = None
        self.playhead_line = None
        self.razor_line = None
        self.ghost_patch = None

    def draw_waveform(self, samples, color, total_duration_ms, segments=None, selected_segment_id=None, playhead_ms=0, cut_color='#ff5252'):
        """Renderiza la forma de onda y las marcas de cortes en el frame contenedor."""
        for w in self.master_frame.winfo_children():
            w.destroy()

        self.fig, self.ax = plt.subplots(figsize=(4, 1.2), dpi=80)
        self.fig.patch.set_facecolor('#2b2b2b')
        self.ax.set_facecolor('#2b2b2b')

        # Eje X en milisegundos reales (0 a total_duration_ms)
        n = len(samples) if samples is not None else 0
        if n > 0:
            x_coords = np.linspace(0, total_duration_ms, n)
            self.ax.plot(x_coords, samples, color=color, linewidth=0.6)
            max_val = max(abs(float(samples.max())), abs(float(samples.min()))) if n > 0 else 1.0
            if max_val > 0:
                self.ax.set_ylim(-max_val * 1.15, max_val * 1.15)
        self.ax.set_xlim(0, max(1, total_duration_ms))

        # Marcas de cortes de cada frase
        if segments:
            for seg_item in segments:
                s_ms = seg_item[0]
                e_ms = seg_item[1]
                seg_id = seg_item[3] if len(seg_item) > 3 else ""
                is_selected = bool(self.is_dubbed and selected_segment_id and seg_id == selected_segment_id)

                if is_selected:
                    # Resaltado amarillo neón para clip seleccionado
                    self.ax.axvspan(s_ms, e_ms, color='#ffe600', alpha=0.22, zorder=3)
                    self.ax.axvline(x=s_ms, color='#ffe600', linestyle='-', linewidth=2.0, zorder=6)
                    self.ax.axvline(x=e_ms, color='#ffe600', linestyle='-', linewidth=2.0, zorder=6)
                else:
                    self.ax.axvspan(s_ms, e_ms, color='white', alpha=0.06)
                    self.ax.axvline(x=s_ms, color=cut_color, linestyle='--', linewidth=0.85, alpha=0.85)
                    self.ax.axvline(x=e_ms, color=cut_color, linestyle='--', linewidth=0.85, alpha=0.85)

        # Cabezal de reproducción (Playhead)
        self.playhead_line = self.ax.axvline(x=playhead_ms, color='#ffe600', linewidth=1.8, zorder=10)

        self.ax.axis('off')
        plt.subplots_adjust(left=0.005, right=0.995, top=0.98, bottom=0.02)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(self.fig)

    def update_playhead(self, current_ms):
        """Mueve la línea vertical del playhead en tiempo real de forma ultra ligera."""
        try:
            if self.canvas and self.playhead_line:
                self.playhead_line.set_xdata([current_ms, current_ms])
                self.canvas.draw_idle()
        except Exception:
            pass

    def set_razor_guide(self, cut_ms):
        """Muestra u orienta la línea guía roja de corte con cuchilla."""
        if not self.ax or not self.canvas:
            return
        if self.razor_line is None:
            self.razor_line = self.ax.axvline(x=cut_ms, color='#ff1744', linestyle='--', linewidth=1.5, zorder=25)
        else:
            self.razor_line.set_xdata([cut_ms, cut_ms])
        self.canvas.draw_idle()

    def remove_razor_guide(self):
        """Elimina la línea guía de corte de la cuchilla."""
        if self.razor_line:
            try:
                self.razor_line.remove()
            except Exception:
                pass
            self.razor_line = None
            if self.canvas:
                self.canvas.draw_idle()

    def set_ghost_patch(self, start_ms, end_ms, color='#00e5ff', alpha=0.35):
        """Dibuja un rectángulo de previsualización mientras se arrastra o estira un clip."""
        if not self.ax or not self.canvas:
            return
        self.remove_ghost_patch()
        self.ghost_patch = self.ax.axvspan(start_ms, end_ms, color=color, alpha=alpha, zorder=5)
        self.canvas.draw_idle()

    def remove_ghost_patch(self):
        """Elimina el rectángulo fantasma de previsualización."""
        if self.ghost_patch:
            try:
                self.ghost_patch.remove()
            except Exception:
                pass
            self.ghost_patch = None
            if self.canvas:
                self.canvas.draw_idle()

    def set_cursor(self, cursor_name):
        if self.canvas:
            self.canvas.get_tk_widget().configure(cursor=cursor_name)

    def connect(self, event_name, callback):
        """Conecta un evento de matplotlib (ej. button_press_event) con un callback."""
        if self.canvas:
            return self.canvas.mpl_connect(event_name, callback)
        return None
