"""Sessão autenticada no ServiceNow via navegador com perfil persistente.

O login (SSO/MFA) é sempre manual, numa janela do Edge/Chromium. O perfil fica em
data/browser_profile/, então depois do primeiro login a renovação costuma ser
automática (headless). Aqui só lemos cookies + window.g_ck; nenhuma credencial é digitada.
"""
import json
import threading
import time
from pathlib import Path

import requests

from backend.config import config, ROOT

PROFILE_DIR = ROOT / "data" / "browser_profile"
SESSION_FILE = ROOT / "data" / "sn_session.json"  # cookies + g_ck (segredo: fora do git)
PORTAL = f"https://{config.SERVICENOW_INSTANCE}.service-now.com/sp_iamsmart"
CHECK_EVERY = 300  # s
LOGIN_TIMEOUT = 300  # s para o usuário concluir SSO/MFA
REFRESH_TIMEOUT = 40  # s no modo headless


class SNSession:
    def __init__(self):
        self._lock = threading.Lock()
        self._http: requests.Session | None = None
        self._g_ck: str | None = None
        self.user: str | None = None
        self.connected = False
        self.busy: str | None = None  # 'login' | 'refresh' | None
        self.message = "Sem sessão. Clique em Conectar."
        self.checked_at: float | None = None
        self._keepalive_started = False

    # ---------- estado ----------
    def status(self) -> dict:
        return {
            "connected": self.connected,
            "busy": self.busy,
            "user": self.user,
            "message": self.message,
            "checked_at": self.checked_at,
        }

    @property
    def base(self) -> str:
        return f"https://{config.SERVICENOW_INSTANCE}.service-now.com"

    def http(self):
        """requests.Session autenticada, ou None se não conectado."""
        return self._http if self.connected else None

    def headers(self) -> dict:
        return {"X-UserToken": self._g_ck or "", "Accept": "application/json", "Content-Type": "application/json"}

    # ---------- navegador ----------
    def _harvest(self, headless: bool, timeout: int) -> bool:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            ctx = None
            for channel in ("msedge", "chrome", None):
                try:
                    kw = {"channel": channel} if channel else {}
                    ctx = p.chromium.launch_persistent_context(
                        str(PROFILE_DIR), headless=headless, viewport=None if not headless else {"width": 1280, "height": 800}, **kw
                    )
                    break
                except Exception:
                    continue
            if ctx is None:
                self.message = "Nenhum navegador disponível (Edge/Chrome/Chromium)."
                return False
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_function(
                        "typeof window.g_ck === 'string' && window.g_ck.length > 10", timeout=timeout * 1000, polling=1000
                    )
                except PWTimeout:
                    self.message = "Login não concluído a tempo." if not headless else "Sessão expirou: é preciso logar de novo."
                    return False
                g_ck = page.evaluate("window.g_ck")
                try:
                    user = page.evaluate("(window.NOW && (window.NOW.user_name || window.NOW.user_display_name)) || null")
                except Exception:
                    user = None
                s = requests.Session()
                for c in ctx.cookies():
                    s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
                with self._lock:
                    self._http, self._g_ck, self.user = s, g_ck, user
                self._save(ctx.cookies(), g_ck, user)
                return True
            finally:
                ctx.close()

    def _save(self, cookies, g_ck, user) -> None:
        """Guarda a sessão para sobreviver a reinício do backend (validada ao carregar)."""
        try:
            SESSION_FILE.write_text(json.dumps({"cookies": cookies, "g_ck": g_ck, "user": user}), encoding="utf-8")
        except OSError:
            pass

    def _load(self) -> bool:
        try:
            d = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        s = requests.Session()
        for c in d.get("cookies", []):
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
        self._http, self._g_ck, self.user = s, d.get("g_ck"), d.get("user")
        return self._validate()

    def _validate(self) -> bool:
        s = self._http
        if not s or not self._g_ck:
            return False
        try:
            r = s.get(f"{self.base}/api/now/table/incident", params={"sysparm_limit": 1, "sysparm_fields": "number"},
                      headers=self.headers(), timeout=15, allow_redirects=False)
            return r.status_code == 200
        except Exception:
            return False

    def _run(self, kind: str):
        if self.busy:
            return
        self.busy = kind
        try:
            headless = kind == "refresh"
            self.message = "Renovando sessão…" if headless else "Aguardando login na janela aberta…"
            ok = self._harvest(headless=headless, timeout=REFRESH_TIMEOUT if headless else LOGIN_TIMEOUT)
            ok = ok and self._validate()
            self.connected = ok
            if ok:
                self.message = "Sessão ativa."
            elif "Nenhum navegador" not in self.message and "não concluído" not in self.message and "expirou" not in self.message:
                self.message = "Sessão obtida, mas o ServiceNow recusou (sem permissão/API bloqueada?)."
            self.checked_at = time.time()
        except Exception as e:  # noqa: BLE001
            self.connected = False
            self.message = f"Erro: {e}"
        finally:
            self.busy = None

    # ---------- API pública ----------
    def login(self):
        """Abre a janela para login manual (assíncrono)."""
        threading.Thread(target=self._run, args=("login",), daemon=True).start()

    def refresh(self):
        threading.Thread(target=self._run, args=("refresh",), daemon=True).start()

    def check(self):
        """Valida a sessão atual; se caiu, tenta renovar em headless."""
        if self.busy:
            return
        if self._validate():
            self.connected = True
            self.message = "Sessão ativa."
            self.checked_at = time.time()
            return
        self.connected = False
        self._run("refresh")

    def start_keepalive(self):
        if self._keepalive_started or config.SERVICENOW_MOCK:
            return
        self._keepalive_started = True

        def loop():
            # 1) sessão salva em disco (sobrevive a reinício) 2) renovar com o perfil, sem abrir janela
            if self._load():
                self.connected, self.message, self.checked_at = True, "Sessão ativa.", time.time()
            elif Path(PROFILE_DIR).exists():
                self._run("refresh")
            while True:
                time.sleep(CHECK_EVERY)
                if self.connected or Path(PROFILE_DIR).exists():
                    self.check()

        threading.Thread(target=loop, daemon=True).start()


session = SNSession()
