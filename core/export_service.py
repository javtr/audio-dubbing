import os

class ExportService:
    """Servicio para orquestar la exportación final de audio y video."""

    @staticmethod
    def export_audio(processor, save_path, vol_orig=1.0, mute_orig=False, vol_dub=1.0, mute_dub=False):
        """Exporta la mezcla de audio actual al archivo especificado."""
        if not processor:
            raise ValueError("No hay procesador de audio activo.")
        return processor.export_mix_audio(
            save_path,
            vol_orig=vol_orig,
            mute_orig=mute_orig,
            vol_dub=vol_dub,
            mute_dub=mute_dub
        )

    @staticmethod
    def export_video(processor, video_file, save_path, vol_orig=1.0, mute_orig=False, vol_dub=1.0, mute_dub=False):
        """Combina el video original con el nuevo audio doblado."""
        if not processor:
            raise ValueError("No hay procesador de audio activo.")
        if not video_file or not os.path.exists(video_file):
            raise FileNotFoundError(f"Video original no encontrado: {video_file}")

        temp_audio = os.path.join(processor.temp_dir, f"export_video_temp_{os.getpid()}.wav")
        try:
            processor.export_mix_audio(
                temp_audio,
                vol_orig=vol_orig,
                mute_orig=mute_orig,
                vol_dub=vol_dub,
                mute_dub=mute_dub
            )
            processor.export_video_with_audio(video_file, temp_audio, save_path)
            return save_path
        finally:
            if os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass
