from datetime import date

from backend import volumetria


def test_meses_cruzam_a_virada_do_ano():
    m = volumetria.meses(date(2026, 2, 15), 5)
    assert [r for r, _, _ in m] == ["out/25", "nov/25", "dez/25", "jan/26", "fev/26"]
    assert m[2][1:] == (date(2025, 12, 1), date(2026, 1, 1))
    assert m[-1][1:] == (date(2026, 2, 1), date(2026, 3, 1))


def test_consulta_por_mes_e_filtros(monkeypatch):
    volumetria._cache.clear()
    monkeypatch.setattr(volumetria.config, "SERVICENOW_MOCK", False)
    vistos = []

    def contar(tabela, q):
        vistos.append((tabela, q))
        return 7 if "closed_at" in q else 9
    monkeypatch.setattr(volumetria, "_contar", contar)

    d = volumetria.serie("tasks", 5)
    assert len(d["meses"]) == 5 and d["total_encerrados"] == 35 and d["total_entraram"] == 45
    assert all(t == "sc_task" and "cat_itemIN" in q and "^^" not in q for t, q in vistos)
    fechadas = [q for _, q in vistos if "closed_at" in q]
    assert all("stateIN3,4" in q and "gs.dateGenerate" in q for q in fechadas)

    vistos.clear()
    volumetria.serie("incidentes", 5)
    assert all(t == "incident" for t, _ in vistos)
    assert sum("resolved_at" in q for _, q in vistos) == 5


def test_endpoints_em_mock(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setattr(volumetria.config, "SERVICENOW_MOCK", True)
    volumetria._cache.clear()
    c = TestClient(app)
    for url in ("/tasks/volumetria", "/metrics/volumetria"):
        r = c.get(url)
        assert r.status_code == 200, r.text
        assert len(r.json()["meses"]) == 5
