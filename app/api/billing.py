"""Billing API — invoices, upcoming invoice, Stripe webhook."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.billing.service import billing_service
from app.billing.webhook_handler import stripe_webhook_handler
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/invoices")
async def list_invoices(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List invoices for the organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    invoices = await billing_service.list_invoices(
        organization_id=str(current_user.organization_id),
        db=db,
        limit=limit,
    )
    return [
        {
            "id": str(inv.id),
            "stripe_invoice_id": inv.stripe_invoice_id,
            "amount_due": float(inv.amount_due),
            "amount_paid": float(inv.amount_paid),
            "currency": inv.currency,
            "status": inv.status,
            "invoice_pdf": inv.invoice_pdf,
            "hosted_invoice_url": inv.hosted_invoice_url,
            "period_start": inv.period_start.isoformat() if inv.period_start else None,
            "period_end": inv.period_end.isoformat() if inv.period_end else None,
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
            "created_at": inv.created_at.isoformat(),
        }
        for inv in invoices
    ]


@router.get("/upcoming-invoice")
async def upcoming_invoice(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get upcoming invoice details from Stripe."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    invoice = await billing_service.get_upcoming_invoice(
        organization_id=str(current_user.organization_id),
        db=db,
    )
    if not invoice:
        return {"message": "No upcoming invoice"}
    return invoice


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook endpoint — receives and processes all Stripe events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_webhook_handler.verify_signature(payload, sig_header)
    except ValueError as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        result = await stripe_webhook_handler.handle(event, db)
        return result
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        # Return 200 to prevent Stripe retries for non-recoverable errors
        return {"status": "error", "message": str(e)}
