# -*- coding: utf-8 -*-
import os
import re
import time
import random
import asyncio
import threading
import urllib.parse
import requests
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ==========================================
# 1. CREDENCIAIS E CANAIS
# ==========================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")

# Canais monitorados: Fada dos Cupons + Afiliados e Criadores ML Brasil
CANAL_FADA = "fadadoscupons"
CANAL_AFILIADOS_ML = -1002098480505
CANAIS_ORIGEM = [CANAL_FADA, CANAL_AFILIADOS_ML]

CANAL_DESTINO = "pegueicupom"

# Se True, posta tambem cupons sem link do Fada dos Cupons (ex: iFood)
POSTAR_MESMO_SEM_LINK = True

# Nomes exatos das imagens padrao que voce vai subir no GitHub
IMAGENS_PADRAO = {
    "mercadolivre": "cupom_ml.jpg",
    "shopee": "cupom_shopee.jpg",
    "amazon": "cupom_amazon.jpg",
    "magalu": "cupom_magalu.jpg"
}

# ==========================================
# 2. SEUS IDS DE AFILIADA
# ==========================================
MEU_ID_AMAZON = "achadinh0cc44-20"
MEU_ID_SHOPEE = "18337380528"

MEU_ID_MELI_PERFIL = "pepo8413118"
MEU_ID_MELI_TOOL = "46346758"
PARAMS_MELI = f"matt_word={MEU_ID_MELI_PERFIL}&matt_tool={MEU_ID_MELI_TOOL}&forceInApp=true"

MAGALU_NOME_LOJA = "ofertinhasdapoli"
ALIEXPRESS_TRACKING_ID = "Canalwhats"
MEU_ID_AWIN = "1905004"

ENCURTAR_COM_NOME_DA_LOJA = True

# ==========================================
# 3. MINI SERVIDOR FLASK (RENDER + CRON-JOB)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Robô Peguei Cupom (Telegram) rodando 24h!", 200

def rodar_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 4. CONVERSOR DE LINKS E DETECTOR DE LOJA
# ==========================================
def encurtar_com_nome_loja(url_longa, prefixo_loja):
    if not ENCURTAR_COM_NOME_DA_LOJA or not url_longa.startswith("http"):
        return url_longa

    for _ in range(2):
        try:
            codigo = random.randint(10000, 99999)
            shorturl = f"{prefixo_loja}_{codigo}"
            api = (
                f"https://is.gd/create.php?format=simple"
                f"&url={urllib.parse.quote(url_longa)}"
                f"&shorturl={shorturl}"
            )
            r = requests.get(api, timeout=5)
            if r.status_code == 200 and r.text.startswith("http"):
                return r.text.strip()
        except Exception:
            pass

    try:
        r_tiny = requests.get(f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url_longa)}", timeout=5)
        if r_tiny.status_code == 200 and r_tiny.text.startswith("http"):
            return r_tiny.text.strip()
    except Exception:
        pass

    return url_longa


def abrir_link_camuflado(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9"
    }
    url_atual = url
    html_pag = ""

    try:
        with requests.Session() as s:
            for _ in range(8):
                if "awin1.com/cread.php" in url_atual.lower():
                    break
                r = s.get(url_atual, headers=headers, timeout=7, allow_redirects=False)
                if r.status_code in [301, 302, 303, 307, 308]:
                    prox = r.headers.get("Location", "")
                    if prox:
                        if prox.startswith("/"):
                            p = urllib.parse.urlparse(url_atual)
                            prox = f"{p.scheme}://{p.netloc}{prox}"
                        url_atual = urllib.parse.unquote(prox)
                        continue
                html_pag = r.text
                break
    except Exception as e:
        print("Aviso ao abrir link:", str(e))

    return url_atual, html_pag


def converter_link_individual(url_original):
    url_limpa = url_original.strip()
    if not url_limpa.startswith("http"):
        url_limpa = "https://" + url_limpa

    url_real, html_pag = abrir_link_camuflado(url_limpa)
    u_low = (url_limpa + " " + url_real).lower()

    # 1. MERCADO LIVRE
    if any(d in u_low for d in ["meli.la", "mercadolivre.com", "mercadolado.com"]):
        base = url_real.split("?")[0].split("#")[0]
        if any(b in base.lower() for b in ["/login", "/identification", "not-found", "meli.la", "/sec/", "/social/"]):
            link_ml = f"https://www.mercadolivre.com.br/cupons?{PARAMS_MELI}"
        else:
            link_ml = f"{base}?{PARAMS_MELI}"
        return encurtar_com_nome_loja(link_ml, "MercadoLivre"), "mercadolivre"

    # 2. MAGALU
    if any(d in u_low for d in ["magazineluiza.com", "magazinevoce.com", "magalu.com", "maga.lu", "divulgador.magalu"]):
        base = url_real.split("?")[0].split("#")[0]
        if "magazinevoce.com.br/" in base.lower():
            link_mgl = re.sub(r'magazinevoce\.com\.br/[^/]+', f'magazinevoce.com.br/magazine{MAGALU_NOME_LOJA}', base, flags=re.IGNORECASE)
        elif "magazineluiza.com.br/" in base.lower():
            link_mgl = re.sub(r'(?:www\.)?magazineluiza\.com\.br', f'www.magazinevoce.com.br/magazine{MAGALU_NOME_LOJA}', base, flags=re.IGNORECASE)
        else:
            link_mgl = f"https://www.magazinevoce.com.br/magazine{MAGALU_NOME_LOJA}/"
        return encurtar_com_nome_loja(link_mgl, "Magalu"), "magalu"

    # 3. AMAZON
    if any(d in u_low for d in ["amazon.com", "amzn.to", "amzlink.to", "://a.co/", "link.amazon"]):
        m_asin = (
            re.search(r'/(?:dp|gp/product|gp/aw/d|d)/([A-Z0-9]{10})', url_real, re.IGNORECASE)
            or re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', html_pag, re.IGNORECASE)
        )
        if m_asin:
            link_amz = f"https://www.amazon.com.br/dp/{m_asin.group(1).upper()}?linkCode=ll1&tag={MEU_ID_AMAZON}"
        else:
            base = url_real.split("?")[0].split("#")[0]
            if "amazon.com.br" not in base.lower():
                link_amz = f"https://www.amazon.com.br/ofertas?linkCode=ll1&tag={MEU_ID_AMAZON}"
            else:
                link_amz = f"{base}?linkCode=ll1&tag={MEU_ID_AMAZON}"
        return encurtar_com_nome_loja(link_amz, "Amazon"), "amazon"

    # 4. SHOPEE
    if any(d in u_low for d in ["shopee.com", "shp.ee"]):
        base = url_real.split("?")[0].split("#")[0]
        if "shopee.com.br" not in base.lower():
            base = "https://shopee.com.br/m/cupom-de-desconto"
        link_shp = (
            f"{base}?mmp_pid=an_{MEU_ID_SHOPEE}"
            f"&utm_source=an_{MEU_ID_SHOPEE}"
            f"&utm_medium=affiliates"
            f"&af_siteid={MEU_ID_SHOPEE}"
            f"&pid=affiliates"
            f"&af_id={MEU_ID_SHOPEE}"
        )
        return encurtar_com_nome_loja(link_shp, "Shopee"), "shopee"

    # 5. AWIN
    if "awin1.com/cread.php" in url_real.lower() and MEU_ID_AWIN:
        if re.search(r'awinaffid=\d+', url_real, re.IGNORECASE):
            link_aw = re.sub(r'awinaffid=\d+', f'awinaffid={MEU_ID_AWIN}', url_real, flags=re.IGNORECASE)
        else:
            sep = "&" if "?" in url_real else "?"
            link_aw = f"{url_real}{sep}awinaffid={MEU_ID_AWIN}"
        return encurtar_com_nome_loja(link_aw, "Oferta"), ""

    # 6. ALIEXPRESS
    if any(d in u_low for d in ["aliexpress.com", "s.click.aliexpress", "ali.ski"]):
        base = url_real.split("?")[0]
        return encurtar_com_nome_loja(f"{base}?trackingId={ALIEXPRESS_TRACKING_ID}", "AliExpress"), ""

    return url_original, ""


def identificar_loja_por_texto(texto):
    t = (texto or "").lower()
    if any(k in t for k in ["mercado livre", "meli", "mercadolivre"]):
        return "mercadolivre"
    if "shopee" in t:
        return "shopee"
    if "amazon" in t:
        return "amazon"
    if any(k in t for k in ["magalu", "magazine luiza"]):
        return "magalu"
    return ""


def limpar_e_converter_mensagem(texto):
    """Usada para mensagens do @fadadoscupons."""
    if not texto:
        return "", False, ""

    linhas_limpas = []
    for linha in texto.split("\n"):
        l_low = linha.lower()
        if any(b in l_low for b in ["fadadoscupons", "fadapromos", "t.me/", "chat.whatsapp.com", "#anúncio", "#anuncio"]):
            continue
        linha_mod = re.sub(r'fada\s+dos\s+cupons', 'Peguei Cupom', linha, flags=re.IGNORECASE)
        linhas_limpas.append(linha_mod)

    texto_limpo = "\n".join(linhas_limpas).strip()

    padrao_url = r'(https?://[^\s\)\]\>\"\'`<]+)'
    urls = re.findall(padrao_url, texto_limpo)
    tem_link = len(urls) > 0
    loja_detectada = ""

    for u in set(urls):
        novo_link, loja = converter_link_individual(u)
        if loja and not loja_detectada:
            loja_detectada = loja
        texto_limpo = texto_limpo.replace(u, novo_link)

    if not loja_detectada:
        loja_detectada = identificar_loja_por_texto(texto_limpo)

    return texto_limpo, tem_link, loja_detectada


def formatar_cupom_afiliados_ml(texto):
    """Filtra e limpa mensagens do canal Afiliados e Criadores Mercado Livre Brasil."""
    if not texto:
        return "", False

    t_low = texto.lower()
    # Trava: so aceita se realmente for postagem de cupom
    eh_cupom = (
        any(s in t_low for s in ["🎟", "compra mínima", "compra minima", "desconto máx", "desconto max"])
        and ("off" in t_low or "%" in t_low or "r$" in t_low)
    )
    if not eh_cupom:
        return "", False

    # Extrai apenas as linhas uteis do cupom (nome, %, compra minima, limite, validade)
    linhas_cupom = []
    for linha in texto.split("\n"):
        l = linha.strip()
        l_low = l.lower()
        if not l or "http" in l_low:
            continue
        if any(k in l_low for k in [
            "🎟", "compra mínima", "compra minima", "desconto máx", "desconto max",
            "válido até", "valido ate", "limite", "acima de", "produtos elegíveis",
            "produtos elegiveis", "👉"
        ]):
            linhas_cupom.append(l)

    if not linhas_cupom:
        return "", False

    # Tenta aproveitar o link da mensagem se for de produto/lista ML; senao usa a central de cupons
    padrao_url = r'(https?://[^\s\)\]\>\"\'`<]+)'
    urls = re.findall(padrao_url, texto)
    link_final = ""
    for u in urls:
        convertido, loja = converter_link_individual(u)
        if loja == "mercadolivre":
            link_final = convertido
            break

    if not link_final:
        link_final = encurtar_com_nome_loja(
            f"https://www.mercadolivre.com.br/cupons?{PARAMS_MELI}",
            "MercadoLivre"
        )

    bloco_info = "\n".join(linhas_cupom)
    mensagem_pronta = (
        f"🔥 Cupom Mercado Livre Liberado!\n\n"
        f"{bloco_info}\n\n"
        f"✅ Resgate aqui:\n{link_final}"
    )
    return mensagem_pronta, True


def obter_imagem_padrao(loja):
    """Retorna o caminho da imagem padrao se ela existir no repositorio."""
    arquivo = IMAGENS_PADRAO.get(loja, "")
    if arquivo and os.path.exists(arquivo):
        return arquivo
    return None


# ==========================================
# 5. MOTOR DO TELEGRAM (TELETHON)
# ==========================================
async def iniciar_robo_telegram():
    if not API_ID or not API_HASH or not STRING_SESSION:
        print("❌ ERRO: Configure API_ID, API_HASH e STRING_SESSION nas variaveis de ambiente do Render!")
        return

    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    await client.start()
    print(f"✅ Conectado! Monitorando @{CANAL_FADA} e Afiliados ML -> enviando para @{CANAL_DESTINO}")

    @client.on(events.NewMessage(chats=CANAIS_ORIGEM))
    async def ao_receber_cupom(event):
        try:
            texto_original = event.message.message or ""

            # 1. Se veio do canal Afiliados e Criadores Mercado Livre
            if event.chat_id == CANAL_AFILIADOS_ML:
                texto_final, valido = await asyncio.to_thread(formatar_cupom_afiliados_ml, texto_original)
                if not valido:
                    return
                loja_detectada = "mercadolivre"
                usar_midia_original = False
            else:
                # 2. Se veio do @fadadoscupons
                texto_final, tem_link, loja_detectada = await asyncio.to_thread(limpar_e_converter_mensagem, texto_original)
                if not texto_final and not event.message.media:
                    return
                if not tem_link and not POSTAR_MESMO_SEM_LINK:
                    return
                usar_midia_original = True

            # Escolhe a sua imagem padrao da loja (se existir no GitHub)
            imagem_padrao = obter_imagem_padrao(loja_detectada)

            if imagem_padrao:
                await client.send_message(
                    CANAL_DESTINO,
                    texto_final,
                    file=imagem_padrao
                )
            elif usar_midia_original and event.message.media:
                await client.send_message(
                    CANAL_DESTINO,
                    texto_final,
                    file=event.message.media
                )
            else:
                await client.send_message(
                    CANAL_DESTINO,
                    texto_final,
                    link_preview=True
                )

            print(f"🚀 Cupom ({loja_detectada or 'geral'}) enviado para @{CANAL_DESTINO}!")
        except Exception as e:
            print("❌ Erro ao processar cupom:", str(e))

    await client.run_until_disconnected()


if __name__ == "__main__":
    t_flask = threading.Thread(target=rodar_flask, daemon=True)
    t_flask.start()
    asyncio.run(iniciar_robo_telegram())
