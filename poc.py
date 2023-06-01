import os
import sys
import time
import json
import uuid
import torch
import yt_dlp
import logging
import whisper
import threading
import subprocess
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)5s] %(threadName)10s: %(message)s", level=logging.DEBUG)

print(f"cuda: {torch.cuda.is_available()}, v: {torch.cuda.current_device()}")
if torch.cuda.is_available():

    youtube_id = "5jeezDV1Cik"
    ydl_opts = {
        "format": "opus/bestaudio/best",
        "outtmpl": youtube_id,
    }

    error_code = 0
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download([youtube_id])

    # 
    model = whisper.load_model("base", device="cuda")
    audio_path = youtube_id
    if os.path.exists(audio_path):
        logger.info(f"File exists: {audio_path}")
    t1 = time.time()
    audio = whisper.load_audio(audio_path)
    t2 = time.time()
    logger.info(f"File loaded by whisper: {audio_path}")
    audio = whisper.pad_or_trim(audio)
    t3 = time.time()
    mel = whisper.log_mel_spectrogram(audio).to(model.device)
    t4 = time.time()
    _, probs = model.detect_language(mel)
    t5 = time.time()

    logger.debug(f"Detected language ru: {probs['ru']}")
    logger.debug(f"Detected language en: {probs['en']}")
    logger.debug(f"Detected language uk: {probs['uk']}")
    logger.debug(f"Elapsed time: {t2 - t1} {t3 - t2} {t4 - t3} {t5 - t4}")
