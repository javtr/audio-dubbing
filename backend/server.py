import sys
import os
import re
import copy
import json
import asyncio
import threading
import time
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from core.project_manager import ProjectManager
from core.whisper_aligner import WhisperAligner
from core.pinokio_client import PinokioClient
from core.audio_processor import AudioProcessor
from core.export_service import ExportService
from core.timing_validator import TimingValidator

app = FastAPI(title="Audio Dubbing Studio API", version="2.0.0")

# CORS middleware for local Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core singletons
pm = ProjectManager(base_dir=str(PROJECT_ROOT))
aligner = WhisperAligner()
tts_client = PinokioClient(base_url="http://127.0.0.1:7860")

# Global stop flag for batch TTS
stop_tts_event = threading.Event()
mix_export_lock = threading.Lock()
CURRENT_MIX_FILES: dict[str, str] = {}


def get_current_mix_file(paths: dict, project: str) -> str:
    """Devuelve la ruta al archivo de mezcla activo más reciente para el proyecto."""
    mix_dir = os.path.join(paths["root"], "mix")
    os.makedirs(mix_dir, exist_ok=True)
    if project in CURRENT_MIX_FILES:
        current = os.path.join(mix_dir, CURRENT_MIX_FILES[project])
        if os.path.exists(current):
            return current
            
    # Buscar el archivo de mezcla más reciente en disco si existe
    mix_files = [f for f in os.listdir(mix_dir) if f.startswith("dubbed_mix") and f.endswith(".mp3")]
    if mix_files:
        mix_files.sort(key=lambda x: os.path.getmtime(os.path.join(mix_dir, x)), reverse=True)
        CURRENT_MIX_FILES[project] = mix_files[0]
        return os.path.join(mix_dir, mix_files[0])
        
    return os.path.join(mix_dir, "dubbed_mix.mp3")


def export_dubbed_mix_versioned(processor, paths: dict, project: str) -> str:
    """
    Genera una mezcla con nombre versionado único.
    Evita el error WinError 32 / WinError 5 de Windows cuando el navegador tiene abierto el archivo.
    """
    with mix_export_lock:
        mix = processor.mix_dubbed_audio(force=True)
        if not mix:
            return ""

        mix_dir = os.path.join(paths["root"], "mix")
        os.makedirs(mix_dir, exist_ok=True)
        
        timestamp = int(time.time() * 1000)
        new_filename = f"dubbed_mix_{timestamp}.mp3"
        new_filepath = os.path.join(mix_dir, new_filename)

        print(f"[MIX-EXPORT] Exportando mezcla versión {timestamp} ({len(mix)} ms) para proyecto '{project}'...")
        mix.export(new_filepath, format="mp3", bitrate="192k")
        CURRENT_MIX_FILES[project] = new_filename

        # Limpieza oportunista de mezclas anteriores que ya no estén bloqueadas
        for f in os.listdir(mix_dir):
            if f != new_filename and (f.startswith("dubbed_mix") and f.endswith(".mp3")):
                try:
                    os.remove(os.path.join(mix_dir, f))
                except Exception:
                    pass  # Sigue en uso por streaming activo; se limpiará en la próxima ejecución

        print(f"[MIX-EXPORT] Mezcla completada exitosamente: {new_filename}")
        return new_filepath


def calculate_segment_speed_ratio(raw_duration_ms: int, target_span_ms: int, manual_ratio: Optional[float] = None) -> float:
    """Calcula ratio de velocidad con límite inferior 0.85x y sin límite superior."""
    if manual_ratio is not None and manual_ratio > 0:
        return round(float(manual_ratio), 2)
    if target_span_ms <= 0 or raw_duration_ms <= 0:
        return 1.0
    
    raw_ratio = raw_duration_ms / float(target_span_ms)
    
    # Si necesita acelerar (> 1.0): sin límite superior para evitar solapes
    if raw_ratio > 1.0:
        return round(raw_ratio, 2)
    
    # Si necesita desacelerar (< 1.0): NUNCA bajar de 0.85x
    if raw_ratio < 0.85:
        return 0.85
        
    return round(raw_ratio, 2)


def process_segment_from_raw(paths: dict, segment: dict, requested_ratio: Optional[float] = None, is_manual: bool = False):
    """Procesa un segmento desde su audio virgen inmutable en audios/raw/ sin estiramiento destructivo."""
    import shutil
    import subprocess
    audios_dir = paths.get("audios_dir", "")
    raw_dir = os.path.join(audios_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    
    filename = segment.get("filename", "")
    if not filename:
        return segment
        
    raw_path = os.path.join(raw_dir, filename)
    active_path = os.path.join(audios_dir, filename)
    
    # Salvaguardar en raw/ si aún no existe
    if not os.path.exists(raw_path) and os.path.exists(active_path):
        shutil.copy(active_path, raw_path)
        os.utime(raw_path, None)
        
    if not os.path.exists(raw_path):
        return segment
        
    from pydub import AudioSegment
    raw_audio = AudioSegment.from_file(raw_path)
    raw_len = len(raw_audio)
    target_span = segment.get("end_ms", 0) - segment.get("start_ms", 0)
    
    final_ratio = calculate_segment_speed_ratio(
        raw_duration_ms=raw_len,
        target_span_ms=target_span,
        manual_ratio=requested_ratio if is_manual else segment.get("speed_ratio") if segment.get("is_manual_ratio") else None
    )
    
    if abs(final_ratio - 1.0) < 0.005:
        shutil.copy(raw_path, active_path)
        os.utime(active_path, None)
        clip_len = raw_len
        print(f"[RATIO-ADJUST] Restaurado 1.0x desde master raw: {filename} | Dur={clip_len}ms")
    else:
        temp_dir = os.path.join(paths["root"], "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_out = os.path.join(temp_dir, f"stretched_{final_ratio:.3f}_{filename}")
        
        ratio_clamped = max(0.5, min(final_ratio, 100.0))
        cmd = [
            "ffmpeg", "-y", "-i", raw_path,
            "-filter:a", f"atempo={ratio_clamped}",
            temp_out
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        shutil.copy(temp_out, active_path)
        os.utime(active_path, None)
        clip_len = len(AudioSegment.from_file(active_path))
        print(f"[RATIO-ADJUST] Procesado {final_ratio:.2f}x: {filename} | Master={raw_len}ms -> Salida={clip_len}ms")
        
    segment["raw_duration_ms"] = raw_len
    segment["clip_duration_ms"] = clip_len
    segment["speed_ratio"] = final_ratio
    segment["current_speed_ratio"] = final_ratio
    segment["is_manual_ratio"] = is_manual
    segment["end_ms"] = segment.get("start_ms", 0) + clip_len
            
    return segment


def export_dubbed_mix_atomic(processor, mix_file: str) -> bool:
    """Función de compatibilidad: exporta dubbed_mix.mp3 de forma atómica."""
    with mix_export_lock:
        mix = processor.mix_dubbed_audio(force=True)
        if not mix:
            return False
            
        mix_dir = os.path.dirname(mix_file)
        os.makedirs(mix_dir, exist_ok=True)
        temp_mix_file = f"{mix_file}.tmp_{os.getpid()}_{threading.get_ident()}.mp3"
        
        try:
            mix.export(temp_mix_file, format="mp3", bitrate="192k")
            if os.path.exists(mix_file):
                try:
                    os.remove(mix_file)
                except Exception:
                    pass
            os.replace(temp_mix_file, mix_file)
            return True
        except Exception as e:
            print("[MIX-WARN] Error en exportación atómica fija (usando versionada como alternativa):", e)
            if os.path.exists(temp_mix_file):
                try:
                    os.remove(temp_mix_file)
                except Exception:
                    pass
            return False

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._loop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self._loop = asyncio.get_running_loop()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

    def broadcast_sync(self, message: dict):
        """Allows threads (Whisper / TTS) to broadcast messages to all connected WebSockets."""
        if self._loop and self.active_connections:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)

ws_manager = ConnectionManager()


@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                if parsed.get("action") == "stop_tts":
                    stop_tts_event.set()
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ==================== PROJECTS API ====================

@app.get("/api/projects")
def list_projects():
    projects = pm.list_projects()
    return {"projects": projects}


class CreateProjectRequest(BaseModel):
    name: str
    media_path: str
    language: str = "en"

@app.post("/api/projects")
def create_project(req: CreateProjectRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre del proyecto es obligatorio.")
    if not os.path.exists(req.media_path):
        raise HTTPException(status_code=400, detail=f"No se encontró el archivo de medios: {req.media_path}")
    try:
        paths = pm.create_project(name, req.media_path, lang=req.language)
        return {"status": "ok", "project": name, "paths": paths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{name}")
def get_project(name: str):
    projects = pm.list_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")

    paths = pm.get_project_paths(name)
    metadata = pm.load_project_metadata(name)
    lang = pm.get_project_language(name)

    # Audio duration
    audio_duration_ms = 0
    audio_file = paths.get("audio_file")
    if audio_file and os.path.exists(audio_file):
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_file)
            audio_duration_ms = len(audio)
        except Exception:
            pass

    validation = TimingValidator.validate(metadata, audio_duration_ms)

    # Calculate actual speeds for each segment with generated wav
    audios_dir = paths.get("audios_dir", "")
    raw_dir = os.path.join(audios_dir, "raw") if audios_dir else ""
    from pydub import AudioSegment
    for seg in metadata:
        fname = seg.get("filename", "")
        fpath = os.path.join(audios_dir, fname) if fname and audios_dir else ""
        raw_path = os.path.join(raw_dir, fname) if fname and raw_dir and os.path.exists(raw_dir) else ""
        target_span = seg.get("end_ms", 0) - seg.get("start_ms", 0)

        raw_len = 0
        if raw_path and os.path.exists(raw_path):
            try:
                raw_len = len(AudioSegment.from_file(raw_path))
            except Exception:
                pass
        elif fpath and os.path.exists(fpath):
            try:
                raw_len = len(AudioSegment.from_file(fpath))
            except Exception:
                pass

        seg["raw_duration_ms"] = raw_len

        if fpath and os.path.exists(fpath) and target_span > 0:
            try:
                clip_len = len(AudioSegment.from_file(fpath))
                seg["clip_duration_ms"] = clip_len
                if seg.get("is_manual_ratio") and seg.get("speed_ratio"):
                    r = round(float(seg["speed_ratio"]), 2)
                    seg["speed_ratio"] = r
                    seg["current_speed_ratio"] = r
                else:
                    auto_r = calculate_segment_speed_ratio(raw_len or clip_len, target_span)
                    seg["speed_ratio"] = auto_r
                    seg["current_speed_ratio"] = auto_r
            except Exception:
                pass
        else:
            seg["clip_duration_ms"] = 0
            seg["speed_ratio"] = 1.0
            seg["current_speed_ratio"] = 1.0

    return {
        "name": name,
        "language": lang,
        "paths": paths,
        "audio_duration_ms": audio_duration_ms,
        "metadata": metadata,
        "validation": validation
    }


class SaveMetadataRequest(BaseModel):
    metadata: List[Dict[str, Any]]

@app.post("/api/projects/{name}/metadata")
def save_project_metadata(name: str, req: SaveMetadataRequest):
    try:
        pm.save_project_metadata(name, req.metadata)
        val = TimingValidator.validate(req.metadata)
        return {"status": "ok", "validation": val}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{name}/reset-master")
def reset_to_master(name: str):
    master = pm.load_master_metadata(name)
    if not master:
        raise HTTPException(status_code=400, detail="No existe una copia maestra inicial (master_secciones.json).")
    pm.save_project_metadata(name, master)
    return {"status": "ok", "metadata": master}


# ==================== SCRIPT & ALIGNMENT API ====================

class TranscribeRequest(BaseModel):
    project: str

@app.post("/api/script/transcribe")
def transcribe_audio(req: TranscribeRequest, background_tasks: BackgroundTasks):
    paths = pm.get_project_paths(req.project)
    audio_file = paths.get("audio_file")
    if not audio_file or not os.path.exists(audio_file):
        raise HTTPException(status_code=400, detail="Audio original no encontrado en el proyecto.")

    def _worker():
        try:
            ws_manager.broadcast_sync({"type": "transcribe_status", "status": "Iniciando Whisper..."})
            text = aligner.transcribe_to_plain_text(
                audio_file,
                callback_status=lambda msg: ws_manager.broadcast_sync({
                    "type": "transcribe_status",
                    "status": msg
                })
            )
            ws_manager.broadcast_sync({
                "type": "transcribe_complete",
                "text": text
            })
        except Exception as e:
            ws_manager.broadcast_sync({
                "type": "transcribe_error",
                "error": str(e)
            })
        finally:
            aligner.unload_model()

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


class GeneratePromptRequest(BaseModel):
    project: str
    transcript: str

@app.post("/api/script/generate-prompt")
def generate_prompt(req: GeneratePromptRequest):
    lang = pm.get_project_language(req.project)
    prompt = aligner.generate_gemini_prompt(req.transcript, target_lang=lang)
    return {"prompt": prompt, "language": lang}


class AlignRequest(BaseModel):
    project: str
    gemini_data: List[Dict[str, Any]]
    split_on_pauses: bool = True
    min_pause_ms: int = 1000

@app.post("/api/script/align")
def align_script(req: AlignRequest):
    paths = pm.get_project_paths(req.project)
    audio_file = paths.get("audio_file")
    if not audio_file or not os.path.exists(audio_file):
        raise HTTPException(status_code=400, detail="Audio original no encontrado.")

    def _worker():
        try:
            ws_manager.broadcast_sync({"type": "align_status", "status": "Cargando Whisper con marcas por palabra..."})
            aligned, duration_ms = aligner.align_timestamps(
                audio_file,
                req.gemini_data,
                callback_status=lambda msg: ws_manager.broadcast_sync({
                    "type": "align_status",
                    "status": msg
                }),
                split_on_pauses=req.split_on_pauses,
                min_pause_ms=req.min_pause_ms
            )
            pm.save_project_metadata(req.project, aligned)
            pm.save_master_metadata(req.project, aligned)
            val = TimingValidator.validate(aligned, duration_ms)
            ws_manager.broadcast_sync({
                "type": "align_complete",
                "segments": aligned,
                "duration_ms": duration_ms,
                "validation": val
            })
        except Exception as e:
            ws_manager.broadcast_sync({
                "type": "align_error",
                "error": str(e)
            })
        finally:
            aligner.unload_model()

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


class RetranslationPromptRequest(BaseModel):
    project: str

@app.post("/api/script/generate-retranslation-prompt")
def generate_retranslation_prompt(req: RetranslationPromptRequest):
    metadata = pm.load_project_metadata(req.project)
    if not metadata:
        raise HTTPException(status_code=400, detail="No hay segmentos en el proyecto para re-traducir.")
    lang = pm.get_project_language(req.project)
    prompt = aligner.generate_retranslation_prompt(metadata, target_lang=lang)
    return {"prompt": prompt, "language": lang, "segments_count": len(metadata)}


class ApplyRetranslationRequest(BaseModel):
    project: str
    retranslated_json: List[Dict[str, Any]]

@app.post("/api/script/apply-retranslation")
def apply_retranslation(req: ApplyRetranslationRequest):
    metadata = pm.load_project_metadata(req.project)
    new_data = req.retranslated_json

    new_map = {str(item.get("id")): item for item in new_data if "id" in item}

    updated_count = 0
    for idx, seg in enumerate(metadata):
        sid = str(seg.get("id"))
        if sid in new_map:
            match = new_map[sid]
            if "translated" in match:
                seg["translated"] = match["translated"].strip()
            if "tone" in match:
                seg["tone"] = match["tone"].strip()
            updated_count += 1
        elif idx < len(new_data):
            match = new_data[idx]
            if "translated" in match:
                seg["translated"] = match["translated"].strip()
            if "tone" in match:
                seg["tone"] = match["tone"].strip()
            updated_count += 1

    pm.save_project_metadata(req.project, metadata)
    val = TimingValidator.validate(metadata)
    return {
        "status": "ok",
        "updated_count": updated_count,
        "metadata": metadata,
        "validation": val
    }


# ==================== TTS & CLONING API ====================

@app.get("/api/tts/status")
def check_tts_connection():
    is_connected = tts_client.check_connection()
    return {"connected": is_connected, "url": tts_client.base_url}


@app.get("/api/tts/references")
def get_references(language: str = "en"):
    examples_file = PROJECT_ROOT / "assets" / "clone_examples" / "examples.json"
    refs = []
    if examples_file.exists():
        try:
            with open(examples_file, "r", encoding="utf-8") as f:
                refs = json.load(f)
        except Exception:
            pass

    lang_dir = PROJECT_ROOT / "assets" / "clone_examples" / language
    if not lang_dir.exists() and language == "en":
        lang_dir = PROJECT_ROOT / "assets" / "clone_examples"

    for r in refs:
        wav_name = f"{r['segmento']}.wav"
        wav_path = lang_dir / wav_name
        r["exists"] = wav_path.exists()
        r["audio_url"] = f"/api/audio/reference/{r['segmento']}?lang={language}"

    return {"references": refs}


@app.get("/api/audio/reference/{ref_name}")
def stream_reference_audio(ref_name: str, lang: str = "en"):
    lang_dir = PROJECT_ROOT / "assets" / "clone_examples" / lang
    wav_path = lang_dir / f"{ref_name}.wav"
    if not wav_path.exists():
        wav_path = PROJECT_ROOT / "assets" / "clone_examples" / f"{ref_name}.wav"
    if not wav_path.exists():
        raise HTTPException(status_code=404, detail="Referencia de audio no encontrada.")
    return FileResponse(str(wav_path), media_type="audio/wav")


class GenerateSingleTTSRequest(BaseModel):
    project: str
    segment_id: str
    ref_name: str
    model_size: str = "1.7B"

@app.post("/api/tts/generate-single")
def generate_single_tts(req: GenerateSingleTTSRequest):
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)
    lang = pm.get_project_language(req.project)

    target_seg = None
    for s in metadata:
        if str(s.get("id")) == str(req.segment_id):
            target_seg = s
            break

    if not target_seg:
        raise HTTPException(status_code=404, detail="Segmento no encontrado.")

    # Find reference audio & text
    examples_file = PROJECT_ROOT / "assets" / "clone_examples" / "examples.json"
    ref_text = ""
    if examples_file.exists():
        with open(examples_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                if item["segmento"] == req.ref_name:
                    ref_text = item["transcripcion"]
                    break

    lang_dir = PROJECT_ROOT / "assets" / "clone_examples" / lang
    ref_wav = lang_dir / f"{req.ref_name}.wav"
    if not ref_wav.exists():
        ref_wav = PROJECT_ROOT / "assets" / "clone_examples" / f"{req.ref_name}.wav"

    if not ref_wav.exists():
        raise HTTPException(status_code=400, detail=f"Audio de referencia {req.ref_name} no encontrado.")

    target_text = target_seg.get("translated", "").strip()
    if not target_text:
        raise HTTPException(status_code=400, detail="El segmento no tiene texto traducido.")

    out_file = os.path.join(paths["audios_dir"], target_seg["filename"])

    tts_client.generate_voice_clone(
        ref_audio_path=str(ref_wav),
        ref_text=ref_text,
        target_text=target_text,
        output_path=out_file,
        language="Portuguese" if lang == "pt" else "English",
        model_size=req.model_size
    )

    from pydub import AudioSegment
    clip_dur = len(AudioSegment.from_file(out_file))
    target_span = target_seg.get("end_ms", 0) - target_seg.get("start_ms", 0)
    speed_ratio = calculate_segment_speed_ratio(clip_dur, target_span)

    # Save copy to audios/raw/ as untouched master
    raw_dir = os.path.join(paths["audios_dir"], "raw")
    os.makedirs(raw_dir, exist_ok=True)
    import shutil
    shutil.copy2(out_file, os.path.join(raw_dir, target_seg["filename"]))

    target_seg["raw_duration_ms"] = clip_dur
    target_seg["clip_duration_ms"] = clip_dur
    target_seg["speed_ratio"] = speed_ratio
    target_seg["current_speed_ratio"] = speed_ratio
    target_seg["is_manual_ratio"] = False
    pm.save_project_metadata(req.project, metadata)

    # Invalidate old dubbed mix file
    mix_file = os.path.join(paths["root"], "mix", "dubbed_mix.mp3")
    if os.path.exists(mix_file):
        try:
            os.remove(mix_file)
        except Exception:
            pass

    return {
        "status": "ok",
        "segment_id": req.segment_id,
        "clip_duration_ms": clip_dur,
        "speed_ratio": speed_ratio,
        "audio_url": f"/api/audio/{req.project}/segment/{target_seg['filename']}"
    }


class GenerateBatchTTSRequest(BaseModel):
    project: str
    segment_ids: List[str]
    default_ref: str = "ref_Conversational"
    model_size: str = "1.7B"

@app.post("/api/tts/generate-batch")
def generate_batch_tts(req: GenerateBatchTTSRequest):
    stop_tts_event.clear()
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)
    lang = pm.get_project_language(req.project)

    examples_file = PROJECT_ROOT / "assets" / "clone_examples" / "examples.json"
    ref_map = {}
    if examples_file.exists():
        with open(examples_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                ref_map[item["segmento"]] = item["transcripcion"]

    def _worker():
        total = len(req.segment_ids)
        for idx, seg_id in enumerate(req.segment_ids):
            if stop_tts_event.is_set():
                ws_manager.broadcast_sync({
                    "type": "tts_batch_stopped",
                    "processed": idx,
                    "total": total
                })
                break

            target_seg = next((s for s in metadata if str(s.get("id")) == str(seg_id)), None)
            if not target_seg:
                continue

            ref_name = req.default_ref
            ref_text = ref_map.get(ref_name, "")
            lang_dir = PROJECT_ROOT / "assets" / "clone_examples" / lang
            ref_wav = lang_dir / f"{ref_name}.wav"
            if not ref_wav.exists():
                ref_wav = PROJECT_ROOT / "assets" / "clone_examples" / f"{ref_name}.wav"

            out_file = os.path.join(paths["audios_dir"], target_seg["filename"])
            target_text = target_seg.get("translated", "").strip()

            ws_manager.broadcast_sync({
                "type": "tts_progress",
                "current": idx + 1,
                "total": total,
                "segment_id": seg_id,
                "status": f"Generando segmento {idx+1}/{total} [{seg_id}]..."
            })

            try:
                tts_client.generate_voice_clone(
                    ref_audio_path=str(ref_wav),
                    ref_text=ref_text,
                    target_text=target_text,
                    output_path=out_file,
                    language="Portuguese" if lang == "pt" else "English",
                    model_size=req.model_size
                )

                from pydub import AudioSegment
                clip_dur = len(AudioSegment.from_file(out_file))
                target_span = target_seg.get("end_ms", 0) - target_seg.get("start_ms", 0)
                speed_ratio = calculate_segment_speed_ratio(clip_dur, target_span)

                # Save copy to audios/raw/ as untouched master
                raw_dir = os.path.join(paths["audios_dir"], "raw")
                os.makedirs(raw_dir, exist_ok=True)
                import shutil
                shutil.copy2(out_file, os.path.join(raw_dir, target_seg["filename"]))

                target_seg["raw_duration_ms"] = clip_dur
                target_seg["clip_duration_ms"] = clip_dur
                target_seg["speed_ratio"] = speed_ratio
                target_seg["current_speed_ratio"] = speed_ratio
                target_seg["is_manual_ratio"] = False

                # Remove old mix file so next playback will build fresh
                mix_file = os.path.join(paths["root"], "mix", "dubbed_mix.mp3")
                if os.path.exists(mix_file):
                    try:
                        os.remove(mix_file)
                    except Exception:
                        pass

                ws_manager.broadcast_sync({
                    "type": "tts_segment_done",
                    "segment_id": seg_id,
                    "clip_duration_ms": clip_dur,
                    "speed_ratio": speed_ratio
                })
            except Exception as e:
                ws_manager.broadcast_sync({
                    "type": "tts_segment_error",
                    "segment_id": seg_id,
                    "error": str(e)
                })

        # Save all updated clip durations to project metadata
        pm.save_project_metadata(req.project, metadata)
        ws_manager.broadcast_sync({"type": "tts_batch_complete"})

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started", "total": len(req.segment_ids)}


@app.post("/api/tts/stop")
def stop_tts():
    stop_tts_event.set()
    return {"status": "stop_requested"}


# ==================== AUDIO STREAMING & WAVEFORMS ====================

def compute_min_max_waveform(audio_segment, num_bins=1600):
    if not audio_segment:
        return []
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
    if audio_segment.channels == 2:
        samples = samples[::2]
    
    total_samples = len(samples)
    if total_samples == 0:
        return []

    max_amp = float(np.max(np.abs(samples)))
    if max_amp > 0:
        samples /= max_amp

    bin_size = max(1, total_samples // num_bins)
    peaks = []
    for i in range(num_bins):
        start = i * bin_size
        end = min(total_samples, start + bin_size)
        if start < total_samples:
            chunk = samples[start:end]
            peaks.append(round(float(np.min(chunk)), 3))
            peaks.append(round(float(np.max(chunk)), 3))
        else:
            peaks.extend([0.0, 0.0])
    return peaks


@app.get("/api/audio/{project}/original")
def stream_original_audio(project: str):
    paths = pm.get_project_paths(project)
    audio_path = paths.get("audio_file")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio original no encontrado.")
    return FileResponse(audio_path, media_type="audio/wav")


@app.get("/api/audio/{project}/segment/{filename}")
def stream_segment_audio(project: str, filename: str):
    paths = pm.get_project_paths(project)
    seg_path = os.path.join(paths["audios_dir"], filename)
    if not os.path.exists(seg_path):
        raise HTTPException(status_code=404, detail="Audio del segmento no generado.")
    return FileResponse(
        seg_path,
        media_type="audio/wav",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@app.get("/api/audio/{project}/dubbed")
def stream_dubbed_audio(project: str, force: bool = False):
    paths = pm.get_project_paths(project)
    metadata = pm.load_project_metadata(project)
    audio_path = paths.get("audio_file")
    audios_dir = paths.get("audios_dir")

    current_mix = get_current_mix_file(paths, project)
    rebuild = force or not os.path.exists(current_mix)
    if not rebuild and os.path.exists(current_mix):
        mix_mtime = os.path.getmtime(current_mix)
        metadata_file = paths.get("metadata_file")
        if metadata_file and os.path.exists(metadata_file) and os.path.getmtime(metadata_file) > mix_mtime:
            rebuild = True
        elif audios_dir and os.path.exists(audios_dir):
            for f in os.listdir(audios_dir):
                if f.endswith(".wav"):
                    if os.path.getmtime(os.path.join(audios_dir, f)) > mix_mtime:
                        rebuild = True
                        break

    if rebuild:
        processor = AudioProcessor(audio_path, audios_dir, metadata)
        current_mix = export_dubbed_mix_versioned(processor, paths, project)
        if not current_mix or not os.path.exists(current_mix):
            raise HTTPException(status_code=404, detail="No se pudo generar la mezcla doblada.")

    return FileResponse(
        current_mix,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/api/waveform/{project}/all")
def get_all_waveforms(project: str, points: int = 1600):
    paths = pm.get_project_paths(project)
    metadata = pm.load_project_metadata(project)
    
    audio_path = paths.get("audio_file")
    orig_peaks = []
    total_dur_ms = 0
    from pydub import AudioSegment
    if audio_path and os.path.exists(audio_path):
        try:
            audio_orig = AudioSegment.from_file(audio_path)
            total_dur_ms = len(audio_orig)
            orig_peaks = compute_min_max_waveform(audio_orig, num_bins=points)
        except Exception as e:
            print("Error loading original audio for waveform:", e)

    # Dubbed mix waveform & dead silence gaps
    audios_dir = paths.get("audios_dir", "")
    processor = AudioProcessor(audio_path, audios_dir, metadata)
    dub_peaks = []
    try:
        dub_mix = processor.mix_dubbed_audio(force=True)
        if dub_mix:
            if total_dur_ms == 0:
                total_dur_ms = len(dub_mix)
            dub_peaks = compute_min_max_waveform(dub_mix, num_bins=points)

            # Keep dubbed mix synchronized cleanly via versioned export
            export_dubbed_mix_versioned(processor, paths, project)
    except Exception as e:
        print("Error mixing dubbed audio for waveform:", e)

    # Detect dead silences >= 4.0s
    silences = []
    for s in metadata:
        s_ms = s.get("start_ms", 0)
        e_ms = s.get("end_ms", 0)
        fname = s.get("filename", "")
        fpath = os.path.join(audios_dir, fname) if fname and audios_dir else ""
        if fpath and os.path.exists(fpath):
            try:
                clip_audio = AudioSegment.from_file(fpath)
                clip_dur = len(clip_audio)
                voice_end = s_ms + clip_dur
                gap_ms = e_ms - voice_end
                if gap_ms >= 4000:
                    silences.append({
                        "start_ms": voice_end,
                        "end_ms": e_ms,
                        "dur_s": round(gap_ms / 1000.0, 1),
                        "segment_id": str(s.get("id")),
                        "level": "critical" if gap_ms > 10000 else "warning"
                    })
            except Exception:
                pass

    return {
        "duration_ms": total_dur_ms,
        "orig_peaks": orig_peaks,
        "dub_peaks": dub_peaks,
        "silences": silences
    }


class AdjustRatioRequest(BaseModel):
    project: str
    segment_id: str
    ratio: float

@app.post("/api/timeline/adjust-ratio")
def adjust_segment_ratio(req: AdjustRatioRequest):
    print(f"[TIMELINE-ADJUST] Solicitud: project={req.project}, segment_id={req.segment_id}, ratio={req.ratio}")
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)

    target_seg = next((s for s in metadata if str(s.get("id")) == str(req.segment_id)), None)
    if not target_seg:
        raise HTTPException(status_code=404, detail="Segmento no encontrado.")

    updated_seg = process_segment_from_raw(
        paths=paths,
        segment=target_seg,
        requested_ratio=req.ratio,
        is_manual=True
    )

    pm.save_project_metadata(req.project, metadata)
    
    # Reconstruir la mezcla inmediatamente con la nueva versión
    audio_path = paths.get("audio_file")
    audios_dir = paths.get("audios_dir")
    processor = AudioProcessor(audio_path, audios_dir, metadata)
    export_dubbed_mix_versioned(processor, paths, req.project)

    val = TimingValidator.validate(metadata)
    print(f"[TIMELINE-ADJUST] Completado con éxito: segment_id={req.segment_id}, dur={updated_seg.get('clip_duration_ms')}ms")
    return {"status": "ok", "segment": updated_seg, "metadata": metadata, "validation": val}


class TimingItem(BaseModel):
    id: str
    start_ms: int

class UpdateTimingsRequest(BaseModel):
    project: str
    timings: list[TimingItem]

@app.post("/api/timeline/update-timings")
def update_project_timings(req: UpdateTimingsRequest):
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)
    audio_path = paths.get("audio_file")
    audios_dir = paths.get("audios_dir")
    
    print(f"[TIMINGS-UPDATE] Actualizando y recalculando tiempos para {len(req.timings)} segmentos en proyecto '{req.project}'...")
    timing_map = {t.id: t.start_ms for t in req.timings}
    for seg in metadata:
        sid = str(seg.get("id"))
        if sid in timing_map:
            seg["start_ms"] = max(0, timing_map[sid])

    # Ordenar cronológicamente
    metadata.sort(key=lambda x: x.get("start_ms", 0))

    # Obtener duración total del audio original para límite del último segmento
    from pydub import AudioSegment
    total_audio_ms = 0
    if audio_path and os.path.exists(audio_path):
        try:
            total_audio_ms = len(AudioSegment.from_file(audio_path))
        except Exception:
            total_audio_ms = 0

    # Recalcular spans y procesar segmentos automáticos
    for i, seg in enumerate(metadata):
        cur_start = seg.get("start_ms", 0)
        if i < len(metadata) - 1:
            next_start = metadata[i+1].get("start_ms", cur_start + 1000)
            available_span = max(100, next_start - cur_start)
        else:
            available_span = max(1000, total_audio_ms - cur_start) if total_audio_ms > cur_start else 10000

        if not seg.get("is_manual_ratio"):
            seg["end_ms"] = cur_start + available_span
            process_segment_from_raw(paths, seg, is_manual=False)
        else:
            # Respetar ratio fijado por el usuario
            clip_dur = seg.get("clip_duration_ms", 0)
            if clip_dur <= 0:
                raw_p = os.path.join(audios_dir, "raw", seg.get("filename", ""))
                if os.path.exists(raw_p):
                    clip_dur = len(AudioSegment.from_file(raw_p))
            seg["end_ms"] = cur_start + clip_dur

    pm.save_project_metadata(req.project, metadata)
    
    # Regenerar mezcla versionada
    processor = AudioProcessor(audio_path, audios_dir, metadata)
    export_dubbed_mix_versioned(processor, paths, req.project)

    val = TimingValidator.validate(metadata)
    print(f"[TIMINGS-UPDATE] Recálculo completado con éxito para proyecto '{req.project}'.")
    return {"status": "ok", "metadata": metadata, "validation": val}


class DeleteSegmentRequest(BaseModel):
    project: str
    segment_id: str

@app.post("/api/timeline/delete-segment")
def delete_segment(req: DeleteSegmentRequest):
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)
    
    metadata = [s for s in metadata if str(s.get("id")) != str(req.segment_id)]
    
    processor = AudioProcessor(paths.get("audio_file"), paths.get("audios_dir"), metadata)
    processor.recalculate_end_times()

    for i, s in enumerate(processor.metadata):
        s["filename"] = f"segment_{i:03d}.wav"

    pm.save_project_metadata(req.project, processor.metadata)
    val = TimingValidator.validate(processor.metadata)
    return {"status": "ok", "metadata": processor.metadata, "validation": val}



# ==================== TIMELINE TOOLS & SPLITTING ====================

class AutoSplitRequest(BaseModel):
    project: str
    segment_id: str

@app.post("/api/timeline/auto-split")
def auto_split_segment(req: AutoSplitRequest):
    metadata = pm.load_project_metadata(req.project)
    idx = next((i for i, s in enumerate(metadata) if str(s.get("id")) == str(req.segment_id)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Segmento no encontrado.")

    seg = metadata[idx]
    orig_text = seg.get("original", "").strip()
    trans_text = seg.get("translated", "").strip()

    # Split using commas/punctuation or connectors
    part1_es, part2_es, part1_tr, part2_tr = aligner._split_segment_text(seg, 0.5)

    base_id = str(seg.get("id", "seg"))
    mid_time = int((seg.get("start_ms", 0) + seg.get("end_ms", 0)) / 2)

    seg_a = copy.deepcopy(seg)
    seg_a["id"] = f"{base_id}_a"
    seg_a["original"] = part1_es
    seg_a["translated"] = part1_tr
    seg_a["end_ms"] = mid_time

    seg_b = copy.deepcopy(seg)
    seg_b["id"] = f"{base_id}_b"
    seg_b["original"] = part2_es
    seg_b["translated"] = part2_tr
    seg_b["start_ms"] = mid_time

    # Replace segment with subsegments
    metadata = metadata[:idx] + [seg_a, seg_b] + metadata[idx + 1:]
    
    # Reindex filenames
    for i, s in enumerate(metadata):
        s["filename"] = f"segment_{i:03d}.wav"

    pm.save_project_metadata(req.project, metadata)
    val = TimingValidator.validate(metadata)
    return {"status": "ok", "metadata": metadata, "validation": val}


class AutoSplitAllRequest(BaseModel):
    project: str

@app.post("/api/timeline/auto-split-all")
def auto_split_all_segments(req: AutoSplitAllRequest):
    metadata = pm.load_project_metadata(req.project)
    expanded = []
    split_count = 0

    for seg in metadata:
        target_span = seg.get("end_ms", 0) - seg.get("start_ms", 0)
        orig_text = seg.get("original", "").strip()
        words = orig_text.split()

        # Criteria for auto-split: > 14 words or duration > 10s and contains comma/connector
        if len(words) >= 14 or target_span >= 10000:
            part1_es, part2_es, part1_tr, part2_tr = aligner._split_segment_text(seg, 0.5)
            if part1_es and part2_es and part1_tr and part2_tr:
                base_id = str(seg.get("id", "seg"))
                mid_time = int((seg.get("start_ms", 0) + seg.get("end_ms", 0)) / 2)

                seg_a = copy.deepcopy(seg)
                seg_a["id"] = f"{base_id}_a"
                seg_a["original"] = part1_es
                seg_a["translated"] = part1_tr
                seg_a["end_ms"] = mid_time

                seg_b = copy.deepcopy(seg)
                seg_b["id"] = f"{base_id}_b"
                seg_b["original"] = part2_es
                seg_b["translated"] = part2_tr
                seg_b["start_ms"] = mid_time

                expanded.extend([seg_a, seg_b])
                split_count += 1
                continue

        expanded.append(seg)

    for i, s in enumerate(expanded):
        s["filename"] = f"segment_{i:03d}.wav"

    pm.save_project_metadata(req.project, expanded)
    val = TimingValidator.validate(expanded)
    return {"status": "ok", "split_count": split_count, "metadata": expanded, "validation": val}


# ==================== EXPORT SERVICE ====================

class ExportRequest(BaseModel):
    project: str
    export_type: str = "video"  # "video" or "audio"
    output_path: str
    vol_orig: float = 1.0
    mute_orig: bool = False
    vol_dub: float = 1.0
    mute_dub: bool = False

@app.post("/api/export")
def export_project(req: ExportRequest, background_tasks: BackgroundTasks):
    paths = pm.get_project_paths(req.project)
    metadata = pm.load_project_metadata(req.project)
    audio_file = paths.get("audio_file")
    video_file = paths.get("video_file")
    audios_dir = paths.get("audios_dir")

    def _worker():
        try:
            ws_manager.broadcast_sync({"type": "export_status", "status": "Preparando procesador de audio..."})
            processor = AudioProcessor(audio_file, audios_dir, metadata)

            if req.export_type == "audio":
                ws_manager.broadcast_sync({"type": "export_status", "status": "Mezclando y exportando audio final..."})
                ExportService.export_audio(
                    processor, req.output_path,
                    vol_orig=req.vol_orig, mute_orig=req.mute_orig,
                    vol_dub=req.vol_dub, mute_dub=req.mute_dub
                )
            else:
                ws_manager.broadcast_sync({"type": "export_status", "status": "Uniendo video con pista doblada (FFmpeg)..."})
                ExportService.export_video(
                    processor, video_file, req.output_path,
                    vol_orig=req.vol_orig, mute_orig=req.mute_orig,
                    vol_dub=req.vol_dub, mute_dub=req.mute_dub
                )

            ws_manager.broadcast_sync({
                "type": "export_complete",
                "output_path": req.output_path
            })
        except Exception as e:
            ws_manager.broadcast_sync({
                "type": "export_error",
                "error": str(e)
            })

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


# ==================== STATIC REACT FRONTEND ====================
dist_dir = PROJECT_ROOT / "frontend" / "dist"
if dist_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
