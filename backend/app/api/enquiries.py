"""POST /enquiries (step 9.6): the traveller hands over to the team from the UI.

Contact details come straight from the form to this table: they never pass through the
graph, the LLM or the traces.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import EnquiryOut, EnquiryRequest
from app.db.models import Conversation, Quote
from app.db.repo import create_enquiry

router = APIRouter(tags=["enquiries"])
THANKS = "Thank you. A travel specialist will get back to you."


@router.post("/enquiries", response_model=EnquiryOut)
def send_enquiry(req: EnquiryRequest, db: Session = Depends(get_db)) -> EnquiryOut:
    quote = db.get(Quote, req.quote_id) if req.quote_id else None
    if req.quote_id and quote is None:
        raise HTTPException(404, "We couldn't find that quote.")
    conv_id = req.conversation_id if req.conversation_id and db.get(Conversation, req.conversation_id) else None
    enquiry = create_enquiry(db, req.kind, quote=quote, conversation_id=conv_id, flags=["from_traveller"],
                             notes=req.notes, contact=req.contact.model_dump() if req.contact else None)
    db.commit()
    return EnquiryOut(enquiry_id=enquiry.id, message=THANKS)
