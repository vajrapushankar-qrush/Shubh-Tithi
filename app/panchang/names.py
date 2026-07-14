"""Canonical name tables for Panchang elements.

Names are transliterated (IAST-ish, ASCII-friendly). Indices are 0-based
internally; public "numbers" are 1-based where a tradition numbers them
(e.g. tithi 1..30, nakshatra 1..27).
"""
from __future__ import annotations

# --- Tithi -----------------------------------------------------------------
# 30 tithis per lunar month: 15 in Shukla paksha (waxing) then 15 in Krishna
# paksha (waning). The 15th of Shukla is Purnima; the 15th (30th overall) of
# Krishna is Amavasya.
_TITHI_BASE = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
]


def tithi_name(number: int) -> str:
    """number is 1..30."""
    idx = (number - 1) % 15
    if idx < 14:
        base = _TITHI_BASE[idx]
    else:  # 15th of a paksha
        base = "Purnima" if number == 15 else "Amavasya"
    return base


def tithi_paksha(number: int) -> str:
    return "Shukla" if number <= 15 else "Krishna"


# --- Nakshatra (27) --------------------------------------------------------
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

# --- Yoga (27) -------------------------------------------------------------
YOGAS = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti",
]

# --- Karana (11 types over 60 half-tithis) --------------------------------
# 7 "movable" karanas repeat 8 times filling the middle, bracketed by 4 fixed
# karanas. Standard sequence over the 60 half-tithis of a lunar month:
#   half-tithi 1 (index 0)        -> Kimstughna (fixed)
#   half-tithis 2..57 (idx 1..56) -> repeating cycle of the 7 movable
#   half-tithis 58..60 (idx 57..59) -> Shakuni, Chatushpada, Naga (fixed)
_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
_FIXED_FIRST = "Kimstughna"
_FIXED_LAST = ["Shakuni", "Chatushpada", "Naga"]

# Vishti karana == Bhadra. Track its name for the Bhadra convenience field.
VISHTI = "Vishti"


def karana_name(half_tithi_index: int) -> str:
    """half_tithi_index is 0..59 within a lunar month (0 = first half of
    Shukla Pratipada)."""
    i = half_tithi_index % 60
    if i == 0:
        return _FIXED_FIRST
    if i >= 57:
        return _FIXED_LAST[i - 57]
    # indices 1..56 -> movable cycle; (i-1) % 7 into the 7 movable karanas
    return _MOVABLE[(i - 1) % 7]


# --- Vara / weekday --------------------------------------------------------
# Index 0 = Sunday (matches Python date.weekday()+1 handling below).
VARAS = [
    "Ravivara", "Somavara", "Mangalavara", "Budhavara",
    "Guruvara", "Shukravara", "Shanivara",
]
VARA_ENGLISH = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]

# --- Rashi (12 sidereal signs) --------------------------------------------
RASHIS = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]

# --- Lunar months (12, amanta ordering starting Chaitra) ------------------
LUNAR_MONTHS = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashwina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna",
]

# --- Samvatsara (60-year Jovian cycle) ------------------------------------
SAMVATSARAS = [
    "Prabhava", "Vibhava", "Shukla", "Pramoda", "Prajapati", "Angirasa",
    "Shrimukha", "Bhava", "Yuva", "Dhata", "Ishvara", "Bahudhanya",
    "Pramadi", "Vikrama", "Vrisha", "Chitrabhanu", "Svabhanu", "Tarana",
    "Parthiva", "Vyaya", "Sarvajit", "Sarvadhari", "Virodhi", "Vikriti",
    "Khara", "Nandana", "Vijaya", "Jaya", "Manmatha", "Durmukhi",
    "Hevilambi", "Vilambi", "Vikari", "Sharvari", "Plava", "Shubhakritu",
    "Shobhakritu", "Krodhi", "Vishvavasu", "Parabhava", "Plavanga",
    "Kilaka", "Saumya", "Sadharana", "Virodhikritu", "Paridhavi",
    "Pramadicha", "Ananda", "Rakshasa", "Nala", "Pingala", "Kalayukti",
    "Siddharthi", "Raudra", "Durmati", "Dundubhi", "Rudhirodgari",
    "Raktakshi", "Krodhana", "Akshaya",
]

# --- Solar (sankranti-based) month names by regional tradition ------------
# Ordered by the sidereal sign the Sun enters (0 = Mesha/Aries ingress).
TAMIL_MONTHS = [
    "Chithirai", "Vaikasi", "Aani", "Aadi", "Aavani", "Purattasi",
    "Aippasi", "Kaarthigai", "Maargazhi", "Thai", "Maasi", "Panguni",
]
MALAYALAM_MONTHS = [
    "Medam", "Edavam", "Mithunam", "Karkidakam", "Chingam", "Kanni",
    "Thulam", "Vrischikam", "Dhanu", "Makaram", "Kumbham", "Meenam",
]
# Bengali solar year begins at Mesha ingress with Boishakh.
BENGALI_MONTHS = [
    "Boishakh", "Jyoishtho", "Asharh", "Shrabon", "Bhadro", "Ashwin",
    "Kartik", "Ogrohayon", "Poush", "Magh", "Falgun", "Choitro",
]
