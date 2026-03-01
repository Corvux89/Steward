
import logging


log = logging.getLogger(__name__)


def setup(_):
    log.warning("Deprecated module loaded: Steward.cogs.auctionHouse. Use Steward.cogs.raffleHouse instead.")