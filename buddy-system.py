"""A small, in-memory buddy system for pairing up and sharing garden progress.

This demo-friendly storage is local to the process. A deployed app should use a
shared database and add authentication/authorization around these operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4


@dataclass
class BuddyOffer:
    """A buddy offer that can be shared with another user."""

    owner_id: str
    owner_name: str
    description: str
    image_url: Optional[str] = None
    id: UUID = field(default_factory=uuid4)
    recipient_id: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_accepted: bool = False
    owner_confirmed: bool = False

    @property
    def is_mutually_confirmed(self) -> bool:
        return self.recipient_accepted and self.owner_confirmed


@dataclass(frozen=True)
class BuddyCheckIn:
    sender_id: str
    message: str
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)


class BuddyError(Exception):
    """An expected error while managing buddy offers and interactions."""


class OfferNotFound(BuddyError):
    "That buddy offer was not found."


class CannotRequestOwnOffer(BuddyError):
    "You cannot request your own offer."


class OfferUnavailable(BuddyError):
    "This offer already has a recipient."


class OnlyRecipientCanAccept(BuddyError):
    "Only the invited recipient can accept."


class OnlyOwnerCanConfirm(BuddyError):
    "Only the offer owner can confirm."


class BuddiesNotConfirmed(BuddyError):
    "Both people must confirm before sharing gardens."


def _offer_id(value: UUID | str) -> UUID:
    """Accept UUID objects and their string representation."""
    try:
        return value if isinstance(value, UUID) else UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise OfferNotFound() from exc


class BuddySystem:
    """In-memory buddy offers, confirmed garden access, and check-ins."""

    def __init__(self) -> None:
        self.offers: list[BuddyOffer] = []
        self.check_ins: dict[UUID, list[BuddyCheckIn]] = {}
        self._gardens: dict[str, list[str]] = {}

    def set_garden(self, items: list[str], user_id: str) -> None:
        self._gardens[user_id] = list(items)

    def post_offer(
        self,
        owner_id: str,
        owner_name: str,
        description: str,
        image_url: Optional[str] = None,
    ) -> UUID:
        if image_url is not None:
            parsed = urlparse(image_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("image_url must be an absolute http(s) URL or None")
        offer = BuddyOffer(owner_id, owner_name, description, image_url)
        self.offers.append(offer)
        return offer.id

    def _find_offer(self, offer_id: UUID | str) -> BuddyOffer:
        normalized_id = _offer_id(offer_id)
        for offer in self.offers:
            if offer.id == normalized_id:
                return offer
        raise OfferNotFound()

    def request(self, offer_id: UUID | str, recipient_id: str, recipient_name: str) -> None:
        offer = self._find_offer(offer_id)
        if offer.owner_id == recipient_id:
            raise CannotRequestOwnOffer()
        if offer.recipient_id is not None:
            raise OfferUnavailable()
        offer.recipient_id = recipient_id
        offer.recipient_name = recipient_name

    def accept(self, offer_id: UUID | str, as_recipient: str) -> None:
        offer = self._find_offer(offer_id)
        if offer.recipient_id != as_recipient:
            raise OnlyRecipientCanAccept()
        offer.recipient_accepted = True

    def confirm(self, offer_id: UUID | str, as_owner: str) -> None:
        offer = self._find_offer(offer_id)
        if offer.owner_id != as_owner:
            raise OnlyOwnerCanConfirm()
        if not offer.recipient_accepted:
            raise BuddiesNotConfirmed()
        offer.owner_confirmed = True

    def garden(self, garden_owner_id: str, viewed_by: str) -> list[str]:
        """Return a garden only to the other member of a confirmed pair."""
        confirmed_pair = any(
            offer.is_mutually_confirmed
            and (
                (offer.owner_id == garden_owner_id and offer.recipient_id == viewed_by)
                or (offer.recipient_id == garden_owner_id and offer.owner_id == viewed_by)
            )
            for offer in self.offers
        )
        if not confirmed_pair:
            raise BuddiesNotConfirmed()
        return list(self._gardens.get(garden_owner_id, []))

    def check_in(self, offer_id: UUID | str, from_user: str, message: str) -> BuddyCheckIn:
        offer = self._find_offer(offer_id)
        if not offer.is_mutually_confirmed:
            raise BuddiesNotConfirmed()
        if from_user not in (offer.owner_id, offer.recipient_id):
            raise OnlyRecipientCanAccept("Only a member of this buddy pair can check in.")
        entry = BuddyCheckIn(sender_id=from_user, message=message)
        self.check_ins.setdefault(offer.id, []).append(entry)
        return entry


def main() -> None:
    """Run a short end-to-end example when this file is executed directly."""
    buddy_system = BuddySystem()
    buddy_system.set_garden(["Sunflower", "Mint"], user_id="alex")
    offer_id = buddy_system.post_offer(
        owner_id="alex",
        owner_name="Alex",
        description="Looking for a study buddy to check in a few times a week.",
    )

    try:
        buddy_system.request(offer_id, recipient_id="sam", recipient_name="Sam")
        buddy_system.accept(offer_id, as_recipient="sam")
        buddy_system.confirm(offer_id, as_owner="alex")
        buddy_system.check_in(offer_id, from_user="sam", message="I finished my goal today!")
        offer = buddy_system.offers[0]
        print(f"Offer: {offer.description}")
        print(f"Mutually confirmed: {offer.is_mutually_confirmed}")
        print(f"Alex's garden as seen by Sam: {buddy_system.garden('alex', viewed_by='sam')}")
        print(f"Check-ins: {len(buddy_system.check_ins[offer_id])}")
    except BuddyError as error:
        print(f"Buddy demo failed: {error}")


if __name__ == "__main__":
    main()
