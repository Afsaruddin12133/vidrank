// YouTube Auto Tag Generator - Injected Sidebar UI

// Strip spaces/specials, lowercase, prepend # (was TagGenerator.toHashtags)
function toHashtags(tags) {
  if (!tags || !Array.isArray(tags)) return [];
  return tags.map(tag => {
    const cleaned = tag.replace(/[^a-zA-Z0-9\u0980-\u09FF]/g, '').toLowerCase();
    return cleaned.startsWith('#') ? cleaned : '#' + cleaned;
  }).filter(t => t.length > 1);
}

class YouTubeStudioUI {
  constructor(options = {}) {
    this.containerId = 'yt-auto-tag-sidebar';
    this.element = null;
    this.isOpen = false;
    this.tags = [];
    this.isLoggedIn = options.isLoggedIn || false;
    
    // Callback registers
    this.onToggleHashtag = options.onToggleHashtag || (() => {});
    this.onRegenerate = options.onRegenerate || (() => {});
    this.onInsertTags = options.onInsertTags || (() => {});
    
    this.init();
  }

  /**
   * Initialize Sidebar elements and mount to document body.
   */
  init() {
    if (document.getElementById(this.containerId)) {
      console.warn("[YouTube Tag Generator] Sidebar UI already exists.");
      this.element = document.getElementById(this.containerId);
      return;
    }

    // Load initial settings
    chrome.storage.sync.get({
      autoGenerate: true,
      autoInsert: true,
      hashtagMode: false,
      maxTagsCount: 35,
      preferredSeparator: ","
    }, (settings) => {
      this.createSidebar(settings);
      this.log("Sidebar UI loaded and initialized.", "info");
    });
  }

  /**
   * Create HTML structure of the sidebar and insert it into the DOM.
   */
  createSidebar(settings) {
    const sidebar = document.createElement('div');
    sidebar.id = this.containerId;
    sidebar.className = 'yt-sidebar-panel';

    let innerContent = '';

    if (!this.isLoggedIn) {
      innerContent = `
        <div class="yt-sidebar-wrapper" style="justify-content: center; text-align: center; padding: 20px;">
          <h2 style="color: white; margin-bottom: 12px; font-family: 'Outfit', sans-serif;">VidRank is Locked</h2>
          <p style="color: #aaaaaa; font-size: 13px; line-height: 1.5; margin-bottom: 24px;">Please sign in with Google to unlock all features.</p>
          <button id="yt-sidebar-btn-login" style="background: white; color: black; border-radius: 8px; padding: 12px; width: 100%; border: none; font-weight: 600; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 10px; font-family: 'Outfit', sans-serif; font-size: 14px;">
            <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            Sign in with Google
          </button>
          <div id="yt-sidebar-login-error" style="color: #ff4444; margin-top: 15px; font-size: 12px; display: none;"></div>
        </div>
      `;
    } else {
      innerContent = `
        <!-- Header -->
        <div class="yt-sidebar-header">
          <div class="yt-sidebar-title-row">
            <h2>VidRank</h2>
          </div>
          <p class="yt-sidebar-subtitle">Optimize Every Video. Unlock Better YouTube Rankings.</p>
        </div>

        <!-- Controls / Switches -->
        <div class="yt-sidebar-section">

          <div class="yt-control-row">
            <label for="yt-toggle-insert" class="yt-switch-label">
              <span>Auto Insert to Studio</span>
              <span class="yt-label-help" title="Automatically type generated tags into YouTube's Tags textfield.">?</span>
            </label>
            <label class="yt-switch">
              <input type="checkbox" id="yt-toggle-insert" ${settings.autoInsert ? 'checked' : ''}>
              <span class="yt-slider"></span>
            </label>
          </div>

          <div class="yt-control-row">
            <label for="yt-toggle-hashtag" class="yt-switch-label">
              <span>Hashtag Mode</span>
              <span class="yt-label-help" title="Remove spaces and add '#' to the front of tags.">?</span>
            </label>
            <label class="yt-switch">
              <input type="checkbox" id="yt-toggle-hashtag" ${settings.hashtagMode ? 'checked' : ''}>
              <span class="yt-slider"></span>
            </label>
          </div>
        </div>

        <!-- Detected Title Info -->
        <div class="yt-sidebar-section yt-info-section">
          <div class="yt-info-item">
            <span class="yt-info-key">Detected Title:</span>
            <span class="yt-info-val" id="yt-sidebar-detected-title">Waiting for video details...</span>
          </div>
          <div class="yt-info-item">
            <span class="yt-info-key">Tag Count / Limit:</span>
            <span class="yt-info-val"><strong id="yt-tag-counter">0</strong> / <span id="yt-max-tags-limit">${settings.maxTagsCount}</span> tags</span>
          </div>
          <div class="yt-info-item">
            <span class="yt-info-key">Total Size:</span>
            <span class="yt-info-val"><strong id="yt-char-counter">0</strong> / 500 characters</span>
          </div>
          <div class="yt-info-item">
            <span class="yt-info-key">Last Synced:</span>
            <span class="yt-info-val" id="yt-last-update-time">-</span>
          </div>
        </div>

        <!-- Tags Container -->
        <div class="yt-sidebar-tags-section">
          <div class="yt-tags-header-row">
            <h3>Generated Tags</h3>
            <span class="yt-tags-placeholder-tip">No tags generated yet. Type a title to start.</span>
          </div>
          
          <div class="yt-chips-container" id="yt-chips-container">
            <!-- Chips injected dynamically -->
          </div>

          <!-- Add manual tag input -->
          <div class="yt-add-manual-tag-row">
            <input type="text" id="yt-manual-tag-input" placeholder="Type a custom tag and hit Enter..." />
            <button id="yt-manual-tag-add-btn" title="Add Tag">+</button>
          </div>
        </div>

        <!-- Actions Panel Footer -->
        <div class="yt-sidebar-footer">
          <button id="yt-action-regenerate" class="yt-btn yt-btn-primary">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
            </svg>
            <span>Regenerate Tags</span>
          </button>
          
          <button id="yt-action-insert" class="yt-btn yt-btn-secondary">
            <span>Insert to Studio</span>
          </button>

          <div class="yt-btn-group-row" style="margin-top: 8px;">
            <button id="yt-action-copy" class="yt-btn yt-btn-outline" title="Copy comma separated tags list">
              Copy Tags
            </button>
            <button id="yt-action-clear" class="yt-btn yt-btn-outline" title="Clear all tags">
              Clear All
            </button>
          </div>
        </div>
      </div>
      `;
    }

    sidebar.innerHTML = `
      <!-- Collapsible trigger tab -->
      <button id="yt-sidebar-toggle-btn" class="yt-sidebar-toggle-btn" title="Toggle Tag Generator">
        <img src="${chrome.runtime.getURL('assets/icons/logo.png')}" width="20" height="20" alt="VidRank Logo">
        <span class="badge" id="yt-sidebar-badge-count" style="display: none;">0</span>
      </button>

      <!-- Sidebar Content Wrapper -->
      <div class="yt-sidebar-wrapper">
        ${innerContent}
      </div>
    `;

    document.body.appendChild(sidebar);
    this.element = sidebar;

    // Attach Event Listeners
    this.attachEventListeners();
  }

  /**
   * Bind event actions to HTML DOM controls.
   */
  attachEventListeners() {
    const toggleBtn = document.getElementById('yt-sidebar-toggle-btn');
    
    if (!this.isLoggedIn) {
      // Only attach toggle open/close for locked state
      toggleBtn.addEventListener('click', () => {
        this.isOpen = !this.isOpen;
        this.element.classList.toggle('open', this.isOpen);
      });

      const btnLogin = document.getElementById('yt-sidebar-btn-login');
      const errorMsg = document.getElementById('yt-sidebar-login-error');
      
      if (btnLogin) {
        btnLogin.addEventListener('click', () => {
          btnLogin.disabled = true;
          btnLogin.style.opacity = '0.7';
          errorMsg.style.display = 'none';

          chrome.runtime.sendMessage({ action: "login" }, (response) => {
            btnLogin.disabled = false;
            btnLogin.style.opacity = '1';
            
            if (chrome.runtime.lastError || !response || !response.success) {
              errorMsg.textContent = response?.error || chrome.runtime.lastError?.message || "Login failed.";
              errorMsg.style.display = 'block';
            }
          });
        });
      }
      return;
    }

    const toggleInsert = document.getElementById('yt-toggle-insert');
    const toggleHashtag = document.getElementById('yt-toggle-hashtag');
    const btnRegenerate = document.getElementById('yt-action-regenerate');
    const btnInsert = document.getElementById('yt-action-insert');
    const btnCopy = document.getElementById('yt-action-copy');
    const btnClear = document.getElementById('yt-action-clear');
    const manualInput = document.getElementById('yt-manual-tag-input');
    const manualAddBtn = document.getElementById('yt-manual-tag-add-btn');

    // Sidebar sliding drawer toggle
    toggleBtn.addEventListener('click', () => {
      this.isOpen = !this.isOpen;
      this.element.classList.toggle('open', this.isOpen);
      
      // Hide badge count if opened
      if (this.isOpen) {
        document.getElementById('yt-sidebar-badge-count').style.display = 'none';
      }
    });

    // Auto-insert switch listener
    toggleInsert.addEventListener('change', (e) => {
      const active = e.target.checked;
      chrome.storage.sync.set({ autoInsert: active }, () => {
        this.log(`Auto Insert toggled: ${active}`, "success");
      });
    });

    // Hashtag Mode switch listener
    if (toggleHashtag) {
      toggleHashtag.addEventListener('change', (e) => {
        const active = e.target.checked;
        chrome.storage.sync.set({ hashtagMode: active }, () => {
          this.log(`Hashtag Mode toggled: ${active}`, "success");
          this.updateTagsList(this.tags); // Re-render tags instantly
          this.onToggleHashtag(active);
        });
      });
    }

    // Action buttons
    this.checkAndApplyPaywall();
    
    // Listen for storage changes to instantly apply paywall if generated from another button
    chrome.storage.onChanged.addListener((changes, namespace) => {
      if (namespace === 'local' && (changes.usageCount || changes.plan || changes.usageLimit)) {
        this.checkAndApplyPaywall();
      }
    });

    btnRegenerate.addEventListener('click', () => {
      chrome.storage.local.get(["usageCount", "plan", "usageLimit", "uid", "retry_after"], (data) => {
        const count = data.usageCount || 0;
        const plan = data.plan || "free";
        const limit = data.usageLimit != null ? data.usageLimit : 10;
        const uid = data.uid || "";
        
        if (plan === "free" && limit >= 0 && count >= limit) {
          window.open(`https://www.vidrank.tech/?userId=${uid}`, '_blank');
          return;
        }

        const waitSeconds = data.retry_after || 0;

        if (plan === "free" && waitSeconds > 0) {
          let remaining = waitSeconds;
          
          btnRegenerate.disabled = true;
          const originalHTML = btnRegenerate.innerHTML;
          btnRegenerate.innerHTML = `<span>Wait ${remaining}s...</span>`;
          
          const timerId = setInterval(() => {
            remaining--;
            if (remaining > 0) {
              btnRegenerate.innerHTML = `<span>Wait ${remaining}s...</span>`;
            } else {
              clearInterval(timerId);
              btnRegenerate.innerHTML = originalHTML;
              btnRegenerate.disabled = false;
              this.log("Regenerate tags manually requested.", "info");
              this.onRegenerate();
            }
          }, 1000);
          return;
        }

        this.log("Regenerate tags manually requested.", "info");
        this.onRegenerate();
      });
    });

    btnInsert.addEventListener('click', () => {
      this.log("Manual tags placement started...", "info");
      this.onInsertTags(this.tags);
    });

    btnCopy.addEventListener('click', () => {
      this.copyTagsToClipboard();
    });

    btnClear.addEventListener('click', () => {
      this.clearTags();
    });

    // Add manual tag triggers
    manualInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        this.addManualTag();
      }
    });

    manualAddBtn.addEventListener('click', () => {
      this.addManualTag();
    });

    // Global settings sync channel (e.g. settings updated from Popup)
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'sync') {

        if (changes.autoInsert) {
          toggleInsert.checked = changes.autoInsert.newValue;
        }

        if (changes.hashtagMode && toggleHashtag) {
          toggleHashtag.checked = changes.hashtagMode.newValue;
          this.updateTagsList(this.tags); // Re-render chips
        }
        if (changes.maxTagsCount) {
          document.getElementById('yt-max-tags-limit').textContent = changes.maxTagsCount.newValue;
        }
      }
    });
  }

  /**
   * Log action updates to sidebar UI console panel.
   */
  log(msg, level = 'info') {
    // Only console.log under the hood now that UI is removed
    console.log(`[VidRank] ${level.toUpperCase()}: ${msg}`);
  }

  /**
   * Update the detected title text in the sidebar.
   */
  updateDetectedTitle(title) {
    const titleEl = document.getElementById('yt-sidebar-detected-title');
    if (titleEl) {
      titleEl.textContent = title ? title : "Waiting for video details...";
      titleEl.title = title; // tooltip for full text
    }
  }

  /**
   * Check usage limits and apply a premium blurred paywall overlay if maxed out.
   */
  checkAndApplyPaywall() {
    chrome.storage.local.get(["usageCount", "plan", "usageLimit"], (data) => {
      const isFree = (data.plan || "free") === "free";
      const limit = data.usageLimit != null ? data.usageLimit : 10;
      const limitReached = limit >= 0 && (data.usageCount || 0) >= limit;
      
      if (isFree && limitReached) {
        this.applyPaywallOverlay();
      }
    });
  }

  applyPaywallOverlay() {
    const wrapper = this.element.querySelector('.yt-sidebar-wrapper');
    if (!wrapper || this.element.querySelector('.yt-paywall-overlay')) return;

    // Blur the sidebar contents
    wrapper.style.filter = 'blur(6px)';
    wrapper.style.pointerEvents = 'none';
    wrapper.style.userSelect = 'none';

    // Create the overlay container
    const overlay = document.createElement('div');
    overlay.className = 'yt-paywall-overlay';
    overlay.style.position = 'absolute';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.display = 'flex';
    overlay.style.flexDirection = 'column';
    overlay.style.justifyContent = 'center';
    overlay.style.alignItems = 'center';
    overlay.style.background = 'rgba(15, 15, 15, 0.2)';
    overlay.style.zIndex = '1000';
    overlay.style.padding = '20px';
    overlay.style.textAlign = 'center';
    overlay.style.boxSizing = 'border-box';

    overlay.innerHTML = `
      <div style="background: #181818; padding: 32px 24px; border-radius: 16px; border: 1px solid rgba(255, 215, 0, 0.4); box-shadow: 0 16px 40px rgba(0,0,0,0.5), 0 0 40px rgba(255, 215, 0, 0.1); width: 100%; box-sizing: border-box;">
        <svg viewBox="0 0 24 24" width="56" height="56" fill="#FFD700" style="margin-bottom: 20px; filter: drop-shadow(0 0 8px rgba(255, 215, 0, 0.4));">
          <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
        </svg>
        <h2 style="color: #FFD700; margin-bottom: 16px; font-family: 'Outfit', sans-serif; font-size: 22px; font-weight: 700; letter-spacing: 0.5px;">Limit Reached</h2>
        <p style="color: #e0e0e0; font-size: 14px; line-height: 1.6; margin-bottom: 28px; font-family: 'Outfit', sans-serif;">You've used all your free optimizations for today.<br><br>Unlock unlimited generations and higher rankings instantly.</p>
        <button id="yt-sidebar-btn-upgrade-overlay" style="background: linear-gradient(135deg, #FFD700 0%, #FDB931 100%); color: #000; border-radius: 10px; padding: 14px 20px; border: none; font-weight: 700; cursor: pointer; font-family: 'Outfit', sans-serif; font-size: 15px; text-transform: uppercase; letter-spacing: 0.8px; width: 100%; box-shadow: 0 6px 20px rgba(255, 215, 0, 0.35); transition: all 0.2s ease;">
          ⭐ Upgrade to Pro
        </button>
      </div>
    `;

    this.element.appendChild(overlay);

    const upgradeBtn = document.getElementById('yt-sidebar-btn-upgrade-overlay');
    upgradeBtn.addEventListener('mouseenter', () => {
      upgradeBtn.style.transform = 'translateY(-2px)';
      upgradeBtn.style.boxShadow = '0 8px 25px rgba(255, 215, 0, 0.5)';
    });
    upgradeBtn.addEventListener('mouseleave', () => {
      upgradeBtn.style.transform = 'translateY(0)';
      upgradeBtn.style.boxShadow = '0 6px 20px rgba(255, 215, 0, 0.35)';
    });
    upgradeBtn.addEventListener('click', () => {
      chrome.storage.local.get(['uid'], (data) => {
        const uid = data.uid || '';
        window.open(`https://www.vidrank.tech/?userId=${uid}`, '_blank');
      });
    });
  }

  /**
   * Update sidebar state values and re-render the generated tag chips.
   */
  updateTagsList(tagsList) {
    this.tags = tagsList;
    const chipsContainer = document.getElementById('yt-chips-container');
    const badge = document.getElementById('yt-sidebar-badge-count');
    const placeholderTip = document.querySelector('.yt-tags-placeholder-tip');
    
    if (!chipsContainer) return;

    // Clear current chips
    chipsContainer.innerHTML = '';

    if (this.tags.length === 0) {
      placeholderTip.style.display = 'block';
      badge.style.display = 'none';
      this.updateCounters(0, 0);
      return;
    }

    placeholderTip.style.display = 'none';

    // Update badges
    if (!this.isOpen) {
      badge.textContent = this.tags.length;
      badge.style.display = 'block';
    }

    // Format display tags based on Hashtag Mode
    const toggleHashtag = document.getElementById('yt-toggle-hashtag');
    const hashtagMode = toggleHashtag ? toggleHashtag.checked : false;
    
    let displayTags = this.tags;
    if (hashtagMode && typeof toHashtags === 'function') {
      displayTags = toHashtags(this.tags);
    }

    // Render chips
    let totalCharSize = 0;
    displayTags.forEach((tag, idx) => {
      totalCharSize += tag.length;
      if (idx > 0) totalCharSize += 1; // plus comma cost
      
      const chip = document.createElement('div');
      chip.className = 'yt-tag-chip';
      chip.innerHTML = `
        <span class="yt-chip-label" title="Copy individual tag">${tag}</span>
        <button class="yt-chip-delete-btn" data-index="${idx}" title="Remove tag">×</button>
      `;

      // Copy individual tag on label click
      chip.querySelector('.yt-chip-label').addEventListener('click', () => {
        navigator.clipboard.writeText(tag).then(() => {
          this.log(`Copied tag: "${tag}"`, "success");
        });
      });

      // Delete action listener
      chip.querySelector('.yt-chip-delete-btn').addEventListener('click', (e) => {
        const removeIdx = parseInt(e.target.getAttribute('data-index'), 10);
        this.removeTag(removeIdx);
      });

      chipsContainer.appendChild(chip);
    });

    this.updateCounters(displayTags.length, totalCharSize);
    document.getElementById('yt-last-update-time').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  /**
   * Update character and tag counters.
   */
  updateCounters(count, chars) {
    document.getElementById('yt-tag-counter').textContent = count;
    
    const charCounter = document.getElementById('yt-char-counter');
    charCounter.textContent = chars;

    if (chars > 480) {
      charCounter.style.color = '#ff4d4d'; // limit alert warning
    } else {
      charCounter.style.color = '';
    }
  }

  /**
   * Manual entry of custom tag.
   */
  addManualTag() {
    const input = document.getElementById('yt-manual-tag-input');
    const val = input.value.trim().toLowerCase();
    
    if (!val) return;
    
    if (this.tags.includes(val)) {
      this.log(`Tag "${val}" already exists in the list.`, "warning");
      input.value = '';
      return;
    }

    // Comma-separated entries parsed separately
    const splitTags = val.split(',').map(t => t.trim()).filter(t => t.length > 0);
    let tagsAddedCount = 0;

    chrome.storage.sync.get({ maxTagsCount: 35 }, (settings) => {
      const maxCount = settings.maxTagsCount;
      const updatedTags = [...this.tags];

      for (const singleTag of splitTags) {
        if (updatedTags.length >= maxCount) {
          this.log(`Tag limit of ${maxCount} reached. Cannot add "${singleTag}".`, "warning");
          break;
        }
        
        // Size validation
        const currentLength = updatedTags.join(',').length + (updatedTags.length > 0 ? 1 : 0);
        const addedCost = singleTag.length + 1;

        if (currentLength + addedCost > 495) {
          this.log(`YouTube 500-char limits exceeded. Skipping tag "${singleTag}".`, "warning");
          break;
        }

        if (!updatedTags.includes(singleTag)) {
          updatedTags.push(singleTag);
          tagsAddedCount++;
        }
      }

      if (tagsAddedCount > 0) {
        input.value = '';
        this.updateTagsList(updatedTags);
        this.log(`Manually added ${tagsAddedCount} custom tag(s).`, "success");
        
        // Auto-insert if active
        if (document.getElementById('yt-toggle-insert').checked) {
          this.onInsertTags(this.tags);
        }
      }
    });
  }

  /**
   * Remove a tag from the list.
   */
  removeTag(index) {
    const removedText = this.tags[index];
    const updatedTags = this.tags.filter((_, idx) => idx !== index);
    this.updateTagsList(updatedTags);
    this.log(`Removed tag: "${removedText}"`, "warning");
    
    // Auto-insert if active
    if (document.getElementById('yt-toggle-insert').checked) {
      this.onInsertTags(this.tags);
    }
  }

  /**
   * Clear all tags from the list.
   */
  clearTags() {
    this.updateTagsList([]);
    this.log("All tags cleared.", "warning");
  }

  /**
   * Copy whole list of tags.
   */
  copyTagsToClipboard() {
    if (this.tags.length === 0) {
      this.log("No tags available to copy.", "warning");
      return;
    }

    chrome.storage.sync.get({ preferredSeparator: "," }, (settings) => {
      const separator = settings.preferredSeparator || ",";
      
      // Format display tags based on Hashtag Mode
      const toggleHashtag = document.getElementById('yt-toggle-hashtag');
      const hashtagMode = toggleHashtag ? toggleHashtag.checked : false;
      
      let finalTags = this.tags;
      if (hashtagMode && typeof toHashtags === 'function') {
        finalTags = toHashtags(this.tags);
      }

      const tagsStr = finalTags.join(separator);
      
      navigator.clipboard.writeText(tagsStr).then(() => {
        this.log(`Copied ${finalTags.length} tags to clipboard.`, "success");
      }).catch(err => {
        this.log(`Clipboard copy failed: ${err.message}`, "error");
      });
    });
  }
}

// Bind to window to allow contents.js access
window.YouTubeStudioUI = YouTubeStudioUI;
