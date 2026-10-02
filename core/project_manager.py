import os
import json
import shutil
import subprocess
import re

class ProjectManager:
    def __init__(self, base_dir=None):
        if base_dir is None:
            # Sube un nivel desde 'core/' hacia la raíz del proyecto
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            self.base_dir = base_dir

        self.projects_dir = os.path.join(self.base_dir, "proyectos")
        self.assets_dir = os.path.join(self.base_dir, "assets", "clone_examples")
        self.ensure_base_dirs()

    def ensure_base_dirs(self):
        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)

    def sanitize_name(self, name):
        """Convierte un nombre a formato seguro para carpetas."""
        clean = re.sub(r'[\\/*?:"<>|]', '', name).strip()
        clean = re.sub(r'\s+', '_', clean)
        return clean or "proyecto_sin_nombre"

    def list_projects(self):
        """Devuelve la lista ordenada de nombres de proyectos disponibles."""
        self.ensure_base_dirs()
        projects = []
        for entry in os.listdir(self.projects_dir):
            full_path = os.path.join(self.projects_dir, entry)
            if os.path.isdir(full_path):
                projects.append(entry)
        return sorted(projects)

    def get_project_paths(self, project_name):
        """Devuelve un diccionario con todas las rutas relevantes de un proyecto."""
        proj_root = os.path.join(self.projects_dir, project_name)
        audios_dir = os.path.join(proj_root, "audios")
        metadata_file = os.path.join(proj_root, "secciones.json")

        # Buscar archivo de audio original (.wav o .mp3)
        audio_file = None
        for ext in (".wav", ".mp3", ".m4a", ".flac"):
            p = os.path.join(proj_root, f"original{ext}")
            if os.path.exists(p):
                audio_file = p
                break
        
        # Si no se llamó original.*, buscar cualquier archivo de audio en la raíz del proyecto
        if not audio_file and os.path.exists(proj_root):
            for f in os.listdir(proj_root):
                if f.lower().endswith((".wav", ".mp3", ".m4a", ".flac")):
                    audio_file = os.path.join(proj_root, f)
                    break

        # Buscar archivo de video original
        video_file = None
        for ext in (".mp4", ".mkv", ".mov", ".avi", ".webm"):
            p = os.path.join(proj_root, f"video{ext}")
            if os.path.exists(p):
                video_file = p
                break

        if not video_file and os.path.exists(proj_root):
            for f in os.listdir(proj_root):
                if f.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".webm")) and not f.startswith("video_doblado"):
                    video_file = os.path.join(proj_root, f)
                    break

        return {
            "root": proj_root,
            "audios_dir": audios_dir,
            "metadata_file": metadata_file,
            "master_metadata_file": os.path.join(proj_root, "secciones_master.json"),
            "audio_file": audio_file,
            "video_file": video_file,
            "export_audio": os.path.join(proj_root, "doblaje_final.wav"),
            "export_video": os.path.join(proj_root, "video_doblado.mp4"),
            "config_file": os.path.join(proj_root, "config.json")
        }

    def create_project(self, name, source_file=None, target_language="en"):
        """
        Crea un nuevo proyecto.
        Si se pasa source_file (.mp4 o audio), copia o extrae el audio a 'original.wav'.
        Guarda config.json con el idioma seleccionado ('en' o 'pt').
        """
        safe_name = self.sanitize_name(name)
        proj_root = os.path.join(self.projects_dir, safe_name)
        os.makedirs(proj_root, exist_ok=True)
        os.makedirs(os.path.join(proj_root, "audios"), exist_ok=True)

        # Guardar config.json del proyecto
        config_file = os.path.join(proj_root, "config.json")
        config_data = {
            "name": safe_name,
            "target_language": target_language or "en"
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        metadata_file = os.path.join(proj_root, "secciones.json")
        if not os.path.exists(metadata_file):
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)

        if source_file and os.path.exists(source_file):
            ext = os.path.splitext(source_file)[1].lower()
            target_audio = os.path.join(proj_root, "original.wav")

            video_exts = (".mp4", ".mkv", ".mov", ".avi", ".webm")
            audio_exts = (".wav", ".mp3", ".m4a", ".flac", ".ogg")

            if ext in video_exts:
                # Copiar video al proyecto
                target_video = os.path.join(proj_root, f"video{ext}")
                shutil.copy2(source_file, target_video)

                # Extraer audio a original.wav usando ffmpeg
                cmd = [
                    "ffmpeg", "-y", "-i", target_video,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    target_audio
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            elif ext in audio_exts:
                if ext == ".wav":
                    shutil.copy2(source_file, target_audio)
                else:
                    cmd = [
                        "ffmpeg", "-y", "-i", source_file,
                        "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                        target_audio
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        return safe_name, self.get_project_paths(safe_name)

    def load_project_metadata(self, project_name):
        """Carga el contenido de secciones.json de un proyecto."""
        paths = self.get_project_paths(project_name)
        metadata_file = paths["metadata_file"]
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] No se pudo leer {metadata_file}: {e}")
                return []
        return []

    def save_project_metadata(self, project_name, data):
        """Guarda la lista de secciones en secciones.json."""
        paths = self.get_project_paths(project_name)
        metadata_file = paths["metadata_file"]
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def load_master_metadata(self, project_name):
        """Carga el respaldo original inmutable de secciones (secciones_master.json)."""
        paths = self.get_project_paths(project_name)
        master_file = paths["master_metadata_file"]
        if os.path.exists(master_file):
            try:
                with open(master_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] No se pudo leer {master_file}: {e}")
        return None

    def save_master_metadata(self, project_name, data):
        """Guarda el respaldo original inmutable de secciones en secciones_master.json."""
        paths = self.get_project_paths(project_name)
        master_file = paths["master_metadata_file"]
        with open(master_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def get_project_config(self, project_name):
        """Carga la configuración de un proyecto (config.json) con fallback seguro a inglés."""
        if not project_name:
            return {"target_language": "en"}
        paths = self.get_project_paths(project_name)
        cfg_file = paths.get("config_file")
        if cfg_file and os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Warning] Error leyendo {cfg_file}: {e}")
        return {"target_language": "en"}

    def get_project_language(self, project_name):
        """Devuelve el código de idioma destino del proyecto ('en' o 'pt')."""
        cfg = self.get_project_config(project_name)
        return cfg.get("target_language", "en")

    def get_clone_examples_dir(self, lang="en"):
        """Devuelve la ruta absoluta a la carpeta de ejemplos de clonación para el idioma dado ('en' o 'pt')."""
        clean_lang = "pt" if str(lang).lower() in ("pt", "portuguese") else "en"
        target_dir = os.path.join(self.assets_dir, clean_lang)
        if os.path.exists(target_dir):
            return target_dir
        return self.assets_dir

    def get_examples_config(self, lang="en"):
        """Carga los ejemplos de clonación y tonos de assets/clone_examples/<lang>/examples.json."""
        target_dir = self.get_clone_examples_dir(lang)
        json_path = os.path.join(target_dir, "examples.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        root_json = os.path.join(self.assets_dir, "examples.json")
        if os.path.exists(root_json):
            with open(root_json, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
