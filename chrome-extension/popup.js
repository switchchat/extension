// popup.js - Displays recent interactions

document.addEventListener('DOMContentLoaded', () => {
    const logsContainer = document.getElementById('logs');

    function renderLogs() {
        chrome.storage.local.get({ interactions: [] }, (result) => {
            const interactions = result.interactions.slice().reverse(); // Show newest first
            
            logsContainer.innerHTML = '';
            
            if (interactions.length === 0) {
                logsContainer.innerHTML = '<div class="log-entry">No interactions recorded yet.</div>';
                return;
            }

            interactions.forEach(log => {
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                
                const time = new Date(log.timestamp).toLocaleTimeString();
                let detailsText = '';
                
                if (log.type === 'click') {
                    detailsText = `Click: ${log.details.tagName}#${log.details.id}`;
                } else if (log.type === 'input_change') {
                    detailsText = `Input: ${log.details.tagName} (Type: ${log.details.inputType})`;
                } else if (log.type === 'scroll') {
                    detailsText = `Scroll: ${log.details.scrollY}`;
                } else if (log.type === 'page_load') {
                    detailsText = `Load: ${log.details.title}`;
                } else {
                    detailsText = `${log.type}: ${JSON.stringify(log.details)}`;
                }

                entry.textContent = `[${time}] ${detailsText}`;
                logsContainer.appendChild(entry);
            });
        });
    }

    renderLogs();

    // Check server status
    fetch('http://localhost:8000/api/log', { 
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ type: 'status_check', details: 'popup' })
    }).then(() => {
        document.getElementById('status-text').textContent = 'Connected';
        document.getElementById('status-text').style.color = 'green';
    }).catch((err) => {
        document.getElementById('status-text').textContent = 'Disconnected';
        document.getElementById('status-text').style.color = 'red';
        console.error('Server check failed:', err);
    });

    // Listen for storage changes to update live
    chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName === 'local' && changes.interactions) {
            renderLogs();
        }
    });
});
