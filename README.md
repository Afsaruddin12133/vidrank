# YouTube Auto Tag Generator

YouTube Auto Tag Generator is a complete, production-ready Google Chrome extension (Manifest V3) designed to optimize metadata creation workflows for creators. When uploading or editing a video in YouTube Studio, this extension automatically reads the video's title, generates SEO-friendly, highly targeted tags using a fully offline NLP algorithm, and inserts them directly into YouTube's Tags input field—eliminating the need to copy-paste.

---

## Key Features

1. **YouTube Studio Integration**: Works seamlessly on `https://studio.youtube.com/*`, dynamically adjusting between video details pages and upload workflows.
2. **Automatic Title Detection**: Instantly registers changes to the video title textbox, triggering automated re-tagging without lagging.
3. **Advanced Offline SEO Engine**:
   - Clean/tokenize titles and strip prepositions, articles, and pronouns.
   - Extract bi-grams, tri-grams, and quad-grams.
   - Detect geographic settings (e.g., `bangladesh`, `india`, `usa`) and temporal markers (e.g., `2026`) in the title to generate target variables.
   - Map titles against an offline thesaurus covering Finance, Tech, Gaming, Education, Lifestyle, Food, Fitness, and Music.
4. **Keystroke-Simulated Insertion**: Types tags sequentially into YouTube Studio's Polymer input container, dispatching `input`, `change`, and keystroke codes (Enter) to trigger YouTube's native saving.
5. **Modern Glassmorphism UI**: Floating sliding drawer sidebar on the right side of YouTube Studio, equipped with status switches, progress counts, and a scrollable log.
6. **Privacy-First Design**: Runs fully offline. No external APIs or web requests are made.

---

## File Structure

The project consists of the following modular files:

```text
Youtube tag generator/
├── manifest.json         # Manifest V3 configuration (permissions, scripts, action popup)
├── background.js         # Service worker setting default options on installation
├── tagGenerator.js       # Core SEO tokenizing and category classification algorithm
├── ui.js                 # HTML generation and binding controllers for the Sidebar
├── content.css           # Glassmorphism dark-theme style specifications for the Sidebar
├── content.js            # Orchestrator setting up observers and keystroke-simulation queues
├── popup.html            # Browser action panel layout
├── popup.css             # Browser action panel stylesheet
├── popup.js              # Sync storage controls and offline sandbox preview script
└── README.md             # This guide
```

---

## Installation Guide

To load the extension into your Chrome browser, follow these steps:

1. **Download / Copy Files**:
   Ensure all extension files are placed inside a folder named `Youtube tag generator` (e.g., `C:\Users\DST\Desktop\Youtube tag generator`).

2. **Open Extensions Page**:
   Open a new tab in Google Chrome and navigate to:
   ```text
   chrome://extensions/
   ```

3. **Enable Developer Mode**:
   In the top-right corner of the Extensions page, switch the **Developer mode** toggle to **ON**.

4. **Load Unpacked**:
   - Click the **Load unpacked** button in the top-left corner.
   - Select the `Youtube tag generator` folder containing `manifest.json`.
   - The extension card "YouTube Auto Tag Generator" will appear on the grid, confirming it was successfully loaded.

---

## How to Use

1. Navigate to [YouTube Studio](https://studio.youtube.com).
2. Click **Create** -> **Upload videos** to upload a new video, or click **Content** and click an existing video to edit its details.
3. A collapsible red tab with a tag icon will slide out on the right edge of the screen.
4. Click this tab to slide open the **YouTube Auto Tag Generator** sidebar.
5. In YouTube Studio, type or edit a title in the video title box (e.g., `"How to Earn Money Online in Bangladesh 2026"`).
6. **Tag Generation**:
   - If **Auto Generate** is toggled ON, the sidebar will instantly extract keywords and populate a list of tags.
   - If OFF, click the **Regenerate** button in the sidebar to create them manually.
7. **Tag Placement**:
   - Scroll down to the bottom of the video details page in YouTube Studio and click **SHOW MORE** to load the hidden Tags field.
   - If **Auto Insert** is toggled ON, the extension will automatically begin typing the tags one-by-one into YouTube's Tag field.
   - If OFF, you can click **Insert to Studio** to insert them, or **Copy Tags** to paste them manually.
8. Click **Save** in the top-right corner of YouTube Studio to persist the tags.

---

## Troubleshooting Guide

### 1. "Tags field not found / Sidebar says 'Tags field not yet loaded'"
* **Explanation**: YouTube Studio lazy-loads the tags input element. It only loads into the DOM after clicking the **SHOW MORE** link at the bottom of the details scroll area.
* **Fix**: Scroll down in YouTube Studio details and click **SHOW MORE**. The extension will detect the input within 1 second and allow insertion.

### 2. "The tag chips do not save or disappear when I click Save"
* **Explanation**: Programmatically updating text fields without triggering events will cause YouTube's framework (Polymer/React) to drop changes.
* **Fix**: This extension is built with keystroke simulators that dispatch a sequence of `input`, `change`, and `keydown/keyup` (Enter / keycode 13) events with appropriate delays. Ensure that you let the insertion finish (indicated by a green success log in the console) before clicking Save.

### 3. "Auto Generate/Insert settings are reset when loading a new tab"
* **Explanation**: Local state variables reset on page reloads.
* **Fix**: The extension saves all setting toggles inside `chrome.storage.sync`. Verify that storage syncing is allowed in your Google Chrome settings or that you are not running in Incognito mode where extension storage permissions might be constrained.

### 4. "The Sidebar is overlapping the scroll bar"
* **Explanation**: The sidebar is styled with a fixed position on the right viewport margin (`right: 0`).
* **Fix**: You can toggle the sidebar closed at any time by clicking the small red tag icon floating on its left border. When collapsed, it occupies 0px of your workspace.

### 5. "Changes to code do not take effect"
* **Explanation**: Chrome caches extension files.
* **Fix**: If you edit any code file, go back to `chrome://extensions/` and click the **Reload icon** (circular arrow) on the extension's card, then refresh your YouTube Studio page.
