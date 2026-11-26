import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple

def is_safe_url(url: str) -> Tuple[bool, str]:
    """Validates that a URL is HTTP/HTTPS and does not target loopback/private/internal addresses."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False, "Unsupported scheme"
        
        hostname = parsed.hostname
        if not hostname:
            return False, "Missing hostname"
        
        # Check hostname literal IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False, "Target IP is in a private/restricted range"
            return True, ""
        except ValueError:
            pass
        
        # Resolve hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False, "Resolved IP is in a private/restricted range"
                
        return True, ""
    except Exception as e:
        return False, f"URL validation failed: {str(e)}"
