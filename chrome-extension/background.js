// background.js - Service Worker

console.log("Nova: Background script started.");

chrome.runtime.onInstalled.addListener(() => {
  console.log("Nova installed.");
});

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "log_interaction") {
    console.log("Received interaction from tab:", sender.tab ? sender.tab.id : "unknown");
    console.log("Data:", request.data);
    
    // Store in local storage for persistence (optional but good practice)
    chrome.storage.local.get({ interactions: [] }, (result) => {
      const interactions = result.interactions;
      interactions.push(request.data);
      // Limit storage size (keep last 100 entries)
      if (interactions.length > 100) {
        interactions.shift();
      }
      chrome.storage.local.set({ interactions: interactions });
    });

    // Send to local Python server
     console.log('Nova Background: Sending to server...', request.data);
     fetch('http://localhost:8000/api/log', {
         method: 'POST',
         headers: {
             'Content-Type': 'application/json'
         },
         body: JSON.stringify(request.data)
     }).then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
     })
       .then(data => console.log('Nova Server analysis:', data))
       .catch(error => {
          console.error('Nova Error sending to server:', error);
          // Try to fallback or retry?
       });
    }
  return true; // Keep message channel open for async response
});

// Also monitor tab updates/navigation directly from background script
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    console.log(`Tab updated: ${tab.url}`);
    // Log navigation event
    const logEntry = {
      timestamp: new Date().toISOString(),
      type: 'tab_update',
      url: tab.url,
      title: tab.title
    };
    // Save to storage
    chrome.storage.local.get({ interactions: [] }, (result) => {
      const interactions = result.interactions;
      interactions.push(logEntry);
      chrome.storage.local.set({ interactions: interactions });
    });
  }
});
