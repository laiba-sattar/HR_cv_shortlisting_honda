# Caliper — chalane ka tareeqa (step by step)

Do terminal chahiye. **Ek backend ke liye, ek frontend ke liye.** Ye sab se
badi galti hai jo baar baar hoti hai — dono command ek hi terminal me chalao
to `No module named uvicorn` jaisi error aati hai.

| Kya | Folder | Port | Terminal |
|---|---|---|---|
| Backend (model + API) | `cv-model` | 8000 | Terminal 1 |
| Frontend (website) | `honda-hr-frontend` | 5173 | Terminal 2 |

---

## Step 0 — VS Code kholo

VS Code me `C:\hr` folder open karo (File → Open Folder).

Terminal kholne ke liye: **Ctrl + `**
Doosra terminal banane ke liye: terminal panel ke upar **+** ka button.

---

## Step 1 — Terminal 1: Backend

```powershell
cd C:\hr\cv-model
.\.venv\Scripts\activate
```

Activate hone ke baad line ke shuru me `(.venv)` likha aayega. Agar na aaye to
venv abhi bana nahi — sirf pehli baar ye chalao:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Ab server start karo:

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

Sahi chal raha ho to terminal me kuch aisa dikhega:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

> Ye lines **output** hain — inko terminal me type nahi karna.

Check karne ke liye browser me kholo: <http://localhost:8000/api/health>
JSON dikhna chahiye jisme aapka model ka naam ho.

**Ye terminal chalta rehne do.** Band karoge to website kaam karna band kar
degi. Rokna ho to `Ctrl + C`.

---

## Step 2 — Terminal 2: Frontend

Naya terminal kholo (**+** button), phir:

```powershell
cd C:\hr\honda-hr-frontend
npm run dev
```

Pehli baar ho to us se pehle ek dafa `npm install` chala lena.

Terminal me link aayega:

```
  ➜  Local:   http://localhost:5173/
```

Wahi kholo browser me. Caliper ka login page aayega.

---

## Step 3 — Login

1. Apni email (jo `ADMIN_EMAILS` me hai) aur password likho — **dono ek hi
   screen par**.
2. **Sign in** dabao.
3. Pehli baar ho to email par 6 digit ka code aayega. Wo daal do — password
   usi waqt save ho jayega.
4. Agli dafa sirf email + password kaafi hai, code nahi aayega.

Password bhool jao to **Forgot password?** — naya password likho, code email
par aayega, verify karte hi naya password lag jayega.

---

## Step 4 — Ranking chalana

1. Job title likho.
2. JD upload karo ya paste karo → **Read requirements**.
3. Qualification, experience aur age check karo. Jo JD me na mile, wo khud
   likhna zaroori hai — warna ranking start nahi hogi.
4. CVs add karo.
5. **Rank** dabao.

Age sirf flag hoti hai, score me kabhi nahi jaati. Final score teen cheezon ka
barabar average hai (33.3% har ek): qualification, relevant experience, aur
JD & skills.

---

## Band kaise karna hai

Dono terminals me `Ctrl + C`.

Agar kabhi purana server background me atka reh jaye (health page purana model
dikhaye, ya port busy bole):

```powershell
taskkill /F /IM python.exe
```

Phir Step 1 dobara.

---

## `.env` me kya hona chahiye

File: `C:\hr\cv-model\.env` — **ye file kabhi GitHub par push nahi karni.**

```
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_API_KEY=<aapki groq key>

EMBED_PROVIDER=sentence_transformers

ADMIN_EMAILS=<4 emails, comma se alag>
SESSION_SECRET=<lamba random string>
SESSION_COOKIE_SECURE=0

EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<aapki gmail>
SMTP_PASSWORD=<16 digit App Password>
EMAIL_FROM=Caliper <aapki gmail>
```

Email theek chal rahi hai ya nahi, test karne ke liye (backend terminal me):

```powershell
python mailtest.py
```

---

## Aam errors aur unka hal

| Terminal kya kehta hai | Wajah | Hal |
|---|---|---|
| `No module named uvicorn` | frontend wale terminal me backend command chala di | `cd C:\hr\cv-model` phir `.\.venv\Scripts\activate` |
| `Failed to fetch` (website par) | backend band hai | Terminal 1 dekho, uvicorn chal raha hai? |
| `model_not_found` | Groq ne wo model hata diya | <https://console.groq.com/docs/models> se naya ID le kar `.env` me `LLM_MODEL` badlo |
| `429 rate limit` | Groq ki free limit | Thoda ruk kar dobara — system khud wait karta hai |
| Health page purana model dikhata hai | purana server background me chal raha hai | `taskkill /F /IM python.exe` phir Step 1 |
| `The code could not be emailed` | SMTP settings galat | `python mailtest.py` chala kar dekho kya bolta hai |
| Port 8000 busy | pehle se koi server chal raha hai | `taskkill /F /IM python.exe` |

---

## Tests chalane ke liye (optional)

Backend terminal me:

```powershell
python -m pytest -q
```

Sab pass hone chahiye.
