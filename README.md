# Nova - Privacy-First Browser Activity Monitor

Nova is an intelligent, privacy-preserving browser activity monitor that leverages hybrid AI to analyze your digital habits. By combining the speed and privacy of on-device inference (Cactus + FunctionGemma) with the reasoning capabilities of the cloud (Gemini), Nova provides real-time insights without compromising user data.

## Features

-   **Privacy-First Analysis**: Your browsing data is analyzed locally on your device by default. Sensitive information never leaves your machine unless complex reasoning is required.
-   **Hybrid Intelligence**: Seamlessly switches between a lightweight local model (FunctionGemma 270M) for speed and a powerful cloud model (Gemini 3.0 Flash) for complex tasks.
-   **Real-Time Categorization**: Instantly categorizes web activity (e.g., Coding, Social Media, Productivity) and assesses productivity risk.
-   **Chrome Extension**: A lightweight browser extension captures events and provides a live feed of your digital footprint.
-   **Optimized for Apple Silicon**: Built on the Cactus engine, delivering up to 3000 tokens/sec prefill speed on M-series chips.

## Technologies Used

-   **On-Device AI**: [Google FunctionGemma](https://huggingface.co/google/functiongemma-270m-it) (270M parameters) running on [Cactus](https://cactus.co).
-   **Cloud AI**: [Google Gemini 3.0 Flash](https://deepmind.google/technologies/gemini/flash/) for fallback reasoning.
-   **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn.
-   **Frontend**: Chrome Extension (Manifest V3), HTML/JS/CSS.
-   **Tooling**: `cactus-python` SDK, `google-genai` SDK.

## Project Structure

```bash
├── monitor-backend/        # 🧠 The Brain
│   ├── main.py             # FastAPI server & AI orchestration
│   ├── tools/              # AI Tool definitions (API, Context)
│   └── storage/            # Local data persistence
├── chrome-extension/       # 👁️ The Eyes
│   ├── manifest.json       # Extension config
│   ├── background.js       # Event capture & API communication
│   └── popup.js            # User interface
├── hackathon-challenge/    # 🧪 The Lab
│   ├── main.py             # Hybrid routing logic (The Core Challenge)
│   └── benchmark.py        # Performance evaluation suite
└── docs/                   # 📚 Documentation
```

## System Architecture

Nova operates on a three-tier architecture designed for minimal latency and maximum privacy:

1.  **Presentation Layer**: The Chrome Extension captures user interactions (page loads, inputs) and sends them to the local server.
2.  **Application Layer**: The Monitor Backend receives events, manages session state, and orchestrates the AI analysis.
3.  **Intelligence Layer**: The Hybrid Router determines the best execution path:
    *   **Local Path**: Uses FunctionGemma via Cactus for fast, private inference (typical latency: 50-100ms).
    *   **Cloud Path**: Falls back to Gemini 3.0 Flash when the local model's confidence is low or the task is too complex (typical latency: 500ms+).

## Our Approach

The core innovation in Nova is its **Hybrid Routing Strategy**. Instead of relying solely on the cloud (slow, privacy-invasive) or solely on the edge (limited reasoning), we implemented a dynamic router:

1.  **Confidence-Based Routing**: We utilize the confidence scores returned by the Cactus engine. If the local model is >99% confident, we use its result immediately.
2.  **Latency Optimization**: By prioritizing the local model, we achieve near-instantaneous feedback for the user, essential for a real-time monitoring tool.
3.  **Graceful Fallback**: If the local model struggles or returns a low-confidence score, the system seamlessly delegates the task to Gemini Cloud, ensuring high accuracy even for ambiguous inputs.

## Getting Started

### Prerequisites

-   macOS with Apple Silicon (M1/M2/M3/M4).
-   Python 3.9+.
-   Google Chrome.

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/switchchat/extension.git
    cd extension
    ```

2.  **Run the setup script**:
    This will create a virtual environment, install dependencies, and start the backend.
    ```bash
    ./start.sh
    ```

3.  **Install the Chrome Extension**:
    -   Go to `chrome://extensions`.
    -   Enable "Developer mode".
    -   Click "Load unpacked" and select the `chrome-extension` folder.

4.  **Start Browsing**:
    -   Open the extension popup to see the connection status.
    -   Browse the web, and watch Nova analyze your activity in real-time!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">
  Built with 🌵 Cactus and 🧠 Google DeepMind
</div>
