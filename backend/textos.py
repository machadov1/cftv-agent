"""Regras do manual 'Padrões de Textos de Encerramento — Incidentes CFTV LORA UWB.md' (raiz do projeto).

Blocos sempre na ordem Causa raiz > Análise > Resolução > Encaminhamento > Encerramento, um parágrafo cada.
Regra de ouro: nunca descrever ação que não foi informada; o que falta fica entre colchetes e bloqueia o envio.
"""
import re

MANUAL = "Padrões de Textos de Encerramento — Incidentes CFTV LORA UWB.md"

FECHAMENTOS = [
    "Incidente encerrado.",
    "Incidente encerrado com pendência vinculada à requisição.",
    "Incidente encerrado com pendência vinculada ao suporte da área.",
    "Incidente encerrado com pendência vinculada ao recebimento do material.",
    "Incidente encerrado com pendência vinculada à disponibilidade da PEMT.",
    "Incidente encerrado com acompanhamento vinculado à requisição.",
    "Incidente encerrado, com continuidade das ações no incidente principal (duplicidade).",
    "Incidente encerrado pelo fluxo padrão AMS.",
]
COM_PENDENCIA = FECHAMENTOS[1]

# pendência da RITM -> (Análise: "Reparo depende de ...", Encaminhamento padrão, como dizer ao solicitante)
PENDENCIAS = {
    "PEMT": ("disponibilização de PEMT para acesso ao ponto", "Aguardando disponibilização da PEMT.",
             "da disponibilização de uma PEMT para acesso ao ponto"),
    "Andaime": ("montagem de andaime para acesso ao ponto", "Aguardando montagem do andaime.",
                "da montagem de andaime para acesso ao ponto"),
    "PTA": ("disponibilização de PTA para acesso ao ponto", "Aguardando disponibilização da PTA.",
            "da disponibilização de PTA para acesso ao ponto"),
    "Elétrica": ("apoio da equipe de elétrica para tratativa da falha", "Aguardando atuação da equipe de elétrica.",
                 "do apoio da equipe de elétrica"),
    "Infraestrutura": ("apoio da equipe de infraestrutura para tratativa da falha",
                       "Aguardando atuação da equipe de infraestrutura.", "do apoio da equipe de infraestrutura"),
    "Redes": ("apoio da equipe de redes para tratativa da falha", "Aguardando atuação da equipe de redes.",
              "do apoio da equipe de redes"),
    "Recurso": ("disponibilização de recurso para tratativa da falha", "Aguardando disponibilização do recurso.",
                "da disponibilização de recurso"),
    "Agendamento": ("agendamento de acesso à área para tratativa da falha", "Aguardando agendamento do acesso.",
                    "do agendamento de acesso à área"),
}
_SEM_PENDENCIA = ("atuação de outra equipe para tratativa da falha", "Aguardando atuação da equipe responsável.",
                  "da atuação de outra equipe")

SLA_PROXIMO = ("Considerando a proximidade do encerramento do SLA do incidente, o acompanhamento seguirá vinculado à "
               "requisição.")


def pendencia(nome: str | None) -> tuple[str, str, str]:
    return PENDENCIAS.get(nome or "", _SEM_PENDENCIA)


def validacao_fmt(nome: str | None) -> str | None:
    """'Leila Canazart' -> 'Canazart, Leila'; 'Canazart, Leila' fica como está."""
    n = re.sub(r"\s+", " ", (nome or "").strip().rstrip("."))
    if not n:
        return None
    if "," in n:
        sob, pre = (p.strip() for p in n.split(",", 1))
        return f"{sob}, {pre}" if pre else sob
    partes = n.split(" ")
    return n if len(partes) == 1 else f"{partes[-1]}, {' '.join(partes[:-1])}"


def montar(causa: str, analise: str | list[str] | None = None, resolucao: str | None = None,
           encaminhamento: str | None = None, encerramento: str = FECHAMENTOS[0], validacao: str | None = None) -> str:
    def frase(t: str) -> str:
        t = re.sub(r"[ \t]{2,}", " ", t.strip())
        return t if t.endswith((".", "!", "?", ")")) else f"{t}."
    blocos = [f"Causa raiz: {frase(causa)}"]
    if isinstance(analise, list):
        blocos.append("Análise:\n\n" + "\n".join(f"- {frase(a)}" for a in analise))
    elif analise:
        blocos.append(f"Análise: {frase(analise)}")
    if resolucao:
        blocos.append(f"Resolução: {frase(resolucao)}")
    if encaminhamento:
        blocos.append(f"Encaminhamento: {frase(encaminhamento)}")
    fim = f"Encerramento: {frase(encerramento)}"
    v = validacao_fmt(validacao)
    if v:
        fim += f" Validação: {v}."
    blocos.append(fim)
    return "\n\n".join(blocos)


def com_validacao(texto: str, nome: str | None) -> str:
    """Acrescenta 'Validação: Sobrenome, Nome.' na linha de Encerramento (ou no fim), sem duplicar."""
    v = validacao_fmt(nome)
    if not v or re.search(r"Valida[çc][ãa]o:", texto):
        return texto
    linhas = texto.rstrip().splitlines()
    for i in range(len(linhas) - 1, -1, -1):
        if linhas[i].lstrip().startswith("Encerramento:"):
            linhas[i] = f"{linhas[i].rstrip()} Validação: {v}."
            return "\n".join(linhas)
    return f"{texto.rstrip()} Validação: {v}."


_PLACEHOLDER = re.compile(r"\[(?!credencial\]|CPF\])[^\]\n]{2,60}\]")
_LINK_REQ = re.compile(r"https?://\S*?(RITM\d{7}|REQ\d{7})\S*", re.I)
_LINK_SN = re.compile(r"https?://\S*service-now\.com\S*", re.I)
_CRED = re.compile(r"(?i)\b(senha|password|pwd|token|usu[áa]rio\s*/\s*senha)\s*[:=]\s*\S+")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def _restabelec(m: re.Match) -> str:
    return m.group(1) + "eestabelec"


def revisar(texto: str, encerramento: bool = True) -> tuple[str, list[str]]:
    """Corrige o que o manual manda corrigir sem comentar e devolve avisos do que precisa de atenção."""
    t = texto or ""
    avisos = []
    t = re.sub(r"\b([Rr])estabelec", _restabelec, t)
    t = re.sub(r"\bCausa base\b", "Causa raiz", t)
    t = _LINK_REQ.sub(lambda m: m.group(1).upper(), t)
    if _CRED.search(t):
        t = _CRED.sub(lambda m: f"{m.group(1)}: [credencial]", t)
        avisos.append("Credencial no texto foi substituída por [credencial].")
    if _CPF.search(t):
        t = _CPF.sub("[CPF]", t)
        avisos.append("CPF no texto foi substituído por [CPF].")
    if _LINK_SN.search(t):
        avisos.append("Há link do ServiceNow no texto: use só o número (RITM/REQ/INC).")
    if encerramento and t.strip() and "Incidente encerrado" not in t and "Incidente desconsiderado" not in t:
        avisos.append("Texto de encerramento sem a linha 'Incidente encerrado'.")
    for p in bloqueios(t):
        avisos.append(f"Preencha {p} antes de enviar.")
    return t, avisos


def bloqueios(texto: str) -> list[str]:
    """Colchetes de modelo ainda não preenchidos ([RITM], [descreva a ação executada]): não pode ir ao ServiceNow."""
    return list(dict.fromkeys(_PLACEHOLDER.findall(texto or "")))


def causa_do_titulo(titulo: str, cidade: str | None = None) -> str | None:
    """'Piracicaba - Câmeras 399, 407 sem conexão' -> 'Câmeras 399, 407 sem conexão'. Título fora do padrão -> None."""
    t = (titulo or "").strip()
    if not t or t.startswith("["):
        return None
    if cidade and re.match(rf"^{re.escape(cidade)}\s*-\s*", t, re.I):
        return re.sub(rf"^{re.escape(cidade)}\s*-\s*", "", t, flags=re.I).strip() or None
    m = re.match(r"^[^\-\[\]]{3,40}\s-\s(.+)$", t)
    return m.group(1).strip() if m else None


def alvo_cameras(codes: list[str]) -> str:
    return f"Câmera {codes[0]}" if len(codes) == 1 else f"Câmeras {', '.join(codes)}"


# ---------- modelos por cenário ----------
def camera_verificada(causa: str | None, com_print: list[str], sem_sinal: list[str] | None = None,
                      validacao: str | None = None) -> str:
    """Câmera testada no Digifort e operando (cenário 3: verificado e já operando, sem dizer que reestabeleceu)."""
    sem_sinal = [c for c in (sem_sinal or []) if c not in com_print]
    todas = com_print + sem_sinal
    causa = causa or f"{alvo_cameras(todas)} sem conexão"
    if not sem_sinal:
        analise = ("Realizada verificação no Digifort, com identificação de que "
                   + ("a câmera se encontra operando" if len(com_print) == 1 else "as câmeras se encontram operando")
                   + " normalmente no momento da checagem. Evidência (print) anexada ao incidente.")
        return montar(causa, analise, validacao=validacao)
    linhas = [f"{c}: operando normalmente no momento da checagem, evidência (print) anexada" for c in com_print]
    linhas += [f"{c}: sem sinal no Digifort no momento da checagem" for c in sem_sinal]
    return montar(causa, linhas, encaminhamento="Acompanhamento seguirá vinculado à requisição [RITM]",
                  encerramento=COM_PENDENCIA, validacao=validacao)


def scom_heartbeat(fqdn: str, ip: str | None = None, media_ms: int | None = None) -> str:
    ping = f"ao servidor ({ip})" if ip else "ao servidor"
    media = f" e tempo médio de {media_ms}ms" if media_ms is not None else ""
    return montar(f"Falha de heartbeat do serviço System Center Management no servidor {fqdn}",
                  f"Realizado teste de conectividade via ping {ping}, com 0% de perda de pacotes{media}. "
                  "Evidência anexada ao incidente.",
                  "Serviço verificado e validado, operando normalmente sem necessidade de intervenção.")


ACESSO_CAUSA = "Solicitação de acesso às câmeras aberta via incidente"
ACESSO_ANALISE = "Fluxo de concessão de acesso segue por requisição, dada a necessidade de aprovações gerenciais"


def acesso_despacho() -> str:
    return f"Causa raiz: {ACESSO_CAUSA}.\n\nAnálise: {ACESSO_ANALISE}."


def acesso_encerramento(validacao: str | None = None) -> str:
    return montar(ACESSO_CAUSA, ACESSO_ANALISE,
                  encaminhamento="Realizado contato com o solicitante, com orientação sobre o caminho correto para "
                                 "abertura da requisição", validacao=validacao)


def ritm_descricao(causa: str, pend: str | None, encaminhamento: str | None = None, ritm: str | None = None,
                   sla_proximo: bool = False) -> str:
    recurso, aguardando, _ = pendencia(pend)
    analise = f"Reparo depende de {recurso}."
    if sla_proximo:
        analise += f" {SLA_PROXIMO}"
    enc = (encaminhamento or aguardando).strip()
    enc = enc if enc.endswith(".") else f"{enc}."
    # sem número (a própria RITM ainda vai ser criada): "à requisição."; a work note recebe o número via com_ritm
    vinculo = f"requisição {ritm}" if ritm else "requisição"
    return montar(causa, analise, encaminhamento=f"{enc} Acompanhamento seguirá vinculado à {vinculo}",
                  encerramento=COM_PENDENCIA)


def com_ritm(texto: str, ritm: str) -> str:
    """Põe o número da RITM no Encaminhamento (só lá: o Encerramento fica 'vinculada à requisição.')."""
    t = texto.replace("[RITM]", ritm)
    if ritm not in t:
        t = re.sub(r"(vinculado à requisição)(\.)", rf"\1 {ritm}\2", t, count=1)
    return t


def simples(causa: str | None) -> str:
    return montar(causa or "[sintoma e ativo afetado]", resolucao="[descreva a ação executada]")
