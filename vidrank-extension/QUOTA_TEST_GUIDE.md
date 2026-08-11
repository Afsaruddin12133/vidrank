# Quota Counting Fix - Testing Guide with Logs

## Setup

1. **Rebuild the extension:**
   ```bash
   cd vidrank-extension
   npm run build
   ```

2. **Reload extension in Chrome:**
   - Go to `chrome://extensions/`
   - Find VidRank
   - Click refresh icon

3. **Open Chrome DevTools:**
   - Right-click on VidRank extension icon → Inspect Popup (for popup logs)
   - Go to YouTube Studio → F12 (for content script logs)
   - Go to `chrome://extensions/` → Click "service worker" link under VidRank (for background logs)

## Test Scenario 1: Generate Tags and Check Quota

### Steps:
1. Open VidRank popup and note quota (e.g., "10 / 10")
2. Go to YouTube Studio, open a video for editing
3. Click "✨ Confirm Title & Generate"
4. Wait for generation to complete
5. Open VidRank popup again

### Expected Logs in Background Service Worker Console:

```
🔵 [QUOTA] BEFORE API CALL: {used: 0, remaining: 10, limit: 10, plan: 'free'}
📥 [QUOTA] SERVER RESPONSE: {used: 1, limit: 10, plan: 'free'}
💾 [QUOTA] persistUsage UPDATE: {
  from: {used: 0, remaining: 10},
  to: {used: 1, remaining: 9},
  serverData: {used: 1, limit: 10, plan: 'free'}
}
🟢 [QUOTA] AFTER UPDATE: {used: 1, remaining: 9, limit: 10, plan: 'free'}
```

### Expected Logs in Popup Console:

```
👁️ [POPUP] Popup became visible, refreshing quota...
🔄 [POPUP] Refreshing quota from background...
📊 [QUOTA] Popup requested quota, refreshing from backend...
📊 [QUOTA] Sending to popup: {usageCount: 1, remaining: 9, plan: 'free', usageLimit: 10}
✅ [POPUP] Received quota: {usageCount: 1, remaining: 9, plan: 'free', usageLimit: 10}
✅ [POPUP] Displaying: 9 / 10 | Raw data: {used: 1, remaining: 9, limit: 10}
```

### Expected Result:
✅ Popup shows "9 / 10" (decreased by 1)

## Test Scenario 2: Multiple Generations

### Steps:
1. Generate tags for 3 videos in a row
2. After each generation, open popup and check quota

### Expected Progression:

**After 1st generation:**
- Background: `used: 1, remaining: 9`
- Popup: "9 / 10"

**After 2nd generation:**
- Background: `used: 2, remaining: 8`
- Popup: "8 / 10"

**After 3rd generation:**
- Background: `used: 3, remaining: 7`
- Popup: "7 / 10"

## What to Look For

### ✅ CORRECT Behavior:
- Background log shows quota update ONLY after server response
- `persistUsage` shows: `from: {used: X}` to `to: {used: X+1}`
- Popup displays the exact remaining count from server
- Each generation decrements by exactly 1

### ❌ WRONG Behavior (Old Bug):
- Quota decrements before API call
- Double counting (used: 0 → used: 2 after one generation)
- Popup shows wrong count

## Debugging Tips

If quota doesn't update:

1. **Check Background Console** - Look for:
   - `📥 [QUOTA] SERVER RESPONSE` - Confirms backend returned usage
   - `💾 [QUOTA] persistUsage UPDATE` - Confirms cache was updated

2. **Check Popup Console** - Look for:
   - `👁️ [POPUP] Popup became visible` - Confirms visibility listener fired
   - `✅ [POPUP] Displaying` - Shows what UI is rendering

3. **Check Backend Logs** - In dev_server.log or Cloudflare Workers logs:
   - Look for quota consumption messages
   - Verify `/v1/generate` returns usage object

## Clean Test (Reset Quota)

To test from fresh quota (10/10), you can:
1. Wait until next day (quota resets daily)
2. Or use admin dashboard to reset user's quota
3. Or create a test user account

---

**Pro Tip:** Keep all three consoles open side-by-side while testing to see the complete flow!
