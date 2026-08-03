"""Natal-chart (kundali) computation: grahas, bhavas, navamsa, dasha, doshas.

Kept separate from :mod:`app.panchang`, which answers "what is the almanac
saying today" for a *place*; this package answers "what does the sky look like
from a *birth*". Both share the same sidereal (Lahiri) longitude source in
:mod:`app.astronomy.core`, so a chart and a ``/v1/nakshatra-at`` call for the
same instant agree on the moon by construction.
"""
