import requests
from config import FLARESOLVERR_URL, FLARESOLVERR_TIMEOUT

def scrape_with_flaresolverr(url: str) -> str | None:
    try:
        response = requests.post(
            FLARESOLVERR_URL,
            json={"cmd": "request.get", "url": url, "maxTimeout": FLARESOLVERR_TIMEOUT}
        )
        data = response.json()
        if data.get("status") != "ok" or "solution" not in data:
            print(f"❌ FlareSolverr error : {data}")
            return None
        return data["solution"]["response"]
    except Exception as e:
        print(f"❌ FlareSolverr exception : {e}")
        return None