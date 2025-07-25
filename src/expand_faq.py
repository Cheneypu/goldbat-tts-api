import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

# 讀取 .env 環境變數
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# 初始化 Gemini 模型
model = genai.GenerativeModel("models/gemini-1.5-flash")

def gen_variants(question: str, n: int = 5) -> list[str]:
    prompt = (
        f"請針對問題「{question}」列出{n}個用戶可能會用的同義問法，"
        f"不包含原句，每句只要一句話。"
    )
    response = model.generate_content(prompt)
    text = response.text
    return [line.strip(" -") for line in text.split("\n") if line.strip()]

# FAQ 檔案路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAQ_PATH = os.path.join(BASE_DIR, "..", "public", "data", "FAQ.json")

# 讀原始 JSON
with open(FAQ_PATH, "r", encoding="utf-8") as f:
    faqs = json.load(f)

# 生成變體並合併
expanded = []
for item in faqs:
    base_q = item["q_variants"][0]
    variants = [base_q] + gen_variants(base_q, 5)
    expanded.append({
        "q_variants": variants,
        "a_variants": item["a_variants"]
    })

# 寫回同一份檔案
with open(FAQ_PATH, "w", encoding="utf-8") as f:
    json.dump(expanded, f, ensure_ascii=False, indent=2)

print(f"✅ FAQ 擴充完成，共 {len(expanded)} 條目。")
