from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, tempfile, boto3
from google.cloud import texttospeech

# 載入 .env 環境變數
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# 語音預設設定
GOOGLE_LANGUAGE_CODE = os.getenv("GOOGLE_TTS_LANGUAGE_CODE", "cmn-TW")
GOOGLE_VOICE_NAME = os.getenv("GOOGLE_TTS_VOICE_NAME", "cmn-TW-Wavenet-A")

# AWS 設定
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

# 初始化
app = Flask(__name__)
CORS(app)

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

@app.route("/api/tts", methods=["POST"])
def google_tts():
    data = request.get_json()
    text = data.get("text", "").strip()
    filename = data.get("filename", "output.mp3")
    rate = float(data.get("rate", os.getenv("GOOGLE_TTS_SPEAKING_RATE", "1.0")))
    pitch = float(os.getenv("GOOGLE_TTS_PITCH", "0.0"))

    if not text:
        return jsonify({"error": "❌ 未提供文字"}), 400

    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=GOOGLE_LANGUAGE_CODE,
            name=GOOGLE_VOICE_NAME
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=rate,
            pitch=pitch
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
    except Exception as e:
        return jsonify({"error": "❌ 語音產生錯誤", "details": str(e)}), 500

    # 上傳至 S3
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmpfile:
        tmpfile.write(response.audio_content)
        tmp_path = tmpfile.name

    try:
        s3.upload_file(
            tmp_path, AWS_BUCKET_NAME, filename,
            ExtraArgs={"ContentType": "audio/mpeg"}
        )
        os.remove(tmp_path)

        signed_url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': AWS_BUCKET_NAME, 'Key': filename},
            ExpiresIn=300
        )
        return jsonify({"status": "ok", "url": signed_url})
    except Exception as e:
        return jsonify({"error": "❌ S3 上傳失敗", "details": str(e)}), 500

if __name__ == "__main__":
    print("✅ Flask 語音服務啟動中…")
    print(f"🌐 VOICE: {GOOGLE_VOICE_NAME}")
    print(f"☁️  S3 BUCKET: {AWS_BUCKET_NAME}")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)