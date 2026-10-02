"""Inspeciona (SÓ LEITURA) o item de catálogo da RITM de acompanhamento e as localidades "CFTV - ..." do formulário.

Uso: venv\\Scripts\\python.exe scripts\\inspect_ritm_item.py   (precisa da sessão do ServiceNow conectada no painel)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.ritm import CAT_ITEM  # noqa: E402
from backend.sn_session import session  # noqa: E402


def main():
    if not session._load():
        print("Sem sessão salva: conecte o ServiceNow no painel primeiro.")
        return 1
    session.connected = True
    http, h, base = session._http, session.headers(), session.base

    r = http.get(f"{base}/api/sn_sc/servicecatalog/items/{CAT_ITEM}", headers=h, timeout=30)
    print("item:", r.status_code)
    item = r.json().get("result", {}) if r.ok else {}
    print("nome:", item.get("name"))
    def walk(vs):
        for v in vs:
            yield v
            yield from walk(v.get("children") or [])

    for v in walk(item.get("variables", [])):
        ch = [c.get("value") for c in v.get("choices", [])][:15]
        print(f"  {v.get('name')!r:40} tipo={v.get('type')} obrig={v.get('mandatory')} ref={v.get('reference')} "
              f"rotulo={v.get('label')!r} {'opções=' + str(ch) if ch else ''}")

    r = http.get(f"{base}/api/now/table/cmn_location", headers=h, timeout=30, params={
        "sysparm_query": "nameSTARTSWITHCFTV - ^ORDERBYname", "sysparm_fields": "name,sys_id", "sysparm_limit": 100})
    locs = r.json().get("result", []) if r.ok else []
    print("localidades:", r.status_code, len(locs))
    for loc in locs:
        print(f"  {loc['name']} | {loc['sys_id']}")
    if locs:  # lista usada pelo painel (select da localidade do formulário)
        out = Path(__file__).resolve().parents[1] / "data" / "ritm_locais.json"
        out.write_text(json.dumps({"_fonte": "cmn_location 'CFTV - ...' (scripts/inspect_ritm_item.py)",
                                   "locais": [{"nome": re.sub(r"\s+", " ", x["name"]).strip(), "sys_id": x["sys_id"]}
                                              for x in locs]}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("salvo em", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
