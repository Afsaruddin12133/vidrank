# 🚀 VidRank Backend - How to Run

## ✅ Current Status: Backend is RUNNING!

```bash
# Test it:
curl http://localhost:8787/healthz
# Response: {"ok":true}
```

---

## 🎯 How to Start/Stop Backend

### Option 1: Using dev_server.py (Development) ✅ RECOMMENDED

#### Start Backend:
```bash
cd /Users/macm1/Desktop/vidrank/backend

# Start in background (keeps running)
nohup uv run python dev_server.py > dev_server.log 2>&1 &

# Or start in foreground (see logs directly)
uv run python dev_server.py
```

#### Check if Running:
```bash
curl http://localhost:8787/healthz
# Should return: {"ok":true}
```

#### View Logs:
```bash
cd /Users/macm1/Desktop/vidrank/backend
tail -f dev_server.log
```

#### Stop Backend:
```bash
# Find the process
ps aux | grep dev_server

# Kill it
pkill -f "dev_server.py"

# Or kill by PID
kill <PID>
```

---

### Option 2: Using wrangler dev (Alternative)

```bash
cd /Users/macm1/Desktop/vidrank/backend

# Start with wrangler
npx wrangler dev

# Or if wrangler is installed globally
wrangler dev
```

**Note:** wrangler dev is for testing Cloudflare Workers locally

---

## 📋 Backend Commands Cheat Sheet

```bash
# Go to backend directory
cd /Users/macm1/Desktop/vidrank/backend

# Start backend (background)
nohup uv run python dev_server.py > dev_server.log 2>&1 &

# Check if running
curl http://localhost:8787/healthz

# Check admin dashboard
open http://localhost:5173

# View logs
tail -f dev_server.log

# Stop backend
pkill -f "dev_server.py"

# Restart backend
pkill -f "dev_server.py" && sleep 2 && nohup uv run python dev_server.py > dev_server.log 2>&1 &
```

---

## 🔧 Troubleshooting

### Issue 1: "Port 8787 already in use"

**Check what's using it:**
```bash
lsof -i :8787
```

**Kill the process:**
```bash
kill -9 <PID>
```

---

### Issue 2: "uv: command not found"

**Install uv:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or use python directly:
```bash
python3 dev_server.py
```

---

### Issue 3: Backend crashes immediately

**Check logs:**
```bash
cat dev_server.log
```

**Common causes:**
- Missing dependencies
- Database not initialized
- Port already in use

**Fix dependencies:**
```bash
cd /Users/macm1/Desktop/vidrank/backend
uv pip install -r requirements.txt
```

---

## 🎯 Backend Endpoints

Once running on http://localhost:8787:

```bash
# Health check
curl http://localhost:8787/healthz

# Auth endpoints
POST http://localhost:8787/v1/auth/login
POST http://localhost:8787/v1/auth/logout

# Generation endpoint
POST http://localhost:8787/v1/generate

# User info
GET http://localhost:8787/v1/me

# Admin dashboard
http://localhost:5173
```

---

## 📊 Backend Structure

```
backend/
├── dev_server.py          ← Local development server
├── app/
│   ├── main.py           ← FastAPI app
│   ├── db.py             ← Database operations
│   ├── router.py         ← Request routing
│   └── quotas.py         ← Quota management
├── frontend/             ← Admin dashboard
│   └── src/
├── .dev.vars             ← Environment variables
└── wrangler.toml         ← Cloudflare config
```

---

## 🚀 Quick Start (If Backend Stopped)

```bash
# 1. Go to backend directory
cd /Users/macm1/Desktop/vidrank/backend

# 2. Start backend
nohup uv run python dev_server.py > dev_server.log 2>&1 &

# 3. Wait 2 seconds
sleep 2

# 4. Test it
curl http://localhost:8787/healthz

# 5. Should see: {"ok":true}
```

---

## 🎉 You're Ready!

**Backend is running on:** http://localhost:8787

**Admin Dashboard:** http://localhost:5173

**Extension Backend URL:** http://localhost:8787/v1

---

## 💡 Tips

1. **Keep terminal open** when starting in foreground to see logs
2. **Use nohup** to run in background and keep running after closing terminal
3. **Check logs** regularly: `tail -f dev_server.log`
4. **Health check** before testing: `curl http://localhost:8787/healthz`

---

**Backend is already running! ✅ No need to start it again!**
