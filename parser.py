import re
from typing import Dict, List

MESES = {"ENERO":1, "FEBRERO":2, "MARZO":3, "ABRIL":4, "MAYO":5, "JUNIO":6,
         "JULIO":7, "AGOSTO":8, "SEPTIEMBRE":9, "OCTUBRE":10, "NOVIEMBRE":11, "DICIEMBRE":12}

def extract_and_calculate(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    full = "\n".join(lines)

    # Metadata
    code = re.search(r"SMENOR\s+(\d+)", full)
    date_m = re.search(r"SÁBADO\s+(\d+)\s+DE\s+(\w+)\s+DE\s+(\d+)", full, re.I)
    salon_m = re.search(r"SALÓN:\s*([^\n]+)", full, re.I)
    pax_m = re.search(r"ASISTENTES:\s*(\d+)\s+ADULTOS\+\s*(\d+)\s+NIÑOS", full, re.I)

    adults = int(pax_m.group(1)) if pax_m else 0
    children = int(pax_m.group(2)) if pax_m else 0
    total = adults + children
    mes = MESES.get(date_m.group(2).upper(), 5) if date_m else 5
    service_date = f"{date_m.group(3)}-{mes:02d}-{date_m.group(1)}" if date_m else "2026-05-09"

    # Horarios
    schedules = []
    coc = re.search(r"HORARIO COCTEL:\s*(\d{2}:\d{2})H?\s*(\d{2}:\d{2})H?", full, re.I)
    if coc: schedules.append({"type":"cocktail","start":coc.group(1),"end":coc.group(2)})
    ban = re.search(r"HORARIO BANQUETE:\s*(\d{2}:\d{2})H?\s*A\s*(\d{2}:\d{2})H?", full, re.I)
    if ban: schedules.append({"type":"banquet","start":ban.group(1),"end":ban.group(2)})

    # Precios
    menus = {}
    for m in re.finditer(r"(MENÚ ADULTO|BARRA LIBRE 2 H|MENÚ INFANTIL)\s+([\d,]+)€", full, re.I):
        menus[m.group(1)] = float(m.group(2).replace(",", "."))

    # Finanzas
    sig = re.search(r"SEÑAL\s*(\d+)€", full, re.I)
    tel = re.search(r"(\d{9})", full)
    finance = {
        "signal": float(sig.group(1)) if sig else 0,
        "remaining": "MISMA SEMANA" if "RESTO MISMA SEMANA" in full else "PENDIENTE",
        "contact_phone": tel.group(1) if tel else ""
    }

    # Producción
    production = []
    def add(station, name, unit=1.0, target="adults"):
        pax = adults if target=="adults" else (children if target=="children" else total)
        production.append({"station": station, "item_name": name, "base_qty": unit, "pax_factor": pax, "notes": ""})

    # CÓCTEL ADULTOS
    cocktails = [
        ("GRISINES DE JAMÓN", "CÓCTEL/FRÍOS", "Grisines de jamón de reserva"),
        ("LARDONES DE QUESO", "CÓCTEL/FRÍOS", "Lardones de queso Idiazábal"),
        ("ROLLITO DE TRAMEZZINO", "CÓCTEL/FRÍOS", "Rollito de tramezzino con pavo"),
        ("CARAMELOS DE CHISTORRA", "CÓCTEL/FRÍOS", "Caramelos de chistorra"),
        ("BRIOCHE DE CALAMARES", "CÓCTEL/FRÍOS", "Brioche de calamares a la Andaluza"),
    ]
    for kw, st, name in cocktails:
        if kw in full: add(st, name, 1.0, "adults")
    if "CROQUETAS DE IBÉRICO 6 PIEZAS" in full:
        add("CÓCTEL/FRÍOS", "Croquetas de ibérico (6 uds/pax)", 6.0, "adults")

    # MENÚ ADULTO
    adultos = [
        ("ENSALADA DE BURRATA", "PRIMEROS", "Ensalada de burrata sobre nido de rúcula"),
        ("LUBINA COSTRADA", "CALIENTES/PESCADO", "Lubina costrada de ajo perejil"),
        ("SORBETE", "POSTRES", "Sorbete de mandarina"),
        ("SOLOMILLO DE TERNERA", "CALIENTES/CARNE", "Solomillo de ternera crocante"),
        ("LINGOTE DE PATATA", "GUARNICIONES", "Lingote de patata"),
        ("SACHER DE ALBARICOQUE", "PASTELERÍA", "Sacher de albaricoque con coulis de mango"),
        ("HELADO DE PLÁTANO", "POSTRES", "Helado de plátano"),
    ]
    for kw, st, name in adultos:
        if kw in full: add(st, name, 1.0, "adults")
    if "TARTA:" in full: add("PASTELERÍA", "Tarta evento (cortan)", 1.0, "total")
    if "MUÑECO" in full: add("PASTELERÍA", "Muñeco tarta", 1.0, "total")

    # MENÚ INFANTIL
    infantil = [
        ("CROQUETAS", "INFANTIL/CÓCTEL", "Croquetas"),
        ("FINGERS DE QUESO", "INFANTIL/CÓCTEL", "Fingers de queso"),
        ("EMPANADILLAS", "INFANTIL/CÓCTEL", "Empanadillas"),
        ("ESCALOPE MILANESA", "INFANTIL/CARNE", "Escalope milanesa de ternera con queso"),
        ("PATATAS FRITAS", "INFANTIL/GUARNICIÓN", "Patatas fritas"),
        ("LINGOTE DE CHOCOLATE", "INFANTIL/POSTRE", "Lingote de chocolate con lacasitos"),
    ]
    for kw, st, name in infantil:
        if kw in full and "INFANTIL" in full: add(st, name, 1.0, "children")

    # BODEGA
    if "BARRA LIBRE" in full:
        add("BODEGA/SERVICIOS", "Barra libre 2h adultos", 1.0, "adults")
        if children > 0: add("BODEGA/SERVICIOS", "Barra libre 2h infantil", 1.0, "children")
    for kw in ["VINO BLANCO", "VINO TINTO", "CERVEZAS", "AGUA MINERAL", "REFRESCOS", "LICORES", "CAFÉ"]:
        if kw in full: add("BODEGA/STOCK", kw, 1.0, "total")

    # MONTAJE
    details = []
    if "TABLERO CANDY" in full: details.append("• TABLERO CANDY")
    if "MANTEL GRIS" in full: details.append("• MANTEL GRIS BORDADO")
    tables = re.findall(r"Nº\d+", full)
    if tables: add("MONTAJE/SALA", f"Mesetas: {', '.join(tables)}", 1.0, "total")

    return {
        "event": {"code": code.group(1) if code else "UNK", "name": "COMUNIÓN EVA", "service_date": service_date, "salon": salon_m.group(1).strip() if salon_m else "MENORCA", "adults": adults, "children": children},
        "schedules": schedules, "menus": menus, "production": production,
        "montage": {"area": "SALÓN MENORCA", "details": "\n".join(details), "table_map": tables},
        "finance": finance
    }