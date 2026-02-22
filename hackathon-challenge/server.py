
import sys
import os
import json
import logging
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

# Add cactus path
# We assume this script is running from the root of the 'working' directory
sys.path.insert(0, "cactus/python/src")

# Try to import cactus. If it fails, we mock it for development (so user can still see frontend)
try:
    from cactus import cactus_init, cactus_complete, cactus_destroy
    CACTUS_AVAILABLE = True
except ImportError:
    print("Warning: Cactus library not found. Running in mock mode.")
    CACTUS_AVAILABLE = False
    def cactus_init(path): return "mock_model"
    def cactus_destroy(model): pass
    def cactus_complete(model, messages, **kwargs):
        return json.dumps({
            "function_calls": [{
                "name": "categorize_activity",
                "arguments": {"category": "mock", "summary": "Mock analysis"}
            }],
            "total_time_ms": 0,
            "confidence": 1.0
        })

app = Flask(__name__)
CORS(app)

# Global model handle
MODEL_PATH = "cactus/weights/functiongemma-270m-it"
model = None

# In-memory storage for logs
logs = []

def get_model():
    global model
    if model is None and CACTUS_AVAILABLE:
        print(f"Loading FunctionGemma from {MODEL_PATH}...")
        try:
            model = cactus_init(MODEL_PATH)
            print("Model loaded successfully.")
        except Exception as e:
            print(f"Failed to load model: {e}")
    return model

@app.route('/api/log', methods=['POST', 'OPTIONS'])
def log_interaction():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    data = request.json
    print(f"Received log: {data.get('type')} on {data.get('url', 'unknown')}")
    
    # Simple heuristic to avoid spamming the model
    # Analyze EVERYTHING for now to ensure we see logs
    should_analyze = True 
    # should_analyze = data['type'] in ['page_load', 'form_submit', 'input_change']
    
    analysis = None
    if should_analyze:
        analysis = analyze_event(data)
    
    log_entry = {
        "raw": data,
        "analysis": analysis
    }
    logs.insert(0, log_entry) # Prepend to show newest first
    # Keep last 50 logs
    if len(logs) > 50:
        logs.pop()
        
    return jsonify({"status": "ok", "analysis": analysis})

def analyze_event(event_data):
    model = get_model()
    if not model and CACTUS_AVAILABLE:
        return {"error": "Model not loaded"}
        
    tools = [{
        "name": "categorize_activity",
        "description": "Analyze the user interaction and categorize it.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string", 
                    "enum": ["Coding", "Social Media", "News", "Shopping", "Productivity", "Entertainment", "Other"],
                    "description": "The category of the activity based on the URL and interaction."
                },
                "summary": {
                    "type": "string", 
                    "description": "A very brief (1 sentence) summary of what the user is doing."
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Assessment of productivity risk (e.g. social media is high risk during work hours)."
                }
            },
            "required": ["category", "summary", "risk_level"]
        }
    }]
    
    # Construct prompt
    event_desc = json.dumps(event_data)
    messages = [
        {"role": "system", "content": "You are an AI productivity monitor. Analyze the user's browser interaction."},
        {"role": "user", "content": f"Analyze this event: {event_desc}"}
    ]
    
    cactus_tools = [{"type": "function", "function": t} for t in tools]
    
    try:
        raw_str = cactus_complete(
            model,
            messages,
            tools=cactus_tools,
            force_tools=True,
            max_tokens=256
        )
        
        # Parse response
        # cactus_complete returns a JSON string that might contain 'function_calls'
        try:
            response = json.loads(raw_str)
            function_calls = response.get("function_calls", [])
            if function_calls:
                # Return the arguments of the first function call
                return function_calls[0].get("arguments", {})
        except json.JSONDecodeError:
            print(f"Failed to parse model response: {raw_str}")
            return {"error": "Invalid JSON response"}
            
    except Exception as e:
        print(f"Error during inference: {e}")
        return {"error": str(e)}

    return None

@app.route('/')
def index():
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cactus Monitor Dashboard</title>
        <meta http-equiv="refresh" content="5"> <!-- Auto-refresh every 5s -->
        <style>
            body { font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
            h1 { color: #333; }
            .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .meta { color: #666; font-size: 0.9em; margin-bottom: 5px; }
            .type { font-weight: bold; color: #007bff; }
            .url { color: #28a745; word-break: break-all; }
            .analysis { margin-top: 10px; padding: 10px; background: #e9ecef; border-left: 4px solid #007bff; border-radius: 4px; }
            .tag { display: inline-block; padding: 2px 6px; border-radius: 4px; color: white; font-size: 0.8em; }
            .risk-low { background-color: #28a745; }
            .risk-medium { background-color: #ffc107; color: black; }
            .risk-high { background-color: #dc3545; }
            pre { background: #eee; padding: 5px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h1>🌵 Cactus Activity Monitor</h1>
        <p>Real-time monitoring powered by FunctionGemma (On-Device)</p>
        
        <div id="logs">
            {% for log in logs %}
            <div class="card">
                <div class="meta">
                    <span class="type">{{ log.raw.type }}</span> | 
                    <span class="timestamp">{{ log.raw.timestamp }}</span>
                </div>
                <div class="url">{{ log.raw.url }}</div>
                
                {% if log.analysis and not log.analysis.error %}
                <div class="analysis">
                    <strong>AI Analysis:</strong>
                    <span class="tag risk-{{ log.analysis.risk_level }}">{{ log.analysis.category }}</span>
                    {{ log.analysis.summary }}
                </div>
                {% elif log.analysis and log.analysis.error %}
                <div class="analysis" style="border-left-color: red;">
                    Error: {{ log.analysis.error }}
                </div>
                {% else %}
                <div class="details">
                    <pre>{{ log.raw.details | tojson }}</pre>
                </div>
                {% endif %}
            </div>
            {% else %}
            <p>No interactions recorded yet. Use Chrome to browse!</p>
            {% endfor %}
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template, logs=logs)

if __name__ == '__main__':
    print("Starting server on http://localhost:5000")
    try:
        # Pre-load model
        get_model()
        app.run(port=5000, debug=False) # Debug mode reloads and might mess up model loading
    finally:
        if model and CACTUS_AVAILABLE:
            cactus_destroy(model)
