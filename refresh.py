#!/usr/bin/env python3
"""
Pipeline de dados do Dashboard ENAMED (Aristo - Direcao Enamed).
Le a planilha DASH_ENAMED (abas DADOS_GERENCIADOR + DADOS_HUBSPOT),
computa todos os KPIs/pace/quebra por criativo e escreve data.json.

Fonte canonica:
  - Spend/impr/clicks/LPV  -> DADOS_GERENCIADOR (Meta), filtrado p/ campanhas "direcaoenamed"
  - Inscritos/leads/medico -> DADOS_HUBSPOT (form do evento)
  - Lead PAGO = UTM Campaign contem "direcaoenamed". Demais = organico/outros.
"""
import os, json, datetime as dt
from pathlib import Path
from collections import defaultdict

SID = "1uExbyUCZ3fKqfZCayHRf-UzxgafDORPmUqucFR5OKRs"
OUT = Path(__file__).parent / "data.json"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
LOCAL_CRED = os.path.expanduser("~/.claude/skills/ga4/credentials/ga4-instituto-andhela.json")

def get_client():
    """Funciona no CI (secret GOOGLE_SHEETS_CREDENTIALS_JSON) e local (arquivo da SA)."""
    import gspread
    from google.oauth2.service_account import Credentials
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH", LOCAL_CRED)
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)

# ---------------- METAS (print do cliente; editar aqui) ----------------
CPL_TARGET        = 129.0
BUDGET            = 31000.0
LEADS_PAGOS_TARGET = 240
ORGANICO_TARGET   = 150
TOTAL_TARGET      = 390
CAMPAIGN_START    = dt.date(2026, 6, 5)
EVENT_DATE        = dt.date(2026, 6, 16)   # Live 16/06 20h
try:
    from zoneinfo import ZoneInfo
    TODAY = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
except Exception:
    TODAY = (dt.datetime.utcnow() - dt.timedelta(hours=3)).date()
# -----------------------------------------------------------------------

def num(x):
    if x is None: return 0.0
    s = str(x).strip().replace(".", "").replace(",", ".")
    if s in ("", "-"): return 0.0
    try: return float(s)
    except: return 0.0

def is_enamed(c): return "direcaoenamed" in (c or "").lower()

gc = get_client()
sh = gc.open_by_key(SID)

# ---------- GERENCIADOR (Meta) ----------
g = sh.worksheet("DADOS_GERENCIADOR").get_all_values()
gh = {h.strip(): i for i, h in enumerate(g[0])}
G_DAY, G_CAMP, G_AD = gh["Day"], gh["Campaign Name"], gh["Ad Name"]
G_IMPR, G_SPEND, G_CLK = gh["Impressions"], gh["Amount Spent"], gh["Link Clicks"]
G_LPV = gh["Landing Page Views"]
grows = [r for r in g[1:] if any(c.strip() for c in r) and len(r) > G_CAMP and is_enamed(r[G_CAMP])]

spend = impr = clk = lpv = 0.0
spend_by_day = defaultdict(float)
spend_by_ad  = defaultdict(float)
lpv_by_ad    = defaultdict(float)
for r in grows:
    s = num(r[G_SPEND]) if len(r) > G_SPEND else 0
    spend += s; impr += num(r[G_IMPR]); clk += num(r[G_CLK]) if len(r)>G_CLK else 0
    lpv += num(r[G_LPV]) if len(r)>G_LPV else 0
    spend_by_day[r[G_DAY]] += s
    ad = r[G_AD] if len(r) > G_AD else ""
    spend_by_ad[ad] += s
    if len(r) > G_LPV: lpv_by_ad[ad] += num(r[G_LPV])

# ---------- HUBSPOT (inscritos) ----------
h = sh.worksheet("DADOS_HUBSPOT_ENAMED").get_all_values()
hh = {x.strip(): i for i, x in enumerate(h[0])}
H_DATA, H_MED, H_UCAMP = hh["Data de conversão recente"], hh["É médico?"], hh["UTM Campaign"]
H_SRC, H_CONT = hh["UTM Source"], hh["UTM Content"]
hrows = [r for r in h[1:] if any(c.strip() for c in r) and len(r) > H_DATA and r[H_DATA].strip()]

def daykey(s):  # "05/06/2026 16:56:38" -> "2026-06-05"
    d = s.strip().split(" ")[0]
    try:
        dd, mm, yy = d.split("/"); return f"{yy}-{mm}-{dd}"
    except: return ""

total_inscritos = len(hrows)
paid = [r for r in hrows if len(r) > H_UCAMP and is_enamed(r[H_UCAMP])]
organico = [r for r in hrows if r not in paid]
medicos = sum(1 for r in hrows if len(r) > H_MED and r[H_MED].strip().lower() == "sim")

leads_by_day = defaultdict(int)        # todos inscritos
paid_by_day  = defaultdict(int)
leads_by_ad  = defaultdict(int)        # por UTM content (paid)
for r in hrows:
    leads_by_day[daykey(r[H_DATA])] += 1
for r in paid:
    paid_by_day[daykey(r[H_DATA])] += 1
    ad = r[H_CONT] if len(r) > H_CONT else ""
    leads_by_ad[ad] += 1

n_paid = len(paid)
n_org  = len(organico)

# ---------- PACE / PROJECAO ----------
# dias cheios = anteriores a hoje, dentro da campanha
all_days = sorted(set(spend_by_day) | set(f"{daykey(r[H_DATA])}" for r in hrows))
all_days = [d for d in all_days if d]
full_days = [d for d in all_days if d < TODAY.isoformat()]
n_full = max(len(full_days), 1)
days_left = max(0, (EVENT_DATE - TODAY).days)   # ate o evento, sem contar hoje (>=0 apos a live)

paid_per_day_full = sum(paid_by_day[d] for d in full_days) / n_full
spend_per_day_full = sum(spend_by_day[d] for d in full_days) / n_full
total_per_day_full = sum(leads_by_day[d] for d in full_days) / n_full

cpl_real = spend / n_paid if n_paid else 0
# Projecao a run-rate atual (inclui hoje + days_left dias)
proj_paid = round(n_paid + paid_per_day_full * (days_left + 1))
proj_total = round(total_inscritos + total_per_day_full * (days_left + 1))
proj_spend = round(spend + spend_per_day_full * (days_left + 1), 2)
# Pace necessario p/ bater meta de leads pagos ate o evento
need_paid_per_day = (LEADS_PAGOS_TARGET - n_paid) / (days_left + 1) if days_left >= 0 else 0
# Budget pacing
budget_left = BUDGET - spend
budget_per_day_needed = budget_left / (days_left + 1) if days_left >= 0 else 0

# ---------- series acumuladas ----------
series_days = sorted(set(spend_by_day) | set(leads_by_day))
series_days = [d for d in series_days if d]
cum_paid = cum_total = cum_spend = 0
series = []
# meta diaria linear de leads pagos (burn-up alvo)
total_window = (EVENT_DATE - CAMPAIGN_START).days + 1
for i, d in enumerate(series_days):
    cum_paid += paid_by_day.get(d, 0)
    cum_total += leads_by_day.get(d, 0)
    cum_spend += spend_by_day.get(d, 0)
    series.append({
        "day": d,
        "leads_paid": paid_by_day.get(d, 0),
        "leads_total": leads_by_day.get(d, 0),
        "spend": round(spend_by_day.get(d, 0), 2),
        "cum_paid": cum_paid,
        "cum_total": cum_total,
        "cum_spend": round(cum_spend, 2),
    })

# ---------- por criativo ----------
ads = []
for ad in sorted(set(spend_by_ad) | set(leads_by_ad), key=lambda a: -spend_by_ad.get(a, 0)):
    sp = round(spend_by_ad.get(ad, 0), 2)
    ld = leads_by_ad.get(ad, 0)
    ads.append({
        "ad": ad,
        "spend": sp,
        "leads": ld,
        "lpv": int(lpv_by_ad.get(ad, 0)),
        "cpl": round(sp / ld, 2) if ld else None,
    })

data = {
    "updated_at": dt.datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0).isoformat(),
    "today": TODAY.isoformat(),
    "event_date": EVENT_DATE.isoformat(),
    "campaign_start": CAMPAIGN_START.isoformat(),
    "days_left": days_left,
    "targets": {
        "cpl": CPL_TARGET, "budget": BUDGET,
        "leads_pagos": LEADS_PAGOS_TARGET, "organico": ORGANICO_TARGET, "total": TOTAL_TARGET,
    },
    "kpis": {
        "inscritos": total_inscritos,
        "leads_pagos": n_paid,
        "organico": n_org,
        "medicos": medicos,
        "pct_medico": round(100 * medicos / total_inscritos, 1) if total_inscritos else 0,
        "spend": round(spend, 2),
        "impressions": int(impr),
        "clicks": int(clk),
        "lpv": int(lpv),
        "cpl_real": round(cpl_real, 2),
        "cpc": round(spend / clk, 2) if clk else 0,
        "conv_lpv_lead": round(100 * n_paid / lpv, 1) if lpv else 0,
        "pct_budget_gasto": round(100 * spend / BUDGET, 1),
    },
    "pace": {
        "full_days": n_full,
        "paid_per_day": round(paid_per_day_full, 1),
        "total_per_day": round(total_per_day_full, 1),
        "spend_per_day": round(spend_per_day_full, 2),
        "need_paid_per_day": round(need_paid_per_day, 1),
        "budget_per_day_needed": round(budget_per_day_needed, 2),
        "proj_paid": proj_paid,
        "proj_total": proj_total,
        "proj_spend": proj_spend,
        "on_track_leads": proj_paid >= LEADS_PAGOS_TARGET,
        "on_track_cpl": cpl_real <= CPL_TARGET,
    },
    "series": series,
    "ads": ads,
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# ---------- render index.html (dados embutidos, graficos em SVG nativo -> 100% offline) ----------
base = Path(__file__).parent
tpl = (base / "template.html").read_text()
html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
(base / "index.html").write_text(html)

# ---------- resumo no terminal ----------
print(f"INSCRITOS: {total_inscritos} (meta {TOTAL_TARGET}) | PAGOS: {n_paid} (meta {LEADS_PAGOS_TARGET}) | ORGANICO: {n_org} (meta {ORGANICO_TARGET})")
print(f"MEDICOS: {medicos}/{total_inscritos} ({data['kpis']['pct_medico']}%)")
print(f"SPEND: R$ {spend:,.2f} / R$ {BUDGET:,.0f} ({data['kpis']['pct_budget_gasto']}%) | CPL real: R$ {cpl_real:,.2f} (meta R$ {CPL_TARGET:.0f})")
print(f"LPV: {int(lpv)} | conv LPV->lead pago: {data['kpis']['conv_lpv_lead']}% | CPC: R$ {data['kpis']['cpc']}")
print(f"PACE (dias cheios={n_full}): {paid_per_day_full:.1f} pagos/dia | spend {spend_per_day_full:.0f}/dia")
print(f"DIAS ATE EVENTO (16/06): {days_left}")
print(f"PRECISA: {need_paid_per_day:.1f} pagos/dia p/ bater 240 | budget/dia p/ gastar tudo: R$ {budget_per_day_needed:,.0f}")
print(f"PROJECAO run-rate: {proj_paid} pagos | {proj_total} inscritos | R$ {proj_spend:,.0f} gastos")
print("\n-- por criativo (spend desc) --")
for a in ads:
    cpl = f"R$ {a['cpl']:.0f}" if a['cpl'] else "s/ lead"
    print(f"  {a['ad']:<40} spend R$ {a['spend']:>8,.0f} | {a['leads']:>2} leads | {cpl}")
print(f"\nOK -> {OUT}")
