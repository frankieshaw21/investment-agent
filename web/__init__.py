from sys import platform

# macOS AirPlay Receiver can occupy port 5000.
DEFAULT_PORT = 5001 if platform == "darwin" else 5000
