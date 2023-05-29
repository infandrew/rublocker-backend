import os
import sys
import time
import json
import uuid
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

def get_config(config_path):
    # try to decrypt with sops
    if ".enc." in config_path:
        try:
            result = subprocess.run(['sops', '--decrypt', config_path], capture_output=True)
            return json.loads(result.stdout.decode('utf-8'))
        except:
            logger.error("Failed to decrypt configuration")
            exit(1)
    else:            
        with open(config_path) as config:
            return json.load(config)

app = Flask(__name__)
app.config.update(get_config(sys.argv[1]))
db = SQLAlchemy(app)
current_worker_id = uuid.getnode()
downloaded_limit = app.config.get("RUBLOCKER_DOWNLOADED_LIMIT", 100)

INIT_STATE = "INIT"
DOWNLOAD_STATE = "DOWNLOAD"
DOWNLOADED_STATE = "DOWNLOADED"
ANALYSIS_STATE = "ANALYSIS"
ANALYZED_STATE = "ANALYZED"
FAIL_STATE = "FAIL"

REASON_FAIL_TOO_LONG = "TOO_LONG"
REASON_FAIL_LIVE_STREAM = "LIVE_STREAM"
REASON_FAIL_LONG_LIVE_STREAM = "LONG_LIVE_STREAM"
REASON_FAIL_REQUIRES_PAYMENT = "REQUIRES_PAYMENT"
REASON_FAIL_NOT_AVAILABLE = "NOT_AVAILABLE"
REASON_FAIL_WILL_BEGIN = "WILL_BEGIN"
REASON_FAIL_PRIVATE_VIDEO = "PRIVATE_VIDEO"
REASON_FAIL_INAPPROPRIATE = "INAPPROPRIATE"

# assume threshold is 5 hours
VIDEO_DURATION_THRESHOLD = 60 * 60 * 5


class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    youtube_id = db.Column(db.String(31), nullable=False)
    ru_score = db.Column(db.Float, nullable=True)
    en_score = db.Column(db.Float, nullable=True)
    uk_score = db.Column(db.Float, nullable=True)
    state = db.Column(db.String(16), default=INIT_STATE)
    fail_reason = db.Column(db.String(16), nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    worker_id = db.Column(db.BigInteger, nullable=True)
    update_date = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.current_timestamp(),
    )
    create_date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def __init__(self, youtube_id: str):
        self.youtube_id = youtube_id


def recreate_db():
    db.drop_all()
    db.create_all()
    return ""

@app.route("/verify/states")
def fix_incorrect_states_api():
    fix_incorrect_states()
    
@app.route("/stat/scan/time")
def stat_scan_time():
    total_duration = (
        db.session.query(func.sum(Record.duration))
        .filter(Record.duration.isnot(None),Record.state!=FAIL_STATE).scalar()
    )
    hours, remainder = divmod(total_duration, 3600)
    # minutes, seconds = divmod(remainder, 60)
    # :{int(minutes)}:{int(seconds)}
    result = f'''
    <div style="background:black; color:white; text-align:center;">
        Total hours of scanned videos: {int(hours)} hrs
    </div>
    <script>setInterval(function() {{location.reload()}}, 60000);</script>
    '''
    return result

@app.route("/verify/fails")
def verify_fails():
    rows_updated = (
        db.session.query(Record)
        .filter_by(state=FAIL_STATE, fail_reason=None)
        .update({Record.state: INIT_STATE, Record.worker_id: None}, synchronize_session=False)
    )
    db.session.commit()
    logger.info(f"Rows updated: {rows_updated}")
    return ""


@app.route("/ru/identify/<youtube_id>")
def identify(youtube_id: str):
    logger.info(f"Input video id: {youtube_id}")
    record: Record = db.session.query(Record).filter_by(youtube_id=youtube_id).first()

    if record is not None and record.state == ANALYZED_STATE:
        return jsonify(ru=record.ru_score, uk=record.uk_score, en=record.en_score)

    if record is None:
        # add new record to queue
        record = Record(youtube_id)
        db.session.add(record)
        db.session.commit()
        logger.info(f"Added new record {record.id}:{record.youtube_id}")
    else:
        # check if record is live stream to be reverified
        if record.state == FAIL_STATE:
            diff = datetime.now() - record.update_date

            if (
                record.fail_reason == REASON_FAIL_WILL_BEGIN
                or record.fail_reason == REASON_FAIL_PRIVATE_VIDEO
                or record.fail_reason == REASON_FAIL_NOT_AVAILABLE
                or record.fail_reason == REASON_FAIL_LIVE_STREAM
            ) and diff > timedelta(days=1):
                record.state = INIT_STATE
                record.worker_id = None
                db.session.commit()

    queue_size = (
        db.session.query(Record)
        .filter(Record.state.notin_([ANALYZED_STATE, FAIL_STATE]))
        .count()
    )
    return jsonify(queue_size=queue_size, state=record.state)


def download():
    while True:
        time.sleep(0.5)
        try:
            with app.app_context():
                # Limit downloads if we already downloaded some videos
                # Needed to balance videos between workers
                downloaded_count = (
                    db.session.query(func.count(Record.id))
                    .filter_by(state=DOWNLOADED_STATE,worker_id=current_worker_id)
                    .scalar()
                )
                if downloaded_count >= downloaded_limit:
                    continue
                
                record: Record = (
                    db.session.query(Record)
                    .with_for_update()
                    .filter_by(state=INIT_STATE)
                    .order_by(Record.create_date.asc())
                    .first()
                )
                if record is None:
                    continue
                    
                record.state = DOWNLOAD_STATE
                record.worker_id = current_worker_id
                db.session.commit()

                logger.info(f"record started download: {record.id}/{record.youtube_id}")

                ydl_opts = {
                    "format": "opus/bestaudio/best",
                    "outtmpl": f"{app.config['STORAGE_ROOT']}/{record.youtube_id}",
                }

                error_code = 0
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(record.youtube_id, download=False)
                        if info["live_status"] == "is_live":
                            logger.info("Live streams should be skipped for now")
                            error_code = -2
                            if datetime.now() - datetime.fromtimestamp(
                                info["release_timestamp"]
                            ) > timedelta(days=1):
                                record.fail_reason = REASON_FAIL_LONG_LIVE_STREAM
                            else:
                                record.fail_reason = REASON_FAIL_LIVE_STREAM
                        elif (
                            "duration" in info
                            and info["duration"] > VIDEO_DURATION_THRESHOLD
                        ):
                            logger.info(f"Video is too big: {info['duration']}s")
                            error_code = -3
                            record.duration = info["duration"]
                            record.fail_reason = REASON_FAIL_TOO_LONG
                        else:
                            record.duration = info["duration"]
                            error_code = ydl.download([record.youtube_id])
                except Exception as e:
                    logger.error(f"Downloaded error_code: {error_code}")
                    logger.error(e)
                    if hasattr(e, "msg"):
                        if "requires payment" in e.msg:
                            record.fail_reason = REASON_FAIL_REQUIRES_PAYMENT
                        if "not available" in e.msg:
                            record.fail_reason = REASON_FAIL_NOT_AVAILABLE
                        if "live event will begin" in e.msg:
                            record.fail_reason = REASON_FAIL_WILL_BEGIN
                        if "Private video" in e.msg:
                            record.fail_reason = REASON_FAIL_PRIVATE_VIDEO
                        if "This video may be inappropriate" in e.msg:
                            record.fail_reason = REASON_FAIL_INAPPROPRIATE
                    error_code = -1

                if error_code == 0:
                    record.state = DOWNLOADED_STATE
                else:
                    record.state = FAIL_STATE
                db.session.commit()
        except:
            logger.error("Download thread failed")


def analyze():
    model = whisper.load_model("base")
    logger.info("whisper base model loaded")
    while True:
        time.sleep(0.5)
        try:
            with app.app_context():
                record: Record = (
                    db.session.query(Record)
                    .with_for_update()
                    .filter_by(state=DOWNLOADED_STATE, worker_id=current_worker_id)
                    .order_by(Record.create_date.asc())
                    .first()
                )
                if record is None:
                    continue
                
                record.state = ANALYSIS_STATE
                db.session.commit()

                logger.info(f"record started analysis: {record.youtube_id}")
                error_code = 0
                try:
                    audio_path = f"{app.config['STORAGE_ROOT']}/{record.youtube_id}"
                    if os.path.exists(audio_path):
                        logger.info(f"File exists: {audio_path}")
                    audio = whisper.load_audio(audio_path)
                    logger.info(f"File loaded by whisper: {audio_path}")
                    audio = whisper.pad_or_trim(audio)
                    mel = whisper.log_mel_spectrogram(audio).to(model.device)
                    _, probs = model.detect_language(mel)
                    logger.debug(f"Detected language ru: {probs['ru']}")
                    logger.debug(f"Detected language en: {probs['en']}")
                    logger.debug(f"Detected language uk: {probs['uk']}")
                    record.ru_score = probs["ru"]
                    record.en_score = probs["en"]
                    record.uk_score = probs["uk"]
                except Exception as e:
                    logger.error(e)
                    error_code = -1

                if error_code == 0:
                    record.state = ANALYZED_STATE
                else:
                    record.state = FAIL_STATE
                db.session.commit()
                
                # Lets remove the audio
                os.remove(audio_path)
                if os.path.exists(audio_path):
                    logger.error(f"File failed to be deleted: {audio_path}")
        except:
            logger.error("Analysis thread failed")


def fix_incorrect_states():
    try:
        rows_updated = (
            db.session.query(Record)
            .filter(
                Record.state.in_([ANALYSIS_STATE, DOWNLOAD_STATE, DOWNLOADED_STATE])
            )
            .update({Record.state: INIT_STATE}, synchronize_session=False)
        )
        db.session.commit()
        logger.info(f"Updated incorrect states: {rows_updated}")
    except Exception as e:
        logger.error(e)

logger.info(f"Worker id: {current_worker_id}")

download_threads_limit = app.config.get("RUBLOCKER_DOWNLOAD_THREADS_LIMIT", 1)
for i in range(download_threads_limit):
    threading.Thread(target=download, daemon=True, name="download" + str(i)).start()
logger.info(f"Download threads started (count: {download_threads_limit})")

analysis_threads_limit = app.config.get("RUBLOCKER_ANALYSIS_THREADS_LIMIT", 1)
for i in range(analysis_threads_limit):
    threading.Thread(target=analyze, daemon=True, name="analysis" + str(i)).start()
logger.info(f"Analysis threads started (count: {analysis_threads_limit})")

if __name__ == "__main__":
    app.run()
