"""Abre um dashboard do ServiceNow (SOMENTE LEITURA) e salva capturas de tela + os títulos dos widgets.

Uso: python scripts/snapshot_dashboard.py <url> <pasta_de_saida>
Abre o navegador com o perfil salvo; se pedir login/MFA, o login é manual na própria janela.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from backend.sn_session import PROFILE_DIR  # noqa: E402


def main(url: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = None
        for channel in ("msedge", "chrome", None):
            try:
                kw = {"channel": channel} if channel else {}
                ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False, viewport={"width": 1600, "height": 1000}, **kw)
                break
            except Exception as e:  # noqa: BLE001
                err = e
        if ctx is None:
            print("Sem navegador disponível:", err)
            return 1
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("Aguardando login (até 5 min)...", flush=True)
            page.wait_for_function("location.hostname.includes('service-now.com') && typeof window.g_ck === 'string' && window.g_ck.length > 10",
                                   timeout=300000, polling=1000)
            print("Logado. Esperando os widgets renderizarem...", flush=True)
            time.sleep(20)
            page.screenshot(path=str(out / "dash_1.png"))
            frame = next((f for f in page.frames if f != page.main_frame), None)
            texto = ""
            if frame:
                try:
                    texto = frame.locator("body").inner_text(timeout=10000)
                except Exception:  # noqa: BLE001
                    pass
                for i in (2, 3):
                    try:
                        frame.evaluate(f"window.scrollTo(0, {(i - 1) * 800})")
                        time.sleep(2)
                        page.screenshot(path=str(out / f"dash_{i}.png"))
                    except Exception:  # noqa: BLE001
                        break
            (out / "dash_texto.txt").write_text(texto or page.locator("body").inner_text(), encoding="utf-8")
            print("OK: capturas em", out, flush=True)
            return 0
        finally:
            ctx.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
