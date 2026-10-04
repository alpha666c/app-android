"""Atomic fund reservations."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.db.models import LedgerAccount, Reservation


class InsufficientFunds(Exception):
    pass


def _ledger(session: Session, name: str) -> LedgerAccount:
    acct = session.scalar(select(LedgerAccount).where(LedgerAccount.name == name))
    if acct is None:
        acct = LedgerAccount(name=name, balance=Decimal("0"))
        session.add(acct)
        session.flush()
    return acct


def reserve_funds(session: Session, intent_id: int, amount: Decimal) -> None:
    available = _ledger(session, "available")
    reserved = _ledger(session, "reserved")
    if available.balance < amount:
        raise InsufficientFunds(f"need {amount}, have {available.balance}")
    available.balance -= amount
    reserved.balance += amount
    session.add(
        Reservation(intent_id=intent_id, amount=amount, released=False)
    )
    session.flush()


def release_reservation(session: Session, intent_id: int, unused_amount: Decimal) -> None:
    reservation = session.scalar(
        select(Reservation).where(Reservation.intent_id == intent_id)
    )
    if reservation is None or reservation.released:
        return
    available = _ledger(session, "available")
    reserved = _ledger(session, "reserved")
    release = min(unused_amount, reservation.amount)
    reserved.balance -= release
    available.balance += release
    reservation.released = True
    session.flush()


def commit_spend(session: Session, intent_id: int, spent: Decimal) -> None:
    reservation = session.scalar(
        select(Reservation).where(Reservation.intent_id == intent_id)
    )
    if reservation is None:
        return
    reserved = _ledger(session, "reserved")
    reserved.balance -= spent
    refund = reservation.amount - spent
    if refund > 0:
        available = _ledger(session, "available")
        available.balance += refund
    reservation.released = True
    session.flush()
