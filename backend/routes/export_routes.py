"""
Data Export Routes — CSV/PDF export for portfolio and trade data.

Provides:
- Export trade history as CSV
- Export portfolio snapshot as CSV
- Export margin positions as CSV
- Export compliance report as PDF
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import io
import csv

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/trades/csv")
async def export_trades_csv(
    days: int = Query(90, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
):
    """Export user's trade history as CSV."""
    db = get_database()
    uid = current_user["user_id"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data", "Tipo", "Asset", "Quantita", "Prezzo", "Valore EUR", "Fee", "Stato"])

    # NENO transactions
    async for tx in db.neno_transactions.find(
        {"user_id": uid, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("created_at", -1):
        ts = tx.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([
            ts, tx.get("type", ""),
            tx.get("pay_asset", tx.get("receive_asset", "NENO")),
            tx.get("neno_amount", ""),
            tx.get("neno_eur_price", tx.get("rate", "")),
            tx.get("pay_amount", tx.get("receive_amount", "")),
            tx.get("fee", ""),
            tx.get("status", ""),
        ])

    # Trading engine orders
    async for order in db.orders.find(
        {"user_id": uid}, {"_id": 0}
    ).sort("created_at", -1).limit(500):
        ts = order.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([
            ts, order.get("side", ""),
            order.get("pair_id", ""),
            order.get("amount", order.get("quantity", "")),
            order.get("price", ""),
            order.get("total", ""),
            order.get("fee", ""),
            order.get("status", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=trades_{days}d.csv"},
    )


@router.get("/portfolio/csv")
async def export_portfolio_csv(
    current_user: dict = Depends(get_current_user),
):
    """Export user's current portfolio as CSV."""
    db = get_database()
    uid = current_user["user_id"]

    wallets = await db.wallets.find({"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}).to_list(100)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Asset", "Saldo", "Valore Stimato EUR"])

    # Market reference prices
    prices = {
        "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36, "USDT": 0.92,
        "USDC": 0.92, "MATIC": 0.55, "SOL": 74.72, "NENO": 10000.0,
        "EUR": 1.0, "USD": 0.92, "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082,
    }

    total_eur = 0
    for w in wallets:
        asset = w.get("asset", "")
        balance = w.get("balance", 0)
        eur_price = prices.get(asset, 0)
        eur_value = round(balance * eur_price, 2)
        total_eur += eur_value
        writer.writerow([asset, round(balance, 8), eur_value])

    writer.writerow([])
    writer.writerow(["TOTALE", "", round(total_eur, 2)])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=portfolio.csv"},
    )


@router.get("/margin/csv")
async def export_margin_csv(
    current_user: dict = Depends(get_current_user),
):
    """Export user's margin positions as CSV."""
    db = get_database()
    uid = current_user["user_id"]

    positions = await db.margin_positions.find({"user_id": uid}, {"_id": 0}).sort("opened_at", -1).to_list(200)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Data Apertura", "Coppia", "Direzione", "Leva", "Prezzo Entrata", "Margine", "PnL", "Stato"])

    for p in positions:
        ts = p.get("opened_at", p.get("created_at", ""))
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([
            ts, p.get("pair_id", ""),
            p.get("side", ""), p.get("leverage", ""),
            p.get("entry_price", ""), p.get("margin_amount", ""),
            p.get("realized_pnl", p.get("unrealized_pnl", "")),
            p.get("status", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=margin_positions.csv"},
    )



@router.get("/compliance/pdf")
async def export_compliance_pdf(
    days: int = Query(90, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
):
    """Generate a professional PDF compliance report."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    db = get_database()
    uid = current_user["user_id"]
    user = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "role": 1, "kyc_verified": 1, "kyc_tier": 1, "nium_compliance_status": 1})
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Gather data
    wallets = await db.wallets.find({"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}).to_list(100)
    trades_cursor = db.neno_transactions.find({"user_id": uid, "created_at": {"$gte": cutoff}}, {"_id": 0}).sort("created_at", -1)
    trades = await trades_cursor.to_list(200)
    orders = await db.orders.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    margin_positions = await db.margin_positions.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    dca_plans = await db.dca_plans.find({"user_id": uid}, {"_id": 0}).to_list(20)

    prices = {
        "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36, "USDT": 0.92,
        "USDC": 0.92, "MATIC": 0.55, "SOL": 74.72, "NENO": 10000.0,
        "EUR": 1.0, "USD": 0.92, "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082,
    }

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=20, textColor=HexColor("#7c3aed"), spaceAfter=6)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=10, textColor=HexColor("#64748b"), spaceAfter=12)
    heading_style = ParagraphStyle("SectionH", parent=styles["Heading2"], fontSize=13, textColor=HexColor("#1e1b4b"), spaceBefore=16, spaceAfter=6)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)

    elements = []

    # Header
    elements.append(Paragraph("NeoNoble Ramp — Report di Compliance", title_style))
    elements.append(Paragraph(
        f"Utente: {(user or {}).get('email', uid)} | Generato: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')} | Periodo: ultimi {days} giorni",
        subtitle_style
    ))

    # KYC Status
    elements.append(Paragraph("1. Stato KYC / Compliance", heading_style))
    kyc_data = [
        ["Campo", "Valore"],
        ["KYC Verificato", "Si" if (user or {}).get("kyc_verified") else "No"],
        ["Tier KYC", str((user or {}).get("kyc_tier", 0))],
        ["Ruolo", (user or {}).get("role", "USER")],
        ["Compliance NIUM", (user or {}).get("nium_compliance_status", "N/A")],
    ]
    t = Table(kyc_data, colWidths=[150, 300])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7c3aed")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
    ]))
    elements.append(t)

    # Portfolio
    elements.append(Paragraph("2. Portfolio Attuale", heading_style))
    port_data = [["Asset", "Saldo", "Valore EUR"]]
    total_eur = 0
    for w in wallets:
        asset = w.get("asset", "")
        bal = w.get("balance", 0)
        price = prices.get(asset, 0)
        eur = round(bal * price, 2)
        total_eur += eur
        port_data.append([asset, f"{bal:.8f}" if bal < 10 else f"{bal:.2f}", f"EUR {eur:,.2f}"])
    port_data.append(["TOTALE", "", f"EUR {total_eur:,.2f}"])
    t2 = Table(port_data, colWidths=[100, 180, 170])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7c3aed")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, HexColor("#f8fafc")]),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#1e1b4b")),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    elements.append(t2)

    # Trade History (last 20)
    elements.append(Paragraph("3. Storico Transazioni (ultime 20)", heading_style))
    trade_data = [["Data", "Tipo", "Asset", "Quantita", "Prezzo", "Stato"]]
    for tx in (trades + orders)[:20]:
        ts = tx.get("created_at", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%d/%m/%Y")
        elif isinstance(ts, str) and len(ts) > 10:
            ts = ts[:10]
        trade_data.append([
            ts,
            tx.get("type", tx.get("side", "")),
            tx.get("pay_asset", tx.get("pair_id", "")),
            str(tx.get("neno_amount", tx.get("quantity", tx.get("amount", "")))),
            str(tx.get("neno_eur_price", tx.get("price", tx.get("rate", "")))),
            tx.get("status", ""),
        ])
    if len(trade_data) > 1:
        t3 = Table(trade_data, colWidths=[70, 60, 80, 80, 80, 80])
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
        ]))
        elements.append(t3)
    else:
        elements.append(Paragraph("Nessuna transazione nel periodo selezionato.", body_style))

    # Margin Positions
    if margin_positions:
        elements.append(Paragraph("4. Posizioni Margin", heading_style))
        m_data = [["Coppia", "Lato", "Leva", "Entry", "Stato", "PnL"]]
        for p in margin_positions[:15]:
            pnl = p.get("realized_pnl", p.get("unrealized_pnl", 0))
            m_data.append([
                p.get("pair_id", ""), p.get("side", ""), f"{p.get('leverage', '')}x",
                str(p.get("entry_price", "")), p.get("status", ""), f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else str(pnl),
            ])
        t4 = Table(m_data, colWidths=[80, 50, 50, 80, 70, 80])
        t4.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
        ]))
        elements.append(t4)

    # DCA Plans
    if dca_plans:
        elements.append(Paragraph("5. Piani DCA Automatici", heading_style))
        dca_data = [["Asset", "EUR/Exec", "Intervallo", "Esecuzioni", "Investito", "Stato"]]
        for d in dca_plans:
            dca_data.append([
                d.get("asset", ""), f"{d.get('amount_eur', 0):.2f}",
                d.get("interval", ""), str(d.get("total_executions", 0)),
                f"{d.get('total_invested_eur', 0):.2f}", d.get("status", ""),
            ])
        t5 = Table(dca_data, colWidths=[60, 70, 70, 70, 80, 60])
        t5.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
        ]))
        elements.append(t5)

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(
        "Documento generato automaticamente da NeoNoble Ramp per finalita di compliance e fiscali. Non costituisce consulenza finanziaria.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=HexColor("#94a3b8"), alignment=TA_CENTER),
    ))

    doc.build(elements)
    buf.seek(0)
    filename = f"NeoNoble_Compliance_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
