"""
server.py - Compatibility launcher delegating to api_server.py
"""
import api_server

if __name__ == "__main__":
    api_server.start_server(8080)
