// content.js - Monitors user interactions

console.log("Nova: Content script loaded.");

function logInteraction(type, details) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    type,
    url: window.location.href,
    details
  };
  
  // Send to background script or just log
  console.log("Nova Interaction (Sending to Background):", JSON.stringify(logEntry, null, 2));
  
  // Optionally send to background for storage/transmission
  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
    try {
      chrome.runtime.sendMessage({ action: "log_interaction", data: logEntry }, (response) => {
        if (chrome.runtime.lastError) {
            // Suppress standard connection errors that happen during reload
            console.warn("Nova Warning: Could not reach background script.", chrome.runtime.lastError.message);
        }
      });
    } catch (e) {
      console.log("Nova: Extension context invalidated. Please refresh the page.");
    }
  } else {
      console.warn("Nova: chrome.runtime API unavailable.");
  }
}

// Click Listener
document.addEventListener('click', (event) => {
  const target = event.target;
  const details = {
    tagName: target.tagName,
    id: target.id,
    className: target.className,
    text: target.innerText ? target.innerText.substring(0, 50) : '', // Limit text length
    x: event.clientX,
    y: event.clientY
  };
  logInteraction('click', details);
}, true); // Capture phase to ensure we catch it

// Input Listener (debounced or on change/blur to avoid spam)
document.addEventListener('change', (event) => {
  const target = event.target;
  const details = {
    tagName: target.tagName,
    id: target.id,
    className: target.className,
    value: target.value ? '***' : '', // Privacy: don't log actual value unless necessary
    inputType: target.type
  };
  logInteraction('input_change', details);
}, true);

// Scroll Listener (throttled)
let lastScrollTime = 0;
document.addEventListener('scroll', (event) => {
  const now = Date.now();
  if (now - lastScrollTime > 1000) { // Log at most once per second
    const details = {
      scrollY: window.scrollY,
      scrollX: window.scrollX
    };
    logInteraction('scroll', details);
    lastScrollTime = now;
  }
}, true);

// Selection Change (debounced)
let lastSelectionTime = 0;
document.addEventListener('selectionchange', () => {
    const now = Date.now();
    if (now - lastSelectionTime > 1000) {
        const selection = document.getSelection().toString();
        if (selection.length > 0) {
            logInteraction('text_selection', { length: selection.length, preview: selection.substring(0, 20) });
            lastSelectionTime = now;
        }
    }
});

// Window Focus/Blur
window.addEventListener('focus', () => logInteraction('window_focus', {}));
window.addEventListener('blur', () => logInteraction('window_blur', {}));

logInteraction('page_load', { title: document.title });

// Form Submit
document.addEventListener('submit', (event) => {
    const target = event.target;
    logInteraction('form_submit', {
        action: target.action,
        method: target.method,
        id: target.id
    });
}, true);
