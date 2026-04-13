import socket

def domain_exists(url: str) -> bool:
    try:
        domain = url.split("//")[-1].split("/")[0]
        socket.gethostbyname(domain)
        return True
    except:
        return False