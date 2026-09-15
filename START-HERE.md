# Naya folder — saaf shuruat

Ye poora system hai, ek jagah. **Purane folder ko chherne ki zaroorat nahi** — ye alag folder mein rakhein aur wahin se chalayein.

```
HONDA-HR-FINAL/
├── honda-hr-frontend/    React site (login, dashboard, history, admin, help)
├── cv-model/             Python backend (API + scoring)
├── Dockerfile            deploy ke liye
├── .dockerignore
└── .railwayignore        (ab andar hi hai — pehle alag se copy karni parti thi)
```

**Andar kya nahi hai (jaan bujh kar):** `.env`, `firebase-key.json`, `node_modules`, `.venv`, `storage`. Pehle do aap purane folder se layengi, baqi commands khud bana dengi.

---

## Is version mein kya badla

**Password ab Firebase ke paas hai, hamare server ke paas nahi.** Aap ne yahi kaha tha — "koi apna server nahi".

Iska seedha faida: **Forgot password ab sabke liye chalta hai.** Reset ka email Firebase khud bhejta hai, apne servers se, kisi bhi address par, muft. Pehle wo email hamare apne mail account se jata tha aur sirf aapke apne inbox tak pahunchta tha — kisi aur colleague tak nahi.

Iske saath ek shart aati hai jo hata nahi sakte: **sign up ke baad email confirm karna zaroori hai.** Wajah saaf hai — Firebase kisi ko bhi *koi bhi* address likh kar account banane deta hai. Agar confirmation na ho, to koi ajnabi `sadaf@honda.com.pk` likh kar account bana leta aur allowed-users list use andar bhi de deti, kyunki address to list par hai hi. Confirmation wali email wahi darwaza band karti hai.

**Phone / SMS wala option hata diya gaya hai.** Firebase ne kabhi SMS bheja hi nahi (usage graph "No Data" dikhata raha), aur uske liye paid Blaze plan bhi chahiye tha. Ab sirf do raaste hain.

---

## Step 1 — Folder apni jagah rakhein

Zip `Downloads` mein extract karein, phir:

```powershell
Copy-Item -Recurse -Force "$env:USERPROFILE\Downloads\HONDA-HR-FINAL" "C:\"
```

Ab poora project `C:\HONDA-HR-FINAL` par hai.

> Agar `C:\HONDA-HR-FINAL` pehle se maujood hai to `\*` lagayein — warna folder folder ke andar chala jata hai:
> `Copy-Item -Recurse -Force "$env:USERPROFILE\Downloads\HONDA-HR-FINAL\*" "C:\HONDA-HR-FINAL\"`

---

## Step 2 — Purane project se secret files uthayein

Ye zip mein nahi hain (hone bhi nahi chahiyein):

```powershell
Copy-Item "C:\hr\cv-model\.env" "C:\HONDA-HR-FINAL\cv-model\.env"
Copy-Item "C:\hr\honda-hr-frontend\.env" "C:\HONDA-HR-FINAL\honda-hr-frontend\.env"
Copy-Item "C:\hr\cv-model\firebase-key.json" "C:\HONDA-HR-FINAL\cv-model\" -ErrorAction SilentlyContinue
```

Agar frontend wali `.env` purane folder mein na ho:

```powershell
Copy-Item "C:\HONDA-HR-FINAL\honda-hr-frontend\.env.production" "C:\HONDA-HR-FINAL\honda-hr-frontend\.env"
```

---

## Step 3 — Backend tayar karein

```powershell
cd C:\HONDA-HR-FINAL\cv-model
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Pehli dafa **5–10 minute** (torch bara hai). Ek dafa ka kaam hai.

Check:

```powershell
python -m pytest tests\ -q
```

**163 passed** aana chahiye.

---

## Step 4 — Frontend tayar karein

**Naya PowerShell window:**

```powershell
cd C:\HONDA-HR-FINAL\honda-hr-frontend
npm install
```

2–4 minute. Ye bhi ek dafa ka kaam hai.

---

## Step 5 — Rozana chalana

**Do window, do command. Dono chalti rehni chahiyein.**

Window 1 — backend:

```powershell
cd C:\HONDA-HR-FINAL\cv-model
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --port 8000
```

Window 2 — frontend:

```powershell
cd C:\HONDA-HR-FINAL\honda-hr-frontend
npx vite
```

> `npm run dev` **istemal na karein** — aapki machine pe wo chup chaap band ho jata hai. `npx vite` chalta hai.

Phir: **http://localhost:5173**

**`cd` wali line hamesha saath chalayein.** Galat folder se chalane par vite khul to jata hai lekin galat cheez serve karta hai — ye masla aa chuka hai.

---

## Sign in ke do raaste

| Raasta | Pehli dafa | Uske baad |
|---|---|---|
| **Continue with Google** | ek click | ek click |
| **Email + password** | Sign up → email confirm karein | email + password |

### Naya banda kaise andar aata hai

1. Admin use **Administration** page par add karta hai (address list mein aana zaroori hai)
2. Wo banda **Continue with Google** dabaye — bas, ho gaya
   **ya** **Sign up** par apna password chune → Firebase link bhejega → link kholein → phir sign in

### Password bhool gaye

**Forgot password?** dabayein. Firebase khud reset link bhejta hai. Ab ye sab ke liye kaam karta hai — pehle nahi karta tha.

> **Aik baat clear rahe:** Google ho ya password, dono sirf ek sawal ka jawab dete hain — "ye mailbox is bande ka hai ya nahi". **Andar aane ki ijazat hamesha allowed-users list deti hai** (Administration page). List se bahar koi bhi Google account ho, jawab `403` hi milega. Verified email kabhi permission nahi thi aur na banni chahiye.

---

## Firebase Console mein kya on karna hai

**Authentication → Sign-in method:**

- **Google** → Enable (support email chunein)
- **Email/Password** → Enable — *ye naya hai, ab zaroori hai*

**Authentication → Settings → Authorized domains:**

```
localhost
caliper-production.up.railway.app
```

`localhost` khaas taur pe check karein — 28 April 2025 ke baad bane projects mein wo khud shamil nahi hota, aur uske bagair local pe Google sign-in `auth/unauthorized-domain` deta hai.

**Blaze plan ki ab zaroorat nahi.** Wo sirf SMS ke liye tha, aur SMS hata diya gaya. Email aur Google dono free (Spark) plan par unlimited chalte hain.

---

## Deploy

```powershell
cd C:\HONDA-HR-FINAL
.\railway up
```

`railway.exe` purane folder se yahan copy kar lein, ya `railway` global install kar lein.

`.railwayignore` ab folder ke andar hi hai, is liye `node_modules` upload nahi hoga aur **413** nahi aayega.

**Railway par ye Secrets honi chahiyein (Variables nahi):** `LLM_API_KEY`, `SMTP_PASSWORD`, `SESSION_SECRET`, `FIREBASE_CREDENTIALS`. Aur `SESSION_COOKIE_SECURE=1`.

⚠️ **Har deploy pe data mit jata hai** (users, past rankings, audit log) — database container ke andar hai. Railway mein **Volume** laga kar ye hamesha ke liye theek hota hai:

- Mount path: `/home/app/service/storage`
- Variables mein: `RAILWAY_RUN_UID=0` aur `PYTHONUSERBASE=/home/app/.local`

Ye abhi tak nahi hua — jab tak nahi hota, har deploy ke baad admin ko users dobara add karne parenge.

---

## Kuch galat ho to

| Kya dikh raha hai | Wajah | Hal |
|---|---|---|
| `npx vite` chup chaap band | Galat folder | `cd` wali line pehle chalayein |
| Google button ghayab | `.env` khali, ya vite restart nahi hua | Step 2, phir vite restart |
| **"Demo mode"** peela banner | Backend band hai | Window 1 dekhein |
| "Failed to fetch" | Backend band hai | Window 1 dekhein |
| Google pe `unauthorized-domain` | `localhost` authorized domains mein nahi | Firebase Console |
| "Email and password sign-in is not switched on" | Firebase mein Email/Password enable nahi | Firebase Console |
| Confirmation email nahi aayi | Spam folder | Phir "Send it again" |
| Purana code chal raha hai | Process restart nahi hua | Dono Ctrl+C kar ke dobara |

**Ek usool:** `.env` aur Python code sirf **startup** pe parhe jate hain. Page refresh se kuch nahi hota — process restart karna parta hai.

---

## Ek zaroori yaad-dehani

Asli candidate CVs **deployed (public) site pe upload na karein** — sirf local pe, ya jab IT supervisor sign-off de. Groq CV ka text Pakistan se bahar ek third-party server pe bhejta hai.
