"""NexChecker Platform Engines Package.

Unified access to all e-commerce and quick-commerce registration checkers:
- Zomato (check_zomato)
- Myntra (check_myntra, MyntraChecker, myntra_checker)
- Flipkart (check_flipkart)
- BigBasket (check_bigbasket)
- Meesho (check_meesho)
- Amazon (check_amazon)
- Swiggy (check_swiggy)
- Zepto (check_zepto)
"""
from pathlib import Path
import sys

# Ensure this package directory is on sys.path so intra-package imports work
_DIR = str(Path(__file__).resolve().parent)
_ROOT = str(Path(__file__).resolve().parent.parent)
_NEXBOT = str(Path(__file__).resolve().parent.parent / "NexBot")
for _p in (_DIR, _ROOT, _NEXBOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from core.meesho_api import MeeshoClient, clean_phone
except ImportError:
    from NexBot.core.meesho_api import MeeshoClient, clean_phone

from checkers.zomato_check import check_zomato
from checkers.myntra_check import check_myntra, MyntraChecker, myntra_checker
from checkers.flipkart_check import check_flipkart
from checkers.bigbasket_check import check_bigbasket
from checkers.meesho_check import check_meesho
from checkers.amazon_check import check_amazon
from checkers.swiggy_check import check_swiggy
from checkers.zepto_check import check_zepto

__all__ = [
    "MeeshoClient",
    "clean_phone",
    "check_zomato",
    "check_myntra",
    "MyntraChecker",
    "myntra_checker",
    "check_flipkart",
    "check_bigbasket",
    "check_meesho",
    "check_amazon",
    "check_swiggy",
    "check_zepto",
]
