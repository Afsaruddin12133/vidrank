// YouTube Auto Tag Generator — Page Controller (Rewrite v2)
// Handles: title detection, auto-tag generation, tag insertion,
// description auto-fill, and sidebar coordination.

(function () {
  'use strict';

  /* ─── State ─────────────────────────────────────────────────────── */
  let sidebarUI         = null;
  let pageObserver      = null;
  let titleObserver     = null;          // MutationObserver on title element
  let currentTitle      = '';
  let lastGeneratedTags = [];
  let isInserting       = false;
  let debounceTimer     = null;

  /* ─── Selectors (ordered: most specific → broadest fallback) ─────── */

  // All candidates for the title field. We test each one in order.
  const TITLE_CANDIDATES = [
    '#title-textarea >>> #textbox',
    'ytcp-social-suggestions-textbox[id="title-textarea"] >>> #textbox',
    '[id="title-container"] >>> #textbox',
    '#title >>> #textbox',
  ];

  // Description field candidates
  const DESC_CANDIDATES = [
    '#description-textarea >>> #textbox',
    'ytcp-social-suggestions-textbox[id="description-textarea"] >>> #textbox',
    '[id="description-container"] >>> #textbox',
    '#description >>> #textbox',
  ];

  // Tags plain-text input candidates
  const TAGS_INPUT_CANDIDATES = [
    'ytcp-freeform-chips >>> #text-input',
    '#tags-container >>> #text-input',
    'ytcp-freeform-chips >>> input[type="text"]',
    'ytcp-freeform-chips >>> input',
  ];

  // Existing tag-chip delete buttons (tried in order)
  const CHIP_DELETE_CANDIDATES = [
    'ytcp-freeform-chips >>> ytcp-chip #delete-button',
    'ytcp-freeform-chips >>> ytcp-chip [icon="ytcp:close"]',
    'ytcp-freeform-chips >>> ytcp-chip [aria-label*="emove"]',
    'ytcp-chip #delete-button',
  ];

  // Pages that contain the video editor
  const EDITOR_CANDIDATES = [
    'ytcp-video-details-dialog',
    'ytcp-video-metadata-editor-advanced',
    'ytcp-uploads-dialog',
    '#scrollable-content',
    'main.ytcp-app-layout-main',
  ];

  /* ─── DOM helpers ────────────────────────────────────────────────── */

  /** Recursive search for a single selector path crossing shadow DOMs. */
  function querySelectorPath(path, root = document) {
    let current = root;
    const parts = Array.isArray(path) ? path : path.split('>>>');
    
    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed) continue;
      
      let found = null;
      
      function search(node) {
        if (found) return;
        if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.DOCUMENT_NODE || node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
          try {
            found = node.querySelector(trimmed);
          } catch (e) {}
          if (found) return;
          
          if (node.shadowRoot) {
            search(node.shadowRoot);
          }
        }
        
        let child = node.firstChild;
        while (child) {
          search(child);
          child = child.nextSibling;
        }
      }
      
      search(current);
      if (!found) return null;
      current = found;
    }
    
    return current;
  }

  /** Recursive search for all matching elements crossing shadow DOMs. */
  function querySelectorAllPath(path, root = document) {
    const parts = Array.isArray(path) ? path : path.split('>>>').map(p => p.trim());
    if (parts.length === 0) return [];
    
    let currentNodes = [root];
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const nextNodes = [];
      
      for (const node of currentNodes) {
        function collect(n) {
          if (!n) return;
          
          if (n.nodeType === Node.ELEMENT_NODE || n.nodeType === Node.DOCUMENT_NODE || n.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
            try {
              n.querySelectorAll(part).forEach(el => {
                if (!nextNodes.includes(el)) nextNodes.push(el);
              });
            } catch (e) {}
            
            if (n.shadowRoot) {
              collect(n.shadowRoot);
            }
          }
          
          let child = n.firstChild;
          while (child) {
            collect(child);
            child = child.nextSibling;
          }
        }
        
        collect(node);
      }
      
      if (nextNodes.length === 0) return [];
      currentNodes = nextNodes;
    }
    
    return currentNodes;
  }

  function querySelectorFirstPath(candidates, root = document) {
    for (const cand of candidates) {
      const el = querySelectorPath(cand, root);
      if (el) return el;
    }
    return null;
  }

  /** True when any editor page is present in the DOM. */
  function isEditorOpen() {
    return EDITOR_CANDIDATES.some(sel => {
      try { return !!querySelectorPath(sel); } catch (_) { return false; }
    });
  }

  /** Traverse up parent nodes and cross shadow roots via hosts. */
  function closestDeep(el, selector) {
    let current = el;
    while (current) {
      if (current.nodeType === Node.ELEMENT_NODE && current.matches(selector)) {
        return current;
      }
      current = current.parentNode || current.host;
    }
    return null;
  }

  /** Checks that a contenteditable element is the TITLE box. */
  function looksLikeTitleField(el) {
    if (!el) return false;
    if (el.getAttribute('contenteditable') !== 'true') return false;
    // Reject description fields
    if (closestDeep(el, '[id*="description"]') ||
        closestDeep(el, '[class*="description"]')) return false;
    // Accept known title wrappers
    if (closestDeep(el, '[id*="title"]') ||
        closestDeep(el, '[class*="title"]')) return true;
    return false;
  }

  /** Read innerText cleanly from a contenteditable div. */
  function readText(el) {
    return (el.innerText || el.textContent || '').trim();
  }

  /* ─── Focus & Selection Preservation ────────────────────────────── */

  function saveSelection(containerEl) {
    if (!containerEl) return null;
    const sel = window.getSelection();
    if (sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      if (containerEl.contains(range.startContainer)) {
        return {
          range: range.cloneRange(),
          activeElement: document.activeElement
        };
      }
    }
    return null;
  }

  function restoreSelection(saved) {
    if (!saved) return;
    if (saved.activeElement && typeof saved.activeElement.focus === 'function') {
      saved.activeElement.focus();
    }
    try {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(saved.range);
    } catch (e) {
      console.warn('[YouTube Tag Generator] Failed to restore selection:', e);
    }
  }

  function preserveTitleFocus(actionFn) {
    const titleEl = findTitleField();
    const saved = saveSelection(titleEl);
    try {
      actionFn();
    } finally {
      if (saved) {
        restoreSelection(saved);
      }
    }
  }

  /* ─── UI Helpers (Blinking Popup) ────────────────────────────────── */

  function showBlinkingPopup(remainingTime, currentUsageCount, uid) {
    let popup = document.getElementById('vr-blinking-popup');
    if (!popup) {
      popup = document.createElement('div');
      popup.id = 'vr-blinking-popup';
      // Style it for top-right corner, fixed, premium, lowered so it doesn't overlap headers
      popup.style.position = 'fixed';
      popup.style.top = '95px';
      popup.style.right = '24px';
      popup.style.zIndex = '9999999';
      popup.style.background = 'linear-gradient(135deg, rgba(20,20,20,0.95) 0%, rgba(0,0,0,0.98) 100%)';
      popup.style.backdropFilter = 'blur(10px)';
      popup.style.border = '1px solid rgba(255, 215, 0, 0.3)';
      popup.style.borderRadius = '16px';
      popup.style.padding = '20px 24px';
      popup.style.color = '#FFFFFF';
      popup.style.fontFamily = '"Outfit", -apple-system, sans-serif';
      popup.style.display = 'flex';
      popup.style.flexDirection = 'column';
      popup.style.alignItems = 'flex-start';
      popup.style.cursor = 'pointer';
      
      // Blinking animation and layout
      const style = document.createElement('style');
      style.textContent = `
        @keyframes vrBlink {
          0% { box-shadow: 0 4px 20px rgba(255, 215, 0, 0.15); border-color: rgba(255, 215, 0, 0.3); }
          50% { box-shadow: 0 4px 30px rgba(255, 215, 0, 0.6); border-color: rgba(255, 215, 0, 0.8); }
          100% { box-shadow: 0 4px 20px rgba(255, 215, 0, 0.15); border-color: rgba(255, 215, 0, 0.3); }
        }
        @keyframes vrPulseRed {
          0% { opacity: 0.4; }
          50% { opacity: 1; }
          100% { opacity: 0.4; }
        }
        #vr-blinking-popup {
          animation: vrBlink 2s infinite;
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        #vr-blinking-popup:hover {
          transform: translateY(-4px) scale(1.02);
          box-shadow: 0 8px 40px rgba(255, 215, 0, 0.8) !important;
          border-color: rgba(255, 215, 0, 1) !important;
          animation: none;
        }
      `;
      document.head.appendChild(style);
      
      popup.addEventListener('click', () => {
        window.open(`https://www.vidrank.tech/?userId=${uid}`, '_blank');
      });

      document.body.appendChild(popup);
    }
    
    const hitsRemaining = Math.max(0, 10 - currentUsageCount);
    
    popup.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
        <div style="background: rgba(255, 215, 0, 0.15); padding: 8px; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="#FFD700">
            <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
          </svg>
        </div>
        <div style="font-size: 18px; font-weight: 700; color: #FFD700; text-transform: uppercase; letter-spacing: 0.5px;">Upgrade to Pro</div>
      </div>
      <div style="font-size: 14px; color: #E0E0E0; line-height: 1.5;">
        You have <strong style="color:#FFD700; font-size: 16px;">${hitsRemaining}</strong> free optimizations left.
      </div>
      <div style="font-size: 13px; color: #AAAAAA; margin-top: 10px; display: flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.05); padding: 6px 12px; border-radius: 20px;">
        <span style="display: inline-block; width: 8px; height: 8px; background: #FF4444; border-radius: 50%; animation: vrPulseRed 1.5s infinite;"></span>
        Generating in <span id="vr-popup-timer" style="color: #ffffff; font-weight: bold; font-size: 14px;">${remainingTime}</span>s...
      </div>
    `;
    
    popup.style.display = 'flex';
  }

  function updateBlinkingPopupTimer(remainingTime) {
    const timerSpan = document.getElementById('vr-popup-timer');
    if (timerSpan) {
      timerSpan.textContent = remainingTime;
    }
  }

  function hideBlinkingPopup() {
    const popup = document.getElementById('vr-blinking-popup');
    if (popup) {
      popup.style.display = 'none';
    }
  }

  /* ─── Core: find fields ──────────────────────────────────────────── */

  function findTitleField() {
    // 1. Try precise selectors
    const bySelector = querySelectorFirstPath(TITLE_CANDIDATES);
    if (bySelector) return bySelector;

    // 2. Fallback: scan all contenteditable elements
    const all = querySelectorAllPath('div[contenteditable="true"]');
    for (const el of all) {
      if (looksLikeTitleField(el)) return el;
    }
    return null;
  }

  function findDescriptionField() {
    return querySelectorFirstPath(DESC_CANDIDATES);
  }

  function findTagsInput() {
    return querySelectorFirstPath(TAGS_INPUT_CANDIDATES);
  }

  /* ─── Initialisation ─────────────────────────────────────────────── */

  function initExtension() {
    if (!chrome.runtime?.id) return;
    if (sidebarUI) return;           // already initialised
    
    // Request a fresh sync from the background script on load to catch plan upgrades
    chrome.runtime.sendMessage({ action: "syncUsage" });

    chrome.storage.local.get({ isLoggedIn: false }, (data) => {
      if (chrome.runtime.lastError) return;
      sidebarUI = new window.YouTubeStudioUI({
        isLoggedIn: data.isLoggedIn,
        onToggleAutoGenerate : active => { if (active) scanAndGenerate(); },
        onToggleAutoInsert   : active => { if (active && lastGeneratedTags.length) triggerTagInsertion(lastGeneratedTags); },
        onToggleHashtag      : active => { sidebarUI.updateTagsList(lastGeneratedTags); },
        onRegenerate         : () => scanAndGenerate(true),
        onInsertTags         : tags  => triggerTagInsertion(tags),
        onGenerateDescription: callback => generateAndInsertAIDescription(callback)
      });

      setupPageObserver();
      // Poll every 800 ms for editor presence and new title elements
      setInterval(scanLoop, 800);
    });

    // Listen for Auth or Plan changes
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'local') {
        if (changes.isLoggedIn !== undefined) {
          // Reload YouTube Studio silently to apply new Auth state
          window.location.reload();
        }
        
        // Dynamically update the confirm button if plan or usage limit changes (e.g. from Admin Panel)
        if (changes.plan !== undefined || changes.usageCount !== undefined) {
          chrome.storage.local.get(["usageCount", "plan", "isLoggedIn"], (data) => {
            const btn = document.getElementById('yt-btn-confirm-title');
            if (btn && data.isLoggedIn) {
              if ((data.plan || "free") === "free" && (data.usageCount || 0) >= 10) {
                btn.innerHTML = '⭐ Upgrade to Unlimited';
                btn.style.background = 'linear-gradient(135deg, #FFD700 0%, #FDB931 100%)';
                btn.style.color = '#000';
              } else {
                btn.innerHTML = '✨ Confirm Title & Generate';
                btn.style.background = 'linear-gradient(135deg, #FF0055 0%, #FF0000 100%)';
                btn.style.color = '#ffffff';
                btn.disabled = false;
              }
            }
          });
        }
      }
    });
  }

  /* ─── Scan loop (replaces checkActiveView) ───────────────────────── */

  let _scanBusy = false;
  function scanLoop() {
    if (!chrome.runtime?.id) return;
    if (_scanBusy) return;
    _scanBusy = true;
    try {
      if (!isEditorOpen()) { _scanBusy = false; return; }
      attachTitleObserver();
      injectConfirmTitleButton();
    } finally {
      _scanBusy = false;
    }
  }

  /**
   * Find the title field and attach a MutationObserver on its characterData
   * so we capture every keystroke reliably — even when input events are
   * swallowed by Polymer.
   */
  function attachTitleObserver() {
    const titleEl = findTitleField();
    if (!titleEl) return;

    // Already observed this exact element
    if (titleEl._ytTagObserved) return;
    titleEl._ytTagObserved = true;

    // Fire once immediately for the existing title
    const initialText = readText(titleEl);
    if (initialText) onTitleChanged(initialText);

    // Observe character-level DOM mutations (most reliable for contenteditable)
    titleObserver = new MutationObserver(() => {
      scheduleTitleUpdate(titleEl);
    });
    titleObserver.observe(titleEl, {
      characterData : true,
      childList     : true,
      subtree       : true,
    });

    // Also listen to standard events as secondary triggers
    ['input', 'keyup', 'paste', 'cut'].forEach(evt =>
      titleEl.addEventListener(evt, () => scheduleTitleUpdate(titleEl), { passive: true })
    );

    sidebarUI.log('Title field detected — watching for changes.', 'success');
  }

  function scheduleTitleUpdate(titleEl) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const text = readText(titleEl);
      if (text && text !== currentTitle) {
        onTitleChanged(text);
      }
    }, 900);  // wait 0.9 s after user stops typing
  }

  function injectConfirmTitleButton() {
    const titleEl = findTitleField();
    if (!titleEl) return;

    const container = closestDeep(titleEl, 'ytcp-social-suggestions-textbox') || 
                      closestDeep(titleEl, '#title-container') || 
                      titleEl.parentElement;
    if (!container) return;

    if (document.getElementById('yt-btn-confirm-title-wrapper')) return;

    const btnWrapper = document.createElement('div');
    btnWrapper.id = 'yt-btn-confirm-title-wrapper';
    btnWrapper.style.display = 'flex';
    btnWrapper.style.justifyContent = 'flex-end';
    btnWrapper.style.width = '100%';
    btnWrapper.style.marginTop = '12px';
    btnWrapper.style.marginBottom = '8px';

    const btn = document.createElement('button');
    btn.id = 'yt-btn-confirm-title';
    btn.innerHTML = '✨ Confirm Title & Generate';
    btn.title = 'Click when title is complete to generate and insert both description & tags.';

    chrome.storage.local.get(["usageCount", "plan", "isLoggedIn"], (data) => {
      if (!data.isLoggedIn) {
        btn.innerHTML = '🔒 Sign in to VidRank';
        btn.style.background = '#4285F4';
        btn.style.color = '#ffffff';
      } else if ((data.plan || "free") === "free" && (data.usageCount || 0) >= 10) {
        btn.innerHTML = '⭐ Upgrade to Unlimited';
        btn.style.background = 'linear-gradient(135deg, #FFD700 0%, #FDB931 100%)';
        btn.style.color = '#000';
      }
    });

    // Premium inline styles (dynamic flow instead of absolute positioning)
    btn.style.background = 'linear-gradient(135deg, #FF0055 0%, #FF0000 100%)';
    btn.style.color = '#ffffff';
    btn.style.border = '1px solid rgba(255, 255, 255, 0.1)';
    btn.style.borderRadius = '24px';
    btn.style.fontSize = '13px';
    btn.style.fontWeight = '700';
    btn.style.letterSpacing = '0.3px';
    btn.style.padding = '10px 20px';
    btn.style.cursor = 'pointer';
    btn.style.boxShadow = '0 6px 16px rgba(255, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.2)';
    btn.style.display = 'inline-flex';
    btn.style.alignItems = 'center';
    btn.style.gap = '8px';
    btn.style.fontFamily = '"Outfit", "Roboto", "Arial", sans-serif';
    btn.style.transition = 'all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1)';
    btn.style.zIndex = '1000';
    btn.style.textTransform = 'uppercase';

    // Hover & Active micro-animations
    btn.addEventListener('mouseenter', () => {
      if (!btn.disabled && !btn.innerHTML.includes('Unlimited')) {
        btn.style.background = 'linear-gradient(135deg, #FF1A66 0%, #FF1A1A 100%)';
        btn.style.boxShadow = '0 8px 24px rgba(255, 0, 0, 0.45), inset 0 1px 1px rgba(255, 255, 255, 0.3)';
        btn.style.transform = 'translateY(-2px)';
      } else if (!btn.disabled && btn.innerHTML.includes('Unlimited')) {
        // Upgrade button hover state
        btn.style.transform = 'translateY(-2px)';
        btn.style.boxShadow = '0 8px 24px rgba(255, 215, 0, 0.5)';
      }
    });
    btn.addEventListener('mouseleave', () => {
      if (!btn.disabled && !btn.innerHTML.includes('Unlimited')) {
        btn.style.background = 'linear-gradient(135deg, #FF0055 0%, #FF0000 100%)';
        btn.style.boxShadow = '0 6px 16px rgba(255, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.2)';
        btn.style.transform = 'translateY(0)';
      } else if (!btn.disabled && btn.innerHTML.includes('Unlimited')) {
        btn.style.transform = 'translateY(0)';
        btn.style.boxShadow = '0 6px 16px rgba(255, 215, 0, 0.35)';
      }
    });
    btn.addEventListener('mousedown', () => {
      if (!btn.disabled) {
        btn.style.transform = 'translateY(1px)';
        btn.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.5)';
      }
    });
    btn.addEventListener('mouseup', () => {
      if (!btn.disabled && !btn.innerHTML.includes('Unlimited')) {
        btn.style.transform = 'translateY(-2px)';
        btn.style.boxShadow = '0 8px 24px rgba(255, 0, 0, 0.45), inset 0 1px 1px rgba(255, 255, 255, 0.3)';
      }
    });

    function setBtnDisabled(disabled) {
      btn.disabled = disabled;
      if (disabled) {
        btn.style.background = '#333333';
        btn.style.color = '#888888';
        btn.style.cursor = 'not-allowed';
        btn.style.boxShadow = 'none';
        btn.style.border = '1px solid #444444';
        btn.style.transform = 'none';
      } else {
        btn.style.background = 'linear-gradient(135deg, #FF0055 0%, #FF0000 100%)';
        btn.style.color = '#ffffff';
        btn.style.cursor = 'pointer';
        btn.style.border = '1px solid rgba(255, 255, 255, 0.1)';
        btn.style.boxShadow = '0 6px 16px rgba(255, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.2)';
      }
    }

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      if (!chrome.runtime?.id) {
        alert("Extension context invalidated. Please refresh the page.");
        return;
      }
      
      chrome.storage.local.get(["usageCount", "plan", "uid", "isLoggedIn"], async (data) => {
        if (chrome.runtime.lastError) return;

        if (!data.isLoggedIn) {
          btn.innerHTML = 'Wait...';
          chrome.runtime.sendMessage({ action: "login" }, (response) => {
            if (response && response.success) {
              window.location.reload();
            } else {
              btn.innerHTML = '🔒 Sign in to VidRank';
              alert("Login failed. Please try again.");
            }
          });
          return;
        }

        const count = data.usageCount || 0;
        const plan = data.plan || "free";
        const uid = data.uid || "";
        
        if (plan === "free" && count >= 10) {
          window.open(`https://www.vidrank.tech/?userId=${uid}`, '_blank');
          return;
        }

        const titleText = readText(titleEl);
        if (!titleText) {
          sidebarUI.log("Title is empty! Please write a title first.", "warning");
          return;
        }

        const executeGeneration = async () => {
          btn.innerHTML = '✨ Generating Metadata...';
          sidebarUI.log(`Title confirmed. Generating description and tags for: "${titleText}"`, "info");

          try {
            // Execute sequentially to prevent concurrent API requests hitting rate limits
            const descResponse = await new Promise(resolve => {
              chrome.runtime.sendMessage({
                action: 'generateDescription',
                title: titleText
              }, resolve);
            });

            if (descResponse && descResponse.success) {
              insertDescriptionToStudio(descResponse.description);
            } else {
              const errMsg = descResponse?.error || 'Unknown error';
              sidebarUI.log(`AI Description failed: ${errMsg}`, "error");
              alert(`Error generating description: ${errMsg}`);
            }

            // Wait 1.5 seconds to avoid Groq API rate limits (HTTP 429) between sequential calls
            await new Promise(r => setTimeout(r, 1500));

            const tagsResponse = await new Promise(resolve => {
              const descEl = findDescriptionField();
              const descText = descEl ? readText(descEl) : '';
              
              chrome.runtime.sendMessage({
                action: 'generateTags',
                title: titleText,
                description: descText
              }, resolve);
            });

            if (tagsResponse && tagsResponse.success) {
              chrome.storage.sync.get({ maxTagsCount: 35 }, (settings) => {
                let tags = tagsResponse.tags || [];
                tags = tags.slice(0, settings.maxTagsCount);
                lastGeneratedTags = tags;
                sidebarUI.updateTagsList(tags);
                triggerTagInsertion(tags);
              });
            } else {
              const errMsg = tagsResponse?.error || 'Unknown error';
              sidebarUI.log(`AI Tags failed: ${errMsg}`, "error");
              alert(`Error generating tags: ${errMsg}`);
            }
          } catch (err) {
            sidebarUI.log(`Metadata generation error: ${err.message}`, "error");
          } finally {
            // Re-fetch the actual usage count to ensure we only show "Upgrade" if the backend truly updated
            chrome.storage.local.get(["usageCount", "plan"], (latestData) => {
              const latestCount = latestData.usageCount || 0;
              const currentPlan = latestData.plan || "free";
              
              if (latestCount >= 10 && currentPlan === "free") {
                btn.innerHTML = '⭐ Upgrade to Unlimited';
                btn.style.background = 'linear-gradient(135deg, #FFD700 0%, #FDB931 100%)';
                btn.style.color = '#000';
                setBtnDisabled(false);
              } else {
                setBtnDisabled(false);
                btn.innerHTML = '✨ Confirm Title & Generate';
              }
            });
          }
        };

        const DELAYS = [0, 0, 0, 0, 10, 20, 30, 40, 50, 60];
        const waitSeconds = DELAYS[count] || 0;

        if (plan === "free" && waitSeconds > 0) {
          let remaining = waitSeconds;
          
          setBtnDisabled(true);
          btn.innerHTML = `Wait ${remaining}s...`;
          
          showBlinkingPopup(remaining, count, uid);
          
          const timerId = setInterval(() => {
            remaining--;
            if (remaining > 0) {
              btn.innerHTML = `Wait ${remaining}s...`;
              updateBlinkingPopupTimer(remaining);
            } else {
              clearInterval(timerId);
              hideBlinkingPopup();
              executeGeneration();
            }
          }, 1000);
          return;
        }

        setBtnDisabled(true);
        executeGeneration();
      });
    });

    // Insert wrapper below the title container (so it flows dynamically with the UI)
    btnWrapper.appendChild(btn);
    container.insertAdjacentElement('afterend', btnWrapper);
    
    sidebarUI.log("Injected confirm button below title editor.", "success");
  }



  /* ─── Title change handler ───────────────────────────────────────── */

  function onTitleChanged(title) {
    if (!chrome.runtime?.id) return;
    currentTitle = title;
    sidebarUI.updateDetectedTitle(title);
    sidebarUI.log(`Title detected: "${title.slice(0, 50)}${title.length > 50 ? '…' : ''}"`, 'info');

    try {
      chrome.storage.local.get(["isLoggedIn"], (authData) => {
        if (!authData.isLoggedIn) {
          sidebarUI.log("Auto-generation skipped: Please log in first.", "warning");
          return;
        }
        chrome.storage.sync.get(
        { autoGenerate: true, autoInsert: true, maxTagsCount: 35 },
        settings => {
          if (settings.autoGenerate) {
            sidebarUI.log("Generating tags from title & description context...", "info");
          
          const descEl = findDescriptionField();
          const descText = descEl ? readText(descEl) : '';

          chrome.runtime.sendMessage({
            action: 'generateTags',
            title: title,
            description: descText
          }, (response) => {
            if (chrome.runtime.lastError) {
              sidebarUI.log(`Connection error: ${chrome.runtime.lastError.message}`, 'error');
              return;
            }

            if (response && response.success) {
              let tags = response.tags || [];
              tags = tags.slice(0, settings.maxTagsCount);
              lastGeneratedTags = tags;

              sidebarUI.updateTagsList(tags);
              sidebarUI.log(`Generated ${tags.length} tags.`, 'success');

              if (settings.autoInsert) {
                triggerTagInsertion(tags);
              }
            } else {
              sidebarUI.log(`Generation failed: ${response?.error || 'Unknown error'}`, 'error');
            }
          });
        }

        }
      );
    });
  } catch (err) {
    console.warn("Chrome API error in onTitleChanged:", err);
  }
}

  /* Manual regenerate (called by sidebar Regenerate button) */
  function scanAndGenerate(force = false) {
    const titleEl = findTitleField();
    if (!titleEl) {
      sidebarUI.log('Title field not found. Open a video details page first.', 'error');
      return;
    }
    const title = readText(titleEl);
    if (!title) {
      sidebarUI.log('Title is empty — nothing to generate.', 'warning');
      return;
    }

    if (force) {
      sidebarUI.log("Forcing tag generation from title & description context...", "info");
      
      const descEl = findDescriptionField();
      const descText = descEl ? readText(descEl) : '';

      if (!chrome.runtime?.id) return;
      chrome.storage.sync.get({ maxTagsCount: 35, autoInsert: true }, settings => {
        if (chrome.runtime.lastError) return;
        chrome.runtime.sendMessage({
          action: 'generateTags',
          title: title,
          description: descText
        }, (response) => {
          if (chrome.runtime.lastError) {
            sidebarUI.log(`Connection error: ${chrome.runtime.lastError.message}`, 'error');
            return;
          }

          if (response && response.success) {
            let tags = response.tags || [];
            tags = tags.slice(0, settings.maxTagsCount);
            lastGeneratedTags = tags;

            sidebarUI.updateTagsList(tags);
            sidebarUI.log(`Generated ${tags.length} tags.`, 'success');

            if (settings.autoInsert) {
              triggerTagInsertion(tags);
            }
          } else {
            sidebarUI.log(`Generation failed: ${response?.error || 'Unknown error'}`, 'error');
          }
        });
      });
    } else {
      onTitleChanged(title);
    }
  }

  /* ─── Tag insertion ──────────────────────────────────────────────── */

  async function triggerTagInsertion(tags) {
    if (isInserting) return;
    if (!tags || !tags.length) { sidebarUI.log('No tags to insert.', 'warning'); return; }

    let inputEl = findTagsInput();
    if (!inputEl) {
      sidebarUI.log("Tags field not visible. Attempting to expand 'SHOW MORE' section...", 'info');
      const expanded = expandShowMore();
      if (expanded) {
        await sleep(800); // Wait for transition and elements to render
        inputEl = findTagsInput();
      }
    }

    if (!inputEl) {
      sidebarUI.log("Tags field not visible. Please click 'SHOW MORE' in the details panel.", 'warning');
      return;
    }

    isInserting = true;
    try {
      // Step 1: Remove all existing chips
      await clearExistingChips();
      await sleep(500);

      // Get current Hashtag Mode setting
      const settings = await new Promise(resolve => {
        chrome.storage.sync.get({ hashtagMode: false }, resolve);
      });

      let finalTags = tags;
      if (settings.hashtagMode && window.TagGenerator?.toHashtags) {
        finalTags = window.TagGenerator.toHashtags(tags);
      }

      // Step 2: Insert new tags one by one
      let charCount = 0;
      let inserted  = 0;

      for (const tag of finalTags) {
        const cost = tag.length + (charCount > 0 ? 1 : 0);  // +1 for comma
        if (charCount + cost > 490) break;                   // YouTube 500-char limit

        const input = findTagsInput();
        if (!input) break;

        // Type the tag value inside focus preservation wrapper
        preserveTitleFocus(() => {
          input.value = tag;
          input.dispatchEvent(new Event('input',  { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
        });
        await sleep(100);

        // Press Enter to confirm chip inside focus preservation wrapper
        preserveTitleFocus(() => {
          input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true, cancelable: true }));
          input.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Enter', keyCode: 13, bubbles: true, cancelable: true }));
        });
        await sleep(200);

        charCount += cost;
        inserted++;
      }

      sidebarUI.log(`Inserted ${inserted} tags into YouTube Studio.`, 'success');
    } catch (err) {
      sidebarUI.log(`Tag insertion error: ${err.message}`, 'error');
    } finally {
      isInserting = false;
    }
  }

  async function clearExistingChips() {
    const container = querySelectorPath('ytcp-freeform-chips');
    if (!container) return;

    // Candidates for the delete button inside a single ytcp-chip shadow root
    const candidates = [
      '#delete-button',
      '[icon="ytcp:close"]',
      '[aria-label*="emove"]',
      '[aria-label*="Remove"]',
      '#delete-icon',
      '#close-button',
      'button',
      'ytcp-icon-button'
    ];

    let retries = 3;
    while (retries > 0) {
      const chips = querySelectorAllPath('ytcp-chip', container);
      if (!chips.length) break;

      sidebarUI.log(`Removing ${chips.length} existing tag(s) (Retries left: ${retries})…`, 'info');

      // Iterate in reverse to prevent offset shifting
      for (let i = chips.length - 1; i >= 0; i--) {
        const chip = chips[i];
        let btn = null;
        for (const sel of candidates) {
          btn = querySelectorPath(sel, chip);
          if (btn) break;
        }

        if (btn) {
          preserveTitleFocus(() => {
            try { btn.click(); } catch (_) {}
          });
        } else {
          // Fallback to the last child in the shadow DOM or light DOM (usually the delete icon/button)
          const lastChild = chip.shadowRoot ? chip.shadowRoot.lastElementChild : chip.lastElementChild;
          if (lastChild) {
            preserveTitleFocus(() => {
              try { lastChild.click(); } catch (_) {}
            });
          }
        }
        await sleep(100); // Wait for deletion and DOM update
      }

      retries--;
      if (querySelectorAllPath('ytcp-chip', container).length > 0) {
        await sleep(250); // Additional sleep if elements are slow to disappear
      }
    }
  }

  /* ─── Panel Auto Expansion ───────────────────────────────────────── */

  function expandShowMore() {
    const buttons = querySelectorAllPath('ytcp-button#toggle-button, #toggle-button');
    for (const btn of buttons) {
      const txt = (btn.innerText || btn.textContent || '').toLowerCase();
      if (txt.includes('show more') || (txt.includes('more') && !txt.includes('less'))) {
        btn.click();
        sidebarUI.log("Automatically expanded 'SHOW MORE' section.", "success");
        return true;
      }
    }
    return false;
  }

  /* ─── Description auto-fill ──────────────────────────────────────── */

  function buildDescription(title) {
    const stopWords = new Set([
      'a','an','the','and','but','or','for','so','to','of','in','on','at',
      'by','up','as','is','it','its','be','do','how','what','when','where',
      'who','why','with','from','into','that','this','are','was','were',
      'has','have','had','not','also','can','will','your','our','their'
    ]);

    const words = title
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter(w => w.length > 2 && !stopWords.has(w));

    const keywords = [...new Set(words)];

    // Year and location context
    const yearMatch = title.match(/\b(202[4-9]|203[0-9])\b/);
    const year      = yearMatch ? yearMatch[0] : String(new Date().getFullYear());

    const LOCATIONS = [
      'bangladesh','india','pakistan','usa','uk','canada','australia',
      'nigeria','philippines','germany','france','dhaka','delhi','london','new york'
    ];
    const lc       = title.toLowerCase();
    const location = LOCATIONS.find(l => lc.includes(l)) || null;
    const locLine  = location
      ? `\nThis guide is created especially for viewers in ${location.charAt(0).toUpperCase() + location.slice(1)} and nearby regions.`
      : '';

    const keyPhrase = keywords.slice(0, 5).join(' ');
    const kwList    = keywords.slice(0, 12).join(', ');
    const bullets   = keywords.slice(0, 4).map(k => `• ${k}`).join('\n');

    return [
      title,
      '',
      `In this video, we cover everything you need to know about ${keyPhrase}. ` +
      `Perfect for beginners and advanced learners alike — updated for ${year}.${locLine}`,
      '',
      `📌 What you will learn:\n${bullets}`,
      '',
      `🔑 Keywords: ${kwList}`,
      '',
      '━━━━━━━━━━━━━━━━━━━━━━━━',
      '👍 Found this helpful? Give it a Like!',
      '🔔 Subscribe for weekly videos.',
      '💬 Drop your questions in the comments.',
      '━━━━━━━━━━━━━━━━━━━━━━━━',
    ].join('\n');
  }

  function syncDescription(title) {
    const descEl = findDescriptionField();
    if (!descEl) {
      sidebarUI.log('Description field not found. It may not be loaded yet.', 'warning');
      return;
    }

    const newText = buildDescription(title);

    try {
      descEl.focus();

      // Select all existing content then replace with new text securely
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(descEl);
      selection.removeAllRanges();
      selection.addRange(range);
      const inserted = document.execCommand('insertText', false, newText);

      // Fallback for browsers that block execCommand
      if (!inserted || descEl.innerText.replace(/\n$/, '').trim() !== newText.trim()) {
        descEl.innerText = newText;
      }

      ['beforeinput', 'input', 'change'].forEach(ev =>
        descEl.dispatchEvent(new Event(ev, { bubbles: true }))
      );

      sidebarUI.log('Description auto-filled from title.', 'success');
    } catch (err) {
      sidebarUI.log(`Description sync error: ${err.message}`, 'error');
    }
  }

  /* ─── AI Description Generator ───────────────────────────────────── */

  function generateAndInsertAIDescription(callback) {
    const titleEl = findTitleField();
    if (!titleEl) {
      sidebarUI.log("Title field not found. Cannot generate description.", "error");
      if (callback) callback();
      return;
    }

    const titleText = readText(titleEl);
    if (!titleText) {
      sidebarUI.log("Title field is empty. Please enter a video title first.", "warning");
      if (callback) callback();
      return;
    }

    sidebarUI.log("Contacting Groq AI to generate description...", "info");

    chrome.runtime.sendMessage({
      action: 'generateDescription',
      title: titleText
    }, (response) => {
      if (callback) callback();

      if (chrome.runtime.lastError) {
        sidebarUI.log(`Connection error: ${chrome.runtime.lastError.message}`, "error");
        return;
      }

      if (response && response.success) {
        insertDescriptionToStudio(response.description);
      } else {
        sidebarUI.log(`AI Description failed: ${response?.error || 'Unknown error'}`, "error");
      }
    });
  }

  function insertDescriptionToStudio(newText) {
    const descEl = findDescriptionField();
    if (!descEl) {
      sidebarUI.log('Description field not found. Open a video details page first.', 'error');
      return;
    }

    try {
      descEl.focus();

      // Select all existing content and replace with AI text securely
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(descEl);
      selection.removeAllRanges();
      selection.addRange(range);
      const inserted = document.execCommand('insertText', false, newText);

      if (!inserted || descEl.innerText.replace(/\n$/, '').trim() !== newText.trim()) {
        descEl.innerText = newText;
      }

      // Dispatch input and change events
      ['beforeinput', 'input', 'change'].forEach(ev =>
        descEl.dispatchEvent(new Event(ev, { bubbles: true }))
      );

      descEl.blur();
      sidebarUI.log('AI description successfully generated and inserted into YouTube Studio.', 'success');
    } catch (err) {
      sidebarUI.log(`AI Description insertion error: ${err.message}`, 'error');
    }
  }

  /* ─── Toggle callbacks ───────────────────────────────────────────── */

  function handleAutoGenerateToggle(active) {
    if (active) scanAndGenerate();
  }
  function handleAutoInsertToggle(active) {
    if (active && lastGeneratedTags.length) triggerTagInsertion(lastGeneratedTags);
  }

  /* ─── Page-level MutationObserver ────────────────────────────────── */

  function setupPageObserver() {
    if (pageObserver) return;
    pageObserver = new MutationObserver(mutations => {
      // Only re-scan when new nodes were added (SPA navigation / dialog open)
      if (mutations.some(m => m.addedNodes.length > 0)) {
        scanLoop();
      }
    });
    pageObserver.observe(document.body, { childList: true, subtree: true });
  }

  /* ─── Utility ────────────────────────────────────────────────────── */

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }



  /* ─── Bootstrap ──────────────────────────────────────────────────── */

  // Wait a moment for YouTube Studio's initial JS to paint the DOM
  setTimeout(initExtension, 1800);

})();
