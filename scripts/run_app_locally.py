"""Helper script to launch the Streamlit Search Journey Inspector GUI with local observability."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request


def _check_endpoint(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-search-journey-startup"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return bool(200 <= resp.status < 300)
    except Exception:
        return False


def _get_json(url: str, timeout: float = 2.0) -> list[dict[str, object]] | dict[str, object] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-search-journey-startup"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            loaded = json.loads(data)
            if isinstance(loaded, (list, dict)):
                return loaded
            return None
    except Exception:
        return None


def ensure_observability_stack() -> None:
    """Ensure Docker Compose observability stack is running and provisioned correctly."""
    compose_cmd = ["docker", "compose", "-f", "docker-compose.observability.yml"]

    # 1. Bring up observability containers
    print("🐳 Ensuring local observability stack is running...")
    try:
        subprocess.run([*compose_cmd, "up", "-d"], check=True, stdout=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Warning: Could not start docker compose observability stack: {e}")
        return

    # 2. Wait for services to be ready
    print("⏳ Waiting for observability endpoints...")
    deadline = time.time() + 20.0
    grafana_ready = False
    prometheus_ready = False
    tempo_ready = False

    while time.time() < deadline:
        if not grafana_ready and _check_endpoint("http://localhost:3000/api/health"):
            grafana_ready = True
        if not prometheus_ready and _check_endpoint("http://localhost:9090/-/ready"):
            prometheus_ready = True
        if not tempo_ready and _check_endpoint("http://localhost:3200/ready"):
            tempo_ready = True

        if grafana_ready and prometheus_ready and tempo_ready:
            break
        time.sleep(0.5)

    # 3. Verify Grafana dashboard provisioning (UID: ai-search-journey-overview)
    dashboard_found = False
    search_res = _get_json("http://localhost:3000/api/search")
    if isinstance(search_res, list):
        dashboard_found = any(
            isinstance(d, dict) and d.get("uid") == "ai-search-journey-overview" for d in search_res
        )

    if not dashboard_found and grafana_ready:
        print("🔄 Provisioned dashboard missing; recreating Grafana service cleanly...")
        try:
            subprocess.run(
                [*compose_cmd, "up", "-d", "--force-recreate", "grafana"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            # Re-verify dashboard after restart
            time.sleep(2.0)
            search_res = _get_json("http://localhost:3000/api/search")
            if isinstance(search_res, list):
                dashboard_found = any(
                    isinstance(d, dict) and d.get("uid") == "ai-search-journey-overview"
                    for d in search_res
                )
        except Exception as e:
            print(f"⚠️ Warning during Grafana recreation: {e}")

    # 4. Verify datasources (prometheus & tempo)
    datasources_res = _get_json("http://localhost:3000/api/datasources")
    prom_ds = False
    tempo_ds = False
    if isinstance(datasources_res, list):
        for ds in datasources_res:
            if isinstance(ds, dict):
                if ds.get("uid") == "prometheus" or ds.get("type") == "prometheus":
                    prom_ds = True
                if ds.get("uid") == "tempo" or ds.get("type") == "tempo":
                    tempo_ds = True

    status_msg = (
        f"✓ Observability Ready: Grafana={grafana_ready}, Prometheus={prometheus_ready}, "
        f"Tempo={tempo_ready}, Dashboard={dashboard_found}, "
        f"Datasources (Prom/Tempo)={prom_ds}/{tempo_ds}"
    )
    print(status_msg)


def main() -> None:
    """Launch the observability stack and Streamlit app."""
    ensure_observability_stack()

    print("\n==================================================")
    print("🚀 AI Search Journey Lab")
    print("   Streamlit:")
    print("   http://localhost:8502 (or http://localhost:8501)")
    print("\n📊 Observability")
    print("   Grafana:")
    print("   http://localhost:3000")
    print("\n   AgentOps Dashboard:")
    print("   http://localhost:3000/d/ai-search-journey-overview/ai-search-journey-observability-overview")
    print("\n   Tempo Explore:")
    print("   http://localhost:3000/explore")
    print("\n   Prometheus:")
    print("   http://localhost:9090")
    print("==================================================\n")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/ai_search_journey/app.py",
    ]
    try:
        sys.exit(subprocess.call(cmd))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
