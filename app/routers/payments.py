from datetime import timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, PaymentQuote, Transaction, utcnow
from app.schemas import CreateQuoteRequest, QuoteResponse, ConfirmPaymentRequest, TransactionOut
from app.deps import get_current_user
from app.services.activation import ActivationService
from app.services.quotes import QuoteService
from app.services.payments import PaymentService
from app.services.pdf_receipt import generate_pdf_receipt

router = APIRouter(prefix="/api/payments", tags=["Payments & Transactions"])

@router.post("/quote", response_model=QuoteResponse)
def create_payment_quote(
    payload: CreateQuoteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Strict gate: user must be ACTIVE and KYC VERIFIED to generate a quote
    ActivationService.check_can_pay(db, user, inr_amount=payload.amount)

    try:
        quote = QuoteService.create_quote(
            db=db,
            user=user,
            merchant_name=payload.merchant_name,
            merchant_city=payload.merchant_city,
            merchant_country=payload.merchant_country,
            currency=payload.currency,
            foreign_amount=payload.amount
        )
        now = utcnow()
        rem_sec = max(0, int((quote.expires_at.replace(tzinfo=timezone.utc) - now).total_seconds()))

        return QuoteResponse(
            quote_id=quote.id,
            merchant_name=quote.merchant_name,
            merchant_city=quote.merchant_city,
            merchant_country=quote.merchant_country,
            foreign_currency=quote.foreign_currency,
            foreign_amount=quote.foreign_amount,
            exchange_rate=quote.exchange_rate,
            inr_base_amount=quote.inr_base_amount,
            markup_percent=quote.markup_percent,
            markup_inr=quote.markup_inr,
            gst_percent=quote.gst_percent,
            gst_inr=quote.gst_inr,
            total_inr=quote.total_inr,
            expires_at=quote.expires_at,
            remaining_seconds=rem_sec
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/confirm", response_model=TransactionOut)
def confirm_payment(
    payload: ConfirmPaymentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Fetch and validate quote (120s TTL enforced here)
    quote = QuoteService.get_valid_quote(db, payload.quote_id, user.id)

    # 2. Get device ID from header or default
    device_id = request.headers.get("X-Device-Id", "default_device")

    # 3. Execute payment & settlement
    txn = PaymentService.execute_payment(
        db=db,
        user=user,
        quote=quote,
        pin=payload.pin,
        use_biometric=payload.use_biometric,
        device_id=device_id,
        idempotency_key=payload.idempotency_key
    )

    return TransactionOut(
        id=txn.id,
        txn_type=txn.txn_type,
        status=txn.status,
        merchant_name=txn.merchant_name,
        merchant_city=txn.merchant_city,
        merchant_country=txn.merchant_country,
        foreign_currency=txn.foreign_currency,
        foreign_amount=txn.foreign_amount,
        inr_amount=txn.inr_amount,
        wallet_deduction_inr=txn.wallet_deduction_inr,
        settlement_id=txn.settlement_id,
        settlement_provider=txn.settlement_provider,
        settlement_status=txn.settlement_status,
        failure_reason=txn.failure_reason,
        refund_reason=txn.refund_reason,
        created_at=txn.created_at
    )

@router.get("/{transaction_id}/receipt")
def download_receipt(
    transaction_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id, Transaction.user_id == user.id).first()
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    quote = db.query(PaymentQuote).filter(PaymentQuote.id == txn.quote_id).first() if txn.quote_id else None
    pdf_buffer = generate_pdf_receipt(txn, quote)

    filename = f"TravelPay_Receipt_{txn.id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers=headers)

