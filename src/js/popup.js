// YouTube Auto Tag Generator - Popup Controller

document.addEventListener('DOMContentLoaded', () => {
  // Settings DOM Elements
  const inputApiKey = document.getElementById('popup-input-apikey');
  const toggleInsert = document.getElementById('popup-toggle-insert');
  const toggleHashtag = document.getElementById('popup-toggle-hashtag');
  const selectSeparator = document.getElementById('popup-select-separator');
  const sliderTags = document.getElementById('popup-slider-tags-count');
  const textTagsVal = document.getElementById('popup-tags-count-val');

  // Auth DOM Elements
  const loginView = document.getElementById('login-view');
  const appView = document.getElementById('app-view');
  const btnLogin = document.getElementById('btn-google-login');
  const btnLogout = document.getElementById('btn-logout');
  const loginError = document.getElementById('login-error');

  // Initialize UI based on Auth State
  function updateUIState(isLoggedIn) {
    if (isLoggedIn) {
      loginView.style.display = 'none';
      appView.style.display = 'block';
      btnLogout.style.display = 'block';
    } else {
      loginView.style.display = 'block';
      appView.style.display = 'none';
      btnLogout.style.display = 'none';
    }
  }

  chrome.storage.local.get({ isLoggedIn: false }, (data) => {
    updateUIState(data.isLoggedIn);
  });

  // Handle Login
  btnLogin.addEventListener('click', () => {
    btnLogin.disabled = true;
    btnLogin.style.opacity = '0.7';
    loginError.style.display = 'none';
    
    chrome.runtime.sendMessage({ action: "login" }, (response) => {
      btnLogin.disabled = false;
      btnLogin.style.opacity = '1';
      
      if (chrome.runtime.lastError || !response || !response.success) {
        loginError.textContent = response?.error || chrome.runtime.lastError?.message || "Login failed.";
        loginError.style.display = 'block';
      } else {
        updateUIState(true);
      }
    });
  });

  // Handle Logout
  btnLogout.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.sendMessage({ action: "logout" }, (response) => {
      if (response && response.success) {
        updateUIState(false);
      }
    });
  });

  // 1. Load current configurations from storage
  chrome.storage.local.get({
    groqApiKey: ''
  }, (localSettings) => {
    if (inputApiKey) {
      inputApiKey.value = localSettings.groqApiKey || '';
    }
  });

  chrome.storage.sync.get({
    autoGenerate: true,
    autoInsert: true,
    hashtagMode: false,
    maxTagsCount: 35,
    preferredSeparator: ","
  }, (settings) => {
    toggleInsert.checked = settings.autoInsert;
    if (toggleHashtag) toggleHashtag.checked = settings.hashtagMode;
    selectSeparator.value = settings.preferredSeparator;
    sliderTags.value = settings.maxTagsCount;
    textTagsVal.textContent = settings.maxTagsCount;
  });

  // 2. Attach change listeners to options
  if (inputApiKey) {
    inputApiKey.addEventListener('change', (e) => {
      chrome.storage.local.set({ groqApiKey: e.target.value.trim() });
    });
  }

  toggleInsert.addEventListener('change', (e) => {
    chrome.storage.sync.set({ autoInsert: e.target.checked });
  });

  if (toggleHashtag) {
    toggleHashtag.addEventListener('change', (e) => {
      chrome.storage.sync.set({ hashtagMode: e.target.checked });
    });
  }

  selectSeparator.addEventListener('change', (e) => {
    chrome.storage.sync.set({ preferredSeparator: e.target.value });
  });

  sliderTags.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    textTagsVal.textContent = val;
    chrome.storage.sync.set({ maxTagsCount: val });
  });




});
