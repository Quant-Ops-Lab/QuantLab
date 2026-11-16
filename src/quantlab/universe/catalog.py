"""Curated thematic research universe. Symbols are candidates, NOT validated listings.

Strictly distinguish an investment thesis/research entity from a broker-eligible
security.  Portfolio/instrument validation happens separately before any order.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class AssetKind(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    SAVINGS_BOND = "savings_bond"
    PRIVATE = "private_company"


@dataclass(frozen=True)
class WatchAsset:
    symbol: str
    name: str
    themes: tuple[str, ...]
    kind: AssetKind = AssetKind.EQUITY
    notes: str = ""

    @property
    def intraday_candidate(self) -> bool:
        return self.kind in (AssetKind.EQUITY, AssetKind.ETF)


_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "ai_compute": (("NVDA","Nvidia"),("AMD","AMD"),("MU","Micron"),("AVGO","Broadcom"),
                   ("ARM","Arm Holdings"),("TSM","TSMC"),("QCOM","Qualcomm"),("MRVL","Marvell")),
    "semicap": (("ASML","ASML"),("AMAT","Applied Materials"),("LRCX","Lam Research"),
                ("KLAC","KLA")),
    "storage": (("SNDK","Sandisk"),("WDC","Western Digital"),("STX","Seagate"),
                ("DELL","Dell Technologies"),("HPE","HPE")),
    "cloud_software": (("MSFT","Microsoft"),("GOOGL","Alphabet"),("AMZN","Amazon"),
                       ("ORCL","Oracle"),("META","Meta"),("PLTR","Palantir"),
                       ("SNOW","Snowflake"),("NOW","ServiceNow")),
    "power_cooling": (("VRT","Vertiv"),("ETN","Eaton"),("CEG","Constellation Energy"),
                      ("GEV","GE Vernova")),
    "materials_ceramics": (("ENTG","Entegris"),("MTRN","Materion"),("GLW","Corning")),
    "metals_equity": (("FCX","Freeport-McMoRan"),("MP","MP Materials")),
}
_ETFS: dict[str, tuple[tuple[str,str], ...]] = {
    "semiconductor_etf": (("SMH","VanEck Semiconductor ETF"),("SOXX","iShares Semiconductor ETF")),
    "precious_metals": (("GLD","SPDR Gold Shares"),("IAU","iShares Gold Trust"),
                        ("SLV","iShares Silver Trust"),("SIVR","abrdn Physical Silver Shares"),
                        ("GDX","VanEck Gold Miners ETF")),
    "materials_etf": (("COPX","Global X Copper Miners ETF"),("REMX","VanEck Rare Earth/Strategic Metals ETF")),
    "bond_etf": (("SGOV","iShares 0-3 Month Treasury Bond ETF"),("BIL","SPDR Bloomberg 1-3 Month T-Bill ETF"),
                 ("TLT","iShares 20+ Year Treasury Bond ETF"),("TIP","iShares TIPS Bond ETF")),
}

def default_universe() -> dict[str, WatchAsset]:
    result: dict[str, WatchAsset] = {}
    for groups, kind in ((_GROUPS,AssetKind.EQUITY),(_ETFS,AssetKind.ETF)):
        for theme, entries in groups.items():
            for symbol, name in entries:
                if symbol in result:
                    prev=result[symbol]
                    result[symbol]=WatchAsset(symbol,name,prev.themes+(theme,),kind)
                else:
                    result[symbol]=WatchAsset(symbol,name,(theme,),kind)
    return result


RESEARCH_ONLY = (
    WatchAsset("IBOND", "Series I savings bonds", ("inflation",), AssetKind.SAVINGS_BOND,
               "Not marketable, not executable via intraday broker orders"),
    WatchAsset("COORSTEK", "CoorsTek", ("materials_ceramics",), AssetKind.PRIVATE,
               "Technical ceramics semiconductor supplier; not a listed common stock"),
)


def by_theme(theme: str) -> tuple[WatchAsset,...]:
    return tuple(a for a in default_universe().values() if theme in a.themes)
