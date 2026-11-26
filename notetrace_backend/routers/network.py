import io
import socket
import urllib.parse
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Request
import qrcode
import qrcode.image.svg

from ..config import PORT

router = APIRouter(prefix="/api/system/network", tags=["network"])

def detect_ips(target_port: int = PORT) -> Dict[str, Any]:
    primary_ip = None
    # 1. Connect test to determine primary outbound interface IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        primary_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # 2. Enumerate all interfaces
    candidate_ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                candidate_ips.append(ip)
    except Exception:
        pass

    # Prefer 192.168.* or 10.* over virtual 172.* (WSL/Hyper-V/Docker)
    if not primary_ip or primary_ip.startswith("127."):
        lan_cands = [ip for ip in candidate_ips if ip.startswith("192.168.") or ip.startswith("10.")]
        if lan_cands:
            primary_ip = lan_cands[0]
        elif candidate_ips:
            primary_ip = candidate_ips[0]
        else:
            primary_ip = "127.0.0.1"

    all_info = []
    seen = set()

    # Add primary first
    if primary_ip and primary_ip not in seen:
        seen.add(primary_ip)
        all_info.append({
            "ip": primary_ip,
            "label": "Wi-Fi / LAN (Recommended)",
            "is_primary": True
        })

    for ip in candidate_ips:
        if ip not in seen:
            seen.add(ip)
            label = "Virtual Adapter (WSL/VM)" if (ip.startswith("172.") or ip.startswith("10.255.")) else "Local Network"
            all_info.append({
                "ip": ip,
                "label": label,
                "is_primary": False
            })

    return {
        "primary_ip": primary_ip,
        "all_ips": all_info,
        "port": target_port
    }

def generate_qr_data_url(url: str) -> str:
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(url, image_factory=factory, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    svg_str = buf.getvalue().decode("utf-8")
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg_str)

@router.get("")
@router.get("/")
def get_network_info(request: Request, port: Optional[int] = None):
    req_port = port or request.url.port or 8080
    net = detect_ips(target_port=req_port)
    primary_ip = net["primary_ip"]
    device_url = f"http://{primary_ip}:{req_port}"
    qr_data_url = generate_qr_data_url(device_url)

    return {
        "ip": primary_ip,
        "port": req_port,
        "url": device_url,
        "all_ips": net["all_ips"],
        "qr_data_url": qr_data_url
    }

@router.get("/qr")
def get_qr_for_url(url: str = Query(..., description="Target URL to generate QR for")):
    qr_data_url = generate_qr_data_url(url)
    return {
        "url": url,
        "qr_data_url": qr_data_url
    }
