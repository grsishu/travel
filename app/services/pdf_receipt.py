import io
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.models import Transaction, PaymentQuote

def generate_pdf_receipt(transaction: Transaction, quote: PaymentQuote = None) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReceiptTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1A73E8'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        'ReceiptSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#5F6368'),
        alignment=1
    )
    bold_style = ParagraphStyle(
        'BoldStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#202124')
    )
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#3C4043')
    )

    elements = []

    # Header
    elements.append(Paragraph("TravelPay", title_style))
    elements.append(Paragraph("International Cross-Border Merchant Payment Receipt", subtitle_style))
    elements.append(Paragraph(f"Transaction ID: {transaction.id}", subtitle_style))
    elements.append(Spacer(1, 15))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#DADCE0'), spaceAfter=15))

    # Payment Status Badge
    status_color = colors.HexColor('#1E8E3E') if transaction.status == "SETTLED" else colors.HexColor('#D93025')
    elements.append(Paragraph(f"<b>STATUS:</b> <font color='{status_color}'>{transaction.status}</font>", bold_style))
    elements.append(Spacer(1, 10))

    # Merchant & Foreign Currency Details
    merchant_name = transaction.merchant_name or (quote.merchant_name if quote else "International Merchant")
    city = transaction.merchant_city or (quote.merchant_city if quote else "Overseas")
    country = transaction.merchant_country or (quote.merchant_country if quote else "Global")
    f_curr = transaction.foreign_currency or (quote.foreign_currency if quote else "USD")
    f_amount = transaction.foreign_amount or (quote.foreign_amount if quote else Decimal("0.00"))

    txn_date = transaction.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    table_data = [
        [Paragraph("Merchant Name", bold_style), Paragraph(merchant_name, normal_style)],
        [Paragraph("Location", bold_style), Paragraph(f"{city}, {country}", normal_style)],
        [Paragraph("Transaction Date", bold_style), Paragraph(txn_date, normal_style)],
        [Paragraph("Foreign Amount", bold_style), Paragraph(f"{f_amount:,.2f} {f_curr}", bold_style)],
    ]

    if quote:
        table_data.extend([
            [Paragraph("Applied FX Rate", bold_style), Paragraph(f"1 INR = {quote.exchange_rate:.4f} {f_curr}", normal_style)],
            [Paragraph("Base INR Equivalent", bold_style), Paragraph(f"INR {quote.inr_base_amount:,.2f}", normal_style)],
            [Paragraph(f"Markup Fee ({quote.markup_percent}%)", bold_style), Paragraph(f"INR {quote.markup_inr:,.2f}", normal_style)],
            [Paragraph(f"GST on Fee ({quote.gst_percent}%)", bold_style), Paragraph(f"INR {quote.gst_inr:,.2f}", normal_style)],
        ])

    table_data.extend([
        [Paragraph("Total INR Paid", bold_style), Paragraph(f"INR {transaction.inr_amount:,.2f}", bold_style)],
        [Paragraph("Payment Rail / Method", bold_style), Paragraph(f"Wallet / Gateway ({transaction.txn_type})", normal_style)],
        [Paragraph("Settlement Rail Ref", bold_style), Paragraph(transaction.settlement_id or "STL-INSTANT-CLEARED", normal_style)],
    ])

    summary_table = Table(table_data, colWidths=[200, 340])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DADCE0')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(summary_table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Regulatory & Compliance Note:</b>", bold_style))
    elements.append(Paragraph(
        "This payment was executed under the RBI Liberalised Remittance Scheme (LRS) framework and FEMA guidelines for overseas retail payments. Foreign currency settled directly to foreign merchant.",
        subtitle_style
    ))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("Thank you for using TravelPay — Zero Forex Hassle Worldwide.", subtitle_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

