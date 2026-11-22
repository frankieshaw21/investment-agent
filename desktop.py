"""
DataBoard Desktop App - PyWebView wrapper
Double-click to open as a standalone desktop window.
Close window = exit program cleanly.
"""
import os
import sys
import threading
import traceback

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Fix proxy
for key in list(os.environ.keys()):
    if 'proxy' in key.lower():
        del os.environ[key]

from dotenv import load_dotenv
load_dotenv()


def start_flask(window):
    """Start the local server and load the dashboard once its socket is bound."""
    host = "127.0.0.1"
    try:
        from werkzeug.serving import make_server
        from web import DEFAULT_PORT
        from web.app import app, start_signal_monitor

        server = make_server(host, DEFAULT_PORT, app, threaded=True)
    except (Exception, SystemExit):
        traceback.print_exc()
        window.load_html("<h2>DataBoard could not start</h2><p>See the terminal for details.</p>")
        return

    start_signal_monitor()

    # Preload heavy modules in background after Flask is serving
    # This runs while user sees the UI, so first API call is instant
    def _preload():
        try:
            # langchain_openai is the heaviest single import (~2.3s)
            import langchain_openai  # noqa: F401
            # Then coordinator brings in langgraph + all tools
            from agents.coordinator import create_investment_agent, chat  # noqa: F401
            # chromadb for knowledge base
            import chromadb  # noqa: F401
        except Exception:
            pass

    threading.Thread(target=_preload, daemon=True).start()

    threading.Thread(target=server.serve_forever, daemon=True).start()
    window.load_url(f"http://{host}:{server.server_port}/")


if __name__ == "__main__":
    import webview

    if sys.platform == "darwin":
        from AppKit import NSApplication, NSImage

        icon_path = os.path.join(PROJECT_DIR, "web", "static", "databoard.png")
        icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if icon is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(icon)

    # Open window immediately with loading page, then redirect when ready
    window = webview.create_window(
        "DataBoard",
        html="""
        <html><body style="display:flex;align-items:center;justify-content:center;height:100vh;margin:0;
        font-family:-apple-system,sans-serif;background:#f8f9fa;color:#5f6368">
        <div style="text-align:center">
            <h2 style="font-weight:600;color:#202124">DataBoard</h2>
            <p>Loading...</p>
        </div>
        </body></html>
        """,
        width=1400,
        height=900,
        min_size=(1000, 600),
        text_select=True,
    )

    threading.Thread(target=start_flask, args=(window,), daemon=True).start()
    webview.start()
