import os
import socket
import uvicorn
from notetrace_backend.config import HOST, PORT

def get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print("=" * 60)
    print("               Manifest Server Running                ")
    print("=" * 60)
    print(f"  * Laptop Access:         http://localhost:{PORT}")
    print(f"  * Tablet / Wi-Fi Access: http://{lan_ip}:{PORT}")
    print(f"  * Tablet NiKiosk Display: http://{lan_ip}:{PORT}/display")
    print("=" * 60)
    print()
    uvicorn.run("notetrace_backend.main:app", host=HOST, port=PORT, reload=False, loop="asyncio")
