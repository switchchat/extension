# Nova - Chrome Extension

This Chrome Extension monitors user interactions on web pages and logs them for the Nova project.

## Features
- Captures clicks, input changes, scrolls, text selections, and window focus/blur events.
- Logs interactions to the browser console (`Nova Interaction: ...`).
- Stores recent interactions locally and displays them in the extension popup.

## Installation
1. Open Chrome and go to `chrome://extensions/`.
2. Enable "Developer mode" in the top right corner.
3. Click "Load unpacked".
4. Select the `chrome-extension` folder in this project.

## Usage
- Open any webpage.
- Interact with the page (click, type, scroll).
- Open the Developer Tools (F12) -> Console to see real-time logs.
- Click the Nova extension icon to view a summary of recent interactions.
