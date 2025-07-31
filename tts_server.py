from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, tempfile, boto3, json
import google.generativeai as genai
from rapidfuzz import fuzz, process
from google.cloud import texttospeech
from random import choice

# ✅ 載入 .env 環境變數
load_dotenv()
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# ✅ Gemini 設定
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-pro')

# ✅ 語音預設設定（Google TTS）
GOOGLE_LANGUAGE_CODE = os.getenv("GOOGLE_TTS_LANGUAGE_CODE", "cmn-TW")
GOOGLE_VOICE_NAME = os.getenv("GOOGLE_TTS_VOICE_NAME", "cmn-TW-Wavenet-A")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

# ✅ 初始化 app
app = Flask(__name__)
CORS(app)

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# ✅ FAQ 問答邏輯
with open("FAQ.json", "r", encoding="utf-8") as f:
    FAQ_LIST = json.load(f)

@app.route("/ask", methods=["POST"])
def ask():
    user_question = request.json.get("question")
    SIMILARITY_THRESHOLD = 65

    all_pairs = []
    for faq in FAQ_LIST:
        questions = faq.get("q_variants", [])
        answers = faq.get("a_variants", [])
        for q in questions:
            all_pairs.append((q, answers))

    matches = process.extract(
        user_question,
        [q for q, _ in all_pairs],
        scorer=fuzz.token_sort_ratio,
        limit=1
    )

    best_question, similarity = matches[0]
    best_answer_set = next((a for q, a in all_pairs if q == best_question), None)

    if similarity >= SIMILARITY_THRESHOLD and best_answer_set:
        selected_answer = choice(best_answer_set)
        prompt = f"""
你是一位親切的導覽員，負責講解黃金蝙蝠知識。
請用自然口吻換句話說下面這段文字，避免機械感，但不要改變內容意義。

原始資料：
「{selected_answer}」
"""
    else:
        prompt = f"""
你是一位黃金蝙蝠導覽員。請針對以下問題回答，限制只能講黃金蝙蝠的資訊，
不要談論其他動物或非相關主題。如果不知道答案，可以誠實說明資料有限。

使用者問題：
「{user_question}」
"""

    try:
        response = model.generate_content(prompt)
        return jsonify({"answer": response.text.strip(), "source": "FAQ" if similarity >= SIMILARITY_THRESHOLD else "AI"})
    except Exception as e:
        return jsonify({"answer": f"⚠️ 回答失敗：{str(e)}"}), 500

# ✅ 語音 API：Google TTS + S3 上傳
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
    print("✅ Flask 語音+問答服務啟動中…")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
