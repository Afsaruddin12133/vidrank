// Security Utilities for VidRank Extension
// Input validation, sanitization, and security checks

/**
 * Input Validation
 */

// Validate title input
export function validateTitle(title) {
  if (typeof title !== 'string') {
    throw new Error('Title must be a string');
  }
  
  // Max length: 100 characters (YouTube limit)
  const trimmed = title.trim();
  if (trimmed.length === 0) {
    throw new Error('Title cannot be empty');
  }
  
  if (trimmed.length > 100) {
    throw new Error('Title too long (max 100 characters)');
  }
  
  // Check for malicious patterns
  if (containsMaliciousContent(trimmed)) {
    throw new Error('Title contains invalid characters');
  }
  
  return trimmed;
}

// Validate description input
export function validateDescription(description) {
  if (typeof description !== 'string') {
    throw new Error('Description must be a string');
  }
  
  // Max length: 5000 characters (YouTube limit)
  const trimmed = description.trim();
  if (trimmed.length > 5000) {
    throw new Error('Description too long (max 5000 characters)');
  }
  
  return trimmed;
}

// Check for malicious content
function containsMaliciousContent(text) {
  // Check for script injection attempts
  const scriptPatterns = [
    /<script[^>]*>.*?<\/script>/gi,
    /javascript:/gi,
    /on\w+\s*=/gi, // onclick, onerror, etc.
  ];
  
  return scriptPatterns.some(pattern => pattern.test(text));
}

/**
 * Token Validation
 */

// Validate JWT token format (basic check)
export function isValidTokenFormat(token) {
  if (typeof token !== 'string') return false;
  
  const parts = token.split('.');
  if (parts.length !== 3) return false;
  
  // Check if parts are base64
  try {
    parts.forEach(part => atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Safe Storage Operations
 */

// Safely get from chrome.storage
export function safeStorageGet(keys, defaultValues = {}) {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get(keys, (result) => {
        if (chrome.runtime.lastError) {
          console.error('[Storage] Get error:', chrome.runtime.lastError);
          resolve(defaultValues);
        } else {
          resolve({ ...defaultValues, ...result });
        }
      });
    } catch (error) {
      console.error('[Storage] Get exception:', error);
      resolve(defaultValues);
    }
  });
}

// Safely set to chrome.storage
export function safeStorageSet(items) {
  return new Promise((resolve, reject) => {
    try {
      chrome.storage.local.set(items, () => {
        if (chrome.runtime.lastError) {
          console.error('[Storage] Set error:', chrome.runtime.lastError);
          reject(chrome.runtime.lastError);
        } else {
          resolve();
        }
      });
    } catch (error) {
      console.error('[Storage] Set exception:', error);
      reject(error);
    }
  });
}

export default {
  validateTitle,
  validateDescription,
  isValidTokenFormat,
  safeStorageGet,
  safeStorageSet,
};
