# PRISgen int'l Limited — V1 Deploy Guide

## What's in V1
- Flask app skeleton
- PostgreSQL ready (SQLite locally, Postgres on Render)
- /lady login page (Lady C branded)
- Session auth with rate limiting (5 attempts, 30 min lockout)
- Activity vault at /lady/vault
- All routes wired up, ready for V2 content

---

## Step 1 — GitHub

1. Create a new GitHub repo called `prisgen`
2. Upload ALL files keeping the folder structure:
   ```
   app.py
   config.txt
   requirements.txt
   Procfile
   templates/
     index.html
     login.html
     vault.html
     product.html
   ```

---

## Step 2 — Render (free hosting)

1. Go to render.com → Sign up / Log in
2. Click **New** → **Web Service**
3. Connect your GitHub → select the `prisgen` repo
4. Fill in:
   - **Name**: prisgen
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
5. Click **Create Web Service**

---

## Step 3 — Add PostgreSQL on Render

1. In Render dashboard → **New** → **PostgreSQL**
2. Name it `prisgen-db`, pick the free plan
3. Once created, copy the **Internal Database URL**
4. Go back to your Web Service → **Environment** tab
5. Add environment variable:
   - Key: `DATABASE_URL`
   - Value: (paste the URL)
6. Also add:
   - Key: `SECRET_KEY`
   - Value: (make up any long random string)
   - Key: `WHATSAPP_NUMBER`
   - Value: `2348023905056`

---

## Step 4 — Test

Visit your Render URL (e.g. `prisgen.onrender.com`)

- Homepage: shows V1 placeholder ✓
- Visit `/lady` → Lady C login page ✓
- Enter password `LadyC_PRISgen2026` → redirects home, shows admin notice ✓
- Visit `/lady/vault` → activity log ✓

---

## Changing the password

Open `config.txt` and change the line:
```
password=LadyC_PRISgen2026
```
to whatever you want. Push to GitHub → Render redeploys automatically.

---

## Notes
- Free Render tier sleeps after 15 mins inactivity. First visitor waits ~30s.
- Upgrade to Render Starter ($7/mo) to keep it always awake.
- Custom domain (prisgen.com) can be added in Render dashboard under your service → Settings → Custom Domains.
